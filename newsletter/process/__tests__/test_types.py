"""
Tests for the Event model’s recurrence-rule validator.

Adjust the import below to match your project layout.
"""
import re
from datetime import date, time, timedelta, datetime

import pytest

from newsletter.process.events import Event  # ← update if your path differs


# ─────────────────────────
# helpers
# ─────────────────────────
def _base_kwargs(**overrides):
    """Return the minimum-viable kwargs for building an Event."""
    base = {
        "email_message_id": "stub-1",
        "title": "pytest event",
        "start_date": date(2025, 5, 19),
    }
    base.update(overrides)
    return base


# ─────────────────────────
# 1) normalisation & round-trips
# ─────────────────────────
@pytest.mark.parametrize(
    "raw_rrule, expected",
    [
        (
                # missing “RRULE:” prefix & ISO UNTIL
                "FREQ=WEEKLY;UNTIL=2025-06-19T19:00:00Z",
                "RRULE:FREQ=WEEKLY;UNTIL=20250619T190000Z",
        ),
        (
                # already perfect
                "RRULE:FREQ=WEEKLY;UNTIL=20250619T190000Z",
                "RRULE:FREQ=WEEKLY;UNTIL=20250619T190000Z",
        ),
    ],
)
def test_rrule_is_normalised(raw_rrule, expected):
    ev = Event(**_base_kwargs(recurrence_rule=raw_rrule))
    assert ev.recurrence_rule == expected


# ─────────────────────────
# 2) infinite rules are capped to one year
# ─────────────────────────
@pytest.mark.parametrize(
    "raw_rrule",
    [
        "FREQ=DAILY",  # no prefix, infinite
        "RRULE:FREQ=MONTHLY",  # prefix present, still infinite
    ],
)
def test_infinite_rrule_capped(raw_rrule):
    ev = Event(**_base_kwargs(recurrence_rule=raw_rrule))
    m = re.search(r"UNTIL=(\d{8})", ev.recurrence_rule)
    assert m, "UNTIL should have been injected"
    until = datetime.strptime(m.group(1), "%Y%m%d").date()
    assert until == ev.start_date + timedelta(days=365)


# ─────────────────────────
# 3) incoherent input raises ValueError
# ─────────────────────────
@pytest.mark.parametrize(
    "kwargs",
    [
        # malformed RRULE
        {"recurrence_rule": "RRULE:FREQ=WEEKLY;BYDAY=XX"},
        # end_date conflicts with UNTIL
        {
            "recurrence_rule": "RRULE:FREQ=DAILY;UNTIL=20250619",
            "end_date": date(2025, 6, 20),
        },
        # same-day event where end_time < start_time
        {
            "start_time": (10, 0),  # tuples expanded below
            "end_time": (9, 0),
            "end_date": date(2025, 5, 19),
        },
    ],
)
def test_invalid_event_raises(kwargs):
    # Expand (hh, mm) tuples into datetime.time objects when present
    if "start_time" in kwargs and isinstance(kwargs["start_time"], tuple):
        kwargs["start_time"] = time(*kwargs["start_time"])
    if "end_time" in kwargs and isinstance(kwargs["end_time"], tuple):
        kwargs["end_time"] = time(*kwargs["end_time"])

    with pytest.raises(ValueError):
        Event(**_base_kwargs(**kwargs))
