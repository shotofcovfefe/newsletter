import logging
import typing as ta
import os
from openai import OpenAI
from dotenv import load_dotenv

from newsletter.database import fetch_all_emails, save_events_to_db
from newsletter.types import Events, Event

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def extract_events(email_body: str) -> ta.List[Event]:
    """
    Uses GPT-4o to parse the email content and extract structured event data
    using OpenAI's structured output format.

    Returns a list of `Event` objects.
    """

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an AI assistant that extracts structured event details from text. "
                        "Analyze the provided newsletter content and return a list of events in JSON format. "
                        "Each event should contain:\n"
                        " - title (string)\n"
                        " - event_date (string, YYYY-MM-DD format if possible, or exact wording from email)\n"
                        " - location (string, this might also be online)\n"
                        " - event_type (string, keep it simple)\n"
                        " - description (string, concise summary)\n\n"
                        "Return structured JSON output that strictly adheres to this format."
                    ),
                },
                {"role": "user", "content": email_body},
            ],
            response_format=Events,
        )

        parsed_events = completion.choices[0].message.parsed
        if isinstance(parsed_events, Events) and len(parsed_events.events):
            return parsed_events.events

        logger.warning("Parsed output is not a list. Returning empty.")
        return []

    except Exception as e:
        logger.error(f"Error extracting events: {e}")
        return []


def is_events_newsletter(email_body: str) -> bool:
    """
    Uses GPT-4o to determine if the email content is an 'events newsletter'.
    Returns True if yes, False otherwise.
    """
    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            store=True,
            messages=[
                {
                    "role": "system",
                    "content": "You are an AI that classifies whether an email contains details about upcoming events. "
                               "If the email contains events that can be parsed with dates, respond only with 'true'. Otherwise, respond only with 'false'.",
                },
                {"role": "user", "content": email_body},
            ],
            max_tokens=5
        )

        classification = completion.choices[0].message

        return classification.content == "true"

    except Exception as exc:
        logger.error(f"Error calling OpenAI for classification: {exc}")
        return False


def main() -> None:
    emails = fetch_all_emails()

    for email_rec in emails:
        message_id = email_rec["message_id"]
        body = email_rec["body"] or ""

        # 1) Classify if it is an events newsletter
        if is_events_newsletter(body):
            logger.info(f"Email {message_id} is an events newsletter. Extracting events...")
            # 2) Extract event details
            events_data = extract_events(body)

            if events_data:
                # 3) Save to the 'events' table
                save_events_to_db(events_data, message_id)
            else:
                logger.info(f"No events detected in email {message_id} after parsing.")
        else:
            logger.info(f"Email {message_id} is not an events newsletter. Skipping.")


if __name__ == "__main__":
    main()
