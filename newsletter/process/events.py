"""
Parse all stored newsletters → structured Event objects → Supabase.
"""

import json
import logging
import os
import typing as ta
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

from newsletter.database import (
    save_events_to_db,
    email_already_parsed, mark_email_processed, fetch_unprocessed_emails,
)
from newsletter.types import (
    Event,
    EventType,
    EventOccurrenceType,
    EventLocationType,
    EventBookingType,
    EventTargetAudience,
)

# ─────────────────────────── setup ────────────────────────────────
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ───────────── human-readable field descriptions ──────────────────
FIELD_DESCRIPTIONS: dict[str, str] = {
    # ─── identifiers & core text ─────────────────────────────────────
    "email_message_id":  "RFC-822 Message-ID of the source email.",
    "title":             "Concise title, no org names, cap first letter, no full stop.",
    "summary":           "One-line blurb; empty string allowed.",
    "description_verbatim": "Exact newsletter snippet for this event.",

    # ─── when ────────────────────────────────────────────────────────
    "start_date":        "YYYY-MM-DD first date the event happens (required).",
    "end_date":          "YYYY-MM-DD for continuous spans; null for single-day or recurring.",
    "start_time":        "HH:MM:SS if a clock is given; otherwise null.",
    "end_time":          "HH:MM:SS; optional.",
    "is_all_day":        "True if the event runs 24 h for that date.",
    "time_of_day":       "early_morning | late_morning | morning | afternoon | evening | night | tbc.",
    "timezone":          "IANA TZ; default Europe/London.",

    # ─── recurrence ─────────────────────────────────────────────────
    "occurrence_type":   "one_off | recurring | course_session | series_part | tbc.",
    "recurrence_rule":   "RFC-5545 RRULE with UNTIL or COUNT; null if not repeating.",

    # ─── where ──────────────────────────────────────────────────────
    "location_type":     "venue | online | address_only | various | tbc.",
    "location_address_verbatim": "Street address verbatim; optional.",
    "location_neighbourhood":    "Neighbourhood / borough; optional.",
    "online_url":        "Streaming / meeting URL; optional.",

    # ─── cost & booking ─────────────────────────────────────────────
    "cost_amount":       "Numeric ticket price; null if free/unknown.",
    "cost_currency":     "ISO-4217 code, e.g. GBP.",
    "is_donation_based": "True for pay-what-you-can.",
    "is_cost_tbc":       "True if price not announced yet.",
    "cost_description_verbatim": "Pricing text verbatim.",
    "booking_type":      "required | recommended | not_required | tbc.",
    "booking_url":       "Direct booking link.",

    # ─── discovery & audience ───────────────────────────────────────
    "event_url":         "Public landing page.",
    "vibes_tags":        "2-5 lower-case themes (array), vibes should be creatively defined, and not overlap too closely with `target_audiences`",
    "target_audiences":  "Array of EventTargetAudience enums. Nothing else, must be one of these values.",
    "event_types":       "Array of EventType enums. Nothing else, must be one of these values.",

    # ─── accessibility & organiser ──────────────────────────────────
    "is_accessible":     "True if explicitly step-free etc.",
    "accessibility_notes_verbatim": "Exact accessibility wording.",
    "organizer_name":    "Inferred organiser / venue name.",
    "is_organizer_sender": "True if email sender == organiser.",

    # ─── QA ─────────────────────────────────────────────────────────
    "parsing_confidence_score":  "Float 0–1 extraction certainty."
}
FIELDS_TXT = "\n".join(f"{k}: {v}" for k, v in FIELD_DESCRIPTIONS.items())


# ─────────────────── extraction routine ───────────────────────────
def extract_events(
        email_body: str,
        email_sent_date: str,
        message_id: str
) -> ta.List[Event]:
    """
    Run LLM → structured list[Event].
    """
    day_name = datetime.fromisoformat(email_sent_date).strftime("%A")

    # dynamic enum dump
    enum_map = {
        "EventOccurrenceType": EventOccurrenceType,
        "EventLocationType": EventLocationType,
        "EventBookingType": EventBookingType,
        "EventTargetAudience": EventTargetAudience,
        "EventType": EventType,
    }
    ENUMS_TXT = "\n".join(
        f"{n}: {', '.join(e.value for e in enum_cls)}"
        for n, enum_cls in enum_map.items()
    )

    # JSON Schema (Pydantic v2)
    schema = Event.model_json_schema()
    schema.pop("title", None);
    schema.pop("description", None)
    SCHEMA_TXT = json.dumps(schema, separators=(",", ":"))

    system_prompt = f"""
<role>
You convert newsletter prose into structured JSON for a local-events DB.
</role>

<task>
E-mail send-date: {day_name} {email_sent_date or 'UNKNOWN'} (weekday YYYY-MM-DD).

Return **ONE** JSON object only:
{{ "events": [ 0 + objects exactly matching <schema> ] }}

Rules:
• Fill start_date (YYYY-MM-DD) for every event.
  – If span “28–30 Apr” → start_date=28-04, end_date=30-04, is_all_day=true.
  – If “Fri & Sat 18–19 Apr 7 pm” → TWO events with start_date 18-04 & 19-04.
• If a time exists, set start_time (HH:MM:SS); else use time_of_day bucket (if available, do not make it up).
• Provide recurrence_rule ONLY when the pattern repeats
  (must include UNTIL or COUNT so it is finite).
• Required fields per event:
     title, occurrence_type, location_type,
     start_date, time_of_day (or start_time),
     summary, vibes_tags (≥1), target_audiences (≥1), event_types (≥1)
     parsing_confidence_score.
• Unknowns → null.  Enum values → exactly as in <enums>.
• Titles: no org names, capitalise first letter, no trailing full stop. Critical: never mention the venue name in the title!
• Never invent venues, URLs, or prices not present in the text.
• All enum fields MUST use exactly one of the allowed values listed in <enums>.
• CRITCAL: NEVER, that is, NEVER(!) invent new enum values for target_audiences or event_types, etc.). For `target_audiences` or `event_types`, if a value does not exist, use the fallback option `tbc`
• CRITCAL: to reiterate, for enum columns, do not use values outside of the specified enum (otherwise the world may end). DO NOT MAKE IT UP DO NOT MAKE IT UP!!!
• If no value fits, use "tbc" instead.
</task>

<fields>
{FIELDS_TXT}
</fields>

<schema>
{SCHEMA_TXT}
</schema>

<enums>
{ENUMS_TXT}
</enums>

<tips>
Before finalizing your output:
- Check that every "target_audiences" array contains ONLY valid values.
- Check that every "event_types" array contains ONLY valid values.
- If a generated value is not in the allowed list, replace it with "tbc".
Do not skip this verification step. Otherwise critical errors will occur.
</tips>

<output_format>
Return valid JSON only—no markdown fences or commentary.
</output_format>
    """.strip()

    # 4) call OpenAI
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": email_body},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    data = json.loads(completion.choices[0].message.content)

    events_raw = data["events"]
    if not isinstance(events_raw, list):
        logger.warning("Key 'events' missing or not a list → [].")
        return []

    events: list[Event] = []
    for obj in events_raw:
        obj["email_message_id"] = message_id
        print(obj)
        if isinstance(obj['recurrence_rule'], str):
            obj['recurrence_rule'] = obj['recurrence_rule'].removeprefix('RRULE:')
        if not obj['time_of_day']:
            obj['time_of_day'] = 'tbc'
        if len(obj['target_audiences']):
            allowed = {e.value for e in EventTargetAudience}
            filtered = [t for t in obj["target_audiences"] if t in allowed]
            obj["target_audiences"] = filtered or ["tbc"]
        if len(obj['event_types']):
            allowed = {e.value for e in EventType}
            filtered = [t for t in obj["event_types"] if t in allowed]
            obj["event_types"] = filtered or ["tbc"]

        events.append(Event(**obj))

    return events


# ─────────────────── orchestration loop ───────────────────────────
def main(batch: int = 10000) -> None:
    for email_rec in fetch_unprocessed_emails(batch):
        msg_id = email_rec["message_id"]
        body = email_rec.get("body") or ""

        assert msg_id is not None

        if email_already_parsed(msg_id):
            logger.info(f"Email already processed for {msg_id} – skipping processing.")
            continue

        if len(body) > 10_000:
            logger.info("Email %s too large – skipping.", msg_id)
            mark_email_processed(msg_id, parsed_ok=False, note="body_too_large")
            continue

        if not email_rec.get("is_newsletter"):
            logger.info("Email %s is not a newsletter – skipping.", msg_id)
            mark_email_processed(msg_id, parsed_ok=False, note="not_newsletter")
            continue

        logger.info("Processing newsletter %s …", msg_id)

        # Build anchor date for relative terms
        sent_dt = datetime.fromisoformat(email_rec.get("date"))
        send_date_str = sent_dt.strftime("%Y-%m-%d")

        events = extract_events(body, send_date_str, msg_id)

        if events:
            logger.info(f"Events found: {[str(e)[:100] for e in events]}...")

            save_events_to_db(events, msg_id)
            mark_email_processed(msg_id, parsed_ok=True, note="is_newsletter")
        else:
            mark_email_processed(msg_id, parsed_ok=True, note="no_events_found")


if __name__ == "__main__":
    main()
