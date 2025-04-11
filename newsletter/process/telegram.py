import os
import time
import logging
import datetime
import random
import requests
import typing as ta
from supabase import create_client
from dotenv import load_dotenv

from newsletter.utils import is_valid_uk_postcode, geocode_postcode_to_latlon, haversine_distance

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


def send_telegram_message(chat_id: str, text: str) -> bool:
    """Send a text message to a Telegram user/channel, splitting if over 4000 chars."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Telegram bot token not configured.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    max_length = 4000
    parts = [text[i:i + max_length] for i in range(0, len(text), max_length)]
    success = True

    for part in parts:
        payload = {"chat_id": chat_id, "text": part, "parse_mode": "HTML"}
        try:
            resp = requests.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Failed to send message to {chat_id}: {resp.text}")
                success = False
        except Exception as exc:
            logger.error(f"Error sending message: {exc}")
            success = False

    return success

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
                dist = haversine_distance(user_lat, user_lon, float(ev_lat), float(ev_lon))
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

def send_event_messages(chat_id: str, events: ta.List[ta.Dict[str, ta.Any]]):
    """Send each event as an individual message with HTML formatting, including distance if available."""
    for event in events:
        message = format_events_message(events=[event])
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

        if user_pc and is_valid_uk_postcode(user_pc):
            lat, lon = geocode_postcode_to_latlon(user_pc)
            if lat is not None and lon is not None:
                today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
                future_str = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
                local_events = fetch_events(date_from=today_str, date_to=future_str, user_lat=lat, user_lon=lon)
                msg_text = format_events_message(local_events, time_period="in the next 7 days", postcode=user_pc)
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

    location_str = f"near {postcode}" if postcode else ""
    header = f"Here are events {time_period} {location_str}:\n".strip()

    lines = []
    if not location_str or time_period:
        lines.append(header)

    for ev in events:
        name = ev.get("pretty_event_name", "").strip()
        venue = ev.get("pretty_venue_name", "").strip()
        date = ev.get("pretty_date", "").strip()
        summary = ev.get("pretty_description", "").strip()

        line = f"<b>{name}</b>\n📍 <i>{venue}</i> - <u>{date}</u>\n{summary}"

        if "distance_km" in ev:
            dist_km = ev["distance_km"]
            line += f"\n📏 <i>{dist_km:.1f} km away</i>"

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
        if not is_valid_uk_postcode(user_pc):
            send_telegram_message(chat_id, f"Your postcode '{user_pc}' isn't valid. Try /updatelocation.")
            return
        lat, lon = geocode_postcode_to_latlon(user_pc)
        if lat is None or lon is None:
            send_telegram_message(chat_id, f"Could not geocode '{user_pc}'. Try /updatelocation.")
            return
        today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        future_str = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        events = fetch_events(date_from=today_str, date_to=future_str, user_lat=lat, user_lon=lon)
        if events:
            send_event_messages(chat_id, events)
        else:
            send_telegram_message(chat_id, "No local events found in the next 7 days.")

    elif text_lower in ["/best"]:
        awaiting_location_update[chat_id] = False
        events = fetch_random_events(days_ahead=7, limit=5)
        if events:
            send_event_messages(chat_id, events)
        else:
            send_telegram_message(chat_id, "No events found.")

    elif text_lower in ["/today"]:
        awaiting_location_update[chat_id] = False
        user_pc = get_user_postcode(chat_id)
        if not user_pc:
            send_telegram_message(chat_id, "No location set. Use /updatelocation for today’s events.")
            return
        if not is_valid_uk_postcode(user_pc):
            send_telegram_message(chat_id, f"Your postcode '{user_pc}' isn't valid. Try /updatelocation.")
            return
        lat, lon = geocode_postcode_to_latlon(user_pc)
        if lat is None or lon is None:
            send_telegram_message(chat_id, f"Could not geocode '{user_pc}'. Try /updatelocation.")
            return
        today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        events = fetch_events(date_from=today_str, date_to=today_str, user_lat=lat, user_lon=lon)
        if events:
            send_event_messages(chat_id, events)
        else:
            send_telegram_message(chat_id, "No events found today.")

    elif text_lower in ["/tomorrow"]:
        awaiting_location_update[chat_id] = False
        user_pc = get_user_postcode(chat_id)
        if not user_pc:
            send_telegram_message(chat_id, "No location set. Use /updatelocation for tomorrow’s events.")
            return
        if not is_valid_uk_postcode(user_pc):
            send_telegram_message(chat_id, f"Your postcode '{user_pc}' isn't valid. Try /updatelocation.")
            return
        lat, lon = geocode_postcode_to_latlon(user_pc)
        if lat is None or lon is None:
            send_telegram_message(chat_id, f"Could not geocode '{user_pc}'. Try /updatelocation.")
            return
        tomorrow = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        events = fetch_events(date_from=tomorrow, date_to=tomorrow, user_lat=lat, user_lon=lon)
        if events:
            send_event_messages(chat_id, events)
        else:
            send_telegram_message(chat_id, "No events found tomorrow.")

    elif text_lower in ["/random"]:
        awaiting_location_update[chat_id] = False
        events = fetch_random_events(days_ahead=7, limit=1)
        if events:
            send_event_messages(chat_id, events)
        else:
            send_telegram_message(chat_id, "No events found.")

    elif is_valid_uk_postcode(text_raw.upper()):
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
            message = upd.get('message')
            if message:
                process_message(message)

        now_utc = datetime.datetime.utcnow()
        if now_utc.weekday() == 5 and now_utc.hour == 9:
            logger.info("Saturday 9 AM UTC: Broadcasting events.")
            broadcast_newsletter()
            time.sleep(3600)

        time.sleep(3)

if __name__ == "__main__":
    main()