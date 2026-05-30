"""HTMLResponse を返すルート（index・programs・episodes・downloads・help等）。"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse

from nhk_radio_web import __version__
from nhk_radio_web.config import _default_download_dir
from nhk_radio_web.constants import NHK_DETAIL_TMPL
from nhk_radio_web.help_content import render_help_html
from nhk_radio_web.job_manager import JobManager
from nhk_radio_web.search import filter_episodes, filter_programs
from nhk_radio_web.types import Episode, Program

from ..api_models import DownloadJobCreateRequest
from ._shared import (
    _all_programs_dep,
    _build_genre_options,
    _create_download_job_from_models,
    _find_program,
    _genre_counts,
    _job_manager_dep,
    _matches_genre,
    _parse_program_id,
    get_episode_list,
    is_episode_downloaded,
    templates,
)

router = APIRouter()


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
    from fastapi import HTTPException

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
