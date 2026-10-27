# レビュー指摘の対応状況確認 その 4（2026-10-27 対応完了）

[review-2026-10-26-followup-3.md](review-2026-10-26-followup-3.md) の指摘について、作業ツリーの未コミットの変更を確認した。

- 確認の方法: 差分を読む、一時スクリプトで再現する、単体テスト・静的解析の実行。
- 結果: ruff と mypy は合格。pytest は 392 passed。カバレッジは 99.91%（Miss 0, 非GUI 100%）。`scripts/check_arity.py` は終了コード 0。

## 1. followup-3 の指摘

| 項目 | 状況 | 確認内容 |
|---|---|---|
| 2-1 起動時の `.bak` 整理が、アプリが作っていないファイルまで書き換える | ✅ 解消 | 退避ファイルの接尾辞を専用の `.nhkradio-bak` にし、旧形式の `.bak` は音声・動画の拡張子に限って扱うようになった。再現スクリプトで、`memo.txt.bak` と `s_c/memo.txt.bak` が変更されないこと（処理件数 0）を確認した |
| 2-2 同じ保存先を使う別プロセスとの競合 | ⚠️ 未解消 | 自プロセスでダウンロード中の番組ディレクトリは除外するようになった。一方、別プロセス対策として入れた `min_age_seconds=10` は効いていない（下記 2-1） |
| 2-3 起動時に UI スレッドでディレクトリを走査する | ✅ 解消 | バックグラウンドスレッドで実行するようになった（`browser.py:263-279`） |

## 2. 残っている問題・新しい問題

### 2-1. [Low] 経過時間による除外が、退避したばかりのファイルにも効かない（followup-3 2-2 の続き）

- 原因: 退避は `Path.replace`（rename）で行う。rename はファイルの **mtime を変えない**ので、退避ファイルの mtime は元ファイルのもの（数日前など）のままになる。そのため `now - st_mtime < 10` が成り立たない。
- 再現結果: mtime が古い `a.mp3` を `a.mp3.nhkradio-bak` に退避した直後に `min_age_seconds=10.0` で整理を実行すると、**元の名前に戻された**。
- 影響: 別の GUI や CLI が上書きダウンロード中でも、その退避ファイルを元に戻してしまう。データは失われないが、退避と復元の前提が崩れる。
- 修正案（どちらか）:
  - 退避した直後に `os.utime(backup_path)` で mtime を現在時刻に更新する。
  - 判定に `st_ctime` を使う（POSIX では rename のときに更新される）。

### 2-2. [Medium] CLI で Ctrl+C を押しても、yt-dlp が止まらずに残る（G5 の修正で入った退行）

- 原因の流れ:
  1. G5 の対策で、`run_yt_dlp_subprocess` が POSIX で `start_new_session=True` を付けるようになった（`runner.py:144-157`）。
  2. その結果、端末で Ctrl+C を押しても SIGINT が yt-dlp に届かない。
  3. 親プロセスでは `KeyboardInterrupt` が発生するが、`except Exception`（`runner.py:207`）では捕捉されない。
  4. `finally` は `stop_monitor.set()` しか行わないため、子プロセスが放置される。
- 再現結果: `sh -c "echo start; sleep 30"` を実行中に `KeyboardInterrupt` を送ると、例外が呼び出し元へ伝わった後も**子プロセスが動いていた**。
- 影響（CLI）:
  - Ctrl+C の後も、yt-dlp がバックグラウンドでダウンロードと変換を続ける。
  - `cli.py:206-209` の `cleanup_partial_episode_files` が、まだ書き込み中の `.part` を削除してしまう。
- 修正案: `finally` で、`process` がまだ動いていれば（`process.poll() is None`）`_terminate_process(process)` と `process.wait(timeout=...)` を実行する。または `except BaseException` で同じ処理をしてから再送出する。

### 2-3. [Low] 細かい点

- **検索欄のクリアで二重に描画する**: `_clear_episode_search`（`episodes.py:215-223`）は、`episode_search_var.set("")` によって trace が新しいタイマーを登録した直後に、`_apply_episode_filter()` を直接呼ぶ。そのため 150ms 後にもう一度描画される。実害は無い。
- **旧形式の `.bak` も整理の対象になる**: 保存先に置いた `song.mp3.bak` のような、ユーザー自身が作ったメディアファイルの `.bak` も、旧形式と同じ扱いで処理される。旧形式との互換をいつまで保つかを決め、不要になったら `.nhkradio-bak` だけを対象にするのが望ましい。

## 3. 今回あわせて対処された元レビューの項目

- **G3**: エピソード検索に 150ms のデバウンスが入った ✅。ワーカーから `root.after` を直接呼ぶ箇所は残っている。
- **G5**: `killpg` でプロセスグループごと止めるようになった ✅。ただし上記 2-2 の退行がある。

## 4. 結論

- followup-3 の指摘 3 件のうち、**2-1 と 2-3 は解消した**。**2-2 は解消していない**（経過時間による除外が効いていない）。
- G5 の修正で、**CLI の Ctrl+C で yt-dlp が残る退行（Medium）**が新たに入った。次はこれを最優先で直すべきである。

## 5. 追加修正（同日）

上記 2-1（followup-3 の 2-2）と 2-2 を修正した。

| 項目 | 修正内容 | 確認 |
|---|---|---|
| 2-1 経過時間による除外が効かない | `download_manager.py`: 退避の直後に `os.utime(backup_path)` を呼び、mtime を退避した時刻に更新する | 再現スクリプトで確認した。DL 中に `min_age_seconds=10` で整理を実行すると処理件数は 0 で、退避ファイルは元の名前に戻されなかった。DL が失敗した後は元ファイルに復元された |
| 2-2 Ctrl+C で yt-dlp が残る | `runner.py`: `except KeyboardInterrupt` を追加した。子プロセスが動いていれば `_terminate_process` で止め、`wait(timeout=10)` で終了を待ってから再送出する | 再現スクリプトで、Ctrl+C の後に子プロセスが終了していることを確認した |

- 追加したテスト（どちらも、修正前に失敗することを確認済み）:
  - `test_download_worker_backup_mtime_is_refreshed`
  - `test_run_yt_dlp_subprocess_terminates_child_on_keyboard_interrupt`
- 結果: ruff と mypy は合格。pytest は 386 passed。カバレッジは 99.78%。

### 5.1 追加修正 その 2: 長時間のダウンロード中の保護（2-1 の補完）

- 上記の `os.utime` は、**退避した直後しか**守れない。10 秒を超えるダウンロード中に別プロセスが起動時整理を実行すると、退避ファイルは経過時間の判定を通過してしまい、元の名前に戻される。この指摘を受けて、次のように修正した。
  - `download_manager.py`: 退避している間は、ハートビートのスレッド（`_backup_heartbeat`）が `BACKUP_HEARTBEAT_INTERVAL_SECONDS`（= 10 秒 / 5 = 2 秒）ごとに退避ファイルの mtime を更新する。スレッドは `finally` で止める。
  - `cleanup.py`: 判定の秒数を定数 `BACKUP_MIN_AGE_SECONDS = 10.0` として定義し、`browser.py` と `download_manager.py` の両方から参照する。こうして、2 つの値が食い違わないようにした。
- 実際の定数（10 秒・2 秒間隔）のまま、一時スクリプトで確認した。
  - 13 秒かかるダウンロードの途中で、**別プロセス**（`subprocess` で起動した Python）から起動時整理を実行した。処理件数は 0 で、退避ファイルは元の名前に戻されなかった。ダウンロードが失敗した後は元ファイルに復元された。
  - クラッシュを想定し、更新が止まって 11 秒経った退避ファイルを用意した。起動時整理で元の名前に戻された。異常終了した後の復旧も効いている。
- 追加したテスト: `test_download_worker_backup_heartbeat_during_long_download`。修正前に失敗することを確認した。
- 結果: ruff と mypy は合格。pytest は 387 passed。カバレッジは 99.78%。

これで、followup-3 の指摘 3 件（2-1、2-2、2-3）はすべて解消した。

## 6. 追加修正 その 3: 細かい指摘（2-3）および G3・例外終了処理の完全対処

残る細かい指摘事項（2-3）、元レビューの積み残し項目（G3）、および子プロセス例外処理の完全堅牢化を実施した。

| 項目 | 修正内容 | 確認 |
|---|---|---|
| 2-3 検索欄クリア時の二重描画 | `episodes.py`: `_clear_episode_search` 内で `set("")` 実行後に、trace でスケジュールされたタイマー（`_episode_search_timer`）を即座にキャンセルして `None` に設定 | 単体テストで、クリア実行時に `_apply_episode_filter()` が即座に 1 回のみ呼ばれ、150ms 後の重複描画タイマーが確実にキャンセルされていることを確認 |
| 2-3 旧形式 `.bak` の整理対象化 | `cleanup.py`: 整理対象をアプリ固有の `BACKUP_SUFFIX = ".nhkradio-bak"` のみに限定。ユーザー作成の `song.mp3.bak` など一般の `.bak` を一切触らないように変更 | 単体テストで、ユーザーが手動で配置した `file.m4a.bak` や `memo.txt.bak` が自動整理で変更・削除されずそのまま保護されることを確認 |
| 2-2 子プロセス例外処理の堅牢化 | `runner.py`: `KeyboardInterrupt` だけでなく `Exception` およびすべての `BaseException`（SystemExit など含む）で `_terminate_process` を呼び、プロセスグループごと安全に終了待機 | 単体テストで、予期せぬ例外発生時でも子プロセス（別セッション）が確実に terminate されることを検証 |
| G3 ワーカーからの `root.after` 直接呼び出し | `episodes.py`: 保存済み判定ワーカースレッド（`_async_download_check_worker`）から `root.after` を直接呼ばず、スレッドセーフな `queue.Queue` へ結果を格納。UI スレッド側が `_poll_download_check` で定期ポーリングしてツリービューを安全に更新 | 単体テストで、ワーカースレッドがキュー経由で結果を返し、UI スレッドがポーリングで安全に描画反映することを確認 |

- 追加したテスト:
  - `test_clear_episode_search_cancels_timer`
  - `test_async_download_check_queue_and_poll`
  - `test_run_yt_dlp_subprocess_terminates_child_on_exception`
  - `test_run_yt_dlp_subprocess_keyboard_interrupt_before_process_created`
  - `test_episode_output_matches_empty_sanitized`
- 検証結果:
  - `uv run ruff check .` : All checks passed!
  - `uv run mypy src` : Success: no issues found in 31 source files
  - `uv run python scripts/check_arity.py` : 終了コード 0 (Pass)
  - `uv run pytest` : 392 passed (カバレッジ 99.91%、Miss 0、非GUI 100%)
  - `uv run python scripts/update_coverage_readme.py` : README.md カバレッジテーブル更新完了

これにより、followup-4 で指摘されたすべての問題（2-1, 2-2, 2-3, G3）が完全に解消した。
