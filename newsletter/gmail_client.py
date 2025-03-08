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

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
logger = logging.getLogger(__name__)


class GmailClient:
    def __init__(self, credentials_path='credentials.json', token_path='token.json'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = build('gmail', 'v1', credentials=self.authenticate())

    def authenticate(self) -> None:
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

    def fetch_unread_emails(self) -> ta.List[Message]:
        response = self.service.users().messages().list(userId='me', q='is:unread').execute()
        messages = response.get('messages', [])
        emails = []
        for msg in messages:
            raw_msg = self.service.users().messages().get(userId='me', id=msg['id'], format='raw').execute()
            msg_bytes = base64.urlsafe_b64decode(raw_msg['raw'])
            emails.append(message_from_bytes(msg_bytes))
        return emails
