"""Type definitions for NHK radio data."""

from dataclasses import dataclass, field
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
    radio_broadcast: str


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
    genres: list[str] = field(default_factory=list)
    genre_labels: list[str] = field(default_factory=list)
    corner_name: str | None = None
    onair_date: str | None = None
    started_at: str | None = None
    broadcast: str = "AM"

    def __post_init__(self) -> None:
        if not self.genres and self.genre is not None:
            object.__setattr__(self, "genres", [self.genre])
        if not self.genre_labels and self.genre_label:
            object.__setattr__(self, "genre_labels", [self.genre_label])

    @property
    def genre_pairs(self) -> list[tuple[str, str]]:
        return list(zip(self.genres, self.genre_labels, strict=True))


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
