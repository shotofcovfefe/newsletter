import os
import json
import logging
import typing as ta
from urllib.parse import urlparse
from dotenv import load_dotenv
from supabase import create_client, Client

from newsletter.constants import VENUES_FILEPATH, AGGREGATORS_FILEPATH
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


def process_single_venues(filepath: str) -> None:
    logger.info(f"Processing single venues from: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        venues_data = json.load(f)

    rows_to_upsert = []
    for v in venues_data:

        if not v.get("name"):
            logger.warning(f"Skipping single venue due to missing name: {v}")
            continue

        pc_info = get_postcode_info(v.get("postcode"))  # Needs postcode
        venue_id = hash_prefix(v["name"].lower().replace(' ', '').strip())

        rows_to_upsert.append({
            "id": venue_id,
            "email_address": v.get("email"),
            "name": v["name"],
            "address": v.get("address"),
            "postcode": v.get("postcode"),
            "venue_type": v.get("venue_type"),
            "has_newsletter": v.get("has_newsletter", False),
            "is_generic": v.get("is_generic", False),
            "url": v.get("url"),
            "domain": extract_domain(v.get("url")),
            # Ensure lat/lon are numeric or None for DB
            "latitude": pc_info.get('lat') if pc_info else None,
            "longitude": pc_info.get('lon') if pc_info else None,
            "borough": pc_info.get('borough') if pc_info else None,
            "neighbourhood": pc_info.get('neighbourhood') if pc_info else None,
        })

    if not rows_to_upsert:
        logger.warning(f"No valid single venue rows found in {filepath}")
        return

    logger.info(f"Upserting {len(rows_to_upsert)} rows into 'venues' table...")

    response = supabase.table("venues").upsert(
        rows_to_upsert,
        on_conflict="id"
    ).execute()
    logger.info("Upsert operation into 'venues' attempted.")
    # Minimal response logging
    if hasattr(response, 'error') and response.error:
        logger.error(f"'venues' upsert failed: {response.error.message}")
    elif response.data:
        logger.info(f"'venues' upsert processed {len(response.data)} rows.")
    else:
        logger.warning(
            f"'venues' upsert completed but returned no data. Status: {getattr(response, 'status_code', 'N/A')}")


def process_aggregator_venues(filepath: str) -> None:
    logger.info(f"Processing aggregator venues from: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        venues_data = json.load(f)

    rows_to_upsert = []
    for v in venues_data:
        if not v.get("name"):
            logger.warning(f"Skipping aggregator venue due to missing name: {v}")
            continue

        aggregator_id = hash_prefix(v["name"].lower().replace(' ', '').strip())

        rows_to_upsert.append({
            "id": aggregator_id,
            "name": v["name"],
            "description": v.get("descriptions"),
            "url": v.get("url"),
            "email_address": None if v.get("email") == "" else v.get("email"),
            "newsletter_type": v.get("newsletter_type"),
            "has_newsletter": v.get("has_newsletter", False),
            "domain": extract_domain(v.get("url")),
        })

    if not rows_to_upsert:
        logger.warning(f"No valid aggregator venue rows found in {filepath}")
        return

    logger.info(f"Upserting {len(rows_to_upsert)} rows into 'aggregators' table...")

    # Ensure the table name 'aggregators' matches your actual DB table
    response = supabase.table("aggregators").upsert(
        rows_to_upsert,
        on_conflict="id"
    ).execute()
    logger.info("Upsert operation into 'aggregators' attempted.")

    if hasattr(response, 'error') and response.error:
        logger.error(f"'aggregators' upsert failed: {response.error.message}")
    elif response.data:
        logger.info(f"'aggregators' upsert processed {len(response.data)} rows.")
    else:
        logger.warning(
            f"'aggregators' upsert completed but returned no data. Status: {getattr(response, 'status_code', 'N/A')}")


def main() -> None:
    # Process single venues first
    try:
        process_single_venues(VENUES_FILEPATH)
    except FileNotFoundError:
        logger.error(f"{VENUES_FILEPATH} not found.")
    except Exception as e:
        logger.error(f"Unhandled error processing single venues: {e}", exc_info=True)

    # Process aggregator venues
    try:
        process_aggregator_venues(AGGREGATORS_FILEPATH)
    except FileNotFoundError:
        logger.error(f"{AGGREGATORS_FILEPATH} not found.")
    except Exception as e:
        logger.error(f"Unhandled error processing aggregator venues: {e}", exc_info=True)


if __name__ == "__main__":
    main()
