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
from newsletter.ai.constants import MODEL_CONFIGS, PROVIDER_OPENAI
from newsletter.ai.prompts import (
    construct_web_search_system_prompt,
    construct_event_refinement_system_prompt,
    construct_extract_events_sys_prompt
)
from newsletter.database import (
    save_events_to_db,
    email_already_parsed,
    mark_email_processed, fetch_unprocessed_emails,
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
from newsletter.utils.utils import (
    trim_aggregator_email_bodies_from_known_sources,
    replace_json_gates, is_valid_london_postcode, get_postcode_info
)
from newsletter.utils.browser import resolve_links_in_body
from newsletter.utils.caching import disk_cache

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
    "end_time": "HH:MM:SS.",
    "is_all_day": "True if the event runs 24 h for that date.",
    "time_of_day": "early_morning | late_morning | morning | afternoon | evening | night | tbc.",
    "timezone": "IANA TZ; default Europe/London.",

    # ─── recurrence ─────────────────────────────────────────────────
    "occurrence_type": "one_off | recurring | course_session | series_part | tbc.",
    "recurrence_rule": "RFC-5545 RRULE with UNTIL or COUNT; null if not repeating.",

    # ─── where ──────────────────────────────────────────────────────
    "location_type": "venue | online | address_only | various | tbc.",
    "location_address_verbatim": "Street address, as complete as possible.",
    "location_neighbourhood": "The local London neighbourhood which contains the event (e.g. Hackney Wick)",
    "location_borough": "The London borough where the event is held (e.g. Tower Hamlets)",
    "location_postcode": "The postcode of the event venue",
    "online_url": "Streaming / meeting URL.",

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


@disk_cache(cache_subdirectory_name="web_search_summary")
def _get_web_search_summary(event_dict_to_enrich: dict, provider_for_search: str) -> str | None:
    """
    Performs a web search for an event and returns the summary.
    """
    title = event_dict_to_enrich.get('title', 'Unknown Event')
    start_date_str = event_dict_to_enrich.get('start_date')

    if not title or not start_date_str:
        logger.warning(msg="⚠️ Title or start_date missing, cannot perform web search.")
        return None

    try:
        dt_object = datetime.strptime(start_date_str, '%Y-%m-%d')
        formatted_start_date = dt_object.strftime(format='%B %d, %Y')
    except (ValueError, TypeError):
        formatted_start_date = start_date_str

    query = f"{title} {formatted_start_date}"
    if event_dict_to_enrich.get("organizer_name"):
        query += f" {event_dict_to_enrich['organizer_name']}"
    if event_dict_to_enrich.get("location_neighbourhood"):
        query += f" {event_dict_to_enrich['location_neighbourhood']}"

    logger.info(msg=f"🌐 Web search query for '{title}': {query}")

    fields_to_retrieve_txt = "\n".join([
        f"*   `{key}`: {description}"
        for key, description in FIELD_DESCRIPTIONS.items()
    ])
    field_names_for_example = list(FIELD_DESCRIPTIONS.keys())

    current_event_info_lines = []
    for key, value in event_dict_to_enrich.items():
        if value is not None and value != '':
            current_event_info_lines.append(f"{key}: {value}")
    current_event_info_txt = "\n".join(current_event_info_lines)
    if not current_event_info_txt:
        current_event_info_txt = "No pre-existing information available for this event."

    system_prompt_for_search = construct_web_search_system_prompt(
        fields_to_retrieve_txt=fields_to_retrieve_txt,
        field_names_for_example=field_names_for_example,
        current_event_info_txt=current_event_info_txt
    )

    if provider_for_search not in MODEL_CONFIGS or "web_search_details" not in MODEL_CONFIGS[provider_for_search]:
        logger.error(msg=f"🛑 Web search details not configured for provider: {provider_for_search}")
        return None

    web_search_config = MODEL_CONFIGS[provider_for_search]["web_search_details"]
    model_for_search = web_search_config["model"]
    current_web_search_options = web_search_config["options"]

    web_search_summary_result = call_llm(
        provider=provider_for_search,
        model=model_for_search,
        system=system_prompt_for_search,
        user=query,
        enable_web_search=True,
        max_tokens=16_384,
        web_search_options=current_web_search_options,
    )

    web_search_summary_processed = replace_json_gates(s=web_search_summary_result)

    if not web_search_summary_processed or web_search_summary_processed.strip() == "":
        logger.info(msg=f"💨 Web search for query:['{query}'] yielded no content.")
        return None

    logger.info(msg=f"📄 Web search summary for '{title}': {web_search_summary_processed[:500]}...")
    return web_search_summary_processed


@disk_cache(cache_subdirectory_name="event_refinement")
def _refine_event_with_web_summary(
        event: dict,
        web_search_summary: str,
        provider_for_refinement: str
) -> dict:
    """
    Refines event data using a web search summary and an LLM call.
    Results are cached to disk via decorator.
    """
    title = event['title']
    event_schema_properties = Event.model_json_schema().get("properties", {})
    for key_to_remove in ["email_message_id", "from_aggregator", "enrichment_status", "parsing_confidence_score",
                          "description_verbatim", "original_event_text_from_aggregator"]:
        event_schema_properties.pop(key_to_remove, None)

    refinement_schema_context = json.dumps(obj=event_schema_properties, indent=2)
    relevant_enums_txt = _get_relevant_enums_for_refinement()

    refinement_system_prompt = construct_event_refinement_system_prompt(
        refinement_schema_context=refinement_schema_context,
        relevant_enums_txt=relevant_enums_txt
    )

    refine_user_content = f"Current Event JSON:```{json.dumps(obj=event, indent=2)}```\n\nWeb Search Summary:```{web_search_summary}```"

    provider_config = MODEL_CONFIGS[provider_for_refinement]
    refinement_model = provider_config['model']
    refinement_response_format = provider_config.get("response_format")

    refined_data_str = call_llm(
        provider=provider_for_refinement,
        model=refinement_model,
        system=refinement_system_prompt,
        user=refine_user_content,
        response_format=refinement_response_format,
        temperature=0.1
    )
    refined_data = json.loads(s=refined_data_str)

    if refined_data:
        logger.info(msg=f"📬  Refinement for '{title}' suggested updates: {refined_data}")
    else:
        logger.info(msg=f"🫗  Refinement for '{title}' suggested no changes.")
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
        logger.debug(msg=f"🚫 Event incomplete (title, start_date, or location_type missing): {ev.get('title')}")
        return False
    if float(ev.get("parsing_confidence_score", 0)) < 0.4:
        logger.debug(
            msg=f"📉 Event incomplete (low confidence after processing): {ev.get('title')}, score: {ev.get('parsing_confidence_score')}")
        return False

    if is_aggregator:
        if not ev.get("organizer_name"):
            logger.debug(msg=f"🏢 Aggregator event incomplete (organizer_name missing): {ev.get('title')}")
            return False
        if ev.get("location_type") == EventLocationType.venue.value and (
                (not ev.get("location_address_verbatim") or (not ev.get("location_postcode")))):
            logger.debug(msg=f"🗺️ Aggregator event incomplete (venue address missing): {ev.get('title')}")
            return False

        if not (ev.get("event_url") or ev.get("booking_url")):
            logger.debug(msg=f"🔗 Aggregator event incomplete (event/booking URL missing): {ev.get('title')}")
            return False
    return True


# ─────────────────── LLM-specific sub-routines ────────────────────

@disk_cache(cache_subdirectory_name="initial_extraction")
def _perform_initial_event_extraction(
        processed_email_body: str,
        extraction_system_prompt: str,
        extraction_provider: str
) -> list[dict]:
    """
    Calls the LLM to perform the initial extraction of events from the email body.
    Returns a list of raw event dictionaries.
    Results are cached to disk via decorator.
    """
    if extraction_provider not in MODEL_CONFIGS:
        logger.error(msg=f"🛑 Extraction provider '{extraction_provider}' not supported.")
        raise NotImplementedError(f"Extraction provider '{extraction_provider}' not supported")

    model_config = MODEL_CONFIGS[extraction_provider]
    extraction_model = model_config["model"]
    extraction_response_format = model_config.get("response_format")

    logger.info(
        msg=f"✨ Making call to {extraction_provider}:{extraction_model} to extract initial set of events....")

    raw_completion_content = call_llm(
        provider=extraction_provider,
        model=extraction_model,
        system=extraction_system_prompt,
        user=processed_email_body,
        response_format=extraction_response_format,
        temperature=0.1
    )

    extracted_event_list: list[dict] = []
    if raw_completion_content:
        try:
            parsed_json_response = json.loads(s=raw_completion_content)
            if "events" in parsed_json_response and isinstance(parsed_json_response["events"], list):
                extracted_event_list = parsed_json_response["events"]
                logger.info(f"🎉 Initial extraction found {len(extracted_event_list)} potential events.")
            else:
                logger.error(
                    msg=f"💥  LLM response for event extraction did not contain a list under 'events' key. Response: {raw_completion_content[:500]}...")
        except json.JSONDecodeError:
            logger.error(msg=f"💥  Failed to decode JSON from extraction: {raw_completion_content[:500]}...")

    return extracted_event_list


def _process_single_extracted_event(
        obj: dict,
        message_id: str,
        is_aggregator: bool,
        search_provider: str,
        refinement_provider: str
) -> ta.Optional[Event]:
    """
    Processes a single raw extracted event object.
    This includes enrichment, refinement, data cleaning, and validation.
    Returns an Event object or None if processing fails or event is invalid.
    """
    logger.info(msg=f"⚙️ Processing event: '{obj.get('title')}'")

    obj["email_message_id"] = message_id
    obj["from_aggregator"] = is_aggregator

    if is_aggregator and _needs_enrichment(ev=obj):
        logger.info(msg=f"🔍 Event '{obj.get('title')}' needs enrichment. Web search provider: {search_provider}")
        web_summary = _get_web_search_summary(
            event_dict_to_enrich=obj,
            provider_for_search=search_provider
        )
        if web_summary:
            logger.info(
                msg=f"🛠️ Refining event '{obj.get('title')}' with web summary. Refinement provider: {refinement_provider}")
            enrichment_updates = _refine_event_with_web_summary(
                event=obj,
                web_search_summary=web_summary,
                provider_for_refinement=refinement_provider
            )
            if enrichment_updates:
                obj.update(enrichment_updates)
                logger.info(f"✅ Event '{obj.get('title')}' updated with refinement data.")
        else:
            logger.info(msg=f"💨 No web summary found for '{obj.get('title')}', skipping refinement.")

    # --- Data cleaning and validation ---
    if obj.get('end_time') == 'tbc':
        obj['end_time'] = None
    if obj.get('start_time') == 'tbc':
        obj['start_time'] = None
    if 'start_date' not in obj or obj['start_date'] is None:
        logger.warning(msg=f"🗓️ Event '{obj.get('title', 'Untitled Event')}' missing start_date, skipping.")
        return None

    if 'end_date' not in obj:
        obj['end_date'] = None

    if obj.get('start_date') and obj.get('end_date'):
        try:
            start_dt = datetime.fromisoformat(str(obj['start_date']).split('T')[0])
            end_dt = datetime.fromisoformat(str(obj['end_date']).split('T')[0])
            if start_dt > end_dt:
                logger.error(
                    msg=f"🛑 Start date ({obj['start_date']}) cannot be later than end date ({obj['end_date']}) for event: {obj.get('title', 'Untitled Event')}")
                return None
        except (ValueError, TypeError) as e:
            logger.error(
                msg=f"💥 Invalid date format for event '{obj.get('title', 'Untitled Event')}': {e}. Start: {obj.get('start_date')}, End: {obj.get('end_date')}")
            return None

    if isinstance(obj.get('recurrence_rule'), str):
        obj['recurrence_rule'] = obj['recurrence_rule'].removeprefix('RRULE:')

    if not obj.get('time_of_day'):
        obj['time_of_day'] = 'tbc'

    # Ensure list types for target_audiences and event_types
    if "target_audiences" not in obj or not isinstance(obj["target_audiences"], list):
        obj["target_audiences"] = []

    if "event_types" not in obj or not isinstance(obj["event_types"], list):
        obj["event_types"] = []

    if len(obj.get('target_audiences', [])):
        allowed = {e.value for e in EventTargetAudience}
        original_audiences = list(obj["target_audiences"])
        filtered_audiences = [t for t in original_audiences if isinstance(t, str) and t in allowed]
        if len(original_audiences) > len(filtered_audiences):
            rejected_audiences = set(original_audiences) - set(filtered_audiences)
            logger.warning(
                msg=f"✂️ Filtered out target audiences for '{obj.get('title', 'Untitled Event')}': {rejected_audiences}")
        obj["target_audiences"] = filtered_audiences or ["tbc"]
    else:
        obj["target_audiences"] = ["tbc"]

    if len(obj.get('event_types', [])):
        allowed = {e.value for e in EventType}
        original_types = list(obj["event_types"])
        filtered_types = [t for t in original_types if isinstance(t, str) and t in allowed]
        if len(original_types) > len(filtered_types):
            rejected_types = set(original_types) - set(filtered_types)
            logger.warning(
                msg=f"🏷️ Filtered out event types for '{obj.get('title', 'Untitled Event')}': {rejected_types}")
        obj["event_types"] = filtered_types or ["tbc"]
    else:
        obj["event_types"] = ["tbc"]

    # Default values for potentially missing fields
    if "title" not in obj or not obj["title"]:
        logger.warning(
            msg=f"📛 Event missing title, setting to 'Untitled Event'. Original obj snippet: {str(obj)[:200]}")
        obj["title"] = "Untitled Event"
    obj.setdefault("summary", "")
    obj.setdefault("description_verbatim", "")
    obj.setdefault("occurrence_type", EventOccurrenceType.tbc.value)
    obj.setdefault("location_type", EventLocationType.tbc.value)
    obj.setdefault("parsing_confidence_score", 0.5)

    # ensure these weren't over-riden
    obj["email_message_id"] = message_id
    obj["from_aggregator"] = is_aggregator

    postcode = obj.get('location_postcode')
    if postcode and is_valid_london_postcode(postcode=postcode):
        postcode_info = get_postcode_info(postcode=postcode)
        if not obj.get('location_borough'):
            obj['location_borough'] = postcode_info.get('borough')
        if not obj.get('location_neighbourhood'):
            obj['location_neighbourhood'] = postcode_info.get('neighbourhood')

    try:
        event_model = Event(**obj)
        return event_model
    except Exception as e:
        logger.error(
            msg=f"Failed to create Event Pydantic model for '{obj.get('title', 'Untitled')}' due to: {e}. Object data: {obj}")
        return None


# ─────────────────── main extraction routine ───────────────────────────

def extract_events(
        email_body: str,
        email_sent_date: str,
        message_id: str,
        is_aggregator: bool,
        extraction_provider: str,
        search_provider: str,
        refinement_provider: str
) -> ta.List[Event]:
    """
    Run LLM → structured list[Event].
    """
    logger.info(f"🏁 Starting event extraction for email_id: {message_id}, is_aggregator: {is_aggregator}")

    # 1. Pre-process email body
    processed_email_body = email_body
    if is_aggregator:
        trimmed_body = trim_aggregator_email_bodies_from_known_sources(
            body=processed_email_body
        )
        # Resolve links *after* trimming, as trimming might remove context for resolving
        processed_email_body = resolve_links_in_body(body=trimmed_body)

        # Attempt to remove unsubscribe sections
    match = re.search(pattern=r'^(.*?)(?=unsubscribe\\b.*$)\'', string=processed_email_body,
                      flags=re.IGNORECASE | re.DOTALL)
    if match:
        processed_email_body = match.group(1).rstrip()

    if not processed_email_body.strip():
        logger.warning("📧 Email body is empty after pre-processing. No events to extract.")
        return []

    # 2. Prepare for initial extraction
    day_name = datetime.fromisoformat(email_sent_date).strftime(format="%A")
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
    schema = Event.model_json_schema()
    schema.pop("title", None)
    SCHEMA_TXT = json.dumps(obj=schema, separators=(",", ":"))

    extraction_system_prompt = construct_extract_events_sys_prompt(
        day_name=day_name,
        email_sent_date=email_sent_date,
        fields_txt=FIELDS_TXT,
        schema_txt=SCHEMA_TXT,
        enums_txt=ENUMS_TXT,
    )

    # 3. Perform initial event extraction (LLM Call #1)
    extracted_raw_event_list = _perform_initial_event_extraction(
        processed_email_body=processed_email_body,
        extraction_system_prompt=extraction_system_prompt,
        extraction_provider=extraction_provider
    )

    if not extracted_raw_event_list:
        logger.info("💨 No potential events found after initial extraction.")
        return []

    # 4. Process each extracted event object
    # Enrichment (LLM Call #2) and Refinement (LLM Call #3) happen inside _process_single_extracted_event
    # The refinement provider is now explicitly passed. It makes sense for the refinement
    # to use the same provider as the websearch that informed it.
    # Or, if websearch and refinement should use base_provider, that can be passed.
    # For now, aligning refinement with websearch_provider seems logical.
    final_events: list[Event] = []
    for raw_event_obj in extracted_raw_event_list:
        processed_event_model = _process_single_extracted_event(
            obj=raw_event_obj,
            message_id=message_id,
            is_aggregator=is_aggregator,
            search_provider=search_provider,
            refinement_provider=refinement_provider
        )
        if processed_event_model:
            final_events.append(processed_event_model)
            logger.info(msg=f"☀️ Finished processing event: {processed_event_model}")

    logger.info(f"🏁 Finished event extraction for email_id: {message_id}. Found {len(final_events)} valid events.")
    return final_events


# ─────────────────── orchestration loop ───────────────────────────
def main(
        extraction_provider: str = PROVIDER_OPENAI,
        search_provider: str = PROVIDER_OPENAI,
        refinement_provider: str = PROVIDER_OPENAI,
        batch: int = N_CHARS_MAX
) -> None:
    emails = list(fetch_unprocessed_emails(batch_size=batch))
    total = len(emails)
    by_type = {"aggregate": 0, "venue": 0, "unknown": 0}
    for email_item in emails:  # Renamed to avoid conflict
        t = email_item.get("newsletter_source_type", "unknown")
        if t not in by_type:  # Ensure key exists
            by_type[t] = 0
        by_type[t] += 1
    logger.info(
        msg=f"📊 Processing {total} unprocessed emails: {by_type['aggregate']} aggregate, {by_type['venue']} venue, {by_type['unknown']} unknown, {total - by_type['aggregate'] - by_type['venue'] - by_type['unknown']} other.")

    for idx, email_rec in enumerate(emails):

        msg_id = email_rec["message_id"]
        body = email_rec.get("body") or ""

        assert msg_id is not None

        if email_already_parsed(message_id=msg_id):
            logger.info(msg=f"✅  Email already processed for {msg_id} – skipping processing.")
            continue

        if len(body) > N_CHARS_MAX:
            logger.info(msg=f"📏 Email {msg_id} too large – skipping.")
            mark_email_processed(message_id=msg_id, parsed_ok=False, note="body_too_large")
            continue

        if not email_rec.get("is_newsletter"):
            logger.info(msg=f"📰  Email {msg_id} is not a newsletter – skipping.")
            mark_email_processed(message_id=msg_id, parsed_ok=False, note="not_newsletter")
            continue

        logger.info(msg=f"📧  Processing email {msg_id[:10]}[...]{msg_id[-15:]}")

        sent_dt = datetime.fromisoformat(email_rec.get("date"))
        send_date_str = sent_dt.strftime(format="%Y-%m-%d")

        is_agg = email_rec["newsletter_source_type"] == "aggregate"
        extracted_events = extract_events(
            email_body=body,
            email_sent_date=send_date_str,
            message_id=msg_id,
            is_aggregator=is_agg,
            extraction_provider=extraction_provider,
            search_provider=search_provider,
            refinement_provider=refinement_provider
        )

        if extracted_events:
            logger.info(msg=f"🎉 Events found: {[str(e)[:100] for e in extracted_events]}...")

            save_events_to_db(events=extracted_events, email_message_id=msg_id)
            mark_email_processed(message_id=msg_id, parsed_ok=True, note="is_newsletter")
        else:
            mark_email_processed(message_id=msg_id, parsed_ok=True, note="no_events_found")


if __name__ == "__main__":
    main()
