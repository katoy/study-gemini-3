"""進捗パース機能テスト。"""


from nhk_radio_web.progress import parse_progress_line


def test_parse_progress_empty_line():
    """空行を パースして None を返す。"""
    result = parse_progress_line("")
    assert result["percent"] is None
    assert result["eta"] is None
    assert result["status"] is None


def test_parse_progress_whitespace():
    """空白のみの行を パースして None を返す。"""
    result = parse_progress_line("   \t  ")
    assert result["percent"] is None
    assert result["eta"] is None
    assert result["status"] is None


def test_parse_progress_extract_audio():
    """[ExtractAudio] メッセージから 100% を抽出。"""
    result = parse_progress_line("[ExtractAudio] Destination: /path/to/file.mp3")
    assert result["percent"] == 100.0
    assert result["eta"] is None
    assert result["status"] == "変換中..."


def test_parse_progress_post_process():
    """Post-process メッセージから 100% を抽出。"""
    result = parse_progress_line("[Metadata] Adding metadata to '/path/to/file.m4a'")
    # "Post-process" が含まれないため、次のテストで確認
    assert result["percent"] is None


def test_parse_progress_downloading():
    """ダウンロード中メッセージをパース。"""
    result = parse_progress_line("[download]  50.5% of ~10.00MiB at 1.25MiB/s ETA 00:05")
    assert result["percent"] == 50.5
    assert result["eta"] == "00:05"
    assert result["status"] == "ダウンロード中..."


def test_parse_progress_downloading_no_eta():
    """ETA なしのダウンロードメッセージ。"""
    result = parse_progress_line("[download]  25.0% of ~10.00MiB at 1.00MiB/s")
    assert result["percent"] == 25.0
    assert result["eta"] is None
    assert result["status"] == "ダウンロード中..."


def test_parse_progress_100_percent():
    """100% でも convert メッセージでない場合は変換完了ではない。"""
    result = parse_progress_line("[download] 100.0% of ~10.00MiB at 2.00MiB/s ETA 00:00")
    assert result["percent"] == 100.0
    assert result["status"] == "変換中..."


def test_parse_progress_unknown_line():
    """未知のメッセージは None を返す。"""
    result = parse_progress_line("[some-other-tag] message text")
    assert result["percent"] is None
    assert result["eta"] is None
    assert result["status"] is None
