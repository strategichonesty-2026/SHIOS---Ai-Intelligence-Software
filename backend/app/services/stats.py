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
    residual_std: float = 0.0
    mean_x: float = 0.0
    sxx: float = 0.0

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
        return Fit(slope=0.0, intercept=mean_y, r_squared=0.0, n=n, mean_x=mean_x)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys, strict=True))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    residual_std = (ss_res / (n - 2)) ** 0.5 if n > 2 else 0.0
    return Fit(
        slope=slope,
        intercept=intercept,
        r_squared=max(0.0, min(1.0, r_squared)),
        n=n,
        residual_std=residual_std,
        mean_x=mean_x,
        sxx=sxx,
    )


# One-tailed 0.90 Student-t quantiles (equivalently the two-sided 80% interval), df 1-30.
# Hardcoded rather than computed so the number behind every published bound can be checked
# against any printed t-table. Beyond df=30 the normal quantile 1.2816 is used.
_T_90 = {
    1: 3.078, 2: 1.886, 3: 1.638, 4: 1.533, 5: 1.476, 6: 1.440, 7: 1.415, 8: 1.397,
    9: 1.383, 10: 1.372, 11: 1.363, 12: 1.356, 13: 1.350, 14: 1.345, 15: 1.341,
    16: 1.337, 17: 1.333, 18: 1.330, 19: 1.328, 20: 1.325, 21: 1.323, 22: 1.321,
    23: 1.319, 24: 1.318, 25: 1.316, 26: 1.315, 27: 1.314, 28: 1.313, 29: 1.311,
    30: 1.310,
}


def t_quantile_80(df: int) -> float:
    """Critical value for a two-sided 80% prediction interval with `df` degrees of freedom."""
    if df < 1:
        return _T_90[1]
    return _T_90.get(df, 1.2816)


def prediction_interval_80(fit: Fit, x0: float) -> tuple[float, float]:
    """Two-sided 80% OLS prediction interval for a new observation at x0.

    half-width = t * s * sqrt(1 + 1/n + (x0 - mean_x)^2 / Sxx)

    For degenerate fits (fewer than three points, or zero x-spread) the residual standard
    error is zero and the interval collapses to the point estimate; callers gate on a
    minimum number of periods before publishing anyway.
    """
    point = fit.predict(x0)
    if fit.n < 3 or fit.sxx == 0:
        return point, point
    spread = (1.0 + 1.0 / fit.n + ((x0 - fit.mean_x) ** 2) / fit.sxx) ** 0.5
    half_width = t_quantile_80(fit.n - 2) * fit.residual_std * spread
    return point - half_width, point + half_width


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
