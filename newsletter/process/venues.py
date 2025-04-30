import os
import json
import logging
import typing as ta
from urllib.parse import urlparse
from dotenv import load_dotenv
from supabase import create_client, Client

from newsletter.utils import hash_prefix, get_postcode_info

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def extract_domain(url: str) -> ta.Optional[str]:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.netloc.replace('www.', '') or None


def main() -> None:
    with open("newsletter/data/venues_single.json", "r", encoding="utf-8") as f:
        venues_data = json.load(f)

    rows_to_insert = []
    for v in venues_data:
        pc_info = get_postcode_info(v.get("postcode"))
        rows_to_insert.append({
            "id": hash_prefix(v["name"].lower().replace(' ', '').strip()),
            "email_address": v.get("email") or None,
            "name": v["name"],
            "address": v["address"],
            "postcode": v["postcode"],
            "venue_type": v["venue_type"],
            "has_newsletter": v["has_newsletter"],
            "is_generic": v.get("is_generic") or False,
            "url": v["url"],
            "domain": extract_domain(v["url"]),
            "latitude": str(pc_info.get('lat')),
            "longitude": str(pc_info.get('lon')),
            "borough": str(pc_info.get('borough')),
        })

    try:
        response = supabase.table("venues").upsert(
            rows_to_insert,
            on_conflict="id"
        ).execute()
        logger.info("Insert successful")
        logger.info(response.data)
    except Exception as e:
        logger.error(f"Error inserting data: {e}")


if __name__ == "__main__":
    main()
