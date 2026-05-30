"""内部 /api/* ルート（/api/v1 を除く）。"""

import fnmatch
import logging
import sys
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from nhk_radio_web.cache import clear_episode_cache, clear_program_cache
from nhk_radio_web.config import _default_download_dir
from nhk_radio_web.downloads import _episode_output_identity, _program_search_dirs
from nhk_radio_web.text import _safe_name

from ..api_models import SettingsUpdateRequest
from ._shared import (
    _settings_payload,
    _update_storage_limit,
    fetch_program_list_async,
    get_episode_list,
    load_storage_limit,
    templates,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/download/{job_id}/status", response_class=HTMLResponse)
async def download_status(request: Request, job_id: str):
    """htmx ポーリング用のダウンロード状態 HTML フラグメント。"""
    job_manager = request.app.state.job_manager
    job = job_manager.status_snapshot(job_id)
    if job is None:
        # ジョブが見つからない場合、ポーリングを停止（hx-polling-stop）
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
    # フォールバック: キャッシュにない場合は最小構成で組み立てる
    if program is None:
        from nhk_radio_web.constants import NHK_DETAIL_TMPL
        program = Program(
            title=f"{site_id}_{corner_id}",
            display_title=f"{site_id}_{corner_id}",
            display_date="",
            site_id=site_id,
            corner_id=corner_id,
            url=NHK_DETAIL_TMPL.format(site_id=site_id, corner_id=corner_id),
        )

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
