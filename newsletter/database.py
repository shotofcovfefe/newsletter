import os
import dateutil.parser
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


def email_already_parsed(message_id: str) -> bool:
    """
    Returns True if we've already inserted at least one event for this email_message_id in the 'events' table.
    """
    try:
        result = (
            supabase.table("events")
            .select("id")
            .eq("email_message_id", message_id)
            .limit(1)
            .execute()
        )
        # If there's any row, we've parsed this email before
        return len(result.data) > 0
    except Exception as e:
        logger.error(f"Error checking if email {message_id} was previously parsed: {e}")
        # On error, default to False so we don't skip a potentially valid parse
        return False


def save_email(email_data: t.Dict[str, t.Any]) -> None:
    """
    Saves the given email data to the Supabase 'emails' table.
    """
    date = email_data["date"]
    if date:
        try:
            date = dateutil.parser.parse(date)
            date = date.isoformat()  # e.g. '2025-03-10T20:58:24+01:00'
        except Exception as e:
            logger.warning(f"Could not parse date '{date}'. Storing as null. Error: {e}")

    data = {
        "message_id": email_data["message_id"],
        "sender": email_data["sender"],
        "subject": email_data["subject"],
        "date": date,
        "body": email_data["body"],
        "is_newsletter": email_data["is_newsletter"],
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


def save_events_to_db(events: t.List[Event], email_message_id: str) -> None:
    """
    Saves all events from a given email to the 'events' table *if* we haven't
    already parsed this email (checking email_already_parsed).
    """
    if not events:
        return

    # 1) If the email was already parsed, skip
    if email_already_parsed(email_message_id):
        logger.info(f"Email {email_message_id} was previously parsed. Skipping event insert.")
        return

    # 2) Otherwise, insert these events (attach email_message_id for reference)
    events_dicts = []
    for event in events:
        record = event.dict()

        if record["event_start_date"] is not None:
            record["event_start_date"] = record["event_start_date"].isoformat()

        if record["event_end_date"] is not None:
            record["event_end_date"] = record["event_end_date"].isoformat()

        record["email_message_id"] = email_message_id
        events_dicts.append(record)

    try:
        response = supabase.table("events").insert(events_dicts).execute()
        logger.info(f"Inserted {len(response.data)} events into 'events' table for email {email_message_id}.")
    except Exception as exc:
        logger.error(f"Failed to insert events for email {email_message_id}: {exc}")