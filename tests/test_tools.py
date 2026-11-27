"""Tests for tools/linkmetrics.py and an end-to-end run of the MAVLink proxy."""
import argparse
import os
import socket
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from linkmetrics import JitterEstimator, LossCounter, Summary  # noqa: E402


class LossCounterTest(unittest.TestCase):
    def test_gap(self):
        c = LossCounter(8)
        for s in (0, 1, 2, 5, 6):
            c.update(s)
        self.assertEqual(c.lost, 2)

    def test_wrap(self):
        c = LossCounter(8)
        for s in (254, 255, 1):
            c.update(s)
        self.assertEqual(c.lost, 1)

    def test_reorder_corrects_loss(self):
        c = LossCounter(8)
        for s in (0, 1, 3, 2, 4):
            c.update(s)
        self.assertEqual(c.lost, 0)
        self.assertEqual(c.reordered, 1)

    def test_duplicate(self):
        c = LossCounter(8)
        for s in (0, 1, 1, 2):
            c.update(s)
        self.assertEqual(c.duplicates, 1)
        self.assertEqual(c.received, 3)
        self.assertEqual(c.lost, 0)


class JitterTest(unittest.TestCase):
    def test_constant_delay_has_no_jitter(self):
        j = JitterEstimator()
        for i in range(100):
            j.update(i * 0.1, i * 0.1 + 0.05)
        self.assertAlmostEqual(j.jitter, 0.0)

    def test_alternating_delay(self):
        j = JitterEstimator()
        for i in range(500):
            j.update(i * 0.1, i * 0.1 + (0.02 if i % 2 else 0.0))
        self.assertAlmostEqual(j.jitter, 0.02, places=3)


class SummaryTest(unittest.TestCase):
    def test_summary(self):
        s = Summary.of(range(1, 101))
        self.assertEqual(s.n, 100)
        self.assertAlmostEqual(s.p50, 50.5)
        self.assertEqual(s.max, 100)


try:
    from pymavlink.dialects.v20 import ardupilotmega as mavlink2
except ImportError:  # pragma: no cover
    mavlink2 = None


@unittest.skipIf(mavlink2 is None, "pymavlink not installed")
class ProxyEndToEndTest(unittest.TestCase):
    """Fake vehicle -> proxy (10 % loss, 30 ms delay) -> fake GCS."""

    def test_loss_and_delay_are_applied_and_measured(self):
        import mavlink_link_proxy as mp

        gcs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        gcs.bind(("127.0.0.1", 0))
        gcs.settimeout(0.2)
        gcs_port = gcs.getsockname()[1]

        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        listen_port = probe.getsockname()[1]
        probe.close()

        args = argparse.Namespace(
            listen=listen_port, forward=f"127.0.0.1:{gcs_port}", delay=30.0, jitter=0.0, loss=10.0,
            loss_up=0.0, burst=None, duration=4.0, csv=None, quiet=True, seed=3)
        proxy = mp.LinkProxy(args)
        th = threading.Thread(target=proxy.run, daemon=True)
        th.start()

        veh = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        enc = mavlink2.MAVLink(None, srcSystem=1, srcComponent=1)
        sent_t = {}
        n = 400
        for i in range(n):
            msg = enc.attitude_encode(i * 10, 0, 0, 0, 0, 0, 0)
            veh.sendto(msg.pack(enc), ("127.0.0.1", listen_port))
            enc.seq = (enc.seq + 1) % 256
            sent_t[i * 10] = time.time()
            time.sleep(0.005)

        dec = mavlink2.MAVLink(None)
        got, delays = 0, []
        deadline = time.time() + 2
        while time.time() < deadline:
            try:
                data = gcs.recv(4096)
            except socket.timeout:
                continue
            for m in dec.parse_buffer(data) or []:
                got += 1
                delays.append(time.time() - sent_t[m.time_boot_ms])
        th.join(timeout=5)

        down = proxy.stats["down"]
        self.assertGreater(down.dropped_by_proxy, 20)            # ~10 % of 400
        self.assertLess(down.dropped_by_proxy, 70)
        self.assertEqual(got, n - down.dropped_by_proxy)
        self.assertAlmostEqual(down.lost, down.dropped_by_proxy, delta=2)  # measured == injected
        self.assertGreater(min(delays), 0.025)                    # 30 ms delay applied


if __name__ == "__main__":
    unittest.main()
