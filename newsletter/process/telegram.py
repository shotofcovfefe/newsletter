import os
import time
import logging
import datetime
import json
import random
import requests
import typing as ta
from supabase import create_client
from dotenv import load_dotenv

from newsletter.utils import is_valid_london_postcode, geocode_postcode_to_latlon, haversine_distance, round_sig

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

awaiting_location_update = {}  # dict: {chat_id: bool}

# ---------------------------------------------------------------------
# Telegram Helper
# ---------------------------------------------------------------------


def get_telegram_updates(offset: ta.Optional[int] = None) -> ta.List[ta.Dict]:
    """
    Poll new updates from Telegram.
    By default, sets a 30 second timeout to allow for long-polling.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not configured.")
        return []

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": 30}
    if offset is not None:
        params["offset"] = offset

    try:
        r = requests.get(url, params=params)
        if r.status_code == 200:
            return r.json().get('result', [])
        else:
            logger.error(f"Failed to get updates: {r.text}")
            return []
    except Exception as exc:
        logger.error(f"Error getting updates: {exc}")
        return []


def send_telegram_message(chat_id: str, text: str, reply_markup: ta.Optional[ta.Dict] = None) -> bool:
    """Send a text message to a Telegram user/channel, splitting if over 4000 chars."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Telegram bot token not configured.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    max_length = 4000
    parts = [text[i:i + max_length] for i in range(0, len(text), max_length)]
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
            resp = requests.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Failed to send message part to {chat_id}: {resp.text}")
                success = False
        except Exception as exc:
            logger.error(f"Error sending message part: {exc}")
            success = False
        # Small delay between parts if splitting
        if len(parts) > 1 and i < len(parts) - 1:
            time.sleep(0.1)

    return success


def edit_telegram_message(chat_id: str, message_id: int, text: str, reply_markup: ta.Optional[ta.Dict] = None) -> bool:
    """Edit an existing message text and optionally its inline keyboard."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Telegram bot token not configured.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
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

    try:
        resp = requests.post(url, json=payload)
        if resp.status_code != 200:
             # Gracefully handle the "message is not modified" error
            if "message is not modified" in resp.text:
                logger.info(f"Message {message_id} in chat {chat_id} was not modified (content likely the same).")
                return True # Treat as success, no change needed
            logger.error(f"Failed to edit message {message_id} in chat {chat_id}: {resp.text}")
            return False
        return True
    except Exception as exc:
        logger.error(f"Error editing message: {exc}")
        return False


def answer_callback_query(callback_query_id: str) -> bool:
    """Sends an empty acknowledgement for a callback query."""
    if not TELEGRAM_BOT_TOKEN:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    try:
        resp = requests.post(url, json=payload)
        return resp.status_code == 200
    except Exception as exc:
        logger.error(f"Error answering callback query: {exc}")
        return False


# ---------------------------------------------------------------------
# Fetch Events
# ---------------------------------------------------------------------

def fetch_events(
    date_from: ta.Optional[str] = None,
    date_to: ta.Optional[str] = None,
    user_lat: ta.Optional[float] = None,
    user_lon: ta.Optional[float] = None,
    max_distance_km: float = 15.0,
    limit_per_venue: int = 1,
    overall_limit: int = 5
) -> ta.List[ta.Dict[str, ta.Any]]:
    """Fetch events from events_enriched, filtered by date and location if provided."""
    query = supabase.table("events_enriched").select("*")

    if date_from and date_to:
        if date_from == date_to:
            query = query.eq("event_date", date_from)
        else:
            query = query.gte("event_date", date_from).lt("event_date", date_to)
    elif date_from:
        query = query.gte("event_date", date_from)
    elif date_to:
        query = query.lt("event_date", date_to)

    try:
        resp = query.execute()
        data = resp.data or []
    except Exception as exc:
        logger.error(f"Error fetching events: {exc}")
        return []
    if user_lat is not None and user_lon is not None:
        for row in data:
            ev_lat = row.get("latitude")
            ev_lon = row.get("longitude")
            if ev_lat is None or ev_lon is None:
                row["distance_km"] = 9999999
            else:
                dist = haversine_distance(
                    lat1=user_lat,
                    lon1=user_lon,
                    lat2=float(ev_lat),
                    lon2=float(ev_lon)
                )
                row["distance_km"] = dist
        data = [r for r in data if r["distance_km"] <= max_distance_km]

    by_venue = {}
    for r in data:
        v_id = r.get("venue_id")
        if v_id not in by_venue:
            by_venue[v_id] = []
        if len(by_venue[v_id]) < limit_per_venue:
            by_venue[v_id].append(r)

    filtered = [event for venue_events in by_venue.values() for event in venue_events]
    if user_lat is not None and user_lon is not None:
        sorted_events = sorted(filtered, key=lambda x: x["distance_km"])
    else:
        sorted_events = sorted(filtered, key=lambda x: x["event_date"])

    return sorted_events[:overall_limit]

def fetch_random_events(days_ahead: int = 7, limit: int = 1) -> ta.List[ta.Dict[str, ta.Any]]:
    """Return up to `limit` random events in the next `days_ahead` days."""
    today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    future_str = (datetime.datetime.utcnow() + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    try:
        resp = (
            supabase.table("events_enriched")
            .select("*")
            .gte("event_date", today_str)
            .lt("event_date", future_str)
            .execute()
        )
        data = resp.data or []
    except Exception as exc:
        logger.error(f"Error fetching random events: {exc}")
        return []

    random.shuffle(data)
    return data[:limit]

# ---------------------------------------------------------------------
# Send Individual Event Messages
# ---------------------------------------------------------------------

def send_event_messages(
    chat_id: str,
    events: ta.List[ta.Dict[str, ta.Any]],
    postcode: str = "",
):
    """Send each event as an individual message with HTML formatting, including distance if available."""
    for event in events:
        message = format_events_message(events=[event], postcode=postcode)
        send_telegram_message(chat_id, message)
        time.sleep(0.2)

# ---------------------------------------------------------------------
# User Postcodes
# ---------------------------------------------------------------------

def get_user_postcode(chat_id: str) -> ta.Optional[str]:
    """Return the user's stored postcode, or None if none."""
    try:
        resp = (
            supabase.table("user_postcodes")
            .select("postcode")
            .eq("chat_id", chat_id)
            .single()
            .execute()
        )
        return resp.data["postcode"] if resp.data else None
    except:
        return None

def set_user_postcode(chat_id: str, postcode: str) -> None:
    """Store or update the user's postcode."""
    supabase.table("user_postcodes").delete().eq("chat_id", chat_id).execute()
    supabase.table("user_postcodes").insert({
        "chat_id": chat_id,
        "postcode": postcode,
        "created_date": datetime.datetime.utcnow().isoformat()
    }).execute()

# ---------------------------------------------------------------------
# Broadcast Events
# ---------------------------------------------------------------------

def broadcast_newsletter(n_events: int = 5):
    """Send weekly updates to subscribers with local or random events."""
    try:
        resp = supabase.table("telegram_subscribers").select("chat_id").execute()
        subscribers = resp.data or []
    except Exception as exc:
        logger.error(f"Error fetching subscribers for Saturday broadcast: {exc}")
        return

    for sub in subscribers:
        chat_id = sub.get("chat_id")
        if not chat_id:
            continue

        user_pc = get_user_postcode(chat_id)

        if user_pc and is_valid_london_postcode(user_pc):
            lat, lon = geocode_postcode_to_latlon(user_pc)
            if lat is not None and lon is not None:
                today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
                n_days = 7
                future_str = (datetime.datetime.utcnow() + datetime.timedelta(days=n_days)).strftime("%Y-%m-%d")
                local_events = fetch_events(date_from=today_str, date_to=future_str, user_lat=lat, user_lon=lon)
                msg_text = format_events_message(local_events, time_period=f"in the next {n_days} days", postcode=user_pc)
                send_telegram_message(chat_id, f"🎉 Saturday Update!\n\n{msg_text}")
                continue
            # Restored nuanced messaging
            random_ev = fetch_random_events(days_ahead=7, limit=n_events)
            msg_text = format_events_message(random_ev, time_period="some random events")
            send_telegram_message(chat_id, "⚠️ We had trouble using your stored postcode. Here's some random events:\n\n" + msg_text)
        else:
            random_ev = fetch_random_events(days_ahead=7, limit=n_events)
            msg_text = format_events_message(random_ev, time_period="some random events")
            send_telegram_message(chat_id, "📍 Set your location with /updatelocation for local events!\n\n" + msg_text)


def process_callback_query(callback_query: dict):
    """Handles incoming callback queries from inline keyboard buttons."""
    query_id = callback_query.get('id')
    from_user = callback_query.get('from', {}) # User who clicked
    message = callback_query.get('message') # Original message the button was attached to
    data = callback_query.get('data') # The callback_data string we defined

    if not query_id or not message or not data:
        logger.warning("Received incomplete callback query.")
        if query_id: answer_callback_query(query_id) # Still try to answer
        return

    chat_id = str(message.get('chat', {}).get('id', ''))
    message_id = message.get('message_id')

    # Always acknowledge the query first!
    answer_callback_query(query_id)

    if not chat_id or not message_id:
        logger.error(f"Could not get chat_id or message_id from callback query {query_id}")
        return

    # --- Handle specific callback data ---
    if data == "load_random":
        logger.info(f"Processing 'load_random' callback from chat {chat_id}, msg {message_id}")
        # Fetch a *new* random event
        new_events = fetch_random_events(days_ahead=7, limit=1)
        if new_events:
             # Re-define the keyboard (to keep it on the message after editing)
            keyboard = {
                "inline_keyboard": [
                    [{"text": "Load another random event 🎲", "callback_data": "load_random"}]
                ]
            }
            # Format the new event's text
            new_message_text = format_events_message(events=[new_events[0]], time_period="a random event")
            # Edit the original message
            success = edit_telegram_message(chat_id, message_id, new_message_text, reply_markup=keyboard)
            if not success:
                 logger.error(f"Failed to edit message for 'load_random' callback. Chat: {chat_id}, Msg: {message_id}")
                 # Optional: Send a temporary error message if editing fails
                 # send_telegram_message(chat_id, "Sorry, couldn't update the event just now.")
        else:
            # No more events found, edit the message to inform the user
            edit_telegram_message(chat_id, message_id, "Sorry, couldn't find another random event right now.")

    # Add elif data == "other_button": blocks here for future buttons

    else:
        logger.warning(f"Received unhandled callback data: {data} from chat {chat_id}")


# ---------------------------------------------------------------------
# Format Messages
# ---------------------------------------------------------------------

def format_events_message(events: ta.List[ta.Dict[str, ta.Any]], time_period: str = "", postcode: str = "") -> str:
    """
    Format a list of events using rich HTML formatting and the structured fields from events_enriched.
    - time_period: e.g., "today", "tomorrow", "in the next 7 days"
    - postcode: included in the header if provided
    """
    if not events:
        location_str = f"near {postcode}" if postcode else ""
        return f"No events found {time_period} {location_str}.".strip()

    lines = []
    location_str = f"near {postcode}" if postcode else ""
    if len(events) > 1:
        header = f"Here are events {time_period} {location_str}:\n".strip()

        if location_str != "" or time_period != "" :
            lines.append(header)

    for ev in events:
        name = (ev.get("pretty_event_name") or "").strip()
        venue = (ev.get("pretty_venue_name") or "").strip()
        date = (ev.get("pretty_date") or "").strip()
        url = (ev.get("venue_url") or "").strip()
        summary = (ev.get("pretty_description") or "").strip()

        if url:
            venue_html = f'<a href="{url}">{venue}</a>'
        else:
            venue_html = venue

        line = f"<b>{name}</b>\n📍 <i>{venue_html}</i>\n👉 {summary}\n📅 {date}"

        if "distance_km" in ev and postcode:
            dist_km = ev["distance_km"]
            if dist_km < 1:
                dist_m = round_sig(dist_km * 1000)
                line += f"\n🧭 <i>{dist_m:.0f}m from {postcode.upper()}</i>"
            else:
                line += f"\n🧭 <i>{dist_km:.1f} km from {postcode.upper()}</i>"
        lines.append(line + "\n")

    return "\n\n".join(lines)


# ---------------------------------------------------------------------
# Process Incoming Messages
# ---------------------------------------------------------------------

def process_message(msg: dict):
    chat_id = str(msg.get('chat', {}).get('id', ''))
    text_raw = (msg.get('text') or '').strip()

    if not chat_id:
        return

    # Update message count
    try:
        resp = supabase.table("telegram_chats").select("chat_id, message_count").eq("chat_id", chat_id).single().execute()
        if resp.data:
            new_count = resp.data["message_count"] + 1
            supabase.table("telegram_chats").update({"message_count": new_count}).eq("chat_id", chat_id).execute()
        else:
            supabase.table("telegram_chats").insert({"chat_id": chat_id, "message_count": 1}).execute()
    except Exception as exc:
        logger.error(f"Error updating message_count: {exc}")

    # Ensure user is subscribed
    try:
        if not supabase.table("telegram_subscribers").select("id").eq("chat_id", chat_id).execute().data:
            supabase.table("telegram_subscribers").insert({
                "chat_id": chat_id,
                "subscribed_date": datetime.datetime.utcnow().isoformat()
            }).execute()
    except Exception as exc:
        logger.error(f"Error adding subscriber: {exc}")

    help_text = (
        "Welcome to Niche London Events! 👋\n\n"
        "Commands:\n"
        "local - Your closest events 🧭\n"
        "best - Our top picks  🏆\n"
        "today - What's on today? 🔜\n"
        "tomorrow - What's on tomorrow? 👣\n"
        "random - I'm feeling lucky 🍀\n"
        "subscribe - Weekly roundup 📬\n"
        "unsubscribe - Stop already! 🫗\n"
        "updatelocation - Update map pinhead 📍\n"
        "Or send a valid UK postcode (e.g., E8 3PN) for local events!"
    )

    text_lower = text_raw.lower()

    if text_lower in ["/start", "/help", "help", "hello", "hi", "?"]:
        awaiting_location_update[chat_id] = False
        send_telegram_message(chat_id, help_text)

    elif text_lower in ["/updatelocation"]:
        awaiting_location_update[chat_id] = True
        send_telegram_message(chat_id, "Please send me a valid UK postcode now.")

    elif text_lower in ["/subscribe"]:
        awaiting_location_update[chat_id] = False
        send_telegram_message(chat_id, "You're now subscribed to weekly updates.")

    elif text_lower in ["/unsubscribe"]:
        awaiting_location_update[chat_id] = False
        try:
            supabase.table("telegram_subscribers").delete().eq("chat_id", chat_id).execute()
            send_telegram_message(chat_id, "You've been unsubscribed.")
        except Exception as exc:
            logger.error(f"Error unsubscribing: {exc}")
            send_telegram_message(chat_id, "Error unsubscribing. Try again later.")

    elif text_lower in ["/local"]:
        awaiting_location_update[chat_id] = False
        user_pc = get_user_postcode(chat_id)
        if not user_pc:
            send_telegram_message(chat_id, "No location set. Use /updatelocation or send a postcode.")
            return
        if not is_valid_london_postcode(postcode=user_pc):
            send_telegram_message(chat_id, f"Postcode must be valid and in London. Try /updatelocation.")
            return
        lat, lon = geocode_postcode_to_latlon(user_pc)
        if lat is None or lon is None:
            send_telegram_message(chat_id, f"Could not geocode '{user_pc}'. Try /updatelocation.")
            return
        today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        future_str = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        events = fetch_events(date_from=today_str, date_to=future_str, user_lat=lat, user_lon=lon)
        if events:
            send_event_messages(
                chat_id=chat_id,
                events=events,
                postcode=user_pc,
            )
        else:
            send_telegram_message(chat_id, "No local events found in the next 7 days.")

    elif text_lower in ["/best"]:
        awaiting_location_update[chat_id] = False
        events = fetch_random_events(days_ahead=7, limit=5)
        if events:
            send_event_messages(
                chat_id=chat_id,
                events=events
            )
        else:
            send_telegram_message(chat_id, "No events found.")

    elif text_lower in ["/today"]:
        awaiting_location_update[chat_id] = False
        user_pc = get_user_postcode(chat_id)
        if not user_pc:
            send_telegram_message(chat_id, "No location set. Use /updatelocation for today’s events.")
            return
        if not is_valid_london_postcode(user_pc):
            send_telegram_message(chat_id, f"Postcode must be valid and in London. Try /updatelocation.")
            return
        lat, lon = geocode_postcode_to_latlon(user_pc)
        if lat is None or lon is None:
            send_telegram_message(chat_id, f"Could not geocode '{user_pc}'. Try /updatelocation.")
            return
        today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        events = fetch_events(date_from=today_str, date_to=today_str, user_lat=lat, user_lon=lon)
        if events:
            send_event_messages(
                chat_id=chat_id,
                events=events,
                postcode=user_pc,
            )
        else:
            send_telegram_message(chat_id, "No events found today.")

    elif text_lower in ["/tomorrow"]:
        awaiting_location_update[chat_id] = False
        user_pc = get_user_postcode(chat_id)
        if not user_pc:
            send_telegram_message(chat_id, "No location set. Use /updatelocation for tomorrow’s events.")
            return
        if not is_valid_london_postcode(user_pc):
            send_telegram_message(chat_id, f"Postcode must be valid and in London. Try /updatelocation.")
            return
        lat, lon = geocode_postcode_to_latlon(user_pc)
        if lat is None or lon is None:
            send_telegram_message(chat_id, f"Could not geocode '{user_pc}'. Try /updatelocation.")
            return
        tomorrow = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        events = fetch_events(date_from=tomorrow, date_to=tomorrow, user_lat=lat, user_lon=lon)
        if events:
            send_event_messages(
                chat_id=chat_id,
                events=events,
                postcode=user_pc,
            )
        else:
            send_telegram_message(chat_id, "No events found tomorrow.")

    elif text_lower in ["/random"]:
        awaiting_location_update[chat_id] = False
        events = fetch_random_events(days_ahead=7, limit=1)
        if events:
            keyboard = {
                "inline_keyboard": [
                    [{"text": "Another one! 🎰", "callback_data": "load_random"}]
                ]
            }
            message_text = format_events_message(events=[events[0]], time_period="a random event")
            send_telegram_message(chat_id, message_text, reply_markup=keyboard)
        else:
            send_telegram_message(chat_id, "No random events found.")


    elif is_valid_london_postcode(text_raw.upper()):
        if awaiting_location_update.get(chat_id, False):
            set_user_postcode(chat_id, text_raw.upper())
            awaiting_location_update[chat_id] = False
            send_telegram_message(chat_id, f"Your location is now {text_raw.upper()}!")
        else:
            lat, lon = geocode_postcode_to_latlon(text_raw.upper())
            if not lat or not lon:
                send_telegram_message(chat_id, "Couldn’t geocode that postcode. Try again.")
                return
            today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
            future_str = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
            events = fetch_events(date_from=today_str, date_to=future_str, user_lat=lat, user_lon=lon)
            if events:
                send_event_messages(chat_id, events)
            else:
                send_telegram_message(chat_id, "No local events found in the next 7 days.")

    else:
        send_telegram_message(chat_id, "Unrecognized command or invalid postcode. Try /help.")

# ---------------------------------------------------------------------
# Main Loop
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
                    # chat_id = message.get('chat', {}).get('id')
                    # if chat_id:
                    #    send_telegram_message(str(chat_id), "Sorry, something went wrong processing your request.")

        # --- Saturday Broadcast ---
        now_utc = datetime.datetime.utcnow()
        # Check if it's Saturday (5) and 9 AM UTC and if we haven't already run it this hour
        # (Simple check to prevent multiple runs if loop is fast)
        current_hour_key = f"{now_utc.date()}-{now_utc.hour}"
        if not hasattr(main, 'last_broadcast_hour') or main.last_broadcast_hour != current_hour_key:
            if now_utc.weekday() == 5 and now_utc.hour == 9:
                 logger.info("Saturday 9 AM UTC: Broadcasting events.")
                 try:
                     broadcast_newsletter()
                     main.last_broadcast_hour = current_hour_key # Mark as run for this hour
                 except Exception as e:
                     logger.error(f"Error during broadcast: {e}", exc_info=True)
                 # Sleep longer after broadcast attempt to avoid immediate re-check if it failed
                 time.sleep(60) # Sleep for a minute after check/run

        time.sleep(1) # Reduced sleep time for better responsiveness, adjust as needed


if __name__ == "__main__":
    main()