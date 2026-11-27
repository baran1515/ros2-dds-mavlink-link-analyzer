"""Build rclpy QoS profiles from simple string parameters."""
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy,
                       qos_profile_sensor_data)


def make_qos(reliability: str = "reliable", depth: int = 10, durability: str = "volatile") -> QoSProfile:
    if reliability == "sensor":
        return qos_profile_sensor_data
    rel = {"reliable": ReliabilityPolicy.RELIABLE,
           "best_effort": ReliabilityPolicy.BEST_EFFORT}[reliability]
    dur = {"volatile": DurabilityPolicy.VOLATILE,
           "transient_local": DurabilityPolicy.TRANSIENT_LOCAL}[durability]
    return QoSProfile(reliability=rel, durability=dur, history=HistoryPolicy.KEEP_LAST, depth=depth)
