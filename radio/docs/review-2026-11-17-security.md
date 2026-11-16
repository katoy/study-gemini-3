# radio 全体セキュリティ・コードレビュー（2026-11-17）

対象: `radio/` 全体（`src/nhk_radio/` 配下のコアロジック、ダウンロード管理、ファイルI/O、CLI、GUI、および各種設定）

---

## 0. レビュー概要

本リポジトリは、NHK ラジオの聞き逃し番組をダウンロード・管理する Python ツールです。
過去のレビュー（L1〜L8、G4〜G16 等）を通じて、原子的ファイル書き込み、ファイルロック、URL の `--` エスケープ、出力テンプレートの `%` エスケープ、パス名のサニタイズなど、多くの防御的プログラミングが既に組み込まれています。

今回のレビューでは、システム全体を俯瞰しつつ、**セキュリティホール（任意コード実行、パストラバーサル、未検証入力の悪用、リソース枯渇）** を中心に検証を行いました。

### 指摘事項サマリ

| 重要度 | ID | 分類 | 項目名 | 対象ファイル | 状況 |
|---|---|---|---|---|---|
| **High** | **S1** | 任意コード実行 | `_play_episode_file` でのメディア拡張子未検証および保存先境界未確認 | `src/nhk_radio/gui/listing/operations.py` | ✅ 解消 |
| **Medium** | **S2** | ファイル誤実行 / 引数誤認 | `open_downloaded_folder` のディレクトリ検証不足および相対パス | `src/nhk_radio/downloads/cleanup.py` | ✅ 解消 |
| **Medium** | **S3** | SSRF / 外部サイト実行 | `download_url_direct` における未検証 URL の `yt-dlp` 引き渡し | `src/nhk_radio/cli.py`, `src/nhk_radio/core.py` | ✅ 解消 |
| **Low** | **S4** | スキーム未検証 | `webbrowser.open` 呼び出し時の URL スキーム確認 | `src/nhk_radio/gui/listing/programs.py` | ✅ 解消 |
| **Info** | **Q1** | 品質 / テスト環境 | Python 3.13 互換性・Ruff 静的解析・テスト環境 | `pyproject.toml`, `src/nhk_radio/gui/`, `src/nhk_radio/downloads/` | ✅ 解消 |

---

## 1. セキュリティ指摘事項（重要度順）

### S1. 【High】`_play_episode_file` でのメディア拡張子未検証および保存先境界未確認による任意コード実行リスク

- **場所**: `src/nhk_radio/gui/listing/operations.py:120-149`
- **問題点**:
  1. **拡張子制限の不備**:
     エピソード行の右クリックメニュー「デフォルトプレイヤーで再生」は、OS の `open`（macOS）、`os.startfile`（Windows）、`xdg-open`（Linux）を呼び出してファイルを起動します。
     しかし、`--keep-video`（`audio_only=False`）モードでは、`find_episode_downloaded_path` が拡張子チェックをスキップするため、マニフェスト（`.downloaded.json`）やファイル走査結果にある任意の拡張子のファイルが返されます。
     もし共有フォルダや改ざんされたマニフェストにより `.sh`, `.command`, `.bat`, `.exe`, `.app`, `.desktop` などの実行可能ファイルが指定されていた場合、OS はこれらを「メディアファイル」ではなく**「実行可能スクリプト/アプリケーション」として実行**してしまいます。
  2. **保存先境界チェックの欠落**:
     同ファイルの `_delete_episode_file`（削除処理）では `is_within_output_dir(path, self.output_dir)` によるシンボリックリンク脱出防止が行われていますが、`_play_episode_file` ではこの検証が行われていません。保存先ディレクトリ内に置かれた外部へのシンボリックリンクを踏んだ場合、外部の任意コマンドやアプリケーションが起動されるリスクがあります。
- **失敗シナリオ**:
  - 悪意ある `.downloaded.json` を含むアーカイブを展開して本アプリで読み込み、右クリックから「デフォルトプレイヤーで再生」をクリックした際に、埋め込まれたシェルスクリプトが即座に実行される。
- **修正案**:
  再生対象を既知のメディア拡張子（`{".mp3", ".m4a", ".aac", ".wav", ".mp4"}`）のみに制限し、かつ `is_within_output_dir` を事前に検証する。

```python
# operations.py:134 付近の修正案
MEDIA_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".mp4"}

if path is None or path.suffix.lower() not in MEDIA_EXTENSIONS:
    self.status_var.set("再生可能なメディアファイルが見つかりません。")
    return

from ...downloads import is_within_output_dir
if not is_within_output_dir(path, self.output_dir):
    self.status_var.set(f"保存先の外を指すため再生できません: {path}")
    return
```

---

### S2. 【Medium】`open_downloaded_folder` のディレクトリ検証不足および相対パスによる引数誤認リスク

- **場所**: `src/nhk_radio/downloads/cleanup.py:140-166`
- **問題点**:
  1. `if not folder_path.exists():` としか判定しておらず、`folder_path.is_dir()` を確認していません。もしファイルへのパスが渡された場合、フォルダを Finder / Explorer で開くのではなく、ファイル自体が開かれます（実行形式であれば実行される）。
  2. `folder_path` が相対パスでかつ先頭にハイフンが含まれるような場合（例: `-a`）、macOS の `open` や Linux の `xdg-open` のコマンドラインオプションとして誤認識される恐れがあります。
- **修正案**:
  `folder_path.resolve()` により絶対パスへ正規化し、`is_dir()` を明示的に確認する。

```python
# cleanup.py:140 付近の修正案
def open_downloaded_folder(folder_path: Path) -> bool:
    """ダウンロード済みエピソードの保存先フォルダをファイルマネージャーで開く。"""
    resolved = folder_path.resolve()
    if not resolved.is_dir():
        logger.warning(f"フォルダが存在しないかディレクトリではありません: {folder_path}")
        return False

    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(resolved)], check=True)
        elif sys.platform == "win32":
            subprocess.run(["explorer", str(resolved)], check=True)
        else:
            subprocess.run(["xdg-open", str(resolved)], check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        logger.error(f"フォルダを開く際にエラー: {e}")
        return False
```

---

### S3. 【Medium】`download_url_direct` における未検証 URL の `yt-dlp` 引き渡し

- **場所**: `src/nhk_radio/cli.py:163-188`, `src/nhk_radio/core.py:177-192`
- **問題点**:
  - `url_to_program` のパース処理は `re.search(r"[?&]p=([\da-zA-Z]+)_([\da-zA-Z]+)", url)` であり、スキーム（`https`）やドメイン（`nhk.or.jp`）を制限していません。
  - そのため、`http://attacker-controlled.site/?p=0001_01` や `file:///etc/passwd?p=0001_01` などの URL もパースを通過します。
  - `resolve_program_from_url` は安全な正規 NHK URL（`program.url = "https://www.nhk.or.jp/radio/ondemand/detail.html?p=..."`）を生成しているにもかかわらず、`download_url_direct` はユーザーが入力した生の `url` をそのまま `_yt_dlp_command(url, ...)` に渡して `yt-dlp` を実行しています。
  - これにより、攻撃者が細工した URL を指定させた場合、`yt-dlp` の他サイト用エクストラクタの意図しない実行、ローカルファイル読み取り、内部ネットワークへのリクエスト（SSRF）などの踏み台にされるリスクがあります。
- **修正案**:
  `download_url_direct` で `_yt_dlp_command` に渡す URL を、正規化された `program.url` に置き換える。

```python
# cli.py:181 付近の修正案
cmd = _yt_dlp_command(
    program.url,  # ユーザー入力の生の url ではなく、正規化・検証済みの program.url を使用する
    tmpl,
    audio_only=audio_only,
    no_playlist=not bool(max_items),
    max_items=max_items,
)
```

---

### S4. 【Low】`webbrowser.open` 呼び出し時の URL スキーム確認

- **場所**: `src/nhk_radio/gui/listing/programs.py:276-293`
- **問題点**:
  番組ページを既定のブラウザで開く処理において、`webbrowser.open(url)` を呼び出しています。現状は `program.url` が使われるため問題は生じにくいですが、将来の拡張でカスタム URL や不正なスキーム（`javascript:`, `file:` 等）が混入することを防ぐため、スキーム検証を行っておくことが推奨されます。
- **修正案**:
  `url.startswith(("http://", "https://"))` を確認してから `webbrowser.open` を呼ぶ。

---

## 2. 実装済みの堅牢なセキュリティ機構（評価点）

コードベースにはすでに多くの優れたセキュリティ対策が講じられており、不用意な破壊や攻撃を防御できています。

1. **コマンドインジェクション防御**:
   - `run_yt_dlp_subprocess` は常に配列形式で `Popen` を呼び出し、`shell=True` を一切排除している。
   - `_yt_dlp_command` では URL の直前に `--` を置くことで、`-` で始まる URL（例: `--exec=...`）が `yt-dlp` のオプションとして解釈されるのを防いでいる（回帰テスト `test_security_hardening.py` で検証済み）。
2. **フォーマット文字列インジェクション防御**:
   - 番組名や出力ディレクトリに含まれる `%` を `%%` にエスケープしてから yt-dlp の `-o` テンプレートに渡しているため、番組タイトル起因のテンプレートインジェクションが発生しない。
3. **パス名・ディレクトリ名のサニタイズ (`_safe_name`)**:
   - `_normalize_text`、パス区切り文字（`\` や `/`）および制御文字（`\x00-\x1f\x7f`）のアンダースコア置換。
   - Windows 予約デバイス名（`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`）のサフィックス回避。
   - UTF-8 での 255 バイト境界切り詰め。
4. **マニフェストファイル破損防止と安全な排他制御**:
   - `_io.atomic_write_json` における `tempfile.mkstemp` + `Path.replace` のアトミック書き込み。
   - プロセス間ファイルロック（POSIX: `fcntl.flock` / Windows: `msvcrt.locking`）とスレッド間再入可能ロック（`threading.RLock`）の多重ガード。
   - `_resolve_manifest_path` で保存先ルートディレクトリ外を指す相対・絶対パスを自動検知して除外。
5. **リソース枯渇・プロセスハング防止**:
   - yt-dlp サブプロセス実行時に 120 秒のタイムアウト監視を実施。
   - POSIX 環境では `start_new_session=True` と `os.killpg(pgid, signal.SIGTERM)` により子プロセス群（ffmpeg等）も確実に道連れ終了。
   - HTTP リクエスト時の `Retry-After` や指数バックオフに上限（`HTTP_RETRY_MAX_DELAY = 10.0`）を設けて DoS を防止。

---

## 3. 全体設計・保守性に関するフィードバック

1. **Mixin と Protocol による関心の分離**:
   Tkinter GUI は肥大化しやすい傾向にありますが、`GuiOperationsMixin`, `GuiDownloadsMixin`, `DataManager`, `DownloadManager` と機能ごとに適切に分割され、`GuiBrowserProtocol` による静的型検査が維持されている点が優れています。
2. **クラッシュ時のリカバリ機構**:
   上書きダウンロード時に元ファイルを `.nhkradio-bak` に一時退避し、失敗・中断時には自動復元、成功時には削除するライフサイクル管理（および次回起動時の残存整理）が丁寧に実装されています。
3. **テストの拡充**:
   S1〜S3 の脆弱性修正を行った後は、`tests/test_security_hardening.py` にそれぞれのテストケースを追加し、回帰を防止することを強く推奨します。

---

## 4. 対応状況（2026-11-17）

| 項目 | 対応内容 |
|---|---|
| **S1** `_play_episode_file` | `src/nhk_radio/gui/listing/operations.py` にて、`is_within_output_dir(path, self.output_dir)` および `path.resolve().is_relative_to(self.output_dir.resolve())` による保存先境界検証と、`MEDIA_EXTENSIONS` によるメディア拡張子ホワイトリスト検証を追加。またサブプロセスへ渡すパスを `os.path.abspath(path)` に正規化した。 |
| **S2** `open_downloaded_folder` | `src/nhk_radio/downloads/cleanup.py` にて、`folder_path.is_dir()` によるディレクトリ検証と `os.path.abspath(folder_path)` による絶対パス正規化を実装した。 |
| **S3** URL 検証・正規化 | `src/nhk_radio/core.py` の `url_to_program` で `urllib.parse.urlparse` により `http`/`https` スキームと `www.nhk.or.jp` ホストを必須化。`src/nhk_radio/cli.py` の `download_url_direct` で生 URL ではなく正規化済みの `program.url` を `_yt_dlp_command` へ渡すようにした。 |
| **S4** `_open_nhk_program_page` | `src/nhk_radio/gui/listing/programs.py` にて `webbrowser.open` 実行前に `http`/`https` スキームかつ `www.nhk.or.jp` ホストであることを検証するようにした。 |
| **Q1** Python 3.13 / Ruff / モック互換 | GUI 8 モジュール（`activity_view.py`, `browser.py`, `build.py`, `episode_view.py`, `logo.py`, `program_view.py`, `settings_view.py`, `theme_manager.py`）に `from __future__ import annotations` を追加し、`tkinter` 不在環境での `test_cli_imports_without_tkinter` 失敗を解消。`cleanup.py` と `manifest.py` で `Path.stat` モックに影響されない `os.path.*` 呼び出しに修正。`downloads/__init__.py`, `filesystem.py`, `runner.py`, `manifest.py` の Ruff 指摘 35 件をすべて解消した。 |

- **回帰テスト**: `tests/test_security_hardening.py` に S1〜S4 の回帰テスト 12 件を追加。
- **検証結果**:
  - `ruff check .`: `All checks passed!`
  - `mypy src`: `Success: no issues found in 36 source files`
  - `scripts/check_arity.py`: 終了コード 0
  - `pytest`（Python 3.13 + tkinter 含む全テスト）: `591 passed, 41 subtests passed`
  - `scripts/check_non_gui_coverage.py`: `non-GUI coverage OK: 15 files at 100%`（ブランチカバレッジ含む）

