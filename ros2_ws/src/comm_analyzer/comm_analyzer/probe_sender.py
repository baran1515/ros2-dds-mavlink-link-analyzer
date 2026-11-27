"""Ground-unit side probe: publishes /probe/ping, measures RTT from /probe/pong.

Parameters
  rate_hz        probe rate (default 50 - similar to a fast telemetry stream)
  payload_bytes  padding per probe (default 64)
  reliability    reliable | best_effort
  depth          KEEP_LAST history depth
  timeout_s      a probe without answer after this time counts as lost
  csv            optional path; one row of statistics per second

Publishes diagnostic_msgs/DiagnosticArray on /link/diagnostics every second.
"""
import csv
import os
import time

import rclpy
from builtin_interfaces.msg import Time
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from rclpy.node import Node

from comm_analyzer.linkmetrics import JitterEstimator, Summary
from comm_analyzer.qos import make_qos
from comm_interfaces.msg import Probe


def to_ns(t: Time) -> int:
    return t.sec * 1_000_000_000 + t.nanosec


class ProbeSender(Node):
    def __init__(self):
        super().__init__("probe_sender")
        self.rate = self.declare_parameter("rate_hz", 50.0).value
        self.payload = bytes(self.declare_parameter("payload_bytes", 64).value)
        rel = self.declare_parameter("reliability", "reliable").value
        depth = self.declare_parameter("depth", 10).value
        self.timeout_ns = int(self.declare_parameter("timeout_s", 1.0).value * 1e9)
        csv_path = self.declare_parameter("csv", "none").value

        qos = make_qos(rel, depth)
        self.pub = self.create_publisher(Probe, "/probe/ping", qos)
        self.sub = self.create_subscription(Probe, "/probe/pong", self.on_pong, qos)
        self.diag_pub = self.create_publisher(DiagnosticArray, "/link/diagnostics", 10)
        self.create_timer(1.0 / self.rate, self.send_probe)
        self.create_timer(1.0, self.report)

        self.seq = 0
        self.outstanding: dict[int, int] = {}   # seq -> send time ns
        self.sent = self.received = self.lost = self.late = 0
        self.rtts_ms: list[float] = []
        self.window_ms: list[float] = []
        self.jitter = JitterEstimator()
        self.t0 = time.monotonic()
        self.qos_desc = f"{rel}/depth={depth}"

        self.writer = None
        if csv_path and csv_path != "none":
            os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
            self._fh = open(csv_path, "w", newline="")
            self.writer = csv.writer(self._fh)
            self.writer.writerow(["t_s", "qos", "rate_hz", "payload_b", "sent", "received", "lost",
                                  "loss_pct", "late", "rtt_p50_ms", "rtt_p95_ms", "rtt_max_ms", "jitter_ms"])
        self.get_logger().info(f"probing at {self.rate} Hz, {len(self.payload)} B, QoS {self.qos_desc}")

    def send_probe(self):
        now = self.get_clock().now()
        msg = Probe(seq=self.seq, stamp=now.to_msg(), payload=self.payload)
        self.outstanding[self.seq] = now.nanoseconds
        self.pub.publish(msg)
        self.seq = (self.seq + 1) & 0xFFFFFFFF
        self.sent += 1

    def on_pong(self, msg: Probe):
        now_ns = self.get_clock().now().nanoseconds
        sent_ns = self.outstanding.pop(msg.seq, None)
        if sent_ns is None:
            self.late += 1           # answer after timeout (already counted lost) or duplicate
            return
        rtt = (now_ns - sent_ns) / 1e6
        self.received += 1
        self.rtts_ms.append(rtt)
        self.window_ms.append(rtt)
        self.jitter.update(sent_ns / 1e9, now_ns / 1e9)

    def expire(self):
        now_ns = self.get_clock().now().nanoseconds
        expired = [s for s, t in self.outstanding.items() if now_ns - t > self.timeout_ns]
        for s in expired:
            del self.outstanding[s]
        self.lost += len(expired)

    def report(self):
        self.expire()
        s = Summary.of(self.window_ms)
        total = self.received + self.lost
        loss = 100.0 * self.lost / total if total else 0.0
        t = time.monotonic() - self.t0
        self.get_logger().info(f"RTT {s.fmt()} | loss {loss:.2f}% ({self.lost}/{total}) "
                               f"| jitter {self.jitter.jitter * 1000:.2f} ms | late {self.late}")

        st = DiagnosticStatus(name="dds_link", hardware_id=self.qos_desc)
        st.level = DiagnosticStatus.OK if loss < 1 else (DiagnosticStatus.WARN if loss < 5 else DiagnosticStatus.ERROR)
        st.message = f"loss {loss:.2f}%, rtt p95 {s.p95:.1f} ms"
        st.values = [KeyValue(key=k, value=str(v)) for k, v in (
            ("rtt_p50_ms", round(s.p50, 2)), ("rtt_p95_ms", round(s.p95, 2)), ("rtt_max_ms", round(s.max, 2)),
            ("loss_pct", round(loss, 3)), ("jitter_ms", round(self.jitter.jitter * 1000, 3)),
            ("sent", self.sent), ("received", self.received), ("lost", self.lost))]
        arr = DiagnosticArray(status=[st])
        arr.header.stamp = self.get_clock().now().to_msg()
        self.diag_pub.publish(arr)

        if self.writer:
            self.writer.writerow([round(t, 1), self.qos_desc, self.rate, len(self.payload), self.sent,
                                  self.received, self.lost, round(loss, 3), self.late, round(s.p50, 2),
                                  round(s.p95, 2), round(s.max, 2), round(self.jitter.jitter * 1000, 3)])
            self._fh.flush()
        self.window_ms = []


def main():
    rclpy.init()
    node = ProbeSender()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        s = Summary.of(node.rtts_ms)
        node.get_logger().info(f"FINAL RTT {s.fmt()} lost {node.lost} of {node.sent}")
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
