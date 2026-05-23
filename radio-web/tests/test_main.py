"""FastAPI lifespan コンテキストマネージャのテスト。"""

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

from app.main import lifespan


@pytest.mark.asyncio
async def test_lifespan_startup():
    """lifespan 起動時: JobManager 初期化、環境変数読み取り。"""
    # 環境変数をクリア（デフォルト値を使用）
    with patch.dict(os.environ, {}, clear=False):
        if "NHK_RADIO_MAX_CONCURRENT_DL" in os.environ:
            del os.environ["NHK_RADIO_MAX_CONCURRENT_DL"]

        # FastAPI インスタンスを作成
        from fastapi import FastAPI

        test_app = FastAPI()

        # lifespan を手動で実行
        ctx = lifespan(test_app)
        await ctx.__aenter__()

        # JobManager が初期化されたことを確認
        assert hasattr(test_app.state, "job_manager")
        assert test_app.state.job_manager is not None
        assert test_app.state.job_manager.max_concurrent > 0

        await ctx.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_lifespan_startup_with_env_var():
    """lifespan 起動時: NHK_RADIO_MAX_CONCURRENT_DL 環境変数が指定された場合。"""
    with patch.dict(os.environ, {"NHK_RADIO_MAX_CONCURRENT_DL": "5"}):
        from fastapi import FastAPI

        test_app = FastAPI()
        ctx = lifespan(test_app)
        await ctx.__aenter__()

        assert test_app.state.job_manager.max_concurrent == 5

        await ctx.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_lifespan_shutdown_success():
    """lifespan 終了時: cancel_all() が正常に実行される。"""
    from fastapi import FastAPI

    test_app = FastAPI()
    ctx = lifespan(test_app)
    await ctx.__aenter__()

    # cancel_all のモックを設定
    mock_cancel_all = AsyncMock()
    test_app.state.job_manager.cancel_all = mock_cancel_all

    # 終了処理を実行
    await ctx.__aexit__(None, None, None)

    # cancel_all が呼び出されたことを確認
    mock_cancel_all.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_shutdown_timeout():
    """lifespan 終了時: cancel_all() がタイムアウトした場合。"""
    from fastapi import FastAPI

    test_app = FastAPI()
    ctx = lifespan(test_app)
    await ctx.__aenter__()

    # cancel_all がタイムアウトするようにモック
    async def timeout_cancel():
        await asyncio.sleep(10)

    test_app.state.job_manager.cancel_all = timeout_cancel

    # 終了処理を実行（タイムアウト後も例外が出ない）
    try:
        await ctx.__aexit__(None, None, None)
    except TimeoutError:
        pytest.fail("TimeoutError should be caught and logged")
