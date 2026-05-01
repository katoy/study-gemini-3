# 多言語音声対応 Hello World — 構築プロンプト

以下のプロンプト1つでプロジェクト全体を構築できます。

---

```
以下の仕様で Python プロジェクトを構築して。

## 機能

`hello.py` に多言語 Hello World CLI を実装する。

- 引数なしで実行すると英語で挨拶する
- 言語コードを引数に指定するとその言語で挨拶する
- `--list` で対応言語一覧を表示する
- 未対応の言語コードを指定したら専用の例外を出して終了コード 1 で終わる

対応言語（コード: メッセージ / macOS ボイス名）:
- en: Hello, World! / Daniel
- ja: こんにちは、世界！ / Kyoko
- zh: 你好，世界！ / Tingting
- ko: 안녕하세요, 세계! / Yuna
- es: ¡Hola, Mundo! / Jorge
- fr: Bonjour, le monde ! / Thomas
- de: Hallo, Welt! / Anna
- pt: Olá, Mundo! / Joana
- ar: مرحبا بالعالم! / Maged
- ru: Привет, мир! / Milena
- morse: HELLO WORLD をモールス信号に変換して表示・再生

macOS では `say` コマンドで音声読み上げ、非 macOS ではテキスト表示のみ。

## モールス信号

- 標準ライブラリ (`array`, `wave`, `tempfile`) で 800Hz のサイン波 WAV を生成
- `afplay` で再生（macOS のみ）、再生後は一時ファイルを必ず削除
- タイミング: unit = 0.06秒、dot = unit、dash = unit×3、文字間 = unit×2、語間 = unit×4

## コード構成

- `LangEntry(NamedTuple)`: message と voice のペア
- `UnsupportedLanguageError(Exception)`: 未対応言語エラー
- `MESSAGES: Final[dict[str, LangEntry]]`: 言語辞書
- `MORSE_CODE: Final[dict[str, str]]`: モールス変換表
- `GreetingManager` クラス: speak / play_morse / text_to_morse / list_languages / greet
- `build_parser()`: argparse パーサー構築
- `main()`: エントリポイント

表示は `rich` を使う（Panel で挨拶、Table で一覧、赤字でエラー）。
全関数に型ヒントを付け、mypy strict に通ること。

## プロジェクト構成

`uv` + `pyproject.toml` で管理する。

```toml
[project]
name = "hello-world"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["rich>=15.0.0"]

[project.scripts]
hello = "hello:main"

[dependency-groups]
dev = ["mypy", "pre-commit", "pytest", "pytest-cov", "ruff"]

[tool.uv]
package = true

[tool.pytest.ini_options]
addopts = "--cov=hello --cov-report=term-missing --cov-fail-under=100"

[tool.ruff]
line-length = 99
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
strict = true
python_version = "3.10"
```

## テスト

`test_hello.py` で pytest 100% カバレッジを達成する。

- `autouse` フィクスチャで `Console(force_terminal=False)` をパッチし rich の装飾を無効化
- `subprocess.run` と `time.sleep` はフィクスチャでモック化
- speak は darwin / non-darwin 両方をテスト
- greet は `@pytest.mark.parametrize` で全言語をテスト
- play_morse は sleep の回数と値を厳密にアサート
- main の全パス（デフォルト/言語指定/--list/無効言語/エントリポイント）をテスト

## Docker

本番用 `Dockerfile`:
- `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` をベースに使用
- `UV_COMPILE_BYTECODE=1` を設定
- `pyproject.toml` と `uv.lock` を先にコピーして `uv sync --frozen --no-dev`
- 非 root ユーザー `appuser` を作成し `--chown=appuser:appuser` で `hello.py` をコピー
- `ENTRYPOINT ["/app/.venv/bin/hello"]`

CI 用 `Dockerfile.ci`（`Dockerfile.ci.dockerignore` も作成）:
- `uv sync --frozen`（dev 依存も含む）
- `hello.py` と `test_hello.py` をコピー

`.dockerignore` で不要ファイルを除外する。

## CI/CD

`.github/workflows/ci.yml`:
- トリガー: main/master への push と pull_request
- `astral-sh/setup-uv@v5`（`enable-cache: true`, `python-version: "3.12"`）
- ステップ: uv sync → ruff check → ruff format --check → mypy → pytest

ローカル検証用に `ci.sh`（Docker で上記を再現）も作成する。

## pre-commit と .gitignore

`.pre-commit-config.yaml`:
- `astral-sh/ruff-pre-commit`: ruff（--fix 付き）と ruff-format
  （バージョンは pyproject.toml の ruff バージョンと合わせる）
- `pre-commit/mirrors-mypy`（additional_dependencies に pytest と rich を追加）

`.gitignore` は Python プロジェクトの標準的な除外対象を設定する。
```

---

## 完成確認

```bash
uv run ruff check
uv run ruff format --check
uv run mypy hello.py test_hello.py
uv run pytest
```

ruff/mypy エラー 0、pytest 全テスト PASS、カバレッジ 100% が合格基準。
