"""Statistics.

Spec rule for the Trend Agent: "Statistics first. No LLM guessing." Everything numeric in
SHIOS is computed here, in plain Python, so it can be audited line by line.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Fit:
    slope: float
    intercept: float
    r_squared: float
    n: int

    def predict(self, x: float) -> float:
        return self.slope * x + self.intercept


def linear_fit(xs: list[float], ys: list[float]) -> Fit:
    """Ordinary least squares. Returns a zero-slope fit for degenerate input."""
    n = len(xs)
    if n < 2:
        return Fit(slope=0.0, intercept=(ys[0] if ys else 0.0), r_squared=0.0, n=n)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return Fit(slope=0.0, intercept=mean_y, r_squared=0.0, n=n)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys, strict=True))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    return Fit(slope=slope, intercept=intercept, r_squared=max(0.0, min(1.0, r_squared)), n=n)


def direction_of(delta: float, tolerance: float = 1e-9) -> str:
    if delta > tolerance:
        return "up"
    if delta < -tolerance:
        return "down"
    return "flat"


def percent_change(current: float, previous: float) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return (current - previous) / abs(previous) * 100.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    m = mean(values)
    return (sum((v - m) ** 2 for v in values) / (n - 1)) ** 0.5


def accuracy_score(predicted: float, actual: float) -> float:
    """Bounded 0-1 accuracy. Scale-free, so a miss of 2 on a base of 3 hurts more than on 300."""
    denominator = max(abs(actual), abs(predicted), 1.0)
    return max(0.0, 1.0 - abs(predicted - actual) / denominator)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
