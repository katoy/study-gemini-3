import argparse
import array
import contextlib
import math
import os
import subprocess
import sys
import tempfile
import time
import wave
from typing import Final, NamedTuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


class LangEntry(NamedTuple):
    message: str
    voice: str


class UnsupportedLanguageError(Exception):
    """未対応の言語が指定された際のエラー。"""

    def __init__(self, lang: str):
        self.lang = lang
        super().__init__(f"未対応の言語コード: '{lang}'")


MESSAGES: Final[dict[str, LangEntry]] = {
    "en": LangEntry("Hello, World!", "Daniel"),
    "ja": LangEntry("こんにちは、世界！", "Kyoko"),
    "zh": LangEntry("你好，世界！", "Tingting"),
    "ko": LangEntry("안녕하세요, 세계!", "Yuna"),
    "es": LangEntry("¡Hola, Mundo!", "Jorge"),
    "fr": LangEntry("Bonjour, le monde !", "Thomas"),
    "de": LangEntry("Hallo, Welt!", "Anna"),
    "pt": LangEntry("Olá, Mundo!", "Joana"),
    "ar": LangEntry("مرحبا بالعالم!", "Maged"),
    "ru": LangEntry("Привет, мир!", "Milena"),
    "morse": LangEntry("HELLO WORLD", "Morse Code"),
}

MORSE_CODE: Final[dict[str, str]] = {
    "A": ".-",
    "B": "-...",
    "C": "-.-.",
    "D": "-..",
    "E": ".",
    "F": "..-.",
    "G": "--.",
    "H": "....",
    "I": "..",
    "J": ".---",
    "K": "-.-",
    "L": ".-..",
    "M": "--",
    "N": "-.",
    "O": "---",
    "P": ".--.",
    "Q": "--.-",
    "R": ".-.",
    "S": "...",
    "T": "-",
    "U": "..-",
    "V": "...-",
    "W": ".--",
    "X": "-..-",
    "Y": "-.--",
    "Z": "--..",
    "1": ".----",
    "2": "..---",
    "3": "...--",
    "4": "....-",
    "5": ".....",
    "6": "-....",
    "7": "--...",
    "8": "---..",
    "9": "----.",
    "0": "-----",
    " ": "/",
}


class GreetingManager:
    """挨拶と言語管理を担当するクラス。"""

    def __init__(self, messages: dict[str, LangEntry] | None = None):
        self.messages = messages if messages is not None else MESSAGES

    def _generate_beep(self, duration: float, frequency: int = 800) -> str:
        """指定された周波数と長さのビープ音（WAV）を生成し、一時ファイルのパスを返す。"""
        sample_rate = 44100
        n_samples = int(sample_rate * duration)

        samples = array.array(
            "h",
            (
                int(32767.0 * math.sin(2.0 * math.pi * frequency * i / sample_rate))
                for i in range(n_samples)
            ),
        )
        fd, path = tempfile.mkstemp(suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as f, wave.open(f, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframesraw(samples.tobytes())
        except Exception:
            # os.fdopen が成功していれば with 文が fd を閉じる。
            # os.fdopen が失敗した場合は fd が開いたままなので手動で閉じる。
            with contextlib.suppress(OSError):
                os.close(fd)
            if os.path.exists(path):
                os.remove(path)
            raise
        return path

    def speak(self, text: str, voice: str) -> None:
        """macOS の say コマンドを使用して音声を再生する。"""
        if sys.platform != "darwin":
            return
        subprocess.run(["say", "-v", voice, text], check=False)

    def play_morse(self, morse_text: str) -> None:
        """モールス信号を音として再生する。"""
        if sys.platform != "darwin":
            return

        # タイミング基準（1単位 = 0.06秒）
        unit = 0.06
        dot_path = self._generate_beep(unit)
        dash_path = self._generate_beep(unit * 3)

        try:
            for char in morse_text:
                if char == ".":
                    subprocess.run(["afplay", dot_path], check=False)
                    time.sleep(unit)
                elif char == "-":
                    subprocess.run(["afplay", dash_path], check=False)
                    time.sleep(unit)
                elif char == " ":
                    time.sleep(unit * 2)
                elif char == "/":
                    time.sleep(unit * 4)
        finally:
            for p in [dot_path, dash_path]:
                if os.path.exists(p):
                    os.remove(p)

    def text_to_morse(self, text: str) -> str:
        """テキストをモールス信号に変換する。未対応の文字はスキップする。"""
        chars = []
        for c in text.upper():
            if c in MORSE_CODE:
                chars.append(MORSE_CODE[c])
        return " ".join(chars)

    def list_languages(self) -> None:
        """利用可能な言語の一覧をテーブル形式で表示する。"""
        table = Table(title="利用可能な言語一覧", header_style="bold magenta")
        table.add_column("コード", style="cyan", no_wrap=True)
        table.add_column("メッセージ", style="green")
        table.add_column("ボイス (macOS)", style="yellow")

        for code, entry in self.messages.items():
            table.add_row(code, entry.message, entry.voice)

        console.print(table)

    def greet(self, lang: str) -> None:
        """指定された言語で挨拶を表示し、音声を再生する。"""
        entry = self.messages.get(lang)
        if entry is None:
            raise UnsupportedLanguageError(lang)

        if lang == "morse":
            morse = self.text_to_morse(entry.message)
            console.print(Panel(morse, title="[bold cyan]Morse Code[/bold cyan]", expand=False))
            self.play_morse(morse)
        else:
            console.print(
                Panel(entry.message, title=f"[bold cyan]{lang}[/bold cyan]", expand=False)
            )
            self.speak(entry.message, entry.voice)


def build_parser() -> argparse.ArgumentParser:
    """引数パーサーを構築する。"""
    parser = argparse.ArgumentParser(description="多言語 Hello World（音声付き）")
    parser.add_argument(
        "lang",
        nargs="?",
        default="en",
        metavar="LANG",
        help=f"言語コード（デフォルト: en）。対応: {', '.join(MESSAGES)}",
    )
    parser.add_argument("--list", action="store_true", help="対応言語一覧を表示")
    return parser


def main() -> None:
    """メインエントリポイント。"""
    args = build_parser().parse_args()
    manager = GreetingManager()

    if args.list:
        manager.list_languages()
        return

    try:
        manager.greet(args.lang)
    except UnsupportedLanguageError as exc:
        console.print(f"[bold red]エラー:[/bold red] {exc}")
        console.print(f"対応言語: [green]{', '.join(MESSAGES.keys())}[/green]")
        sys.exit(1)


if __name__ == "__main__":
    main()
