#!/usr/bin/env bash
# ROS 2 Humble on Ubuntu 22.04 (official apt repository).
set -euo pipefail
sudo apt-get update
sudo apt-get install -y software-properties-common curl locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
sudo add-apt-repository -y universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo "$UBUNTU_CODENAME") main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt-get update
sudo apt-get install -y ros-humble-ros-base ros-dev-tools python3-colcon-common-extensions \
  ros-humble-diagnostic-msgs ros-humble-sensor-msgs ros-humble-rmw-cyclonedds-cpp
grep -q "/opt/ros/humble/setup.bash" ~/.bashrc || echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
echo "ROS 2 Humble installed - open a new shell"
