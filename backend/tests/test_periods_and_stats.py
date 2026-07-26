from __future__ import annotations

from datetime import date

from app.services.periods import period_index, period_range, shift_period, week_period
from app.services.stats import accuracy_score, direction_of, linear_fit, percent_change


def test_week_period_is_iso():
    assert week_period(date(2026, 7, 25)) == "2026-W30"


def test_shift_and_range_are_inverse():
    start = "2026-W20"
    assert shift_period(shift_period(start, 4), -4) == start
    span = period_range("2026-W20", "2026-W24")
    assert span == ["2026-W20", "2026-W21", "2026-W22", "2026-W23", "2026-W24"]


def test_period_index_is_monotonic():
    assert period_index("2026-W21") - period_index("2026-W20") == 1


def test_period_range_crosses_year_boundary():
    span = period_range("2025-W52", "2026-W02")
    assert span[0] == "2025-W52" and span[-1] == "2026-W02" and len(span) >= 3


def test_linear_fit_recovers_known_line():
    fit = linear_fit([1, 2, 3, 4], [3, 5, 7, 9])
    assert round(fit.slope, 6) == 2.0
    assert round(fit.intercept, 6) == 1.0
    assert fit.r_squared == 1.0
    assert fit.predict(5) == 11.0


def test_linear_fit_handles_degenerate_input():
    assert linear_fit([], []).slope == 0.0
    assert linear_fit([2.0], [7.0]).intercept == 7.0
    assert linear_fit([1, 1, 1], [4, 5, 6]).slope == 0.0


def test_accuracy_is_bounded_and_scale_aware():
    assert accuracy_score(10, 10) == 1.0
    assert accuracy_score(0, 100) == 0.0
    assert accuracy_score(102, 100) > accuracy_score(5, 3)


def test_direction_and_percent_change():
    assert direction_of(2) == "up"
    assert direction_of(-2) == "down"
    assert direction_of(0) == "flat"
    assert percent_change(150, 100) == 50.0
    assert percent_change(1, 0) == 100.0
