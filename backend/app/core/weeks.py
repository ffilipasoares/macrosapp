"""Week and meal-slot helpers. A week is identified by the ISO date of its Monday."""

from datetime import date, timedelta

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MEALS = ["lunch", "dinner"]
SLOT_KEYS = [f"{day}_{meal}" for day in DAYS for meal in MEALS]


def week_id(day: date) -> str:
    """Return the id of the week containing ``day`` (its Monday, as YYYY-MM-DD)."""
    return (day - timedelta(days=day.weekday())).isoformat()


def parse_week_id(value: str) -> date:
    """Parse a week id, rejecting dates that are not a Monday."""
    monday = date.fromisoformat(value)
    if monday.weekday() != 0:
        raise ValueError(f"{value} is not a Monday")
    return monday


def next_week_id(today: date) -> str:
    return week_id(today + timedelta(days=7))


def previous_week_ids(current: str, count: int) -> list[str]:
    """The ``count`` week ids immediately before ``current``, most recent first."""
    monday = parse_week_id(current)
    return [(monday - timedelta(days=7 * i)).isoformat() for i in range(1, count + 1)]
