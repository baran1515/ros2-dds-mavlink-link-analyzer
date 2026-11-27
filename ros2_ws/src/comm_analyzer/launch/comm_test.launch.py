"""Start both ends of the DDS link test (and optionally the telemetry monitor).

ros2 launch comm_analyzer comm_test.launch.py reliability:=best_effort rate_hz:=100 \
     payload_bytes:=256 csv:=results/ros2_best_effort.csv monitor:=true
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    args = {
        "reliability": "reliable",
        "depth": "10",
        "rate_hz": "50.0",
        "payload_bytes": "64",
        "timeout_s": "1.0",
        "csv": "none",
        "monitor": "false",
        "telemetry_topic": "/ap/navsat/navsat0",
    }
    decl = [DeclareLaunchArgument(k, default_value=v) for k, v in args.items()]
    cfg = {k: LaunchConfiguration(k) for k in args}

    echo = Node(package="comm_analyzer", executable="probe_echo", name="probe_echo",
                parameters=[{"reliability": cfg["reliability"], "depth": cfg["depth"]}])
    sender = Node(package="comm_analyzer", executable="probe_sender", name="probe_sender", output="screen",
                  parameters=[{"reliability": cfg["reliability"], "depth": cfg["depth"],
                               "rate_hz": cfg["rate_hz"], "payload_bytes": cfg["payload_bytes"],
                               "timeout_s": cfg["timeout_s"], "csv": cfg["csv"]}])
    monitor = Node(package="comm_analyzer", executable="telemetry_monitor", name="telemetry_monitor",
                   output="screen", condition=IfCondition(cfg["monitor"]),
                   parameters=[{"topic": cfg["telemetry_topic"]}])
    return LaunchDescription(decl + [echo, sender, monitor])
