"""HLS ストリーミング機能のテスト。"""

import pytest
from unittest.mock import AsyncMock, patch

from nhk_radio_web.streaming import (
    fetch_and_decrypt_segment,
    fetch_hls_master,
    parse_hls_key,
    rewrite_playlist_urls,
)


def test_parse_hls_key_with_key_and_iv():
    """EXT-X-KEY パース: 鍵と IV 両方ある場合。"""
    manifest = 'EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key",IV=0x12345678'
    method, key_uri, iv = parse_hls_key(manifest)
    assert method == "AES-128"
    assert key_uri == "https://example.com/key"
    assert iv == bytes.fromhex("12345678")


def test_parse_hls_key_without_iv():
    """EXT-X-KEY パース: IV なし。"""
    manifest = 'EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"'
    method, key_uri, iv = parse_hls_key(manifest)
    assert method == "AES-128"
    assert key_uri == "https://example.com/key"
    assert iv is None


def test_parse_hls_key_not_found():
    """EXT-X-KEY パース: キーがない場合。"""
    manifest = "#EXTM3U\n#EXT-X-VERSION:3"
    method, key_uri, iv = parse_hls_key(manifest)
    assert method is None
    assert key_uri is None
    assert iv is None


def test_rewrite_playlist_urls_segments():
    """プレイリスト URL 書き換え: セグメント URL。"""
    playlist = "#EXTM3U\nsegment1.ts\nsegment2.ts"
    rewritten = rewrite_playlist_urls(
        playlist,
        "https://example.com/playlist/",
        "/stream/site/corner/ep",
    )
    assert "/stream/site/corner/ep/seg/segment1" in rewritten
    assert "/stream/site/corner/ep/seg/segment2" in rewritten
    assert "segment1.ts" not in rewritten


def test_rewrite_playlist_urls_absolute_urls():
    """プレイリスト URL 書き換え: 絶対 URL。"""
    playlist = "#EXTM3U\nhttps://example.com/segments/001.ts"
    rewritten = rewrite_playlist_urls(
        playlist,
        "https://example.com/",
        "/stream/site/corner/ep",
    )
    assert "/stream/site/corner/ep/seg/001" in rewritten


def test_rewrite_playlist_urls_ext_x_key():
    """プレイリスト URL 書き換え: EXT-X-KEY ディレクティブ。"""
    playlist = 'EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key",IV=0x123\nsegment.ts'
    rewritten = rewrite_playlist_urls(
        playlist,
        "https://example.com/",
        "/stream/site/corner/ep",
    )
    # URI と IV が削除されることを確認
    assert 'URI="' not in rewritten
    assert "IV=" not in rewritten
    assert "EXT-X-KEY:METHOD=AES-128" in rewritten


@pytest.mark.asyncio
async def test_fetch_hls_master_success():
    """HLS マスタープレイリスト取得: 成功。"""
    mock_content = "#EXTM3U\n#EXT-X-VERSION:3"
    with patch("nhk_radio_web.streaming.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.text = mock_content
        mock_response.raise_for_status.return_value = None
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = await fetch_hls_master("https://example.com/master.m3u8")
        assert result == mock_content


@pytest.mark.asyncio
async def test_fetch_hls_master_failure():
    """HLS マスタープレイリスト取得: 失敗。"""
    with patch("nhk_radio_web.streaming.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection failed")
        mock_client.__aenter__.return_value = mock_client
        mock_client_class.return_value = mock_client

        result = await fetch_hls_master("https://example.com/master.m3u8")
        assert result is None


@pytest.mark.asyncio
async def test_fetch_and_decrypt_segment_success():
    """セグメント取得・復号: 成功。"""
    # 16 バイト鍵、16 バイト IV、16 バイト平文データ
    test_key = b"\x00" * 16
    test_iv = b"\x00" * 16
    test_plaintext = b"test data here!!!"  # 16 bytes with PKCS7 padding

    # AES-128-CBC で暗号化
    from Cryptodome.Cipher import AES
    from Cryptodome.Util.Padding import pad

    padded = pad(test_plaintext, AES.block_size)
    cipher = AES.new(test_key, AES.MODE_CBC, test_iv)
    encrypted = cipher.encrypt(padded)

    with patch("nhk_radio_web.streaming.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response_key = AsyncMock()
        mock_response_key.content = test_key
        mock_response_key.raise_for_status.return_value = None

        mock_response_seg = AsyncMock()
        mock_response_seg.content = encrypted
        mock_response_seg.raise_for_status.return_value = None

        mock_client.get.side_effect = [mock_response_key, mock_response_seg]
        mock_client.__aenter__.return_value = mock_client
        mock_client_class.return_value = mock_client

        result = await fetch_and_decrypt_segment(
            "https://example.com/seg.ts",
            "https://example.com/key",
            test_iv,
        )
        assert result is not None
        assert test_plaintext in result or test_plaintext == result


@pytest.mark.asyncio
async def test_fetch_and_decrypt_segment_without_iv():
    """セグメント取得・復号: IV なし（デフォルト IV を使用）。"""
    test_key = b"\x00" * 16
    test_plaintext = b"test data here!!!"

    from Cryptodome.Cipher import AES
    from Cryptodome.Util.Padding import pad

    # デフォルト IV (0x00 * 16) で暗号化
    padded = pad(test_plaintext, AES.block_size)
    cipher = AES.new(test_key, AES.MODE_CBC, b"\x00" * 16)
    encrypted = cipher.encrypt(padded)

    with patch("nhk_radio_web.streaming.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response_key = AsyncMock()
        mock_response_key.content = test_key
        mock_response_key.raise_for_status.return_value = None

        mock_response_seg = AsyncMock()
        mock_response_seg.content = encrypted
        mock_response_seg.raise_for_status.return_value = None

        mock_client.get.side_effect = [mock_response_key, mock_response_seg]
        mock_client.__aenter__.return_value = mock_client
        mock_client_class.return_value = mock_client

        # IV を指定しない場合
        result = await fetch_and_decrypt_segment(
            "https://example.com/seg.ts",
            "https://example.com/key",
        )
        assert result is not None
        assert test_plaintext in result or test_plaintext == result


@pytest.mark.asyncio
async def test_fetch_and_decrypt_segment_failure():
    """セグメント取得・復号: 失敗。"""
    with patch("nhk_radio_web.streaming.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Network error")
        mock_client.__aenter__.return_value = mock_client
        mock_client_class.return_value = mock_client

        result = await fetch_and_decrypt_segment(
            "https://example.com/seg.ts",
            "https://example.com/key",
        )
        assert result is None
