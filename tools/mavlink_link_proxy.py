#!/usr/bin/env python3
"""MAVLink UDP link proxy: impairment injection + real-time packet analysis.

Sits between ArduPilot SITL and the ground side and forwards MAVLink in both
directions while it

  * delays packets (fixed delay + random jitter), drops them (uniform or
    Gilbert-Elliott burst loss) - a user-space alternative to `tc netem`
    that also works on macOS/Windows and can be scripted per experiment,
  * parses every packet (pymavlink) and reports per direction: packets/s,
    bytes/s, loss from MAVLink sequence numbers, reordering, per-message
    rates and RFC 3550 jitter from the vehicle's own time_boot_ms stamps.

    SITL --udp:127.0.0.1:14550--> [proxy] --udp:127.0.0.1:14560--> GCS / ROS bridge

  sim_vehicle.py -v ArduCopter --out udp:127.0.0.1:14550
  python3 tools/mavlink_link_proxy.py --listen 14550 --forward 127.0.0.1:14560 \
          --delay 80 --jitter 20 --loss 2 --csv results/proxy_degraded.csv
  QGroundControl / mavproxy: udpin:0.0.0.0:14560

requires: pip install pymavlink
"""
from __future__ import annotations

import argparse
import csv
import heapq
import itertools
import os
import random
import select
import socket
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from linkmetrics import JitterEstimator, LossCounter, Summary  # noqa: E402

from pymavlink.dialects.v20 import ardupilotmega as mavlink2  # noqa: E402


class Impairment:
    """Delay / jitter / loss model for one direction."""

    def __init__(self, delay_ms=0.0, jitter_ms=0.0, loss_pct=0.0, ge=None, seed=1):
        self.delay = delay_ms / 1000.0
        self.jitter = jitter_ms / 1000.0
        self.loss = loss_pct / 100.0
        self.ge = ge            # (p_good_to_bad, p_bad_to_good, loss_in_bad)
        self.bad = False
        self.rng = random.Random(seed)

    def drop(self) -> bool:
        if self.ge:
            p_gb, p_bg, loss_bad = self.ge
            self.bad = (self.rng.random() >= p_bg) if self.bad else (self.rng.random() < p_gb)
            if self.bad and self.rng.random() < loss_bad:
                return True
        return self.rng.random() < self.loss

    def latency(self) -> float:
        return max(0.0, self.delay + self.rng.uniform(-self.jitter, self.jitter))


class DirectionStats:
    def __init__(self, name):
        self.name = name
        self.parser = mavlink2.MAVLink(None)
        self.parser.robust_parsing = True
        self.loss: dict[tuple[int, int], LossCounter] = {}
        self.jitter: dict[str, JitterEstimator] = {}
        self.types = Counter()
        self.pkts = self.bytes = self.dropped_by_proxy = 0
        self.applied_delay_ms: list[float] = []
        self.win_pkts = self.win_bytes = 0

    def observe(self, data: bytes, recv_t: float) -> None:
        self.bytes += len(data)
        self.win_bytes += len(data)
        try:
            msgs = self.parser.parse_buffer(data) or []
        except mavlink2.MAVError:
            msgs = []
        for m in msgs:
            if m.get_type() == "BAD_DATA":
                continue
            self.pkts += 1
            self.win_pkts += 1
            h = m.get_header()
            self.loss.setdefault((h.srcSystem, h.srcComponent), LossCounter(8)).update(h.seq)
            t = m.get_type()
            self.types[t] += 1
            tb = getattr(m, "time_boot_ms", None)
            if tb is not None:
                self.jitter.setdefault(t, JitterEstimator()).update(tb / 1000.0, recv_t)

    @property
    def lost(self):
        return sum(c.lost for c in self.loss.values())

    @property
    def reordered(self):
        return sum(c.reordered for c in self.loss.values())

    @property
    def loss_pct(self):
        rx = sum(c.received for c in self.loss.values())
        return 100.0 * self.lost / (rx + self.lost) if rx + self.lost else 0.0


class LinkProxy:
    def __init__(self, args):
        self.args = args
        self.vehicle_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.vehicle_sock.bind(("0.0.0.0", args.listen))
        self.gcs_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.gcs_sock.bind(("0.0.0.0", 0))
        host, port = args.forward.rsplit(":", 1)
        self.gcs_addr = (host, int(port))
        self.vehicle_addr = None
        ge = tuple(args.burst) if args.burst else None
        self.imp = {
            "down": Impairment(args.delay, args.jitter, args.loss, ge, seed=args.seed),
            "up": Impairment(args.delay, args.jitter, args.loss_up if args.loss_up is not None else args.loss,
                             ge, seed=args.seed + 1),
        }
        self.stats = {"down": DirectionStats("down (vehicle->gcs)"), "up": DirectionStats("up (gcs->vehicle)")}
        self.queue: list = []
        self._tie = itertools.count()
        self.running = True
        self.writer = None
        if args.csv:
            os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
            self._fh = open(args.csv, "w", newline="")
            self.writer = csv.writer(self._fh)
            self.writer.writerow(["t_s", "dir", "pkts_s", "bytes_s", "lost_total", "loss_pct",
                                  "reordered", "proxy_drops", "att_jitter_ms", "delay_p50_ms", "delay_p95_ms"])

    def _enqueue(self, direction, data, now):
        st, imp = self.stats[direction], self.imp[direction]
        if imp.drop():
            st.dropped_by_proxy += 1
            return
        lat = imp.latency()
        st.applied_delay_ms.append(lat * 1000)
        heapq.heappush(self.queue, (now + lat, next(self._tie), direction, data))

    def _flush(self, now):
        while self.queue and self.queue[0][0] <= now:
            _, _, direction, data = heapq.heappop(self.queue)
            if direction == "down":
                self.gcs_sock.sendto(data, self.gcs_addr)
                self.stats["down"].observe(data, now)   # what the GCS actually receives
            elif self.vehicle_addr:
                self.vehicle_sock.sendto(data, self.vehicle_addr)
                self.stats["up"].observe(data, now)

    def report(self, t, dt):
        for key, st in self.stats.items():
            jit = st.jitter.get("ATTITUDE")
            d = Summary.of(st.applied_delay_ms[-500:])
            row = [round(t, 1), key, round(st.win_pkts / dt, 1), round(st.win_bytes / dt),
                   st.lost, round(st.loss_pct, 2), st.reordered, st.dropped_by_proxy,
                   round(jit.jitter * 1000, 2) if jit else "", round(d.p50, 1), round(d.p95, 1)]
            if self.writer:
                self.writer.writerow(row)
            if not self.args.quiet:
                print(f"[{t:6.1f}s] {st.name:<20} {row[2]:>6} pkt/s {row[3]:>7} B/s  "
                      f"loss {row[5]:>5}% (lost {st.lost}, reord {st.reordered})  "
                      f"att-jitter {row[8] or '-'} ms  delay p95 {row[10]} ms")
            st.win_pkts = st.win_bytes = 0
        if self.writer:
            self._fh.flush()

    def run(self):
        t0 = last = time.time()
        while self.running:
            now = time.time()
            timeout = 0.01
            if self.queue:
                timeout = max(0.0, min(timeout, self.queue[0][0] - now))
            r, _, _ = select.select([self.vehicle_sock, self.gcs_sock], [], [], timeout)
            now = time.time()
            for s in r:
                try:
                    data, addr = s.recvfrom(65535)
                except (ConnectionResetError, OSError):
                    continue
                if s is self.vehicle_sock:
                    self.vehicle_addr = addr
                    self._enqueue("down", data, now)
                else:
                    self._enqueue("up", data, now)
            self._flush(now)
            if now - last >= 1.0:
                self.report(now - t0, now - last)
                last = now
            if self.args.duration and now - t0 >= self.args.duration:
                break
        self.summary()

    def summary(self):
        print("\n=== summary ===")
        for st in self.stats.values():
            top = ", ".join(f"{k}:{v}" for k, v in st.types.most_common(6))
            print(f"{st.name}: {st.pkts} pkts, lost {st.lost} ({st.loss_pct:.2f}%), "
                  f"reordered {st.reordered}, proxy drops {st.dropped_by_proxy}")
            print(f"  applied delay: {Summary.of(st.applied_delay_ms).fmt()}")
            print(f"  top messages: {top}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listen", type=int, default=14550, help="UDP port SITL sends to")
    ap.add_argument("--forward", default="127.0.0.1:14560", help="ground side host:port")
    ap.add_argument("--delay", type=float, default=0.0, help="one-way delay ms")
    ap.add_argument("--jitter", type=float, default=0.0, help="+/- uniform jitter ms")
    ap.add_argument("--loss", type=float, default=0.0, help="uniform loss %% (both directions)")
    ap.add_argument("--loss-up", type=float, help="override loss %% for gcs->vehicle")
    ap.add_argument("--burst", type=float, nargs=3, metavar=("P_GB", "P_BG", "LOSS_BAD"),
                    help="Gilbert-Elliott burst loss, e.g. 0.01 0.3 0.8")
    ap.add_argument("--duration", type=float, default=0)
    ap.add_argument("--csv")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)
    try:
        LinkProxy(args).run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
