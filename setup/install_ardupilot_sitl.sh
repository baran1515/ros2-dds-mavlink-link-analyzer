#!/usr/bin/env bash
# ArduPilot SITL with DDS (Micro XRCE-DDS client) enabled + Micro XRCE-DDS agent.
# Reference: ArduPilot docs "ROS 2" / "ROS 2 with SITL".
set -euo pipefail
AP=${ARDUPILOT_HOME:-$HOME/ardupilot}
WS=${ROS2_AP_WS:-$HOME/ros2_ap_ws}

if [ ! -d "$AP" ]; then
  git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git "$AP"
fi
cd "$AP"
Tools/environment_install/install-prereqs-ubuntu.sh -y
# shellcheck disable=SC1090
. ~/.profile || true
pip3 install --user empy==3.3.4 pymavlink    # empy 3.x is required by the DDS code generator

./waf configure --board sitl --enable-dds
./waf copter

# Micro XRCE-DDS agent packaged as micro_ros_agent (built in a colcon workspace)
mkdir -p "$WS/src" && cd "$WS"
[ -d src/micro_ros_agent ] || git clone -b humble https://github.com/micro-ROS/micro-ROS-Agent.git src/micro_ros_agent
[ -d src/micro_ros_msgs ] || git clone -b humble https://github.com/micro-ROS/micro_ros_msgs.git src/micro_ros_msgs
# shellcheck disable=SC1091
source /opt/ros/humble/setup.bash
rosdep update && rosdep install --from-paths src --ignore-src -y
colcon build --symlink-install
echo "done: source $WS/install/setup.bash"
