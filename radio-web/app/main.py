"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from nhk_radio_web.config import DEFAULT_MAX_CONCURRENT_DL
from nhk_radio_web.job_manager import JobManager

from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時: JobManager を初期化して app.state に保存
    max_concurrent = int(os.getenv("NHK_RADIO_MAX_CONCURRENT_DL", str(DEFAULT_MAX_CONCURRENT_DL)))
    app.state.job_manager = JobManager(max_concurrent=max_concurrent)
    yield
    # 終了時: 全ジョブをキャンセル
    await app.state.job_manager.cancel_all()


app = FastAPI(title="NHK ラジオ聞き逃し Web", lifespan=lifespan)
app.include_router(router)
