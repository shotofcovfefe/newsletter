from collections import deque
from dateutil.rrule import rrulestr, rrule
from dateutil.parser import isoparse, ParserError
from datetime import date, datetime, timedelta, timezone
import os
import time
import logging
import json
import math
import random
import urllib.parse

from zoneinfo import ZoneInfo

import requests
import typing as ta
from supabase import create_client, Client
from dotenv import load_dotenv

from newsletter.utils import (
    is_valid_london_postcode, geocode_postcode_to_latlon, haversine_distance,
    calculate_bearing, bearing_to_arrow
)

load_dotenv()

# --- Configuration and Setup ---

# Basic Logging Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO) # Explicitly set level for this logger

SUPABASE_URL: ta.Optional[str] = os.getenv("SUPABASE_URL")
SUPABASE_KEY: ta.Optional[str] = os.getenv("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN: ta.Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")

SLEEP_TIME_LENGTH: float = 0.2

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Stores event history for back button functionality
message_event_history: ta.Dict[ta.Tuple[str, int], deque[ta.Dict[str, ta.Any]]] = {}

# Stores the original command context (e.g., "load_local") for refresh consistency
message_context_type: ta.Dict[ta.Tuple[str, int], str] = {}

# Stores the current expansion state (True=expanded, False=collapsed) for toggle persistence
message_expansion_state: ta.Dict[ta.Tuple[str, int], bool] = {}

# Stores if the bot is waiting for a postcode update
awaiting_location_update: ta.Dict[str, bool] = {}

# Stores the list of events fetched by the original command for list navigation
message_event_list_cache: ta.Dict[ta.Tuple[str, int], ta.List[ta.Dict[str, ta.Any]]] = {}

# Stores the index of the currently viewed event within the cached list
message_list_index: ta.Dict[ta.Tuple[str, int], int] = {}


# --- Constants ---
HISTORY_SIZE: int = 5
DEFAULT_EVENT_FETCH_LIMIT: int = 10
DEFAULT_BROADCAST_LIMIT: int = 5
DEFAULT_RANDOM_DAYS_AHEAD: int = 7
TELEGRAM_MAX_MSG_LENGTH: int = 4000

LOCATION_PROMPT_MESSAGE: str = "I need your valid London location first! Use /updatelocation or send me your postcode."
GEOCODE_ERROR_MESSAGE: str = "Sorry, couldn't find coordinates for your location '{postcode}'. Try updating it via /updatelocation."
NO_EVENTS_MESSAGE: str = "Couldn't find any events {context} near {postcode}."
DEFAULT_ERROR_MESSAGE: str = "Sorry, something went wrong processing your request."

help_text_header = (
"Welcome to <b>Niche London</b> 👋\n\n"
"We find local events happening across London!\n\n"
)

help_text_commands = (
"Here are my commands:\n"
"/weekend - What's on this weekend? 🎉\n"
"/tomorrow - What's on tomorrow? 👣\n"
"/today - What's on today? 🔜\n"
"/local - What's on nearby? 🧭\n"
"/best - Our top picks  🏆\n"
"/random - I'm feeling lucky 🍀\n"
"/subscribe - Weekly roundup 📬\n"
"/unsubscribe - Stop already! 🫗\n"
"/updatelocation - Update location 📍\n\n"
"Or send a London postcode (e.g., <i>E8 3PN</i>)!"
)

help_text = help_text_header + help_text_commands


# --- Telegram API Helpers ---

def _telegram_api_request(method: str, payload: ta.Dict[str, ta.Any], timeout: int = 10) -> ta.Optional[ta.Dict[str, ta.Any]]:
    """Helper function to make requests to the Telegram Bot API."""
    url: str = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        resp: requests.Response = requests.post(url, json=payload, timeout=timeout)
        if resp.status_code == 200:
            return resp.json() # Type Dict[str, Any] potentially
        logger.error(f"Telegram API error for method '{method}': {resp.status_code} - {resp.text}")
        return None
    except requests.exceptions.RequestException as exc:
        logger.error(f"Network error calling Telegram API method '{method}': {exc}")
        return None
    except Exception as exc:
        logger.error(f"Unexpected error calling Telegram API method '{method}': {exc}", exc_info=True)
        return None


def get_telegram_updates(offset: ta.Optional[int] = None) -> ta.List[ta.Dict[str, ta.Any]]:
    """Poll new updates from Telegram."""
    url: str = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params: ta.Dict[str, int] = {"timeout": 30}  # Long polling timeout
    if offset is not None:
        params["offset"] = offset

    try:
        r: requests.Response = requests.get(url, params=params, timeout=40)
        if r.status_code == 200:
            return r.json().get('result', [])
        elif r.status_code == 502:
             logger.warning("Received 502 Bad Gateway from Telegram, likely restarting. Will retry.")
             time.sleep(5); return []
        else:
            logger.error(f"Failed to get updates: {r.status_code} - {r.text}"); return []
    except requests.exceptions.Timeout:
        logger.warning("Telegram getUpdates request timed out. Retrying."); return []
    except requests.exceptions.RequestException as exc:
        logger.error(f"Error getting updates: {exc}"); return []
    except Exception as exc:
        logger.error(f"Unexpected error getting updates: {exc}", exc_info=True); return []

def send_telegram_message(chat_id: str, text: str, reply_markup: ta.Optional[ta.Dict[str, ta.Any]] = None) -> ta.Optional[ta.Dict[str, ta.Any]]:
    """
    Send a text message, handling splitting.
    Returns the API response data for the *last* message part sent (which contains the keyboard), or None on failure.
    """
    parts: ta.List[str] = [text[i:i + TELEGRAM_MAX_MSG_LENGTH] for i in range(0, len(text), TELEGRAM_MAX_MSG_LENGTH)]
    last_part_response_data: ta.Optional[ta.Dict[str, ta.Any]] = None
    overall_success: bool = True

    for i, part in enumerate(parts):
        payload: ta.Dict[str, ta.Any] = {
            "chat_id": str(chat_id),
            "text": part,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        is_last_part = (i == len(parts) - 1)

        # Add reply_markup only to the last part
        if reply_markup and is_last_part:
             payload["reply_markup"] = json.dumps(reply_markup)

        # Make the API request
        response_data = _telegram_api_request("sendMessage", payload)

        if not response_data:
            overall_success = False
            # Optional: break here if one part fails? Or continue sending other parts?
            # Let's continue for now, but mark overall failure.
        elif is_last_part:
            # Store the response data only for the last part
            last_part_response_data = response_data

        # Small delay between parts if splitting
        if len(parts) > 1 and not is_last_part:
            time.sleep(SLEEP_TIME_LENGTH)

    # Return the response data of the last part IF the overall operation seems successful
    # Modify the condition based on desired behavior if parts fail.
    # Here, we return last part data even if prior parts failed, as long as last part succeeded.
    # If the *last* part failed, last_part_response_data will be None.
    # If overall_success is required, use: return last_part_response_data if overall_success else None
    return last_part_response_data if overall_success else None


def format_event_for_forwarding(event: ta.Dict[str, ta.Any]) -> str:
    """Creates a plain text summary for forwarding. Uses NEW fields."""
    lines = []
    name = (event.get("card_title") or "Event").strip()
    venue = (event.get("venue_name") or "Venue TBC").strip()
    date = (event.get("card_date_line") or "Date TBC").strip()
    cost = (event.get("cost_line") or "").strip()
    summary = (event.get("card_blurb") or "").strip()
    url = (event.get("venue_url") or "").strip()

    lines.append(f"{name}")
    lines.append(f"📍 {venue}")
    lines.append(f"📅 {date}")
    if cost: lines.append(f"💰 {cost}")
    lines.append("")

    if summary:
        lines.append(f"📝 {summary}")
        lines.append("")

    if url and (url.startswith("http://") or url.startswith("https://")):
        lines.append(f"🔗 {url}")

    return "\n".join(lines).strip()


def edit_telegram_message(chat_id: str, message_id: int, text: str, reply_markup: ta.Optional[ta.Dict[str, ta.Any]] = None) -> bool:
    """Edit an existing message."""
    if len(text) > TELEGRAM_MAX_MSG_LENGTH:
        logger.warning(f"Truncating text for editing message {message_id} in chat {chat_id}.")
        text = text[:TELEGRAM_MAX_MSG_LENGTH]

    payload: ta.Dict[str, ta.Any] = {
        "chat_id": str(chat_id),
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": json.dumps(reply_markup if reply_markup else {}) # Ensure empty dict if None
    }

    resp_data: ta.Optional[ta.Dict[str, ta.Any]] = _telegram_api_request("editMessageText", payload)

    if resp_data is None: return False # Failed request

    # Check for "message is not modified" case, which is successful operationally
    if isinstance(resp_data, dict) and resp_data.get("description") and "message is not modified" in resp_data["description"].lower():
        logger.info(f"Message {message_id} in chat {chat_id} was not modified.")
        return True # Treat as success

    # Otherwise, success if resp_data is a dictionary (indicating successful API call)
    return isinstance(resp_data, dict)

def answer_callback_query(callback_query_id: str) -> bool:
    """Acknowledge a callback query."""
    payload: ta.Dict[str, str] = {"callback_query_id": callback_query_id}
    return _telegram_api_request("answerCallbackQuery", payload, timeout=5) is not None

# --- Database Interaction Helpers ---

def get_user_postcode(chat_id: str) -> ta.Optional[str]:
    """Return the user's stored postcode."""
    try:
        resp = supabase.table("user_postcodes").select("postcode").eq("chat_id", str(chat_id)).maybe_single().execute()
        # Access data safely
        return resp.data["postcode"] if resp and hasattr(resp, 'data') and resp.data else None
    except Exception as e:
        # Catching specific Supabase/PostgREST errors is better if library provides them
        logger.error(f"DB error getting postcode for {chat_id}: {e}", exc_info=True)
        return None

def set_user_postcode(chat_id: str, postcode: str) -> bool:
    """Store or update the user's postcode using upsert."""
    try:
        supabase.table("user_postcodes").upsert({
            "chat_id": str(chat_id),
            "postcode": postcode.upper().strip(),
            "created_date": datetime.utcnow().isoformat() # Use ISO format for timestamp
        }, on_conflict="chat_id").execute()
        return True
    except Exception as e:
         logger.error(f"DB error setting postcode for {chat_id}: {e}", exc_info=True)
         return False

def upsert_chat_info(chat_id: str, chat_type: str, user_info: ta.Dict[str, ta.Any]) -> None:
    """Update chat info and ensure subscription for private chats."""
    try:
        # Assumes existence of this RPC function in Supabase
        supabase.rpc('upsert_telegram_chat', {
            'p_chat_id': str(chat_id),
            'p_chat_type': chat_type,
            'p_first_name': user_info.get('first_name'),
            'p_last_name': user_info.get('last_name'),
            'p_username': user_info.get('username')
        }).execute()

        # if chat_type == 'private':
        #     supabase.table("telegram_subscribers").upsert({
        #         "chat_id": str(chat_id),
        #         "subscribed_date": datetime.utcnow().isoformat()
        #     }, on_conflict="chat_id").execute()
    except Exception as exc:
        logger.error(f"DB error updating chat/subscriber info for chat {chat_id}: {exc}", exc_info=True)


def unsubscribe_user(chat_id: str) -> bool:
    """Unsubscribe user."""
    try:
        supabase.table("telegram_subscribers").delete().eq("chat_id", str(chat_id)).execute()
        return True
    except Exception as exc:
        logger.error(f"DB error unsubscribing chat {chat_id}: {exc}", exc_info=True)
        return False

# --- Event Fetching ---

def fetch_events(
    date_from: ta.Optional[str] = None, # Expects YYYY-MM-DD
    date_to: ta.Optional[str] = None, # Expects YYYY-MM-DD (exclusive end for ranges)
    user_lat: ta.Optional[float] = None,
    user_lon: ta.Optional[float] = None,
    max_distance_km: float = 15.0,
    limit_per_venue: int = 1,
    overall_limit: int = 5
) -> ta.List[ta.Dict[str, ta.Any]]:
    """
    Fetch events, applying date range filtering including recurrence checks in Python.
    """
    # --- Parse input dates and define target range [start_of_day, end_of_day) ---
    try:
        # Use UTC for all date comparisons
        today_dt = datetime.now(timezone.utc)

        # Determine the exact start and end datetime for the query range
        if date_from and date_to and date_from == date_to: # Single day query
             start_of_day = isoparse(date_from).replace(tzinfo=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
             end_of_day = start_of_day + timedelta(days=1)
        elif date_from and date_to: # Date range query
             start_of_day = isoparse(date_from).replace(tzinfo=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
             end_of_day = isoparse(date_to).replace(tzinfo=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_from: # Only start date given, assume single day
             start_of_day = isoparse(date_from).replace(tzinfo=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
             end_of_day = start_of_day + timedelta(days=1)
        else: # Default: today
             start_of_day = today_dt.replace(hour=0, minute=0, second=0, microsecond=0)
             end_of_day = start_of_day + timedelta(days=1)

    except (ValueError, TypeError, ParserError) as e:
        logger.error(f"Invalid date format provided: date_from='{date_from}', date_to='{date_to}'. Error: {e}")
        return []

    logger.info(f"Fetching events between {start_of_day.isoformat()} and {end_of_day.isoformat()}")

    # --- Initial Candidate Fetching from Supabase ---
    candidate_events: ta.List[ta.Dict[str, ta.Any]] = []
    try:
        # Fetch events starting before the end of the range.
        # Further filtering (recurrence, exact overlap) happens in Python.
        query = (
            supabase.table("events_enriched")
            .select("*") # Select all columns needed for filtering and display
            .lt("start_date", end_of_day.strftime("%Y-%m-%d"))
            # Optional: Add filter to exclude non-recurring events that ended before the range starts?
            # .filter("end_date", "gte", start_of_day.strftime("%Y-%m-%d")) # Might exclude needed recurring starts
            .order("start_date", desc=False)
            # Fetch more candidates as Python filtering will reduce the list
            .limit(max(overall_limit * 10, 50)) # Adjust limit as needed
        )

        resp = query.execute()
        candidate_events = resp.data if resp and hasattr(resp, 'data') and isinstance(resp.data, list) else []
        logger.info(f"Fetched {len(candidate_events)} candidate events from DB.")

    except Exception as exc:
        logger.error(f"Error fetching candidate events from Supabase: {exc}", exc_info=True)
        return [] # Return empty on DB error

    # --- Python Filtering (Date Range, Overlap & Recurrence) ---
    relevant_events: ta.List[ta.Dict[str, ta.Any]] = []
    for event in candidate_events:
        rule_str = event.get("recurrence_rule")
        start_date_str = event.get("start_date")
        end_date_str = event.get("end_date") or start_date_str # Assume end=start if missing

        if not start_date_str:
            logger.warning(f"Skipping event with missing start_date: {event.get('event_id')}")
            continue

        try:
            # Parse dates as aware datetime objects (UTC) at start of day
            event_start_dt = isoparse(start_date_str).replace(tzinfo=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            # Assume end_date is inclusive, so add 1 day to make it exclusive for range checks
            event_end_dt_exclusive = isoparse(end_date_str).replace(tzinfo=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

        except (ValueError, TypeError, ParserError):
             logger.warning(f"Skipping event: Invalid date format ID={event.get('event_id')}, Start={start_date_str}, End={end_date_str}")
             continue

        is_relevant = False
        actual_occurrence_dt = None # Store the specific date it occurs in range

        if rule_str:
            # --- Recurring Event Check ---
            try:
                # Use event's start datetime as the base for the rule
                event_rrule: rrule = rrulestr(rule_str, dtstart=event_start_dt)

                # Find the first occurrence within the target range [start_of_day, end_of_day)
                # Note: rrule.between includes start date, excludes end date by default
                occurrences_in_range = event_rrule.between(start_of_day, end_of_day - timedelta(microseconds=1), inc=True) # Make range inclusive

                if occurrences_in_range:
                    is_relevant = True
                    actual_occurrence_dt = occurrences_in_range[0] # Use first occurrence for sorting

            except (ValueError, TypeError) as e:
                 logger.warning(f"Skipping recurring event: Invalid rule/date ID={event.get('event_id')}, Rule='{rule_str}', Error: {e}")
        else:
            # --- Non-Recurring Event Check (Overlap) ---
            # Check if [event_start_dt, event_end_dt_exclusive) overlaps with [start_of_day, end_of_day)
            if event_start_dt < end_of_day and event_end_dt_exclusive > start_of_day:
                is_relevant = True
                # Use the later of event start or range start as the effective date for sorting within the range
                actual_occurrence_dt = max(event_start_dt, start_of_day)

        if is_relevant:
            # Store the specific occurrence time for sorting
            event['_occurrence_dt'] = actual_occurrence_dt
            relevant_events.append(event)

    logger.info(f"Found {len(relevant_events)} relevant events after date/recurrence filtering.")

    # --- Apply Location Filtering (to relevant events) ---
    if user_lat is not None and user_lon is not None:
        events_with_distance: ta.List[ta.Dict[str, ta.Any]] = []
        for row in relevant_events:
             lat_val = row.get("latitude"); lon_val = row.get("longitude")
             if lat_val is not None and lon_val is not None:
                 try:
                     ev_lat = float(lat_val); ev_lon = float(lon_val)
                     dist: float = haversine_distance(user_lat, user_lon, ev_lat, ev_lon)
                     if dist <= max_distance_km:
                         row["distance_km"] = dist; events_with_distance.append(row)
                 except (ValueError, TypeError): pass
        relevant_events = events_with_distance
        if not relevant_events: return []

    # --- Sort before applying venue limit for consistency ---
    # Sort by the actual occurrence time, then title
    relevant_events.sort(key=lambda x: (x.get('_occurrence_dt', datetime.max.replace(tzinfo=timezone.utc)), x.get('card_title', '')))

    # --- Apply Limit Per Venue ---
    by_venue: ta.Dict[str, int] = {}
    filtered_by_venue: ta.List[ta.Dict[str, ta.Any]] = []
    for r in relevant_events:
        v_id: ta.Optional[str] = r.get("venue_id")
        # Include events even if venue_id is missing? Assuming yes for now.
        venue_key = v_id or f"no_venue_{r.get('event_id')}" # Create unique key if no venue_id
        if venue_key not in by_venue: by_venue[venue_key] = 0
        if by_venue[venue_key] < limit_per_venue:
            filtered_by_venue.append(r)
            by_venue[venue_key] += 1
    relevant_events = filtered_by_venue
    if not relevant_events: return []

    # --- Final Sorting & Limit ---
    # If location was provided, sort the final limited set by distance
    if user_lat is not None and user_lon is not None:
        relevant_events.sort(key=lambda x: x.get("distance_km", float('inf')))
    # Otherwise, they remain sorted by occurrence date/title from before venue limiting

    # Remove temporary key before returning
    for ev in relevant_events: ev.pop('_occurrence_dt', None)

    return relevant_events[:overall_limit]


def fetch_random_events(days_ahead: int = 7, limit: int = 1) -> ta.List[ta.Dict[str, ta.Any]]:
    """Fetch random events using 'events_enriched' and 'start_date'."""
    # Keep original try/except
    try:
        # Use start_date for filtering
        today_str: str = datetime.now(timezone.utc).date().strftime("%Y-%m-%d")
        future_str: str = (datetime.now(timezone.utc).date() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        potential_limit: int = max(limit * 10, 50) # Fetch larger pool

        resp = (
            supabase.table("events_enriched")
            .select("*")
            # Use start_date instead of event_date
            .gte("start_date", today_str)
            .lt("start_date", future_str)
            .limit(potential_limit)
            .execute()
        )
        data: ta.List[ta.Dict[str, ta.Any]] = resp.data if resp and hasattr(resp, 'data') and isinstance(resp.data, list) else []
        if not data: return []
        random.shuffle(data)
        return data[:limit]
    except Exception as exc:
        logger.error(f"Error fetching random events: {exc}", exc_info=True)
        return []

# --- Formatting and Keyboard Helpers ---

def format_events_message(
    events: ta.List[ta.Dict[str, ta.Any]],
    time_period: str = "",
    postcode: str = "",
    user_lat: ta.Optional[float] = None,
    user_lon: ta.Optional[float] = None,
    show_details: bool = False
) -> str:
    """Formats events using NEW fields from events_enriched."""
    if not events: return ""

    lines: ta.List[str] = []
    if len(events) > 1:
        header_parts: ta.List[str] = ["Here are events"]
        if time_period: header_parts.append(time_period)
        lines.append(" ".join(header_parts) + ":\n")

    for ev in events:
        event_lines: ta.List[str] = []
        type_badge = (ev.get("type_badge") or "").strip()
        name: str = (ev.get("card_title") or "Event").strip()
        venue: str = (ev.get("venue_name") or "Venue TBC").strip()
        date: str = (ev.get("card_date_line") or "Date TBC").strip()
        cost: str = (ev.get("cost_line") or "").strip()
        url: str = (ev.get("venue_url") or "").strip()
        vibes: str = (ev.get("card_vibes") or "").strip()
        summary: str = (ev.get("card_blurb") or "").strip()

        title_line = f"<b>{name}</b>"
        if type_badge:
             title_line = f"<b>{type_badge} {name}</b>"
        event_lines.append(title_line)

        venue_html: str = f"<i>{venue}</i>"
        if url and (url.startswith("http://") or url.startswith("https://")):
            try:
                encoded_url: str = urllib.parse.quote(url, safe=':/%#?=&')
                venue_html = f'<a href="{encoded_url}">{venue}</a>'
            except Exception as e: logger.warning(f"Failed to encode URL '{url}': {e}")
        event_lines.append(f"📍 {venue_html}")

        if show_details:
            if summary:
                 max_summary_len: int = 250
                 display_summary = summary
                 if len(display_summary) > max_summary_len: display_summary = display_summary[:max_summary_len] + "..."
                 event_lines.append(f"👉 {display_summary}")
            # if vibes:
            #     event_lines.append(f"✨ {vibes}")

        event_lines.append(f"📅 {date}")
        if cost:
             event_lines.append(f"💰 {cost}")

        if "distance_km" in ev and postcode and user_lat is not None and user_lon is not None:
            try:
                dist_km: float = float(ev["distance_km"])
                arrow: str = ""
                lat_val = ev.get("latitude")
                lon_val = ev.get("longitude")
                if lat_val is not None and lon_val is not None:
                     ev_lat = float(lat_val)
                     ev_lon = float(lon_val)
                     bearing: float = calculate_bearing(user_lat, user_lon, ev_lat, ev_lon)
                     arrow = bearing_to_arrow(bearing) + " "

                dist_str: str
                if dist_km < 0.01: dist_str = "<10m"
                elif dist_km < 0.1: dist_str = f"{round(dist_km * 1000)}m"
                elif dist_km < 1: dist_str = f"{round(dist_km * 100)/100 * 1000:.0f}m"
                elif dist_km < 10: dist_str = f"{dist_km:.1f}km"
                else: dist_str = f"{round(dist_km)}km"

                event_lines.append(f"🧭 <i>{dist_str} {arrow}from {postcode.upper()}</i>")
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                 logger.warning(f"Error processing distance/bearing for event {ev.get('event_id')}: {e}", exc_info=False)

        lines.append("\n".join(event_lines))

    return "\n\n".join(lines)


def create_event_keyboard(
    event: ta.Dict[str, ta.Any],
    refresh_callback_data: str,
    can_go_back: bool,
    can_go_forward: bool,
    is_currently_expanded: bool
) -> ta.Optional[ta.Dict[str, ta.Any]]:
    """Creates the inline keyboard with a two-row layout."""

    nav_row: ta.List[ta.Dict[str, str]] = []
    action_row: ta.List[ta.Dict[str, str]] = []

    # --- Populate Top Navigation Row ---
    # 1. Back Button
    if can_go_back:
        nav_row.append({"text": "⏪ Back", "callback_data": "show_previous"})

    # 2. Refresh/Random Button (using original context callback)
    nav_row.append({"text": "🔄 Next", "callback_data": refresh_callback_data})

    # 3. Forward Navigation Button
    if can_go_forward: # Requires logic to determine if forward is possible
        nav_row.append({"text": "⏩", "callback_data": "show_next"})

    # --- Populate Bottom Action Row ---
    # 1. Toggle Button
    summary = (event.get("card_blurb") or "").strip()
    vibes = (event.get("card_vibes") or "").strip()
    has_details_to_toggle = bool(summary or vibes)
    if has_details_to_toggle:
        button_text = "➖ Less" if is_currently_expanded else "➕ More"
        callback_action = "toggle_details_hide" if is_currently_expanded else "toggle_details_show"
        action_row.append({"text": button_text, "callback_data": callback_action})

    # 2. Map Button
    venue_name: ta.Optional[str] = event.get("venue_name")
    venue_postcode: ta.Optional[str] = event.get("postcode")
    if venue_name and venue_postcode:
        # Keep original try/except for URL generation
        try:
            search_query: str = f"{venue_name}, {venue_postcode}"
            # Consider using https for maps link
            maps_url: str = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(search_query)}"
            # maps_url: str = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(search_query)}" # Original link
            action_row.append({"text": "📍 Map", "url": maps_url})
        except Exception as e: logger.error(f"Error creating map link: {e}")

    # 3. Forward/Share Button
    # Keep original try/except for forwarding text generation
    try:
        forward_text: str = format_event_for_forwarding(event)
        action_row.append({"text": "📤 Share", "switch_inline_query": forward_text or "Check out this event!"})
    except Exception as e:
        logger.error(f"Error formatting event for forwarding: {e}")

    # --- Construct Keyboard ---
    keyboard_rows = []
    if nav_row:
        keyboard_rows.append(nav_row)
    if action_row:
        keyboard_rows.append(action_row)

    if keyboard_rows:
        return {"inline_keyboard": keyboard_rows}
    else:
        return None # Return None if somehow no buttons are generated


# --- Location Handling Helper ---

def get_user_location(chat_id: str) -> ta.Tuple[ta.Optional[str], ta.Optional[float], ta.Optional[float]]:
    """Gets validated postcode and coordinates for a user."""
    postcode: ta.Optional[str] = get_user_postcode(chat_id)
    if not postcode or not is_valid_london_postcode(postcode): # Assume is_valid checks format/existence
        return None, None, None

    # Try geocoding
    lat, lon = geocode_postcode_to_latlon(postcode) # Assumes this returns Optional[float], Optional[float]
    if lat is None or lon is None:
        return postcode, None, None # Return postcode even if geocoding fails, indicates attempt

    return postcode, lat, lon

# --- Command/Callback Processing Helpers ---


def handle_single_event_command(chat_id: str, command: str) -> None:
    """
    Handles commands, fetches an initial list of events, stores it,
    and displays the first event with navigation buttons.
    """
    command_config = {
        "/local": {"cb": "load_local", "ctx": "nearby", "loc": True, "days": 7},
        "/today": {"cb": "load_today", "ctx": "today", "loc": True, "days": 0},
        "/tomorrow": {"cb": "load_tomorrow", "ctx": "tomorrow", "loc": True, "days": 1},
        "/weekend": {"cb": "load_weekend", "ctx": "this weekend", "loc": True},
        "/random": {"cb": "load_random", "ctx": "a random event", "loc": False},
        "/best": {"cb": "load_best", "ctx": "a top pick", "loc": False},
    }
    config = command_config.get(command);
    if not config: logger.error(f"Invalid command: {command}"); return
    callback_data: str = config["cb"]; time_period_context: str = config["ctx"]
    is_location_based: bool = config["loc"]
    user_pc: ta.Optional[str] = None; lat: ta.Optional[float] = None; lon: ta.Optional[float] = None
    fetch_params: ta.Dict[str, ta.Any] = {}; fetched_events: ta.List[ta.Dict[str, ta.Any]] = []
    no_event_context: str = ""
    if is_location_based:
        user_pc, lat, lon = get_user_location(chat_id)
        if not user_pc: send_telegram_message(chat_id, LOCATION_PROMPT_MESSAGE); return
        if lat is None or lon is None: send_telegram_message(chat_id, GEOCODE_ERROR_MESSAGE.format(postcode=user_pc)); return
        fetch_params.update({"user_lat": lat, "user_lon": lon}); no_event_context = f"near {user_pc.upper()}"

    try:
        today_date = datetime.now(timezone.utc).date()
        date_from_str: ta.Optional[str] = None; date_to_str: ta.Optional[str] = None
        if command == "/weekend": today_weekday=today_date.weekday(); days_until_saturday=(5-today_weekday+7)%7; saturday_date=today_date+timedelta(days=days_until_saturday); monday_date=saturday_date+timedelta(days=2); date_from_str=saturday_date.strftime("%Y-%m-%d"); date_to_str=monday_date.strftime("%Y-%m-%d"); no_event_context = f"starting this weekend {no_event_context}".strip()
        elif command in ["/local", "/today", "/tomorrow"]: days_offset = config.get("days", 0); start_date = today_date + timedelta(days=days_offset); end_date = start_date + timedelta(days=(7 if command == "/local" else 1)); date_from_str = start_date.strftime("%Y-%m-%d"); date_to_str = end_date.strftime("%Y-%m-%d"); no_event_context = f"starting {'in the next 7 days' if command == '/local' else time_period_context} {no_event_context}".strip()

        list_fetch_limit = HISTORY_SIZE
        if command in ["/random", "/best"]:
            fetched_events = fetch_random_events(days_ahead=DEFAULT_RANDOM_DAYS_AHEAD, limit=list_fetch_limit)
            no_event_context = "matching that criteria"
        elif is_location_based or command in ["/local", "/today", "/tomorrow", "/weekend"]:
             fetch_params["date_from"] = date_from_str; fetch_params["date_to"] = date_to_str
             fetched_events = fetch_events( overall_limit=list_fetch_limit, limit_per_venue=2, **fetch_params )

        if not fetched_events:
            base_msg = NO_EVENTS_MESSAGE.format(context=no_event_context, postcode=user_pc.upper() if user_pc else "your area")
            suggestion_map = {"/today": "\nMaybe try /tomorrow or /weekend?", "/tomorrow": "\nMaybe try /weekend or /local?", "/weekend": "\nMaybe try /local?", "/local": "\nMaybe try /random?", "/best": "\nMaybe try /local or /random?"}
            suggestion = suggestion_map.get(command, "")
            send_telegram_message(chat_id, base_msg + suggestion); return

        event_to_display = fetched_events[0]
        if lat is not None and lon is not None:
             try:
                 lat_val=event_to_display.get("latitude"); lon_val=event_to_display.get("longitude")
                 if lat_val is not None and lon_val is not None: ev_lat=float(lat_val); ev_lon=float(lon_val); event_to_display["distance_km"]=haversine_distance(lat,lon,ev_lat,ev_lon)
             except (ValueError, TypeError) as e: logger.warning(f"Could not calc dist {command}: {e}")

    except Exception as e:
        logger.error(f"Error fetching list {command}: {e}", exc_info=True); send_telegram_message(chat_id, DEFAULT_ERROR_MESSAGE); return

    try:
        can_go_forward = len(fetched_events) > 1
        keyboard = create_event_keyboard( event=event_to_display, refresh_callback_data=callback_data, can_go_back=False, can_go_forward=can_go_forward, is_currently_expanded=False )
        message_text = format_events_message( events=[event_to_display], time_period=time_period_context, postcode=user_pc, user_lat=lat, user_lon=lon, show_details=False )

        sent_message_api_response = _telegram_api_request("sendMessage", { "chat_id": str(chat_id), "text": message_text, "parse_mode": "HTML", "disable_web_page_preview": True, "reply_markup": json.dumps(keyboard if keyboard else {}) })

        if sent_message_api_response and sent_message_api_response.get('ok') and isinstance(sent_message_api_response.get("result"), dict) and (msg_id := sent_message_api_response["result"].get('message_id')):
            history_key = (str(chat_id), msg_id)
            # Initialize all state, including list cache, regardless of length initially
            message_event_history[history_key] = deque([event_to_display.copy()], maxlen=HISTORY_SIZE)
            message_context_type[history_key] = callback_data
            message_expansion_state[history_key] = False
            message_event_list_cache[history_key] = fetched_events # Store the list always
            message_list_index[history_key] = 0 # Store index 0 always
            logger.info(f"Initialized state msg {msg_id}. List size: {len(fetched_events)}")
        else: logger.error(f"Failed message_id {command}. API Response: {sent_message_api_response}")

    except Exception as e:
        logger.error(f"Error formatting/sending {command}: {e}", exc_info=True); send_telegram_message(chat_id, DEFAULT_ERROR_MESSAGE)


def handle_refresh_callback(chat_id: str, message_id: int, callback_data: str) -> None:
    """Handles all refresh callback queries (load_...). Updates history."""
    # --- Initial Setup ---
    fetch_params: ta.Dict[str, ta.Any] = {}
    user_pc: ta.Optional[str] = None; lat: ta.Optional[float] = None; lon: ta.Optional[float] = None
    fetch_limit: int = DEFAULT_EVENT_FETCH_LIMIT
    # Determine command type from callback data
    is_location_based: bool = callback_data in ["load_local", "load_today", "load_tomorrow", "load_weekend"]
    is_random: bool = callback_data == "load_random"; is_best: bool = callback_data == "load_best"
    time_period_context: str = ""; no_event_context: str = ""
    event_to_show: ta.Optional[ta.Dict[str, ta.Any]] = None;
    fetched_events: ta.List[ta.Dict[str, ta.Any]] = []

    # --- Get Location if Needed ---
    if is_location_based:
        user_pc, lat, lon = get_user_location(chat_id)
        if not user_pc: edit_telegram_message(chat_id, message_id, LOCATION_PROMPT_MESSAGE, None); return
        if lat is None or lon is None: edit_telegram_message(chat_id, message_id, GEOCODE_ERROR_MESSAGE.format(postcode=user_pc), None); return
        fetch_params.update({"user_lat": lat, "user_lon": lon}); no_event_context = f"near {user_pc.upper()}"

    # --- Determine Fetch Dates/Context ---
    today_dt: datetime = datetime.utcnow()
    today_date: datetime.date = today_dt.date() # Use only date part for calculations

    if callback_data == "load_local":
        fetch_params["date_from"] = today_date.strftime("%Y-%m-%d")
        fetch_params["date_to"] = (today_date + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        time_period_context = "nearby"; no_event_context = f"in the next 7 days {no_event_context}".strip()
    elif callback_data == "load_today":
        fetch_params["date_from"] = today_date.strftime("%Y-%m-%d")
        fetch_params["date_to"] = today_date.strftime("%Y-%m-%d") # Date range is just today
        time_period_context = "today"; no_event_context = f"today {no_event_context}".strip()
    elif callback_data == "load_tomorrow":
        tomorrow_date = today_date + datetime.timedelta(days=1)
        fetch_params["date_from"] = tomorrow_date.strftime("%Y-%m-%d")
        fetch_params["date_to"] = tomorrow_date.strftime("%Y-%m-%d") # Date range is just tomorrow
        time_period_context = "tomorrow"; no_event_context = f"tomorrow {no_event_context}".strip()
    # --- ADDED: Weekend Logic ---
    elif callback_data == "load_weekend":
        today_weekday = today_date.weekday() # Monday is 0, Sunday is 6
        days_until_saturday = (5 - today_weekday + 7) % 7
        saturday_date = today_date + datetime.timedelta(days=days_until_saturday)
        monday_date = saturday_date + datetime.timedelta(days=2) # End date is exclusive
        fetch_params["date_from"] = saturday_date.strftime("%Y-%m-%d")
        fetch_params["date_to"] = monday_date.strftime("%Y-%m-%d")
        time_period_context = "this weekend"; no_event_context = f"this weekend {no_event_context}".strip()
    # --- END Weekend Logic ---

    # --- Fetch event(s) ---
    if is_random or is_best:
        # Fetch more for random/best to allow choosing a different one
        fetched_events = fetch_random_events(days_ahead=DEFAULT_RANDOM_DAYS_AHEAD, limit=fetch_limit)
        time_period_context = "a random event" if is_random else "a top pick"; no_event_context = "randomly" if is_random else "as a top pick"
    elif is_location_based:
        fetched_events = fetch_events(overall_limit=fetch_limit, **fetch_params)
    else: logger.error(f"Unhandled callback type in refresh handler: {callback_data}"); return

    # --- Select Event to Show (Try not to repeat) ---
    history_key = (chat_id, message_id) # Define history key here
    history = message_event_history.get(history_key)
    last_event_id = history[-1].get('event_id') if history else None
    if fetched_events:
         # Filter out the last shown event if possible and multiple options exist
         potential_events = [e for e in fetched_events if e.get('event_id') != last_event_id]
         if potential_events: # If filtering left any events
             event_to_show = random.choice(potential_events)
             logger.info(f"Refresh for msg {message_id}: Chose different event {event_to_show.get('event_id', 'N/A')} from {len(potential_events)} options.")
         else: # All fetched events were the same as last shown, or only one fetched
             event_to_show = fetched_events[0]
             logger.info(f"Refresh for msg {message_id}: Re-showing event {event_to_show.get('event_id', 'N/A')} or only one option found.")
    logger.debug(f"Refresh selected event: {event_to_show.get('event_id') if event_to_show else 'None'}") # Debug log

    # --- Update message or show 'no events' ---
    if event_to_show:
        # Get location info again for formatting distance
        user_pc_refresh, lat_refresh, lon_refresh = (user_pc, lat, lon) if is_location_based else get_user_location(chat_id)
        # Add distance if possible
        if lat_refresh is not None and lon_refresh is not None:
            try:
                ev_lat=float(event_to_show.get("latitude",math.nan)); ev_lon=float(event_to_show.get("longitude",math.nan))
                if not math.isnan(ev_lat) and not math.isnan(ev_lon): event_to_show["distance_km"] = haversine_distance(lat_refresh, lon_refresh, ev_lat, ev_lon)
            except: pass
        # Update History
        if history_key not in message_event_history: message_event_history[history_key] = deque(maxlen=HISTORY_SIZE)
        message_event_history[history_key].append(event_to_show.copy())
        if history_key not in message_context_type: message_context_type[history_key] = callback_data # Store original context
        current_history_len = len(message_event_history[history_key])
        logger.info(f"Appended history for msg {message_id}. New len: {current_history_len}")
        # Format and Edit
        can_go_back = current_history_len > 1
        keyboard = create_event_keyboard( event_to_show, callback_data, can_go_back, is_currently_expanded=False ) # Reset to collapsed view
        message_text = format_events_message(
            events=[event_to_show], postcode=user_pc_refresh, user_lat=lat_refresh, user_lon=lon_refresh,
            time_period=time_period_context, show_details=False # Reset to collapsed view
        )
        if not edit_telegram_message(chat_id, message_id, message_text, reply_markup=keyboard):
            logger.error(f"Edit failed for refresh callback {callback_data} on msg {message_id}")
    else: # No event found
        final_no_event_msg = NO_EVENTS_MESSAGE.format(context=f"further {no_event_context}", postcode=user_pc.upper() if user_pc else "your area")
        edit_telegram_message(chat_id, message_id, final_no_event_msg, reply_markup=None)


# ---------------------------------------------------------------------
# Send Individual Event Messages (Used by postcode search etc.)
# ---------------------------------------------------------------------

def send_event_messages(
    chat_id: str,
    events: ta.List[ta.Dict[str, ta.Any]],
    postcode: str = "",
    user_lat: ta.Optional[float] = None,
    user_lon: ta.Optional[float] = None
):
    """Send each event as an individual message using updated formatter."""
    if not events:
         logger.info(f"No events provided to send_event_messages for chat {chat_id}.")
         return

    for event in events:
        # Calls the updated format_events_message
        message = format_events_message(
            events=[event],
            postcode=postcode,
            user_lat=user_lat,
            user_lon=user_lon,
            show_details=False # Default to collapsed for individual sends
        )
        if message:
            # Send message WITHOUT reply_markup
            send_telegram_message(chat_id, message, reply_markup=None)
            time.sleep(SLEEP_TIME_LENGTH)
        else:
            logger.warning(f"Empty message generated by format_events_message for event: {event.get('event_id', 'N/A')}")

# --- Main Message Processing Logic ---

def process_message(msg: ta.Dict[str, ta.Any]) -> None:
    """Handles incoming text messages and commands."""
    chat_info: ta.Dict[str, ta.Any] = msg.get('chat', {})
    chat_id: str = str(chat_info.get('id', ''))
    chat_type: str = chat_info.get('type', '')
    user_info: ta.Dict[str, ta.Any] = msg.get('from', {})
    user_id: str = str(user_info.get('id', ''))

    if not chat_id or user_info.get('is_bot') or msg.get('edit_date'): return
    text_raw: str = (msg.get('text') or '').strip()
    text_lower: str = text_raw.lower()
    logger.info(f"Processing message from chat {chat_id} (user: {user_id}): '{text_raw}'")

    # Keep original try/except around DB operation
    try:
        upsert_chat_info(chat_id, chat_type, user_info)
    except Exception as e:
         logger.error(f"DB error in upsert_chat_info for {chat_id}: {e}", exc_info=False) # Log DB error but continue


    if text_lower == "/start":
        awaiting_location_update[chat_id] = False
        send_telegram_message(chat_id, help_text)
        return

    if text_lower in ["/help", "help", "hello", "hi", "?"]:
        awaiting_location_update[chat_id] = False
        try:
            # Keep original try/except around timezone operation
            now_london = datetime.now(ZoneInfo("Europe/London"))
            weekday = now_london.weekday()
            greetings = { 4: "Happy Friday! 🎉 Looking for weekend events?\n\n", 5: "Hope you're having a great weekend! 😎\n\n", 6: "Hope you're having a great weekend! 😎\n\n", 0: "Morning! Hope you had a good weekend. Planning your week?\n\n"}
            greeting = greetings.get(weekday, "Hi there! 👋 Let's find some events.\n\n")
        except Exception as e: # Catch potential ZoneInfo errors
             logger.warning(f"ZoneInfo lookup failed: {e}")
             greeting = "Hi there! 👋 Let's find some events.\n\n"
        send_telegram_message(chat_id, greeting + help_text_commands)
        return

    if text_lower == "/updatelocation":
        awaiting_location_update[chat_id] = True
        send_telegram_message(chat_id, "OK. Please send me your London postcode (e.g., SW1A 0AA).")
        return

    if text_lower == "/subscribe":
        if chat_type == 'private':
            awaiting_location_update[chat_id] = False
            logger.info(f"Processing /subscribe for chat {chat_id}")
            try: # Keep original try/except around DB operation
                supabase.table("telegram_subscribers").upsert({"chat_id": str(chat_id),"subscribed_date": datetime.now(timezone.utc).isoformat()}, on_conflict="chat_id").execute()
                send_telegram_message(chat_id, "✅ You've subscribed to the weekly roundup!")
            except Exception as e:
                logger.error(f"Error subscribing chat {chat_id}: {e}", exc_info=True)
                send_telegram_message(chat_id, "⚠️ Sorry, there was an error trying to subscribe you.")
        else:
            send_telegram_message(chat_id, "Subscription commands only work in a private chat with me.")
        return

    if text_lower == "/unsubscribe":
        if chat_type == 'private':
            awaiting_location_update[chat_id] = False
            # Keep original helper call (which has try/except)
            if unsubscribe_user(chat_id):
                send_telegram_message(chat_id, "You've been unsubscribed from the weekly roundup.")
            else:
                send_telegram_message(chat_id, "Sorry, there was an error trying to unsubscribe.")
        else:
            send_telegram_message(chat_id, "Subscription commands only work in a private chat with me.")
        return

    # --- Single Event Commands ---
    # Calls the updated handle_single_event_command implicitly
    if text_lower in ["/local", "/today", "/tomorrow", "/weekend", "/random", "/best"]:
        awaiting_location_update[chat_id] = False
        handle_single_event_command(chat_id, text_lower)
        return

    # --- Postcode Handling ---
    elif is_valid_london_postcode(text_raw.upper()):
        postcode_norm: str = text_raw.upper()
        is_updating = awaiting_location_update.get(chat_id, False)
        pc_lat, pc_lon = None, None

        # Keep original try/except around geocoding
        try: pc_lat, pc_lon = geocode_postcode_to_latlon(postcode_norm)
        except Exception as e: logger.error(f"Geocoding error for '{postcode_norm}': {e}")

        if is_updating:
            if pc_lat is not None and pc_lon is not None:
                # Keep original helper call (which has try/except)
                if set_user_postcode(chat_id, postcode_norm):
                    send_telegram_message(chat_id, f"✅ Location updated to {postcode_norm}!")
                else: send_telegram_message(chat_id, "⚠️ There was an error saving your postcode.")
            else: send_telegram_message(chat_id, f"⚠️ Couldn't validate postcode {postcode_norm}. Please try a different London postcode.")
            awaiting_location_update[chat_id] = False
        else: # Not updating, treat as a search
            if pc_lat is not None and pc_lon is not None:
                send_telegram_message(chat_id, f"OK, looking for events near {postcode_norm}...")
                today_dt_pc = datetime.now(timezone.utc)
                # Calls updated fetch_events
                events_pc: ta.List[ta.Dict[str, ta.Any]] = fetch_events(
                    date_from=today_dt_pc.strftime("%Y-%m-%d"),
                    date_to=(today_dt_pc + timedelta(days=7)).strftime("%Y-%m-%d"),
                    user_lat=pc_lat, user_lon=pc_lon, overall_limit=5
                )
                if events_pc:
                    # Calls updated send_event_messages (which calls updated formatter)
                    send_event_messages( chat_id=chat_id, events=events_pc, postcode=postcode_norm, user_lat=pc_lat, user_lon=pc_lon )
                else:
                    # Updated context string to mention "starting"
                    send_telegram_message(chat_id, f"Couldn't find any events starting near {postcode_norm} in the next 7 days.")
            else: send_telegram_message(chat_id, f"Sorry, I couldn’t find coordinates for {postcode_norm}.")
        return

    # --- Fallback ---
    else:
        if not awaiting_location_update.get(chat_id, False):
            send_telegram_message(chat_id, "Sorry, I didn't understand that. Try /help for commands.")


def process_callback_query(callback_query: ta.Dict[str, ta.Any]) -> None:
    """Handles incoming callback queries using updated fetch/format logic."""
    query_id: ta.Optional[str] = callback_query.get('id')
    message: ta.Optional[ta.Dict[str, ta.Any]] = callback_query.get('message')
    data: ta.Optional[str] = callback_query.get('data')

    if not query_id or not message or not data:
        logger.warning("Received incomplete callback query: %s", callback_query)
        if query_id: answer_callback_query(query_id)
        return

    chat_id: str = str(message.get('chat', {}).get('id', ''))
    message_id: ta.Optional[int] = message.get('message_id')

    try: answer_callback_query(query_id)
    except Exception as e: logger.error(f"Failed ack callback {query_id}: {e}")

    if not chat_id or not message_id: logger.error(f"No chat/msg ID from cb {query_id}"); return

    history_key = (chat_id, message_id)
    logger.info(f"Processing callback '{data}' for msg {message_id} in chat {chat_id}")

    original_context = message_context_type.get(history_key) # Needed for multiple actions

    # --- Refresh Actions (load_*) ---
    if data.startswith("load_"):
        # Keep original try/except block
        try:
            # Re-fetch a SINGLE new event based on original context
            # Note: This resets the list navigation
            fetch_params: ta.Dict[str, ta.Any] = {}
            user_pc: ta.Optional[str]=None; lat: ta.Optional[float]=None; lon: ta.Optional[float]=None
            fetch_limit: int = DEFAULT_EVENT_FETCH_LIMIT # Fetch more to find different one
            is_location_based: bool = data in ["load_local", "load_today", "load_tomorrow", "load_weekend"]
            is_random: bool = data == "load_random"; is_best: bool = data == "load_best"
            time_period_context: str = ""; no_event_context: str = ""
            event_to_show: ta.Optional[ta.Dict[str, ta.Any]] = None; fetched_events: ta.List[ta.Dict[str, ta.Any]] = []

            if is_location_based:
                user_pc, lat, lon = get_user_location(chat_id)
                if not user_pc: edit_telegram_message(chat_id, message_id, LOCATION_PROMPT_MESSAGE, None); return
                if lat is None or lon is None: edit_telegram_message(chat_id, message_id, GEOCODE_ERROR_MESSAGE.format(postcode=user_pc), None); return
                fetch_params.update({"user_lat": lat, "user_lon": lon}); no_event_context = f"near {user_pc.upper()}"

            date_from_str: ta.Optional[str] = None; date_to_str: ta.Optional[str] = None
            today_date = datetime.now(timezone.utc).date()
            if data=="load_local": date_from_str=today_date.strftime("%Y-%m-%d"); date_to_str=(today_date + timedelta(days=7)).strftime("%Y-%m-%d"); time_period_context="nearby"; no_event_context = f"starting in the next 7 days {no_event_context}".strip()
            elif data=="load_today": date_from_str=today_date.strftime("%Y-%m-%d"); date_to_str=(today_date + timedelta(days=1)).strftime("%Y-%m-%d"); time_period_context="today"; no_event_context = f"starting today {no_event_context}".strip()
            elif data=="load_tomorrow": tomorrow_date=today_date+timedelta(days=1); date_from_str=tomorrow_date.strftime("%Y-%m-%d"); date_to_str=(tomorrow_date + timedelta(days=1)).strftime("%Y-%m-%d"); time_period_context="tomorrow"; no_event_context = f"starting tomorrow {no_event_context}".strip()
            elif data=="load_weekend": today_weekday=today_date.weekday(); days_until_saturday=(5-today_weekday+7)%7; saturday_date=today_date+timedelta(days=days_until_saturday); monday_date=saturday_date+timedelta(days=2); date_from_str=saturday_date.strftime("%Y-%m-%d"); date_to_str=monday_date.strftime("%Y-%m-%d"); time_period_context="this weekend"; no_event_context = f"starting this weekend {no_event_context}".strip()

            if is_random or is_best: fetched_events = fetch_random_events(days_ahead=DEFAULT_RANDOM_DAYS_AHEAD, limit=fetch_limit); time_period_context="a random event" if is_random else "a top pick"; no_event_context="randomly" if is_random else "as a top pick"
            elif is_location_based or data in ["load_local", "load_today", "load_tomorrow", "load_weekend"]:
                 fetch_params["date_from"] = date_from_str; fetch_params["date_to"] = date_to_str
                 fetched_events = fetch_events(overall_limit=fetch_limit, **fetch_params) # Fetch list to find a different one
            else: logger.error(f"Unhandled cb type {data}"); return

            history = message_event_history.get(history_key)
            last_event_id = history[-1].get('event_id') if history else None
            if fetched_events:
                 potential_events = [e for e in fetched_events if e.get('event_id') != last_event_id]
                 event_to_show = random.choice(potential_events) if potential_events else fetched_events[0]
            logger.info(f"Refresh selected event {event_to_show.get('event_id') if event_to_show else 'None'}")

            if event_to_show:
                user_pc_refresh, lat_refresh, lon_refresh = (user_pc, lat, lon) if is_location_based else get_user_location(chat_id)
                if lat_refresh is not None and lon_refresh is not None:
                    try: # Add distance
                        lat_val=event_to_show.get("latitude"); lon_val=event_to_show.get("longitude")
                        if lat_val is not None and lon_val is not None: ev_lat=float(lat_val); ev_lon=float(lon_val); event_to_show["distance_km"]=haversine_distance(lat_refresh,lon_refresh,ev_lat,ev_lon)
                    except (ValueError, TypeError) as e: logger.warning(f"Failed dist on refresh: {e}")

                # Reset List Navigation State on Refresh
                message_event_list_cache.pop(history_key, None)
                message_list_index.pop(history_key, None)
                logger.info(f"Reset list navigation state for msg {message_id} due to refresh.")

                # Update View History
                if history_key not in message_event_history: message_event_history[history_key] = deque(maxlen=HISTORY_SIZE)
                message_event_history[history_key].append(event_to_show.copy())
                message_context_type[history_key] = data # Update context if needed? Or keep original? Let's keep original context type 'data'
                current_history_len = len(message_event_history[history_key])
                logger.info(f"Appended history for msg {message_id}. New len: {current_history_len}")

                # Read expansion state (preserve it)
                current_state_expanded = message_expansion_state.get(history_key, False)

                # Format and Edit - No forward button possible after refresh resets list
                keyboard = create_event_keyboard( event=event_to_show, refresh_callback_data=data, can_go_back=True, can_go_forward=False, is_currently_expanded=current_state_expanded)
                message_text = format_events_message( events=[event_to_show], postcode=user_pc_refresh, user_lat=lat_refresh, user_lon=lon_refresh, time_period=time_period_context, show_details=current_state_expanded)

                if not edit_telegram_message(chat_id, message_id, message_text, reply_markup=keyboard): logger.error(f"Edit failed for refresh {data} on msg {message_id}")
            else:
                final_no_event_msg = NO_EVENTS_MESSAGE.format(context=f"further events {no_event_context}", postcode=user_pc.upper() if user_pc else "your area")
                edit_telegram_message(chat_id, message_id, final_no_event_msg, reply_markup=None)
        except Exception as e:
            logger.error(f"Error handling refresh callback {data}: {e}", exc_info=True)
            try: edit_telegram_message(chat_id, message_id, DEFAULT_ERROR_MESSAGE, None)
            except Exception: pass

    # --- Back Action (Uses List Cache) ---
    elif data == "show_previous":
        cached_list = message_event_list_cache.get(history_key)
        current_index = message_list_index.get(history_key)

        # Check if list cache exists and index is valid for going back
        if cached_list is not None and current_index is not None and current_index > 0:
            try:
                new_index = current_index - 1
                event_to_show = cached_list[new_index]
                message_list_index[history_key] = new_index  # Update state

                can_go_back = new_index > 0  # Correctly checks lower bound
                # --- MODIFIED LINE ---
                # Check if forward is possible based on list bounds
                can_go_forward = new_index < len(cached_list) - 1
                # --- END MODIFIED LINE ---

                user_pc_back, lat_back, lon_back = get_user_location(chat_id)
                if lat_back is not None and lon_back is not None:
                    try:  # Add distance
                        lat_val = event_to_show.get("latitude");
                        lon_val = event_to_show.get("longitude")
                        if lat_val is not None and lon_val is not None: ev_lat = float(lat_val);ev_lon = float(lon_val);
                        event_to_show["distance_km"] = haversine_distance(lat_back, lon_back, ev_lat, ev_lon)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed dist back: {e}")

                current_state_expanded = message_expansion_state.get(history_key, False)
                keyboard = create_event_keyboard(event=event_to_show, refresh_callback_data=original_context,
                                                 can_go_back=can_go_back, can_go_forward=can_go_forward,
                                                 is_currently_expanded=current_state_expanded)
                message_text = format_events_message(events=[event_to_show], postcode=user_pc_back, user_lat=lat_back,
                                                     user_lon=lon_back, show_details=current_state_expanded)

                if not edit_telegram_message(chat_id, message_id, message_text, reply_markup=keyboard): logger.error(
                    f"Edit failed show_previous msg {message_id}")
            except IndexError:
                logger.error(
                    f"Index err show_previous msg {message_id}. Idx: {new_index}, Size: {len(cached_list)}"); edit_telegram_message(
                    chat_id, message_id, DEFAULT_ERROR_MESSAGE, None)
            except Exception as e:
                logger.error(f"Error show_previous: {e}", exc_info=True); edit_telegram_message(chat_id, message_id,
                                                                                                DEFAULT_ERROR_MESSAGE,
                                                                                                None)
        else:  # Cannot go back or cache missing
            logger.warning(f"Cannot go back further or cache missing msg {message_id}")
            # Optionally edit keyboard to disable back button
            history = message_event_history.get(history_key)
            if history and original_context:
                try:
                    current_event = history[-1];
                    current_state_expanded = message_expansion_state.get(history_key, False)
                    # Determine if forward is possible even if back isn't
                    can_go_forward_at_start = cached_list is not None and 0 < len(cached_list) - 1
                    keyboard = create_event_keyboard(current_event, original_context, can_go_back=False,
                                                     can_go_forward=can_go_forward_at_start,
                                                     is_currently_expanded=current_state_expanded)
                    _telegram_api_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                                                     "reply_markup": json.dumps(
                                                                         keyboard if keyboard else {})})
                except Exception as e:
                    logger.error(f"Error editing keyboard show_previous (at start): {e}")


    # --- Forward Action (New - Uses List Cache) ---
    elif data == "show_next":
        cached_list = message_event_list_cache.get(history_key)
        current_index = message_list_index.get(history_key)

        if cached_list is not None and current_index is not None and current_index < len(cached_list) - 1:
            # Keep original try/except structure style
            try:
                new_index = current_index + 1
                event_to_show = cached_list[new_index] # Get next from CACHED LIST
                message_list_index[history_key] = new_index # Update index state

                # Append this newly viewed event to the separate history deque
                if history_key not in message_event_history: message_event_history[history_key] = deque(maxlen=HISTORY_SIZE)
                message_event_history[history_key].append(event_to_show.copy())
                logger.info(f"Appended history for msg {message_id} via show_next. New len: {len(message_event_history[history_key])}")


                can_go_back = True # Always true if we went forward
                can_go_forward = new_index < len(cached_list) - 1 # Check if not at the new end

                user_pc_fwd, lat_fwd, lon_fwd = get_user_location(chat_id)
                if lat_fwd is not None and lon_fwd is not None:
                    try: # Add distance
                        lat_val = event_to_show.get("latitude"); lon_val = event_to_show.get("longitude")
                        if lat_val is not None and lon_val is not None: ev_lat=float(lat_val); ev_lon=float(lon_val); event_to_show["distance_km"]=haversine_distance(lat_fwd, lon_fwd, ev_lat, ev_lon)
                    except (ValueError, TypeError) as e: logger.warning(f"Failed dist on forward: {e}")

                current_state_expanded = message_expansion_state.get(history_key, False)

                keyboard = create_event_keyboard( event=event_to_show, refresh_callback_data=original_context, can_go_back=can_go_back, can_go_forward=can_go_forward, is_currently_expanded=current_state_expanded)
                message_text = format_events_message( events=[event_to_show], postcode=user_pc_fwd, user_lat=lat_fwd, user_lon=lon_fwd, show_details=current_state_expanded)

                if not edit_telegram_message(chat_id, message_id, message_text, reply_markup=keyboard): logger.error(f"Edit failed for show_next on msg {message_id}")

            except IndexError: logger.error(f"Index error during show_next for msg {message_id}. Index: {new_index}, List size: {len(cached_list)}"); edit_telegram_message(chat_id, message_id, DEFAULT_ERROR_MESSAGE, None)
            except Exception as e: logger.error(f"Error processing show_next: {e}", exc_info=True); edit_telegram_message(chat_id, message_id, DEFAULT_ERROR_MESSAGE, None)
        else:
            logger.warning(f"Cannot go forward further or list cache missing for msg {message_id}")
            # Optionally edit keyboard to disable forward button
            history = message_event_history.get(history_key) # Get current event from history
            if history and original_context:
                 try:
                     current_event = history[-1]; current_state_expanded = message_expansion_state.get(history_key, False)
                     keyboard = create_event_keyboard(current_event, original_context, can_go_back=True, can_go_forward=False, is_currently_expanded=current_state_expanded)
                     _telegram_api_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": json.dumps(keyboard if keyboard else {})})
                 except Exception as e: logger.error(f"Error editing keyboard for show_next (at end): {e}")

    # --- Toggle Actions ---
    elif data in ["toggle_details_show", "toggle_details_hide"]:
        # This logic primarily uses the current event from message_event_history
        # and doesn't need the list cache directly, so it remains largely unchanged.
        # It correctly reads/updates message_expansion_state.
        history = message_event_history.get(history_key)
        # Need original_context to rebuild keyboard correctly
        original_context_toggle = message_context_type.get(history_key)

        # Determine can_go_back/can_go_forward based on list state if available
        cached_list_toggle = message_event_list_cache.get(history_key)
        current_index_toggle = message_list_index.get(history_key)
        can_go_back_toggle = history and len(history) > 1 # Back depends on view history
        can_go_forward_toggle = cached_list_toggle is not None and current_index_toggle is not None and current_index_toggle < len(cached_list_toggle) - 1

        if history and original_context_toggle:
            # Keep original try/except
            try:
                event_to_show = history[-1] # Use the currently viewed event
                show_details_new_state = (data == "toggle_details_show")

                user_pc_toggle, lat_toggle, lon_toggle = get_user_location(chat_id)
                if lat_toggle is not None and lon_toggle is not None and "distance_km" not in event_to_show:
                     try: # Add distance if missing
                         lat_val=event_to_show.get("latitude");lon_val=event_to_show.get("longitude")
                         if lat_val is not None and lon_val is not None: ev_lat=float(lat_val);ev_lon=float(lon_val);event_to_show["distance_km"]=haversine_distance(lat_toggle,lon_toggle,ev_lat,ev_lon)
                     except (ValueError, TypeError) as e: logger.warning(f"Failed dist on toggle: {e}")

                message_text = format_events_message( events=[event_to_show], postcode=user_pc_toggle, user_lat=lat_toggle, user_lon=lon_toggle, show_details=show_details_new_state)
                keyboard = create_event_keyboard( event=event_to_show, refresh_callback_data=original_context_toggle, can_go_back=can_go_back_toggle, can_go_forward=can_go_forward_toggle, is_currently_expanded=show_details_new_state)

                if edit_telegram_message(chat_id, message_id, message_text, reply_markup=keyboard):
                    message_expansion_state[history_key] = show_details_new_state
                    logger.info(f"Set expansion state to {show_details_new_state} for msg {message_id}")
                else: logger.error(f"Edit failed for {data} on msg {message_id}")
            except IndexError: logger.error(f"History empty for toggle on msg {message_id}"); edit_telegram_message(chat_id, message_id, DEFAULT_ERROR_MESSAGE, None)
            except Exception as e: logger.error(f"Error processing {data}: {e}", exc_info=True); edit_telegram_message(chat_id, message_id, DEFAULT_ERROR_MESSAGE, None)
        else: logger.warning(f"History/context not found for {data} on msg {message_id}")

    # --- Fallback ---
    else:
        logger.warning(f"Received unhandled callback data: {data} from chat {chat_id}")

# --- Broadcast Logic ---

def broadcast_newsletter(n_events: int = DEFAULT_BROADCAST_LIMIT) -> None:
    """Send weekly updates to subscribers using updated fetch/format."""
    subscribers: ta.List[ta.Dict[str, ta.Any]] = []
    # Keep original try/except around fetching subscribers
    try:
        resp = supabase.table("telegram_subscribers").select("chat_id").execute()
        subscribers = resp.data if resp and hasattr(resp, 'data') and isinstance(resp.data, list) else []
    except Exception as exc:
        logger.error(f"Error fetching subscribers for broadcast: {exc}", exc_info=True); return

    logger.info(f"Starting broadcast to {len(subscribers)} subscribers.")
    sent_count: int = 0; failed_count: int = 0
    today_date = datetime.now(timezone.utc).date()
    # Define date range for the week ahead
    today_str: str = today_date.strftime("%Y-%m-%d")
    future_str: str = (today_date + timedelta(days=7)).strftime("%Y-%m-%d")

    for sub in subscribers:
        chat_id: ta.Optional[str] = sub.get("chat_id")
        if not chat_id: continue

        # Keep original try/except around processing each subscriber
        try:
            user_pc, lat, lon = get_user_location(chat_id)
            events_to_send: ta.List[ta.Dict[str, ta.Any]] = []
            message_header: str = "🎉 Your Saturday Update!"
            # Update context string to reflect fetch logic
            time_period_str: str = "starting in the next 7 days"
            postcode_for_msg: str = ""

            if user_pc and lat is not None and lon is not None:
                # Calls updated fetch_events
                events_to_send = fetch_events(date_from=today_str, date_to=future_str, user_lat=lat, user_lon=lon, overall_limit=n_events)
                message_header = f"📍 Your Saturday Update near {user_pc.upper()}!"
                postcode_for_msg = user_pc
            elif user_pc:
                 logger.warning(f"Failed geocode in broadcast for stored postcode '{user_pc}' (Chat ID: {chat_id}).")
                 message_header = f"⚠️ Couldn't use postcode {user_pc}. Showing random events."
                 time_period_str = "some random events"
            else:
                message_header = "📍 Set your location with /updatelocation for local events!\n\n🎉 Your Saturday Update!"
                time_period_str = "some random events"

            if not events_to_send: # Fetch random if needed
                # Calls updated fetch_random_events
                events_to_send = fetch_random_events(days_ahead=7, limit=n_events)
                if "Update!" in message_header and "random events" not in message_header:
                     message_header += " Showing random events instead."
                elif "Update!" not in message_header: # If headers were errors
                     message_header += "\nShowing some random events:"

            msg_text: str = ""
            if events_to_send:
                 # Calls updated format_events_message
                 msg_text = format_events_message(
                     events=events_to_send, time_period=time_period_str,
                     postcode=postcode_for_msg, user_lat=lat, user_lon=lon,
                     show_details=False
                 )

            if events_to_send and msg_text:
                full_message: str = f"{message_header}\n\n{msg_text}"
                if send_telegram_message(chat_id, full_message, reply_markup=None):
                    sent_count += 1
                else:
                    logger.error(f"Failed sending broadcast message to chat_id {chat_id}.")
                    failed_count += 1
            elif not events_to_send:
                 logger.info(f"No events found (local or random) for broadcast to chat_id {chat_id}.")
                 failed_count += 1

        except Exception as e:
            logger.error(f"Error processing broadcast for subscriber {chat_id}: {e}", exc_info=True)
            failed_count += 1

        # Keep original rate limit delay
        time.sleep(0.5)

    logger.info(f"Broadcast finished. Sent to {sent_count}, Failed/No Events for {failed_count}/{len(subscribers)} subscribers.")


# --- Main Application Loop ---

def main() -> None:
    """Main bot execution loop."""
    logger.info("Bot started. Polling for messages...")
    offset: ta.Optional[int] = None
    last_broadcast_hour_key: ta.Optional[str] = None # In-memory flag

    while True:
        # Fetch Updates
        updates: ta.List[ta.Dict[str, ta.Any]] = []
        try: updates = get_telegram_updates(offset)
        except Exception as e: logger.error(f"Critical error fetching updates: {e}", exc_info=True); time.sleep(15); continue

        # Process Updates
        for upd in updates:
            try:
                update_id: ta.Optional[int] = upd.get('update_id')
                if update_id is not None: offset = update_id + 1

                callback_query: ta.Optional[ta.Dict[str, ta.Any]] = upd.get('callback_query')
                message: ta.Optional[ta.Dict[str, ta.Any]] = upd.get('message')

                if callback_query:
                    process_callback_query(callback_query)
                elif message:
                    process_message(message)
            except Exception as e:
                 logger.error(f"Error processing update {upd.get('update_id')}: {e}", exc_info=True)
                 if message and (chat_id := message.get('chat', {}).get('id')):
                      try: send_telegram_message(str(chat_id), DEFAULT_ERROR_MESSAGE)
                      except Exception: pass # Ignore failure to notify

        # Trigger Broadcast
        try:
            now_utc: datetime = datetime.utcnow()
            current_hour_key: str = f"{now_utc.date()}-{now_utc.hour}"
            if now_utc.weekday() == 5 and now_utc.hour == 9 and current_hour_key != last_broadcast_hour_key:
                 logger.info(f"Triggering Saturday 9AM UTC broadcast for {current_hour_key}.")
                 broadcast_newsletter()
                 last_broadcast_hour_key = current_hour_key # Mark as triggered
        except Exception as e:
            logger.error(f"Error during broadcast check/trigger: {e}", exc_info=True)

        time.sleep(1)


if __name__ == "__main__":
    main()
