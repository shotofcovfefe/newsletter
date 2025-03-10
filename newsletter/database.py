import os
import logging
import typing as t
from dotenv import load_dotenv
from supabase import create_client

from newsletter.types import Event

load_dotenv()
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

logger.info(f"Supabase URL: {SUPABASE_URL}")
if SUPABASE_KEY:
    logger.info(f"Supabase Key (partial): {SUPABASE_KEY[:5]}...")

# Create the Supabase client once at import time
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def email_exists(message_id: str) -> bool:
    """
    Returns True if an email with the given message_id is already stored in the database.
    """
    try:
        result = (
            supabase.table("emails")
            .select("message_id")
            .eq("message_id", message_id)
            .execute()
        )
        return len(result.data) > 0
    except Exception as e:
        logger.error(f"Error checking email existence for {message_id}: {e}")
        # On error, default to False so we do not skip a potentially valid email.
        return False


def save_email(email_data: t.Dict[str, t.Any]) -> None:
    """
    Saves the given email data to the Supabase 'emails' table.
    """
    data = {
        "message_id": email_data["message_id"],
        "sender": email_data["sender"],
        "subject": email_data["subject"],
        "date": email_data["date"],
        "body": email_data["body"],
    }

    try:
        supabase.table("emails").insert(data).execute()
        logger.info(f"Stored email {data['message_id']} in Supabase.")
    except Exception as e:
        logger.error(f"Failed to save email {data['message_id']}: {e}")


def fetch_all_emails() -> t.List[t.Dict[str, t.Any]]:
    """
    Fetches all emails from the emails table.
    You might add WHERE clauses or pagination here in a real system.
    """
    try:
        response = supabase.table("emails").select("*").execute()
        return response.data or []
    except Exception as exc:
        logger.error(f"Failed to fetch emails: {exc}")
        return []


def event_exists_in_db(title: str, event_date: str, location: str) -> bool:
    """
    Checks if an event with the same title, date, and location already exists in the Supabase database.
    """
    try:
        result = (
            supabase.table("events")
            .select("id")  # Select a minimal field (id) to reduce data transfer
            .eq("title", title)
            .eq("event_date", event_date)
            .eq("location", location)
            .limit(1)  # Only need to check if one exists
            .execute()
        )

        return len(result.data) > 0  # If any results exist, return True
    except Exception as e:
        logger.error(f"Error checking event existence ({title}, {event_date}, {location}): {e}")
        return False  # Default to False on error so we don't block inserts unnecessarily


def save_events_to_db(events: t.List[Event], email_message_id: str) -> None:
    if not events:
        return

    events_to_insert = []
    for event in events:
        if not event_exists_in_db(event.title, event.event_date, event.location):
            event.email_message_id = email_message_id
            events_to_insert.append(event.dict())

    if events_to_insert:
        try:
            response = supabase.table("events").insert(events_to_insert).execute()
            logger.info(f"Inserted {len(response.data)} events into 'events' table for email {email_message_id}.")
        except Exception as exc:
            logger.error(f"Failed to insert events for email {email_message_id}: {exc}")
    else:
        logger.info(f"No new events to save from email {email_message_id}.")