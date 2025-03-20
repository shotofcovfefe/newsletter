import os
import time
import logging
import datetime
import requests
import typing as ta
from collections import defaultdict
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------------------------------------
# Newsletter Data Retrieval/Storage
# ---------------------------------------------------------------------

def get_newsletter_by_id(nl_id: int) -> ta.Optional[ta.Dict[str, ta.Any]]:
    """Fetch a single newsletter by primary key."""
    try:
        resp = (
            supabase.table("newsletter")
            .select("*")
            .eq("id", nl_id)
            .single()
            .execute()
        )
        return resp.data
    except Exception as exc:
        logger.error(f"Failed to fetch newsletter {nl_id}: {exc}")
        return None

def get_latest_newsletter(is_dev: bool = False, lookback_days: int = 7) -> ta.Optional[ta.Dict[str, ta.Any]]:
    """
    Returns the most recently created newsletter within `lookback_days`.
    Defaults to `is_dev=False` (production).
    """
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=lookback_days)).isoformat()
    try:
        resp = (
            supabase.table("newsletter")
            .select("*")
            .eq("is_dev", is_dev)
            .gte("created_date", cutoff)
            .order("created_date", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None
    except Exception as exc:
        logger.error(f"Failed to retrieve latest newsletter (is_dev={is_dev}): {exc}")
        return None

def newsletter_already_broadcast(nl_id: int) -> bool:
    """
    Checks if newsletter has already been broadcast
    by looking for a record in 'newsletter_broadcast'.
    """
    try:
        resp = (
            supabase.table("newsletter_broadcast")
            .select("id")
            .eq("newsletter_id", nl_id)
            .execute()
        )
        return bool(resp.data)  # True if any record
    except Exception as exc:
        logger.error(f"Error checking broadcast history: {exc}")
        return True  # fail-safe => treat as already broadcast

def mark_newsletter_broadcasted(nl_id: int, success: bool) -> None:
    """
    Inserts a record to mark that we broadcasted the newsletter (success/fail).
    """
    try:
        supabase.table("newsletter_broadcast").insert({
            "newsletter_id": nl_id,
            "sent_at": datetime.datetime.utcnow().isoformat(),
            "success": success
        }).execute()
        logger.info(f"Marked newsletter {nl_id} as broadcasted (success={success}).")
    except Exception as exc:
        logger.error(f"Failed to mark newsletter broadcast: {exc}")

# ---------------------------------------------------------------------
# Telegram Logic
# ---------------------------------------------------------------------

def send_telegram_message(chat_id: str, text: str) -> bool:
    """Send a message to a Telegram user/channel."""
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

def derive_newsletter_index() -> int:
    """
    Count how many distinct sets of event_ids have been used across *production* newsletters.
    """
    try:
        resp_newsletters = (
            supabase.table("newsletter")
            .select("id")
            .eq("is_dev", False)
            .execute()
        )
        production_ids = {row["id"] for row in (resp_newsletters.data or [])}
        if not production_ids:
            return 0

        resp_events = (
            supabase.table("newsletter_events")
            .select("newsletter_id, event_id")
            .in_("newsletter_id", list(production_ids))
            .execute()
        )

        newsletter_events = defaultdict(set)
        for row in (resp_events.data or []):
            newsletter_events[row["newsletter_id"]].add(row["event_id"])

        unique_event_sets = {frozenset(s) for s in newsletter_events.values()}
        return len(unique_event_sets)
    except Exception as exc:
        logger.error(f"Error deriving newsletter index: {exc}")
        return 0

def format_newsletter_for_telegram(nl: ta.Dict[str, ta.Any]) -> str:
    """Adds a heading (with newsletter index) above the body text."""
    body = nl.get("body", "")
    issue_number = derive_newsletter_index()
    header = f"<b>📅 EVENTS NEWSLETTER VOL. #{issue_number}</b>\n\n"
    return header + body

def broadcast_production_newsletter():
    """
    1) Grab the latest production newsletter
    2) If not broadcast, broadcast it to all subscribers
    3) Mark as broadcast in DB
    """
    newsletter = get_latest_newsletter(is_dev=False)
    if not newsletter:
        logger.info("No recent production newsletter found. Skipping auto-broadcast.")
        return

    nl_id = newsletter["id"]
    if newsletter_already_broadcast(nl_id):
        logger.info(f"Newsletter {nl_id} was already broadcast. Skipping.")
        return

    logger.info(f"Broadcasting newsletter {nl_id} to all subscribers...")
    text = format_newsletter_for_telegram(newsletter)
    success = True

    try:
        resp = supabase.table("telegram_subscribers").select("chat_id").execute()
        subscribers = resp.data or []
        for sub in subscribers:
            c_id = sub.get("chat_id")
            if c_id:
                ok = send_telegram_message(c_id, text)
                if not ok:
                    success = False
            time.sleep(0.1)  # small rate-limit delay
    except Exception as exc:
        logger.error(f"Error during broadcast: {exc}")
        success = False

    mark_newsletter_broadcasted(nl_id, success)

# ---------------------------------------------------------------------
# Handling Telegram Updates (Commands)
# ---------------------------------------------------------------------

def get_telegram_updates(offset: ta.Optional[int] = None) -> ta.List[ta.Dict]:
    """Poll new updates from Telegram."""
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

def process_message(msg: dict):
    chat_id = str(msg.get('chat', {}).get('id', ''))
    text = (msg.get('text') or '').lower().strip()

    if not chat_id:
        return

    # Ensure user is subscribed (or gets added)
    try:
        existing = (
            supabase.table("telegram_subscribers")
            .select("id")
            .eq("chat_id", chat_id)
            .execute()
        )
        if not existing.data:
            supabase.table("telegram_subscribers").insert({
                "chat_id": chat_id,
                "subscribed_date": datetime.datetime.utcnow().isoformat()
            }).execute()
            logger.info(f"New subscriber added: {chat_id}")
    except Exception as exc:
        logger.error(f"Error adding subscriber: {exc}")

    # Commands:
    if text in ['/start', '/help', 'hello', 'hi', '?']:
        help_text = (
            "Welcome to Niche London Events! 👋\n\n"
            "I curate a weekly newsletter about local and low-key London events. No, you won't find these on Time Out.\n"
            "Here are my commands:\n"
            "/latest - Get the latest newsletter\n"
            "/subscribe - Subscribe to receive newsletters\n"
            "/unsubscribe - Unsubscribe from newsletters"
        )
        send_telegram_message(chat_id, help_text)

    elif text == '/latest':
        newsletter = get_latest_newsletter(is_dev=False)
        if newsletter:
            msg_text = format_newsletter_for_telegram(newsletter)
            send_telegram_message(chat_id, msg_text)
        else:
            send_telegram_message(chat_id, "No recent production newsletter found.")

    elif text == '/latest-dev':
        # Hidden command for latest newsletter
        newsletter = get_latest_newsletter(is_dev=True)
        if newsletter:
            msg_text = format_newsletter_for_telegram(newsletter)
            send_telegram_message(chat_id, msg_text)
        else:
            send_telegram_message(chat_id, "No recent dev newsletter found.")

    elif text == '/subscribe':
        send_telegram_message(chat_id, "You are subscribed. You'll receive the weekly broadcast.")

    elif text == '/unsubscribe':
        try:
            supabase.table("telegram_subscribers").delete().eq("chat_id", chat_id).execute()
            send_telegram_message(chat_id, "You've been unsubscribed.")
        except Exception as exc:
            logger.error(f"Error unsubscribing: {exc}")
            send_telegram_message(chat_id, "Error unsubscribing. Please try again later.")
    else:
        send_telegram_message(chat_id, "Unrecognized command. Try /latest or /help.")

# ---------------------------------------------------------------------
# Main: Always Running, Weekly Broadcast at Saturday 9 AM UTC
# ---------------------------------------------------------------------

def main():
    logger.info("Bot started. Always running, polling for commands...")
    offset = None  # track the last update_id

    while True:
        # 1) Poll for new updates
        updates = get_telegram_updates(offset)
        for upd in updates:
            update_id = upd.get('update_id')
            if update_id is not None:
                offset = update_id + 1

            message = upd.get('message')
            if message:
                process_message(message)

        # 2) Check if it's Saturday at 9 AM UTC => broadcast
        now_utc = datetime.datetime.utcnow()
        # weekday(): Monday=0 ... Sunday=6, so Saturday=5
        if now_utc.weekday() == 5 and now_utc.hour == 9:
            # Attempt broadcast. If the newsletter is already broadcast, no duplicate is sent.
            logger.info("Detected Saturday 9 AM UTC. Attempting auto-broadcast...")
            broadcast_production_newsletter()

            # Sleep for a while so we don't keep re-checking every loop within 9:00 hour
            # (The DB also prevents duplicates, but let's avoid spamming logs or repeated checks)
            time.sleep(3600)  # 1 hour

        time.sleep(3)  # short delay to prevent busy looping

if __name__ == "__main__":
    main()
