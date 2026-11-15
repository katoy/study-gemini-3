# レビュー指摘の対応状況確認 その 5（2026-11-15）

[review-2026-10-26.md](review-2026-10-26.md) の指摘のうち、[followup](review-2026-10-26-followup.md) で「未対応」とされ、followup-2〜4 で対応済みと記録されていない項目を、現在のコード（`6447622`、2026-11-10）と照らし合わせた。

- 確認の方法: ソースコードを読む。再現スクリプトとテストは実行していない。
- 対象: L1、L3〜L8、G11〜G14、G16、G17。
- [review-2026-11-08-ui.md](review-2026-11-08-ui.md)（GUI レビュー）は全項目が対応済み。注記として、L6 のヒント文字列とヘルプ本文の二重管理だけが残っている。

## 1. 結果の一覧

| # | 状況 | 要点 |
|---|---|---|
| L1 タイムゾーン | ✅ 解消 | 下記 9 で対応した。実際の不具合はエピソードの表示日付だった |
| L3 `manifest.py` | ⚠️ 一部解消 | 下記 7 で 2 点に対応した。プロセスをまたぐロックは残る |
| L4 セキュリティ | ✅ 解消 | 下記 4 で対応した |
| L5 `_safe_name` | ✅ 解消 | 下記 11 で対応した |
| L6 `cli.py` | ✅ 解消 | 下記 12 で対応した |
| L7 `core.py` | ✅ 解消 | 下記 6 で対応した。「最大 9 回試行」は誤りだった |
| L8 `config.py` | ⚠️ 未解消 | 2 点とも残る |
| G11 表示の不整合 | ✅ 解消 | 下記 8 で対応した。当初「実行中: N は無くなった」としたのは誤り |
| G12 小さな UI 不具合 | ✅ 解消 | 下記 8 で対応した |
| G13 UI スレッドでのファイル I/O | ⚠️ 未解消 | 右クリックなどの操作で、UI スレッドから保存先を参照する |
| G14 キャンセル時の `.part` | ✅ 解消 | 下記 10 で対応した。残す意味が無かったため、コメントではなく動作を直した |
| G16 状態の持ち主があいまい | ✅ 解消 | 下記 5 で対応した |
| G17 使われていない値 | ✅ 解消 | `self.result` は使われている。`started_count` / `finished_count` は下記 8 で削除した |

## 2. 詳細

### L1 タイムゾーン

- `text.py:23`: `started_at` の `Z` を `+00:00` に置き換えて読み、そのまま `strftime("%Y-%m-%d")` で日付にしている。JST に変換しないため、JST の 0〜9 時に始まる放送は前日の日付になる。
- `text.py:81`: `fromtimestamp` が実行環境のタイムゾーンに依存する。
- 対応案: `ZoneInfo("Asia/Tokyo")` に変換してから日付と時刻を作る。

### L3 `manifest.py`（`downloads/manifest.py`）

- `:161-163`、`:193-195`: 旧ディレクトリのマニフェストに書かれた相対パスも、新ディレクトリ（`program_output_dir`）を基準に解決している。
- `:15`: ロックは `threading.RLock` だけなので、プロセスをまたぐと効かない。GUI と CLI を同時に動かすと、後から書いた方が勝つ。
- `:58`、`:129-136`: `_load_download_manifest` はキャッシュ中の dict をそのまま返す。`mark_episode_downloaded` はそれを直接書き換えてから保存する。保存後にキャッシュを消しているので通常は問題にならないが、保存が失敗するとディスクと食い違う。
- 対応案: 読み込み結果は `dict(cached_data)` のコピーで返す。相対パスは、読み込んだマニフェストのディレクトリを基準に解決する。

### L4 セキュリティ

- マニフェストのパスを検証していない（`manifest.py:193-198`）。絶対パスや `../` を書き込まれると、GUI の「ファイルを削除」で保存先の外のファイルを消せる。前提はマニフェストの改ざん。
- `runner.py:50`: URL の前に `--` を入れていない。`-` で始まる URL を渡すと、オプションとして解釈される。
- `filesystem.py:85-88`: 番組名を yt-dlp の出力テンプレートにそのまま埋め込んでいる。番組名に `%(` が含まれるとテンプレートエラーになる。`%` を `%%` にエスケープしていない。
- `site_id` のサニタイズ（`filesystem.py:34-37`）は、今回は確認していない。
- 対応案: 解決したパスが番組ディレクトリの下にあることを `is_relative_to` で確かめる。`cmd += ["--", url]` にする。テンプレートへ入れる前に `replace("%", "%%")` する。

### L5 `_safe_name`（`text.py:159-163`）

- 置き換えるのは `\/:*?"<>|` と、末尾のドットと空白だけである。Windows の予約名（`CON`、`NUL` など）、制御文字、255 バイトの長さ上限は扱っていない。

### L6 `cli.py`

- `:28`: GUI をトップレベルで import している。tkinter が無い環境では URL モードも使えない。CI に tkinter が入ったため、CI 上の実害は無くなった。
- `:318`: `-n`（`type=int`）の 0 以下の値を検証していない。
- `:283-286`: 対話モードは、ダウンロードに失敗しても終了コード 0 を返す。

### L7 `core.py`

- `:409-431`: `info is None` のときに投げる `RuntimeError` を、同じ関数の `except Exception` が捕まえる。ログが 2 回出て、メッセージに「エピソード取得失敗:」が二重に付く。
- `:402`、`:449-466`: yt-dlp の `retries: 2` と `refresh_episode_list` の `HTTP_RETRY_COUNT = 3` が重なる。1 回の取得で最大 9 回試行する。
- `:470`: `if stale:` のため、空の stale キャッシュを「キャッシュ無し」とみなす。`:169` の `stale or programs` も同じ。

### L8 `config.py`

- `:91-93`: 移行の失敗を `pass` で握りつぶしている。debug ログも出していない。
- `:120-`: `_load_ui_settings` は既知のキーだけを取り出す。新しい版が書いたキーは、古い版で保存すると消える。

### G11 表示の不整合

- `browser.py:313-319` の `_set_progress` は、`total > 0` のとき `f"{text} {current}/{total}"` を表示する。`download_panel.py:204`、`:226` が `_set_progress(0, 1, "")` を呼ぶため、一覧を取得するたびに " 0/1" と表示される。
- ~~「実行中: N」の概要表示は、現在のコードには無い（解消済み）。~~ **訂正**: `activity_view.py` の `_update_summary` に残っていた。確認時に grep の出力を途中で切っていたため見落とした。`add` が `_update_summary` を呼ばないため、行を追加しても更新されない（下記 8 で対応）。

### G12 小さな UI 不具合

- `listing/episodes.py:302-311`、`:324-`: ☑ のセルの上でマウスが動くたびに `_show_tooltip` が呼ばれ、tooltip を破棄して作り直している。
- `listing/operations.py:68`: 右クリックのたびに `tk.Menu` を作る。`grab_release` は呼んでいるが `destroy` は呼んでいないため、メニューが溜まっていく。
- `episode_view.py:152`: `<Button-2>` に右クリックメニューを割り当てている。Linux と Windows では、これは中ボタンにあたる。

### G13 UI スレッドでのファイル I/O

- `listing/operations.py:120-`、`:171-`、`:190-` など: `find_episode_downloaded_path` を UI スレッドから呼んでいる。この関数は `exists()` を呼び、`filesystem._get_cached_glob_files`（`stat` と走査）も使う。NAS などの遅い保存先では UI が止まる恐れがある（要確認）。

### G14 キャンセル時の `.part`

- `gui/download_manager.py:231-233`: 失敗したときだけ `cleanup_partial_episode_files` を呼び、キャンセルしたときは `.part` を残す。再開を意図しているのかどうか、コメントが無い。

### G16 状態の持ち主があいまい

- `browser.py:172` で `self.programs` に `data_manager.programs` と同じリストを代入している。一方、`browser.py:379` と `data_manager.py:92` は、それぞれ自分の側だけを新しいリストに差し替える。差し替えた後は 2 つが別のリストになる。
- `data_manager.py:86-88` の `clear_all_data` は、共有しているリストを `clear()` で中身ごと消す。
- エピソードキャッシュの上限処理（100 件）が、`data_manager.py:100-102` と `download_panel.py:263-264` の 2 か所にある。

### G17 使われていない値

- `self.result`（`browser.py:134`）は、`browse_programs` の戻り値として `cli.py:248` と `:259` で使われている（解消済み）。
- `gui/download_manager.py:48-49`、`:63`、`:244` の `started_count` / `finished_count` は、増やすだけでどこからも読まれていない。

## 3. 推奨する対応順

1. **L4**: パスの検証、`--`、`%%` のエスケープ。どれも小さな修正で済む。`%(` は再現済みの不具合。
2. **G16**: `programs` の持ち主を `DataManager` に一本化し、上限処理を 1 か所にまとめる。
3. **L7**: `RuntimeError` の包み直しをやめ、リトライを片方に寄せる。stale の判定を `is not None` にする。
4. **L3**: キャッシュはコピーを返す。相対パスの基準ディレクトリを直す。
5. **G12 / G11 / G17**: メニューの `destroy`、tooltip の再利用、" 0/1" の表示、使われていないカウンタの削除。
6. **L1 / L5 / L6 / L8 / G13 / G14**: 影響を確かめてから順次対応する。G14 はコメントの追加だけで済む。

## 4. 対応状況（2026-11-15, ブランチ `fix/l4-security`）

| 項目 | 対応内容 |
|---|---|
| L4 マニフェストのパス | `manifest.py` に `_resolve_manifest_path` を追加した。解決したパスが保存先（`output_dir`）の下に無ければ、警告を出して使わない。`find_episode_downloaded_path` と `get_downloaded_episode_keys` の両方で使う。保存先の下にある絶対パス（旧ディレクトリの記録）は従来どおり使える |
| L4 URL の前の `--` | `runner.py` の `_yt_dlp_command` で、URL の直前に `--` を置く |
| L4 テンプレートの `%` | 番組名の `%` を `%%` にエスケープする（`program_filename_template`）。保存先ディレクトリ名の `%` も、新設した `output_template` でエスケープする。CLI の URL モードも `output_template` を使う。yt-dlp の `prepare_filename` で、`%` がそのまま出力されることを確かめた |
| L4 `site_id` | `_program_storage_id` で `site_id` / `corner_id` を `_safe_name` に通す。通常の英数字の ID は変わらないため、既存の保存先はそのまま使える |

- 回帰テスト: `tests/test_security_hardening.py`（11 件）。修正前は 9 件が失敗した（残る 2 件は、既存の動作が保たれることを確かめるテスト）。CI の non-GUI カバレッジ対象にも追加した。
- 結果: ruff と mypy は合格。pytest は 457 passed。non-GUI カバレッジは 15 ファイルとも 100%。

## 5. 対応状況（2026-11-15, ブランチ `fix/g16-state-ownership`）

| 項目 | 対応内容 |
|---|---|
| G16 番組リストの共有 | `DataManager` から `programs` / `filtered_programs` / `update_programs` を外した。`DataManager` はこれらを読んでいなかったため、番組リストはブラウザだけが持つ。`filtered_programs` は初期化時から `programs` と別のリストにした |
| G16 ワーカーによる `clear()` | キャッシュ全削除のワーカーは `clear_all_cache()`（ディスク）だけを行う。メモリ上のエピソードキャッシュは UI スレッドの `_on_cache_cleared_success` で消す。使われなくなった `clear_all_data` は削除した。番組一覧は表示したまま取り直す（従来も、一度取得し直した後は共有が切れて空にならなかった） |
| G16 上限処理の重複 | エピソードキャッシュへの書き込みを `DataManager.store_episodes` 1 か所にまとめ、上限を定数 `EPISODE_CACHE_MAX_PROGRAMS = 100` にした。取得ワーカーはキャッシュに書かず、UI スレッドの `_finish_fetch` だけが書く |

- 回帰テスト: `tests/test_state_ownership.py`（10 件）。共有を前提にしていた `test_smoke_populate_programs_consistency` は、新しい持ち方に合わせて書き換えた。
- 結果: ruff と mypy は合格。pytest は 467 passed。non-GUI カバレッジは 15 ファイルとも 100%。

## 6. 対応状況（2026-11-15, ブランチ `fix/l7-core-retry`）

| 項目 | 対応内容 |
|---|---|
| L7 ログの二重出力 | `fetch_episodes` で、`info is None` の判定を `try` の外に移した。自分で投げた `RuntimeError` を同じ関数の `except Exception` が捕まえなくなり、エラーログは 1 回、メッセージも「エピソード取得失敗:」が二重に付かなくなった |
| L7 リトライの重複 | **指摘は誤りだった**。yt-dlp 2026.03.17 では、`retries` を参照するのはダウンロード処理（`downloader/http.py` など）だけで、NHK の抽出処理は再試行しない。通信を失敗させて数えると、`retries` を 0・2・10 と変えても `fetch_episodes` 1 回あたりの通信は 2 回（設定ファイルと番組 API）で変わらず、`refresh_episode_list` 全体では 6 回（3 回の試行 × 2）だった。効いていない `retries: 2` を削除した。削除後も 6 回で変わらないことを確かめた |
| L7 空の stale キャッシュ | `refresh_episode_list` の判定を `if stale is not None:` にした。以前に 0 件で取得できた番組は、取得に失敗しても 0 件の stale キャッシュを返す。`fetch_program_list_async` の `stale or programs` は、そこに来る時点で `programs` も空なので結果が変わらず、変更していない |

- 回帰テスト: `tests/test_core_fetch_episodes.py`（6 件）。修正前は 3 件が失敗した（残る 3 件は、既存の動作が保たれることを確かめるテスト）。CI の non-GUI カバレッジ対象にも追加した。
- 結果: ruff と mypy は合格。pytest は 473 passed。non-GUI カバレッジは 15 ファイルとも 100%。

## 7. 対応状況（2026-11-15, ブランチ `fix/l3-manifest`）

| 項目 | 対応内容 |
|---|---|
| L3 キャッシュの dict の書き換え | `_load_download_manifest` は、キャッシュに入れた dict ではなくコピーを返す（キャッシュに当たった場合も外れた場合も）。呼び出し側が書き換えても、キャッシュの内容は変わらない |
| L3 旧ディレクトリの相対パス | 旧ディレクトリのマニフェストにある相対パスは、読み込むときにそのマニフェストのディレクトリを基準にした絶対パスにする。現在の番組ディレクトリのマニフェストの相対パスはそのまま。旧ディレクトリにあり、名前のパターン照合では見つからないファイルも、マニフェスト経由で見つかるようになった |
| L3 プロセスをまたぐロック | **未対応**。GUI と CLI を同時に動かすと、マニフェストは後から書いた方が勝つ。対応にはファイルロック（`fcntl` / `msvcrt`）が必要になり、作業が大きいため見送った |

- 回帰テスト: `tests/test_manifest_loading.py`（5 件）。修正前は 4 件が失敗した（残る 1 件は、現在の番組ディレクトリの相対パスが変わらないことを確かめるテスト）。CI の non-GUI カバレッジ対象にも追加した。旧ディレクトリの相対パスがそのまま返ることを確かめていた `test_load_download_manifest_handles_invalid_and_legacy_files` は、新しい動作に合わせて書き換えた。
- 結果: ruff と mypy は合格。pytest は 478 passed。non-GUI カバレッジは 15 ファイルとも 100%。

## 8. 対応状況（2026-11-15, ブランチ `fix/g11-g12-g17-ui`）

| 項目 | 対応内容 |
|---|---|
| G11 " 0/1" の表示 | エピソード一覧の取得で呼んでいた `_set_progress(0, 1, "")` を削除した。この表示はダウンロードの概要（「実行中: N / 全体: M」）と同じ StringVar を使っていたため、取得のたびに概要を上書きしていた。呼び出し元が無くなった `_set_progress` も削除した |
| G11 「実行中: N」の更新 | `ActivityView.add` で `_update_summary` を呼ぶ。行を追加した時点で件数が更新される |
| G12 右クリックメニュー | `tk.Menu` を 1 つ作って使い回し、開くたびに項目を作り直す。右クリックのたびにメニューが溜まらなくなった。X11 では `tk_popup` がすぐに戻るため、使い終わりに `destroy` する方法は取らなかった |
| G12 tooltip | 同じ文言の tooltip を表示し直すときは、ウィンドウを作り直さず位置だけ動かす |
| G12 `<Button-2>` | 右クリックに使うボタンを `context_menu_buttons` で決める。macOS (aqua) は Button-2 と Button-3、Linux と Windows は Button-3 だけ（Button-2 は中ボタン） |
| G17 | `DownloadManager` の `started_count` / `finished_count` を削除した |

- 回帰テスト: `tests/test_gui_small_fixes.py`（9 件）。修正前は、新設の `context_menu_buttons` を import できず収集の段階で失敗した。
- 変更に合わせて既存テスト 3 件を書き換えた: `_set_progress` の存在と呼び出しを確かめるテスト 2 件、毎回 `tk.Menu` を差し替えて項目を数えるテスト 1 件。
- 気付いた点（未変更）: `download_panel.py` の `_update_download_summary` はどこからも呼ばれていない。
- 結果: ruff と mypy は合格。pytest は 487 passed。non-GUI カバレッジは 15 ファイルとも 100%。

## 9. 対応状況（2026-11-15, ブランチ `fix/l1-timezone`）

### 実際に起きていたこと

- 番組一覧（`text.py:23`）: 番組 API の `started_at` は 182 件すべてが `+09:00` 付きだった（2026-11-15 に確認）。そのため、現在の API では日付はずれていなかった。
- **エピソード一覧**: yt-dlp の `upload_date` は UTC の日付で、アプリはこれを `timestamp`（JST に変換していた）より優先して表示に使っていた。そのため、JST の 0〜9 時の放送は前日の日付で表示されていた。実例として、「マイあさ！」の JST 2026-11-15 07:20 の放送が「2026-11-14(土)」と表示された。yt-dlp 自身のテストデータ（`extractor/nhk.py`、`timestamp: 1751837100` に対して `upload_date: 20250706`）でも同じ。
- 放送時刻（`text.py:81`）: 実行環境のタイムゾーンで表示していた。日本以外の環境では、JST とは違う時刻になっていた。

### 対応内容

| 項目 | 対応内容 |
|---|---|
| エピソードの表示日付 | `display_date` は放送時刻を JST に変換して作る。保存ファイル名（yt-dlp の `%(upload_date)s`）との照合に使う `date` は、yt-dlp の値のままにした。既存のファイル名や保存済みの判定には影響しない |
| エピソードキャッシュ | `save_episode_cache` が `display_date` を `date` から作り直していたため、キャッシュから読むと UTC の日付に戻っていた。`display_date` があればそのまま保存する |
| 放送時刻 | `_format_broadcast_time` は JST で表示する |
| 番組の更新日 | `started_at` にタイムゾーンがあれば JST に変換してから日付にする。現在の API の形式（`+09:00`）では結果は変わらない |
| JST の定義 | `ZoneInfo("Asia/Tokyo")` ではなく固定オフセット（UTC+9）にした。日本には夏時間が無いため結果は同じで、`tzdata` の無い Windows でも動く |

- 残る点: 保存するファイル名の日付は、早朝の回では UTC の前日のまま。直すにはファイル名の付け方と、既存ファイルとの照合の両方を変える必要があるため、今回は表示だけを直した。
- 回帰テスト: `tests/test_timezone.py`（13 件）。実行環境を UTC にしたテストを含む。修正前は 6 件が失敗した。CI の non-GUI カバレッジ対象にも追加した。
- 変更に合わせて既存テスト 2 件を書き換えた: `ZoneInfo` の失敗を想定していたテスト（範囲外の `timestamp` で同じ分岐を確かめる形にした）と、期待値をローカルタイムゾーンで計算していたテスト（UTC の CI では落ちるため、JST の固定値にした）。
- 結果: ruff と mypy は合格。pytest は 500 passed（ローカルのタイムゾーンでも `TZ=UTC` でも）。non-GUI カバレッジは 15 ファイルとも 100%。

## 10. 対応状況（2026-11-16, ブランチ `fix/g14-cancel-cleanup`）

- **調べたこと**: GUI のダウンロードは常に `--force-overwrites` 付きで yt-dlp を動かす。yt-dlp では `--force-overwrites` が `--no-continue` を含む（`yt_dlp/__init__.py` の `if opts.overwrites:  # --force-overwrites implies --no-continue`）。そのため、キャンセルで残した `.part` から再開されることは無く、再試行しない限り保存先に残り続けるだけだった。CLI は Ctrl+C で中断したときに片付けており（`cli.py`）、GUI だけが残していた。
- **対応**: `DownloadManager._download_worker` で、キャンセル時も失敗時と同じく `cleanup_partial_episode_files` を呼ぶ。`run_yt_dlp_subprocess` はキャンセル時にプロセスグループを止め、`process.wait` で終了を待ってから戻るため、書き込み中のファイルを消すことは無い。
- 回帰テスト: `tests/test_cancel_cleanup.py`（2 件）。修正前はキャンセルの 1 件が失敗した。
- 結果: ruff と mypy は合格。pytest は 502 passed。

## 11. 対応状況（2026-11-16, ブランチ `fix/l5-safe-name`）

| 項目 | 対応内容 |
|---|---|
| 制御文字 | 改行・タブ・NUL などの制御文字（`\x00`〜`\x1f`、`\x7f`）も `_` に置き換える |
| Windows の予約名 | `CON`・`PRN`・`AUX`・`NUL`・`COM1`〜`COM9`・`LPT1`〜`LPT9` は、大文字小文字を問わず末尾に `_` を付ける。拡張子付き（`NUL.txt`）も同じく `NUL_.txt` にする。`CONSOLE` や `COM10` のように予約名そのものでない名前は変えない |
| 長さ上限 | UTF-8 で 255 バイト（`SAFE_NAME_MAX_BYTES`）を超える名前は、文字の途中で切らないように詰める。詰めた結果の末尾がドットや空白になれば取り除く |

- 既存の保存先・ファイル名への影響: 結果が変わるのは、上の 3 つに当たる名前だけ。普通の番組名・エピソード名の結果は従来と同じで、既存ファイルとの照合は変わらない。
- 残る点: `_safe_name` が詰めるのは番組名などの 1 要素だけ。yt-dlp が作るファイル名全体（`日付_番組名_エピソード名.拡張子`）は、エピソード名が長いと 255 バイトを超えうる。
- 回帰テスト: `tests/test_safe_name.py`（20 件）。修正前は、新設の定数を import できず収集の段階で失敗した。CI の non-GUI カバレッジ対象にも追加した。
- 結果: ruff と mypy は合格。pytest は 520 passed。non-GUI カバレッジは 15 ファイルとも 100%。

## 12. 対応状況（2026-11-16, ブランチ `fix/l6-cli`）

| 項目 | 対応内容 |
|---|---|
| GUI のトップレベル import | `sys.modules['tkinter'] = None` で tkinter が無い環境を再現すると、`import nhk_radio.cli` が `ImportError` になり、URL モードも使えなかった。GUI の import を `try/except ImportError` で囲み、import できなければ `browse_programs = None` とする。対話モードは GUI が使えないものとして CLI のフォールバックで動く。関数内での遅延 import にしなかったのは、`nhk_radio.cli.browse_programs` を差し替えている既存テストを保つため |
| `-n` の負の値 | `-n` / `--max-items` は 1 以上の整数だけを受け付ける。0 以下や整数でない値は、argparse のエラー（終了コード 2）にする |
| 対話モードの終了コード | `_download_selected_episodes` は `(完了件数, 失敗件数)` を返す。`interactive_mode` と `_interactive_cli_fallback` は、失敗が 1 件でもあれば 1、なければ 0 を返し、`run_cli` がそれを終了コードにする |

- 回帰テスト: `tests/test_cli_l6.py`（12 件）。修正前は 10 件が失敗した。CI の non-GUI カバレッジ対象にも追加した。
- 戻り値を変えたため、`_download_selected_episodes` の件数を確かめる既存テスト 6 件を `(完了件数, 失敗件数)` に合わせて書き換えた。
- 結果: ruff と mypy は合格。pytest は 534 passed。non-GUI カバレッジは 15 ファイルとも 100%。
