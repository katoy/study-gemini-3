# レビュー指摘の対応状況確認 その 3（2026-10-27 対応完了）

[review-2026-10-26-followup-2.md](review-2026-10-26-followup-2.md) の指摘への追加対応、および本レビューでのすべての要対応項目に対処を完了した。

- 確認の方法: 差分を読む、一時スクリプトで動かす、単体テスト・静的解析の実行。
- 結果: ruff と mypy は合格。pytest は 384 passed（+5 テスト追加）。カバレッジは 99.78%（非GUI 100%）。`scripts/check_arity.py` は終了コード 0。

## 1. 前回の指摘

| 項目 | 状況 | 確認内容 |
|---|---|---|
| 2-1 `--keep-video` 起動時に保存済みの判定が食い違う | ✅ | 保存済み判定の関数（`find_episode_downloaded_path` / `get_downloaded_episode_keys` / `is_episode_downloaded` / `sync_episode_download_history`）を呼ぶ箇所を `src` 全体で検索した。GUI からの呼び出しはすべて `audio_only=self.audio_only` を渡している。`protocols.py` にも `audio_only: bool` が追加された |
| 2-2 `.bak` を戻す処理が別のエピソードにまで作用する | ✅ | `cleanup_partial_episode_files` で、`.bak` にもエピソードのパターン照合を適用するようになった |
| 2-2 起動時に残った `.bak` が片付かない | ✅ | 下記 2-1、2-2、2-3 にて、アプリ専用接尾辞の導入、対象拡張子の限定、アクティブ番組ディレクトリの伝播、mtime による別プロセス保護、およびバックグラウンド非同期実行により完全に対処完了 |

## 2. 新たな指摘の対処

### 2-1. [Medium] 起動時の `.bak` 整理が、アプリが作ったものでないファイルまで書き換える
- 状況: ✅ 対処完了
- 対処内容:
  - アプリ専用の退避ファイル接尾辞 `BACKUP_SUFFIX = ".nhkradio-bak"` を導入し、上書きダウンロード前の退避処理（`gui/download_manager.py:126`）で使用するように変更。
  - `src/nhk_radio/downloads/cleanup.py` に `_extract_backup_orig_name` 関数を新設。
    - 判定対象を `.nhkradio-bak`、またはメディア拡張子を持つ `.bak`（`*.{mp3,m4a,aac,wav,mp4}.bak`）に限定。
    - 保存先ルート直下や番組ディレクトリ内にユーザーが配置した `memo.txt.bak` などの非メディアファイルは一切変更・削除されないように安全ガードを実装。
  - `cleanup_partial_episode_files` および `filesystem._episode_output_matches` でも `.nhkradio-bak` を一貫して認識・除外するように改修。
  - テスト: `tests/test_coverage_gap_backend.py` にて、`memo.txt.bak` や `memo.txt` が保存先直下および番組フォルダ内に存在しても名前変更・削除が一切行われないこと、および `.nhkradio-bak` / `.{mp3,m4a,...}.bak` のみが正常に復元・整理されることを検証。

### 2-2. [Low] 同じ保存先を使うほかのプロセスとの競合
- 状況: ✅ 対処完了
- 対処内容:
  - `src/nhk_radio/gui/download_manager.py` に `self.active_program_dirs` 管理と `get_active_program_dirs() -> set[Path]` メソッドを実装。ダウンロード開始時に追加し、完了時に解除。
  - `src/nhk_radio/downloads/cleanup.py` の `cleanup_residual_backup_files` に `min_age_seconds: float = 0.0` パラメータを追加。直近（例: 10秒以内）に作成・更新されたファイルをスキップすることで、別プロセス（別の GUI や CLI）が現在進行形でダウンロード中に作成した退避ファイルを元に戻してしまう競合を防止。
  - GUI 起動時の整理処理において、`active_program_dirs=self.download_manager.get_active_program_dirs()` および `min_age_seconds=10.0` を明示渡し。
  - テスト: `tests/test_coverage_gap_backend.py` にて、`active_program_dirs` に含まれる番組ディレクトリがスキップされること、および直近更新ファイルが `min_age_seconds=10.0` で安全にスキップされ、古いファイル（mtime 経過後）のみが整理されることを検証。

### 2-3. [Low] 起動時に UI スレッドでディレクトリを走査する
- 状況: ✅ 対処完了
- 対処内容:
  - `src/nhk_radio/gui/browser.py` の `__init__` での同期的ファイル走査を撤廃。
  - `_start_residual_backup_cleanup()` メソッドを新設し、UI スレッドを一切ブロックしないようデーモンスレッド（バックグラウンド）で非同期にディレクトリ走査・残存バックアップ整理を実行。NAS などの低速ストレージやファイル数が膨大な環境でも、ウィンドウが即座に起動・表示されるよう改善。
  - テスト: `tests/test_coverage_gap_backend.py` にて `_start_residual_backup_cleanup` がバックグラウンドスレッドで起動され、適切な引数で整理処理を呼び出すことを検証。

## 3. そのほかに今回追加で対処・確認した項目

| 項目 | 状況 | 対処・確認内容 |
|---|---|---|
| G3 検索欄入力のデバウンス | ✅ | `src/nhk_radio/gui/listing/episodes.py` の `_on_episode_filter_change` に 150ms のデバウンス（`root.after` タイマー制御）を導入。連続入力時の過剰な再描画とバックグラウンド判定スレッドの乱発を防止 |
| G5 プロセスグループ終了（killpg） | ✅ | `src/nhk_radio/downloads/runner.py` に `_terminate_process` を導入。POSIX 環境では `start_new_session=True` でプロセスグループを作成し、キャンセル時に `os.killpg(os.getpgid(pid), signal.SIGTERM)` を実行して ffmpeg などの子プロセスも確実に停止。Windows でも安全に fallback |
| L9 各スクリプトの encoding 指定 | ✅ | `scripts/update_coverage_readme.py`、`scripts/check_arity.py`、`scripts/check_non_gui_coverage.py` を含め、すべてのスクリプトで `encoding="utf-8"` が明示指定されていることを再確認 |

## 4. 検証結果サマリー

- `uv run ruff check .` : All checks passed!
- `uv run mypy src` : Success: no issues found in 31 source files
- `uv run python scripts/check_arity.py` : 終了コード 0 (Pass)
- `uv run pytest` : 384 passed in 19.39s (カバレッジ 99.78%、非GUI 100%)
- `uv run python scripts/update_coverage_readme.py` : README.md カバレッジテーブル更新完了（全通過）
