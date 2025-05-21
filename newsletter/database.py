import os
import dateutil.parser
import logging
import typing as t
from dotenv import load_dotenv
from supabase import create_client
from datetime import date, time, datetime, timezone

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


# ---------- helpers -----------------------------------------------------------

def _date_to_iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _time_to_str(t: time | None) -> str | None:
    return t.isoformat(timespec="seconds") if t else None


def email_already_parsed(message_id: str) -> bool:
    res_1 = (
        supabase.table("events")
        .select("id")
        .eq("email_message_id", message_id)
        .limit(1)
        .execute()
    )
    if bool(res_1.data):
        return True

    res_2 = (
        supabase.table("emails_processed")
        .select("message_id")
        .eq("message_id", message_id)
        .limit(1)
        .execute()
    )
    if bool(res_2.data):
        return True
    return False


def fetch_all_emails() -> t.List[t.Dict[str, t.Any]]:
    """Fetch every stored email (add filters/pagination in prod)."""
    try:
        res = supabase.table("emails").select("*").execute()
        return res.data or []
    except Exception as exc:
        logger.error("Failed to fetch emails: %s", exc)
        return []


# ---------- event persistence -------------------------------------------------

def _datetime_to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def save_events_to_db(events: list[Event], email_message_id: str) -> None:
    """
    Insert a batch of events into `events` iff the email hasn’t been parsed.
    """
    if not events:
        return

    if email_already_parsed(email_message_id):
        logger.info("Events for %s already in DB – skipping insert.", email_message_id)
        return

    rows: list[dict[str, t.Any]] = []
    for ev in events:
        rec = ev.dict()

        # --- SERIALISE new date/time columns -----------------------
        rec["start_date"] = _date_to_iso(rec["start_date"])
        rec["end_date"] = _date_to_iso(rec["end_date"])
        rec["start_time"] = _time_to_str(rec["start_time"])
        rec["end_time"] = _time_to_str(rec["end_time"])

        rec["email_message_id"] = email_message_id
        rows.append(rec)

    supabase.table("events").insert(rows).execute()
    logger.info("Inserted %s events for %s", len(rows), email_message_id)


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
    date = email_data["date"]
    if date:
        date = dateutil.parser.parse(date)
        date = date.isoformat()  # e.g. '2025-03-10T20:58:24+01:00'

    data = {
        "message_id": email_data["message_id"],
        "sender": email_data["sender"],
        "subject": email_data["subject"],
        "email_address": email_data["email_address"],
        "sender_name": email_data["sender_name"],
        "date": date,
        "body": email_data["body"],
        "is_newsletter": email_data["is_newsletter"],
    }
    print(data['sender_name'])

    supabase.table("emails").insert(data).execute()
    logger.info(f"Stored email {data['message_id']} in Supabase.")


def email_already_processed(message_id: str) -> bool:
    """
    True ⇢ row exists in emails_processed.
    """
    res = (
        supabase.table("emails_processed")
        .select("message_id")
        .eq("message_id", message_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def mark_email_processed(message_id: str, parsed_ok: bool, note: str | None = None) -> None:
    """
    Upsert {message_id, processed_at, parsed_ok, note}.
    """
    row = {
        "message_id": message_id,
        "processed_at": datetime.utcnow().isoformat(),
        "parsed_ok": parsed_ok,
        "note": note,
    }
    supabase.table("emails_processed").upsert(row).execute()


def fetch_unprocessed_emails(batch_size: int) -> list[dict]:
    """
    Return up to `batch_size` emails that have **no** row in emails_processed.
    """
    # grab processed ids only once (tiny table)
    res = supabase.table("emails_processed").select("message_id").execute()
    done = {r["message_id"] for r in (res.data or [])}

    q = supabase.table("emails").select("*")
    if batch_size:
        q = q.limit(batch_size)

    emails = q.execute().data or []
    return [e for e in emails if e["message_id"] not in done]
