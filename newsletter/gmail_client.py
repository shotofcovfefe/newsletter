import os
import base64
import logging
import typing as t

from email import message_from_bytes
from email.message import Message

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# For read-only access to Gmail
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def load_credentials(token_path: str, scopes: t.List[str]) -> Credentials:
    """
    Loads credentials from an existing token file.
    If the token is expired but has a refresh token, it refreshes and updates the file.
    If the token file doesn't exist or can't be refreshed, raises an error instead
    of regenerating token.json via browser-based OAuth flow.
    """
    if not os.path.exists(token_path):
        raise FileNotFoundError(
            f"No token file found at '{token_path}'. "
            "Please generate one before running this script."
        )

    creds = Credentials.from_authorized_user_file(token_path, scopes)
    if not creds:
        raise ValueError("Failed to load credentials from token file.")

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        logger.info("Token was expired but has been refreshed.")
        # Optionally save the updated token back to the file
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
        logger.info("Refreshed token saved back to file.")

    if not creds.valid:
        # If it's still not valid, there's no way to refresh automatically.
        raise ValueError("Credentials are invalid and cannot be refreshed.")

    return creds


class GmailClient:
    def __init__(self, token_path: str = "token.json") -> None:
        """
        Initializes the GmailClient with credentials from the given token file.
        """
        self.token_path = token_path
        self.creds = load_credentials(self.token_path, SCOPES)
        self.service = build("gmail", "v1", credentials=self.creds)

    def fetch_messages(
            self,
            query: t.Optional[str] = None,
            max_results: int = 100
    ) -> t.List[Message]:
        """
        Fetches all messages from Gmail matching the optional 'query'.
        Returns them as a list of 'email.message.Message' objects.
        """
        messages: t.List[Message] = []
        page_token = None

        while True:
            list_args = {
                "userId": "me",
                "maxResults": max_results,
            }
            if query:
                list_args["q"] = query
            if page_token:
                list_args["pageToken"] = page_token

            response = self.service.users().messages().list(**list_args).execute()
            raw_messages = response.get("messages", [])

            for msg_info in raw_messages:
                msg_id = msg_info["id"]
                # Retrieve the raw email
                detail = self.service.users().messages().get(
                    userId="me", id=msg_id, format="raw"
                ).execute()
                msg_bytes = base64.urlsafe_b64decode(detail["raw"])
                msg_obj = message_from_bytes(msg_bytes)
                messages.append(msg_obj)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return messages

    @staticmethod
    def extract_email_body(email_msg: Message) -> str:
        """
        Extracts and returns the plain-text body from an email.
        Skips attachments and HTML parts, returning only text/plain if available.
        """
        if email_msg.is_multipart():
            for part in email_msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", "")).lower()

                # We only care about plain text that's not an attachment
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    payload = part.get_payload(decode=True)
                    return payload.decode("utf-8", "ignore") if payload else "No Content"

        # Single-part emails
        payload = email_msg.get_payload(decode=True)
        return payload.decode("utf-8", "ignore") if payload else "No Content"
