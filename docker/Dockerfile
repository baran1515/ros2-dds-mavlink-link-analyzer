# ROS 2 Humble + comm_analyzer workspace (SITL is run on the host or in its own container).
#   docker build -t sitl-comm -f docker/Dockerfile .
#   docker run --rm -it --net=host --cap-add=NET_ADMIN sitl-comm
FROM ros:humble-ros-base

RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-humble-rmw-cyclonedds-cpp ros-humble-diagnostic-msgs ros-humble-sensor-msgs \
        python3-pip iproute2 tcpdump \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir pymavlink matplotlib

WORKDIR /opt/sitl-comm
COPY . .
RUN . /opt/ros/humble/setup.sh && cd ros2_ws && colcon build --symlink-install

ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    CYCLONEDDS_URI=file:///opt/sitl-comm/config/cyclonedds_lo.xml
RUN echo "source /opt/ros/humble/setup.bash && source /opt/sitl-comm/ros2_ws/install/setup.bash" >> /root/.bashrc
CMD ["bash"]
