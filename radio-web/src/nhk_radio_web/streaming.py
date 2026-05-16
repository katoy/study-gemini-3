"""HLS マニフェスト取得・AES 復号プロキシ。

NHK ラジオのストリーミング再生をブラウザで可能にするモジュール。
HLS マスタープレイリストを取得し、セグメント URL をサーバプロキシに書き換える。
"""

import logging
import re
from typing import Optional

import httpx
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import unpad

logger = logging.getLogger(__name__)

# HLS マニフェスト内の EXT-X-KEY ディレクティブをパースするパターン
KEY_PATTERN = re.compile(r'EXT-X-KEY:METHOD=([^,]+),URI="([^"]+)"(?:,IV=([^,\s]+))?')


async def fetch_hls_master(stream_url: str) -> Optional[str]:
    """HLS マスタープレイリストを取得。

    Args:
        stream_url: HLS マスタープレイリストの URL

    Returns:
        マスタープレイリストの内容、または失敗時は None
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(stream_url)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        logger.error(f"HLS マスタープレイリスト取得失敗: {e}")
        return None


def parse_hls_key(manifest_content: str) -> tuple[Optional[str], Optional[str], Optional[bytes]]:
    """HLS マニフェストから EXT-X-KEY を抽出。

    Returns:
        (方式, 鍵 URI, IV)
    """
    match = KEY_PATTERN.search(manifest_content)
    if not match:
        return None, None, None

    method = match.group(1)
    key_uri = match.group(2)
    iv_str = match.group(3)

    iv = None
    if iv_str:
        iv = bytes.fromhex(iv_str.replace("0x", "").replace("0X", ""))

    return method, key_uri, iv


async def fetch_and_decrypt_segment(
    segment_url: str,
    key_uri: str,
    iv: Optional[bytes] = None,
) -> Optional[bytes]:
    """HLS セグメントを取得し、AES-128-CBC で復号。

    Args:
        segment_url: TS セグメントの URL
        key_uri: AES 鍵の URL
        iv: 初期化ベクトル（省略時はセグメント番号から生成される場合がある）

    Returns:
        復号されたセグメントデータ、または失敗時は None
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # 鍵を取得
            key_resp = await client.get(key_uri)
            key_resp.raise_for_status()
            key = key_resp.content

            # セグメントを取得
            seg_resp = await client.get(segment_url)
            seg_resp.raise_for_status()
            encrypted_data = seg_resp.content

            # IV がない場合は 0 にする (多くの HLS は IV を明示していない)
            if iv is None:
                iv = b"\x00" * 16

            # AES-128-CBC で復号
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted = cipher.decrypt(encrypted_data)

            # PKCS7 パディングを削除
            decrypted = unpad(decrypted, AES.block_size)

            return decrypted
    except Exception as e:
        logger.error(f"セグメント復号失敗: {e}")
        return None


def rewrite_playlist_urls(
    playlist_content: str,
    base_url: str,
    proxy_base: str,
) -> str:
    """プレイリスト内のセグメント URL をサーバプロキシ経由に書き換え。

    Args:
        playlist_content: 元のプレイリスト内容
        base_url: 元のプレイリストベース URL
        proxy_base: プロキシのベース URL (e.g., "/stream/site_id/corner_id/episode_id")

    Returns:
        書き換えられたプレイリスト
    """
    lines = playlist_content.split("\n")
    rewritten = []

    for line in lines:
        # EXT-X-KEY の URI をプロキシに書き換えない (サーバが解決)
        if line.startswith("EXT-X-KEY:"):
            # URI を削除（サーバが暗号化を処理する）
            line = re.sub(r',URI="[^"]+"', "", line)
            line = re.sub(r',IV=[^\s,]+', "", line)
            rewritten.append(line)
        # セグメント URL を書き換え
        elif line.endswith(".ts") or line.endswith(".m4s"):
            # 絶対 URL か相対 URL か判定
            if line.startswith("http"):
                # 絶対 URL → セグメントインデックスを抽出してプロキシ経由に
                match = re.search(r"(\d+)", line)
                seg_idx = match.group(1) if match else "0"
                rewritten.append(f"{proxy_base}/seg/{seg_idx}")
            else:
                # 相対 URL → 解決して同様に処理
                rewritten.append(f"{proxy_base}/seg/{line.split('/')[-1].replace('.ts', '').replace('.m4s', '')}")
        else:
            rewritten.append(line)

    return "\n".join(rewritten)
