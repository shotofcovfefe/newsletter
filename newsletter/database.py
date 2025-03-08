from supabase import create_client
import os
from dotenv import load_dotenv
import logging
import typing as ta

load_dotenv()
logger = logging.getLogger(__name__)

supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
logger.info(f"Supabase URL: {supabase_url}")
logger.info(f"Supabase Key: {supabase_key[:5]}...")

supabase = create_client(supabase_url, supabase_key)


def save_email(email_data: ta.Dict[str, ta.Any]) -> None:
    data = {
        "message_id": email_data["message_id"],
        "sender": email_data['sender'],
        "subject": email_data["subject"],
        "date": email_data['date'],
        "body": email_data["body"]
    }
    try:
        supabase.table("emails").insert(data).execute()  # Use insert instead of upsert
        logger.info(f"Stored email {data['message_id']} in Supabase.")
    except Exception as e:
        logger.error(f"Failed to save email {data['message_id']}: {e}")


def email_exists(message_id: str) -> bool:
    try:
        result = supabase.table("emails").select("message_id").eq("message_id", message_id).execute()
        return len(result.data) > 0
    except Exception as e:
        logger.error(f"Failed to check email existence for {message_id}: {e}")
        return False  # Default to processing if check fails) > 0