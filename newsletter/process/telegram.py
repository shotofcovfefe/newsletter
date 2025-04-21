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
from supabase import create_client
from dotenv import load_dotenv

from newsletter.utils import (is_valid_london_postcode, geocode_postcode_to_latlon, haversine_distance, calculate_bearing, bearing_to_arrow)

load_dotenv()


# Basic Logging Configuration (adjust as needed)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Handle potential missing environment variables during startup
if not all([SUPABASE_URL, SUPABASE_KEY, TELEGRAM_BOT_TOKEN]):
    logger.error("Missing required environment variables (SUPABASE_URL, SUPABASE_KEY, TELEGRAM_BOT_TOKEN). Exiting.")
    exit() # Or raise an exception

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

awaiting_location_update = {}  # dict: {chat_id: bool}

# ---------------------------------------------------------------------
# Telegram Helper (Keep as is)
# ---------------------------------------------------------------------

def get_telegram_updates(offset: ta.Optional[int] = None) -> ta.List[ta.Dict]:
    """
    Poll new updates from Telegram.
    By default, sets a 30 second timeout to allow for long-polling.
    """
    if not TELEGRAM_BOT_TOKEN:
        # This check might be redundant due to the startup check, but kept for safety
        logger.error("TELEGRAM_BOT_TOKEN not configured.")
        return []

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": 30}
    if offset is not None:
        params["offset"] = offset

    try:
        # Increased overall request timeout
        r = requests.get(url, params=params, timeout=40)
        if r.status_code == 200:
            return r.json().get('result', [])
        # Handle Telegram's 502 error during restarts gracefully
        elif r.status_code == 502:
             logger.warning("Received 502 Bad Gateway from Telegram, likely restarting. Will retry.")
             time.sleep(5) # Wait a bit before retrying
             return []
        else:
            logger.error(f"Failed to get updates: {r.status_code} - {r.text}")
            return []
    except requests.exceptions.Timeout:
        logger.warning("Telegram getUpdates request timed out. Retrying.")
        return []
    except requests.exceptions.RequestException as exc:
        logger.error(f"Error getting updates: {exc}")
        return []
    except Exception as exc:
        logger.error(f"Unexpected error getting updates: {exc}", exc_info=True)
        return []


def send_telegram_message(chat_id: str, text: str, reply_markup: ta.Optional[ta.Dict] = None) -> bool:
    """Send a text message to a Telegram user/channel, splitting if over 4000 chars."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Telegram bot token not configured.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Telegram's max message length is 4096, leave a little buffer
    max_length = 4000
    parts = []
    if len(text) > max_length:
        # Basic split logic, can be improved to split at newlines etc.
        parts = [text[i:i + max_length] for i in range(0, len(text), max_length)]
    else:
        parts = [text]

    success = True

    for i, part in enumerate(parts):
        payload = {
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        # Only add reply_markup to the last part if splitting, or the only part if not splitting
        if reply_markup and i == len(parts) - 1:
             payload["reply_markup"] = json.dumps(reply_markup) # Use json.dumps here

        try:
            # Added timeout to post request
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code != 200:
                logger.error(f"Failed to send message part {i+1}/{len(parts)} to {chat_id}: {resp.status_code} - {resp.text}")
                success = False
        except requests.exceptions.RequestException as exc:
            logger.error(f"Error sending message part: {exc}")
            success = False
        except Exception as exc:
            logger.error(f"Unexpected error sending message part: {exc}", exc_info=True)
            success = False
        # Small delay between parts if splitting
        if len(parts) > 1 and i < len(parts) - 1:
            time.sleep(0.2) # Increased slightly

    return success


def edit_telegram_message(chat_id: str, message_id: int, text: str, reply_markup: ta.Optional[ta.Dict] = None) -> bool:
    """Edit an existing message text and optionally its inline keyboard."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Telegram bot token not configured.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
    # Telegram's max message length is 4096
    max_length = 4000
    if len(text) > max_length:
        logger.warning(f"Attempting to edit message {message_id} in chat {chat_id} with text longer than {max_length} chars. Truncating.")
        text = text[:max_length]

    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        # Inline keyboard markup needs to be a JSON string for editing
        payload["reply_markup"] = json.dumps(reply_markup)
    else:
        # Explicitly send empty reply_markup if we intend to remove the keyboard
        payload["reply_markup"] = json.dumps({})


    try:
        # Added timeout
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
             # Gracefully handle the "message is not modified" error
            resp_json = {}
            try:
                resp_json = resp.json()
            except json.JSONDecodeError:
                pass # Keep resp_json as {} if response is not valid JSON

            if resp_json.get("description") and "message is not modified" in resp_json["description"].lower():
                logger.info(f"Message {message_id} in chat {chat_id} was not modified (content likely the same).")
                return True # Treat as success, no change needed
            else:
                logger.error(f"Failed to edit message {message_id} in chat {chat_id}: {resp.status_code} - {resp.text}")
                return False
        return True
    except requests.exceptions.RequestException as exc:
        logger.error(f"Error editing message: {exc}")
        return False
    except Exception as exc:
        logger.error(f"Unexpected error editing message: {exc}", exc_info=True)
        return False


def answer_callback_query(callback_query_id: str) -> bool:
    """Sends an empty acknowledgement for a callback query."""
    if not TELEGRAM_BOT_TOKEN:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    try:
        # Added timeout
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code != 200:
            logger.error(f"Failed to answer callback query {callback_query_id}: {resp.status_code} - {resp.text}")
            return False
        return True
    except requests.exceptions.RequestException as exc:
        logger.error(f"Error answering callback query: {exc}")
        return False
    except Exception as exc:
        logger.error(f"Unexpected error answering callback query: {exc}", exc_info=True)
        return False


# ---------------------------------------------------------------------
# Fetch Events (Keep as is, overall_limit is controlled by caller)
# ---------------------------------------------------------------------
def fetch_events(
    date_from: ta.Optional[str] = None,
    date_to: ta.Optional[str] = None,
    user_lat: ta.Optional[float] = None,
    user_lon: ta.Optional[float] = None,
    max_distance_km: float = 15.0,
    limit_per_venue: int = 1,
    overall_limit: int = 5 # Default limit remains 5 for general use
) -> ta.List[ta.Dict[str, ta.Any]]:
    """Fetch events from events_enriched, filtered by date and location if provided."""
    query = supabase.table("events_enriched").select("*", count='exact')

    # Date filtering
    if date_from and date_to:
        if date_from == date_to:
            # For single day, include events exactly on that date
            query = query.eq("event_date", date_from)
        else:
            # For range, include from start date up to (but not including) end date
            query = query.gte("event_date", date_from).lt("event_date", date_to)
    elif date_from:
        # Only start date provided
        query = query.gte("event_date", date_from)
    elif date_to:
         # Only end date provided (less common use case)
         query = query.lt("event_date", date_to)
    # If neither date_from nor date_to, it fetches all future events implicitly if combined with location sort later? No, let's ensure it fetches future events if no dates given
    if not date_from and not date_to:
         today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
         query = query.gte("event_date", today_str)


    try:
        resp = query.execute()
        data = resp.data or []
        count = resp.count # Get the total count matching filters *before* location calc
        # logger.info(f"Initial fetch count for query: {count}") # Debug log
    except Exception as exc:
        logger.error(f"Error fetching events from Supabase: {exc}", exc_info=True)
        return []

    # Location filtering and distance calculation
    events_with_distance = []
    if user_lat is not None and user_lon is not None:
        for row in data:
            ev_lat = row.get("latitude")
            ev_lon = row.get("longitude")
            # Skip events without valid coordinates
            if ev_lat is None or ev_lon is None:
                continue # Don't add distance, just skip
            try:
                dist = haversine_distance(
                    lat1=user_lat,
                    lon1=user_lon,
                    lat2=float(ev_lat),
                    lon2=float(ev_lon)
                )
                # Filter by distance *before* adding to the list
                if dist <= max_distance_km:
                    row["distance_km"] = dist
                    events_with_distance.append(row)
            except (ValueError, TypeError):
                 logger.warning(f"Could not parse lat/lon for event {row.get('event_id')}: lat={ev_lat}, lon={ev_lon}")
                 continue # Skip if coordinates are invalid
        # If location provided, use the distance-filtered list
        data = events_with_distance
    # else: data remains the list fetched initially if no location provided

    # Apply limit per venue *after* distance filtering
    by_venue = {}
    filtered_by_venue = []
    for r in data:
        v_id = r.get("venue_id")
        if v_id not in by_venue:
            by_venue[v_id] = 0
        if by_venue[v_id] < limit_per_venue:
            filtered_by_venue.append(r)
            by_venue[v_id] += 1

    # Sort the results
    if user_lat is not None and user_lon is not None:
        # Sort by distance if location was used
        sorted_events = sorted(filtered_by_venue, key=lambda x: x["distance_km"])
    else:
        # Otherwise, sort by date (primary) and then maybe name (secondary)?
        sorted_events = sorted(filtered_by_venue, key=lambda x: (x["event_date"], x.get("pretty_event_name", "")))

    # Apply the overall limit *after* sorting
    # logger.info(f"Returning {min(len(sorted_events), overall_limit)} events out of {len(sorted_events)} post-filtering.") # Debug log
    return sorted_events[:overall_limit]


def fetch_random_events(days_ahead: int = 7, limit: int = 1) -> ta.List[ta.Dict[str, ta.Any]]:
    """Return up to `limit` random events in the next `days_ahead` days."""
    today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    future_str = (datetime.datetime.utcnow() + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    try:
        # Fetching more initially to improve randomness if called repeatedly
        potential_limit = max(limit * 5, 20) # Fetch a larger pool
        resp = (
            supabase.table("events_enriched")
            .select("*")
            .gte("event_date", today_str)
            .lt("event_date", future_str)
            .limit(potential_limit) # Limit DB query size
            .execute()
        )
        data = resp.data or []
    except Exception as exc:
        logger.error(f"Error fetching random events: {exc}", exc_info=True)
        return []

    if not data:
        return []

    # Shuffle the potentially larger list and take the required limit
    random.shuffle(data)
    return data[:limit]

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
        # Call format_events_message without the invalid parameter
        message = format_events_message(
            events=[event], # Format one event at a time
            postcode=postcode,
            user_lat=user_lat,
            user_lon=user_lon
            # is_single_event_request removed
        )
        if message:
            send_telegram_message(chat_id, message)
            time.sleep(0.2) # Keep delay between messages
        else:
            logger.warning(f"Empty message generated by format_events_message for event: {event.get('event_id', 'N/A')}")


# ---------------------------------------------------------------------
# User Postcodes (MODIFIED get_user_postcode, set_user_postcode)
# ---------------------------------------------------------------------

def get_user_postcode(chat_id: str) -> ta.Optional[str]:
    """Return the user's stored postcode, or None if none."""
    try:
        resp = (
            supabase.table("user_postcodes")
            .select("postcode")
            .eq("chat_id", str(chat_id)) # Ensure chat_id is string
            .single() # Returns error if not exactly one row found (or no rows)
            .execute()
        )
        return resp.data["postcode"] if resp.data else None
    except Exception as e: # Changed from bare except
        # Log if it's not just 'No results found' which single() might raise implicitly
        # Check PostgREST error details if possible if needed
        # Example: PostgrestAPIError has http_status attribute
        logger.error(f"Error getting user postcode for {chat_id}: {e}", exc_info=True)
        return None


def set_user_postcode(chat_id: str, postcode: str) -> bool:
    """Store or update the user's postcode using upsert. Returns True on success."""
    try:
        # Use upsert for atomicity: insert or update if chat_id exists
        # Assumes 'chat_id' is the primary key or has a unique constraint
        supabase.table("user_postcodes").upsert(
            {
                "chat_id": str(chat_id), # Ensure chat_id is string
                "postcode": postcode.upper().strip(), # Store consistently
                "created_date": datetime.datetime.utcnow().isoformat() # Keep track of updates
            },
            on_conflict="chat_id" # Specify the conflict target column
        ).execute()
        # If execute() doesn't raise an exception, assume success
        return True
    except Exception as e:
         logger.error(f"Error setting postcode for {chat_id}: {e}", exc_info=True)
         return False # Return False on failure


# ---------------------------------------------------------------------
# Broadcast Events (Keep as is)
# ---------------------------------------------------------------------

def broadcast_newsletter(n_events: int = 5):
    """Send weekly updates to subscribers with local or random events."""
    try:
        # Fetch only chat_id
        resp = supabase.table("telegram_subscribers").select("chat_id").execute()
        # Ensure we have a list, even if empty
        subscribers = resp.data if hasattr(resp, 'data') and resp.data else []
    except Exception as exc:
        logger.error(f"Error fetching subscribers for Saturday broadcast: {exc}", exc_info=True)
        return

    logger.info(f"Starting broadcast to {len(subscribers)} subscribers.")
    broadcast_count = 0

    for sub in subscribers:
        chat_id = sub.get("chat_id")
        if not chat_id:
            logger.warning("Found subscriber entry with no chat_id.")
            continue

        user_pc = get_user_postcode(chat_id)
        lat, lon = None, None
        events_to_send = []
        message_header = ""
        time_period_str = "in the next 7 days" # Default period for broadcast

        if user_pc:
            # Validate postcode format roughly first
            if is_valid_london_postcode(user_pc): # Assuming this checks format and maybe region
                lat, lon = geocode_postcode_to_latlon(user_pc)
                if lat is not None and lon is not None:
                    # Successfully got location, fetch local events
                    today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
                    n_days = 7
                    future_date = datetime.datetime.utcnow() + datetime.timedelta(days=n_days)
                    future_str = future_date.strftime("%Y-%m-%d")
                    # Fetch events for the next 7 days near the user
                    events_to_send = fetch_events(
                        date_from=today_str,
                        date_to=future_str,
                        user_lat=lat,
                        user_lon=lon,
                        overall_limit=n_events # Use the broadcast limit
                        )
                    message_header = f"🎉 Your Saturday Update near {user_pc}!"
                else:
                    # Geocoding failed for a stored postcode
                    logger.warning(f"Failed to geocode stored postcode '{user_pc}' for chat_id {chat_id}.")
                    message_header = f"⚠️ Couldn't use postcode {user_pc}. Showing random events."
            else:
                 # Stored postcode is invalid
                 logger.warning(f"Invalid stored postcode '{user_pc}' for chat_id {chat_id}.")
                 message_header = f"⚠️ Your stored postcode {user_pc} seems invalid. Showing random events."
        else:
            # No postcode stored
            message_header = "📍 Set your location with /updatelocation for local events!\n\n🎉 Your Saturday Update!"

        # If local events weren't fetched successfully, get random ones
        if not events_to_send:
            events_to_send = fetch_random_events(days_ahead=7, limit=n_events)
            if not message_header: # Ensure there's a header if random events are the fallback
                message_header = "🎉 Your Saturday Update!"
            # Only adjust time period if we actually fell back to random
            time_period_str = "some random events"

        # Format the message (handles empty events_to_send)
        # Call format_events_message without the invalid parameter
        msg_text = format_events_message(
            events=events_to_send,
            time_period=time_period_str,
            postcode=user_pc if lat is not None else "", # Only show postcode if used
            user_lat=lat,
            user_lon=lon
            # is_single_event_request removed
        )

        # Send the combined header and event list
        full_message = f"{message_header}\n\n{msg_text}"
        if send_telegram_message(chat_id, full_message):
            broadcast_count += 1
        else:
             logger.error(f"Failed to send broadcast message to chat_id {chat_id}.")

        time.sleep(0.5) # Pause between sending to different users

    logger.info(f"Successfully sent broadcast to {broadcast_count}/{len(subscribers)} subscribers.")


# ---------------------------------------------------------------------
# Format Messages (Signature unchanged, logic handles single event via len())
# ---------------------------------------------------------------------

def format_events_message(
    events: ta.List[ta.Dict[str, ta.Any]],
    time_period: str = "",
    postcode: str = "",
    user_lat: ta.Optional[float] = None,
    user_lon: ta.Optional[float] = None
) -> str:
    """
    Format a list of events using rich HTML formatting. Includes distance and direction if available.
    - time_period: e.g., "today", "tomorrow", "in the next 7 days"
    - postcode: included in the distance line if provided and relevant
    - user_lat, user_lon: User's coordinates needed for direction calculation.
    """
    if not events:
        # Let the caller handle the "no events" message for better context.
        return ""


    lines = []
    # --- Header Logic ---
    # Only add a header if formatting multiple events (e.g., for broadcast, postcode search)
    # Check length directly instead of using the removed parameter
    if len(events) > 1:
        header_parts = ["Here are events"]
        if time_period: header_parts.append(time_period)
        # Avoid adding postcode to header if it's already in the distance line
        # if postcode and not (user_lat is not None and user_lon is not None):
        #    header_parts.append(f"near {postcode.upper()}")
        lines.append(" ".join(header_parts) + ":\n")
    # If formatting a single event, the calling function adds context if needed.

    # --- Event Formatting ---
    for i, ev in enumerate(events):
        event_lines = [] # Store lines for the current event

        name = (ev.get("pretty_event_name") or "Event").strip()
        venue = (ev.get("pretty_venue_name") or "Venue").strip()
        date = (ev.get("pretty_date") or ev.get("event_date") or "Date TBC").strip() # Fallback date
        url = (ev.get("venue_url") or "").strip()
        vibes = (ev.get("vibes") or "").strip()
        summary = (ev.get("pretty_description") or "No description available.").strip()

        # Truncate long summaries
        max_summary_len = 250
        if len(summary) > max_summary_len:
            summary = summary[:max_summary_len] + "..."

        # Venue Name + Link
        venue_html = f"<i>{venue}</i>" # Default italic venue
        if url:
            # Basic URL validation (starts with http)
            if url.startswith("http://") or url.startswith("https://"):
                venue_html = f'<a href="{url}">{venue}</a>'
            else:
                logger.warning(f"Invalid URL format for event {ev.get('event_id')}: {url}")
                # Keep venue name without link if URL is bad

        # Event Name (Bold)
        event_lines.append(f"<b>{name}</b>")
        # Venue Line
        event_lines.append(f"📍 {venue_html}") # Use the generated venue_html
        # Summary Line
        event_lines.append(f"👉 {summary}")
        # Vibes Line (Optional)
        if vibes:
            event_lines.append(f"✨ {vibes}")
        # Date Line
        event_lines.append(f"📅 {date}")

        # --- Distance and Direction ---
        # Only add distance if postcode and coords were provided AND distance exists
        if "distance_km" in ev and postcode and user_lat is not None and user_lon is not None:
            dist_km = ev["distance_km"]
            arrow = "" # Initialize arrow

            # Calculate direction arrow if user coords and event coords are valid
            ev_lat_str = ev.get("latitude")
            ev_lon_str = ev.get("longitude")
            try:
                # Ensure event coords are valid floats and not NaN
                ev_lat = float(ev_lat_str) if ev_lat_str is not None else math.nan
                ev_lon = float(ev_lon_str) if ev_lon_str is not None else math.nan
                if not math.isnan(ev_lat) and not math.isnan(ev_lon):
                    # Calculate bearing and get arrow
                    bearing = calculate_bearing(user_lat, user_lon, ev_lat, ev_lon)
                    arrow = bearing_to_arrow(bearing) + " " # Add space after arrow
                else:
                    arrow = "" # No arrow if event coords invalid
            except (TypeError, ValueError, AttributeError):
                # logger.warning(f"Could not parse event lat/lon for bearing: lat='{ev_lat_str}', lon='{ev_lon_str}' for event '{name}'")
                arrow = "" # Default to no arrow if coords are bad

            # Format distance string (meters or km)
            dist_str = ""
            try:
                if dist_km < 0.1: # Show meters if < 100m
                    dist_m = round(dist_km * 1000)
                    dist_str = f"{dist_m}m"
                elif dist_km < 10: # Show 1 decimal place if < 10km
                    dist_str = f"{dist_km:.1f}km"
                else: # Show no decimal places if >= 10km
                    dist_str = f"{dist_km:.0f}km"
            except (TypeError, ValueError):
                dist_str = "Distance unknown" # Fallback

            # Append the compass line with distance, arrow, and postcode
            event_lines.append(f"🧭 <i>{dist_str} {arrow}from {postcode.upper()}</i>")

        # Join lines for the current event with single newlines
        lines.append("\n".join(event_lines))

    # Join multiple events with double newline for separation
    return "\n\n".join(lines)


# ---------------------------------------------------------------------
# Process Callbacks (MODIFIED - removed is_single_event_request)
# ---------------------------------------------------------------------

def process_callback_query(callback_query: dict):
    """Handles incoming callback queries from inline keyboard buttons."""
    query_id = callback_query.get('id')
    message = callback_query.get('message')
    data = callback_query.get('data')

    if not query_id or not message or not data:
        logger.warning("Received incomplete callback query.")
        if query_id: answer_callback_query(query_id)
        return

    chat_id = str(message.get('chat', {}).get('id', ''))
    message_id = message.get('message_id')

    answer_callback_query(query_id) # Acknowledge first

    if not chat_id or not message_id:
        logger.error(f"Could not get chat_id or message_id from callback query {query_id}")
        return

    # --- Handle Specific Callbacks ---

    # --- Handle Random Refresh ---
    if data == "load_random":
        logger.info(f"Processing 'load_random' callback from chat {chat_id}, msg {message_id}")
        new_events = fetch_random_events(days_ahead=7, limit=1)

        if new_events:
            new_event = new_events[0]
            user_pc = None
            lat, lon = None, None
            postcode_valid_and_geocoded = False

            # --- Attempt to get user location for distance calculation ---
            user_pc = get_user_postcode(chat_id)
            if user_pc and is_valid_london_postcode(user_pc):
                lat, lon = geocode_postcode_to_latlon(user_pc)
                if lat is not None and lon is not None:
                    postcode_valid_and_geocoded = True
                    # Calculate distance if possible
                    ev_lat_str = new_event.get("latitude")
                    ev_lon_str = new_event.get("longitude")
                    try:
                        temp_ev_lat = float(ev_lat_str) if ev_lat_str is not None else math.nan
                        temp_ev_lon = float(ev_lon_str) if ev_lon_str is not None else math.nan
                        if not math.isnan(temp_ev_lat) and not math.isnan(temp_ev_lon):
                            dist = haversine_distance(lat, lon, temp_ev_lat, temp_ev_lon)
                            new_event["distance_km"] = dist
                    except (ValueError, TypeError): pass # Ignore errors

            # --- Construct Keyboard ---
            refresh_button = {"text": "🔄🔄🔄", "callback_data": "load_random"}
            button_row = [refresh_button]
            maps_url = None

            # Try to get venue name and postcode for map link
            venue_name = new_event.get("pretty_venue_name")
            venue_postcode = new_event.get("postcode") #

            if venue_name and venue_postcode: # Check if both are non-empty
                try:
                    search_query = f"{venue_name}, {venue_postcode}"
                    encoded_query = urllib.parse.quote_plus(search_query)
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
                    map_button = {"text": "📍", "url": maps_url}
                    button_row.append(map_button)
                except Exception as e:
                    logger.error(f"Error creating map link for {venue_name}: {e}")
            else:
                 logger.warning(f"Missing venue name or postcode for map link for event {new_event.get('event_id')}")


            keyboard = {"inline_keyboard": [button_row]}

            # --- Format and Edit Message ---
            if postcode_valid_and_geocoded and "distance_km" in new_event:
                 new_message_text = format_events_message(
                    events=[new_event], time_period="a random event",
                    postcode=user_pc, user_lat=lat, user_lon=lon
                )
            else:
                new_message_text = format_events_message(
                    events=[new_event], time_period="a random event"
                )
            edit_telegram_message(chat_id, message_id, new_message_text, reply_markup=keyboard)
        else:
            edit_telegram_message(chat_id, message_id, "Sorry, couldn't find another random event right now.", reply_markup=None)

    # --- Handle Local Refresh ---
    elif data == "load_local":
        logger.info(f"Processing 'load_local' callback from chat {chat_id}, msg {message_id}")
        user_pc = get_user_postcode(chat_id)
        if not user_pc or not is_valid_london_postcode(user_pc):
             edit_telegram_message(chat_id, message_id, "Please set a valid London location first using /updatelocation.", reply_markup=None); return
        lat, lon = geocode_postcode_to_latlon(user_pc)
        if lat is None or lon is None:
             edit_telegram_message(chat_id, message_id, f"Could not find location for {user_pc}. Please update it.", reply_markup=None); return

        today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        future_date = datetime.datetime.utcnow() + datetime.timedelta(days=7)
        future_str = future_date.strftime("%Y-%m-%d")
        fetched_events = fetch_events(
            date_from=today_str, date_to=future_str, user_lat=lat, user_lon=lon, overall_limit=10
        )

        if fetched_events:
            new_event = random.choice(fetched_events)
            maps_url = None

            # --- Construct Keyboard ---
            refresh_button = {"text": "🔄🔄🔄", "callback_data": "load_local"}
            button_row = [refresh_button]

            venue_name = new_event.get("pretty_venue_name")
            venue_postcode = new_event.get("postcode") # *** ASSUMES THIS KEY EXISTS ***

            if venue_name and venue_postcode:
                try:
                    search_query = f"{venue_name}, {venue_postcode}"
                    encoded_query = urllib.parse.quote_plus(search_query)
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
                    map_button = {"text": "📍", "url": maps_url}
                    button_row.append(map_button)
                except Exception as e:
                    logger.error(f"Error creating map link for {venue_name}: {e}")
            else:
                 logger.warning(f"Missing venue name or postcode for map link for event {new_event.get('event_id')}")

            keyboard = {"inline_keyboard": [button_row]}

            # --- Format and Edit Message ---
            new_message_text = format_events_message(
                events=[new_event], postcode=user_pc, user_lat=lat, user_lon=lon, time_period="nearby"
            )
            edit_telegram_message(chat_id, message_id, new_message_text, reply_markup=keyboard)
        else:
             edit_telegram_message(chat_id, message_id, f"Sorry, couldn't find any other local events near {user_pc} in the next 7 days.", reply_markup=None)

    # --- Handle Today Refresh ---
    elif data == "load_today":
        logger.info(f"Processing 'load_today' callback from chat {chat_id}, msg {message_id}")
        user_pc = get_user_postcode(chat_id)
        if not user_pc or not is_valid_london_postcode(user_pc):
             edit_telegram_message(chat_id, message_id, "Please set a valid London location first using /updatelocation.", reply_markup=None); return
        lat, lon = geocode_postcode_to_latlon(user_pc)
        if lat is None or lon is None:
             edit_telegram_message(chat_id, message_id, f"Could not find location for {user_pc}. Please update it.", reply_markup=None); return

        today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        fetched_events = fetch_events(
            date_from=today_str, date_to=today_str, user_lat=lat, user_lon=lon, overall_limit=10
        )

        if fetched_events:
            new_event = random.choice(fetched_events)
            maps_url = None

            # --- Construct Keyboard ---
            refresh_button = {"text": "🔄🔄🔄", "callback_data": "load_today"}
            button_row = [refresh_button]

            venue_name = new_event.get("pretty_venue_name")
            venue_postcode = new_event.get("postcode") # *** ASSUMES THIS KEY EXISTS ***

            if venue_name and venue_postcode:
                try:
                    search_query = f"{venue_name}, {venue_postcode}"
                    encoded_query = urllib.parse.quote_plus(search_query)
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
                    map_button = {"text": "📍", "url": maps_url}
                    button_row.append(map_button)
                except Exception as e:
                    logger.error(f"Error creating map link for {venue_name}: {e}")
            else:
                 logger.warning(f"Missing venue name or postcode for map link for event {new_event.get('event_id')}")

            keyboard = {"inline_keyboard": [button_row]}

            # --- Format and Edit Message ---
            new_message_text = format_events_message(
                events=[new_event], postcode=user_pc, user_lat=lat, user_lon=lon, time_period="today"
            )
            edit_telegram_message(chat_id, message_id, new_message_text, reply_markup=keyboard)
        else:
             edit_telegram_message(chat_id, message_id, f"Sorry, couldn't find any other events today near {user_pc}.", reply_markup=None)

    # --- Handle Tomorrow Refresh ---
    elif data == "load_tomorrow":
        logger.info(f"Processing 'load_tomorrow' callback from chat {chat_id}, msg {message_id}")
        user_pc = get_user_postcode(chat_id)
        if not user_pc or not is_valid_london_postcode(user_pc):
             edit_telegram_message(chat_id, message_id, "Please set a valid London location first using /updatelocation.", reply_markup=None); return
        lat, lon = geocode_postcode_to_latlon(user_pc)
        if lat is None or lon is None:
             edit_telegram_message(chat_id, message_id, f"Could not find location for {user_pc}. Please update it.", reply_markup=None); return

        tomorrow_date = datetime.datetime.utcnow() + datetime.timedelta(days=1)
        tomorrow_str = tomorrow_date.strftime("%Y-%m-%d")
        fetched_events = fetch_events(
            date_from=tomorrow_str, date_to=tomorrow_str, user_lat=lat, user_lon=lon, overall_limit=10
        )

        if fetched_events:
            new_event = random.choice(fetched_events)
            maps_url = None

            # --- Construct Keyboard ---
            refresh_button = {"text": "🔄🔄🔄", "callback_data": "load_tomorrow"}
            button_row = [refresh_button]

            venue_name = new_event.get("pretty_venue_name")
            venue_postcode = new_event.get("postcode") # *** ASSUMES THIS KEY EXISTS ***

            if venue_name and venue_postcode:
                try:
                    search_query = f"{venue_name}, {venue_postcode}"
                    encoded_query = urllib.parse.quote_plus(search_query)
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
                    map_button = {"text": "📍", "url": maps_url}
                    button_row.append(map_button)
                except Exception as e:
                    logger.error(f"Error creating map link for {venue_name}: {e}")
            else:
                 logger.warning(f"Missing venue name or postcode for map link for event {new_event.get('event_id')}")

            keyboard = {"inline_keyboard": [button_row]}

            # --- Format and Edit Message ---
            new_message_text = format_events_message(
                events=[new_event], postcode=user_pc, user_lat=lat, user_lon=lon, time_period="tomorrow"
            )
            edit_telegram_message(chat_id, message_id, new_message_text, reply_markup=keyboard)
        else:
             edit_telegram_message(chat_id, message_id, f"Sorry, couldn't find any other events tomorrow near {user_pc}.", reply_markup=None)

    elif data == "load_best":
        logger.info(f"Processing 'load_best' callback from chat {chat_id}, msg {message_id}")
        # Fetch ONE new random event as "best" for now
        new_events = fetch_random_events(days_ahead=7, limit=1)

        if new_events:
            new_event = new_events[0]
            user_pc = None
            lat, lon = None, None  # User's location
            postcode_valid_and_geocoded = False
            maps_url = None

            # --- Attempt to get user location for distance calculation ---
            user_pc = get_user_postcode(chat_id)
            if user_pc and is_valid_london_postcode(user_pc):
                lat, lon = geocode_postcode_to_latlon(user_pc)
                if lat is not None and lon is not None:
                    postcode_valid_and_geocoded = True
                    # Calculate distance if possible
                    ev_lat_str = new_event.get("latitude")
                    ev_lon_str = new_event.get("longitude")
                    try:
                        temp_ev_lat = float(ev_lat_str) if ev_lat_str is not None else math.nan
                        temp_ev_lon = float(ev_lon_str) if ev_lon_str is not None else math.nan
                        if not math.isnan(temp_ev_lat) and not math.isnan(temp_ev_lon):
                            dist = haversine_distance(lat, lon, temp_ev_lat, temp_ev_lon)
                            new_event["distance_km"] = dist
                    except (ValueError, TypeError):
                        pass  # Ignore errors

            # --- Construct Keyboard ---
            refresh_button = {"text": "🔄🔄🔄", "callback_data": "load_best"}  # Note callback_data
            button_row = [refresh_button]

            venue_name = new_event.get("pretty_venue_name")
            # Use the venue postcode field added previously to events_enriched
            venue_postcode = new_event.get("postcode")

            if venue_name and venue_postcode:
                try:
                    search_query = f"{venue_name}, {venue_postcode}"
                    encoded_query = urllib.parse.quote_plus(search_query)
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"  # Use HTTPS
                    map_button = {"text": "📍", "url": maps_url}
                    button_row.append(map_button)
                except Exception as e:
                    logger.error(f"Error creating map link for {venue_name}: {e}")
            else:
                logger.warning(f"Missing venue name or postcode for map link for event {new_event.get('event_id')}")

            keyboard = {"inline_keyboard": [button_row]}

            # --- Format and Edit Message ---
            time_period = "a top pick"  # Context for formatting
            if postcode_valid_and_geocoded and "distance_km" in new_event:
                new_message_text = format_events_message(
                    events=[new_event], time_period=time_period,
                    postcode=user_pc, user_lat=lat, user_lon=lon
                )
            else:
                new_message_text = format_events_message(
                    events=[new_event], time_period=time_period
                )

            edit_telegram_message(chat_id, message_id, new_message_text, reply_markup=keyboard)
        else:
            # No *other* "best" event found
            edit_telegram_message(chat_id, message_id, "Sorry, couldn't find another 'best' event right now.",
                                  reply_markup=None)

    else:
        # Handle unrecognized callback data
        logger.warning(f"Received unhandled callback data: {data} from chat {chat_id}")


# ---------------------------------------------------------------------
# Process Incoming Messages (MODIFIED - removed is_single_event_request)
# ---------------------------------------------------------------------

def process_message(msg: dict):
    chat_info = msg.get('chat', {})
    chat_id = str(chat_info.get('id', ''))
    chat_type = chat_info.get('type', '')
    user_info = msg.get('from', {})
    user_id = str(user_info.get('id', ''))
    first_name = user_info.get('first_name', '')
    last_name = user_info.get('last_name', '')
    username = user_info.get('username', '')

    text_raw = (msg.get('text') or '').strip()
    text_lower = text_raw.lower()

    if not chat_id or user_info.get('is_bot'): return
    if msg.get('edit_date'): return

    logger.info(
        f"Processing message from chat {chat_id} (type: {chat_type}, user: {user_id} '{first_name}'): '{text_raw}'")

    # Update chat info and ensure subscription
    try:
        supabase.rpc( 'upsert_telegram_chat', { 'p_chat_id': chat_id, 'p_chat_type': chat_type, 'p_first_name': first_name, 'p_last_name': last_name, 'p_username': username } ).execute()
        if chat_type == 'private':
            supabase.table("telegram_subscribers").upsert( {"chat_id": chat_id, "subscribed_date": datetime.datetime.utcnow().isoformat()}, on_conflict="chat_id" ).execute()
    except Exception as exc: logger.error(f"Error updating chat/subscriber info for chat {chat_id}: {exc}", exc_info=True)

    # Define help text
    help_text = (
        "Welcome to Niche London Events! 👋\n\n"
        "I find unique and interesting events happening across London.\n\n"
        "<b>Commands:</b>\n"
        "/local - Show a nearby event (needs location set)\n"
        "/today - Show an event happening today (needs location)\n"
        "/tomorrow - Show an event happening tomorrow (needs location)\n"
        "/random - Show a random event in the next week\n"
        "/best - Show some top picks for the week 🏆\n"
        "/updatelocation - Set/update your London postcode\n"
        "/help - Show this message\n\n"
        "Tip: You can also just send me a valid London postcode (e.g., E8 3PN) to set your location!"
    )

    # --- Command Handling ---

    if text_lower in ["/start", "/help", "help", "hello", "hi", "?"]:
        awaiting_location_update[chat_id] = False
        send_telegram_message(chat_id, help_text)

    elif text_lower == "/updatelocation":
        awaiting_location_update[chat_id] = True
        send_telegram_message(chat_id, "OK. Please send me your London postcode (e.g., SW1A 0AA).")

    elif text_lower == "/subscribe":
        if chat_type == 'private':
            awaiting_location_update[chat_id] = False
            send_telegram_message(chat_id, "You're set to receive the weekly roundup!")
        else:
            send_telegram_message(chat_id, "Subscription commands only work in private chat with me.")

    elif text_lower == "/unsubscribe":
        if chat_type == 'private':
            awaiting_location_update[chat_id] = False
            try:
                supabase.table("telegram_subscribers").delete().eq("chat_id", chat_id).execute()
                send_telegram_message(chat_id, "You've been unsubscribed from the weekly roundup.")
            except Exception as exc:
                logger.error(f"Error unsubscribing chat {chat_id}: {exc}", exc_info=True)
                send_telegram_message(chat_id, "Sorry, there was an error trying to unsubscribe. Please try again later.")
        else:
            send_telegram_message(chat_id, "Subscription commands only work in private chat with me.")

    elif text_lower == "/local":
        awaiting_location_update[chat_id] = False
        user_pc = get_user_postcode(chat_id)
        if not user_pc or not is_valid_london_postcode(user_pc):
            send_telegram_message(chat_id, "I need your valid London location! Use /updatelocation."); return
        lat, lon = geocode_postcode_to_latlon(user_pc)
        if lat is None or lon is None:
            send_telegram_message(chat_id, f"Sorry, couldn't find coordinates for '{user_pc}'. Try updating."); return

        today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        future_date = datetime.datetime.utcnow() + datetime.timedelta(days=7)
        future_str = future_date.strftime("%Y-%m-%d")
        events = fetch_events( date_from=today_str, date_to=future_str, user_lat=lat, user_lon=lon, overall_limit=1 )

        if events:
            event = events[0]
            maps_url = None

            # --- Construct Keyboard ---
            refresh_button = {"text": "🔄🔄🔄", "callback_data": "load_local"}
            button_row = [refresh_button]

            venue_name = event.get("pretty_venue_name")
            venue_postcode = event.get("postcode") # *** ASSUMES THIS KEY EXISTS ***

            if venue_name and venue_postcode:
                try:
                    search_query = f"{venue_name}, {venue_postcode}"
                    encoded_query = urllib.parse.quote_plus(search_query)
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
                    map_button = {"text": "📍", "url": maps_url}
                    button_row.append(map_button)
                except Exception as e:
                    logger.error(f"Error creating map link for {venue_name}: {e}")
            else:
                 logger.warning(f"Missing venue name or postcode for map link for event {event.get('event_id')}")

            keyboard = {"inline_keyboard": [button_row]}

            # --- Format and Send Message ---
            message_text = format_events_message(
                events=[event], postcode=user_pc, user_lat=lat, user_lon=lon, time_period="nearby"
            )
            send_telegram_message(chat_id, message_text, reply_markup=keyboard)
        else:
            send_telegram_message(chat_id, f"Couldn't find any events near {user_pc.upper()} in the next 7 days.")

    elif text_lower == "/today":
        awaiting_location_update[chat_id] = False
        user_pc = get_user_postcode(chat_id)
        if not user_pc or not is_valid_london_postcode(user_pc):
            send_telegram_message(chat_id, "I need your valid London location for today's events! Use /updatelocation."); return
        lat, lon = geocode_postcode_to_latlon(user_pc)
        if lat is None or lon is None:
            send_telegram_message(chat_id, f"Sorry, couldn't find coordinates for '{user_pc}'. Try updating."); return

        today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        events = fetch_events( date_from=today_str, date_to=today_str, user_lat=lat, user_lon=lon, overall_limit=1 )

        if events:
            event = events[0]
            maps_url = None

            # --- Construct Keyboard ---
            refresh_button = {"text": "🔄🔄🔄", "callback_data": "load_today"}
            button_row = [refresh_button]

            venue_name = event.get("pretty_venue_name")
            venue_postcode = event.get("postcode") # *** ASSUMES THIS KEY EXISTS ***

            if venue_name and venue_postcode:
                try:
                    search_query = f"{venue_name}, {venue_postcode}"
                    encoded_query = urllib.parse.quote_plus(search_query)
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
                    map_button = {"text": "📍", "url": maps_url}
                    button_row.append(map_button)
                except Exception as e:
                    logger.error(f"Error creating map link for {venue_name}: {e}")
            else:
                 logger.warning(f"Missing venue name or postcode for map link for event {event.get('event_id')}")

            keyboard = {"inline_keyboard": [button_row]}

            # --- Format and Send Message ---
            message_text = format_events_message(
                events=[event], postcode=user_pc, user_lat=lat, user_lon=lon, time_period="today"
            )
            send_telegram_message(chat_id, message_text, reply_markup=keyboard)
        else:
            send_telegram_message(chat_id, f"Couldn't find any events today near {user_pc.upper()}.")

    elif text_lower == "/tomorrow":
        awaiting_location_update[chat_id] = False
        user_pc = get_user_postcode(chat_id)
        if not user_pc or not is_valid_london_postcode(user_pc):
             send_telegram_message(chat_id, "I need your valid London location for tomorrow's events! Use /updatelocation."); return
        lat, lon = geocode_postcode_to_latlon(user_pc)
        if lat is None or lon is None:
             send_telegram_message(chat_id, f"Sorry, couldn't find coordinates for '{user_pc}'. Try updating."); return

        tomorrow_date = datetime.datetime.utcnow() + datetime.timedelta(days=1)
        tomorrow_str = tomorrow_date.strftime("%Y-%m-%d")
        events = fetch_events( date_from=tomorrow_str, date_to=tomorrow_str, user_lat=lat, user_lon=lon, overall_limit=1 )

        if events:
            event = events[0]
            maps_url = None

            # --- Construct Keyboard ---
            refresh_button = {"text": "🔄🔄🔄", "callback_data": "load_tomorrow"}
            button_row = [refresh_button]

            venue_name = event.get("pretty_venue_name")
            venue_postcode = event.get("postcode") # *** ASSUMES THIS KEY EXISTS ***

            if venue_name and venue_postcode:
                try:
                    search_query = f"{venue_name}, {venue_postcode}"
                    encoded_query = urllib.parse.quote_plus(search_query)
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
                    map_button = {"text": "📍", "url": maps_url}
                    button_row.append(map_button)
                except Exception as e:
                    logger.error(f"Error creating map link for {venue_name}: {e}")
            else:
                 logger.warning(f"Missing venue name or postcode for map link for event {event.get('event_id')}")

            keyboard = {"inline_keyboard": [button_row]}

            # --- Format and Send Message ---
            message_text = format_events_message(
                events=[event], postcode=user_pc, user_lat=lat, user_lon=lon, time_period="tomorrow"
            )
            send_telegram_message(chat_id, message_text, reply_markup=keyboard)
        else:
            send_telegram_message(chat_id, f"Couldn't find any events tomorrow near {user_pc.upper()}.")

    elif text_lower == "/random":
        awaiting_location_update[chat_id] = False
        events = fetch_random_events(days_ahead=7, limit=1)

        if events:
            event = events[0]
            user_pc = None
            lat, lon = None, None
            postcode_valid_and_geocoded = False
            maps_url = None

            # --- Attempt to get user location for distance calculation ---
            user_pc = get_user_postcode(chat_id)
            if user_pc and is_valid_london_postcode(user_pc):
                lat, lon = geocode_postcode_to_latlon(user_pc)
                if lat is not None and lon is not None:
                    postcode_valid_and_geocoded = True
                    # Calculate distance if possible
                    ev_lat_str = event.get("latitude")
                    ev_lon_str = event.get("longitude")
                    try:
                        temp_ev_lat = float(ev_lat_str) if ev_lat_str is not None else math.nan
                        temp_ev_lon = float(ev_lon_str) if ev_lon_str is not None else math.nan
                        if not math.isnan(temp_ev_lat) and not math.isnan(temp_ev_lon):
                            dist = haversine_distance(lat, lon, temp_ev_lat, temp_ev_lon)
                            event["distance_km"] = dist
                    except (ValueError, TypeError): pass # ignore errors

            # --- Construct Keyboard ---
            refresh_button = {"text": "🔄🔄🔄", "callback_data": "load_random"}
            button_row = [refresh_button]

            venue_name = event.get("pretty_venue_name")
            venue_postcode = event.get("postcode") # *** ASSUMES THIS KEY EXISTS ***

            if venue_name and venue_postcode:
                try:
                    search_query = f"{venue_name}, {venue_postcode}"
                    encoded_query = urllib.parse.quote_plus(search_query)
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
                    map_button = {"text": "📍", "url": maps_url}
                    button_row.append(map_button)
                except Exception as e:
                    logger.error(f"Error creating map link for {venue_name}: {e}")
            else:
                 logger.warning(f"Missing venue name or postcode for map link for event {event.get('event_id')}")

            keyboard = {"inline_keyboard": [button_row]}

            # --- Format and Send Message ---
            if postcode_valid_and_geocoded and "distance_km" in event:
                 message_text = format_events_message(
                    events=[event], time_period="a random event",
                    postcode=user_pc, user_lat=lat, user_lon=lon
                )
            else:
                 message_text = format_events_message(
                    events=[event], time_period="a random event"
                )
            send_telegram_message(chat_id, message_text, reply_markup=keyboard)
        else:
            send_telegram_message(chat_id, "Sorry, couldn't find any random events right now.")

    elif text_lower == "/best":
        awaiting_location_update[chat_id] = False
        logger.info(f"Processing /best command for chat {chat_id}")

        # Fetch ONE random event as "best" for now
        events = fetch_random_events(days_ahead=7, limit=1)

        if events:
            event = events[0]
            user_pc = None
            lat, lon = None, None
            postcode_valid_and_geocoded = False
            maps_url = None

            # --- Attempt to get user location for distance/formatting ---
            user_pc = get_user_postcode(chat_id)
            if user_pc and is_valid_london_postcode(user_pc):
                lat, lon = geocode_postcode_to_latlon(user_pc)
                if lat is not None and lon is not None:
                    postcode_valid_and_geocoded = True
                    # Calculate distance if possible
                    ev_lat_str = event.get("latitude")
                    ev_lon_str = event.get("longitude")
                    try:
                        temp_ev_lat = float(ev_lat_str) if ev_lat_str is not None else math.nan
                        temp_ev_lon = float(ev_lon_str) if ev_lon_str is not None else math.nan
                        if not math.isnan(temp_ev_lat) and not math.isnan(temp_ev_lon):
                            dist = haversine_distance(lat, lon, temp_ev_lat, temp_ev_lon)
                            event["distance_km"] = dist
                    except (ValueError, TypeError):
                        pass  # ignore errors

            # --- Construct Keyboard ---
            refresh_button = {"text": "🔄🔄🔄", "callback_data": "load_best"}  # Use specific callback
            button_row = [refresh_button]

            venue_name = event.get("pretty_venue_name")
            # Use the venue postcode field added previously to events_enriched
            venue_postcode = event.get("postcode")

            if venue_name and venue_postcode:
                try:
                    search_query = f"{venue_name}, {venue_postcode}"
                    encoded_query = urllib.parse.quote_plus(search_query)
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"  # Use HTTPS
                    map_button = {"text": "📍", "url": maps_url}
                    button_row.append(map_button)
                except Exception as e:
                    logger.error(f"Error creating map link for {venue_name}: {e}")
            else:
                logger.warning(f"Missing venue name or postcode for map link for event {event.get('event_id')}")

            keyboard = {"inline_keyboard": [button_row]}

            # --- Format and Send Single Message ---
            time_period = "a top pick"  # Context for formatting
            if postcode_valid_and_geocoded and "distance_km" in event:
                message_text = format_events_message(
                    events=[event], time_period=time_period,
                    postcode=user_pc, user_lat=lat, user_lon=lon
                )
            else:
                message_text = format_events_message(
                    events=[event], time_period=time_period
                )

            # Send the single event message with buttons
            send_telegram_message(chat_id, message_text, reply_markup=keyboard)

    elif is_valid_london_postcode(text_raw.upper()):
        postcode_norm = text_raw.upper()
        if awaiting_location_update.get(chat_id, False):
            lat, lon = geocode_postcode_to_latlon(postcode_norm)
            if lat is not None and lon is not None:
                if set_user_postcode(chat_id, postcode_norm):
                    send_telegram_message(chat_id, f"✅ Location updated to {postcode_norm}!")
                else: send_telegram_message(chat_id, "⚠️ There was an error saving your postcode. Please try again.")
            else: send_telegram_message(chat_id, f"⚠️ Couldn't find coordinates for {postcode_norm}. Please try a different London postcode.")
            awaiting_location_update[chat_id] = False
        else:
            lat, lon = geocode_postcode_to_latlon(postcode_norm)
            if not lat or not lon:
                send_telegram_message(chat_id, "Sorry, I couldn’t find coordinates for that postcode. Please try again."); return
            send_telegram_message(chat_id, f"OK, looking for events near {postcode_norm}...")
            today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
            future_date = datetime.datetime.utcnow() + datetime.timedelta(days=7)
            future_str = future_date.strftime("%Y-%m-%d")
            events = fetch_events( date_from=today_str, date_to=future_str, user_lat=lat, user_lon=lon )
            if events:
                send_event_messages( chat_id=chat_id, events=events, postcode=postcode_norm, user_lat=lat, user_lon=lon )
            else: send_telegram_message(chat_id, f"Couldn't find any events near {postcode_norm} in the next 7 days.")

    else:
        if not awaiting_location_update.get(chat_id, False):
             send_telegram_message(chat_id, "Sorry, I didn't understand that. Try /help to see available commands.")



# ---------------------------------------------------------------------
# Main Loop (Keep as is)
# ---------------------------------------------------------------------

def main():
    logger.info("Bot started. Polling for messages...")
    offset = None

    while True:
        updates = get_telegram_updates(offset)
        for upd in updates:
            update_id = upd.get('update_id')
            if update_id is not None:
                offset = update_id + 1

            # --- Check for callback query FIRST ---
            callback_query = upd.get('callback_query')
            if callback_query:
                try:
                    process_callback_query(callback_query)
                except Exception as e:
                     logger.error(f"Error processing callback query: {e}", exc_info=True)
                     # Ensure we still answer the query even if processing fails
                     query_id = callback_query.get('id')
                     if query_id: answer_callback_query(query_id)
                continue # Skip message processing if it was a callback

            # --- Process regular message ---
            message = upd.get('message')
            if message:
                try:
                    process_message(message)
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    # Optional: Notify user of error?
                    chat_id = message.get('chat', {}).get('id')
                    if chat_id:
                       try:
                           send_telegram_message(str(chat_id), "Sorry, something went wrong processing your request.")
                       except Exception as notify_e:
                            logger.error(f"Failed to send error notification to {chat_id}: {notify_e}")

        # --- Saturday Broadcast ---
        now_utc = datetime.datetime.utcnow()
        current_hour_key = f"{now_utc.date()}-{now_utc.hour}"
        # Use a simple attribute on the main function object for state
        if not hasattr(main, 'last_broadcast_hour') or main.last_broadcast_hour != current_hour_key:
            # Check if it's Saturday (weekday 5) and 9 AM UTC
            if now_utc.weekday() == 5 and now_utc.hour == 9:
                 logger.info(f"Saturday 9 AM UTC detected ({now_utc}): Triggering broadcast.")
                 try:
                     broadcast_newsletter()
                     # Mark as run for this hour ONLY on success
                     main.last_broadcast_hour = current_hour_key
                 except Exception as e:
                     logger.error(f"Error during broadcast: {e}", exc_info=True)
            # Update last checked hour regardless of broadcast attempt,
            # but only update 'last_broadcast_hour' on successful run.
            # A different variable could track last *check* if needed.
            # For simplicity, this check runs every loop iteration near 9 AM Saturday.

        # Main loop sleep
        time.sleep(1)


if __name__ == "__main__":
    main()
