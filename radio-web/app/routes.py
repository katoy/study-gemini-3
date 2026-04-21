"""FastAPI route definitions."""

import asyncio
import dataclasses
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from nhk_radio_web.config import _default_download_dir
from nhk_radio_web.constants import GENRE_LABELS, NHK_GENRES
from nhk_radio_web.core import fetch_program_list_async, get_episode_list
from nhk_radio_web.downloads import (
    _download_episode_command,
    _program_filename_template,
    _program_output_dir,
    is_episode_downloaded,
    mark_episode_downloaded,
)
from nhk_radio_web.types import Episode, Program

logger = logging.getLogger(__name__)

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _dataclass_to_json(obj) -> str:
    """dataclass を JSON 文字列に変換する Jinja2 フィルタ用。"""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return json.dumps(dataclasses.asdict(obj), ensure_ascii=False)
    return json.dumps(obj, ensure_ascii=False)


templates.env.filters["tojson"] = _dataclass_to_json

# ダウンロードジョブ管理 (メモリ内)
# job_id -> {"status": str, "program": Program, "episode": Episode, "error": str}
_jobs: dict[str, dict[str, Any]] = {}

GENRE_OPTIONS = [{"value": "", "label": "すべて"}] + [
    {"value": g, "label": GENRE_LABELS[g]} for g in NHK_GENRES
]


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, genre: str = ""):
    programs = await fetch_program_list_async(genre or None)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "programs": programs,
            "genre_options": GENRE_OPTIONS,
            "selected_genre": genre,
        },
    )


@router.get("/programs", response_class=HTMLResponse)
async def programs_partial(request: Request, genre: str = ""):
    """htmx からのジャンルフィルタ更新リクエスト用。"""
    programs = await fetch_program_list_async(genre or None)
    return templates.TemplateResponse(
        request,
        "partials/program_list.html",
        {
            "programs": programs,
            "selected_genre": genre,
        },
    )


@router.get("/programs/{program_id}/episodes", response_class=HTMLResponse)
async def episodes_partial(request: Request, program_id: str):
    """htmx からのエピソード一覧取得リクエスト用。program_id は {site_id}_{corner_id}。"""
    parts = program_id.split("_", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid program_id")
    site_id, corner_id = parts

    # キャッシュ済み番組一覧から Program を検索
    all_programs = await fetch_program_list_async(None)
    program: Program | None = next(
        (p for p in all_programs if p.site_id == site_id and p.corner_id == corner_id),
        None,
    )
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
        episodes, source = get_episode_list(program)
    except RuntimeError as e:
        return templates.TemplateResponse(
            request,
            "partials/episode_list.html",
            {"program": program, "episodes_with_status": [], "error": str(e)},
        )

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


@router.post("/download", response_class=HTMLResponse)
async def start_download(request: Request, background_tasks: BackgroundTasks):
    """ダウンロードジョブを登録してステータス HTML フラグメントを返す。"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="リクエストボディが JSON ではありません")
    program_dict = body.get("program")
    episode_dict = body.get("episode")
    if not isinstance(program_dict, dict) or not isinstance(episode_dict, dict):
        raise HTTPException(status_code=422, detail="program と episode は dict 形式で指定してください")

    try:
        program = Program(**{k: v for k, v in program_dict.items() if k in Program.__dataclass_fields__})
        episode = Episode(**{k: v for k, v in episode_dict.items() if k in Episode.__dataclass_fields__})
    except (TypeError, KeyError) as e:
        raise HTTPException(status_code=422, detail=f"データ形式が不正です: {e}")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "program": program, "episode": episode, "error": ""}
    background_tasks.add_task(_run_download, job_id, program, episode)
    return templates.TemplateResponse(
        request,
        "partials/download_status.html",
        {"job_id": job_id, "job": _jobs[job_id]},
    )


@router.get("/api/download/{job_id}/status", response_class=HTMLResponse)
async def download_status(request: Request, job_id: str):
    """htmx ポーリング用のダウンロード状態 HTML フラグメント。"""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse(
        request,
        "partials/download_status.html",
        {"job_id": job_id, "job": job},
    )


@router.get("/downloads", response_class=HTMLResponse)
async def downloads_page(request: Request):
    """全ダウンロードジョブの一覧ページ。"""
    return templates.TemplateResponse(
        request,
        "downloads.html",
        {"jobs": dict(_jobs)},
    )


async def _run_download(job_id: str, program: Program, episode: Episode):
    """バックグラウンドで yt-dlp を実行してエピソードをダウンロードする。"""
    _jobs[job_id]["status"] = "downloading"
    output_dir = _default_download_dir()
    program_dir = _program_output_dir(output_dir, program)
    program_dir.mkdir(parents=True, exist_ok=True)
    filename_template = _program_filename_template(program)
    cmd = _download_episode_command(episode.url, program_dir, filename_template)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        await proc.wait()
        if proc.returncode == 0:
            _jobs[job_id]["status"] = "done"
            mark_episode_downloaded(output_dir, program, episode)
        else:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = f"yt-dlp 終了コード: {proc.returncode}"
    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)
        logger.error(f"ダウンロードエラー (job={job_id}): {e}")
