from pydantic import BaseModel
import typing as ta

class Event(BaseModel):
    """
    Pydantic model for structured event extraction.
    """
    title: str
    event_date: str
    location: str
    event_type: str
    description: str
    email_message_id: ta.Optional[str] = None


class Events(BaseModel):
    events: list[Event]
