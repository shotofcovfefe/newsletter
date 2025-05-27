import argparse
import os
import json
import logging
import datetime
import typing as t
from openai import OpenAI
from supabase import create_client
from dotenv import load_dotenv

from newsletter.utils.utils import replace_json_gates

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

if not logger.hasHandlers():
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(console_handler)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
IS_DEV = os.getenv("IS_DEV", "true").lower() == "true"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def fetch_used_event_ids() -> t.Set[int]:
    try:
        response = (
            supabase.table("newsletter_events")
            .select("event_id")
            .execute()
        )
        used_ids = {row["event_id"] for row in response.data} if response.data else set()
        logger.info(f"Fetched {len(used_ids)} previously used event IDs.")
        return used_ids
    except Exception as exc:
        logger.error(f"Failed to fetch used event IDs: {exc}")
        return set()


def fetch_events_last_7_days() -> t.List[t.Dict[str, t.Any]]:
    """
    Fetch all event records from the 'events' table that were *created* in the last 7 days.
    Then also retrieve the related 'emails.sender_name' by referencing the foreign key:
    events.email_message_id -> emails.message_id.

    Supabase returns nested data under the key "emails" if the foreign relationship
    is configured. We'll move 'sender_name' up to the top-level event dict for convenience.
    """
    seven_days_ago = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    try:
        # NOTE: The "emails:email_message_id(sender_name)" syntax tells Supabase:
        # - From the 'emails' table, include 'sender_name'
        # - 'email_message_id' in events references 'message_id' in emails
        response = (
            supabase
            .table("events")
            .select("*, emails:email_message_id(sender_name)")
            .gte("created_at", seven_days_ago)  # Adjust your filter as needed
            .execute()
        )
        data = response.data or []

        # Move emails.sender_name up to top-level "sender_name" for each event
        for ev in data:
            email_data = ev.pop("emails", None)
            if isinstance(email_data, dict):
                ev["sender_name"] = email_data.get("sender_name")
            else:
                # If there's no matching email or no data, you can set a default
                ev["sender_name"] = None

        logger.info(f"Fetched {len(data)} events from last 7 days.")
        return data
    except Exception as exc:
        logger.error(f"Failed to fetch recent events: {exc}")
        return []


def filter_non_recurring_upcoming(events: t.List[t.Dict[str, t.Any]]) -> t.List[t.Dict[str, t.Any]]:
    """
    From the events data, filter out recurring events, and only keep upcoming ones
    (event_start_date >= today).
    """
    today = datetime.date.today()
    used_event_ids = fetch_used_event_ids()
    filtered = []
    for ev in events:
        # Skip recurring events
        if ev.get("is_recurring") is True:
            continue

        # Skip events that have already been used
        if ev["id"] in used_event_ids:
            continue

        event_start = ev.get("event_start_date")
        if event_start:
            try:
                dt_start = datetime.datetime.fromisoformat(event_start).date()
                if dt_start >= today:
                    filtered.append(ev)
            except ValueError:
                pass

    logger.info(f"{len(filtered)} events remain after filtering non-recurring/upcoming.")
    return filtered


def score_events_with_ai(events: t.List[t.Dict[str, t.Any]]) -> t.List[t.Dict[str, t.Any]]:
    """
    Uses AI to score how interesting each event is.
    """
    combined_event_descriptions = "\n".join(
        f"{idx + 1}. {ev.get('title', 'No Title')} - {ev.get('description', '')}"
        for idx, ev in enumerate(events)
    )

    system_prompt = (
        "You are an AI assistant that assigns an 'interest score' / rating (1-10) to each event, based on:\n"
        "• Novelty or uniqueness: How fresh or original is this event?\n"
        "• Broad appeal: How likely is it to engage a wide range of people?\n"
        "• Fun or entertainment value: Is it enjoyable or exciting for attendees?\n\n"
        "A score of 1 indicates minimal interest or excitement, while 10 indicates an extremely compelling or can't-miss event.\n\n"
    )

    user_prompt = (
        "Return a valid JSON array (with double quotes around both keys and string values). "
        "No extra keys, no single quotes. For example: "
        '[{"rating":10,"title":"Some Title","description":"Some Description"}]\n\n'
        "Now, here are the events:\n"
        f"{combined_event_descriptions}\n\n"
        "In that same format, produce a JSON array with one object per event, in order. "
        "No extra keys are allowed. "
        "No text outside of valid JSON. "
        "If the text description contains any double quotes, that will break the JSON format, so be sure to strip / remove them. "
        "The JSON MUST BE VALID, and complete!"
        "Do not add ```json or ```"
    )

    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        raw_response = completion.choices[0].message.content.strip()
        try:
            raw_response = replace_json_gates(raw_response)
            data = json.loads(raw_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON or Python literal: {e}")
            data = []

        if not isinstance(data, list) or len(data) != len(events):
            logger.warning("AI returned different # of objects than # of events. Using defaults.")
            data = [
                {
                    "rating": 5,
                    "title": ev["title"],
                    "description": ev["description"]
                }
                for ev in events
            ]

        for ev, ai_obj in zip(events, data):
            ev["rating"] = ai_obj.get("rating", 5)

    except Exception as exc:
        logger.error(f"Error calling GPT for scoring: {exc}")

    events.sort(key=lambda e: e.get("rating", 0), reverse=True)
    return events


def limit_two_per_venue(events: t.List[t.Dict[str, t.Any]]) -> t.List[t.Dict[str, t.Any]]:
    """
    From the scored list (descending by 'interestingness'), keep at most two events per venue (location).
    """
    result = []
    count_by_venue = {}

    for ev in events:
        venue = ev.get("sender_name", "unknown")
        if count_by_venue.get(venue, 0) < 2:
            result.append(ev)
            count_by_venue[venue] = count_by_venue.get(venue, 0) + 1

    logger.info(f"{len(result)} events remain after limiting to 2 per venue.")
    return result


def add_rows_to_newsletter_events(events: t.List[t.Dict[str, t.Any]]) -> None:
    """
    For each selected event, insert one row into `newsletter_events`.
    References the event's id with `event_id`.
    """
    for ev in events:
        event_id = ev["id"]  # The `events.id` primary key
        try:
            supabase.table("newsletter_events").insert(
                {"event_id": event_id}  # created_date will default to CURRENT_DATE, if so configured
            ).execute()
        except Exception as exc:
            logger.error(f"Failed to insert event {event_id} into newsletter_events: {exc}")


def generate_newsletter_text(events: t.List[t.Dict[str, t.Any]]) -> str:
    events_summary = ""
    for idx, ev in enumerate(events):
        title = ev.get("title", "Untitled Event")
        date = ev.get("event_start_date", "No Date")
        location = ev.get("sender_name", "No Location")
        desc = ev.get("description", "")
        events_summary += (
            f"{idx + 1}. Title: {title}\n"
            f"   Date: {date}\n"
            f"   Location: {location}\n"
            f"   Description: {desc}\n\n"
        )

    system_prompt = (
        "You are an AI assistant that writes a structured newsletter about upcoming events. "
        "Format each event in a consistent multi-line structure as follows:\n\n"
        "[ONE RELEVANT EMOJI] [TITLE]\n"
        "📍 [VENUE NAME] - [START DATE (in format e.g. March 14th, 2025)]\n"
        "[DESCRIPTION - ONE OR TWO SENTENCES MAX]\n"
        "\n\n"
        "Make sure to separate each event with a blank line. "
        "Keep descriptions concise, representative, and engaging. Truthfulness is essential. "
        "Descriptions should never be in the first person (e.g. don't allow words like 'us' or 'we' or 'I')"
        "Output only plain text, no JSON, code blocks, or markdown."
        "Do not use markdown formatting like bold or italics."
    )

    user_prompt = (
        "Here is the list of events:\n\n"
        f"{events_summary}\n"
        "Please produce a structured newsletter with each event in the expected format:\n\n"
    )

    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        newsletter_text = completion.choices[0].message.content.strip()
        logger.info("Generated newsletter text via GPT.")
        return newsletter_text

    except Exception as exc:
        logger.error(f"Error generating newsletter text: {exc}")
        return "(Failed to generate newsletter text.)"


def create_newsletter_record(body: str, is_dev: bool) -> int:
    """
    Inserts a single newsletter row into the 'newsletter' table
    with the summarised text block as `body` and the `is_dev` flag.
    Returns the newly created newsletter.id (integer).
    """
    try:
        current_date = datetime.datetime.utcnow().isoformat()
        response = supabase.table("newsletter").insert({
            "body": body,
            "created_date": current_date,
            "is_dev": is_dev
        }).execute()
        new_record = response.data[0]
        newsletter_id = new_record["id"]
        logger.info(f"Created {'dev' if is_dev else 'production'} newsletter row with id={newsletter_id}")
        return newsletter_id
    except Exception as exc:
        logger.error(f"Failed to insert newsletter record: {exc}")
        raise


def add_events_to_newsletter(newsletter_id: int, events: t.List[t.Dict[str, t.Any]]) -> None:
    """
    For each selected event, insert a row into `newsletter_events`.
    This links the single newsletter row to each included event.
    """
    current_date = datetime.date.today().isoformat()
    rows = []
    for ev in events:
        rows.append({
            "newsletter_id": newsletter_id,
            "event_id": ev["id"],
            "created_date": current_date
        })

    try:
        supabase.table("newsletter_events").insert(rows).execute()
        logger.info(f"Inserted {len(rows)} row(s) into newsletter_events for newsletter_id={newsletter_id}")
    except Exception as exc:
        logger.error(f"Failed to insert into newsletter_events: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a newsletter.")
    parser.add_argument("--dev", action="store_true", help="Create a dev newsletter if set.")
    return parser.parse_args()


def main(min_event_count: int = 8, max_event_count: int = 15) -> None:
    args = parse_args()

    is_dev = True if args.dev else IS_DEV
    logger.info(f"Running newsletter pipeline. is_dev={is_dev}")

    if is_dev:
        min_event_count = 1
        max_event_count = 50

    # 1) Fetch recent events
    recent_events = fetch_events_last_7_days()
    # 2) Filter out recurring or used events
    filtered_events = filter_non_recurring_upcoming(recent_events)
    # 3) Score with AI
    scored_events = score_events_with_ai(filtered_events)
    # 4) Limit to 2 per venue
    limited_by_venue = limit_two_per_venue(scored_events)
    # 5) Hard limit
    final_events = limited_by_venue[:max_event_count]

    logger.info("=== Selected Events ===")
    for e in final_events:
        logger.info(
            f"Score {e['rating']}: {e['title']} by {e.get('sender_name') or 'Unknown Sender'}"
            f" @ {e['location']} on {e['event_start_date']}"
        )

    if len(final_events) < min_event_count:
        # Not enough events => do not create newsletter
        logger.info(f"Skipping newsletter creation; found only {len(final_events)} events (< {min_event_count}).")
        return

    # 6) Generate text
    newsletter_text = generate_newsletter_text(final_events)

    # 7) Insert a newsletter row
    newsletter_id = create_newsletter_record(newsletter_text, is_dev=is_dev)

    # 8) Add those events to newsletter_events
    add_events_to_newsletter(newsletter_id, final_events)
    logger.info("Newsletter pipeline complete.")


if __name__ == "__main__":
    main()
