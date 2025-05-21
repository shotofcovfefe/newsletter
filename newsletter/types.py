from __future__ import annotations

import re
import typing as ta
from datetime import date, time, datetime, timedelta
from enum import Enum

from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrulestr
from pydantic import BaseModel, Field, constr, field_validator, model_validator


# ───────────── ENUMS ──────────────────────────────────────────────
class TimeOfDay(str, Enum):
    early_morning = "early_morning"  # 05:00–08:59
    late_morning = "late_morning"  # 09:00–11:59
    morning = "morning"  # 05:00–11:59
    afternoon = "afternoon"  # 12:00–16:59
    evening = "evening"  # 17:00–20:59
    night = "night"  # 21:00–04:59
    all_day = "all_day"
    tbc = "tbc"


class EventOccurrenceType(str, Enum):
    one_off = "one_off"
    recurring = "recurring"
    course_session = "course_session"
    series_part = "series_part"
    tbc = "tbc"


class EventType(str, Enum):
    music = "music"
    theatre_and_performing_arts = "theatre_and_performing_arts"
    art_and_exhibitions = "art_and_exhibitions"
    film = "film"
    comedy = "comedy"
    talks_and_lectures = "talks_and_lectures"
    workshops_and_classes = "workshops_and_classes"
    festivals = "festivals"
    lgbtq = "lgbtq"
    food_and_drink = "food_and_drink"
    sports_and_fitness = "sports_and_fitness"
    social_and_networking = "social_and_networking"
    family_and_kids = "family_and_kids"
    markets_and_shopping = "markets_and_shopping"
    tours_and_travel = "tours_and_travel"
    activism_and_causes = "activism_and_causes"
    spirituality_and_wellness = "spirituality_and_wellness"
    technology_and_science = "technology_and_science"
    business_and_professional = "business_and_professional"
    other = "tbc"


class EventLocationType(str, Enum):
    venue = "venue"
    online = "online"
    address_only = "address_only"
    various = "various"
    tbc = "tbc"


class EventBookingType(str, Enum):
    required = "required"
    recommended = "recommended"
    not_required = "not_required"
    tbc = "tbc"


class EventTargetAudience(str, Enum):
    # ── broad & default ─────────────────────────────────────────
    all = "all"
    adults = "adults"
    families = "families"
    kids = "kids"
    teens = "teens"
    students = "students"
    young_professionals = "young_professionals"
    seniors = "seniors"

    # ── skill / experience level ───────────────────────────────
    beginners = "beginners"
    intermediate = "intermediate"
    experts = "experts"

    # ── relationship / social mode ─────────────────────────────
    couples = "couples"
    date_night = "date_night"
    singles = "singles"
    friends = "friends"
    solo_attendees = "solo_attendees"
    new_in_town = "new_in_town"
    remote_workers = "remote_workers"

    # ── identity / inclusion ──────────────────────────────────
    lgbtq_plus = "lgbtq+"

    # ── interest: arts & culture ───────────────────────────────
    art_lovers = "art_lovers"
    bookworms = "bookworms"
    film_buffs = "film_buffs"
    theatre_lovers = "theatre_lovers"
    music_lovers = "music_lovers"
    makers_crafters = "makers_crafters"
    photographers = "photographers"
    gamers = "gamers"
    fashion_enthusiasts = "fashionistas"
    history_buffs = "history_buffs"
    comedy_fans = "comedy_fans"

    # ── interest: food & drink ─────────────────────────────────
    foodies = "foodies"
    coffee_aficionados = "coffee_aficionados"
    beer_enthusiasts = "beer_enthusiasts"
    wine_lovers = "wine_lovers"
    vegans = "vegans"

    # ── interest: sport & outdoors ─────────────────────────────
    sports_fans = "sports_fans"
    runners = "runners"
    cyclists = "cyclists"
    hikers = "hikers"
    gardeners = "gardeners"

    # ── interest: wellness & spirituality ──────────────────────
    yogis = "yogis"
    wellness_seekers = "wellness_seekers"
    spirituality_seekers = "spirituality_seekers"
    religious = "religious"

    # ── professional / learning ────────────────────────────────
    entrepreneurs = "entrepreneurs"
    tech_enthusiasts = "tech_enthusiasts"
    creatives = "creatives"
    language_learners = "language_learners"

    # ── cause / lifestyle values ───────────────────────────────
    eco_conscious = "eco_conscious"
    environmentalists = "environmentalists"
    charity_volunteers = "charity_volunteers"
    alternative_culture = "alternative_culture"
    nightlife_crowd = "nightlife_crowd"
    local_community = "local_community"
    pet_owners = "pet_owners"
    activism_and_causes = "activism_and_causes"

    # ── family-stage specifics ─────────────────────────────────
    parents_with_babies = "parents_with_babies"
    pre_schoolers = "pre_schoolers"

    # ── fallback ───────────────────────────────────────────────
    tbc = "tbc"


_RRULE_RE = re.compile(
    r"^(?:RRULE:)?"
    r"FREQ=(DAILY|WEEKLY|MONTHLY|YEARLY)"
    r"(;INTERVAL=\d+)?"
    r"(;BYDAY=(?:MO|TU|WE|TH|FR|SA|SU)"
    r"(?:,(?:MO|TU|WE|TH|FR|SA|SU))*)?"
    r"(;BYMONTHDAY=-?\d{1,2})?"
    r"(;COUNT=\d+"
    r"|;UNTIL=(\d{8}|[0-9]{4}-[0-9]{2}-[0-9]{2})(T\d{6}Z?)?)?"
    r"$"
)


# ───────────── EVENT MODEL ────────────────────────────────────────
class Event(BaseModel):
    # identifiers
    email_message_id: str

    # text
    title: str = "(untitled event)"
    summary: str = ""
    description_verbatim: str | None = None

    # when
    start_date: date
    end_date: date | None = None  # only for continuous spans
    start_time: time | None = None
    end_time: time | None = None
    is_all_day: bool = False  # true for 24-hour spans
    time_of_day: TimeOfDay = TimeOfDay.tbc
    timezone: str = "Europe/London"

    # recurrence
    occurrence_type: EventOccurrenceType = EventOccurrenceType.tbc
    recurrence_rule: constr(strip_whitespace=True) | None = None

    # where
    location_type: EventLocationType = EventLocationType.tbc
    location_address_verbatim: str | None = None
    location_neighbourhood: str | None = None
    location_borough: str | None = None
    online_url: str | None = None

    # cost & booking
    cost_amount: float | None = None
    cost_currency: str | None = None
    is_donation_based: bool = False
    is_cost_tbc: bool = False
    cost_description_verbatim: str | None = None

    booking_type: EventBookingType | None = None
    booking_url: str | None = None

    # discovery
    event_url: str | None = None
    vibes_tags: ta.List[str] = Field(default_factory=list, max_items=5)
    target_audiences: ta.List[EventTargetAudience] = Field(
        default_factory=lambda: [EventTargetAudience.all]
    )
    event_types: ta.List[EventType] = Field(default_factory=list)

    # accessibility & organiser
    organizer_name: str | None = None
    is_organizer_sender: bool | None = None

    from_aggregator: bool = None

    # QA
    parsing_confidence_score: float = Field(0.0, ge=0.0, le=1.0)

    @field_validator("recurrence_rule")
    def validate_and_patch_rrule(cls, v, info):
        if v is None:
            return None

        # 1. Make sure the string starts with "RRULE:"
        if not v.startswith("RRULE:"):
            v = f"RRULE:{v}"

        # 2. Convert any extended ISO UNTIL value to iCalendar “basic” form
        v = re.sub(
            r"UNTIL=([\d]{4}-[\d]{2}-[\d]{2}T[\d]{2}:[\d]{2}:[\d]{2}Z?)",
            lambda m: "UNTIL=" +  # keep the key
                      datetime.fromisoformat(  # parse 2025-06-19T19:00:00[Z]
                          m.group(1).rstrip("Z")
                      ).strftime("%Y%m%dT%H%M%S") +
                      ("Z" if m.group(1).endswith("Z") else ""),
            v,
        )

        # now the string is definitely parsable
        rule = rrulestr(v)

        # --- your existing “infinite rule” patch -------------------
        if rule._count is None and rule._until is None:
            start_date = info.data.get("start_date")
            if start_date is None:
                raise ValueError("Cannot patch infinite recurrence_rule because start_date is missing.")
            until = start_date + timedelta(days=365)
            v = f"{v};UNTIL={until.strftime('%Y%m%d')}"
            rrulestr(v)  # re-validate

        return v

    @model_validator(mode="after")
    def _coherence_checks(self):
        # ------- basic date/time sanity ---------------------------
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        if self.end_date == self.start_date:
            if self.start_time and self.end_time and self.end_time < self.start_time:
                raise ValueError("end_time earlier than start_time")

        # ------- bind infinite RRULEs to one-year window ----------
        if self.recurrence_rule and "COUNT=" not in self.recurrence_rule and "UNTIL=" not in self.recurrence_rule:
            until_date = (self.start_date + relativedelta(years=1) - relativedelta(days=1))
            until_str = until_date.strftime("%Y%m%d")
            bounded_rrule = f"{self.recurrence_rule};UNTIL={until_str}"
            object.__setattr__(self, "recurrence_rule", bounded_rrule)

        # ------- rule + explicit end_date consistency -------------
        if self.recurrence_rule and self.end_date and "UNTIL=" in self.recurrence_rule:
            # extract UNTIL from rule
            m = re.search(r"UNTIL=([0-9]{8})", self.recurrence_rule)
            if m and self.end_date != datetime.strptime(m.group(1), "%Y%m%d").date():
                raise ValueError("end_date does not match UNTIL in recurrence_rule")

        return self


class Events(BaseModel):
    events: ta.List[Event]
