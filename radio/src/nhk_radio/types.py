"""Type definitions for NHK radio data."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypedDict


def _normalize_string_tuple(values: object, fallback: str | None = None) -> tuple[str, ...]:
    items: list[str] = []

    def add(value: object) -> None:
        text = str(value or "").strip()
        if text and text not in items:
            items.append(text)

    if isinstance(values, str):
        add(values)
    elif isinstance(values, Iterable):  # pragma: no cover
        for value in values:
            add(value)

    if fallback:
        add(fallback)

    return tuple(items)


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
    genres: tuple[str, ...] = ()
    genre_labels: tuple[str, ...] = ()
    corner_name: str | None = None
    onair_date: str | None = None
    started_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "genres", _normalize_string_tuple(self.genres, self.genre))
        object.__setattr__(
            self,
            "genre_labels",
            _normalize_string_tuple(self.genre_labels, self.genre_label),
        )


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
