"""Type definitions for NHK radio data."""

from typing import TypedDict, NotRequired

class Program(TypedDict):
    title: str
    display_title: str
    display_date: str
    site_id: str
    corner_id: str
    url: str
    genre: str | None
    genre_label: str
    corner_name: NotRequired[str]
    onair_date: NotRequired[str]
    started_at: NotRequired[str]

class Episode(TypedDict):
    id: str
    title: str
    display_title: str
    date: str
    display_date: str
    broadcast_time: str
    duration_str: str
    url: str
