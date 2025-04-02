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
# Telegram Helper: Polling & Sending Messages
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
    """
    Send a text message to a Telegram user/channel.
    Splits into chunks if over 4000 chars, to avoid message length errors.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Telegram bot token not configured.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    max_length = 4000
    parts = [text[i:i + max_length] for i in range(0, len(text), max_length)]
    success = True

    for part in parts:
        payload = {
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "HTML"
        }
        try:
            resp = requests.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Failed to send message to {chat_id}: {resp.text}")
                success = False
            else:
                logger.info(f"Sent message to chat {chat_id}")
        except Exception as exc:
            logger.error(f"Error sending message: {exc}")
            success = False

    return success

# ---------------------------------------------------------------------
# Broadcast events
# ---------------------------------------------------------------------

def broadcast_newsletter():
    """
    For each subscriber in telegram_subscribers:
      1) Check if they have a postcode in user_postcodes
      2) If yes, fetch local events and send them
      3) If not, either fetch random events or prompt them to update location
    """
    # 1) Grab all subscribers
    try:
        resp = supabase.table("telegram_subscribers").select("chat_id").execute()
        subscribers = resp.data or []
    except Exception as exc:
        logger.error(f"Error fetching subscribers for Saturday broadcast: {exc}")
        return

    # 2) For each subscriber, fetch their postcode
    for sub in subscribers:
        chat_id = sub.get("chat_id")
        if not chat_id:
            continue

        user_pc = get_user_postcode(chat_id)

        if user_pc:
            # Validate & geocode
            if is_valid_uk_postcode(user_pc):
                lat, lon = geocode_postcode_to_latlon(user_pc)
                if lat is not None and lon is not None:
                    # 3a) Fetch local events
                    local_events = fetch_local_events(lat, lon, max_distance_km=15.0, days_ahead=7)
                    msg_text = format_local_events_message(local_events, user_pc)
                    send_telegram_message(chat_id, f"🎉 Saturday Update!\n\n{msg_text}")
                    continue
            # If postcode is invalid or geocode fails, we fall back to random
            random_ev = fetch_random_events(days_ahead=7)
            msg_text = format_random_events_message(random_ev)
            send_telegram_message(chat_id,
                "⚠️ We had trouble using your stored postcode. Here's some random events instead!\n\n" + msg_text
            )
        else:
            # 3b) No postcode => random or a location prompt
            random_ev = fetch_random_events(days_ahead=7)
            msg_text = format_random_events_message(random_ev)
            send_telegram_message(chat_id,
                "📍 You haven't set a location yet! Use /updatelocation to get local events.\n\n" + msg_text
            )

# ---------------------------------------------------------------------
# user_postcodes table
# ---------------------------------------------------------------------

def get_user_postcode(chat_id: str) -> ta.Optional[str]:
    """Return the user's currently stored postcode, or None if none."""
    try:
        resp = (
            supabase.table("user_postcodes")
            .select("postcode")
            .eq("chat_id", chat_id)
            .single()
            .execute()
        )
        if resp.data:
            return resp.data["postcode"]
    except:
        pass
    return None

def set_user_postcode(chat_id: str, postcode: str) -> None:
    """
    Store or update the user_postcodes row for this user.
    We'll do a simple approach: delete any old row, then insert a new one.
    """
    # Remove old record, if any
    supabase.table("user_postcodes").delete().eq("chat_id", chat_id).execute()
    # Insert new
    supabase.table("user_postcodes").insert({
        "chat_id": chat_id,
        "postcode": postcode,
        "created_date": datetime.datetime.utcnow().isoformat()
    }).execute()

# ---------------------------------------------------------------------
# Fetch Local or Random Events from events_enriched
# ---------------------------------------------------------------------

def fetch_local_events(
    user_lat: float,
    user_lon: float,
    max_distance_km: float = 15.0,
    days_ahead: int = 7
) -> ta.List[ta.Dict[str, ta.Any]]:
    """
    1) Query events_enriched for events in the next `days_ahead` days
    2) Compute distance from user_lat/lon
    3) Filter out events beyond `max_distance_km`
    4) Limit to 2 events per venue
    5) Return top 10 by ascending distance
    """
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
        logger.error(f"Error fetching local events: {exc}")
        return []

    # For each event, compute distance
    for row in data:
        ev_lat = row.get("latitude")
        ev_lon = row.get("longitude")
        if ev_lat is None or ev_lon is None:
            row["distance_km"] = 9999999
        else:
            dist = haversine_distance(user_lat, user_lon, float(ev_lat), float(ev_lon))
            row["distance_km"] = dist

    # Filter out beyond max_distance
    filtered = [r for r in data if r["distance_km"] <= max_distance_km]

    # Group by venue to limit 2 each
    final = []
    by_venue_count = {}
    for r in sorted(filtered, key=lambda x: x["distance_km"]):
        v_id = r.get("venue_id")
        if by_venue_count.get(v_id, 0) < 2:
            final.append(r)
            by_venue_count[v_id] = by_venue_count.get(v_id, 0) + 1

    return final[:10]


def fetch_random_events(days_ahead: int = 7, limit: int = 1) -> ta.List[ta.Dict[str, ta.Any]]:
    """
    Return up to `limit` random events in the next `days_ahead` days.
    """
    today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    future_str = (
        datetime.datetime.utcnow() + datetime.timedelta(days=days_ahead)
    ).strftime("%Y-%m-%d")

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

    # Return only the first `limit` events
    return data[:limit]

# ---------------------------------------------------------------------
# Format messages
# ---------------------------------------------------------------------

def format_local_events_message(events: ta.List[ta.Dict[str, ta.Any]], postcode: str) -> str:
    """
    Return a textual summary of up to 10 local events, showing distance.
    """
    if not events:
        return f"No local events found near {postcode} in the next 7 days."
    lines = [f"Here are events near {postcode} in the next 7 days:\n"]
    for ev in events:
        desc = ev.get("description", "").strip()
        dist_km = ev.get("distance_km", 0.0)
        lines.append(f"{desc}\n📏 {dist_km:.1f} km away\n\n")
    return "\n".join(lines)

def format_random_events_message(events: ta.List[ta.Dict[str, ta.Any]]) -> str:
    """
    Return a textual summary of up to 10 random events (no distance).
    """
    if not events:
        return "No upcoming events found for the next 7 days."
    lines = ["Here are some random events in the next 7 days:\n"]
    for ev in events:
        desc = ev.get("description", "").strip()
        lines.append(f"{desc}\n\n")
    return "\n".join(lines)

# ---------------------------------------------------------------------
# Process incoming user messages
# ---------------------------------------------------------------------

def process_message(msg: dict):
    chat_id = str(msg.get('chat', {}).get('id', ''))
    text_raw = (msg.get('text') or '').strip()

    if not chat_id:
        return

    try:
        # Check if a row exists
        resp = supabase.table("telegram_chats").select("chat_id, message_count").eq("chat_id", chat_id).single().execute()
        if resp.data:
            current_count = resp.data["message_count"]
            new_count = current_count + 1
            supabase.table("telegram_chats") \
                .update({"message_count": new_count}) \
                .eq("chat_id", chat_id) \
                .execute()
        else:
            # No row => insert
            supabase.table("telegram_chats").insert({
                "chat_id": chat_id,
                "message_count": 1
            }).execute()
    except Exception as exc:
        # If we fail for any reason, just log it and continue
        logger.error(f"Error updating telegram_chats message_count for {chat_id}: {exc}")

    # Ensure user is in 'telegram_subscribers' (like your previous logic)
    try:
        existing = supabase.table("telegram_subscribers").select("id").eq("chat_id", chat_id).execute()
        if not existing.data:
            supabase.table("telegram_subscribers").insert({
                "chat_id": chat_id,
                "subscribed_date": datetime.datetime.utcnow().isoformat()
            }).execute()
            logger.info(f"New subscriber added: {chat_id}")
    except Exception as exc:
        logger.error(f"Error adding subscriber: {exc}")

    # Our new help text (no references to pre-prepared newsletters)
    help_text = (
        "Welcome to Niche London Events! 👋\n\n"
        "I find local, low-key London events!\n\n"
        "Commands:\n"
        "local - Your closest events 🧭\n"
        "best - Our top picks  🏆\n"
        "today - What's on today? 🔜\n"
        "tomorrow - What's on tomorrow? 👣\n"
        "random - I'm feeling lucky 🍀\n"
        "subscribe - Weekly roundup 📬\n"
        "unsubscribe - Stop already! 🫗\n"  
        "updatelocation - Update map pinhead 📍\n"
        "Or just send me a valid UK postcode (e.g., E8 3PN) to get local events instantly!"
    )

    text_lower = text_raw.lower()

    if text_lower in ["/start", "/help", "help", "hello", "hi", "?"]:
        awaiting_location_update[chat_id] = False
        send_telegram_message(chat_id, help_text)

    elif text_lower == '/updatelocation':
        # We set a flag indicating the next valid postcode is "officially" stored
        awaiting_location_update[chat_id] = True
        send_telegram_message(chat_id, "Please send me a valid UK postcode now (it will become your home location).")

    elif text_lower == "/subscribe":
        awaiting_location_update[chat_id] = False
        send_telegram_message(chat_id, "You're now subscribed. You'll receive weekly event updates (in the future).")

    elif text_lower == "/unsubscribe":
        awaiting_location_update[chat_id] = False
        try:
            supabase.table("telegram_subscribers").delete().eq("chat_id", chat_id).execute()
            send_telegram_message(chat_id, "You've been unsubscribed from weekly updates.")
        except Exception as exc:
            logger.error(f"Error unsubscribing: {exc}")
            send_telegram_message(chat_id, "Error unsubscribing. Please try again later.")

    elif text_lower == "/local":
        awaiting_location_update[chat_id] = False
        user_pc = get_user_postcode(chat_id)
        if not user_pc:
            send_telegram_message(chat_id, "📍 Please set your location first using /updatelocation.")
            return

        lat, lon = geocode_postcode_to_latlon(user_pc)
        if lat is None or lon is None:
            send_telegram_message(chat_id, f"Couldn't find your location '{user_pc}'. Try /updatelocation again.")
            return

        local_events = fetch_local_events(lat, lon)
        msg_text = format_local_events_message(local_events, user_pc)
        send_telegram_message(chat_id, msg_text)

    elif text_lower == "/best":
        awaiting_location_update[chat_id] = False
        events = fetch_random_events(days_ahead=7, limit=10)
        msg_text = format_random_events_message(events)
        send_telegram_message(chat_id, "🏆 Our top event picks this week:\n\n" + msg_text)

    elif text_lower == "/today":
        awaiting_location_update[chat_id] = False
        today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        try:
            resp = (
                supabase.table("events_enriched")
                .select("*")
                .eq("event_date", today_str)
                .execute()
            )
            events_today = resp.data or []
        except Exception as exc:
            logger.error(f"Error fetching today's events: {exc}")
            events_today = []

        msg_text = format_random_events_message(events_today)
        send_telegram_message(chat_id, f"🔜 Events happening today ({today_str}):\n\n" + msg_text)

    elif text_lower == "/tomorrow":
        awaiting_location_update[chat_id] = False
        tomorrow_str = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        try:
            resp = (
                supabase.table("events_enriched")
                .select("*")
                .eq("event_date", tomorrow_str)
                .execute()
            )
            events_tomorrow = resp.data or []
        except Exception as exc:
            logger.error(f"Error fetching tomorrow's events: {exc}")
            events_tomorrow = []

        msg_text = format_random_events_message(events_tomorrow)
        send_telegram_message(chat_id, f"👣 Events happening tomorrow ({tomorrow_str}):\n\n" + msg_text)

    elif text_lower == "/random":
        awaiting_location_update[chat_id] = False
        # Fetch random events (ignore location)
        events = fetch_random_events(days_ahead=7, limit=1)
        msg_text = format_random_events_message(events)
        send_telegram_message(chat_id, msg_text)

    elif is_valid_uk_postcode(text_raw.upper()):
        # The user sent a valid postcode
        if awaiting_location_update.get(chat_id, False):
            # This user *did* type /updatelocation previously, so store it
            set_user_postcode(chat_id, text_raw.upper())
            # Reset the flag
            awaiting_location_update[chat_id] = False
            send_telegram_message(chat_id, f"Your location was updated to {text_raw.upper()}!")
        else:
            # They didn't do /updatelocation => treat it as an ad-hoc request
            lat, lon = geocode_postcode_to_latlon(text_raw.upper())
            if not lat or not lon:
                send_telegram_message(chat_id, "Couldn't geocode that postcode. Please try again.")
                return

            local_events = fetch_local_events(lat, lon)
            msg_text = format_local_events_message(local_events, text_raw.upper())
            send_telegram_message(chat_id, msg_text)

    else:
        send_telegram_message(chat_id, "Unrecognized command or invalid postcode. Try /help.")

# ---------------------------------------------------------------------
# Main Bot Loop
# ---------------------------------------------------------------------

def main():
    logger.info("Bot started. Polling for commands and user messages...")
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
            logger.info("Detected Saturday 9 AM UTC -> broadcasting dynamic events to subscribers.")
            broadcast_newsletter()

            # Sleep an hour so we don't spam repeated broadcasts during the same hour
            time.sleep(3600)

        time.sleep(3)


if __name__ == "__main__":
    main()
