import os
import json
import logging
import typing as ta
from urllib.parse import urlparse
from dotenv import load_dotenv
from supabase import create_client, Client
import pgeocode

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

nomi = pgeocode.Nominatim("GB")


def extract_domain(url: str) -> str:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.netloc or None


def get_lat_lon(postcode: str) -> ta.Tuple[ta.Optional[float], ta.Optional[float]]:
    """Gets latitude and longitude from postcode using pgeocode."""
    if not postcode:
        return None, None
    location = nomi.query_postal_code(postcode)
    if location is None or location.latitude is None or location.longitude is None:
        return None, None
    return location.latitude, location.longitude


def main() -> None:
    with open("venues.json", "r", encoding="utf-8") as f:
        venues_data = json.load(f)

    rows_to_insert = []
    for v in venues_data:
        lat, lon = get_lat_lon(v.get("postcode"))
        rows_to_insert.append({
            "email_address": v.get("email") or None,
            "name": v["name"],
            "address": v["address"],
            "venue_type": v["venue_type"],
            "has_newsletter": v["has_newsletter"],
            "url": v["url"],
            "domain": extract_domain(v["url"]),
            "latitude": str(lat),
            "longitude": str(lon),
        })

    try:
        supabase.table("venues").delete().neq("domain", None).execute()
        logger.info("Existing rows deleted.")

        # Insert new data
        response = supabase.table("venues").insert(rows_to_insert).execute()
        logger.info("Insert successful")
        logger.info(response.data)
    except Exception as e:
        logger.error(f"Error inserting data: {e}")


if __name__ == "__main__":
    main()
