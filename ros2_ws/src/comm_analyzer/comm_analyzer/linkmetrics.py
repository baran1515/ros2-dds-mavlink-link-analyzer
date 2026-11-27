"""Link metrics shared by the UDP analyser and the ROS 2 nodes (pure Python).

* LossCounter   - sequence-number based loss / duplicate / reorder detection
* JitterEstimator - RFC 3550 inter-arrival jitter
* Summary       - min / mean / p50 / p95 / p99 / max of a sample list
"""
from __future__ import annotations

import math
from dataclasses import dataclass


class LossCounter:
    """Loss detection for an N-bit wrapping sequence number.

    Packets that arrive with a sequence number *behind* the highest one seen
    are counted as reordered (and the earlier loss estimate is corrected),
    exact repeats as duplicates.
    """

    def __init__(self, bits: int = 8, window: int = 64):
        self.mod = 1 << bits
        self.half = self.mod // 2
        self.window = window
        self.highest: int | None = None
        self.received = 0
        self.lost = 0
        self.reordered = 0
        self.duplicates = 0
        self._recent: list[int] = []

    def update(self, seq: int) -> None:
        self.received += 1
        if self.highest is None:
            self.highest = seq
            self._remember(seq)
            return
        if seq in self._recent:
            self.duplicates += 1
            self.received -= 1
            return
        diff = (seq - self.highest) % self.mod
        if 0 < diff < self.half:              # newer
            self.lost += diff - 1
            self.highest = seq
        else:                                 # older -> late/reordered packet
            self.reordered += 1
            if self.lost > 0:
                self.lost -= 1                # it was counted as lost before
        self._remember(seq)

    def _remember(self, seq: int) -> None:
        self._recent.append(seq)
        if len(self._recent) > self.window:
            self._recent.pop(0)

    @property
    def loss_pct(self) -> float:
        total = self.received + self.lost
        return 100.0 * self.lost / total if total else 0.0


class JitterEstimator:
    """RFC 3550 §6.4.1: J += (|D| - J) / 16, D = difference of transit times.

    Without synchronised clocks, inter-arrival variation against the nominal
    send period is used: D = (arrival_i - arrival_{i-1}) - (send_i - send_{i-1}).
    """

    def __init__(self):
        self.jitter = 0.0
        self._prev: tuple[float, float] | None = None

    def update(self, send_t: float, recv_t: float) -> float:
        if self._prev is not None:
            d = (recv_t - self._prev[1]) - (send_t - self._prev[0])
            self.jitter += (abs(d) - self.jitter) / 16.0
        self._prev = (send_t, recv_t)
        return self.jitter


def percentile(values, p):
    if not values:
        return math.nan
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (k - lo)


@dataclass
class Summary:
    n: int
    min: float
    mean: float
    p50: float
    p95: float
    p99: float
    max: float

    @classmethod
    def of(cls, values) -> "Summary":
        v = list(values)
        if not v:
            return cls(0, *([math.nan] * 6))
        return cls(len(v), min(v), sum(v) / len(v), percentile(v, 50), percentile(v, 95),
                   percentile(v, 99), max(v))

    def fmt(self, unit="ms") -> str:
        return (f"n={self.n} min={self.min:.1f} mean={self.mean:.1f} p50={self.p50:.1f} "
                f"p95={self.p95:.1f} p99={self.p99:.1f} max={self.max:.1f} {unit}")
