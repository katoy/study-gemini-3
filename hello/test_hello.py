import os
import runpy
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

import hello


@pytest.fixture(autouse=True)
def disable_rich_formatting() -> Generator[None, None, None]:
    """テスト中の rich の装飾を無効化する。"""
    plain_console = Console(force_terminal=False, color_system=None, width=100)
    with patch("hello.console", plain_console):
        yield


@pytest.fixture
def mock_run() -> Generator[MagicMock, None, None]:
    """subprocess.run をモック化する。"""
    with patch("subprocess.run") as mock:
        yield mock


@pytest.fixture
def mock_sleep() -> Generator[MagicMock, None, None]:
    """time.sleep をモック化する。"""
    with patch("time.sleep") as mock:
        yield mock


def test_speak_darwin(mock_run: MagicMock) -> None:
    manager = hello.GreetingManager()
    with patch("sys.platform", "darwin"):
        manager.speak("Hello, World!", "Daniel")
    mock_run.assert_called_once_with(["say", "-v", "Daniel", "Hello, World!"], check=False)


def test_speak_non_darwin(mock_run: MagicMock) -> None:
    manager = hello.GreetingManager()
    with patch("sys.platform", "linux"):
        manager.speak("Hello, World!", "Daniel")
    mock_run.assert_not_called()


def test_play_morse_darwin(mock_run: MagicMock, mock_sleep: MagicMock) -> None:
    manager = hello.GreetingManager()
    unit = 0.06
    fake_paths = ["/tmp/fake_dot.wav", "/tmp/fake_dash.wav"]
    with (
        patch("sys.platform", "darwin"),
        patch.object(hello.GreetingManager, "_generate_beep", side_effect=fake_paths),
        patch("os.path.exists", return_value=True),
        patch("os.remove") as mock_remove,
    ):
        manager.play_morse(".- /")

    # ".- /" → dot, dash, space, slash  ⟹  afplay×2
    assert mock_run.call_count == 2
    args_list = [c[0][0] for c in mock_run.call_args_list]
    assert all(a[0] == "afplay" for a in args_list)
    assert [a[1] for a in args_list] == fake_paths

    # sleep: dot(unit) + dash(unit) + space(unit*2) + slash(unit*4) = 4回
    assert mock_sleep.call_count == 4
    sleep_args = [c[0][0] for c in mock_sleep.call_args_list]
    assert sleep_args == [unit, unit, unit * 2, unit * 4]

    # 一時ファイルは両方とも削除される
    removed = [c[0][0] for c in mock_remove.call_args_list]
    assert sorted(removed) == sorted(fake_paths)


def test_play_morse_non_darwin(mock_run: MagicMock) -> None:
    manager = hello.GreetingManager()
    with patch("sys.platform", "linux"):
        manager.play_morse(".-")
    mock_run.assert_not_called()


def test_generate_beep() -> None:
    manager = hello.GreetingManager()
    # 実際にファイルが生成され、中身がWAVヘッダを持っているか確認
    path = manager._generate_beep(0.1, 800)
    try:
        assert os.path.exists(path)
        with open(path, "rb") as f:
            header = f.read(4)
            assert header == b"RIFF"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_generate_beep_cleanup_on_error() -> None:
    manager = hello.GreetingManager()
    with (
        patch("wave.open", side_effect=RuntimeError("test error")),
        patch("os.close") as mock_close,
        pytest.raises(RuntimeError, match="test error"),
    ):
        manager._generate_beep(0.1)
    # os.fdopen が呼ばれる前に wave.open が失敗するため、fd の手動クローズが呼ばれる
    mock_close.assert_called_once()


def test_text_to_morse() -> None:
    manager = hello.GreetingManager()
    assert manager.text_to_morse("SOS") == "... --- ..."
    assert manager.text_to_morse("A B") == ".- / -..."
    assert manager.text_to_morse("?") == ""  # 未対応文字がスキップされること


@pytest.mark.parametrize("lang,entry", hello.MESSAGES.items())
def test_speak_all_languages(mock_run: MagicMock, lang: str, entry: hello.LangEntry) -> None:
    manager = hello.GreetingManager()
    if lang == "morse":
        pytest.skip("Morse is handled differently")
    with patch("sys.platform", "darwin"):
        manager.speak(entry.message, entry.voice)
    mock_run.assert_called_once_with(["say", "-v", entry.voice, entry.message], check=False)


def test_list_languages(capsys: pytest.CaptureFixture[str]) -> None:
    manager = hello.GreetingManager()
    manager.list_languages()
    out = capsys.readouterr().out
    assert "利用可能な言語一覧" in out
    for code, entry in hello.MESSAGES.items():
        assert code in out
        assert entry.message in out
        assert entry.voice in out


@pytest.mark.parametrize(
    "lang,expected",
    [
        (code, entry.message if code != "morse" else ".... . .-.. .-.. --- / .-- --- .-. .-.. -..")
        for code, entry in hello.MESSAGES.items()
    ],
)
def test_greet_valid(
    capsys: pytest.CaptureFixture[str],
    mock_run: MagicMock,
    mock_sleep: MagicMock,
    lang: str,
    expected: str,
) -> None:
    manager = hello.GreetingManager()
    manager.greet(lang)
    assert expected in capsys.readouterr().out


def test_greet_invalid() -> None:
    manager = hello.GreetingManager()
    with pytest.raises(hello.UnsupportedLanguageError, match="xx"):
        manager.greet("xx")


def test_main_default_lang(capsys: pytest.CaptureFixture[str], mock_run: MagicMock) -> None:
    with patch("sys.argv", ["hello.py"]):
        hello.main()
    assert "Hello, World!" in capsys.readouterr().out


def test_main_explicit_lang(capsys: pytest.CaptureFixture[str], mock_run: MagicMock) -> None:
    with patch("sys.argv", ["hello.py", "ko"]):
        hello.main()
    assert "안녕하세요, 세계!" in capsys.readouterr().out


def test_main_list(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["hello.py", "--list"]):
        hello.main()
    out = capsys.readouterr().out
    assert "利用可能な言語一覧" in out
    for code in hello.MESSAGES:
        assert code in out


def test_main_invalid_lang(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["hello.py", "xx"]), pytest.raises(SystemExit) as exc_info:
        hello.main()
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "エラー" in out
    assert "xx" in out


def test_main_entrypoint(capsys: pytest.CaptureFixture[str], mock_run: MagicMock) -> None:
    with patch("sys.argv", ["hello.py"]):
        runpy.run_path("hello.py", run_name="__main__")
    assert "Hello, World!" in capsys.readouterr().out
