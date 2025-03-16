import logging
import os
import re
import email.header
from bs4 import BeautifulSoup
from email.utils import parseaddr

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
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="#")
    text = re.sub(r'[\n]+', '\n', text).replace("\n#", "")
    return text


def decode_sender_name(sender_raw: str) -> str:
    """
    Extracts and decodes the sender's name from the raw From field.
    Ensures the result is UTF-8 decoded and free from surrounding quotes.
    """
    # parseaddr splits into display_name, email_address
    display_name, _ = parseaddr(sender_raw)

    if not display_name:
        return None

    # decode_header may return a list of (bytes / string, encoding)
    decoded_parts = email.header.decode_header(display_name)
    decoded_str = []
    for part, enc in decoded_parts:
        if isinstance(part, bytes):
            enc = enc or "utf-8"
            decoded_str.append(part.decode(enc, errors="replace"))
        else:
            # Already a string
            decoded_str.append(part)

    # Join together
    decoded_name = "".join(decoded_str)

    # Remove any surrounding quotes
    decoded_name = decoded_name.replace('"', "").strip()

    return decoded_name or None



def is_events_newsletter(email_body: str) -> bool:
    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            store=True,
            messages=[
                {
                    "role": "system",
                    "content": "You are an AI that classifies whether an email contains details about upcoming events. "
                               "If the email contains upcoming events at the venue in question or is obviously an events newsletter, respond only with 'true'. Otherwise, respond only with 'false'.",
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

        email_body = gmail_client.extract_email_body(email_msg)
        sender_raw = email_msg.get("From", "unknown")
        _, email_address = parseaddr(str(sender_raw))
        display_name, email_address = parseaddr(str(sender_raw))
        sender_name = decode_sender_name(sender_raw)

        email_data = {
            "message_id": message_id,
            "sender": sender_raw,
            "sender_name": sender_name,
            "email_address": email_address,
            "subject": email_msg.get("Subject", "No Subject"),
            "date": email_msg.get("Date", "unknown"),
            "body": email_body
        }

        if is_html(email_body):
            email_body = strip_html(email_body)
            email_data['body'] = remove_urls(email_body)

        try:
            newsletter_flag = is_events_newsletter(email_data['body'])
        except Exception as exc:
            logger.error(f"Error determining if newsletter: {exc}")
            newsletter_flag = False

        # 2) Attach the result to the email data
        email_data["is_newsletter"] = newsletter_flag

        # Save to the database
        save_email(email_data)


def remove_urls(text: str) -> str:
    return re.sub(r'https?:\/\/\S+', '', text, flags=re.MULTILINE).strip()


if __name__ == "__main__":
    main()
