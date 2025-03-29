import json
import logging
import typing as ta
import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

from newsletter.database import fetch_all_emails, save_events_to_db, email_already_parsed
from newsletter.process.emails import is_events_newsletter
from newsletter.types import Events, Event

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def extract_events(email_body: str, email_sent_date: str) -> ta.List[Event]:
    """
    Uses an LLM to parse the email content and extract structured event data.
    Instruct LLM to:
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
    - description (string): A concise summary of the event (for example `A hybrid feature film exploring autistic perspectives and perception, directed by The Neurocultures Collective.`
    - description_verbatim (string): A verbatim extraction of the event from the email.
    - is_event_course (boolean): Is the event actually a course (vs one off or recurring) that takes place over multiple sessions 
    - is_event_recurring (boolean | null)
    - event_recur_freq (string | null): e.g., 'weekly', 'monthly', etc. If not recurring, null.
    - llm_rating (int): assign an 'interest score' / rating (1-10) to each event, based on: 1) Novelty or uniqueness, 2. Broad appeal. 3. Fun or entertainment value. A score of 1 indicates minimal interest or excitement, while 10 indicates an extremely compelling or can't-miss event. Penalise if not a one off event.     
    - event_time_of_day (text): the time of the event on the day (either `early morning`, `late morning`, `afternoon`, `evening`, `night`), if multiple times, then mark as null.  
    - venue_name (string | null): The name of the inferred venue hosting the events, if at all extractable (for example, "Ben's Bookstore", "Loafing Cafe"). If it's not obviously extactable, return null). If the venue name is not given on the event itself, it's likely that the venue is the emailer or that it's contained elsewhere in the newsletter, if not don't force it (accuracy is key).  

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
        raw_json = raw_json.lstrip('```json\n').strip('\n').rstrip('```')

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
                events.append(Event(**item))
            except Exception as e:
                logger.error(f"Could not parse an event item: {item} => {e}")

        return events

    except Exception as e:
        print()
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

        body_len = len(email_rec["body"])
        if body_len > 10000:
            logger.info(f"Email {message_id} body is too long ({body_len}), won't process.")
            continue

        # Check if the email is an events newsletter (boolean)
        body = email_rec["body"] or ""
        if email_rec['is_newsletter']:
            logger.info(f"Email {message_id} is an events newsletter. Extracting events...")

            # Attempt to parse a send date from email_rec["date"] (assuming it's standard format)
            email_sent_date_str = email_rec.get("date", "")
            # Format to YYYY-MM-DD if possible
            try:
                dt = datetime.fromisoformat(email_sent_date_str)
                email_sent_date_str = dt.strftime("%Y-%m-%d")
            except ValueError:
                # If we can't parse, don't give a date
                pass

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
