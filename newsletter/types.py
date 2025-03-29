from pydantic import BaseModel
import typing as ta
from datetime import date


class Event(BaseModel):
    title: str
    event_start_date: ta.Optional[date] = None
    event_end_date: ta.Optional[date] = None
    location: str
    event_type: str
    description: str
    description_verbatim: str
    is_event_course: ta.Optional[bool] = None
    is_event_recurring: ta.Optional[bool] = None
    event_recur_freq: ta.Optional[str] = None
    llm_rating: ta.Optional[int] = None
    event_time_of_day: ta.Optional[str] = None
    venue_name: ta.Optional[str] = None


class Events(BaseModel):
    events: ta.List[Event]
