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


def get_latest_newsletter() -> ta.Optional[ta.Dict[str, ta.Any]]:
    """
    Retrieves the latest newsletter entry from the database that was created in the last day.
    Returns None if no recent newsletter is found.
    """
    one_day_ago = (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat()

    try:
        response = (
            supabase
            .table("newsletter")
            .select("*")
            .gte("created_date", one_day_ago)
            .order("created_date", desc=True)
            .limit(1)
            .execute()
        )

        data = response.data
        if data and len(data) > 0:
            logger.info(f"Retrieved latest newsletter with ID: {data[0]['id']}")
            return data[0]
        else:
            logger.info("No newsletter found from the last day.")
            return None

    except Exception as exc:
        logger.error(f"Failed to retrieve latest newsletter: {exc}")
        return None


def send_telegram_message(chat_id: str, text: str) -> bool:
    """
    Sends a message to a Telegram chat using the Telegram Bot API.
    Returns True if successful, False otherwise.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Telegram bot token not configured.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Telegram messages have a 4096 character limit
    # If the message is longer, we'll split it into multiple messages
    max_length = 4000  # Slightly less than the actual limit for safety

    # Split the message if it's too long
    message_parts = [text[i:i + max_length] for i in range(0, len(text), max_length)]

    success = True
    for part in message_parts:
        payload = {
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "HTML"
        }

        try:
            response = requests.post(url, json=payload)
            if response.status_code != 200:
                logger.error(f"Failed to send Telegram message: {response.text}")
                success = False
            else:
                logger.info(f"Telegram message sent successfully to chat {chat_id}.")
        except Exception as exc:
            logger.error(f"Error sending Telegram message: {exc}")
            success = False

    return success


def derive_newsletter_index() -> int:
    response = supabase.table("newsletter_events").select("newsletter_id, event_id").execute()

    newsletter_events = defaultdict(set)
    for row in response.data:
        newsletter_events[row["newsletter_id"]].add(row["event_id"])

    unique_event_sets = {frozenset(event_set) for event_set in newsletter_events.values()}
    return len(unique_event_sets)


def format_newsletter_for_telegram(newsletter: ta.Dict[str, ta.Any]) -> str:
    """
    Formats the newsletter content for Telegram.
    Basic HTML formatting is supported.
    """
    body = newsletter.get("body", "")

    issue_number = derive_newsletter_index()

    # Add a header
    header = f"<b>📅 EVENTS NEWSLETTER VOL. #{issue_number}</b>\n\n"

    # Format the body - replace newlines with HTML line breaks if needed
    formatted_text = header + body

    return formatted_text


def get_telegram_updates(offset: int = None) -> ta.List[ta.Dict]:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset

    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json().get('result', [])
        else:
            logger.error(f"Failed to get updates: {response.text}")
            return []
    except Exception as exc:
        logger.error(f"Error getting updates: {exc}")
        return []


def process_message(message: ta.Dict) -> None:
    chat_id = message.get('chat', {}).get('id')
    text = message.get('text', '').lower()

    if not chat_id:
        return

    try:
        response = (
            supabase
            .table("telegram_subscribers")
            .select("*")
            .eq("chat_id", str(chat_id))
            .execute()
        )

        if not response.data:
            supabase.table("telegram_subscribers").insert({
                "chat_id": str(chat_id),
                "subscribed_date": datetime.datetime.now().isoformat()
            }).execute()
            logger.info(f"Added new subscriber: {chat_id}")
    except Exception as exc:
        logger.error(f"Error managing subscription: {exc}")

    if text.lower() in ['/start', '/help', 'hello', 'hi', 'help', '?']:
        welcome_msg = (
            "Welcome to Niche London Events! 👋\n\n"
            "I curate a weekly newsletter about local and low-key London events. No, you won't find these on Time Out.\n"
            "Here are my commands:\n"
            "/latest - Get the latest newsletter\n"
            "/subscribe - Subscribe to receive newsletters\n"
            "/unsubscribe - Unsubscribe from newsletters"
        )
        send_telegram_message(chat_id, welcome_msg)

    elif text == '/latest':
        newsletter = get_latest_newsletter()
        if newsletter:
            formatted_message = format_newsletter_for_telegram(newsletter)
            send_telegram_message(chat_id, formatted_message)
        else:
            send_telegram_message(chat_id, "Sorry, I don't have any recent newsletters to share.")

    elif text == '/subscribe':
        send_telegram_message(chat_id, "You've been subscribed to receive event newsletters! 🎉")

    elif text == '/unsubscribe':
        try:
            supabase.table("telegram_subscribers").delete().eq("chat_id", str(chat_id)).execute()
            send_telegram_message(chat_id,
                                  "You've been unsubscribed from the newsletter. You can subscribe again anytime with /subscribe.")
        except Exception as exc:
            logger.error(f"Error unsubscribing: {exc}")
            send_telegram_message(chat_id, "There was an error processing your request. Please try again later.")

    else:
        send_telegram_message(chat_id,
                              "I don't understand that command. Try /latest to get the latest newsletter or /subscribe to subscribe.")


def broadcast_latest_newsletter():
    """
    Send the latest newsletter to all subscribers.
    """
    newsletter = get_latest_newsletter()
    if not newsletter:
        logger.info("No recent newsletter found. Not sending broadcast.")
        return

    # Format the newsletter for Telegram
    formatted_message = format_newsletter_for_telegram(newsletter)

    # Get all subscribers
    try:
        response = supabase.table("telegram_subscribers").select("chat_id").execute()
        subscribers = response.data

        if not subscribers:
            logger.info("No subscribers found. Not sending broadcast.")
            return

        logger.info(f"Broadcasting newsletter to {len(subscribers)} subscribers.")

        # Send to each subscriber
        for subscriber in subscribers:
            chat_id = subscriber.get("chat_id")
            if chat_id:
                success = send_telegram_message(chat_id, formatted_message)
                if not success:
                    logger.error(f"Failed to send newsletter to {chat_id}")
                # Avoid hitting Telegram's rate limits
                time.sleep(0.1)

        logger.info("Broadcast complete.")
    except Exception as exc:
        logger.error(f"Error broadcasting newsletter: {exc}")


def main():
    """
    Main function to run the bot. It can work in two modes:
    1. Interactive mode: Process incoming messages from users
    2. Broadcast mode: Send the latest newsletter to all subscribers
    """
    # # Check if we should run in broadcast mode
    # TODO: broadcast mode true / need checks in place to ensure we don't spam users
    # if os.getenv("BROADCAST_MODE", "").lower() == "true":
    #     logger.info("Running in broadcast mode.")
    #     broadcast_latest_newsletter()
    #     return

    # Otherwise, run in interactive mode
    logger.info("Running in interactive mode. Listening for messages...")

    # Keep track of the last update ID we've processed
    last_update_id = None

    # Main polling loop
    while True:
        try:
            updates = get_telegram_updates(last_update_id)

            for update in updates:
                update_id = update.get('update_id')

                # Update the last_update_id to acknowledge this update
                if update_id:
                    last_update_id = update_id + 1

                message = update.get('message')
                if message:
                    process_message(message)

            # Sleep briefly to avoid hammering the API
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            break
        except Exception as exc:
            logger.error(f"Error in main loop: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    main()