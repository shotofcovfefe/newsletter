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
    try:
        processed_response_all = supabase.table("events_enriched_processed").select("id").execute()
        processed_response_success = supabase.table("events_enriched").select("event_id").execute()
        processed_ids_all = [row["id"] for row in processed_response_all.data] if processed_response_all.data else []
        processed_ids_success = [row["event_id"] for row in processed_response_success.data] if processed_response_success.data else []
        processed_ids = list(set(processed_ids_all + processed_ids_success))
    except Exception as e:
        logger.error(f"Error fetching processed IDs: {e}", exc_info=True)
        return # Cannot proceed without knowing what's processed

    today = datetime.now(timezone.utc).date()
    start_of_today = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)

    # Fetch events to process
    try:
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
    except Exception as e:
        logger.error(f"Error fetching events to process: {e}", exc_info=True)
        return # Cannot proceed without events


    for event in events:
        event_id = event["id"]
        matched_venue = None # Initialize matched_venue for broader scope
        venue_name = None
        venue_postcode = None # <<<<<<< ADDED: Initialize venue_postcode
        lat, lon = None, None
        venue_url = None # Initialize venue_url

        # 1) Check start date
        if not event.get("event_start_date"): # Use .get() for safety
            reason = f"Failure: No start date found for event {event_id}"
            try: supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
            except Exception as e_log: logger.error(f"Error logging processed status for {event_id}: {e_log}")
            logger.info(reason)
            continue

        # 2) Get associated email
        try:
            email_response = supabase.table("emails").select("email_address, sender_name").eq("message_id", event["email_message_id"]).maybe_single().execute() # Use maybe_single
        except Exception as e:
             reason = f"Failure: Error fetching email for event {event_id}: {e}"
             try: supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
             except Exception as e_log: logger.error(f"Error logging processed status for {event_id}: {e_log}")
             logger.error(reason, exc_info=True)
             continue

        if not email_response or not email_response.data:
            reason = f"Failure: No email found for event {event_id} with message_id {event.get('email_message_id')}"
            try: supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
            except Exception as e_log: logger.error(f"Error logging processed status for {event_id}: {e_log}")
            logger.info(reason)
            continue

        email_data = email_response.data
        email_address = email_data.get("email_address")
        domain = extract_domain_from_email(email_address) if email_address else None

        # 3) Attempt to find a venue using different methods
        try:
            # (a) match on exact email address
            if email_address:
                venue_response = (
                    supabase
                    .table("venues")
                    .select("id, name, latitude, longitude, url, postcode") # <<<<< ADDED postcode
                    .eq("email_address", email_address)
                    .maybe_single() # Use maybe_single for safety
                    .execute()
                )
                if venue_response and venue_response.data:
                    matched_venue = venue_response.data

            # (b) match on domain (if no email match)
            if not matched_venue and domain:
                venue_response = (
                    supabase.table("venues")
                    .select("id, name, latitude, longitude, url, postcode") # <<<<< ADDED postcode
                    .eq("domain", domain)
                    .limit(1) # Take the first match if multiple exist for a domain
                    .execute()
                    )
                # Check if data is not empty before accessing index 0
                if venue_response and venue_response.data:
                    matched_venue = venue_response.data[0]

            # (c) fallback to sender_name (if still no match)
            if not matched_venue:
                sender_name = email_data.get("sender_name")
                if sender_name:
                    sender_name_lower = sender_name.strip().lower()
                    # Avoid overly broad matches on generic sender names
                    if sender_name_lower not in ["info", "hello", "admin", "events", "bookings"]:
                        venue_response = (
                            supabase
                            .table("venues")
                            .select("id, name, latitude, longitude, url, postcode") # <<<<< ADDED postcode
                            .ilike("name", f"%{sender_name_lower}%") # Use % for substring match, adjust if needed
                            .limit(1) # Take first fuzzy match
                            .execute()
                        )
                        if venue_response and venue_response.data:
                            matched_venue = venue_response.data[0]

        except Exception as e:
             reason = f"Failure: Error querying venues for event {event_id}: {e}"
             try: supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
             except Exception as e_log: logger.error(f"Error logging processed status for {event_id}: {e_log}")
             logger.error(reason, exc_info=True)
             continue

        # Extract details if a venue was matched
        if matched_venue:
            venue_name = matched_venue.get("name")
            lat = matched_venue.get("latitude")
            lon = matched_venue.get("longitude")
            venue_url = matched_venue.get("url")
            venue_postcode = matched_venue.get("postcode") # <<<<< STORE postcode

        # If no venue name could be derived => fail
        if not venue_name:
            reason = f"Failure: No venue name found for email {email_address or 'N/A'} / domain {domain or 'N/A'}"
            try: supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
            except Exception as e_log: logger.error(f"Error logging processed status for {event_id}: {e_log}")
            logger.info(reason)
            continue

        # 4) Generate event summary text using GPT
        pretty_fields_json = generate_pretty_fields(event, venue_name)
        if not pretty_fields_json:
            reason = f"Failure: GPT generation failed for event {event_id}"
            try: supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
            except Exception as e_log: logger.error(f"Error logging processed status for {event_id}: {e_log}")
            logger.info(reason)
            continue

        # 5) Parse GPT JSON output
        try:
            # Attempt to handle potential markdown fences ```json ... ```
            if isinstance(pretty_fields_json, str):
                 clean_json_string = pretty_fields_json.strip()
                 if clean_json_string.startswith("```json"):
                     clean_json_string = clean_json_string[7:]
                 if clean_json_string.endswith("```"):
                     clean_json_string = clean_json_string[:-3]
                 clean_json_string = clean_json_string.strip()
                 pretty_fields = json.loads(clean_json_string)
            else:
                 # If it's already a dict (less likely with recent openai versions)
                 pretty_fields = pretty_fields_json

        except json.JSONDecodeError as exc:
            reason = f"Failure: GPT output could not be parsed as JSON for event {event_id}. Error: {exc}. Raw Output: '{pretty_fields_json}'"
            try: supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
            except Exception as e_log: logger.error(f"Error logging processed status for {event_id}: {e_log}")
            logger.error(reason)
            continue
        except Exception as exc: # Catch other potential errors during parsing/cleaning
             reason = f"Failure: Unexpected error processing GPT output for event {event_id}. Error: {exc}. Raw Output: '{pretty_fields_json}'"
             try: supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
             except Exception as e_log: logger.error(f"Error logging processed status for {event_id}: {e_log}")
             logger.error(reason)
             continue


        # 6) Insert into events_enriched
        try:
            insert_data = {
                "event_id": event_id,
                "venue_id": matched_venue["id"] if matched_venue else None,
                # "description": None, # Keep original description if needed, or remove if unused
                "latitude": lat,
                "longitude": lon,
                "postcode": venue_postcode, # <<<<<<< ADDED postcode field
                "event_date": event["event_start_date"],
                "pretty_event_name": pretty_fields.get("pretty_event_name"),
                "pretty_venue_name": pretty_fields.get("pretty_venue_name"),
                "pretty_date": pretty_fields.get("pretty_date"),
                "pretty_description": pretty_fields.get("pretty_description"),
                "vibes": pretty_fields.get("vibes"),
                "venue_url": venue_url,
                "created_at": datetime.now(timezone.utc).isoformat() # Use timezone aware now
            }
            # Remove keys with None values if your table schema requires it or for cleanliness
            # insert_data = {k: v for k, v in insert_data.items() if v is not None}

            insert_response = supabase.table("events_enriched").insert(insert_data).execute()

            # Optional: Check response status or data if needed
            # if not insert_response.data: # Basic check, might need more specific error handling
            #    raise Exception(f"Insert into events_enriched returned no data. Response: {insert_response}")


            # Mark success in processed table
            supabase.table("events_enriched_processed").insert({
                "id": event_id,
                "reason": "Success"
            }).execute()
            logger.info(f"Enriched event {event_id} successfully.")

        except Exception as exc:
            reason = f"Failure: Insert to events_enriched failed for event {event_id}. Error: {exc}"
            # Log failure in processed table even if insert failed
            try: supabase.table("events_enriched_processed").insert({"id": event_id, "reason": reason}).execute()
            except Exception as e_log: logger.error(f"Error logging processed status after failed insert for {event_id}: {e_log}")
            logger.error(reason, exc_info=True) # Log the original insert error with traceback



def main():
    logger.info("Starting events enrichment process")
    process_events()
    logger.info("Events enrichment process completed")


if __name__ == "__main__":
    main()
