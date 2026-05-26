"""FastAPI route definitions."""

import dataclasses
import fnmatch
import json
import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from nhk_radio_web.cache import clear_episode_cache, clear_program_cache
from nhk_radio_web.config import _default_download_dir, load_storage_limit, save_storage_limit
from nhk_radio_web.constants import GENRE_LABELS, NHK_GENRES
from nhk_radio_web.core import fetch_program_list_async, get_episode_list
from nhk_radio_web.downloads import _episode_output_identity, _program_search_dirs, is_episode_downloaded
from nhk_radio_web.help_content import render_help_html
from nhk_radio_web.search import filter_episodes, filter_programs
from nhk_radio_web.text import _safe_name
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


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, genre: str = ""):
    programs = await fetch_program_list_async(genre or None)
    programs_by_genre: dict[str, list] = {}
    for p in programs:
        programs_by_genre.setdefault(p.genre or "", []).append(p)

    # ジャンルオプションを取得済み番組から動的に生成
    seen = set()
    genre_options = [{"value": "", "label": "すべて"}, {"value": "new_series", "label": "新番組"}]
    for g in NHK_GENRES:
        if g not in seen and any(p.genre == g for p in programs):
            genre_options.append({"value": g, "label": GENRE_LABELS.get(g, g)})
            seen.add(g)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "programs": programs,
            "programs_by_genre": programs_by_genre,
            "genre_options": genre_options,
            "selected_genre": genre,
        },
    )


@router.get("/programs", response_class=HTMLResponse)
async def programs_partial(request: Request, genre: str = "", q: str = ""):
    """htmx からのジャンルフィルタ更新リクエスト用。

    Query params:
        genre: ジャンルフィルタ
        q: 番組名検索キーワード
    """
    programs = await fetch_program_list_async(genre or None)
    if q:
        programs = filter_programs(programs, needle=q)
    return templates.TemplateResponse(
        request,
        "partials/program_list.html",
        {
            "programs": programs,
            "selected_genre": genre,
        },
    )


@router.get("/programs/{program_id}/episodes", response_class=HTMLResponse)
async def episodes_partial(request: Request, program_id: str, q: str = ""):
    """htmx からのエピソード一覧取得リクエスト用。program_id は {site_id}_{corner_id}。

    Query params:
        q: エピソード検索キーワード
    """
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


@router.post("/download", response_class=HTMLResponse)
async def start_download(request: Request, background_tasks: BackgroundTasks):
    """単発ダウンロード: ジョブを登録してステータス HTML フラグメントを返す。"""
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=422, detail="リクエストボディが JSON ではありません") from e
    program_dict = body.get("program")
    episode_dict = body.get("episode")
    if not isinstance(program_dict, dict) or not isinstance(episode_dict, dict):
        raise HTTPException(status_code=422, detail="program と episode は dict 形式で指定してください")

    try:
        program = Program(**{k: v for k, v in program_dict.items() if k in Program.__dataclass_fields__})
        episode = Episode(**{k: v for k, v in episode_dict.items() if k in Episode.__dataclass_fields__})
    except (TypeError, KeyError) as e:
        raise HTTPException(status_code=422, detail=f"データ形式が不正です: {e}") from e

    job_manager = request.app.state.job_manager
    job_id = job_manager.enqueue(program, episode)
    background_tasks.add_task(job_manager.start, job_id)

    job = job_manager.status_snapshot(job_id)
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
    return JSONResponse({
        "storage_limit_bytes": storage_limit,
        "storage_limit_gb": storage_limit / (1024 ** 3),
    })


@router.post("/api/settings")
async def save_settings(request: Request):
    """設定（ストレージ上限等）を保存する。"""
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=422, detail="リクエストボディが JSON ではありません") from e

    storage_limit_gb = body.get("storage_limit_gb")
    if not isinstance(storage_limit_gb, (int, float)) or storage_limit_gb <= 0:
        raise HTTPException(status_code=422, detail="storage_limit_gb は正の数値で指定してください")

    # GB をバイトに変換
    storage_limit_bytes = int(storage_limit_gb * (1024 ** 3))
    success = save_storage_limit(storage_limit_bytes)
    if not success:
        raise HTTPException(status_code=500, detail="設定の保存に失敗しました")

    # app.state を更新
    request.app.state.storage_limit = storage_limit_bytes
    logger.info(f"ストレージ容量上限を更新: {storage_limit_gb} GB")

    return JSONResponse({
        "storage_limit_bytes": storage_limit_bytes,
        "storage_limit_gb": storage_limit_gb,
    })


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
