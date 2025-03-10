import logging
from newsletter.gmail_client import GmailClient
from newsletter.database import email_exists, save_email

logging.basicConfig(level=logging.INFO)


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
            logging.warning("Email is missing Message-ID; skipping.")
            continue

        if email_exists(message_id):
            logging.info(f"Email with Message-ID {message_id} already exists in DB. Skipping.")
            continue

        # Extract the email's data
        email_data = {
            "message_id": message_id,
            "sender": email_msg.get("From", "unknown"),
            "subject": email_msg.get("Subject", "No Subject"),
            "date": email_msg.get("Date", "unknown"),
            "body": gmail_client.extract_email_body(email_msg),
        }

        # Save to the database
        save_email(email_data)


if __name__ == "__main__":
    main()
