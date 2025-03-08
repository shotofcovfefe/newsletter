from newsletter.gmail_client import GmailClient
from newsletter.database import email_exists, save_email
from newsletter.gmail_labels import apply_label, get_label_id
import logging

logging.basicConfig(level=logging.INFO)


def main():
    gmail = GmailClient()
    service = gmail.service
    label_id = get_label_id(service)

    if not label_id:
        logging.error("Label 'Processed' not found. Exiting.")
        return

    emails = gmail.fetch_unprocessed_emails(query='-label:Processed')

    for email_msg in emails:
        try:
            message_id = email_msg.get('Message-ID', 'unknown')
            if not email_exists(message_id):
                email_body = gmail.extract_email_body(email_msg)

                email_data = {
                    'message_id': message_id,
                    'sender': email_msg.get('From', 'unknown'),
                    'subject': email_msg.get('Subject', 'No Subject'),
                    'date': email_msg.get('Date', 'unknown'),
                    'body': email_body
                }
                save_email(email_data)
                apply_label(service=service, message_id=email_msg['id'], label_id=label_id)
        except Exception as e:
            logging.error(f"Failed to process email {email_msg.get('id', 'unknown')}: {e}")


if __name__ == '__main__':
    main()
