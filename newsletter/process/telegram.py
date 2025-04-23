from collections import deque
import os
import time
import logging
import datetime
import json
import math
import random
import urllib.parse
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


supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Structure: {(chat_id, message_id): deque([event_dict, ...], maxlen=HISTORY_SIZE)}
# Stores the actual event data shown in a message to allow going back.
message_event_history: ta.Dict[ta.Tuple[str, int], deque[ta.Dict[str, ta.Any]]] = {}

# Structure: {(chat_id, message_id): "load_random" | "load_local" | ...}
# Stores the original context/command type that generated the message for refresh consistency.
message_context_type: ta.Dict[ta.Tuple[str, int], str] = {}

# In-memory state (consider alternatives like Redis/DB for multi-instance bots)
awaiting_location_update: ta.Dict[str, bool] = {}

# --- Constants ---
HISTORY_SIZE: int = 5 #
DEFAULT_EVENT_FETCH_LIMIT: int = 10 # Fetch more for refresh randomness
DEFAULT_BROADCAST_LIMIT: int = 5
DEFAULT_RANDOM_DAYS_AHEAD: int = 7
TELEGRAM_MAX_MSG_LENGTH: int = 4000

LOCATION_PROMPT_MESSAGE: str = "I need your valid London location first! Use /updatelocation or send me your postcode."
GEOCODE_ERROR_MESSAGE: str = "Sorry, couldn't find coordinates for your location '{postcode}'. Try updating it via /updatelocation."
NO_EVENTS_MESSAGE: str = "Couldn't find any events {context} near {postcode}."
DEFAULT_ERROR_MESSAGE: str = "Sorry, something went wrong processing your request."

help_text = (
"Welcome to <b>Niche London</b> 👋\n\n"
"We find local events happening across London!\n\n"
"My commands:\n"
"/local - Your closest events 🧭\n"
"/best - Our top picks  🏆\n"
"/today - What's on today? 🔜\n"
"/tomorrow - What's on tomorrow? 👣\n"
"/random - I'm feeling lucky 🍀\n"
"/subscribe - Weekly roundup 📬\n"
"/unsubscribe - Stop already! 🫗\n"
"/updatelocation - Update map pinhead 📍\n"
"Or, send a London postcode (e.g., <i>E8 3PN</i>)!"
)


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
    params: ta.Dict[str, int] = {"timeout": 30} # Long polling timeout
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
            time.sleep(0.2)

    # Return the response data of the last part IF the overall operation seems successful
    # Modify the condition based on desired behavior if parts fail.
    # Here, we return last part data even if prior parts failed, as long as last part succeeded.
    # If the *last* part failed, last_part_response_data will be None.
    # If overall_success is required, use: return last_part_response_data if overall_success else None
    return last_part_response_data if overall_success else None

def format_event_for_forwarding(event: ta.Dict[str, ta.Any]) -> str:
    """Creates a nicer plain text summary of an event suitable for forwarding."""
    lines = []

    # --- Core Event Info ---
    # Use pretty names with fallbacks
    name = (event.get("pretty_event_name") or event.get("title") or "Event").strip()
    venue = (event.get("pretty_venue_name") or "Venue").strip() # Assume pretty_venue_name exists
    date = (event.get("pretty_date") or event.get("event_date") or "Date TBC").strip()

    # Use markdown-like bold for name (might render after sending)
    lines.append(f"*{name}*")
    lines.append(f"📍 {venue}")
    lines.append(f"📅 {date}")
    lines.append("") # Add a blank line for separation

    # --- Optional Details ---
    # Include summary (pretty_description) if it exists
    summary = (event.get("pretty_description") or "").strip()
    if summary:
        # Truncate summary for forwarding context
        max_fwd_summary = 150 # Keep it relatively brief
        if len(summary) > max_fwd_summary:
             summary = summary[:max_fwd_summary].strip() + "..."
        lines.append(f"📝 {summary}")
        lines.append("") # Add a blank line

    # Include vibes if they exist
    vibes = (event.get("vibes") or "").strip()
    if vibes:
        lines.append(f"✨ Vibes: {vibes}")
        # lines.append("") # Optional blank line after vibes

    # Include venue URL if it exists and is valid
    url = (event.get("venue_url") or "").strip()
    if url and (url.startswith("http://") or url.startswith("https://")):
        lines.append(f"🔗 Link: {url}")

    # Join lines, ensuring no leading/trailing whitespace on the final string
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
            "created_date": datetime.datetime.utcnow().isoformat() # Use ISO format for timestamp
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
        #         "subscribed_date": datetime.datetime.utcnow().isoformat()
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
    date_from: ta.Optional[str] = None,
    date_to: ta.Optional[str] = None,
    user_lat: ta.Optional[float] = None,
    user_lon: ta.Optional[float] = None,
    max_distance_km: float = 15.0,
    limit_per_venue: int = 1,
    overall_limit: int = 5
) -> ta.List[ta.Dict[str, ta.Any]]:
    """Fetch events from Supabase, applying filters and limits."""
    data: ta.List[ta.Dict[str, ta.Any]] = [] # Initialize empty list
    try:
        query = supabase.table("events_enriched").select("*")

        # Date filtering
        if date_from and date_to:
            query = query.gte("event_date", date_from).lt("event_date", date_to) if date_from != date_to else query.eq("event_date", date_from)
        elif date_from:
            query = query.gte("event_date", date_from)
        elif date_to:
            query = query.lt("event_date", date_to)
        elif not date_from and not date_to: # Default to future
            query = query.gte("event_date", datetime.datetime.utcnow().strftime("%Y-%m-%d"))

        resp = query.execute()
        data = resp.data if resp and hasattr(resp, 'data') else [] # Ensure data is a list
    except Exception as exc:
        logger.error(f"Error fetching events from Supabase: {exc}", exc_info=True)
        return [] # Return empty on error

    # Location filtering
    if user_lat is not None and user_lon is not None:
        events_with_distance: ta.List[ta.Dict[str, ta.Any]] = []
        for row in data:
            try:
                # Ensure lat/lon are treated as floats, handle None/NaN
                ev_lat: float = float(row.get("latitude")) if row.get("latitude") is not None else math.nan
                ev_lon: float = float(row.get("longitude")) if row.get("longitude") is not None else math.nan
                if not math.isnan(ev_lat) and not math.isnan(ev_lon):
                    dist: float = haversine_distance(user_lat, user_lon, ev_lat, ev_lon)
                    if dist <= max_distance_km:
                        row["distance_km"] = dist
                        events_with_distance.append(row)
            except (ValueError, TypeError, AttributeError): # More specific error catching
                 logger.warning(f"Could not parse lat/lon or calculate distance for event {row.get('event_id')}")
        data = events_with_distance # Update data with filtered list

    # Apply limit per venue
    by_venue: ta.Dict[str, int] = {}
    filtered_by_venue: ta.List[ta.Dict[str, ta.Any]] = []
    for r in data:
        v_id: ta.Optional[str] = r.get("venue_id") # venue_id could be None
        if v_id: # Only process if venue_id exists
            if v_id not in by_venue: by_venue[v_id] = 0
            if by_venue[v_id] < limit_per_venue:
                filtered_by_venue.append(r)
                by_venue[v_id] += 1
    data = filtered_by_venue # Update data again

    # Sort and limit
    sort_key: ta.Callable[[ta.Dict[str, ta.Any]], ta.Any]
    if user_lat is not None and user_lon is not None:
        sort_key = lambda x: x.get("distance_km", float('inf')) # Sort by distance, handle missing safely
    else:
        sort_key = lambda x: (x.get("event_date", ""), x.get("pretty_event_name", "")) # Sort by date then name

    sorted_events: ta.List[ta.Dict[str, ta.Any]] = sorted(data, key=sort_key)

    return sorted_events[:overall_limit]


def fetch_random_events(days_ahead: int = 7, limit: int = 1) -> ta.List[ta.Dict[str, ta.Any]]:
    """Fetch random events."""
    try:
        today_str: str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        future_str: str = (datetime.datetime.utcnow() + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        potential_limit: int = max(limit * 5, 20)
        resp = supabase.table("events_enriched").select("*").gte("event_date", today_str).lt("event_date", future_str).limit(potential_limit).execute()
        data: ta.List[ta.Dict[str, ta.Any]] = resp.data if resp and hasattr(resp, 'data') else []
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
    show_details: bool = False # <<<<< ADDED PARAMETER, default is False (hidden)
) -> str:
    """
    Format a list of events. Includes distance/direction if available.
    Can optionally show/hide the pretty_description and vibes lines.
    """
    if not events: return ""

    lines: ta.List[str] = []
    if len(events) > 1:
        header_parts: ta.List[str] = ["Here are events"]
        if time_period: header_parts.append(time_period)
        lines.append(" ".join(header_parts) + ":\n")

    for ev in events:
        event_lines: ta.List[str] = []
        # Safely get event details
        name: str = (ev.get("pretty_event_name") or "Event").strip()
        venue: str = (ev.get("pretty_venue_name") or "Venue").strip()
        date: str = (ev.get("pretty_date") or ev.get("event_date") or "Date TBC").strip()
        url: str = (ev.get("venue_url") or "").strip()
        vibes: str = (ev.get("vibes") or "").strip()
        summary: str = (ev.get("pretty_description") or "").strip() # Use "" as fallback instead of "No description"

        # Format venue with link
        venue_html: str = f"<i>{venue}</i>"
        if url and (url.startswith("http://") or url.startswith("https://")):
            try:
                encoded_url: str = urllib.parse.quote(url, safe=':/%#?=@')
                venue_html = f'<a href="{encoded_url}">{venue}</a>'
            except Exception as e: logger.warning(f"Failed to encode URL '{url}': {e}")

        # --- Build Message Lines ---
        event_lines.append(f"<b>{name}</b>")
        event_lines.append(f"📍 {venue_html}")

        # <<< MODIFIED: Conditionally add summary (pretty_description) and vibes >>>
        if show_details:
            if summary: # Only add if summary is not empty
                 # Truncate here if desired, or assume it's already short
                 max_summary_len: int = 250
                 display_summary = summary
                 if len(display_summary) > max_summary_len: display_summary = display_summary[:max_summary_len] + "..."
                 event_lines.append(f"👉 {display_summary}")

            if vibes: # Only add if vibes is not empty
                event_lines.append(f"✨ {vibes}")
        # <<< END MODIFICATION >>>

        event_lines.append(f"📅 {date}") # Date always shown

        # Distance and Direction (logic remains the same)
        if "distance_km" in ev and postcode and user_lat is not None and user_lon is not None:
            try:
                dist_km: float = float(ev["distance_km"])
                arrow: str = ""
                ev_lat: float = float(ev.get("latitude")) if ev.get("latitude") is not None else math.nan
                ev_lon: float = float(ev.get("longitude")) if ev.get("longitude") is not None else math.nan
                if not math.isnan(ev_lat) and not math.isnan(ev_lon):
                    bearing: float = calculate_bearing(user_lat, user_lon, ev_lat, ev_lon)
                    arrow = bearing_to_arrow(bearing) + " "
                dist_str: str
                if dist_km < 0.1: dist_str = f"{round(dist_km * 1000)}m"
                elif dist_km < 10: dist_str = f"{dist_km:.1f}km"
                else: dist_str = f"{dist_km:.0f}km"
                event_lines.append(f"🧭 <i>{dist_str} {arrow}from {postcode.upper()}</i>")
            except (ValueError, TypeError, KeyError) as e:
                 logger.warning(f"Error processing distance/bearing for event {ev.get('event_id')}: {e}", exc_info=False)

        lines.append("\n".join(event_lines))

    return "\n\n".join(lines)


def create_event_keyboard(
    event: ta.Dict[str, ta.Any],
    refresh_callback_data: str,
    can_go_back: bool,
    is_currently_expanded: bool # <<<<< ADDED PARAMETER BACK
    ) -> ta.Optional[ta.Dict[str, ta.Any]]:
    """
    Creates the inline keyboard with relevant buttons based on context.
    Button order: Back | Toggle | Refresh | Map | Forward
    """
    button_row: ta.List[ta.Dict[str, str]] = []

    # Check if there are details (summary or vibes) to toggle
    summary = (event.get("pretty_description") or "").strip()
    vibes = (event.get("vibes") or "").strip()
    has_details_to_toggle = bool(summary or vibes) # Toggle if either exists

    # --- Define and Add Buttons in Order ---

    # 1. Back Button (Conditional)
    if can_go_back:
        button_row.append({"text": "⏪", "callback_data": "show_previous"})

    # 2. Toggle Button (Show More/Less) - Conditional
    if has_details_to_toggle: # Only show if there are details to toggle
        if is_currently_expanded:
            # Currently expanded -> show "Less" button '➖'
            button_row.append({"text": "➖", "callback_data": "toggle_details_hide"})
        else:
            # Currently collapsed -> show "More" button '➕'
            button_row.append({"text": "➕", "callback_data": "toggle_details_show"})

    # 3. Refresh Button
    button_row.append({"text": "🔄", "callback_data": refresh_callback_data})

    # 4. Map Button (Conditional)
    venue_name: ta.Optional[str] = event.get("pretty_venue_name")
    venue_postcode: ta.Optional[str] = event.get("postcode")
    if venue_name and venue_postcode:
        try:
            search_query: str = f"{venue_name}, {venue_postcode}"
            maps_url: str = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(search_query)}" # Use HTTPS
            button_row.append({"text": "📍", "url": maps_url})
        except Exception as e: logger.error(f"Error creating map link: {e}")

    # 5. Forward Button
    try:
        forward_text: str = format_event_for_forwarding(event)
        button_row.append({"text": "📤", "switch_inline_query": forward_text or "Check out this event!"})
    except Exception as e:
        logger.error(f"Error formatting event for forwarding: {e}")

    # --- Construct Keyboard ---
    if button_row:
        return {"inline_keyboard": [button_row]}
    else:
        return None


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
    """Handles commands that fetch and display a single event with refresh."""
    # Map command to callback data, display context, and location requirement
    command_config = {
        "/local": {"cb": "load_local", "ctx": "nearby", "loc": True, "days": 7},
        "/today": {"cb": "load_today", "ctx": "today", "loc": True, "days": 0},
        "/tomorrow": {"cb": "load_tomorrow", "ctx": "tomorrow", "loc": True, "days": 1},
        "/weekend": {"cb": "load_weekend", "ctx": "this weekend", "loc": True}, # Weekend specific
        "/random": {"cb": "load_random", "ctx": "a random event", "loc": False},
        "/best": {"cb": "load_best", "ctx": "a top pick", "loc": False},
    }

    config = command_config.get(command)
    if not config:
        logger.error(f"Invalid command passed to handle_single_event_command: {command}")
        return # Should not happen if called via process_message map

    callback_data: str = config["cb"]
    time_period_context: str = config["ctx"]
    is_location_based: bool = config["loc"]

    user_pc: ta.Optional[str] = None
    lat: ta.Optional[float] = None
    lon: ta.Optional[float] = None
    fetch_params: ta.Dict[str, ta.Any] = {}
    events: ta.List[ta.Dict[str, ta.Any]] = []
    no_event_context: str = ""

    # --- Get Location if Required ---
    if is_location_based:
        user_pc, lat, lon = get_user_location(chat_id)
        if not user_pc: send_telegram_message(chat_id, LOCATION_PROMPT_MESSAGE); return
        if lat is None or lon is None: send_telegram_message(chat_id, GEOCODE_ERROR_MESSAGE.format(postcode=user_pc)); return
        fetch_params.update({"user_lat": lat, "user_lon": lon})
        no_event_context = f"near {user_pc.upper()}"

    # --- Calculate Date Range and Fetch Events ---
    try:
        today_dt: datetime.datetime = datetime.datetime.utcnow()
        today_date: datetime.date = today_dt.date()

        if command == "/weekend":
            # Calculate upcoming Saturday and Monday (for range end)
            today_weekday = today_date.weekday() # Monday is 0, Sunday is 6
            days_until_saturday = (5 - today_weekday + 7) % 7
            saturday_date = today_date + datetime.timedelta(days=days_until_saturday)
            monday_date = saturday_date + datetime.timedelta(days=2) # End date is exclusive

            fetch_params["date_from"] = saturday_date.strftime("%Y-%m-%d")
            fetch_params["date_to"] = monday_date.strftime("%Y-%m-%d")
            no_event_context = f"this weekend {no_event_context}".strip()
            events = fetch_events(overall_limit=1, **fetch_params)

        elif command in ["/local", "/today", "/tomorrow"]:
            days_offset = config.get("days", 0)
            start_date = today_date + datetime.timedelta(days=days_offset)
            if command == "/local": # Special case for 7-day range
                end_date = start_date + datetime.timedelta(days=7)
                no_event_context = f"in the next 7 days {no_event_context}".strip()
            else: # Today or Tomorrow
                end_date = start_date + datetime.timedelta(days=1)
                no_event_context = f"{time_period_context} {no_event_context}".strip()

            fetch_params["date_from"] = start_date.strftime("%Y-%m-%d")
            fetch_params["date_to"] = end_date.strftime("%Y-%m-%d")
            events = fetch_events(overall_limit=1, **fetch_params)

        elif command in ["/random", "/best"]:
            events = fetch_random_events(days_ahead=DEFAULT_RANDOM_DAYS_AHEAD, limit=1)
            no_event_context = "matching that criteria" # Generic

        # --- Process fetched events ---
        event: ta.Optional[ta.Dict[str, ta.Any]] = events[0] if events else None

        if not event:
            send_telegram_message(chat_id, NO_EVENTS_MESSAGE.format(context=no_event_context, postcode=user_pc.upper() if user_pc else "your area"))
            return

        # Add distance if user location known
        user_pc_dist, lat_dist, lon_dist = get_user_location(chat_id)
        if lat_dist is not None and lon_dist is not None:
             try:
                 ev_lat = float(event.get("latitude", math.nan)); ev_lon = float(event.get("longitude", math.nan))
                 if not math.isnan(ev_lat) and not math.isnan(ev_lon): event["distance_km"] = haversine_distance(lat_dist, lon_dist, ev_lat, ev_lon)
             except: pass

    except Exception as e:
        logger.error(f"Error fetching event for command {command}: {e}", exc_info=True)
        send_telegram_message(chat_id, DEFAULT_ERROR_MESSAGE); return

    # --- Send the event message ---
    try:
        keyboard = create_event_keyboard(event, callback_data, can_go_back=False, is_currently_expanded=False)
        message_text = format_events_message(
            events=[event], time_period=time_period_context,
            postcode=user_pc, user_lat=lat, user_lon=lon, show_details=False
        )
        # Use helper to get message_id for history
        sent_message_api_response = _telegram_api_request("sendMessage", {
             "chat_id": str(chat_id), "text": message_text, "parse_mode": "HTML",
             "disable_web_page_preview": True, "reply_markup": json.dumps(keyboard if keyboard else {})
         })
        # Initialize History
        if sent_message_api_response and isinstance(sent_message_api_response.get("result"), dict) and (msg_id := sent_message_api_response["result"].get('message_id')):
            history_key = (str(chat_id), msg_id)
            message_event_history[history_key] = deque([event.copy()], maxlen=HISTORY_SIZE)
            message_context_type[history_key] = callback_data
            logger.info(f"Initialized history for msg {msg_id} in chat {chat_id} with event {event.get('event_id')}")
        else: logger.error(f"Failed to get message_id after sending {command} command to {chat_id}. API Response: {sent_message_api_response}")
    except Exception as e:
        logger.error(f"Error formatting/sending event for command {command}: {e}", exc_info=True)
        send_telegram_message(chat_id, DEFAULT_ERROR_MESSAGE)


def handle_refresh_callback(chat_id: str, message_id: int, callback_data: str) -> None:
    """Handles all refresh callback queries (load_...). Updates history."""
    # --- Initial Setup ---
    fetch_params: ta.Dict[str, ta.Any] = {}
    user_pc: ta.Optional[str] = None; lat: ta.Optional[float] = None; lon: ta.Optional[float] = None
    fetch_limit: int = DEFAULT_EVENT_FETCH_LIMIT
    # Determine command type from callback data
    is_location_based: bool = callback_data in ["load_local", "load_today", "load_tomorrow", "load_weekend"] # ADDED load_weekend
    is_random: bool = callback_data == "load_random"; is_best: bool = callback_data == "load_best"
    time_period_context: str = ""; no_event_context: str = ""
    event_to_show: ta.Optional[ta.Dict[str, ta.Any]] = None; fetched_events: ta.List[ta.Dict[str, ta.Any]] = []

    # --- Get Location if Needed ---
    if is_location_based:
        user_pc, lat, lon = get_user_location(chat_id)
        if not user_pc: edit_telegram_message(chat_id, message_id, LOCATION_PROMPT_MESSAGE, None); return
        if lat is None or lon is None: edit_telegram_message(chat_id, message_id, GEOCODE_ERROR_MESSAGE.format(postcode=user_pc), None); return
        fetch_params.update({"user_lat": lat, "user_lon": lon}); no_event_context = f"near {user_pc.upper()}"

    # --- Determine Fetch Dates/Context ---
    today_dt: datetime.datetime = datetime.datetime.utcnow()
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
    """Send each event as an individual message, passing location info for formatting."""
    if not events:
         logger.info(f"No events provided to send_event_messages for chat {chat_id}.")
         # Callers should handle the "no events found" message themselves
         return

    for event in events:
        # Call format_events_message to format one event at a time
        message = format_events_message(
            events=[event],
            postcode=postcode,
            user_lat=user_lat,
            user_lon=user_lon,
            show_full_description=False # Ensure default is collapsed view for multi-send
        )
        if message:
            # Send message WITHOUT reply_markup (no buttons)
            send_telegram_message(chat_id, message)
            time.sleep(0.2) # Keep delay between messages
        else:
            logger.warning(f"Empty message generated by format_events_message for event: {event.get('event_id', 'N/A')}")


# --- Main Message Processing Logic ---

def process_message(msg: ta.Dict[str, ta.Any]) -> None:
    """Handles incoming text messages and commands."""
    # ... (initial setup, chat info, user info, text processing) ...
    chat_info: ta.Dict[str, ta.Any] = msg.get('chat', {})
    chat_id: str = str(chat_info.get('id', ''))
    chat_type: str = chat_info.get('type', '')
    user_info: ta.Dict[str, ta.Any] = msg.get('from', {})
    user_id: str = str(user_info.get('id', ''))

    if not chat_id or user_info.get('is_bot') or msg.get('edit_date'): return
    text_raw: str = (msg.get('text') or '').strip()
    text_lower: str = text_raw.lower()
    logger.info(f"Processing message from chat {chat_id} (user: {user_id}): '{text_raw}'")
    upsert_chat_info(chat_id, chat_type, user_info)
    help_text = (
        "Welcome to <b>Niche London</b> 👋\n\n"
        "We find local events happening across London!\n\n"
        "My commands:\n"
        "/local - Your closest events 🧭\n"
        "/best - Our top picks  🏆\n"
        "/today - What's on today? 🔜\n"
        "/tomorrow - What's on tomorrow? 👣\n"
        "/weekend - What's on this weekend? 🎉\n"
        "/random - I'm feeling lucky 🍀\n"
        "/updatelocation - Update map pinhead 📍\n"
        "/help - Show this message\n\n"
        "Or, send a London postcode (e.g., <i>E8 3PN</i>)!"
    )
    # --- Command Routing ---
    if text_lower in ["/start", "/help", "help", "hello", "hi", "?"]: # Simple Commands
        awaiting_location_update[chat_id] = False
        send_telegram_message(chat_id, help_text); return
    if text_lower == "/updatelocation":
        awaiting_location_update[chat_id] = True
        send_telegram_message(chat_id, "OK. Please send me your London postcode (e.g., SW1A 0AA)."); return
    elif text_lower == "/subscribe":
        if chat_type == 'private':
            awaiting_location_update[chat_id] = False
            logger.info(f"Processing /subscribe for chat {chat_id}")
            try:
                # Explicitly add user to subscribers table on command
                supabase.table("telegram_subscribers").upsert({
                    "chat_id": str(chat_id),
                    "subscribed_date": datetime.datetime.utcnow().isoformat()
                }, on_conflict="chat_id").execute()
                # Send confirmation ONLY on success
                send_telegram_message(chat_id, "✅ You've subscribed to the weekly roundup!")
            except Exception as e:
                logger.error(f"Error subscribing chat {chat_id}: {e}", exc_info=True)
                send_telegram_message(chat_id, "⚠️ Sorry, there was an error trying to subscribe you.")
        else:
            # Ignore /subscribe command in group chats
            send_telegram_message(chat_id, "Subscription commands only work in a private chat with me.")
        return
    elif text_lower == "/unsubscribe":
        if chat_type == 'private': # Only works in private chat
            awaiting_location_update[chat_id] = False
            # Calls the helper function to perform the action
            if unsubscribe_user(chat_id):
                send_telegram_message(chat_id, "You've been unsubscribed from the weekly roundup.") # Success feedback
            else:
                send_telegram_message(chat_id, "Sorry, there was an error trying to unsubscribe.") # Error feedback
        else:
            send_telegram_message(chat_id, "Subscription commands only work in a private chat with me.")
        return # Stop further processing

    # --- Single Event Commands ---
    single_event_command_map = {
        "/local": ("load_local", "nearby", True),
        "/today": ("load_today", "today", True),
        "/tomorrow": ("load_tomorrow", "tomorrow", True),
        "/weekend": ("load_weekend", "this weekend", True),
        "/random": ("load_random", "a random event", False),
        "/best": ("load_best", "a top pick", False),
    }
    if text_lower in single_event_command_map:
        awaiting_location_update[chat_id] = False
        callback_data, time_period_context, is_location_based = single_event_command_map[text_lower]
        user_pc: ta.Optional[str] = None; lat: ta.Optional[float] = None; lon: ta.Optional[float] = None
        event: ta.Optional[ta.Dict[str, ta.Any]] = None; events: ta.List[ta.Dict[str, ta.Any]] = []
        no_event_context: str = ""
        # Get location if needed
        if is_location_based:
            user_pc, lat, lon = get_user_location(chat_id)
            if not user_pc: send_telegram_message(chat_id, LOCATION_PROMPT_MESSAGE); return
            if lat is None or lon is None: send_telegram_message(chat_id, GEOCODE_ERROR_MESSAGE.format(postcode=user_pc)); return
            no_event_context = f"near {user_pc.upper()}"
        # Fetch the event
        try:
            # ... (fetch logic based on text_lower remains the same) ...
            if text_lower == "/local":
                 fetch_params = {"date_from": datetime.datetime.utcnow().strftime("%Y-%m-%d"), "date_to": (datetime.datetime.utcnow() + datetime.timedelta(days=7)).strftime("%Y-%m-%d"), "user_lat": lat, "user_lon": lon}
                 no_event_context = f"in the next 7 days {no_event_context}".strip()
                 events = fetch_events(overall_limit=1, **fetch_params)
            elif text_lower == "/today":
                 today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
                 fetch_params = {"date_from": today_str, "date_to": today_str, "user_lat": lat, "user_lon": lon}
                 no_event_context = f"today {no_event_context}".strip()
                 events = fetch_events(overall_limit=1, **fetch_params)
            elif text_lower == "/tomorrow":
                 tomorrow_str = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                 fetch_params = {"date_from": tomorrow_str, "date_to": tomorrow_str, "user_lat": lat, "user_lon": lon}
                 no_event_context = f"tomorrow {no_event_context}".strip()
                 events = fetch_events(overall_limit=1, **fetch_params)
            elif text_lower == "/random" or text_lower == "/best":
                 events = fetch_random_events(days_ahead=DEFAULT_RANDOM_DAYS_AHEAD, limit=1)
                 no_event_context = "matching that criteria"
            # Check results and add distance
            if events:
                event = events[0]
                user_pc_dist, lat_dist, lon_dist = get_user_location(chat_id)
                if lat_dist is not None and lon_dist is not None:
                     try: # Add distance if possible
                         ev_lat = float(event.get("latitude", math.nan)); ev_lon = float(event.get("longitude", math.nan))
                         if not math.isnan(ev_lat) and not math.isnan(ev_lon): event["distance_km"] = haversine_distance(lat_dist, lon_dist, ev_lat, ev_lon)
                     except: pass
            else: send_telegram_message(chat_id, NO_EVENTS_MESSAGE.format(context=no_event_context, postcode=user_pc.upper() if user_pc else "your area")); return
        except Exception as e: logger.error(f"Error fetching event for {text_lower}: {e}", exc_info=True); send_telegram_message(chat_id, DEFAULT_ERROR_MESSAGE); return

        # Send the event message
        if event:
            try:
                # ***** MODIFIED Calls *****
                # Initial state is always collapsed, cannot go back
                keyboard = create_event_keyboard(
                    event=event,
                    refresh_callback_data=callback_data,
                    can_go_back=False,
                    is_currently_expanded=False # <<< Pass False
                )
                # Initial format is collapsed
                message_text = format_events_message(
                    events=[event],
                    time_period=time_period_context,
                    postcode=user_pc, user_lat=lat, user_lon=lon,
                    show_details=False # <<< Pass False
                )
                # Use _telegram_api_request to get message data for history
                sent_message_api_response = _telegram_api_request("sendMessage", {
                     "chat_id": str(chat_id), "text": message_text, "parse_mode": "HTML",
                     "disable_web_page_preview": True, "reply_markup": json.dumps(keyboard if keyboard else {})
                 })
                # Initialize History if message sent successfully
                if sent_message_api_response and isinstance(sent_message_api_response.get("result"), dict) and (msg_id := sent_message_api_response["result"].get('message_id')):
                    history_key = (str(chat_id), msg_id)
                    message_event_history[history_key] = deque([event.copy()], maxlen=HISTORY_SIZE) # Store copy
                    message_context_type[history_key] = callback_data
                    logger.info(f"Initialized history for msg {msg_id} in chat {chat_id} with event {event.get('event_id')}")
                else: logger.error(f"Failed to get message_id after sending {text_lower} command to {chat_id}. API Response: {sent_message_api_response}")
            except Exception as e: logger.error(f"Error formatting/sending event for {text_lower}: {e}", exc_info=True); send_telegram_message(chat_id, DEFAULT_ERROR_MESSAGE)
        return # End processing for single event commands

    # --- Postcode Handling ---
    elif is_valid_london_postcode(text_raw.upper()):
        # ... (postcode handling logic remains the same) ...
        postcode_norm: str = text_raw.upper()
        if awaiting_location_update.get(chat_id, False):
            lat_check, lon_check = geocode_postcode_to_latlon(postcode_norm)
            if lat_check is not None and lon_check is not None:
                if set_user_postcode(chat_id, postcode_norm): send_telegram_message(chat_id, f"✅ Location updated to {postcode_norm}!")
                else: send_telegram_message(chat_id, "⚠️ There was an error saving your postcode.")
            else: send_telegram_message(chat_id, f"⚠️ Couldn't find coordinates for {postcode_norm}. Please try a different London postcode.")
            awaiting_location_update[chat_id] = False
        else:
            lat_pc, lon_pc = geocode_postcode_to_latlon(postcode_norm)
            if not lat_pc or not lon_pc: send_telegram_message(chat_id, f"Sorry, I couldn’t find coordinates for {postcode_norm}."); return
            send_telegram_message(chat_id, f"OK, looking for events near {postcode_norm}...")
            today_dt_pc: datetime.datetime = datetime.datetime.utcnow()
            events_pc: ta.List[ta.Dict[str, ta.Any]] = fetch_events(
                date_from=today_dt_pc.strftime("%Y-%m-%d"),
                date_to=(today_dt_pc + datetime.timedelta(days=7)).strftime("%Y-%m-%d"),
                user_lat=lat_pc, user_lon=lon_pc, overall_limit=5
            )
            if events_pc: send_event_messages( chat_id=chat_id, events=events_pc, postcode=postcode_norm, user_lat=lat_pc, user_lon=lon_pc )
            else: send_telegram_message(chat_id, f"Couldn't find any events near {postcode_norm} in the next 7 days.")
        return # End postcode processing

    # --- Fallback ---
    else:
        if not awaiting_location_update.get(chat_id, False):
             send_telegram_message(chat_id, "Sorry, I didn't understand that. Try /help to see available commands.")


def process_callback_query(callback_query: ta.Dict[str, ta.Any]) -> None:
    """Handles incoming callback queries."""
    query_id: ta.Optional[str] = callback_query.get('id')
    message: ta.Optional[ta.Dict[str, ta.Any]] = callback_query.get('message')
    data: ta.Optional[str] = callback_query.get('data')

    if not query_id or not message or not data:
        logger.warning("Received incomplete callback query.")
        if query_id: answer_callback_query(query_id)
        return

    chat_id: str = str(message.get('chat', {}).get('id', ''))
    message_id: ta.Optional[int] = message.get('message_id')

    answer_callback_query(query_id) # Acknowledge first

    if not chat_id or not message_id:
        logger.error(f"Could not get chat_id/message_id from callback {query_id}"); return

    history_key = (chat_id, message_id)

    # --- Route Callback Data ---

    # --- Refresh Actions ---
    if data.startswith("load_"):
        try:
            # ***** Refactored refresh logic is now INLINE for clarity *****
            # --- Initial Setup for Refresh ---
            fetch_params: ta.Dict[str, ta.Any] = {}
            user_pc: ta.Optional[str] = None; lat: ta.Optional[float] = None; lon: ta.Optional[float] = None
            fetch_limit: int = DEFAULT_EVENT_FETCH_LIMIT
            is_location_based: bool = data in ["load_local", "load_today", "load_tomorrow"]
            is_random: bool = data == "load_random"; is_best: bool = data == "load_best"
            time_period_context: str = ""; no_event_context: str = ""
            event_to_show: ta.Optional[ta.Dict[str, ta.Any]] = None; fetched_events: ta.List[ta.Dict[str, ta.Any]] = []

            # --- Get Location if Needed ---
            if is_location_based:
                user_pc, lat, lon = get_user_location(chat_id)
                if not user_pc: edit_telegram_message(chat_id, message_id, LOCATION_PROMPT_MESSAGE, None); return
                if lat is None or lon is None: edit_telegram_message(chat_id, message_id, GEOCODE_ERROR_MESSAGE.format(postcode=user_pc), None); return
                fetch_params.update({"user_lat": lat, "user_lon": lon}); no_event_context = f"near {user_pc.upper()}"

            # --- Determine Fetch Dates/Context ---
            today_dt: datetime.datetime = datetime.datetime.utcnow(); today_str: str = today_dt.strftime("%Y-%m-%d")
            if data == "load_local":
                fetch_params["date_from"] = today_str; fetch_params["date_to"] = (today_dt + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
                time_period_context = "nearby"; no_event_context = f"in the next 7 days {no_event_context}".strip()
            elif data == "load_today":
                fetch_params["date_from"] = today_str; fetch_params["date_to"] = today_str
                time_period_context = "today"; no_event_context = f"today {no_event_context}".strip()
            elif data == "load_tomorrow":
                tomorrow_str = (today_dt + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                fetch_params["date_from"] = tomorrow_str; fetch_params["date_to"] = tomorrow_str
                time_period_context = "tomorrow"; no_event_context = f"tomorrow {no_event_context}".strip()

            # --- Fetch event(s) ---
            if is_random or is_best:
                fetched_events = fetch_random_events(days_ahead=DEFAULT_RANDOM_DAYS_AHEAD, limit=fetch_limit) # Fetch more for random choice
                time_period_context = "a random event" if is_random else "a top pick"; no_event_context = "randomly" if is_random else "as a top pick"
            elif is_location_based: fetched_events = fetch_events(overall_limit=fetch_limit, **fetch_params)
            else: logger.error(f"Unhandled callback type in refresh handler: {data}"); return

            # --- Select Event to Show (Try not to repeat) ---
            history = message_event_history.get(history_key)
            last_event_id = history[-1].get('event_id') if history else None
            if fetched_events:
                 if len(fetched_events) > 1 and last_event_id:
                     different_events = [e for e in fetched_events if e.get('event_id') != last_event_id]
                     event_to_show = random.choice(different_events) if different_events else fetched_events[0]
                 elif fetched_events: event_to_show = fetched_events[0]
            logger.info(f"Refresh selected event {event_to_show.get('event_id') if event_to_show else 'None'}")

            # --- Update message or show 'no events' ---
            if event_to_show:
                user_pc_refresh, lat_refresh, lon_refresh = (user_pc, lat, lon) if is_location_based else get_user_location(chat_id)
                if lat_refresh is not None and lon_refresh is not None: # Add distance
                    try:
                        ev_lat = float(event_to_show.get("latitude", math.nan)); ev_lon = float(event_to_show.get("longitude", math.nan))
                        if not math.isnan(ev_lat) and not math.isnan(ev_lon): event_to_show["distance_km"] = haversine_distance(lat_refresh, lon_refresh, ev_lat, ev_lon)
                    except: pass
                # Update History
                if history_key not in message_event_history: message_event_history[history_key] = deque(maxlen=HISTORY_SIZE)
                message_event_history[history_key].append(event_to_show.copy())
                if history_key not in message_context_type: message_context_type[history_key] = data
                current_history_len = len(message_event_history[history_key])
                logger.info(f"Appended history for msg {message_id}. New len: {current_history_len}")
                # Format and Edit
                can_go_back: bool = current_history_len > 1
                # Call keyboard creator with expanded=False (refresh resets view)
                keyboard: ta.Optional[ta.Dict[str, ta.Any]] = create_event_keyboard(
                    event=event_to_show, refresh_callback_data=data,
                    can_go_back=can_go_back, is_currently_expanded=False # <<< Pass False
                )
                # Call formatter with expanded=False (refresh resets view)
                message_text: str = format_events_message(
                    events=[event_to_show], postcode=user_pc_refresh, user_lat=lat_refresh, user_lon=lon_refresh,
                    time_period=time_period_context, show_details=False # <<< Pass False
                )
                if not edit_telegram_message(chat_id, message_id, message_text, reply_markup=keyboard):
                    logger.error(f"Edit failed for refresh callback {data} on msg {message_id}")
            else: # No event found
                final_no_event_msg = NO_EVENTS_MESSAGE.format(context=f"further {no_event_context}", postcode=user_pc.upper() if user_pc else "your area")
                edit_telegram_message(chat_id, message_id, final_no_event_msg, reply_markup=None)
        except Exception as e:
            logger.error(f"Error in handle_refresh_callback for {data}: {e}", exc_info=True)
            try: edit_telegram_message(chat_id, message_id, DEFAULT_ERROR_MESSAGE, reply_markup=None)
            except Exception: pass

    # --- Back Action ---
    elif data == "show_previous":
        logger.info(f"Processing 'show_previous' for msg {message_id} in chat {chat_id}")
        history = message_event_history.get(history_key)
        original_context = message_context_type.get(history_key)
        if history and len(history) > 1 and original_context:
            try:
                history.pop() # Remove current
                event_to_show = history[-1] # Get previous
                can_go_back = len(history) > 1
                user_pc_back, lat_back, lon_back = get_user_location(chat_id)
                # Add distance
                if lat_back is not None and lon_back is not None:
                    try:
                        ev_lat=float(event_to_show.get("latitude",math.nan)); ev_lon=float(event_to_show.get("longitude",math.nan))
                        if not math.isnan(ev_lat) and not math.isnan(ev_lon): event_to_show["distance_km"] = haversine_distance(lat_back, lon_back, ev_lat, ev_lon)
                    except: pass
                # ***** MODIFIED Calls *****
                keyboard = create_event_keyboard(
                    event=event_to_show, refresh_callback_data=original_context,
                    can_go_back=can_go_back, is_currently_expanded=False # <<< Pass False
                )
                message_text = format_events_message(
                    events=[event_to_show], postcode=user_pc_back, user_lat=lat_back, user_lon=lon_back,
                    show_details=False # <<< Pass False
                )
                if not edit_telegram_message(chat_id, message_id, message_text, reply_markup=keyboard): logger.error(f"Edit failed for show_previous on msg {message_id}")
            except Exception as e: logger.error(f"Error processing show_previous: {e}", exc_info=True); edit_telegram_message(chat_id, message_id, DEFAULT_ERROR_MESSAGE, None)
        elif history and len(history) == 1: # At oldest
            logger.info(f"Cannot go back further for msg {message_id}, already at oldest.")
            try: # Just remove back button
                event_to_show = history[-1]; original_context = message_context_type.get(history_key, "load_random")
                keyboard = create_event_keyboard(event_to_show, original_context, can_go_back=False, is_currently_expanded=False) # <<< Pass False
                _telegram_api_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": json.dumps(keyboard if keyboard else {})})
            except Exception as e: logger.error(f"Error editing keyboard for show_previous (at oldest): {e}", exc_info=True)
        else: logger.warning(f"Could not find history/context for 'show_previous' on msg {message_id}")

    # --- Toggle Actions ---
    elif data == "toggle_details_show":
        logger.info(f"Processing 'toggle_details_show' for msg {message_id}")
        history = message_event_history.get(history_key)
        original_context = message_context_type.get(history_key)
        if history and original_context:
            try:
                event_to_show = history[-1] # Use current event from history
                can_go_back = len(history) > 1
                user_pc_toggle, lat_toggle, lon_toggle = get_user_location(chat_id)
                # Ensure distance present
                if lat_toggle is not None and lon_toggle is not None and "distance_km" not in event_to_show:
                     try:
                         ev_lat=float(event_to_show.get("latitude",math.nan)); ev_lon=float(event_to_show.get("longitude",math.nan))
                         if not math.isnan(ev_lat) and not math.isnan(ev_lon): event_to_show["distance_km"] = haversine_distance(lat_toggle, lon_toggle, ev_lat, ev_lon)
                     except: pass
                # ***** MODIFIED Calls *****
                message_text = format_events_message(
                    events=[event_to_show], postcode=user_pc_toggle, user_lat=lat_toggle, user_lon=lon_toggle,
                    show_details=True # <<< Show details
                )
                keyboard = create_event_keyboard(
                    event=event_to_show, refresh_callback_data=original_context,
                    can_go_back=can_go_back, is_currently_expanded=True # <<< State is now expanded
                )
                if not edit_telegram_message(chat_id, message_id, message_text, reply_markup=keyboard): logger.error(f"Edit failed for toggle_details_show on msg {message_id}")
            except Exception as e: logger.error(f"Error processing toggle_details_show: {e}", exc_info=True); edit_telegram_message(chat_id, message_id, DEFAULT_ERROR_MESSAGE, None)
        else: logger.warning(f"History/context not found for toggle_details_show on msg {message_id}")

    elif data == "toggle_details_hide":
        logger.info(f"Processing 'toggle_details_hide' for msg {message_id}")
        history = message_event_history.get(history_key)
        original_context = message_context_type.get(history_key)
        if history and original_context:
            try:
                event_to_show = history[-1] # Use current event
                can_go_back = len(history) > 1
                user_pc_toggle, lat_toggle, lon_toggle = get_user_location(chat_id)
                # Ensure distance present
                if lat_toggle is not None and lon_toggle is not None and "distance_km" not in event_to_show:
                     try:
                         ev_lat=float(event_to_show.get("latitude",math.nan)); ev_lon=float(event_to_show.get("longitude",math.nan))
                         if not math.isnan(ev_lat) and not math.isnan(ev_lon): event_to_show["distance_km"] = haversine_distance(lat_toggle, lon_toggle, ev_lat, ev_lon)
                     except: pass
                # ***** MODIFIED Calls *****
                message_text = format_events_message(
                    events=[event_to_show], postcode=user_pc_toggle, user_lat=lat_toggle, user_lon=lon_toggle,
                    show_details=False # <<< Hide details
                )
                keyboard = create_event_keyboard(
                    event=event_to_show, refresh_callback_data=original_context,
                    can_go_back=can_go_back, is_currently_expanded=False # <<< State is now collapsed
                )
                if not edit_telegram_message(chat_id, message_id, message_text, reply_markup=keyboard): logger.error(f"Edit failed for toggle_details_hide on msg {message_id}")
            except Exception as e: logger.error(f"Error processing toggle_details_hide: {e}", exc_info=True); edit_telegram_message(chat_id, message_id, DEFAULT_ERROR_MESSAGE, None)
        else: logger.warning(f"History/context not found for toggle_details_hide on msg {message_id}")

    # --- Fallback ---
    else:
        logger.warning(f"Received unhandled callback data: {data} from chat {chat_id}")

# --- Broadcast Logic ---

def broadcast_newsletter(n_events: int = DEFAULT_BROADCAST_LIMIT) -> None:
    """Send weekly updates to subscribers."""
    subscribers: ta.List[ta.Dict[str, ta.Any]] = []
    try:
        resp = supabase.table("telegram_subscribers").select("chat_id").execute()
        subscribers = resp.data if resp and hasattr(resp, 'data') else []
    except Exception as exc:
        logger.error(f"Error fetching subscribers for broadcast: {exc}", exc_info=True); return

    logger.info(f"Starting broadcast to {len(subscribers)} subscribers.")
    sent_count: int = 0
    today_str: str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    future_str: str = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    for sub in subscribers:
        chat_id: ta.Optional[str] = sub.get("chat_id")
        if not chat_id: continue

        user_pc: ta.Optional[str]; lat: ta.Optional[float]; lon: ta.Optional[float]
        user_pc, lat, lon = get_user_location(chat_id)
        events_to_send: ta.List[ta.Dict[str, ta.Any]] = []
        message_header: str = f"🎉 Your Saturday Update!"
        time_period_str: str = "in the next 7 days"
        postcode_for_msg: str = "" # Only include postcode if used for fetch

        if user_pc:
            if lat is not None and lon is not None: # Geocoded successfully
                events_to_send = fetch_events(date_from=today_str, date_to=future_str, user_lat=lat, user_lon=lon, overall_limit=n_events)
                message_header = f"🎉 Your Saturday Update near {user_pc.upper()}!"
                postcode_for_msg = user_pc
            else: # Stored PC, but geocode failed
                 logger.warning(f"Failed geocode in broadcast for stored postcode '{user_pc}' (Chat ID: {chat_id}).")
                 message_header = f"⚠️ Couldn't use postcode {user_pc}. Showing random events."
                 time_period_str = "some random events"
        else: # No postcode stored
            message_header = "📍 Set your location with /updatelocation for local events!\n\n🎉 Your Saturday Update!"
            time_period_str = "some random events"

        if not events_to_send: # Fetch random if needed
            events_to_send = fetch_random_events(days_ahead=7, limit=n_events)
            if "Update!" not in message_header: message_header += " Showing random events."

        msg_text: str = format_events_message(
            events=events_to_send, time_period=time_period_str,
            postcode=postcode_for_msg, user_lat=lat, user_lon=lon
        )

        if events_to_send and msg_text:
            full_message: str = f"{message_header}\n\n{msg_text}"
            if send_telegram_message(chat_id, full_message):
                sent_count += 1
            else: logger.error(f"Failed sending broadcast to chat_id {chat_id}.")
        elif not events_to_send:
             logger.info(f"No events found for broadcast to chat_id {chat_id}.")

        time.sleep(0.5) # Rate limit

    logger.info(f"Broadcast finished. Sent to {sent_count}/{len(subscribers)} subscribers.")


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
            now_utc: datetime.datetime = datetime.datetime.utcnow()
            current_hour_key: str = f"{now_utc.date()}-{now_utc.hour}"
            if now_utc.weekday() == 5 and now_utc.hour == 9 and current_hour_key != last_broadcast_hour_key:
                 logger.info(f"Triggering Saturday 9AM UTC broadcast for {current_hour_key}.")
                 broadcast_newsletter()
                 last_broadcast_hour_key = current_hour_key # Mark as triggered
        except Exception as e:
            logger.error(f"Error during broadcast check/trigger: {e}", exc_info=True)

        time.sleep(1) # Loop sleep


if __name__ == "__main__":
    main()