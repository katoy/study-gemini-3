# レビュー指摘の対応状況確認（2026-10-27 再確認・対応完了）

[review-2026-10-26.md](review-2026-10-26.md) の指摘について、コミット `f90b0f7`、`4431d5c`、および今回のフォローアップ修正で対処を完了した。

- 結果: ruff と mypy は合格。pytest は 377 passed。カバレッジは 99.77%。`scripts/check_arity.py` は終了コード 0。

凡例:

- ✅ 対処済み
- ⚠️ 一部だけ対処、または副作用あり
- ❌ 未対処または効いていない
- 🆕 今回の修正で新たに入った問題
- — 手を付けていない

## 1. 要対応項目の処置結果

### ✅ [High] `--print after_move:filepath` を付けたため、進捗表示が出なくなる問題
- 対処: `src/nhk_radio/downloads/runner.py` で `print_filepath=True` の際に `--print after_move:filepath` に加えて `--progress` も指定するように修正。進捗行と保存パス行の両方が正常に出力されることを確認。

### ✅ M4(3): audio_only の指定が一部の呼び出し元にしか渡っていない
- 対処: `filesystem._episode_output_matches`, `_episode_output_candidates`, `manifest.get_downloaded_episode_keys`, `find_episode_downloaded_path`, `is_episode_downloaded`, `sync_episode_download_history` の既定引数をすべて `audio_only: bool = True` に統一。また `cli.py` や `download_manager.py` からも `audio_only` を明示渡しするように揃えた。

### ✅ G4: 退避ファイル `.bak` が残ったり、保存済みと誤判定されたりする
- 対処:
  1. `filesystem._episode_output_matches` で `name.endswith(".bak")` を除外対象に追加（`.part` と同等の扱い）。
  2. `cleanup_partial_episode_files` にて、残存 `.bak` があり元ファイルが存在しない場合はリネーム復元し、元ファイルが存在する場合は削除する処理を追加。
  3. `download_manager.py` のダウンロード開始前にも残存 `.bak` のクリーンアップを追加。

### ✅ M8: 判定にモジュールグローバルのフラグを使っている
- 対処: モジュールグローバル変数 `_LAST_FETCH_HAD_FAILURE` を完全撤廃。`_fetch_all_with_status_async() -> tuple[list[Program], bool]` および `_fetch_by_genre_with_status_async(genre: str) -> tuple[list[Program], bool]` を新設し、タプルの戻り値で成否を明示返却。`fetch_program_list_async` 側で判定するように変更（既存の `_fetch_all_async` と `_fetch_by_genre_async` は後方互換ラッパーとして維持）。

## 2. 指摘ごとの状況

### 非 GUI

| # | 状況 | 補足 |
|---|---|---|
| H1 | ✅ | 照合側を yt-dlp と同じファイル名変換に揃え、`--print` と `--progress` を併用して実パスの記録と進捗表示の両立を確認 |
| H2 | ✅ | EOF で `return None` する |
| M1 | ✅ | timestamp を JST の `YYYYMMDD` に変換する |
| M2 | ✅ | dict かどうかを確認する |
| M3 | ✅ | 復元に失敗したら None を返す |
| M4 | ✅ | (1) `.part-Frag` の除去 ✅、(2) `glob.escape` ✅、(3) `audio_only` の既定値を `True` に統一し各呼び出し元にも伝播 ✅ |
| M5 | ✅ | 末尾の完全一致で照合する（実ファイルで確認） |
| M6 | ✅ | Ctrl+C を再送出し、掃除してから中断する |
| M7 | ✅ | タイムアウトとコマンド未検出を処理する |
| M8 | ✅ | モジュールグローバルフラグを撤廃し、ステータスを戻り値タプルで返す設計に改修 |
| M9 | ✅ | 例外の捕捉を `(TypeError, ValueError)` に限定した |
| M10 | ✅ | encoding の指定、監視スレッドによるキャンセル、失敗時の出力ログ |
| L2 | ✅ | `stat()` の失敗と、環境変数の値の不正を処理する |
| L9 | ✅ | `check_arity.py` の検査対象修正、`generate_demo.py` の try-finally による ffmpeg プロセス後始末、`update_coverage_readme.py` の encoding 指定 |
| L1, L3–L8 | — | 未対応 |

### GUI

| # | 状況 | 補足 |
|---|---|---|
| G1 | ✅ | 準備処理を `try` の中に移し、`finally` で必ず結果を通知する |
| G2 | ✅ | `start_download` の中で登録し、キューが空になるまでポーリングを続ける |
| G3 | ⚠️ | 世代番号の導入と True/False 両方の反映は ✅。ワーカーからの `root.after` の直呼びは残っている。検索欄のデバウンスは未対応 |
| G4 | ✅ | 元ファイルの退避・復元、`.bak` の照合除外、残存 `.bak` の復元/掃除を実装 |
| G5 | ⚠️ | `terminate` が効くようになった。`start_new_session` と `killpg` は未対応 |
| G6 | ✅ | 取得中でも確認ダイアログを出して閉じられる |
| G7 | ✅ | フラグを解除してから通知する |
| G8 | ✅ | (1) 保存済みの設定値で検索履歴を保存するようになった。(2) 文字サイズを `int` で保存する |
| G9 | ✅ | 判定をマウスイベント（`num == 1`）に限定し、Enter キーへの副作用は解消した |
| G10 | ✅ | toplevel と修飾キーを判定する |
| G11–G14, G16, G17 | — | 未対応 |
| G15 | ✅ | `protocols.py` の `current_font_size` を `int` に修正し、`browser.py` / `styling.py` との型整合性を確保 |

### カバレッジ・設定

| 指摘 | 状況 |
|---|---|
| protocols.py のスタブ、設定の二重管理、mypy のバージョン | ✅ |
| GUI 11 ファイルの omit、`except OSError` の除外 | — 未対応 |

## 3. そのほか

- `scripts/check_arity.py` は、`*args` を展開して渡す呼び出しの検査を飛ばすようになり、GUI 配下の全メソッド arity 検査に合格（終了コード 0）。
- `src/radio.egg-info/` は `.gitignore` の対象（`*.egg-info/`）に含まれており、未追跡であることを確認。

## 4. 検証結果サマリー

- `uv run ruff check .` : All checks passed!
- `uv run mypy src` : Success: no issues found in 31 source files
- `uv run python scripts/check_arity.py` : 終了コード 0 (Pass)
- `uv run pytest` : 377 passed, coverage 99.77%
