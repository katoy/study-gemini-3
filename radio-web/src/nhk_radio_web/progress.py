"""yt-dlp 進捗パース関数。"""

import re


def parse_progress_line(line: str) -> dict[str, str | float | None]:
    """yt-dlp output line から進捗情報を抽出する。

    Args:
        line: yt-dlp stdout/stderr の 1 行

    Returns:
        {"percent": float|None, "eta": str|None, "status": str|None}
        percent: ダウンロード率 (0-100)
        eta: 推定完了時刻 (HH:MM:SS 形式) または None
        status: ステータステキスト
    """
    text = line.strip()
    if not text:
        return {"percent": None, "eta": None, "status": None}

    # 後処理中 (変換中)
    if "[ExtractAudio]" in text or "Post-process" in text:
        return {"percent": 100.0, "eta": None, "status": "変換中..."}

    # ダウンロード中の進捗
    percent_match = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%", text)
    if percent_match:
        percent = float(percent_match.group(1))
        eta_match = re.search(r"\bETA\s+([0-9:]+)", text)
        eta = eta_match.group(1) if eta_match else None
        status = "変換中..." if percent >= 100 else "ダウンロード中..."
        return {"percent": percent, "eta": eta, "status": status}

    return {"percent": None, "eta": None, "status": None}
