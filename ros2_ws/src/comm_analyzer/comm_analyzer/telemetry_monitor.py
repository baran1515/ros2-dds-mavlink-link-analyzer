"""Monitor an ArduPilot DDS telemetry topic (default: GPS fix from SITL).

ArduPilot (4.5+) built with `--enable-dds` publishes ROS 2 topics through the
Micro XRCE-DDS agent, e.g. /ap/navsat/navsat0 (sensor_msgs/NavSatFix).
This node measures what reaches the ground side:

  * receive rate [Hz] vs expected rate
  * inter-arrival gaps (p95 / max) -> stalls caused by delay or loss
  * message age (now - header.stamp); meaningful when both sides use the
    same clock (use_sim_time with /clock, or NTP/chrony across machines)

Parameters: topic, expected_hz, qos (sensor | reliable | best_effort), csv
"""
import csv
import os
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix

from comm_analyzer.linkmetrics import Summary
from comm_analyzer.qos import make_qos


class TelemetryMonitor(Node):
    def __init__(self):
        super().__init__("telemetry_monitor")
        topic = self.declare_parameter("topic", "/ap/navsat/navsat0").value
        self.expected = self.declare_parameter("expected_hz", 5.0).value
        qos = make_qos(self.declare_parameter("qos", "sensor").value)
        csv_path = self.declare_parameter("csv", "none").value

        self.create_subscription(NavSatFix, topic, self.on_msg, qos)
        self.diag = self.create_publisher(DiagnosticArray, "/link/telemetry_diagnostics", 10)
        self.create_timer(1.0, self.report)
        self.last_rx = None
        self.gaps_ms: list[float] = []
        self.ages_ms: list[float] = []
        self.count = 0
        self.total = 0
        self.t0 = time.monotonic()
        self.writer = None
        if csv_path and csv_path != "none":
            os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
            self._fh = open(csv_path, "w", newline="")
            self.writer = csv.writer(self._fh)
            self.writer.writerow(["t_s", "rate_hz", "gap_p95_ms", "gap_max_ms", "age_p50_ms", "lat", "lon", "alt"])
        self.last_fix = None
        self.get_logger().info(f"monitoring {topic} (expected {self.expected} Hz)")

    def on_msg(self, msg: NavSatFix):
        now = self.get_clock().now()
        mono = time.monotonic()
        if self.last_rx is not None:
            self.gaps_ms.append((mono - self.last_rx) * 1000)
        self.last_rx = mono
        stamp_ns = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
        if stamp_ns:
            self.ages_ms.append((now.nanoseconds - stamp_ns) / 1e6)
        self.count += 1
        self.total += 1
        self.last_fix = msg

    def report(self):
        rate = float(self.count)
        g, a = Summary.of(self.gaps_ms), Summary.of(self.ages_ms)
        stalled = self.last_rx is None or time.monotonic() - self.last_rx > 1.0
        st = DiagnosticStatus(name="ardupilot_dds_telemetry")
        if stalled:
            st.level, st.message = DiagnosticStatus.ERROR, "no telemetry for > 1 s"
        elif rate < 0.8 * self.expected or g.max > 1000:
            st.level, st.message = DiagnosticStatus.WARN, f"degraded: {rate:.0f} Hz, max gap {g.max:.0f} ms"
        else:
            st.level, st.message = DiagnosticStatus.OK, f"{rate:.0f} Hz"
        st.values = [KeyValue(key="rate_hz", value=f"{rate:.1f}"),
                     KeyValue(key="gap_p95_ms", value=f"{g.p95:.1f}"),
                     KeyValue(key="gap_max_ms", value=f"{g.max:.1f}"),
                     KeyValue(key="age_p50_ms", value=f"{a.p50:.1f}")]
        arr = DiagnosticArray(status=[st])
        arr.header.stamp = self.get_clock().now().to_msg()
        self.diag.publish(arr)
        self.get_logger().info(f"{st.message} | gap {g.fmt()}")
        if self.writer:
            f = self.last_fix
            self.writer.writerow([round(time.monotonic() - self.t0, 1), rate, round(g.p95, 1), round(g.max, 1),
                                  round(a.p50, 1), f.latitude if f else "", f.longitude if f else "",
                                  f.altitude if f else ""])
            self._fh.flush()
        self.count = 0
        self.gaps_ms, self.ages_ms = [], []


def main():
    rclpy.init()
    node = TelemetryMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
