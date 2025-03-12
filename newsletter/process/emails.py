import logging
import os
import re
from bs4 import BeautifulSoup

from openai import OpenAI

from newsletter.gmail_client import GmailClient
from newsletter.database import email_exists, save_email

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def is_html(text: str) -> bool:
    """
    Naive check to see if the text contains HTML/DOCTYPE tags.
    Returns True if it looks like HTML, False if it looks like plain text.
    """
    text_lower = text.lower()
    # Look for any of these signatures that strongly suggest HTML
    signatures = ["<!doctype", "<html", "<head", "<body", "<p", "<div", "<span", "<table"]
    return any(sig in text_lower for sig in signatures)


def strip_html(html: str) -> str:
    """
    Parses HTML with Beautiful Soup, strips tags, and returns the plain text.
    """
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text()


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
    """
    Main entry point:
      1. Create a GmailClient using an existing token file.
      2. Fetch messages with a chosen query (e.g., 'in:inbox', 'is:unread', etc.).
      3. For each message, check if its Message-ID is already in the DB.
      4. If not, extract its data and save it to Supabase.
    """
    # Initialize the Gmail client
    gmail_client = GmailClient(token_path="token.json")

    # Adjust or remove the query based on your needs. E.g. "in:inbox", "is:unread", etc.
    messages = gmail_client.fetch_messages(query="in:inbox")

    for email_msg in messages:
        message_id = email_msg.get("Message-ID")
        if not message_id:
            logger.warning("Email is missing Message-ID; skipping.")
            continue

        if email_exists(message_id):
            logger.info(f"Email with Message-ID {message_id} already exists in DB. Skipping.")
            continue

        # Extract the email's data
        email_data = {
            "message_id": message_id,
            "sender": email_msg.get("From", "unknown"),
            "subject": email_msg.get("Subject", "No Subject"),
            "date": email_msg.get("Date", "unknown"),
            "body": gmail_client.extract_email_body(email_msg),
        }

        email_body = gmail_client.extract_email_body(email_msg)
        if is_html(email_body):
            email_body = strip_html(email_body)

        try:
            newsletter_flag = is_events_newsletter(email_body)
        except Exception as exc:
            logger.error(f"Error determining if newsletter: {exc}")
            newsletter_flag = False

        # 2) Attach the result to the email data
        email_data["is_newsletter"] = newsletter_flag

        # Save to the database
        save_email(email_data)


if __name__ == "__main__":
    main()
