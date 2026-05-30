"""共通コード: templates・定数・ビジネスロジック・ヘルパー関数。"""

import dataclasses
import json
import logging
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates

from nhk_radio_web.config import load_storage_limit, save_storage_limit
from nhk_radio_web.constants import GENRE_LABELS
from nhk_radio_web.core import fetch_program_list_async, get_episode_list, get_genres
from nhk_radio_web.downloads import is_episode_downloaded
from nhk_radio_web.job_manager import JobManager
from nhk_radio_web.types import Program

from ..api_models import (
    DownloadJobCreateRequest,
    DownloadJobData,
    DownloadProgressData,
    EpisodeData,
    ProgramData,
    SettingsData,
    SettingsUpdateRequest,
)

logger = logging.getLogger(__name__)

# テストで patch 可能にするため、import した関数を re-export
__all__ = [
    "fetch_program_list_async",
    "get_episode_list",
    "is_episode_downloaded",
    "load_storage_limit",
    "save_storage_limit",
    "templates",
    "UNCLASSIFIED_GENRE",
    "PUBLIC_UNCLASSIFIED_GENRE",
    "LimitQuery",
    "JobStatusQuery",
]

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

UNCLASSIFIED_GENRE = "__unclassified__"
PUBLIC_UNCLASSIFIED_GENRE = "unclassified"

LimitQuery = Annotated[int | None, Query(ge=1, le=200)]
JobStatusQuery = Annotated[
    Literal["pending", "downloading", "done", "error", "cancelled"] | None,
    Query(alias="status"),
]


def _dataclass_to_json(obj) -> str:
    """dataclass を JSON 文字列に変換する Jinja2 フィルタ用。"""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return json.dumps(dataclasses.asdict(obj), ensure_ascii=False)
    return json.dumps(obj, ensure_ascii=False)


def _job_to_payload(job_id: str, job: dict) -> dict:
    """ジョブを WebSocket 送信用 payload に変換。"""
    return {
        "job_id": job_id,
        "status": job["status"],
        "title": job["episode"].title,
        "error": job.get("error", ""),
        "progress": (
            {"percent": job["progress"].percent, "eta": job["progress"].eta}
            if job.get("progress")
            else None
        ),
    }


templates.env.filters["tojson"] = _dataclass_to_json


def _matches_genre(program: Program, genre: str) -> bool:
    if genre == UNCLASSIFIED_GENRE:
        return not program.genres
    return genre in program.genres


def _build_genre_options() -> list[dict[str, str]]:
    genre_options = [{"value": "", "label": "すべて"}]
    for genre in get_genres():
        genre_options.append({"value": genre, "label": GENRE_LABELS.get(genre, genre)})
    genre_options.append({"value": UNCLASSIFIED_GENRE, "label": "未分類"})
    return genre_options


def _to_public_genre_id(genre: str) -> str:
    if genre == UNCLASSIFIED_GENRE:
        return PUBLIC_UNCLASSIFIED_GENRE
    return genre


def _from_public_genre_id(genre: str) -> str:
    if genre == PUBLIC_UNCLASSIFIED_GENRE:
        return UNCLASSIFIED_GENRE
    return genre


def _genre_counts(programs: list[Program]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for program in programs:
        if program.genres:
            for genre in program.genres:
                counts[genre] = counts.get(genre, 0) + 1
        else:
            counts[UNCLASSIFIED_GENRE] = counts.get(UNCLASSIFIED_GENRE, 0) + 1
    return counts


def _program_id(program: Program) -> str:
    return f"{program.site_id}_{program.corner_id}"


def _parse_program_id(program_id: str) -> tuple[str, str]:
    parts = program_id.split("_", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid program_id")
    return parts[0], parts[1]


def _find_program(programs: list[Program], site_id: str, corner_id: str) -> Program | None:
    return next(
        (program for program in programs if program.site_id == site_id and program.corner_id == corner_id),
        None,
    )


def _api_genres(program: Program) -> list[str]:
    if program.genres:
        return [_to_public_genre_id(genre) for genre in program.genres]
    return [PUBLIC_UNCLASSIFIED_GENRE]


def _api_genre_labels(program: Program) -> list[str]:
    if program.genre_labels:
        return list(program.genre_labels)
    return ["未分類"]


def _program_to_api_data(program: Program) -> ProgramData:
    genres = _api_genres(program)
    genre_labels = _api_genre_labels(program)
    primary_genre = genres[0] if genres else None
    primary_genre_label = genre_labels[0] if genre_labels else None
    return ProgramData(
        id=_program_id(program),
        title=program.title,
        display_title=program.display_title,
        display_date=program.display_date,
        site_id=program.site_id,
        corner_id=program.corner_id,
        url=program.url,
        genres=genres,
        genre_labels=genre_labels,
        primary_genre=primary_genre,
        primary_genre_label=primary_genre_label,
        is_unclassified=not program.genres,
        corner_name=program.corner_name,
        onair_date=program.onair_date,
        started_at=program.started_at,
        broadcast=program.broadcast,
    )


def _episode_to_api_data(episode, downloaded: bool | None = None) -> EpisodeData:
    return EpisodeData(
        id=episode.id,
        title=episode.title,
        display_title=episode.display_title,
        date=episode.date,
        display_date=episode.display_date,
        broadcast_time=episode.broadcast_time,
        duration_str=episode.duration_str,
        url=episode.url,
        downloaded=downloaded,
    )


def _job_to_api_data(job_id: str, job: dict[str, Any]) -> DownloadJobData:
    progress = job.get("progress")
    program = job["program"]
    episode = job["episode"]
    return DownloadJobData(
        id=job_id,
        status=job["status"],
        error=job.get("error", ""),
        program_id=_program_id(program),
        program=_program_to_api_data(program),
        episode=_episode_to_api_data(episode),
        progress=(
            DownloadProgressData(percent=progress.percent, eta=progress.eta, status=progress.status)
            if progress
            else None
        ),
        file_path=job.get("file_path"),
    )


def _settings_payload(storage_limit_bytes: int) -> SettingsData:
    return SettingsData(
        storage_limit_bytes=storage_limit_bytes,
        storage_limit_gb=storage_limit_bytes / (1024 ** 3),
    )


async def _all_programs_dep() -> list[Program]:
    return await fetch_program_list_async(None)


def _job_manager_dep(request: Request) -> JobManager:
    return request.app.state.job_manager


async def _program_dep(program_id: str, all_programs: Annotated[list[Program], Depends(_all_programs_dep)]) -> Program:
    site_id, corner_id = _parse_program_id(program_id)
    program = _find_program(all_programs, site_id, corner_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return program


def _create_download_job_from_models(
    payload: DownloadJobCreateRequest,
    job_manager: JobManager,
    background_tasks: BackgroundTasks,
) -> tuple[str, dict[str, Any]]:
    program = payload.program.to_domain()
    episode = payload.episode.to_domain()
    job_id = job_manager.enqueue(program, episode)
    background_tasks.add_task(job_manager.start, job_id)
    job = job_manager.status_snapshot(job_id)
    assert job is not None
    return job_id, job


def _update_storage_limit(request: Request, payload: SettingsUpdateRequest) -> SettingsData:
    storage_limit_bytes = int(payload.storage_limit_gb * (1024 ** 3))
    success = save_storage_limit(storage_limit_bytes)
    if not success:
        raise HTTPException(status_code=500, detail="設定の保存に失敗しました")

    request.app.state.storage_limit = storage_limit_bytes
    logger.info(f"ストレージ容量上限を更新: {payload.storage_limit_gb} GB")
    return _settings_payload(storage_limit_bytes)
