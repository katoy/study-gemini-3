# レビュー指摘の対応状況確認 その 2（2026-10-27 対応完了）

コミット `b7ce6a6`（[review-2026-10-26-followup.md](review-2026-10-26-followup.md) の指摘への対処）に対する追加指摘、および本レビューでのすべての要対応項目に対処を完了した。

- 結果: ruff と mypy は合格。pytest は 379 passed（+2 テスト追加）。カバレッジは 99.77%。`scripts/check_arity.py` は終了コード 0。

## 1. 前回の要対応項目

| 項目 | 状況 | 確認内容 |
|---|---|---|
| 進捗表示が出なくなる問題 | ✅ | `--progress` は `noprogress=False` に設定される。進捗行が出力されることを確認済み |
| M4(3) audio_only の伝播 | ✅ | 下記 2-1 にて GUI 呼び出し全箇所へ `audio_only=self.audio_only` を明示渡し完了。`--keep-video` 時の食い違いを解消 |
| G4 の `.bak` | ✅ | 下記 2-2 にて `.bak` 処理をエピソードパターン照合で絞り込み完了。起動時の残存 `.bak` 整理処理も追加 |
| M8 グローバルフラグ | ✅ | 撤廃され、成否を戻り値（タプル）で返す設計に改修済み |

## 2. 新たな指摘の対処

### 2-1. [Medium] `--keep-video` で GUI を起動すると、保存済みの判定が画面内で食い違う
- 状況: ✅ 対処完了
- 対処内容:
  - `src/nhk_radio/gui/protocols.py` の `GuiBrowserProtocol` に `audio_only: bool` を追加し、Mixin 間での型契約を保証。
  - `src/nhk_radio/gui/listing/episodes.py`:
    - `_async_download_check_worker` (112行)
    - `_refresh_downloaded_column` (156行)
    - `_refresh_saved_only_button_state` (191行)
    - `_sorted_episodes` (224行)
    すべての `get_downloaded_episode_keys` 呼び出しに `audio_only=self.audio_only` を明示。
  - `src/nhk_radio/gui/listing/programs.py`:
    - `_update_program_overview` (220行) にて `audio_only=self.audio_only` を明示。
  - `src/nhk_radio/gui/download_panel.py`:
    - `_start_download_selected` (103行) の上書き確認にて `audio_only=self.audio_only` を明示。
  - `src/nhk_radio/gui/listing/operations.py`:
    - `_play_episode_file` (125行)
    - `_copy_episode_path` (174行)
    - `_copy_episode_filename` (191行)
    - `_delete_episode_file` (208行)
    - `_redownload_episode` (237行)
    すべての `find_episode_downloaded_path` 呼び出しに `audio_only=self.audio_only` を明示。
  - `src/nhk_radio/gui/download_manager.py`:
    - 完了時の `sync_episode_download_history` (184行) に `audio_only=self.audio_only` を明示。
  - テスト: `tests/test_gui_consistency.py` に `test_keep_video_gui_consistency` を追加し、`audio_only=False` 下で保存マーク（☑）・保存済みフィルタ・ソート・番組概要カウント・再生・パスコピー・上書き確認が正常に動画ファイル（`.mp4`）を認識することを網羅検証。

### 2-2. [Low] `.bak` を戻す処理が、別のエピソードの退避ファイルにまで作用する
- 状況: ✅ 対処完了
- 対処内容:
  - `src/nhk_radio/downloads/cleanup.py` の `cleanup_partial_episode_files` において、`.bak` ファイルの元の名前 `orig_name = path.name[:-4]` が `patterns`（対象エピソードの命名パターン）に合致する場合（`any(fnmatch.fnmatch(orig_name, pattern) for pattern in patterns)`）に限定して復元または削除を行うように修正。他エピソードの退避ファイルには一切触れないように改善。
  - 起動時の残存 `.bak` 対策として、`cleanup.py` に `cleanup_residual_backup_files` を新設。ダウンロード中でない番組フォルダを安全に走査して残存 `.bak` を復元・削除する機能を実装し、`EpisodeGuiBrowser` の初期化時に実行するように組み込み。
  - テスト: `tests/test_coverage_gap_backend.py` にて、同一番組フォルダ内に別エピソードの `.bak` が存在しても巻き込まれずに維持されること、対象エピソードのみ復元／削除されること、および `cleanup_residual_backup_files` の全ブランチ・例外処理を検証するテストを追加。

## 3. そのほかに今回確認した項目

| 項目 | 状況 | 補足 |
|---|---|---|
| G15（部分）`protocols.py` の `current_font_size` | ✅ | `int` に統一済み |
| L9 `generate_demo.py` | ✅ | `try/finally` で ffmpeg を確実に終了させる処理を実装済み |
| L9 `update_coverage_readme.py` の encoding | ✅ | `open(..., encoding="utf-8")`、`read_text(encoding="utf-8")`、`write_text(..., encoding="utf-8")` が指定されていることを確認・実機検証済み |

## 4. 検証結果サマリー

- `uv run ruff check .` : All checks passed!
- `uv run mypy src` : Success: no issues found in 31 source files
- `uv run python scripts/check_arity.py` : 終了コード 0 (Pass)
- `uv run pytest` : 379 passed in 15.73s (カバレッジ 99.77%)
- `uv run python scripts/update_coverage_readme.py` : README.md カバレッジテーブル更新完了（全通過）
