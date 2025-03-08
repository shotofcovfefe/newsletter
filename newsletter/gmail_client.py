import base64
import logging
import os
import typing as ta

from email import message_from_bytes
from email.message import Message
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
logger = logging.getLogger(__name__)


class GmailClient:
    def __init__(self, credentials_path='credentials.json', token_path='token.json'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = build('gmail', 'v1', credentials=self.authenticate())

    def authenticate(self) -> Credentials:
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            logger.info("Token refreshed.")
        elif not creds:
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())
            logger.info("Token created and saved.")
        return creds

    def fetch_unprocessed_emails(self, query: str = '-label:Processed') -> ta.List[Message]:
        emails = []
        page_token = None
        while True:
            response = self.service.users().messages().list(
                userId='me',
                q=query,
                pageToken=page_token
            ).execute()
            messages = response.get('messages', [])
            for msg in messages:
                raw_msg = self.service.users().messages().get(userId='me', id=msg['id'], format='raw').execute()
                msg_bytes = base64.urlsafe_b64decode(raw_msg['raw'])
                emails.append(message_from_bytes(msg_bytes))
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return emails

    @staticmethod
    def extract_email_body(email_msg: Message) -> str:
        """Extract the email body, handling both plain and multipart emails."""
        if email_msg.is_multipart():
            for part in email_msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                # Ignore attachments
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    return part.get_payload(decode=True).decode('utf-8', 'ignore')

        # Fallback for non-multipart emails
        return email_msg.get_payload(decode=True).decode('utf-8', 'ignore') if email_msg.get_payload() else "No Content"
