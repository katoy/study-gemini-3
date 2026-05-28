"""FastAPI route definitions."""

import dataclasses
import fnmatch
import json
import logging
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from nhk_radio_web import __version__
from nhk_radio_web.cache import clear_episode_cache, clear_program_cache
from nhk_radio_web.config import _default_download_dir, load_storage_limit, save_storage_limit
from nhk_radio_web.constants import GENRE_LABELS
from nhk_radio_web.core import fetch_program_list_async, get_episode_list, get_genres
from nhk_radio_web.downloads import _episode_output_identity, _program_search_dirs, is_episode_downloaded
from nhk_radio_web.help_content import render_help_html
from nhk_radio_web.job_manager import JobManager
from nhk_radio_web.search import filter_episodes, filter_programs
from nhk_radio_web.text import _safe_name
from nhk_radio_web.types import Episode, Program

from .api_models import (
    CountMeta,
    DownloadJobCreateRequest,
    DownloadJobData,
    DownloadJobListMeta,
    DownloadJobListResponse,
    DownloadJobResponse,
    DownloadProgressData,
    EpisodeData,
    EpisodeDetailMeta,
    EpisodeDetailResponse,
    EpisodeListMeta,
    EpisodeListResponse,
    GenreData,
    GenreListResponse,
    HealthData,
    HealthResponse,
    MetaData,
    MetaResponse,
    ProgramData,
    ProgramDetailResponse,
    ProgramFiltersMeta,
    ProgramListMeta,
    ProgramListResponse,
    SettingsData,
    SettingsResponse,
    SettingsUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()
api_v1_router = APIRouter(prefix="/api/v1", tags=["api-v1"])
UNCLASSIFIED_GENRE = "__unclassified__"
PUBLIC_UNCLASSIFIED_GENRE = "unclassified"

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _dataclass_to_json(obj) -> str:
    """dataclass を JSON 文字列に変換する Jinja2 フィルタ用。"""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return json.dumps(dataclasses.asdict(obj), ensure_ascii=False)
    return json.dumps(obj, ensure_ascii=False)


def _job_to_payload(job_id: str, job: dict) -> dict:
    """ジョブをWebSocket 送信用 payload に変換。"""
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


def _episode_to_api_data(episode: Episode, downloaded: bool | None = None) -> EpisodeData:
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


LimitQuery = Annotated[int | None, Query(ge=1, le=200)]
JobStatusQuery = Annotated[
    Literal["pending", "downloading", "done", "error", "cancelled"] | None,
    Query(alias="status"),
]


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    all_programs: Annotated[list[Program], Depends(_all_programs_dep)],
    genre: str = "",
):
    # 常にすべてのプログラムを取得（genre count 正確性のため）
    programs = [p for p in all_programs if _matches_genre(p, genre)] if genre else all_programs

    genre_counts = _genre_counts(all_programs)

    # ジャンルオプションを get_genres() から動的に生成
    genre_options = _build_genre_options()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "programs": programs,
            "all_programs": all_programs,
            "genre_counts": genre_counts,
            "genre_options": genre_options,
            "selected_genre": genre,
            "version": __version__,
        },
    )


@router.get("/programs", response_class=HTMLResponse)
async def programs_partial(
    request: Request,
    all_programs: Annotated[list[Program], Depends(_all_programs_dep)],
    genre: str = "",
    q: str = "",
):
    """htmx からのジャンルフィルタ更新リクエスト用。

    Query params:
        genre: ジャンルフィルタ
        q: 番組名検索キーワード
    """
    # ジャンルフィルタを適用
    programs = [p for p in all_programs if _matches_genre(p, genre)] if genre else all_programs

    # キーワード検索を適用
    if q:
        programs = filter_programs(programs, needle=q)

    return templates.TemplateResponse(
        request,
        "partials/program_list.html",
        {
            "programs": programs,
            "all_programs": all_programs,
            "selected_genre": genre,
        },
    )


@router.get("/programs/{program_id}/episodes", response_class=HTMLResponse)
async def episodes_partial(
    request: Request,
    all_programs: Annotated[list[Program], Depends(_all_programs_dep)],
    program_id: str,
    q: str = "",
):
    """htmx からのエピソード一覧取得リクエスト用。program_id は {site_id}_{corner_id}。

    Query params:
        q: エピソード検索キーワード
    """
    site_id, corner_id = _parse_program_id(program_id)

    program = _find_program(all_programs, site_id, corner_id)
    if program is None:
        # フォールバック: Program を最小構成で組み立てる
        from nhk_radio_web.constants import NHK_DETAIL_TMPL
        program = Program(
            title=program_id,
            display_title=program_id,
            display_date="",
            site_id=site_id,
            corner_id=corner_id,
            url=NHK_DETAIL_TMPL.format(site_id=site_id, corner_id=corner_id),
        )

    try:
        episodes, source = await get_episode_list(program)
    except RuntimeError as e:
        return templates.TemplateResponse(
            request,
            "partials/episode_list.html",
            {"program": program, "episodes_with_status": [], "error": str(e)},
        )

    # キーワード検索
    if q:
        episodes = filter_episodes(episodes, needle=q)

    output_dir = _default_download_dir()
    episodes_with_status = [
        {
            "episode": ep,
            "downloaded": is_episode_downloaded(output_dir, program, ep),
        }
        for ep in episodes
    ]

    return templates.TemplateResponse(
        request,
        "partials/episode_list.html",
        {
            "program": program,
            "episodes_with_status": episodes_with_status,
            "source": source,
            "error": None,
        },
    )


@api_v1_router.get("/health", response_model=HealthResponse)
async def api_v1_health():
    return HealthResponse(data=HealthData(status="ok", version=__version__))


@api_v1_router.get("/meta", response_model=MetaResponse)
async def api_v1_meta(request: Request):
    app = request.app
    return MetaResponse(
        data=MetaData(
            name="radio-web",
            version=__version__,
            docs_url=getattr(app, "docs_url", None),
            openapi_url=getattr(app, "openapi_url", None),
            redoc_url=getattr(app, "redoc_url", None),
            capabilities=[
                "genres",
                "programs",
                "episodes",
                "download_jobs",
                "settings",
                "websocket_jobs",
            ],
        )
    )


@api_v1_router.get("/genres", response_model=GenreListResponse)
async def api_v1_genres(all_programs: Annotated[list[Program], Depends(_all_programs_dep)]):
    genre_counts = _genre_counts(all_programs)
    options = _build_genre_options()
    return GenreListResponse(
        data=[
            GenreData(
                id=_to_public_genre_id(option["value"]),
                label=option["label"],
                count=genre_counts.get(option["value"], 0),
                is_unclassified=option["value"] == UNCLASSIFIED_GENRE,
            )
            for option in _build_genre_options()
            if option["value"]
        ],
        meta=CountMeta(count=len(options) - 1),
    )


@api_v1_router.get("/programs", response_model=ProgramListResponse)
async def api_v1_programs(
    all_programs: Annotated[list[Program], Depends(_all_programs_dep)],
    genre: Annotated[str, Query(description="ジャンル ID。未分類は unclassified")] = "",
    q: Annotated[str, Query(max_length=200)] = "",
    limit: LimitQuery = None,
):
    effective_genre = _from_public_genre_id(genre)
    programs = [p for p in all_programs if _matches_genre(p, effective_genre)] if effective_genre else all_programs
    if q:
        programs = filter_programs(programs, needle=q)
    if limit is not None:
        programs = programs[:limit]
    return ProgramListResponse(
        data=[_program_to_api_data(program) for program in programs],
        meta=ProgramListMeta(
            count=len(programs),
            filters=ProgramFiltersMeta(genre=genre or None, q=q or None),
        ),
    )


@api_v1_router.get("/programs/{program_id}", response_model=ProgramDetailResponse)
async def api_v1_program(program: Annotated[Program, Depends(_program_dep)]):
    return ProgramDetailResponse(data=_program_to_api_data(program))


@api_v1_router.get("/programs/{program_id}/episodes", response_model=EpisodeListResponse)
async def api_v1_program_episodes(
    program: Annotated[Program, Depends(_program_dep)],
    program_id: str,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: LimitQuery = None,
):
    try:
        episodes, source = await get_episode_list(program)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Episodes fetch failed: {e}") from e
    if q:
        episodes = filter_episodes(episodes, needle=q)
    if limit is not None:
        episodes = episodes[:limit]
    output_dir = _default_download_dir()
    episode_payloads = [
        _episode_to_api_data(episode, downloaded=is_episode_downloaded(output_dir, program, episode))
        for episode in episodes
    ]
    return EpisodeListResponse(
        data=episode_payloads,
        meta=EpisodeListMeta(count=len(episode_payloads), source=source, program_id=program_id, q=q or None),
    )


@api_v1_router.get("/programs/{program_id}/episodes/{episode_id}", response_model=EpisodeDetailResponse)
async def api_v1_program_episode(
    program: Annotated[Program, Depends(_program_dep)],
    program_id: str,
    episode_id: str,
):
    try:
        episodes, source = await get_episode_list(program)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Episodes fetch failed: {e}") from e
    episode = next((candidate for candidate in episodes if candidate.id == episode_id), None)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    output_dir = _default_download_dir()
    return EpisodeDetailResponse(
        data=_episode_to_api_data(episode, downloaded=is_episode_downloaded(output_dir, program, episode)),
        meta=EpisodeDetailMeta(source=source, program_id=program_id),
    )


@api_v1_router.post(
    "/download-jobs",
    response_model=DownloadJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def api_v1_create_download_job(
    payload: DownloadJobCreateRequest,
    background_tasks: BackgroundTasks,
    job_manager: Annotated[JobManager, Depends(_job_manager_dep)],
):
    job_id, job = _create_download_job_from_models(payload, job_manager, background_tasks)
    return DownloadJobResponse(data=_job_to_api_data(job_id, job))


@api_v1_router.get("/download-jobs", response_model=DownloadJobListResponse)
async def api_v1_download_jobs(
    job_manager: Annotated[JobManager, Depends(_job_manager_dep)],
    status_filter: JobStatusQuery = None,
    limit: LimitQuery = None,
):
    jobs: list[DownloadJobData] = []
    jobs_dict = job_manager.all_jobs()
    for job_id, job in reversed(list(jobs_dict.items())):
        if status_filter and job["status"] != status_filter:
            continue
        jobs.append(_job_to_api_data(job_id, job))
        if limit is not None and len(jobs) >= limit:
            break
    return DownloadJobListResponse(
        data=jobs,
        meta=DownloadJobListMeta(count=len(jobs), status=status_filter),
    )


@api_v1_router.get("/download-jobs/{job_id}", response_model=DownloadJobResponse)
async def api_v1_download_job(job_id: str, job_manager: Annotated[JobManager, Depends(_job_manager_dep)]):
    job = job_manager.status_snapshot(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return DownloadJobResponse(data=_job_to_api_data(job_id, job))


@api_v1_router.delete("/download-jobs/{job_id}", response_model=DownloadJobResponse)
async def api_v1_cancel_download_job(job_id: str, job_manager: Annotated[JobManager, Depends(_job_manager_dep)]):
    job = job_manager.status_snapshot(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await job_manager.cancel(job_id)
    cancelled_job = job_manager.status_snapshot(job_id)
    assert cancelled_job is not None
    return DownloadJobResponse(data=_job_to_api_data(job_id, cancelled_job))


@api_v1_router.delete("/download-jobs", response_model=DownloadJobListResponse)
async def api_v1_batch_delete_download_jobs(
    status: Annotated[str | None, Query()] = None,
    job_manager: Annotated[JobManager, Depends(_job_manager_dep)] = None,
):
    """複数ダウンロードジョブをバッチ削除。status フィルタで特定ステータスのみ削除。"""
    all_jobs = job_manager.all_jobs()
    deleted_jobs = []

    # ステータスでフィルタして削除
    for job_id, job in all_jobs.items():
        if status is None or job.get("status") == status:
            await job_manager.cancel(job_id)
            cancelled_job = job_manager.status_snapshot(job_id)
            if cancelled_job is not None:
                deleted_jobs.append(_job_to_api_data(job_id, cancelled_job))

    return DownloadJobListResponse(
        data=deleted_jobs,
        meta=DownloadJobListMeta(count=len(deleted_jobs), status=status),
    )


@api_v1_router.get("/download-jobs/{job_id}/file")
async def api_v1_download_job_file(request: Request, job_id: str):
    return await download_file(request, job_id)


@router.post("/download", response_class=HTMLResponse)
async def start_download(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: DownloadJobCreateRequest,
    job_manager: Annotated[JobManager, Depends(_job_manager_dep)],
):
    """単発ダウンロード: ジョブを登録してステータス HTML フラグメントを返す。"""
    job_id, job = _create_download_job_from_models(payload, job_manager, background_tasks)
    return templates.TemplateResponse(
        request,
        "partials/download_status.html",
        {"job_id": job_id, "job": job},
    )


@router.post("/download/batch", response_class=HTMLResponse)
async def batch_download(request: Request, background_tasks: BackgroundTasks):
    """一括ダウンロード: 複数エピソードをキューに登録。

    JSON body: {
        "program": {...},
        "episodes": [{...}, ...]
    }
    """
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=422, detail="リクエストボディが JSON ではありません") from e

    program_dict = body.get("program")
    episodes_list = body.get("episodes", [])
    if not isinstance(program_dict, dict) or not isinstance(episodes_list, list):
        raise HTTPException(status_code=422, detail="program と episodes は dict/list 形式で指定してください")

    try:
        program = Program(**{k: v for k, v in program_dict.items() if k in Program.__dataclass_fields__})
    except (TypeError, KeyError) as e:
        raise HTTPException(status_code=422, detail=f"プログラムデータが不正です: {e}") from e

    # エピソードを登録
    job_manager = request.app.state.job_manager
    job_ids = []
    for episode_dict in episodes_list:
        try:
            episode = Episode(**{k: v for k, v in episode_dict.items() if k in Episode.__dataclass_fields__})
            job_id = job_manager.enqueue(program, episode)
            job_ids.append(job_id)
            background_tasks.add_task(job_manager.start, job_id)
        except (TypeError, KeyError):
            # 不正なエピソードはスキップ
            continue

    # ジョブカード群を返す
    jobs_html = ""
    for job_id in job_ids:
        job = job_manager.status_snapshot(job_id)
        job_html = templates.get_template("partials/download_status.html").render(
            request=request,
            job_id=job_id,
            job=job,
        )
        jobs_html += job_html

    return HTMLResponse(content=jobs_html)


@router.get("/api/download/{job_id}/status", response_class=HTMLResponse)
async def download_status(request: Request, job_id: str):
    """htmx ポーリング用のダウンロード状態 HTML フラグメント。"""
    job_manager = request.app.state.job_manager
    job = job_manager.status_snapshot(job_id)
    if job is None:
        # ジョブが見つからない場合、ポーリングを停止（hx-polling-stop）
        from fastapi.responses import Response
        return Response(status_code=286, headers={"HX-Trigger": "hx-polling-stop"})
    return templates.TemplateResponse(
        request,
        "partials/download_status.html",
        {"job_id": job_id, "job": job},
    )


@router.post("/api/download/{job_id}/cancel", response_class=HTMLResponse)
async def cancel_download(request: Request, job_id: str):
    """ダウンロードジョブをキャンセルしてステータス HTML フラグメントを返す。"""
    job_manager = request.app.state.job_manager
    job = job_manager.status_snapshot(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        await job_manager.cancel(job_id)
    except Exception as e:
        logger.error(f"キャンセルエラー (job={job_id}): {e}")
        job = job_manager.status_snapshot(job_id)
        return templates.TemplateResponse(
            request,
            "partials/download_status.html",
            {"job_id": job_id, "job": job},
        )

    job = job_manager.status_snapshot(job_id)
    return templates.TemplateResponse(
        request,
        "partials/download_status.html",
        {"job_id": job_id, "job": job},
    )


@router.get("/api/download/{job_id}/file")
async def download_file(request: Request, job_id: str):
    """ダウンロード済みファイルをブラウザでダウンロード。"""
    job_manager = request.app.state.job_manager
    job = job_manager.status_snapshot(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    file_path = job.get("file_path")
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")

    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    # ファイル名を {放送日時}-{エピソード名}.mp3 に
    episode = job.get("episode")
    episode_date = (episode.date or "").strip() if episode else ""
    episode_title = (episode.title or episode.display_title or "episode") if episode else "episode"

    # エピソード名をセーフな形式に
    from nhk_radio_web.text import _safe_name
    safe_title = _safe_name(episode_title)

    filename = f"{episode_date}-{safe_title}.mp3" if episode_date else f"{safe_title}.mp3"

    response = FileResponse(
        path=str(file_path_obj),
        filename=filename,
        media_type="application/octet-stream"
    )
    # RFC 5987: UTF-8 エンコードされたファイル名を指定（URL エンコード必須）
    encoded_filename = quote(filename, safe="")
    response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
    return response


@router.get("/api/episodes/{site_id}/{corner_id}/{episode_id}/file")
async def download_episode_file(request: Request, site_id: str, corner_id: str, episode_id: str):
    """既にダウンロード済みのエピソードファイルをダウンロード。"""
    # キャッシュから Program を取得
    all_programs = await fetch_program_list_async(None)
    program = next(
        (p for p in all_programs if p.site_id == site_id and p.corner_id == corner_id),
        None,
    )
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")

    # キャッシュからエピソードを取得
    try:
        episodes, _ = await get_episode_list(program)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail="Episodes not found") from e

    episode = next(
        (ep for ep in episodes if ep.id == episode_id),
        None,
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    # ダウンロード済みファイルを探す
    output_dir = _default_download_dir()
    program_titles, episode_title, episode_date = _episode_output_identity(program, episode)
    for prog_dir in _program_search_dirs(output_dir, program):
        if not prog_dir.exists():
            continue
        for file_path in prog_dir.glob("*"):
            if file_path.is_file() and fnmatch.fnmatch(
                file_path.name,
                f"*{_safe_name(episode_title)}*",
            ):
                # ファイルが見つかった
                filename = (
                    f"{episode_date}-{_safe_name(episode.title or episode.display_title or 'episode')}.mp3"
                    if episode_date
                    else f"{_safe_name(episode.title or episode.display_title or 'episode')}.mp3"
                )
                response = FileResponse(
                    path=str(file_path),
                    filename=filename,
                    media_type="application/octet-stream"
                )
                # RFC 5987: UTF-8 エンコードされたファイル名を指定（URL エンコード必須）
                encoded_filename = quote(filename, safe="")
                response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
                return response

    raise HTTPException(status_code=404, detail="File not found")


@router.get("/downloads", response_class=HTMLResponse)
async def downloads_page(request: Request):
    """全ダウンロードジョブの一覧ページ。"""
    job_manager = request.app.state.job_manager
    return templates.TemplateResponse(
        request,
        "downloads.html",
        {"jobs": job_manager.all_jobs()},
    )


@router.get("/help", response_class=HTMLResponse)
async def help_page(request: Request):
    """ヘルプページ。"""
    help_html = render_help_html()
    return templates.TemplateResponse(
        request,
        "help.html",
        {"help_content": help_html},
    )


@router.post("/api/cache/clear", response_class=HTMLResponse)
async def clear_cache(request: Request, scope: str = "all"):
    """キャッシュをクリアし、リダイレクト。

    Query params:
        scope: "programs" | "episodes" | "all"
    """
    if scope in ("programs", "all"):
        clear_program_cache()
    if scope in ("episodes", "all"):
        clear_episode_cache()
    logger.info(f"キャッシュをクリア: {scope}")
    # JavaScript で処理するため、204 No Content を返す
    return HTMLResponse(status_code=204)


@router.get("/api/settings")
async def get_settings(request: Request):
    """現在の設定（ストレージ上限等）を JSON で返す。"""
    storage_limit = load_storage_limit()
    return JSONResponse(_settings_payload(storage_limit).model_dump())


@router.post("/api/settings")
async def save_settings(request: Request, payload: SettingsUpdateRequest):
    """設定（ストレージ上限等）を保存する。"""
    return JSONResponse(_update_storage_limit(request, payload).model_dump())


@api_v1_router.get("/settings", response_model=SettingsResponse)
async def api_v1_get_settings(request: Request):
    return SettingsResponse(data=_settings_payload(load_storage_limit()))


@api_v1_router.put("/settings", response_model=SettingsResponse)
async def api_v1_save_settings(request: Request, payload: SettingsUpdateRequest):
    return SettingsResponse(data=_update_storage_limit(request, payload))


@router.get("/api/jobs/recent", response_class=HTMLResponse)
async def recent_jobs(request: Request, limit: int = 10):
    """最近のジョブ一覧（活動パネル用）。

    Query params:
        limit: 最大取得件数（デフォルト 10）
    """
    job_manager = request.app.state.job_manager
    jobs_dict = job_manager.all_jobs()
    jobs = list(reversed(list(jobs_dict.values())))[:limit]
    # テンプレートに job_id を注入
    for job_id, job in zip(list(reversed(list(jobs_dict.keys())))[:limit], jobs, strict=False):
        job["id"] = job_id
    return templates.TemplateResponse(
        request,
        "partials/job_activity.html",
        {"jobs": jobs},
    )


@router.websocket("/ws/jobs")
async def ws_jobs(websocket: WebSocket):
    """ジョブ状態変更をリアルタイム配信する WebSocket エンドポイント。"""
    await websocket.accept()
    job_manager = websocket.app.state.job_manager

    # 既存ジョブをすべて送信
    for job_id, job in job_manager.all_jobs().items():
        await websocket.send_text(
            json.dumps(_job_to_payload(job_id, job), ensure_ascii=False)
        )

    # キューを購読
    queue = job_manager.subscribe()
    try:
        while True:
            payload = await queue.get()
            await websocket.send_text(json.dumps(payload, ensure_ascii=False))
    except WebSocketDisconnect:
        pass
    finally:
        job_manager.unsubscribe(queue)


router.include_router(api_v1_router)
