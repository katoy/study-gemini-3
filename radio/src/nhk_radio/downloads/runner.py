"""yt-dlp サブプロセス実行と進捗解析。"""

import logging
import re
import subprocess
import threading
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from ..constants import YTDLP_CONCURRENT_FRAGMENTS, YTDLP_SOCKET_TIMEOUT
from . import filesystem

logger = logging.getLogger(__name__)


def _yt_dlp_command(
    url: str,
    output_template: str,
    *,
    audio_only: bool,
    no_playlist: bool,
    newline: bool = False,
    max_items: int | None = None,
) -> list[str]:
    cmd = ["yt-dlp"]
    if newline:
        cmd.append("--newline")
    # AES-128 暗号化 HLS ストリームで ffmpeg が aac_adtstoasc フィルタに失敗するのを防ぐ
    cmd.append("--hls-use-mpegts")
    # HLS フラグメントの並列ダウンロードとソケットタイムアウトを設定
    cmd += ["--concurrent-fragments", str(YTDLP_CONCURRENT_FRAGMENTS)]
    cmd += ["--socket-timeout", str(YTDLP_SOCKET_TIMEOUT)]
    if audio_only:
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    cmd += ["-o", output_template]
    if max_items:
        cmd += ["--playlist-end", str(max_items)]
    elif no_playlist:
        cmd.append("--no-playlist")
    cmd.append(url)
    return cmd


def _download_episode_command(url: str, output_dir: Path, filename_template: str, audio_only: bool = True) -> list[str]:
    return _yt_dlp_command(
        url,
        str(output_dir / filename_template),
        audio_only=audio_only,
        no_playlist=True,
        newline=True,
    )


def _parse_yt_dlp_progress(line: str) -> tuple[float | None, str | None, str | None]:
    text = line.strip()
    if not text:
        return None, None, None

    if "[ExtractAudio]" in text or "Post-process" in text:
        return 100.0, None, "変換中..."

    percent_match = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%", text)
    if percent_match:
        percent = float(percent_match.group(1))
        eta_match = re.search(r"\bETA\s+([0-9:]+)", text)
        eta = eta_match.group(1) if eta_match else None
        status = "変換中..." if percent >= 100 else "ダウンロード中..."
        return percent, eta, status

    return None, None, None


def _format_download_percent(percent: float | None) -> str:
    if percent is None:
        return "--%"
    percent = min(max(percent, 0.0), 100.0)
    rounded = round(percent)
    if abs(percent - rounded) < 0.05:
        return f"{int(rounded)}%"
    return f"{percent:.1f}%"


def _format_download_eta(eta: str | None) -> str:
    return f"残り {eta}" if eta else "残り --:--"


def run_yt_dlp_subprocess(
    cmd: list[str],
    on_progress: Callable[[float | None, str | None, str | None], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> bool:
    """yt-dlp サブプロセスを実行し、進捗をコールバックで報告する。

    Args:
        cmd: yt-dlp コマンド (リスト形式)
        on_progress: 進捗コールバック (percent, eta, status)
        cancel_event: キャンセルイベント（設定されたら terminate）

    Returns:
        成功時 True、キャンセル時 False、失敗時 False
    """
    process = None
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        if process.stdout:
            for line in process.stdout:
                # キャンセルイベントがセットされたら terminate
                if cancel_event and cancel_event.is_set():
                    process.terminate()
                    break

                # 進捗コールバックを実行
                if on_progress:
                    percent, eta, status = _parse_yt_dlp_progress(line)
                    if percent is not None or eta is not None or status is not None:
                        on_progress(percent, eta, status)

        # タイムアウト 120 秒で wait
        try:
            return process.wait(timeout=120) == 0
        except subprocess.TimeoutExpired:
            logger.warning("yt-dlp プロセスが応答しません。強制終了します。")
            process.kill()
            process.wait()
            return False
    except Exception as e:
        logger.error(f"yt-dlp 実行エラー: {e}")
        if process is not None:
            with suppress(Exception):
                process.terminate()
                process.wait()
        return False
