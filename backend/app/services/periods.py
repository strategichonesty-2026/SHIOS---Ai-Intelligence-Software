"""Period arithmetic.

Every trend, prediction and reality check is anchored to an ISO week label such as
`2026-W30`. Weeks are the smallest unit that smooths posting noise while still producing a
usable signal inside a 90-day governance window.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def to_date(value: datetime | date) -> date:
    if isinstance(value, datetime):
        return value.astimezone(UTC).date() if value.tzinfo else value.date()
    return value


def week_period(value: datetime | date) -> str:
    d = to_date(value)
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def month_period(value: datetime | date) -> str:
    d = to_date(value)
    return f"{d.year}-{d.month:02d}"


def period_start_date(period: str) -> date:
    """Monday of the given ISO week label."""
    year_s, week_s = period.split("-W")
    return date.fromisocalendar(int(year_s), int(week_s), 1)


def shift_period(period: str, weeks: int) -> str:
    return week_period(period_start_date(period) + timedelta(weeks=weeks))


def period_range(start: str, end: str) -> list[str]:
    """Inclusive, gap-free list of week labels."""
    cur, stop = period_start_date(start), period_start_date(end)
    out: list[str] = []
    while cur <= stop:
        out.append(week_period(cur))
        cur += timedelta(weeks=1)
    return out


def recent_periods(count: int, anchor: date | None = None) -> list[str]:
    anchor = anchor or datetime.now(UTC).date()
    end = week_period(anchor)
    start = shift_period(end, -(count - 1))
    return period_range(start, end)


def period_index(period: str) -> int:
    """Monotonic integer index for regression maths."""
    return period_start_date(period).toordinal() // 7


def week_label(period: str) -> str:
    """Convert '2026-W20' → 'May 12–18, 2026'. Returns original string if not an ISO week."""
    if "-W" not in period:
        return period
    monday = period_start_date(period)
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        return f"{monday.strftime('%b')} {monday.day}–{sunday.day}, {sunday.year}"
    return f"{monday.strftime('%b %-d')}–{sunday.strftime('%b %-d')}, {sunday.year}"
