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

def send_telegram_message(chat_id: str, text: str, reply_markup: ta.Optional[ta.Dict[str, ta.Any]] = None) -> bool:
    """Send a text message, handling splitting."""
    parts: ta.List[str] = [text[i:i + TELEGRAM_MAX_MSG_LENGTH] for i in range(0, len(text), TELEGRAM_MAX_MSG_LENGTH)]
    success: bool = True
    for i, part in enumerate(parts):
        payload: ta.Dict[str, ta.Any] = {
            "chat_id": str(chat_id),
            "text": part,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        # Add reply_markup only to the last part
        if reply_markup and i == len(parts) - 1:
             payload["reply_markup"] = json.dumps(reply_markup)

        if not _telegram_api_request("sendMessage", payload):
            success = False # Error logged in helper

        if len(parts) > 1 and i < len(parts) - 1:
            time.sleep(0.2)
    return success

def format_event_for_forwarding(event: ta.Dict[str, ta.Any]) -> str:
    """Creates a simple text summary of an event suitable for forwarding."""
    lines = []
    name = (event.get("pretty_event_name") or "Event").strip()
    venue = (event.get("pretty_venue_name") or "Venue").strip()
    date = (event.get("pretty_date") or event.get("event_date") or "Date TBC").strip()
    url = (event.get("venue_url") or "").strip()
    summary = (event.get("pretty_description") or "").strip() # Shorter summary maybe?
    max_fwd_summary = 100
    if len(summary) > max_fwd_summary:
         summary = summary[:max_fwd_summary] + "..."

    lines.append(f"{name} @ {venue} ({date})")
    if summary:
        lines.append(summary)
    if url and (url.startswith("http://") or url.startswith("https://")):
        lines.append(f"More info: {url}")
    # Optional: Add a link back to the bot? e.g. f"Found via @YourBotUsername"
    return "\n".join(lines)

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

        if chat_type == 'private':
            supabase.table("telegram_subscribers").upsert({
                "chat_id": str(chat_id),
                "subscribed_date": datetime.datetime.utcnow().isoformat()
            }, on_conflict="chat_id").execute()
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
    user_lon: ta.Optional[float] = None
) -> str:
    """Format a list of events into a single message string."""
    if not events: return ""

    lines: ta.List[str] = []
    if len(events) > 1:
        header_parts: ta.List[str] = ["Here are events"]
        if time_period: header_parts.append(time_period)
        lines.append(" ".join(header_parts) + ":\n")

    for ev in events:
        event_lines: ta.List[str] = []
        name: str = (ev.get("pretty_event_name") or "Event").strip()
        venue: str = (ev.get("pretty_venue_name") or "Venue").strip()
        date: str = (ev.get("pretty_date") or ev.get("event_date") or "Date TBC").strip()
        url: str = (ev.get("venue_url") or "").strip()
        vibes: str = (ev.get("vibes") or "").strip()
        summary: str = (ev.get("pretty_description") or "No description available.").strip()
        max_summary_len: int = 250
        if len(summary) > max_summary_len: summary = summary[:max_summary_len] + "..."

        venue_html: str = f"<i>{venue}</i>"
        # Ensure URL is properly encoded before including in HTML
        if url and (url.startswith("http://") or url.startswith("https://")):
            try:
                encoded_url: str = urllib.parse.quote(url, safe=':/%#?=@') # Encode URL safely
                venue_html = f'<a href="{encoded_url}">{venue}</a>'
            except Exception as e:
                logger.warning(f"Failed to encode URL '{url}': {e}")
                # Keep venue_html as simple italic text if encoding fails

        event_lines.append(f"<b>{name}</b>")
        event_lines.append(f"📍 {venue_html}")
        event_lines.append(f"👉 {summary}")
        if vibes: event_lines.append(f"✨ {vibes}")
        event_lines.append(f"📅 {date}")

        # Distance and Direction
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
            except (ValueError, TypeError, KeyError): # Catch potential float conversion or key errors
                 logger.warning(f"Error processing distance/bearing for event {ev.get('event_id')}", exc_info=True)

        lines.append("\n".join(event_lines))

    return "\n\n".join(lines)

# Full function provided again for clarity
def handle_refresh_callback(chat_id: str, message_id: int, callback_data: str) -> None:
    """Handles all refresh callback queries (load_...). Updates history."""
    # --- Initial Setup ---
    fetch_params: ta.Dict[str, ta.Any] = {}
    user_pc: ta.Optional[str] = None
    lat: ta.Optional[float] = None
    lon: ta.Optional[float] = None
    fetch_limit: int = DEFAULT_EVENT_FETCH_LIMIT # Assumes constant is defined
    is_location_based: bool = callback_data in ["load_local", "load_today", "load_tomorrow"]
    is_random: bool = callback_data == "load_random"
    is_best: bool = callback_data == "load_best" # Treated like random
    time_period_context: str = ""
    no_event_context: str = ""
    event_to_show: ta.Optional[ta.Dict[str, ta.Any]] = None # The event we'll display
    fetched_events: ta.List[ta.Dict[str, ta.Any]] = [] # Initialize

    # --- Get Location if Needed ---
    if is_location_based:
        user_pc, lat, lon = get_user_location(chat_id) # Assumes this helper exists
        if not user_pc:
            edit_telegram_message(chat_id, message_id, LOCATION_PROMPT_MESSAGE, reply_markup=None) # Assumes constant exists
            return
        if lat is None or lon is None:
            edit_telegram_message(chat_id, message_id, GEOCODE_ERROR_MESSAGE.format(postcode=user_pc), reply_markup=None) # Assumes constant exists
            return
        fetch_params.update({"user_lat": lat, "user_lon": lon})
        no_event_context = f"near {user_pc.upper()}"

    # --- Determine Fetch Dates/Context ---
    today_dt: datetime.datetime = datetime.datetime.utcnow()
    today_str: str = today_dt.strftime("%Y-%m-%d")

    if callback_data == "load_local":
        fetch_params["date_from"] = today_str
        fetch_params["date_to"] = (today_dt + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        time_period_context = "nearby"
        no_event_context = f"in the next 7 days {no_event_context}".strip()
    elif callback_data == "load_today":
        fetch_params["date_from"] = today_str
        fetch_params["date_to"] = today_str
        time_period_context = "today"
        no_event_context = f"today {no_event_context}".strip()
    elif callback_data == "load_tomorrow":
        tomorrow_dt: datetime.datetime = today_dt + datetime.timedelta(days=1)
        tomorrow_str: str = tomorrow_dt.strftime("%Y-%m-%d")
        fetch_params["date_from"] = tomorrow_str
        fetch_params["date_to"] = tomorrow_str
        time_period_context = "tomorrow"
        no_event_context = f"tomorrow {no_event_context}".strip()
    # Note: No specific date params set here for random/best, handled below

    # --- Fetch event(s) ---
    if is_random or is_best:
        fetched_events = fetch_random_events(days_ahead=DEFAULT_RANDOM_DAYS_AHEAD, limit=1) # Assumes this helper exists
        time_period_context = "a random event" if is_random else "a top pick"
        no_event_context = "randomly" if is_random else "as a top pick"
    elif is_location_based:
        fetched_events = fetch_events(overall_limit=fetch_limit, **fetch_params) # Assumes this helper exists
    else:
         logger.error(f"Unhandled callback type in refresh handler: {callback_data}")
         return

    # --- Select Event to Show ---
    # SIMPLIFICATION: Just take the first event found, or a random one if multiple were fetched for location.
    if fetched_events:
        if is_location_based and len(fetched_events) > 1:
            event_to_show = random.choice(fetched_events) # Pick randomly from the fetched pool
            logger.info(f"Refresh for msg {message_id}: Chose random event {event_to_show.get('event_id', 'N/A')} from {len(fetched_events)} fetched.")
        else:
            event_to_show = fetched_events[0] # Take the first (or only) one
            logger.info(f"Refresh for msg {message_id}: Selected event {event_to_show.get('event_id', 'N/A')}")
    # else: event_to_show remains None

    # --- Update message or show 'no events' ---
    if event_to_show:
        # Get user location again for distance calculation if needed
        user_pc_refresh, lat_refresh, lon_refresh = (user_pc, lat, lon) if is_location_based else get_user_location(chat_id)

        if lat_refresh is not None and lon_refresh is not None:
            try: # Add/update distance if possible
                ev_lat = float(event_to_show.get("latitude", math.nan))
                ev_lon = float(event_to_show.get("longitude", math.nan))
                if not math.isnan(ev_lat) and not math.isnan(ev_lon):
                    event_to_show["distance_km"] = haversine_distance(lat_refresh, lon_refresh, ev_lat, ev_lon)
            except (ValueError, TypeError): pass

        # --- Update History BEFORE editing ---
        # Consider moving this AFTER successful edit to avoid state mismatch?
        # Let's keep it here for now, simpler flow, accept mismatch risk.
        history_key = (chat_id, message_id)
        if history_key not in message_event_history:
             message_event_history[history_key] = deque(maxlen=HISTORY_SIZE)
             logger.warning(f"Initialized missing history for msg {message_id} during refresh.")
        message_event_history[history_key].append(event_to_show.copy())
        if history_key not in message_context_type:
             message_context_type[history_key] = callback_data
             logger.warning(f"Initialized missing context '{callback_data}' for msg {message_id} during refresh.")
        current_history_len = len(message_event_history[history_key])
        logger.info(f"Appended history for msg {message_id}. New len: {current_history_len}")

        # --- Format and Edit ---
        can_go_back: bool = current_history_len > 1
        keyboard: ta.Optional[ta.Dict[str, ta.Any]] = create_event_keyboard(event_to_show, callback_data, can_go_back=can_go_back)
        message_text: str = format_events_message(
            events=[event_to_show],
            postcode=user_pc_refresh,
            user_lat=lat_refresh,
            user_lon=lon_refresh,
            time_period=time_period_context
        )
        logger.info(f"Attempting to edit msg {message_id} for refresh callback {callback_data}")
        if not edit_telegram_message(chat_id, message_id, message_text, reply_markup=keyboard):
            logger.error(f"Edit failed for refresh callback {callback_data} on msg {message_id}")
            # HISTORY IS NOW OUT OF SYNC WITH DISPLAYED MESSAGE!
    else:
        # No event found at all by the fetch
        logger.info(f"No events found for refresh callback {callback_data} on msg {message_id}")
        final_no_event_msg = NO_EVENTS_MESSAGE.format(context=no_event_context, postcode=user_pc.upper() if user_pc else "your area")
        edit_telegram_message(chat_id, message_id, final_no_event_msg, reply_markup=None)

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
    # ... (keep initial setup: is_location_based, user location checks etc) ...
    is_location_based: bool = command in ["/local", "/today", "/tomorrow"]
    is_random: bool = command == "/random"
    is_best: bool = command == "/best" # Treated like random for now

    user_pc: ta.Optional[str] = None
    lat: ta.Optional[float] = None
    lon: ta.Optional[float] = None
    fetch_params: ta.Dict[str, ta.Any] = {}
    callback_data: str = "" # This will store the 'load_...' type
    time_period_context: str = ""
    no_event_context: str = ""

    if is_location_based:
        user_pc, lat, lon = get_user_location(chat_id)
        if not user_pc: send_telegram_message(chat_id, LOCATION_PROMPT_MESSAGE); return
        if lat is None or lon is None: send_telegram_message(chat_id, GEOCODE_ERROR_MESSAGE.format(postcode=user_pc)); return
        fetch_params.update({"user_lat": lat, "user_lon": lon})
        no_event_context = f"near {user_pc.upper()}"

    today_dt: datetime.datetime = datetime.datetime.utcnow()
    today_str: str = today_dt.strftime("%Y-%m-%d")

    # --- Determine fetch params and context based on command ---
    if command == "/local":
        fetch_params["date_from"] = today_str
        fetch_params["date_to"] = (today_dt + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        callback_data = "load_local"
        time_period_context = "nearby"
        no_event_context = f"in the next 7 days {no_event_context}".strip()
    elif command == "/today":
        fetch_params["date_from"] = today_str
        fetch_params["date_to"] = today_str
        callback_data = "load_today"
        time_period_context = "today"
        no_event_context = f"today {no_event_context}".strip()
    elif command == "/tomorrow":
        tomorrow_dt: datetime.datetime = today_dt + datetime.timedelta(days=1)
        tomorrow_str: str = tomorrow_dt.strftime("%Y-%m-%d")
        fetch_params["date_from"] = tomorrow_str
        fetch_params["date_to"] = tomorrow_str
        callback_data = "load_tomorrow"
        time_period_context = "tomorrow"
        no_event_context = f"tomorrow {no_event_context}".strip()
    elif is_random or is_best:
        events: ta.List[ta.Dict[str, ta.Any]] = fetch_random_events(days_ahead=DEFAULT_RANDOM_DAYS_AHEAD, limit=1)
        callback_data = "load_random" if is_random else "load_best"
        time_period_context = "a random event" if is_random else "a top pick"
        no_event_context = "randomly" if is_random else "as a top pick"
        # --- Send random/best event ---
        if events:
            event: ta.Dict[str, ta.Any] = events[0]
            user_pc_rand, lat_rand, lon_rand = get_user_location(chat_id)
            if lat_rand is not None and lon_rand is not None:
                 try: # Add distance if possible
                    ev_lat = float(event.get("latitude", math.nan))
                    ev_lon = float(event.get("longitude", math.nan))
                    if not math.isnan(ev_lat) and not math.isnan(ev_lon):
                        event["distance_km"] = haversine_distance(lat_rand, lon_rand, ev_lat, ev_lon)
                 except (ValueError, TypeError): pass
            # First time sending, cannot go back
            keyboard: ta.Optional[ta.Dict[str, ta.Any]] = create_event_keyboard(event, callback_data, can_go_back=False)
            message_text: str = format_events_message(events=[event], postcode=user_pc_rand, user_lat=lat_rand, user_lon=lon_rand, time_period=time_period_context)
            sent_message_data = send_telegram_message(chat_id, message_text, reply_markup=keyboard)

            # --- Initialize History ---
            if sent_message_data and isinstance(sent_message_data, dict) and (msg_id := sent_message_data.get('message_id')):
                history_key = (str(chat_id), msg_id)
                message_event_history[history_key] = deque([event], maxlen=HISTORY_SIZE)
                message_context_type[history_key] = callback_data # Store context type
                logger.info(f"Initialized history for msg {msg_id} in chat {chat_id} with event {event.get('event_id')}")
            else:
                 logger.error(f"Failed to get message_id after sending {command} message to {chat_id}")
        else: send_telegram_message(chat_id, f"Sorry, couldn't find any events {no_event_context} right now.")
        return # Exit

    # --- Fetch and Send location-based event ---
    events = fetch_events(overall_limit=1, **fetch_params)
    if events:
        event = events[0]
        # First time sending, cannot go back
        keyboard = create_event_keyboard(event, callback_data, can_go_back=False)
        message_text = format_events_message(events=[event], postcode=user_pc, user_lat=lat, user_lon=lon, time_period=time_period_context)
        sent_message_data = send_telegram_message(chat_id, message_text, reply_markup=keyboard)

        # --- Initialize History ---
        if sent_message_data and isinstance(sent_message_data, dict) and (msg_id := sent_message_data.get('message_id')):
            history_key = (str(chat_id), msg_id)
            message_event_history[history_key] = deque([event], maxlen=HISTORY_SIZE)
            message_context_type[history_key] = callback_data # Store context type
            logger.info(f"Initialized history for msg {msg_id} in chat {chat_id} with event {event.get('event_id')}")
        else:
            logger.error(f"Failed to get message_id after sending {command} message to {chat_id}")
    else: send_telegram_message(chat_id, NO_EVENTS_MESSAGE.format(context=no_event_context, postcode=user_pc.upper() if user_pc else ""))


def handle_refresh_callback(chat_id: str, message_id: int, callback_data: str) -> None:
    """Handles all refresh callback queries (load_...). Updates history."""
    # --- Initial Setup ---
    fetch_params: ta.Dict[str, ta.Any] = {}
    user_pc: ta.Optional[str] = None
    lat: ta.Optional[float] = None
    lon: ta.Optional[float] = None
    # Fetch more events than needed to increase chance of finding a different one
    fetch_limit: int = DEFAULT_EVENT_FETCH_LIMIT # Assumes constant is defined
    is_location_based: bool = callback_data in ["load_local", "load_today", "load_tomorrow"]
    is_random: bool = callback_data == "load_random"
    is_best: bool = callback_data == "load_best" # Treated like random
    time_period_context: str = ""
    no_event_context: str = ""
    event_to_show: ta.Optional[ta.Dict[str, ta.Any]] = None # The event we'll display
    fetched_events: ta.List[ta.Dict[str, ta.Any]] = [] # Initialize

    # --- Get Location if Needed ---
    if is_location_based:
        user_pc, lat, lon = get_user_location(chat_id) # Assumes this helper exists
        if not user_pc:
            # Cannot refresh location-based without location
            edit_telegram_message(chat_id, message_id, LOCATION_PROMPT_MESSAGE, reply_markup=None) # Assumes constant exists
            return
        if lat is None or lon is None:
            # Stored postcode exists but geocoding failed
            edit_telegram_message(chat_id, message_id, GEOCODE_ERROR_MESSAGE.format(postcode=user_pc), reply_markup=None) # Assumes constant exists
            return
        fetch_params.update({"user_lat": lat, "user_lon": lon})
        no_event_context = f"near {user_pc.upper()}"

    # --- Determine Fetch Dates/Context ---
    today_dt: datetime.datetime = datetime.datetime.utcnow()
    today_str: str = today_dt.strftime("%Y-%m-%d")

    if callback_data == "load_local":
        fetch_params["date_from"] = today_str
        fetch_params["date_to"] = (today_dt + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        time_period_context = "nearby"
        no_event_context = f"in the next 7 days {no_event_context}".strip()
    elif callback_data == "load_today":
        fetch_params["date_from"] = today_str
        fetch_params["date_to"] = today_str
        time_period_context = "today"
        no_event_context = f"today {no_event_context}".strip()
    elif callback_data == "load_tomorrow":
        tomorrow_dt: datetime.datetime = today_dt + datetime.timedelta(days=1)
        tomorrow_str: str = tomorrow_dt.strftime("%Y-%m-%d")
        fetch_params["date_from"] = tomorrow_str
        fetch_params["date_to"] = tomorrow_str
        time_period_context = "tomorrow"
        no_event_context = f"tomorrow {no_event_context}".strip()
    # Note: No date params needed for random/best fetch path below

    # --- Fetch event(s) ---
    if is_random or is_best:
        # Fetch 1 new random/best event
        fetched_events = fetch_random_events(days_ahead=DEFAULT_RANDOM_DAYS_AHEAD, limit=1) # Assumes this helper exists
        time_period_context = "a random event" if is_random else "a top pick"
        no_event_context = "randomly" if is_random else "as a top pick"
    elif is_location_based:
        # Fetch multiple potential events based on location/date
        fetched_events = fetch_events(overall_limit=fetch_limit, **fetch_params) # Assumes this helper exists
    else:
         logger.error(f"Unhandled callback type in refresh handler: {callback_data}")
         return

    # --- Select Event to Show ---
    if fetched_events:
        history_key = (chat_id, message_id)
        current_history: ta.Optional[deque[ta.Dict[str, ta.Any]]] = message_event_history.get(history_key)
        current_event_id: ta.Optional[str] = None
        if current_history:
            try:
                # Get ID of the event currently displayed (last in deque)
                current_event_id = current_history[-1].get("event_id")
            except IndexError:
                logger.warning(f"History deque empty for {history_key} unexpectedly.")

        # Try to find an event different from the current one
        possible_events: ta.List[ta.Dict[str, ta.Any]] = [ev for ev in fetched_events if ev.get("event_id") != current_event_id]

        if possible_events:
            # Choose randomly from the different events found
            event_to_show = random.choice(possible_events)
            logger.info(f"Refresh for msg {message_id}: Found {len(possible_events)} different event(s), chose {event_to_show.get('event_id')}")
        elif fetched_events:
            # Only the same event(s) were found, or only one total was fetched
            event_to_show = fetched_events[0] # Show the first one (likely same as current)
            logger.info(f"Refresh for msg {message_id}: No different events found, re-showing {event_to_show.get('event_id')}")
        # else: fetched_events was empty, event_to_show remains None

    # --- Update message or show 'no events' ---
    if event_to_show:
        # Get user location again for distance calculation if needed (user might have updated it)
        # Use the location determined earlier if location-based, or try fetching if random/best
        user_pc_refresh, lat_refresh, lon_refresh = (user_pc, lat, lon) if is_location_based else get_user_location(chat_id)

        if lat_refresh is not None and lon_refresh is not None:
            try: # Add/update distance if possible
                ev_lat = float(event_to_show.get("latitude", math.nan))
                ev_lon = float(event_to_show.get("longitude", math.nan))
                if not math.isnan(ev_lat) and not math.isnan(ev_lon):
                    # Ensure distance is calculated using the potentially updated user location
                    event_to_show["distance_km"] = haversine_distance(lat_refresh, lon_refresh, ev_lat, ev_lon) # Assumes helper exists
            except (ValueError, TypeError): pass # Ignore distance calc errors

        # --- Update History ---
        history_key = (chat_id, message_id)
        if history_key not in message_event_history:
             # Initialize history if it somehow doesn't exist (e.g., after restart)
             message_event_history[history_key] = deque(maxlen=HISTORY_SIZE) # Assumes constant exists
             logger.warning(f"Initialized missing history for msg {message_id} during refresh.")
        # Append a copy to avoid modifying the same dict object if it's reused
        message_event_history[history_key].append(event_to_show.copy())
        # Ensure context type is stored (important for back button consistency)
        if history_key not in message_context_type:
             message_context_type[history_key] = callback_data # Store the *current* refresh type
             logger.warning(f"Initialized missing context '{callback_data}' for msg {message_id} during refresh.")

        current_history_len = len(message_event_history[history_key])
        logger.info(f"Appended history for msg {message_id}. New len: {current_history_len}")

        # --- Format and Edit ---
        can_go_back: bool = current_history_len > 1
        keyboard: ta.Optional[ta.Dict[str, ta.Any]] = create_event_keyboard(event_to_show, callback_data, can_go_back=can_go_back)
        message_text: str = format_events_message( # Assumes this helper exists
            events=[event_to_show],
            postcode=user_pc_refresh, # Use the latest postcode fetched
            user_lat=lat_refresh,
            user_lon=lon_refresh,
            time_period=time_period_context
        )
        logger.info(f"Attempting to edit msg {message_id} for refresh callback {callback_data}")
        if not edit_telegram_message(chat_id, message_id, message_text, reply_markup=keyboard): # Assumes this helper exists
            logger.error(f"Edit failed for refresh callback {callback_data} on msg {message_id}")
            # Potential state inconsistency if edit fails after history update
    else:
        # No event found at all by the fetch
        logger.info(f"No events found for refresh callback {callback_data} on msg {message_id}")
        # Edit message to indicate no events found
        edit_telegram_message(chat_id, message_id, NO_EVENTS_MESSAGE.format(context=no_event_context, postcode=user_pc.upper() if user_pc else ""), reply_markup=None) # Assumes constant exists


# --- Main Message Processing Logic ---

def process_message(msg: ta.Dict[str, ta.Any]) -> None:
    """Handles incoming text messages and commands."""
    chat_info: ta.Dict[str, ta.Any] = msg.get('chat', {})
    chat_id: str = str(chat_info.get('id', ''))
    chat_type: str = chat_info.get('type', '')
    user_info: ta.Dict[str, ta.Any] = msg.get('from', {})

    if not chat_id or user_info.get('is_bot') or msg.get('edit_date'): return # Basic validation

    text_raw: str = (msg.get('text') or '').strip()
    text_lower: str = text_raw.lower()

    logger.info(f"Processing message from chat {chat_id} (user: {user_info.get('id')}): '{text_raw}'")

    upsert_chat_info(chat_id, chat_type, user_info) # Update DB

    # Command routing map
    command_map: ta.Dict[str, ta.Callable[[], None]] = {
        "/start": lambda: send_telegram_message(chat_id, help_text),
        "/help": lambda: send_telegram_message(chat_id, help_text),
        "/local": lambda: handle_single_event_command(chat_id, "/local"),
        "/today": lambda: handle_single_event_command(chat_id, "/today"),
        "/tomorrow": lambda: handle_single_event_command(chat_id, "/tomorrow"),
        "/random": lambda: handle_single_event_command(chat_id, "/random"),
        "/best": lambda: handle_single_event_command(chat_id, "/best"),
    }

    handler: ta.Optional[ta.Callable[[], None]] = command_map.get(text_lower)
    if handler:
        awaiting_location_update[chat_id] = False
        handler()
        return

    # Handle stateful commands
    if text_lower == "/updatelocation":
        awaiting_location_update[chat_id] = True
        send_telegram_message(chat_id, "OK. Please send me your London postcode (e.g., SW1A 0AA).")
    elif text_lower == "/subscribe":
        if chat_type == 'private':
            awaiting_location_update[chat_id] = False
            send_telegram_message(chat_id, "You're set to receive the weekly roundup!")
        else: send_telegram_message(chat_id, "Subscription commands only work in private chat with me.")
    elif text_lower == "/unsubscribe":
        if chat_type == 'private':
            awaiting_location_update[chat_id] = False
            if unsubscribe_user(chat_id):
                send_telegram_message(chat_id, "You've been unsubscribed from the weekly roundup.")
            else: send_telegram_message(chat_id, "Sorry, there was an error trying to unsubscribe.")
        else: send_telegram_message(chat_id, "Subscription commands only work in private chat with me.")

    # Handle postcode input
    elif is_valid_london_postcode(text_raw.upper()):
        postcode_norm: str = text_raw.upper()
        if awaiting_location_update.get(chat_id, False):
            lat_check, lon_check = geocode_postcode_to_latlon(postcode_norm)
            if lat_check is not None and lon_check is not None:
                if set_user_postcode(chat_id, postcode_norm):
                    send_telegram_message(chat_id, f"✅ Location updated to {postcode_norm}!")
                else: send_telegram_message(chat_id, "⚠️ There was an error saving your postcode.")
            else: send_telegram_message(chat_id, f"⚠️ Couldn't find coordinates for {postcode_norm}. Please try a different London postcode.")
            awaiting_location_update[chat_id] = False
        else:
            # Direct postcode query (sends multiple messages)
            lat, lon = geocode_postcode_to_latlon(postcode_norm)
            if not lat or not lon:
                send_telegram_message(chat_id, f"Sorry, I couldn’t find coordinates for {postcode_norm}."); return

            send_telegram_message(chat_id, f"OK, looking for events near {postcode_norm}...")
            today: datetime.datetime = datetime.datetime.utcnow()
            events: ta.List[ta.Dict[str, ta.Any]] = fetch_events(
                date_from=today.strftime("%Y-%m-%d"),
                date_to=(today + datetime.timedelta(days=7)).strftime("%Y-%m-%d"),
                user_lat=lat, user_lon=lon,
                overall_limit=5 # Specific limit for this case
            )
            if events:
                 # --- Local definition for multi-message sending ---
                 def send_multi_event_messages(
                    p_chat_id: str, p_events: ta.List[ta.Dict[str, ta.Any]], p_postcode: str = "",
                    p_user_lat: ta.Optional[float] = None, p_user_lon: ta.Optional[float] = None) -> None:
                     for event in p_events:
                         message = format_events_message( events=[event], postcode=p_postcode, user_lat=p_user_lat, user_lon=p_user_lon)
                         if message:
                             send_telegram_message(p_chat_id, message)
                             time.sleep(0.2)
                 # --- Call the local sender ---
                 send_multi_event_messages( chat_id=chat_id, p_events=events, p_postcode=postcode_norm, p_user_lat=lat, p_user_lon=lon )
            else: send_telegram_message(chat_id, f"Couldn't find any events near {postcode_norm} in the next 7 days.")

    # Fallback for unrecognized input
    else:
        if not awaiting_location_update.get(chat_id, False):
             send_telegram_message(chat_id, "Sorry, I didn't understand that. Try /help to see available commands.")

def process_callback_query(callback_query: ta.Dict[str, ta.Any]) -> None:
    """Handles incoming callback queries."""
    query_id: ta.Optional[str] = callback_query.get('id')
    message: ta.Optional[ta.Dict[str, ta.Any]] = callback_query.get('message')
    data: ta.Optional[str] = callback_query.get('data') # e.g., "load_random"

    if not query_id or not message or not data:
        logger.warning("Received incomplete callback query.")
        if query_id: answer_callback_query(query_id); return

    chat_id: str = str(message.get('chat', {}).get('id', ''))
    message_id: ta.Optional[int] = message.get('message_id')

    # Acknowledge first
    answer_callback_query(query_id)

    if not chat_id or not message_id:
        logger.error(f"Could not get chat_id/message_id from callback {query_id}"); return

    history_key = (chat_id, message_id) # Use consistent key type

    # --- Route Callback Data ---
    if data.startswith("load_"):
        # It's a refresh action
        handle_refresh_callback(chat_id, message_id, data)

    elif data == "show_previous":
        logger.info(f"Processing 'show_previous' for msg {message_id} in chat {chat_id}")
        history = message_event_history.get(history_key)
        original_context = message_context_type.get(history_key)

        if history and len(history) > 1 and original_context:
            history.pop() # Remove the current one from the end
            event_to_show = history[-1] # Get the new last one (the previous)

            can_go_back = len(history) > 1 # Can we go back further?

            # --- Get location data for formatting ---
            # (Needed again as it's not stored in history)
            user_pc_back, lat_back, lon_back = get_user_location(chat_id)
            # Add distance back if possible/relevant
            if lat_back is not None and lon_back is not None:
                try:
                    ev_lat = float(event_to_show.get("latitude", math.nan))
                    ev_lon = float(event_to_show.get("longitude", math.nan))
                    if not math.isnan(ev_lat) and not math.isnan(ev_lon):
                        event_to_show["distance_km"] = haversine_distance(lat_back, lon_back, ev_lat, ev_lon)
                except (ValueError, TypeError): pass

            # --- Format and Edit ---
            keyboard = create_event_keyboard(event_to_show, original_context, can_go_back=can_go_back)
            # Try to determine original time period context (minor detail, can omit if too complex)
            # For simplicity, we might just show the event without specific time period on 'back'
            message_text = format_events_message(
                events=[event_to_show],
                postcode=user_pc_back, user_lat=lat_back, user_lon=lon_back
                # time_period= "previously shown" # Or determine based on original_context?
            )
            edit_telegram_message(chat_id, message_id, message_text, reply_markup=keyboard)

        elif history and len(history) == 1:
            # We are already at the first event, cannot go back further
            answer_callback_query(query_id) # Maybe add text="Already at oldest event" ?
            logger.info(f"Cannot go back further for msg {message_id}, already at oldest.")
            # Optionally edit the message slightly? Or just do nothing.
            # Let's edit the keyboard to remove the back button if needed.
            event_to_show = history[-1]
            original_context = message_context_type.get(history_key, "load_random") # Fallback context
            keyboard = create_event_keyboard(event_to_show, original_context, can_go_back=False)
            # Edit only the keyboard
            _telegram_api_request("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": json.dumps(keyboard if keyboard else {})})

        else:
            # History not found or empty, shouldn't happen if button was shown
            logger.warning(f"Could not find history or context for 'show_previous' on msg {message_id}")
            # Maybe answer callback query with an error text?

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