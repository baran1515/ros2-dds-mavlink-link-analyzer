#!/usr/bin/env bash
# Run the DDS link test for every (network profile x QoS) combination and
# collect one CSV per run in results/. Needs sudo for tc/netem.
#
#   source /opt/ros/humble/setup.bash && source ros2_ws/install/setup.bash
#   ./scripts/run_experiments.sh            # DURATION=60 by default
#   python3 scripts/analyze_results.py results/
set -euo pipefail
cd "$(dirname "$0")/.."

DURATION=${DURATION:-60}
RATE=${RATE:-50}
PAYLOAD=${PAYLOAD:-64}
PROFILES=(${PROFILES:-ideal wifi degraded bad burst})
QOS=(${QOS:-reliable:10 best_effort:1 reliable:1})
DDS_PORTS=${DDS_PORTS:-7400-7450}       # domain 0 discovery + user traffic

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://$PWD/config/cyclonedds_lo.xml"
mkdir -p results
trap 'sudo ./netem/netem.sh clear >/dev/null' EXIT

for prof in "${PROFILES[@]}"; do
  sudo ./netem/netem.sh apply "$prof" --port "$DDS_PORTS" > /dev/null
  for q in "${QOS[@]}"; do
    rel=${q%%:*}; depth=${q##*:}
    out="results/${prof}__${rel}_d${depth}__${RATE}hz_${PAYLOAD}b.csv"
    echo ">>> profile=$prof qos=$rel depth=$depth -> $out"
    timeout --signal=INT "$((DURATION + 5))" ros2 launch comm_analyzer comm_test.launch.py \
        reliability:="$rel" depth:="$depth" rate_hz:="$RATE" payload_bytes:="$PAYLOAD" \
        csv:="$PWD/$out" > "results/${prof}__${rel}_d${depth}.log" 2>&1 || true
  done
done
echo "done - analyse with: python3 scripts/analyze_results.py results/"
