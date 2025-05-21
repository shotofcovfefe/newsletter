"""
Parse all stored newsletters → structured Event objects → Supabase.
"""

import json
import logging
import os
import re
import typing as ta
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

from newsletter.ai.get_ai_response import call_llm
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
    TimeOfDay
)
from newsletter.utils import resolve_redirect_from_known_sources, trim_aggregator_email_bodies_from_known_sources, \
    replace_json_gates, resolve_links_in_body

# ─────────────────────────── setup ────────────────────────────────
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ───────────── human-readable field descriptions ──────────────────
FIELD_DESCRIPTIONS: dict[str, str] = {
    # ─── identifiers & core text ─────────────────────────────────────
    "email_message_id": "RFC-822 Message-ID of the source email.",
    "title": "Concise title, no org names, cap first letter, no full stop.",
    "summary": "One-line blurb; empty string allowed.",
    "description_verbatim": "Exact newsletter snippet for this event.",

    # ─── when ────────────────────────────────────────────────────────
    "start_date": "YYYY-MM-DD first date the event happens (required).",
    "end_date": "YYYY-MM-DD for continuous spans; null for single-day or recurring.",
    "start_time": "HH:MM:SS if a clock is given; otherwise null.",
    "end_time": "HH:MM:SS; optional.",
    "is_all_day": "True if the event runs 24 h for that date.",
    "time_of_day": "early_morning | late_morning | morning | afternoon | evening | night | tbc.",
    "timezone": "IANA TZ; default Europe/London.",

    # ─── recurrence ─────────────────────────────────────────────────
    "occurrence_type": "one_off | recurring | course_session | series_part | tbc.",
    "recurrence_rule": "RFC-5545 RRULE with UNTIL or COUNT; null if not repeating.",

    # ─── where ──────────────────────────────────────────────────────
    "location_type": "venue | online | address_only | various | tbc.",
    "location_address_verbatim": "Street address, as complete as possible; optional.",
    "location_neighbourhood": "The London borough which contains the event; optional.",
    "location_postcode": "The postcode of the event venue, optional",
    "online_url": "Streaming / meeting URL; optional.",

    # ─── cost & booking ─────────────────────────────────────────────
    "cost_amount": "Numeric ticket price; null if free/unknown.",
    "cost_currency": "ISO-4217 code, e.g. GBP.",
    "is_donation_based": "True for pay-what-you-can.",
    "is_cost_tbc": "True if price not announced yet.",
    "cost_description_verbatim": "Pricing text verbatim.",
    "booking_type": "required | recommended | not_required | tbc.",
    "booking_url": "Direct booking link.",

    # ─── discovery & audience ───────────────────────────────────────
    "event_url": "Public landing page.",
    "vibes_tags": "2-5 lower-case themes (array), vibes should be creatively defined, and not overlap too closely with `target_audiences`",
    "target_audiences": "Array of EventTargetAudience enums. Nothing else, must be one of these values.",
    "event_types": "Array of EventType enums. Nothing else, must be one of these values.",

    # ─── accessibility & organiser ──────────────────────────────────
    "organizer_name": "Inferred organiser / venue name.",
    "is_organizer_sender": "True if email sender == organiser.",

    # ─── QA ─────────────────────────────────────────────────────────
    "parsing_confidence_score": "Float 0–1 extraction certainty.",

    # ─── Misc ───────────────────────────────────────────────────────
    "from_aggregator": "comes from aggregate source, boolean"
}
FIELDS_TXT = "\n".join(f"{k}: {v}" for k, v in FIELD_DESCRIPTIONS.items())

N_CHARS_MAX = 40000


def _get_relevant_enums_for_refinement() -> str:
    """Helper to get enum definitions relevant for the refinement step."""
    # Enums most likely to be affected/informed by web search
    relevant_enum_map = {
        "EventLocationType": EventLocationType,
        "EventBookingType": EventBookingType,
        "TimeOfDay": TimeOfDay,  # Web search might clarify times
        "EventType": EventType,  # Web search might give better category
        "EventTargetAudience": EventTargetAudience,  # Less likely but possible
    }
    return "\n".join(
        f"- {n}: {', '.join(e.value for e in enum_cls)}"
        for n, enum_cls in relevant_enum_map.items()
    )


def _enrich_via_web_search(event_dict_to_enrich: dict) -> dict:
    """
    Performs a web search for an event and then refines the event data using a second LLM call.
    Returns a dictionary of fields that were updated or added.
    """
    title = event_dict_to_enrich['title']
    start_date_str = event_dict_to_enrich['start_date']
    query = f"{title} {start_date_str}"
    if event_dict_to_enrich.get("organizer_name"):
        query += f" {event_dict_to_enrich['organizer_name']}"
    if event_dict_to_enrich.get("location_neighbourhood"):
        query += f" {event_dict_to_enrich['location_neighbourhood']}"

    logger.info(f"Pre-search Enrichment _query_ for '{title}': {query}")

    # Step 1: Perform Web Search using gpt-4o-search-preview
    browse_completion = client.chat.completions.create(
        model="gpt-4o-mini-search-preview",
        web_search_options={
            "search_context_size": "low",
            "user_location": {
                "type": "approximate",
                "approximate": {
                    "country": "GB",
                    "city": "London",
                    "region": "London",
                }
            },
        },
        messages=[
            {"role": "system",
             "content": "You are an AI web search assistant. Based on the user's query, perform a web search and provide a comprehensive summary of the findings relevant to the event details requested."},
            {"role": "user", "content": query}
        ]
    )
    web_search_summary = browse_completion.choices[0].message.content
    web_search_summary = replace_json_gates(web_search_summary)

    if not web_search_summary or web_search_summary.strip() == "":
        logger.info(f"Web search for '{title}' yielded no content.")
        return {}

    logger.info(f"Scraped web search _summary_ for '{title}': {web_search_summary[:500]}...")

    # Step 2: Refine Event Data with Web Search Summary
    event_schema_properties = Event.model_json_schema().get("properties", {})
    for key_to_remove in ["email_message_id", "data_source_type", "enrichment_status", "parsing_confidence_score",
                          "description_verbatim", "original_event_text_from_aggregator"]:
        event_schema_properties.pop(key_to_remove, None)

    refinement_schema_context = json.dumps(event_schema_properties, indent=2)
    relevant_enums_txt = _get_relevant_enums_for_refinement()

    refinement_system_prompt = f"""
You are an AI assistant tasked with refining a (likely) partially complete JSON object representing an event, using information from a web search summary.
Your goal is to update the 'Current Event JSON' with more accurate and/or complete data found in the 'Web Search Summary'.

Instructions:
1.  Analyze the 'Current Event JSON' and the 'Web Search Summary'.
2.  Identify fields in the 'Current Event JSON' that are missing (null), marked as 'tbc', or could be improved (made more specific or corrected) based on the web search.
Focus on enriching: `title`, `summary`, `start_date`, `end_date`, `start_time`, `end_time`, `time_of_day`, `occurrence_type`,
`location_type`, `location_address_verbatim`, `location_borough` `location_postcode`, `online_url`,
`cost_amount`, `cost_currency`, `is_donation_based`, `is_cost_tbc`, `cost_description_verbatim`,
`booking_type`, `booking_url`, `event_url`, `organizer_name`, `vibes_tags`, `event_types`, `target_audiences`, `recurrence_rule`
3.  If the web search provides more precise or complete information for a field, use the web search information, but be 
4.  If the web search information conflicts with plausible existing data, prioritize the web search ONLY if it seems more authoritative (e.g., an official event page). 
5.  If the web search does not provide useful information for a particular field, retain the original value from 'Current Event JSON'. DO NOT invent data.
6.  **Enum Adherence**: For fields that are enums (e.g., `location_type`, `event_types`, `target_audiences`, `time_of_day`), any new or updated values MUST EXACTLY match one of the allowed values provided in <relevant_enum_definitions>. If the web search suggests a value not in the list, try to map it to the closest valid enum value or use 'tbc' if appropriate for that enum, if not appropriate for that enum, use None. 
7.  **Output Format**: Return a JSON object containing ONLY the fields that you have updated or newly populated. Do not return fields that remain unchanged from the 'Current Event JSON'. If no fields can be improved or updated, return an empty JSON object {{}}.
8. You must be looking at the correct event! See the original start / end / recurring date fields.
9. `location_postcode` is a really important one to extract, if you can get the address you can get the postcode.   

<relevant_event_json_schema_properties>
{refinement_schema_context}
</relevant_event_json_schema_properties>

<relevant_enum_definitions>
{relevant_enums_txt}
</relevant_enum_definitions>

<tips>
- if the event is at a specific venue (it probably is), the address must be complete with a postcode
- we really want to have the `location_postcode`!   
- urls are favoured from official event sources, but if hard to find, don't worry
- make sure the event you're looking at is the correct one, the dates must align (e.g. don't be looking at one for a previous year or a different place)
- all events should be in London, England. If it'
- the location_neighbourhood will be the London borough (should be easy to work out if you have the address / postcode)
- if you're updating `cost_amount`, make sure cost_currency is infilled (it's fair to assume this will be £).
- the end date CANNOT be before the start date, be VERY hesitant updating these since they're likely to be correct.
- the start and end dates, if not known, should be None, not `tbc`
- the recurrence_rule, if necessary, should be represented as an RRULE.   
</tips>
    """.strip()

    refine_completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": refinement_system_prompt},
            {"role": "user",
             "content": f"Current Event JSON:\n{json.dumps(event_dict_to_enrich, indent=2)}\n\nWeb Search Summary:\n{web_search_summary}"},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    refined_data_str = refine_completion.choices[0].message.content

    refined_data = json.loads(refined_data_str)

    if refined_data:
        logger.info(f"Refinement for '{title}' suggested updates: {refined_data}")
    else:
        logger.info(f"Refinement for '{title}' suggested no changes.")
    return refined_data


# ── quick test whether we need enrichment ───────────────────────
def _needs_enrichment(ev: dict) -> bool:
    """Determines if an event from an aggregator source needs web enrichment."""
    missing_postcode = not ev.get("location_postcode")

    missing_organizer = not ev.get("organizer_name")
    missing_venue_address = (
            ev.get("location_type") == EventLocationType.venue.value and not ev.get("location_address_verbatim"))

    return missing_postcode or missing_organizer or missing_venue_address


# ── minimal completeness gate  (after optional enrichment) ─────
def _is_complete(ev: dict, is_aggregator: bool) -> bool:
    """Return True iff the event dict meets minimal quality rules."""
    if not ev.get("title") or not ev.get("start_date") or not ev.get("location_type"):
        logger.debug(f"Event incomplete (title, start_date, or location_type missing): {ev.get('title')}")
        return False
    if float(ev.get("parsing_confidence_score", 0)) < 0.4:
        logger.debug(
            f"Event incomplete (low confidence after processing): {ev.get('title')}, score: {ev.get('parsing_confidence_score')}")
        return False

    if is_aggregator:
        if not ev.get("organizer_name"):
            logger.debug(f"Aggregator event incomplete (organizer_name missing): {ev.get('title')}")
            return False
        if ev.get("location_type") == EventLocationType.venue.value and (
                (not ev.get("location_address_verbatim") or (not ev.get("location_postcode")))):
            logger.debug(f"Aggregator event incomplete (venue address missing): {ev.get('title')}")
            return False

        if not (ev.get("event_url") or ev.get("booking_url")):
            logger.debug(f"Aggregator event incomplete (event/booking URL missing): {ev.get('title')}")
            return False
    return True


# ─────────────────── extraction routine ───────────────────────────

def construct_extract_events_sys_prompt(
        day_name: str,
        email_sent_date: str,
        fields_txt: str,
        schema_txt: str,
        enums_txt: str,
) -> str:
    return f"""
    <role>
    You extract events from emails sent from digital newsletters and/or mailing lists into a structured and syntactically correct JSON format for an events database.
    </role>

    <task>
    E-mail send-date: {day_name} {email_sent_date or 'UNKNOWN'} (weekday YYYY-MM-DD).

    Return **ONE** JSON object only:
    {{ "events": [ list of event objects infilled (where possible) fields from <schema> ] }}

    Rules:
    • Fill start_date (YYYY-MM-DD) for every event.
      – If span “28–30 Apr” → start_date=28-04, end_date=30-04, is_all_day=true.
      – If “Fri & Sat 18–19 Apr 7 pm” → ONE event with an appropriate start_date, end_date, and recurrence_rule 
    • If a time exists, set start_time (HH:MM:SS); else use time_of_day bucket (if available, do not make it up).
    • Provide recurrence_rule ONLY when the pattern repeats (this is a RRULE)
      - (must include UNTIL or COUNT so it is finite)
      - if it says for example "every Wednesday", or "every month", just infill UNTIL with + 1 month max. 
    • Required fields per event:
         title, occurrence_type, location_type,
         start_date, time_of_day (or start_time),
         summary, vibes_tags (≥1), target_audiences (≥1), event_types (≥1)
         parsing_confidence_score.
    • Enum values → exactly as in <enums>.
    • Titles: no org names, capitalise first letter, no trailing full stop. Critical: never mention the venue name in the title!
    • Never invent venues, URLs, or prices not present in the text.
    • All enum fields MUST use exactly one of the allowed values listed in <enums>.
    • CRITICAL: NEVER, that is, NEVER(!) invent new enum values for target_audiences or event_types, etc.). For `target_audiences` or `event_types`, if a value does not exist, use the fallback option `tbc`
    • CRITICAL: to reiterate, for enum columns, do not use values outside of the specified enum (otherwise the world may end). DO NOT MAKE IT UP DO NOT MAKE IT UP!!! If no value fits, use 'tbc'
    • You must pass EVERY event, ALL events, DO NOT MISS ANY!
    • Only return fields that are clearly present or can be reliably inferred from the text.
    • If a start time or end time aer not there, mark it as null 
    • Do **NOT** invent information. If a field cannot be populated with high confidence, omit it.
    • Ignore fields `email_message_id` and `from_aggregator`, these will get added later.   
    </task>

    <fields>
    {fields_txt}
    </fields>

    <schema>
    {schema_txt}
    </schema>

    <enums>
    {enums_txt}
    </enums>

    <tips>
    Before finalizing your output:
    - Check that every "target_audiences" array contains ONLY valid values.
    - Check that every "event_types" array contains ONLY valid values.
    - Make sure to extract every unique event, and no more. EVERY EVENT, not a subset. 
    - Accuracy is vital to success. 
    - If you see relevant URLs, use them.  
    Do not skip this verification step. Otherwise critical errors will occur.
    Do not stop early. Continue until every event is captured in the list. Use streaming if needed.
    </tips>

    <output_format>
    Return valid JSON only—no markdown fences or commentary.
    </output_format>
        """.strip()


def extract_events(
        email_body: str,
        email_sent_date: str,
        message_id: str,
        is_aggregator: bool,
        provider: str,
) -> ta.List[Event]:
    """
    Run LLM → structured list[Event].
    """

    if is_aggregator:
        email_body = trim_aggregator_email_bodies_from_known_sources(
            email_body
        )
        email_body = resolve_links_in_body(email_body)

    # split on unsubscribe
    match = re.search(r'^(.*?)(?=unsubscribe\b.*$)', email_body, flags=re.IGNORECASE | re.DOTALL)
    if match:
        email_body = match.group(1).rstrip()

    day_name = datetime.fromisoformat(email_sent_date).strftime("%A")

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

    # JSON Schema
    schema = Event.model_json_schema()
    schema.pop("title", None)
    schema.pop("description", None)
    SCHEMA_TXT = json.dumps(schema, separators=(",", ":"))

    system_prompt = construct_extract_events_sys_prompt(
        day_name=day_name,
        email_sent_date=email_sent_date,
        fields_txt=FIELDS_TXT,
        schema_txt=SCHEMA_TXT,
        enums_txt=ENUMS_TXT,
    )

    if provider == "anthropic":
        model = "claude-3-7-sonnet-20250219"
        response_format = None
    elif provider == "openai":
        model = "gpt-4o"
        response_format = {"type": "json_object"}
    else:
        raise NotImplementedError("provider invalid")

    # 4) call OpenAI
    logger.info(
        f"Making call to {provider}:{model} to extract initial set of events (is_aggregator={is_aggregator})....")

    raw_text = call_llm(
        provider=provider,
        model=model,
        system=system_prompt,
        user=email_body,
        response_format=response_format,
        max_tokens=10000,
        timeout=180,
    )
    data = json.loads(raw_text)

    events_raw = data["events"]
    if not isinstance(events_raw, list):
        logger.warning("Key 'events' missing or not a list → [].")
        return []

    logger.info(f"👉  Extracted {len(events_raw)} events.")

    events: list[Event] = []
    for obj in events_raw:
        obj["email_message_id"] = message_id
        obj["from_aggregator"] = is_aggregator

        # ───────── enrichment branch for aggregator sources ──────────
        if is_aggregator and _needs_enrichment(obj):
            obj.update(_enrich_via_web_search(obj))

        logger.info(obj)

        # ───────── existing cleanup / coercions  ─────────────────────
        if obj.get('end_time') == 'tbc':
            obj['end_time'] = None
        if obj.get('start_time') == 'tbc':
            obj['start_time'] = None
        if 'start_date' not in obj:
            obj['start_date'] = None
        if 'end_date' not in obj:
            obj['end_date'] = None
        if obj['start_date'] is not None and obj['end_date'] is not None:
            if obj['start_date'] > obj['end_date']:
                logger.error(f"start date cannot be later than end date: {obj}")
                continue
        if not obj.get('start_date') and not obj.get('end_date'):
            logger.error(f"could not identify start or end date for event: {obj}")
            continue
        if isinstance(obj.get('recurrence_rule'), str):
            obj['recurrence_rule'] = obj['recurrence_rule'].removeprefix('RRULE:')
        if not obj.get('time_of_day'):
            obj['time_of_day'] = 'tbc'
        if len(obj['target_audiences']):
            allowed = {e.value for e in EventTargetAudience}
            filtered = [t for t in obj["target_audiences"] if t in allowed]
            if len(obj["target_audiences"]) > len(filtered):
                logger.warning(f"filtered out some target audiences: {set(obj['target_audiences']) - set(filtered)}")
            obj["target_audiences"] = filtered or ["tbc"]
        if len(obj['event_types']):
            allowed = {e.value for e in EventType}
            filtered = [t for t in obj["event_types"] if t in allowed]
            if len(obj["event_types"]) > len(filtered):
                logger.warning(f"filtered out some event types: {set(obj['event_types']) - set(filtered)}")
            obj["event_types"] = filtered or ["tbc"]

        events.append(Event(**obj))

    return events


# ─────────────────── orchestration loop ───────────────────────────
def main(batch: int = N_CHARS_MAX, provider: str = "openai") -> None:
    for email_rec in fetch_unprocessed_emails(batch):
        msg_id = email_rec["message_id"]
        body = email_rec.get("body") or ""

        assert msg_id is not None

        if email_already_parsed(msg_id):
            logger.info(f"Email already processed for {msg_id} – skipping processing.")
            continue

        if len(body) > N_CHARS_MAX:
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

        is_agg = email_rec["newsletter_source_type"] == "aggregate"
        events = extract_events(body, send_date_str, msg_id, is_aggregator=is_agg, provider=provider)

        if events:
            logger.info(f"Events found: {[str(e)[:100] for e in events]}...")

            save_events_to_db(events, msg_id)
            mark_email_processed(msg_id, parsed_ok=True, note="is_newsletter")
        else:
            mark_email_processed(msg_id, parsed_ok=True, note="no_events_found")


if __name__ == "__main__":
    main()
