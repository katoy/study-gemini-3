"""Pydantic models for FastAPI endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from nhk_radio_web.types import Episode, Program


class ProgramInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    display_title: str
    display_date: str
    site_id: str
    corner_id: str
    url: str
    genre: str | None = None
    genre_label: str = ""
    genres: list[str] = Field(default_factory=list)
    genre_labels: list[str] = Field(default_factory=list)
    corner_name: str | None = None
    onair_date: str | None = None
    started_at: str | None = None
    broadcast: str = "AM"

    def to_domain(self) -> Program:
        return Program(**self.model_dump())


class EpisodeInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    display_title: str
    date: str
    display_date: str
    broadcast_time: str
    duration_str: str
    url: str

    def to_domain(self) -> Episode:
        return Episode(**self.model_dump())


class DownloadJobCreateRequest(BaseModel):
    program: ProgramInput
    episode: EpisodeInput


class SettingsUpdateRequest(BaseModel):
    storage_limit_gb: float = Field(gt=0)


class HealthData(BaseModel):
    status: str
    version: str


class HealthResponse(BaseModel):
    data: HealthData


class MetaData(BaseModel):
    name: str
    version: str
    docs_url: str | None
    openapi_url: str | None
    redoc_url: str | None
    capabilities: list[str]


class MetaResponse(BaseModel):
    data: MetaData


class GenreData(BaseModel):
    id: str
    label: str
    count: int
    is_unclassified: bool


class CountMeta(BaseModel):
    count: int


class GenreListResponse(BaseModel):
    data: list[GenreData]
    meta: CountMeta


class ProgramData(BaseModel):
    id: str
    title: str
    display_title: str
    display_date: str
    site_id: str
    corner_id: str
    url: str
    genres: list[str]
    genre_labels: list[str]
    primary_genre: str | None
    primary_genre_label: str | None
    is_unclassified: bool
    corner_name: str | None
    onair_date: str | None
    started_at: str | None
    broadcast: str


class ProgramDetailResponse(BaseModel):
    data: ProgramData


class ProgramFiltersMeta(BaseModel):
    genre: str | None
    q: str | None


class ProgramListMeta(BaseModel):
    count: int
    filters: ProgramFiltersMeta


class ProgramListResponse(BaseModel):
    data: list[ProgramData]
    meta: ProgramListMeta


class EpisodeData(BaseModel):
    id: str
    title: str
    display_title: str
    date: str
    display_date: str
    broadcast_time: str
    duration_str: str
    url: str
    downloaded: bool | None = None


class EpisodeListMeta(BaseModel):
    count: int
    source: str
    program_id: str
    q: str | None


class EpisodeListResponse(BaseModel):
    data: list[EpisodeData]
    meta: EpisodeListMeta


class EpisodeDetailMeta(BaseModel):
    source: str
    program_id: str


class EpisodeDetailResponse(BaseModel):
    data: EpisodeData
    meta: EpisodeDetailMeta


class DownloadProgressData(BaseModel):
    percent: float | None
    eta: str | None
    status: str | None


class DownloadJobData(BaseModel):
    id: str
    status: str
    error: str
    program_id: str
    program: ProgramData
    episode: EpisodeData
    progress: DownloadProgressData | None
    file_path: str | None = None


class DownloadJobResponse(BaseModel):
    data: DownloadJobData


class DownloadJobListMeta(BaseModel):
    count: int
    status: str | None


class DownloadJobListResponse(BaseModel):
    data: list[DownloadJobData]
    meta: DownloadJobListMeta


class SettingsData(BaseModel):
    storage_limit_bytes: int
    storage_limit_gb: float


class SettingsResponse(BaseModel):
    data: SettingsData


class CacheStatusData(BaseModel):
    size_bytes: int
    last_modified: int


class CacheStatusResponse(BaseModel):
    data: CacheStatusData


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
