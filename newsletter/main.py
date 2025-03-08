from newsletter.gmail_client import GmailClient
from newsletter.database import supabase
import logging

logging.basicConfig(level=logging.INFO)


def main() -> None:
    gmail = GmailClient()
    emails = gmail.fetch_unread_emails()

    for email in emails:
        email_data = {
            'message_id': email['id'],
            'sender': email['from'],
            'subject': email['subject'],
            'date': email['date'],
            'body': email.get_payload()
        }
        supabase.table("emails").upsert(email_data).execute()


if __name__ == '__main__':
    main()
