#!/usr/bin/env bash
# Terminal 1: Micro XRCE-DDS agent (UDP 2019)  |  Terminal 2: ArduCopter SITL with DDS.
#
#   ./scripts/start_sitl_dds.sh agent
#   ./scripts/start_sitl_dds.sh sitl
#
# SITL also outputs MAVLink on UDP 14550 for the packet analyser / QGroundControl.
set -euo pipefail
AP=${ARDUPILOT_HOME:-$HOME/ardupilot}
WS=${ROS2_AP_WS:-$HOME/ros2_ap_ws}
case "${1:-}" in
  agent)
    # shellcheck disable=SC1091
    source /opt/ros/humble/setup.bash && source "$WS/install/setup.bash"
    exec ros2 run micro_ros_agent micro_ros_agent udp4 -p 2019
    ;;
  sitl)
    cd "$AP"
    exec Tools/autotest/sim_vehicle.py -v ArduCopter --enable-dds --no-rebuild \
         --out udp:127.0.0.1:14550 --console
    ;;
  *) echo "usage: $0 {agent|sitl}"; exit 2 ;;
esac
