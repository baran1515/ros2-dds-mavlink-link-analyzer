"""Vehicle side probe reflector: /probe/ping -> /probe/pong (unchanged)."""
import rclpy
from rclpy.node import Node

from comm_analyzer.qos import make_qos
from comm_interfaces.msg import Probe


class ProbeEcho(Node):
    def __init__(self):
        super().__init__("probe_echo")
        rel = self.declare_parameter("reliability", "reliable").value
        depth = self.declare_parameter("depth", 10).value
        qos = make_qos(rel, depth)
        self.pub = self.create_publisher(Probe, "/probe/pong", qos)
        self.create_subscription(Probe, "/probe/ping", self.pub.publish, qos)
        self.get_logger().info(f"echoing /probe/ping -> /probe/pong (QoS {rel}/depth={depth})")


def main():
    rclpy.init()
    node = ProbeEcho()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
