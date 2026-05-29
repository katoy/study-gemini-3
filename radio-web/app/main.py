"""FastAPI application entry point."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from nhk_radio_web import __version__
from nhk_radio_web.config import DEFAULT_MAX_CONCURRENT_DL, load_storage_limit
from nhk_radio_web.job_manager import JobManager

from .api_models import ErrorDetail, ErrorResponse
from .routes import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時: JobManager を初期化して app.state に保存
    print(f"🚀 Starting NHK Radio Web v{__version__}", flush=True)
    max_concurrent = int(os.getenv("NHK_RADIO_MAX_CONCURRENT_DL", str(DEFAULT_MAX_CONCURRENT_DL)))
    app.state.job_manager = JobManager(max_concurrent=max_concurrent)
    # ストレージ容量上限を app.state に保存
    app.state.storage_limit = load_storage_limit()
    yield
    # 終了時: 全ジョブをキャンセル（タイムアウト付き）
    try:
        await asyncio.wait_for(app.state.job_manager.cancel_all(), timeout=5.0)
    except TimeoutError:
        logger.warning("Job cancellation timed out during shutdown")


app = FastAPI(title="NHK ラジオ聞き逃し Web", lifespan=lifespan)
app.include_router(router)

# 静的ファイルをマウント
static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.exception_handler(HTTPException)
async def api_http_exception_handler(request: Request, exc: HTTPException):
    """API ルート用の構造化エラーレスポンスハンドラ"""
    if request.url.path.startswith("/api/v1/"):
        # エラーコードをマッピング
        error_code = f"HTTP_{exc.status_code}"
        error_response = ErrorResponse(
            error=ErrorDetail(
                code=error_code,
                message=exc.detail if isinstance(exc.detail, str) else "Request error",
            )
        )
        return JSONResponse(content=error_response.model_dump(), status_code=exc.status_code)

    # API でない場合は default handler に委譲
    from fastapi.exception_handlers import http_exception_handler
    return await http_exception_handler(request, exc)
