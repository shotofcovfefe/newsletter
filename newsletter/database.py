from supabase import create_client
import os
from dotenv import load_dotenv
import logging
import typing as ta

load_dotenv()
logger = logging.getLogger(__name__)

supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase = create_client(supabase_url, supabase_key)


def save_email(email_data: ta.Dict[str, ta.Any]) -> None:
    data = {
        "message_id": email_data["message_id"],
        "sender": email_data['sender'],
        "subject": email_data["subject"],
        "date": email_data['date'],
        "body": email_data["body"]
    }
    supabase.table("emails").upsert(data).execute()
    logger.info(f"Stored email {data['message_id']} in Supabase.")
