#!/usr/bin/env bash
# Network impairment profiles with Linux tc/netem (needs sudo).
#
#   sudo ./netem/netem.sh apply degraded            # all traffic on lo
#   sudo ./netem/netem.sh apply bad --port 14550    # only UDP/TCP dst port 14550 (MAVLink)
#   sudo ./netem/netem.sh apply wifi --port 7400-7500   # DDS discovery/user ports range
#   sudo ./netem/netem.sh show
#   sudo ./netem/netem.sh clear
#
# Profiles (one-way, applied on egress of the interface; on 'lo' every
# packet passes egress once, so RTT sees the delay twice):
#   ideal    : nothing
#   wifi     : 5 ms +- 2 ms, 0.5 % loss
#   degraded : 50 ms +- 15 ms (normal), 2 % loss, 1 % duplicate
#   bad      : 150 ms +- 50 ms, 10 % loss 25 % correlation, 5 % reorder
#   burst    : 20 ms, Gilbert-Elliott burst loss (p=2 %, r=25 %, 1-h=90 %)
#   outage   : 100 % loss (link down)
set -euo pipefail

DEV=${DEV:-lo}
cmd=${1:-}
profile=${2:-}
port=""
if [ "${3:-}" = "--port" ]; then port=${4:-}; fi

netem_args() {
  case "$1" in
    ideal)    echo "delay 0ms" ;;
    wifi)     echo "delay 5ms 2ms loss 0.5%" ;;
    degraded) echo "delay 50ms 15ms distribution normal loss 2% duplicate 1%" ;;
    bad)      echo "delay 150ms 50ms loss 10% 25% reorder 5% 50%" ;;
    burst)    echo "delay 20ms loss gemodel 2% 25% 90% 0%" ;;
    outage)   echo "loss 100%" ;;
    *) echo "unknown profile: $1" >&2; exit 2 ;;
  esac
}

clear_qdisc() { tc qdisc del dev "$DEV" root 2>/dev/null || true; }

case "$cmd" in
  apply)
    [ -n "$profile" ] || { echo "usage: $0 apply <profile> [--port P|A-B]"; exit 2; }
    clear_qdisc
    if [ -z "$port" ]; then
      # shellcheck disable=SC2046
      tc qdisc add dev "$DEV" root netem $(netem_args "$profile")
    else
      # prio qdisc: band 3 gets netem, only matching ports are steered into it
      tc qdisc add dev "$DEV" root handle 1: prio bands 3 priomap 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
      # shellcheck disable=SC2046
      tc qdisc add dev "$DEV" parent 1:3 handle 30: netem $(netem_args "$profile")
      lo_p=${port%-*}; hi_p=${port#*-}
      for ((p = lo_p; p <= hi_p; p++)); do
        tc filter add dev "$DEV" protocol ip parent 1:0 prio 3 u32 match ip dport "$p" 0xffff flowid 1:3
        tc filter add dev "$DEV" protocol ip parent 1:0 prio 3 u32 match ip sport "$p" 0xffff flowid 1:3
      done
    fi
    echo "applied '$profile' on $DEV${port:+ (ports $port)}"
    tc qdisc show dev "$DEV"
    ;;
  clear) clear_qdisc; echo "cleared $DEV" ;;
  show)  tc qdisc show dev "$DEV"; tc filter show dev "$DEV" 2>/dev/null || true ;;
  *) echo "usage: $0 {apply <profile> [--port P|A-B] | clear | show}"; exit 2 ;;
esac
