def is_complete(ev: dict, is_agg: bool) -> bool:
    if not all(ev.get(k) for k in ("title", "start_date", "location_type")):
        return False
    if ev["parsing_confidence_score"] < 0.30:
        return False

    if is_agg:
        if not ev.get("organizer_name"):
            return False
        if ev["location_type"] == "venue" and not ev.get("location_address_verbatim"):
            return False
        if not (ev.get("event_url") or ev.get("booking_url")):
            return False
    return True


def extract_events(body, date_str, msg_id, is_agg):
    raw = call_llm_initial(body, date_str, is_agg)
    final = []

    for ev in raw:
        # optional single enrichment call
        if is_agg and needs_enrichment(ev):
            try:
                ev.update(web_search_patch(ev))  # one GPT-4o search call
            except Exception:
                pass  # leave as-is

        if is_complete(ev, is_agg):
            final.append(Event(**ev, email_message_id=msg_id))
        else:
            logger.info("Skipped incomplete event: %s", ev.get("title"))

    return final
