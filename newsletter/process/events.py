import json
import logging
import typing as ta
import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

from newsletter.database import fetch_all_emails, save_events_to_db, email_already_parsed
from newsletter.types import Events, Event

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def extract_events(email_body: str, email_sent_date: str) -> ta.List[Event]:
    """
    Uses GPT-4o to parse the email content and extract structured event data.
    Instruct GPT to:
    - Exclude company name from the `title`.
    - Attempt best-effort to parse event_start_date/event_end_date using email_sent_date as a reference.
    - If it's impossible to deduce a date, return null.
    - Indicate whether it's recurring and if so, the frequency.
    """
    system_instructions = f"""
You are an AI assistant that extracts structured event details from text. 
The email was sent on {email_sent_date} (YYYY-MM-DD). 
You will return a JSON list of objects, each containing these fields:
    - title (string): A concise event title (without any company names, capitalised first letter no full stop)
    - event_start_date (date | null) 
    - event_end_date (date | null)
    - location (string): 'on-site', 'off-site', 'online', 'unknown'
    - event_type (string): Keep it simple (e.g., 'Meetup', 'Conference', 'Film screening', etc.).
    - description (string): A concise summary of the event.
    - description_verbatim (string): A verbatim extraction of the event from the email.
    - is_event_recurring (boolean)
    - event_recur_freq (string | null): e.g., 'weekly', 'monthly', etc. If not recurring, null.

Deducing Dates:
    - If the email says "next Friday" or "tomorrow," interpret relative to {email_sent_date}.
    - If impossible to deduce, use null for event_start_date or event_end_date.

The final output MUST be valid JSON, with a top-level list of event objects.
No extra keys are allowed.
No text outside of valid JSON.
"""

    try:
        # Request GPT to return JSON
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": email_body},
            ],
            # We want raw JSON as output so we can parse it ourselves
            temperature=0.2,
        )
        raw_json = completion.choices[0].message.content.strip()

        # Convert JSON string into Python structures
        data = json.loads(raw_json)

        # Expecting a list of events
        if not isinstance(data, list):
            logger.warning("GPT output is not a list. Returning empty list.")
            return []

        # Convert each item to a Pydantic Event
        events = []
        for item in data:
            try:
                # Convert event_start_date / event_end_date from string → date (if not null)
                # Or let Pydantic parse automatically if item["event_start_date"] is str or None
                events.append(Event(**item))
            except Exception as e:
                logger.error(f"Could not parse an event item: {item} => {e}")

        return events

    except Exception as e:
        logger.error(f"Error extracting events: {e}")
        return []


def main() -> None:
    """
    Main workflow:
    1. Fetch all emails.
    2. Check if they've already been parsed; skip if yes.
    3. Classify each to see if it is an events newsletter.
    4. If so, attempt extracting events, and if found, save them.
    """
    emails = fetch_all_emails()

    for email_rec in emails:
        message_id = email_rec["message_id"]

        # If this email was already parsed (i.e. we have any events with this message_id), skip.
        if email_already_parsed(message_id):
            logger.info(f"Email {message_id} was previously parsed. Skipping.")
            continue

        # Check if the email is an events newsletter
        body = email_rec["body"] or ""
        if is_events_newsletter(body):
            logger.info(f"Email {message_id} is an events newsletter. Extracting events...")

            # Attempt to parse a send date from email_rec["date"] (assuming it's standard format)
            email_sent_date_str = email_rec.get("date", "")
            # Format to YYYY-MM-DD if possible
            try:
                # Try parsing. You can adapt the format if needed.
                dt = datetime.fromisoformat(email_sent_date_str)
                email_sent_date_str = dt.strftime("%Y-%m-%d")
            except ValueError:
                # If we can't parse, just pass it raw or fallback to today
                email_sent_date_str = email_sent_date_str or datetime.now().strftime("%Y-%m-%d")

            # Extract event details
            events_data = extract_events(body, email_sent_date_str)

            if events_data:
                # Save to the 'events' table
                save_events_to_db(events_data, message_id)
            else:
                logger.info(f"No events detected in email {message_id} after parsing.")
        else:
            logger.info(f"Email {message_id} is not an events newsletter. Skipping.")


if __name__ == "__main__":
    main()
