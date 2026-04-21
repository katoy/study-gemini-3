"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時: 特に初期化不要 (キャッシュはオンデマンドで生成)
    yield
    # 終了時: ダウンロードジョブの後片付けは routes 側で管理


app = FastAPI(title="NHK ラジオ聞き逃し Web", lifespan=lifespan)
app.include_router(router)
