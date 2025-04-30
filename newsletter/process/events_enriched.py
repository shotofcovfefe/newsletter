"""
Enrich events rows into events_enriched for front-end cards.
"""

from __future__ import annotations

import json, os, logging, re, requests, mimetypes
from datetime import datetime, date, timedelta, timezone
from typing import Any, List

from dotenv import load_dotenv
from openai  import OpenAI
from supabase import create_client, Client
from dateutil import parser as dtparser
from dateutil.rrule import rrulestr, WEEKLY

from newsletter.types import (
    EventType, EventTargetAudience,
)

# ───────────── env / logging / clients ────────────────────────── #
load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(h)

# Make sure to set Supabase and OpenAI keys in your .env file or environment
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY]):
     raise ValueError("Supabase URL/Key or OpenAI API Key not configured in environment.")

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai = OpenAI(api_key=OPENAI_API_KEY)

# allowed enums --------------------------------------------------- #
ALLOWED_AUDIENCES  = {e.value for e in EventTargetAudience}
ALLOWED_TYPES = {e.value for e in EventType}


# ───────────── helpers ────────────────────────────────────────── #

def _get_ordinal_suffix(day: int) -> str:
    """Returns the ordinal suffix (st, nd, rd, th) for a given day."""
    if 11 <= day <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

def render_event_date_string(ev: dict[str, Any]) -> str:
    """
    Generates a user-friendly date/time string for an event card.
    Raises exceptions on parsing errors.
    """
    # --- Parsing (Errors will raise exceptions) ---
    start_dt = dtparser.isoparse(ev["start_date"])
    # Allow end_date to be None, default to start_dt if missing or empty
    end_dt_str = ev.get("end_date")
    end_dt = dtparser.isoparse(end_dt_str) if end_dt_str else start_dt
    start_date = start_dt.date()
    end_date = end_dt.date()

    # --- Logic (Errors will raise exceptions) ---
    # 1. Check for simple weekly recurrence
    if rule := ev.get("recurrence_rule"):
        # Let rrulestr raise errors if rule is invalid
        r = rrulestr(rule, dtstart=start_dt)
        if r._freq == WEEKLY and r._byweekday and len(r._byweekday) == 1:
            weekday_map = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            weekday_name = weekday_map[r._byweekday[0]]
            return f"Every {weekday_name}"
        # If not a simple weekly rule, fall through to date formatting

    # 2. Check for multi-day events
    if start_date != end_date:
        start_day = start_date.day
        end_day = end_date.day
        start_suffix = _get_ordinal_suffix(start_day)
        end_suffix = _get_ordinal_suffix(end_day)
        start_month = start_date.strftime("%b")
        end_month = end_date.strftime("%b")

        if start_month == end_month:
            return f"{start_day}{start_suffix}–{end_day}{end_suffix} {start_month}"
        else:
            start_year = start_date.strftime("%Y")
            end_year = end_date.strftime("%Y")
            start_format = f"{start_day}{start_suffix} {start_month}"
            end_format = f"{end_day}{end_suffix} {end_month}"
            if start_year != end_year:
                start_format += f" {start_year}"
                end_format += f" {end_year}"
            return f"{start_format} – {end_format}"

    # 3. Format single date
    day = start_date.day
    suffix = _get_ordinal_suffix(day)
    date_part = start_date.strftime(f"%A, {day}{suffix} %b")

    # 4. Append time information
    time_part = None
    if start_time_str := ev.get("start_time"):
        # Let parse raise errors if time format is invalid
        time_obj = dtparser.parse(start_time_str).time()
        time_part = time_obj.strftime("%H:%M")
    elif time_of_day := ev.get("time_of_day"):
         if time_of_day != "tbc":
             time_part = time_of_day.replace('_', ' ').title()

    return f"{date_part} · {time_part}" if time_part else date_part


def cost_line(ev: dict[str,Any]) -> str:
    if ev.get("is_donation_based"):
        return "Pay-what-you-can"

    cost_amount = ev.get("cost_amount")
    cost_desc = (ev.get("cost_description_verbatim", "") or "").lower()

    if cost_amount is None:
        if "free" in cost_desc or "no cost" in cost_desc:
             return "Free"
        return None

    # Attempt conversion, let errors propagate if format is wrong
    cost_val = float(cost_amount)
    money = f"{ev.get('cost_currency') or '£'}{int(cost_val) if cost_val.is_integer() else f'{cost_val:.2f}'}"

    if cost_desc:
        # Avoid redundancy
        desc_verbatim = ev.get('cost_description_verbatim', '') # Get original casing
        if str(cost_amount) in desc_verbatim or money in desc_verbatim:
             return money
        # Check again for free just in case description says free but amount is present
        if "free" in cost_desc:
             return "Free"
        return f"{money} · {desc_verbatim}"
    return money


def _clean_list(raw: list[str]|str|None, allowed:set[str]) -> list[str]:
    """Cleans list input, expects list or specific string format '{a,b}'."""
    if not raw:
        return ["tbc"]

    items_to_check: List[str] = []
    if isinstance(raw, list):
        items_to_check = raw
    elif isinstance(raw, str):
        # Handle PostgreSQL array string literal "{item1, item2}"
        if raw.startswith('{') and raw.endswith('}'):
            # Split, strip whitespace and quotes if any
            items_to_check = [item.strip().strip('"') for item in raw[1:-1].split(',')]
        else:
            # Assume single item string if not in {} format
            items_to_check = [raw]
    else:
        # Unexpected type, return tbc or raise error? Let's return tbc for now.
        logger.warning(f"Unexpected type for list cleaning: {type(raw)}. Value: {raw}")
        return ["tbc"]

    # Filter based on allowed set
    cln = [v for v in items_to_check if isinstance(v, str) and v in allowed]
    return cln or ["tbc"]


def _emoji_for_type(t: str) -> str:
    # Added more types based on EventType enum possibilities
    return {
        "music": "🎵", "film": "🎬", "food_and_drink": "🍴",
        "sports_and_fitness": "🏃", "art_and_exhibitions": "🖼️",
        "comedy": "😂", "workshops_and_classes": "🛠️",
        "theatre_and_performing_arts": "🎭", "literature_and_talks": "🎤",
        "markets_and_fairs": "🛍️", "community_and_causes": "🤝",
        "family_and_kids": "👨‍👩‍👧‍👦", "festivals": "🎉", "tours_and_walks": "🚶",
        "wellbeing_and_spirituality": "🧘", "gaming_and_technology":"🎮",
        "networking_and_business":"📈", "other": "🎫" # Default/Other
    }.get(t, "🎫") # Fallback emoji



def gpt_pretty(ev: dict[str,Any], venue_name: str) -> dict[str,str]|None:
    """Calls OpenAI GPT. Handles API errors and JSON parsing errors."""
    sys = (
        "You output STRICT JSON with keys:\n"
        "pretty_title: one representative emoji + concise, engaging title (e.g. '🎨 Life Drawing')\n"
        "venue_name: the venue name (e.g. 'The Royal Swan Pub'"
        "event_type: a one or two word summary of what it is (e.g. 'Art exhibition', 'Film', 'Life drawing', 'Food festival'. Three words if you absolutely have to.\n"
        "blurb: One or two short, factual, engaging sentences. No first-person. Never mention the venue name.\n"
        "No other keys, no markdown."
    )
    user = (
        f"Title: {ev['title']}\n"
        f"Summary: {ev['summary']}\n"
        f"Description: {ev['description_verbatim']}\n"
        f"Venue: {venue_name}\n"
        f"Event Types: {ev['event_types']}\n"
    )
    r = ai.chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"system","content":sys},{"role":"user","content":user}],
        temperature=0.4,
        response_format={"type":"json_object"},
    )
    content = r.choices[0].message.content
    return json.loads(content)


def extract_domain(email:str|None)->str|None:
    if not email or "@" not in email:
        return None
    return email.split("@",1)[1].lower()


# ───────────── main enrichment loop ────────────────────────────── #
def enrich_batch(batch: int = 500) -> None:
    processed_count = 0
    success_count = 0
    skipped_venue = 0
    skipped_gpt = 0
    error_count = 0

    # --- Get already processed/enriched event IDs (Keep try/except) ---
    done: set[str] = set()
    try:
        r_ok = sb.table("events_enriched").select("event_id").execute()
        done.update(row["event_id"] for row in (r_ok.data or []))
        r_proc = sb.table("events_enriched_processed").select("event_id").execute()
        done.update(row["event_id"] for row in (r_proc.data or []) if row["event_id"])
        logger.info(f"Found {len(done)} total unique processed/enriched events to skip.")
    except Exception as e:
        logger.error(f"CRITICAL: Failed to query existing enriched/processed events: {e}. Aborting.")
        return

    # --- Fetch batch of new events (Keep try/except) ---
    events_to_process = []
    try:
        today=date.today().isoformat()
        query = sb.table("events").select("*")
        if done:
            query = query.not_.in_("id", list(done))

        query = (
            query.gte("start_date", today)
            .not_.eq("occurrence_type", "course_session")
            .order("created_at", desc=False)
            .limit(batch)
            .execute()
        )
        events_to_process = query.data or []
        logger.info("Fetched %d new events to enrich", len(events_to_process))
    except Exception as e:
         logger.error(f"CRITICAL: Failed to fetch batch of events: {e}. Aborting.", exc_info=True)
         return

    # --- Columns to select for venue ---
    VENUE_COLUMNS = "id, name, latitude, longitude, url, postcode"

    # --- Process Events (Keep outer try/except for loop continuation) ---
    for e in events_to_process:
        eid=e["id"]
        processed_count += 1
        logger.debug(f"Processing event: {eid} - {e.get('title', 'No Title')}")

        try: # Keep this loop-level try/except for general processing errors

            # --- Fetch associated email data ---
            email_data = {}
            if msg_id := e.get("email_message_id"):
                try:
                    email_resp = sb.table("emails").select("email_address, sender_name").eq("message_id", msg_id).maybe_single().execute()
                    email_data = email_resp.data or {}
                except Exception as email_err:
                    logger.error(f"DBError fetching email data for message_id {msg_id} (event {eid}): {email_err}")
                    # Decide if this is critical - let's continue for now
            else:
                logger.warning(f"Event {eid} has no email_message_id.")

            venue = None
            email_address = email_data.get("email_address")
            domain = extract_domain(email_address)
            sender_name = email_data.get("sender_name")

            # (a) match on exact email address
            if email_address:
                venue_response = (
                    sb.table("venues")
                    .select(VENUE_COLUMNS)
                    .eq("email_address", email_address)
                    .maybe_single()
                    .execute()
                )
                if venue_response and venue_response.data:
                    venue = venue_response.data
                    logger.info(f"Venue matched by email: {email_address} -> {venue['name']}")


            # (b) match on domain (if no email match)
            if not venue and domain:
                venue_response = (
                    sb.table("venues")
                    .select(VENUE_COLUMNS)
                    .eq("domain", domain)
                    .limit(1)
                    .execute()
                    )
                if venue_response and venue_response.data:
                    venue = venue_response.data[0]
                    logger.info(f"Venue matched by domain: {domain} -> {venue['name']}")

            # (c) fallback to sender_name (if still no match)
            if not venue and sender_name:
                sender_name_lower = sender_name.strip().lower()
                generic_names = {"info", "hello", "admin", "events", "bookings"} # Keep this check
                if sender_name_lower not in generic_names:
                    venue_response = (
                        sb.table("venues")
                        .select(VENUE_COLUMNS)
                        .ilike("name", f"%{sender_name_lower}%") # Fuzzy match
                        .limit(1)
                        .execute()
                    )
                    if venue_response and venue_response.data:
                        venue = venue_response.data[0]
                        logger.info(f"Venue matched by fuzzy sender name: '{sender_name}' -> {venue['name']}")

            # --- Check if venue was found ---
            if not venue:
                logger.warning(f"Venue not found for event {eid}. Skipping.")
                _mark_processed(eid,"venue_not_found")
                skipped_venue += 1
                continue

            # --- Sanitize arrays (Errors will raise) ---
            event_types_raw = e.get("event_types")
            target_audiences_raw = e.get("target_audiences")
            vibes_tags_raw = e.get("vibes_tags")

            # --- Generate Card Fields (Errors will raise) ---
            date_line = render_event_date_string(e)
            cost = cost_line(e)

            # --- Call GPT (Errors handled inside function) ---
            pretty = gpt_pretty(e, venue["name"])

            # --- Prepare Insert Payload (Errors will raise) ---
            insert_payload = {
                "event_id"       : eid,
                "venue_id"       : venue["id"],
                "latitude"       : venue["latitude"],
                "longitude"      : venue["longitude"],
                "postcode"       : venue["postcode"],
                "card_title"     : pretty["pretty_title"],
                "venue_name"     : venue['name'],
                "card_subtitle"  : f"at {venue.get('name', 'Venue Name TBC')}",
                "card_date_line" : date_line,
                "card_vibes"     : vibes_tags_raw,
                "card_blurb"     : pretty["blurb"],
                "event_types"    : e["event_types"],
                "audience_badges": e["target_audiences"],
                "type_badge"     : pretty["event_type"],
                "cost_line"      : cost,
                "preview_image_url": e.get("image_url"),
                "venue_url"      : venue["url"],
            }

            # --- Insert into enriched table (Keep try/except) ---
            try:
                insert_resp = sb.table("events_enriched").insert(insert_payload).execute()
                if hasattr(insert_resp, 'data') and insert_resp.data:
                     logger.info(f"Success: Enriched event {eid} - {pretty['pretty_title']}")
                     _mark_processed(eid,"Success") # Mark success
                     success_count += 1
                else:
                     error_message = f"Insert failed (no data returned or potential error). Status: {getattr(insert_resp, 'status_code', 'N/A')}"
                     if hasattr(insert_resp, 'error') and insert_resp.error:
                         error_message = f"Insert failed: {insert_resp.error.message}"
                     logger.error(f"Failed to insert enriched data for event {eid}: {error_message}")
                     error_count += 1

            except Exception as insert_err:
                logger.error(f"CRITICAL: Failed to insert enriched data for event {eid}: {insert_err}", exc_info=True)
                error_count += 1

        # --- Catch errors during *this specific event's general processing* ---
        except Exception as process_err:
            # This catches errors *outside* the venue query block but *inside* the main loop for the event
            logger.error(f"Failed processing event {eid} ({e.get('title', 'No Title')}): {process_err}", exc_info=True)
            # Avoid double-marking if venue query failed and continued already
            if 'venue_exc' not in locals(): # Check if venue error was the cause
                 _mark_processed(eid, f"processing_error: {type(process_err).__name__}") # Mark general error
            error_count += 1
            # Continue to the next event in the loop

    logger.info(f"Batch summary: Processed={processed_count}, Succeeded={success_count}, Skipped (No Venue)={skipped_venue}, Skipped (GPT Fail)={skipped_gpt}, Errors={error_count}")


def _mark_processed(event_uuid: str, reason: str) -> None:
    """Marks an event as processed. Handles DB errors internally."""
    max_reason_length = 255
    reason_truncated = (reason[:max_reason_length] + '...') if len(reason) > max_reason_length else reason
    payload = {
        "event_id":     event_uuid,
        "reason":       reason_truncated,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    try: # Keep try/except for this non-critical logging operation
        sb.table("events_enriched_processed").upsert(payload, on_conflict="event_id").execute()
        logger.debug(f"Marked event {event_uuid} as processed: {reason_truncated}")
    except Exception as e:
        # Log failure to mark, but don't crash main process
        logger.error(f"Failed to mark event {event_uuid} as processed: {e}")


# ───────────── CLI entry ───────────────────────────────────────── #
def main():
    logger.info("▶ enrichment v2 run starting")
    enrich_batch()
    logger.info("✔ enrichment v2 run finished")


if __name__=="__main__":
    # Ensure logging is set up
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(h)
    logger.setLevel(logging.INFO) # Set desired level (e.g., INFO or DEBUG)

    main()