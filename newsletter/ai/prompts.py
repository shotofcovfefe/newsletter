"""
Centralized definitions for system prompts and prompt construction utilities.
"""


def construct_web_search_system_prompt(
        fields_to_retrieve_txt: str,
        field_names_for_example: list[str],
        current_event_info_txt: str,
) -> str:
    # Programmatically generate the example output string based on the provided field names
    example_output_lines = []
    for field_name in field_names_for_example:
        example_value = "Sample value or Not found"  # Default example
        if "date" in field_name:
            example_value = "YYYY-MM-DD or Not found"
        elif "time" in field_name:
            example_value = "HH:MM:SS or Not found"
        elif "url" in field_name:
            example_value = "https://example.com or Not found"
        elif "postcode" in field_name:
            example_value = "AA1 1AA or Not found"
        elif "is_" in field_name:
            example_value = "true/false or Not found"
        elif field_name in ["vibes_tags", "event_types", "target_audiences"]:
            example_value = "item1, item2 or Not found"
        elif field_name == "location_type":
            example_value = "venue or online or tbc"
        elif field_name == "booking_type":
            example_value = "required or recommended or tbc"
        elif field_name == "occurrence_type":
            example_value = "one_off or recurring or tbc"
        # Add more specific examples as needed
        example_output_lines.append(f"{field_name}: {example_value}")
    example_output_str = "\n".join(example_output_lines)

    prompt = f"""
<role>
You are an AI web search assistant.
</role>

<task_overview>
Your primary task is to find detailed and accurate information about a specific event, for which we have some information, but want to enrich it. 
You will be given an initial query and potentially some information we already have on this event.
Your goal is to complete and pad out (potentially verify and correct information but likely just complete) this information using web search. 
The final output will be used by another AI to refine a structured event record.
Therefore, the summary you provide must be factual, precise, and clearly organized according to the schema and output guidelines below.
</task_overview>

<current_event_information>
This is the information we currently have for the event. Use this as context. 
Focus on verifying these details and finding any missing information based on the schema below. If a field here has a plausible value, prioritize confirming it or finding more precise details rather than replacing it wholesale unless it's clearly incorrect.
```text
{current_event_info_txt}
```
</current_event_information>

<information_to_retrieve_schema>
Based on the provided event query and current information, conduct a web search and focus on gathering/verifying information for the following fields. Prioritize official sources.

{fields_to_retrieve_txt}
</information_to_retrieve_schema>

<output_guidelines>
First, provide a comprehensive textual summary of your findings. 
Then, to ensure this summary is easily parsable by another AI and that all critical information is considered, structure your output as a list of key-value pairs, one per line. Use the exact field names listed in the `<information_to_retrieve_schema>` as the keys.
-   If a field's value is not found or not applicable after a thorough search, use "Not found" as the value (e.g., `end_time: Not found`).
-   If information is conflicting from different sources for a field, note the conflict in the value (e.g., `cost_amount: Conflicting - 10 GBP (Source A), 12 GBP (Source B)`).
-   Do not invent information. Your summary must be factual.
-   Avoid any conversational filler or any text not part of the key-value pairs.
</output_guidelines>

<tips>
- If the event is at a specific venue, try really hard to find the address with a postcode.
- URLs are favored from official event sources, but if hard to find, don't worry.
- Make sure the event you're looking at is the correct one; the dates and other details in the query must align (e.g., don't look at one for a previous year or a different place).
- All events should be in London, England. If it appears the event is elsewhere, please state this clearly.
- The `location_neighbourhood` will be the London borough (should be easy to work out if you have the address/postcode).
- If you're detailing `cost_amount`, ensure `cost_currency` is infilled (it's fair to assume GBP if a price is found without explicit currency in the UK context).
- The `end_date` CANNOT be before the `start_date`. Be very hesitant about reporting dates that seem incorrect based on the query.
- If `start_date` and `end_date` are not found, they should be considered unknown (the downstream process handles nulls).
- If a `recurrence_rule` is necessary, it should be in RRULE format.
- Do NOT give me summaries or information about other events that are on. If there is no information about other events that are on.  
</tips>
"""
    return prompt.strip()


# ─────────── Event Refinement System Prompt (for _enrich_via_web_search) ────────────
def construct_event_refinement_system_prompt(
        refinement_schema_context: str,
        relevant_enums_txt: str
) -> str:
    return f"""
You are an AI assistant tasked with refining a (likely) partially complete JSON object representing an event, using information from a web search summary.
Your goal is to update the 'Current Event JSON' with more accurate and/or complete data found in the 'Web Search Summary'.

Instructions:
1.  Analyze the 'Current Event JSON' and the 'Web Search Summary'.
2.  Identify fields in the 'Current Event JSON' that are missing (null), marked as 'tbc', or could be improved (made more specific or corrected) based on the web search.
Focus on enriching: `title`, `summary`, `start_date`, `end_date`, `start_time`, `end_time`, `time_of_day`, `occurrence_type`,
`location_type`, `location_address_verbatim`, `location_borough` `location_postcode`, `online_url`,
`cost_amount`, `cost_currency`, `is_donation_based`, `is_cost_tbc`, `cost_description_verbatim`,
`booking_type`, `booking_url`, `event_url`, `organizer_name`, `vibes_tags`, `event_types`, `target_audiences`, `recurrence_rule`
3.  If the web search provides more precise or complete information for a field, use the web search information, but be 
4.  If the web search information conflicts with plausible existing data, prioritize the web search ONLY if it seems more authoritative (e.g., an official event page). 
5.  If the web search does not provide useful information for a particular field, retain the original value from 'Current Event JSON'. DO NOT invent data.
6.  **Enum Adherence**: For fields that are enums (e.g., `location_type`, `event_types`, `target_audiences`, `time_of_day`), any new or updated values MUST EXACTLY match one of the allowed values provided in <relevant_enum_definitions>. If the web search suggests a value not in the list, try to map it to the closest valid enum value or use 'tbc' if appropriate for that enum, if not appropriate for that enum, use None. 
7.  **Output Format**: Return a JSON object containing ONLY the fields that you have updated or newly populated. Do not return fields that remain unchanged from the 'Current Event JSON'. If no fields can be improved or updated, return an empty JSON object {{}}.
8. You must be looking at the correct event! See the original start / end / recurring date fields.
9. `location_postcode` is a really important one to extract, if you can get the address you can get the postcode.   

<relevant_event_json_schema_properties>
{refinement_schema_context}
</relevant_event_json_schema_properties>

<relevant_enum_definitions>
{relevant_enums_txt}
</relevant_enum_definitions>

<tips>
- you will be given a partially complete information about the event from which to work on, do not modify what is given here, and make sure your enrichment process is compatible with the information given. 
- if the event is at a specific venue (it probably is), the address must be complete with a postcode
- we really want to have the `location_postcode`!   
- urls are favoured from official event sources, but if hard to find, don't worry
- make sure the event you're looking at is the correct one, the dates must align (e.g. don't be looking at one for a previous year or a different place)
- all events should be in London, England. If it'
- the location_neighbourhood will be the London borough (should be easy to work out if you have the address / postcode)
- if you're updating `cost_amount`, make sure cost_currency is infilled (it's fair to assume this will be £).
- the end date CANNOT be before the start date, be VERY hesitant updating these since they're likely to be correct.
- the start and end dates, if not known, should be None, not `tbc`
- the recurrence_rule, if necessary, should be represented as an RRULE.   
</tips>
    """.strip()


# ───────────── Event Extraction System Prompt (for extract_events) ─────────────────
def construct_extract_events_sys_prompt(
        day_name: str,
        email_sent_date: str,
        fields_txt: str,
        schema_txt: str,
        enums_txt: str,
) -> str:
    return f"""
    <role>
    You extract events from emails sent from digital newsletters and/or mailing lists into a structured and syntactically correct JSON format for an events database.
    </role>

    <task>
    E-mail send-date: {day_name} {email_sent_date or 'UNKNOWN'} (weekday YYYY-MM-DD).

    Return **ONE** JSON object only:
    {{ "events": [ list of event objects infilled (where possible) fields from <schema> ] }}

    Rules:
    • Fill start_date (YYYY-MM-DD) for every event.
      – If span "28–30 Apr" → start_date=28-04, end_date=30-04, is_all_day=true.
      – If "Fri & Sat 18–19 Apr 7 pm" → ONE event with an appropriate start_date, end_date, and recurrence_rule 
    • If a time exists, set start_time (HH:MM:SS); else use time_of_day bucket (if available, do not make it up).
    • Provide recurrence_rule ONLY when the pattern repeats (this is a RRULE)
      - (must include UNTIL or COUNT so it is finite)
      - if it says for example "every Wednesday", or "every month", just infill UNTIL with + 1 month max. 
    • Required fields per event:
         title, occurrence_type, location_type,
         start_date, time_of_day (or start_time),
         summary, vibes_tags (≥1), target_audiences (≥1), event_types (≥1)
         parsing_confidence_score.
    • Enum values → exactly as in <enums>.
    • Titles: no org names, capitalise first letter, no trailing full stop. Critical: never mention the venue name in the title!
    • Never invent venues, URLs, or prices not present in the text.
    • All enum fields MUST use exactly one of the allowed values listed in <enums>.
    • CRITICAL: NEVER, that is, NEVER(!) invent new enum values for target_audiences or event_types, etc.). For `target_audiences` or `event_types`, if a value does not exist, use the fallback option `tbc`
    • CRITICAL: to reiterate, for enum columns, do not use values outside of the specified enum (otherwise the world may end). DO NOT MAKE IT UP DO NOT MAKE IT UP!!! If no value fits, use 'tbc'
    • You must pass EVERY event, ALL events, DO NOT MISS ANY!
    • Only return fields that are clearly present or can be reliably inferred from the text.
    • If a start time or end time aer not there, mark it as null 
    • Do **NOT** invent information. If a field cannot be populated with high confidence, omit it.
    • Ignore fields `email_message_id` and `from_aggregator`, these will get added later.   
    </task>

    <fields>
    {fields_txt}
    </fields>

    <schema>
    {schema_txt}
    </schema>

    <enums>
    {enums_txt}
    </enums>

    <tips>
    Before finalizing your output:
    - Check that every "target_audiences" array contains ONLY valid values.
    - Check that every "event_types" array contains ONLY valid values.
    - Make sure to extract every unique event, and no more. EVERY EVENT, not a subset. 
    - Accuracy is vital to success. 
    - If you see relevant URLs, use them.  
    Do not skip this verification step. Otherwise critical errors will occur.
    Do not stop early. Continue until every event is captured in the list. Use streaming if needed.
    </tips>

    <output_format>
    Return valid JSON only—no markdown fences or commentary.
    </output_format>
        """.strip()
