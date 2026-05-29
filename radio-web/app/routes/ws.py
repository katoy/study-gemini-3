"""WebSocket ルート。"""

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ._shared import _job_to_payload

router = APIRouter()


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
