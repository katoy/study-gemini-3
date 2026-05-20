"""Type definitions for NHK radio data."""

from dataclasses import dataclass
from typing import TypedDict


class ApiProgramRaw(TypedDict, total=False):
    """Raw program data from NHK API."""

    site_id: str
    series_site_id: str
    corner_site_id: str
    title: str
    corner_name: str
    onair_date: str
    started_at: str
    genre_label: str
    thumbnail_url: str
    description: str


@dataclass(frozen=True)
class Program:
    """Represents an NHK radio program / series."""

    title: str
    display_title: str
    display_date: str
    site_id: str
    corner_id: str
    url: str
    genre: str | None = None
    genre_label: str = ""
    corner_name: str | None = None
    onair_date: str | None = None
    started_at: str | None = None


@dataclass(frozen=True)
class Episode:
    """Represents a single broadcast episode."""

    id: str
    title: str
    display_title: str
    date: str
    display_date: str
    broadcast_time: str
    duration_str: str
    url: str


@dataclass
class Progress:
    """Download progress tracking."""

    percent: float | None
    eta: str | None
    status: str | None = None
