#!/usr/bin/env python3
"""Summarise results/*.csv from run_experiments.sh into a Markdown table + plot.

File names encode the run: <profile>__<reliability>_d<depth>__<rate>hz_<payload>b.csv
The last row of each CSV holds the cumulative counters; RTT percentiles are
averaged over all 1-second windows after a 5 s warm-up.
"""
import csv
import glob
import math
import os
import sys

ORDER = ["ideal", "wifi", "degraded", "bad", "burst", "outage"]


def load(path):
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    name = os.path.basename(path)[:-4]
    profile, qos, _ = (name.split("__") + ["", ""])[:3]
    return profile, qos, rows


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


def mean(xs):
    xs = [x for x in xs if not math.isnan(x)]
    return sum(xs) / len(xs) if xs else math.nan


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    d = sys.argv[1] if len(sys.argv) > 1 else "results"
    runs = []
    for p in sorted(glob.glob(os.path.join(d, "*.csv"))):
        profile, qos, rows = load(p)
        if not rows:
            continue
        steady = [r for r in rows if f(r["t_s"]) >= 5] or rows
        last = rows[-1]
        runs.append(dict(profile=profile, qos=qos, sent=int(f(last["sent"])), lost=int(f(last["lost"])),
                         loss=f(last["loss_pct"]), late=int(f(last["late"])),
                         p50=mean(f(r["rtt_p50_ms"]) for r in steady),
                         p95=mean(f(r["rtt_p95_ms"]) for r in steady),
                         mx=max(f(r["rtt_max_ms"]) for r in steady),
                         jit=mean(f(r["jitter_ms"]) for r in steady)))
    if not runs:
        raise SystemExit(f"no CSV files in {d}")
    runs.sort(key=lambda r: (ORDER.index(r["profile"]) if r["profile"] in ORDER else 99, r["qos"]))
    print("| Ağ profili | QoS | Gönderilen | Kayıp [%] | Geç gelen | RTT p50 [ms] | RTT p95 [ms] | RTT max [ms] | Jitter [ms] |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        print(f"| {r['profile']} | {r['qos']} | {r['sent']} | {r['loss']:.2f} | {r['late']} | {r['p50']:.1f} | "
              f"{r['p95']:.1f} | {r['mx']:.1f} | {r['jit']:.2f} |")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5))
    qos_list = sorted({r["qos"] for r in runs})
    profiles = [p for p in ORDER if any(r["profile"] == p for r in runs)]
    w = 0.8 / max(1, len(qos_list))
    for i, q in enumerate(qos_list):
        xs = [j + i * w for j in range(len(profiles))]
        get = lambda key: [next((r[key] for r in runs if r["profile"] == p and r["qos"] == q), math.nan) for p in profiles]
        a1.bar(xs, get("p95"), width=w, label=q)
        a2.bar(xs, get("loss"), width=w, label=q)
    for a, t in ((a1, "RTT p95 [ms]"), (a2, "Uygulama seviyesi kayıp [%]")):
        a.set_xticks([j + w * (len(qos_list) - 1) / 2 for j in range(len(profiles))], profiles)
        a.set_title(t)
        a.grid(True, axis="y")
        a.legend()
    fig.tight_layout()
    out = os.path.join(d, "summary.png")
    fig.savefig(out, dpi=110)
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
