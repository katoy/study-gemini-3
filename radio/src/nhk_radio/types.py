"""Type definitions for NHK radio data."""

from dataclasses import dataclass, field
from typing import Any


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
    extra_data: dict[str, Any] = field(default_factory=dict)


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
    extra_data: dict[str, Any] = field(default_factory=dict)
