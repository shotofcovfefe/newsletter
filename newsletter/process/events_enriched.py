import json
import os
import logging
from datetime import datetime, timezone
from openai import OpenAI
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(handler)

# Initialize Supabase and OpenAI clients
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def extract_domain_from_email(email: str) -> str | None:
    """Extracts the domain from an email address (e.g., 'growhackney.co.uk' from 'hello@growhackney.co.uk')."""
    if "@" in email:
        return email.split("@")[-1]
    return None


def get_ordinal_suffix(day: int) -> str:
    """Returns the ordinal suffix for a day (e.g., 'st' for 1, 'th' for 11)."""
    if 11 <= day <= 13:
        return "th"
    elif day % 10 == 1:
        return "st"
    elif day % 10 == 2:
        return "nd"
    elif day % 10 == 3:
        return "rd"
    else:
        return "th"


def format_date(date_str: str) -> str:
    """Formats an ISO date string into 'Month Day[st/nd/rd/th]' (e.g., 'March 14th')."""
    try:
        dt = datetime.fromisoformat(date_str)
        day = dt.day
        suffix = get_ordinal_suffix(day)
        return dt.strftime(f"%B {day}{suffix}")
    except ValueError:
        return date_str


def generate_pretty_fields(event: dict, venue_name: str) -> dict | None:
    """
    Generates structured, prettified fields for an event using GPT:
    - pretty_event_name (e.g. "🎸 Jazz Night")
    - pretty_venue_name (e.g. "at The Blues Kitchen")
    - pretty_date (e.g. "Saturday, March 14th")
    - vibes (e.g. "Chill, soulful, uplifting")
    - pretty_description (short summary)
    """
    title = event.get("title", "Untitled Event")
    date = format_date(event.get("event_start_date", "No Date"))
    description = event.get("description", "")

    system_prompt = (
        "You are an AI assistant that formats event data for presentation. "
        "Return a JSON object with these fields:\n"
        "- pretty_event_name: One representative emoji + concise, engaging title (e.g. '🎨 Life Drawing')\n"
        "- pretty_venue_name: the venue name (e.g. 'The Royal Swan Pub')\n"
        "- pretty_date: Human-readable date (e.g. 'Saturday, March 14th')\n"
        "- vibes: 3 words (comma separated, first letter of first word capitalised) that best represent the event (e.g. 'Powerful, moving, gripping' or 'Chill, soulful, uplifting')\n"
        "- pretty_description: One or two short, factual, engaging sentences. No first-person. Never mention the venue name.\n\n"
        
        "Output ONLY the JSON. Do not add extra text or formatting tags like <b> or <i>."
    )

    user_prompt = (
        f"Event Title: {title}\n"
        f"Event Date: {date}\n"
        f"Venue Name: {venue_name}\n"
        f"Event Description: {description}\n\n"
        "Please generate the formatted fields."
    )

    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"}
        )
        raw_json = completion.choices[0].message.content.strip()
        return raw_json.lstrip('```json\n').strip('\n').rstrip('```')
    except Exception as exc:
        logger.error(f"Error generating fields for event {event['id']}: {exc}")
        return None


def process_events():
    """Processes unprocessed events, enriches them, and tracks processing status."""
    # Fetch processed event IDs
    processed_response_all = supabase.table("events_enriched_processed").select("id").execute()
    processed_response_success = supabase.table("events_enriched").select("event_id").execute()
    processed_ids_all = [row["id"] for row in processed_response_all.data] if processed_response_all.data else []
    processed_ids_success = [row["event_id"] for row in processed_response_success.data] if processed_response_success.data else []
    processed_ids = list(set(processed_ids_all + processed_ids_success))

    today = datetime.now(timezone.utc).date()
    start_of_today = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)

    # Fetch events to process
    events_response = (
        supabase.table("events")
        .select("*")
        # ignore recurring or course events
        .or_("is_event_recurring.is.null,is_event_recurring.eq.false")
        .or_("is_event_course.is.null,is_event_course.eq.false")
        .not_.in_("id", processed_ids)
        .not_.is_("event_start_date", None)
        .gte("event_start_date", start_of_today.isoformat())
        .execute()
    )
    events = events_response.data or []
    logger.info(f"Found {len(events)} events to process.")

    for event in events:
        event_id = event["id"]

        # 1) If no start date => can't enrich
        if not event["event_start_date"]:
            reason = f"Failure: No start date found for event {event_id}"
            supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
            logger.info(reason)
            continue

        # 2) Join with emails table
        email_response = supabase.table("emails").select("email_address, sender_name").eq("message_id", event["email_message_id"]).execute()
        if not email_response.data:
            reason = f"Failure: No email found for event {event_id}"
            supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
            logger.info(reason)
            continue

        email = email_response.data[0]
        domain = extract_domain_from_email(email["email_address"]) or ""

        # 3) Attempt to find a venue name
        #    (a) match on exact email address
        venue_response = (
            supabase
            .table("venues")
            .select("id, name, latitude, longitude, url")
            .eq("email_address", email["email_address"])
            .execute()
        )

        if venue_response.data:
            # success with email match
            matched_venue = venue_response.data[0]
            venue_name = matched_venue["name"]
            lat, lon = matched_venue["latitude"], matched_venue["longitude"]
        else:
            # (b) match on domain
            venue_response = supabase.table("venues").select("id", "name, latitude, longitude, url").eq("domain", domain).execute()
            if venue_response.data:
                matched_venue = venue_response.data[0]
                venue_name = matched_venue["name"]
                lat, lon = matched_venue["latitude"], matched_venue["longitude"]
            else:
                # (c) fallback to email's sender_name if it exists
                sender_name = email.get("sender_name") or None
                if sender_name:
                    sender_name_lower = (sender_name or "").strip().lower()

                    venue_response = (
                        supabase
                        .table("venues")
                        .select("id", "name, latitude, longitude", "url")
                        .ilike("name", sender_name_lower)  # case-insensitive match
                        .execute()
                    )

                    if venue_response.data:
                        matched_venue = venue_response.data[0]
                        venue_name = matched_venue["name"]
                        lat, lon = matched_venue["latitude"], matched_venue["longitude"]
                    else:
                        venue_name = None
                        lat, lon = None, None
                else:
                    venue_name = None
                    lat, lon = None, None

        # If no venue name from any method => fail
        if not venue_name:
            reason = f"Failure: No venue name found for email {email['email_address']}"
            supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
            logger.info(reason)
            continue

        # 4) Generate event summary text
        pretty_fields_json = generate_pretty_fields(event, venue_name)
        if not pretty_fields_json:
            reason = f"Failure: GPT generation failed for event {event_id}"
            supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
            logger.info(reason)
            continue

        # 5) Extract JSON
        try:
            pretty_fields = json.loads(pretty_fields_json)
        except Exception as exc:
            reason = f"Failure: GPT output could not be parsed as JSON for event {event_id}. Error: {exc}"
            supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
            logger.error(reason)
            continue

        # 5) Insert into events_enriched
        try:
            supabase.table("events_enriched").insert({
                "event_id": event_id,
                "venue_id": matched_venue["id"] if matched_venue else None,
                "description": None,
                "latitude": lat,
                "longitude": lon,
                "event_date": event["event_start_date"],
                "pretty_event_name": pretty_fields.get("pretty_event_name"),
                "pretty_venue_name": pretty_fields.get("pretty_venue_name"),
                "pretty_date": pretty_fields.get("pretty_date"),
                "pretty_description": pretty_fields.get("pretty_description"),
                "vibes": pretty_fields.get("vibes"),
                "venue_url": matched_venue["url"],
                "created_at": datetime.utcnow().isoformat()
            }).execute()

            # Mark success
            supabase.table("events_enriched_processed").insert({
                "id": event_id,
                "reason": "Success"
            }).execute()
            logger.info(f"Enriched event {event_id} successfully.")

        except Exception as exc:
            reason = f"Failure: Insert to events_enriched failed for event {event_id}. Error: {exc}"
            supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
            logger.error(reason)


def main():
    logger.info("Starting events enrichment process")
    process_events()
    logger.info("Events enrichment process completed")


if __name__ == "__main__":
    main()
