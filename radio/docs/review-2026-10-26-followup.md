# レビュー指摘の対応状況確認（2026-10-27）

[review-2026-10-26.md](review-2026-10-26.md) の指摘について、作業ツリーの**未コミットの変更**（21 ファイル、+617/-133）が対処できているかを確認した。

- 確認した方法は 3 つ。差分を読む、一時スクリプトで実際に動かす、yt-dlp 2026.03.17 のソースを読む。
- ruff と mypy は合格。pytest は 370 passed（22 件増）。カバレッジは 99.77% で、未到達は `filesystem.py:163` と分岐 4 箇所。

凡例:

- ✅ 対処済み
- ⚠️ 一部だけ対処、または副作用あり
- ❌ 対処されていない、または効いていない
- — 手を付けていない

## 1. 対処できていない／副作用がある項目（要対応）

### ❌ G4: 上書き DL で元ファイルが失われる問題は、まだ直っていない

- 修正の内容: 事前の `unlink` をやめ、代わりに `--force-overwrites` を付けた。
- 効いていない理由: yt-dlp の `YoutubeDL.existing_file()`（`YoutubeDL.py:3287-3295`）は、`overwrites` が真だと**ダウンロードの前に**既存ファイルを `os.remove` する。そのため、DL が失敗すると元ファイルが消える点は以前と変わらない。
- 修正案: 既存ファイルを `*.bak` などに rename で退避してから DL する。成功したら退避ファイルを削除し、失敗またはキャンセルなら元に戻す。

### ⚠️ `--force-overwrites` を全コマンドに付けたことによる退行

- `runner._yt_dlp_command` は CLI の URL 直接モード（`cli.py:169`）でも使われる。
- 以前は既存ファイルを yt-dlp がスキップしていたが、今は**シリーズ全件を毎回ダウンロードし直す**。
- 修正案: GUI で上書きを確認したときだけ、このフラグを付ける。

### ❌ H1 の本命の修正（実際のパスの記録）が効いていない

- `on_output_path` は、出力行の末尾が `.mp3` などで終わる行を拾う作りになっている。しかし `--print after_move:filepath` をコマンドに追加していないため、拾われるのは `[ExtractAudio] Destination: /path/x.mp3` のような行全体である。
- その行から作るパスは常に存在しないので、毎回フォールバック（推測による照合）に回る。つまり実質的に**使われないコード**になっている。
- 一方、照合する側には `yt_dlp.utils.sanitize_filename` による変換が加わった。このため H1 の症状そのものは解消している（再現スクリプトで `True` を確認）。
- 修正案（どちらか）:
  - `--print after_move:filepath` を追加し、該当行だけを解釈する。
  - `on_output_path` の仕組みを削除する。

### ❌ M4(3): audio_only のときに .mp4 を保存済みとみなす問題

- `_episode_output_matches` に `audio_only` 引数を追加したが、呼び出し元（`filesystem.py:212`、`manifest.py:172`）が渡していない。
- 再現結果: `第2回.mp4` だけが存在するとき、`is_episode_downloaded` が **True** を返す（未修正）。

### ⚠️ G8(1): 未保存のテーマが勝手に保存される問題

- `save_search_history` は `ThemeManager.current_theme` と `current_font_size` を保存している。
- ところが、設定画面でテーマを試しに切り替えると、`_apply_current_theme` → `ThemeManager.apply_theme`（`theme_manager.py:50`）を通るため、`ThemeManager.current_theme` もプレビュー中の値に変わる。
- そのため、検索で Enter を押すと**プレビュー中のテーマが保存される**状態のまま。
- 修正案: 保存済みの値（`self.settings["theme"]` / `["font_size_pt"]`）を使う。
- なお G8(2)（文字列と整数の取り違え）は対処済み。

### ⚠️ G9 の副作用

- ダブルクリック時の判定（`download_panel.py:76-80`）は、Double-1 だけでなく `<Return>` のイベントにも適用される（`build.py:550`）。
- Tk のキーイベントは、マウスポインタの座標を持っている。そのため、マウスが ☑ 列の上にある状態で Enter を押すと、ダウンロードが**黙って無視される**。
- 修正案: `getattr(_event, "num", None) == 1`、または `event.type` が ButtonPress であるときだけ判定する。

## 2. 指摘ごとの対応状況

### 非 GUI

| # | 状況 | 確認内容 |
|---|---|---|
| H1 | ⚠️ | 症状は解消（照合側で yt-dlp と同じ変換をするようになった）。実パスを記録する仕組みは効いていない（上記） |
| H2 | ✅ | `EOFError` で `return None` するようになった。テストあり |
| M1 | ✅ | timestamp を JST の `YYYYMMDD` に変換。`_format_episode_date` は 10 桁の数字を日付扱いしない |
| M2 | ✅ | `isinstance(payload, dict)` を確認するようになった |
| M3 | ✅ | `TypeError` / `ValueError` で None を返すようになった。テストあり |
| M4 | ⚠️ | (1) `.part-Frag` の除去 ✅（再現で確認）、(2) `glob.escape` ✅、(3) audio_only ❌ |
| M5 | ✅ | 照合を末尾の完全一致に変更。`第1回` が `第1回 解説` に一致しなくなった（再現で確認） |
| M6 | ✅ | `KeyboardInterrupt` を再送出し、`.part` を掃除してから中断する |
| M7 | ✅ | `TimeoutExpired` と `FileNotFoundError` を処理。タイムアウトは件数 × 3600 秒 |
| M8 | ⚠️ | 一部失敗のときにキャッシュを保存しないようになった。ただし判定がモジュールグローバルのフラグ（`_LAST_FETCH_HAD_FAILURE`）で、並行して取得すると競合する。`_fetch_by_genre_async` の失敗は検知していない。戻り値で失敗数を返す形が望ましい |
| M9 | ✅ | HTTP-date 形式の解釈、上限、最終試行では待たない、の 3 点すべて対応。ただし `except Exception: pass` で例外を握りつぶしている（CLAUDE.md の方針に反する。`(TypeError, ValueError)` に絞るべき） |
| M10 | ✅ | encoding を指定、監視スレッドでキャンセルを確認、失敗時は出力の末尾 20 行をログに出す |
| L2 | ✅ | `stat()` の `OSError` と環境変数の値の不正を処理するようになった |
| L1, L3–L9 | — | 未対応（`scripts/check_arity.py:21` は、存在しない `listing.py` / `downloads.py` のまま） |

### GUI

| # | 状況 | 確認内容 |
|---|---|---|
| G1 | ✅ | 準備処理を `try` の中に移し、`finally` で必ず結果を通知する |
| G2 | ✅ | (a) `start_download` の中で登録するようになった。`cancel_all` は `cancel_events` を基準にする。(b) ポーリングを止める条件に `queue.empty()` を加え、取りこぼしの窓がなくなった |
| G3 | ⚠️ | 世代番号の導入と True/False 両方の反映は ✅。ワーカーからの `root.after` 直呼びは残っていて、例外を suppress しているだけ。検索欄のデバウンスは未対応 |
| G4 | ❌ | 上記のとおり |
| G5 | ⚠️ | `Popen` を外に渡すようになり、`terminate` が効くようになった。`start_new_session` と `killpg` は未対応で、ffmpeg が孤立する可能性は残る |
| G6 | ✅ | 取得中でも確認ダイアログを出して閉じられる。`_set_loading(False)` を `finally` で通す修正はしていない |
| G7 | ✅ | フラグを解除してから通知する順序になった |
| G8 | ⚠️ | (1) ❌ 上記のとおり。(2) ✅ `int` で保存するようになり、`.config/ui_settings.json` も数値になった |
| G9 | ⚠️ | ダブルクリックは対処済み。`<Return>` への副作用あり（上記） |
| G10 | ✅ | toplevel、ポップアップの有無、修飾キーを判定するようになった |
| G11–G14, G16, G17 | — | 未対応 |
| G15 | — | 未対応（mypy の override と `check_untyped_defs` はそのまま。`protocols.py:80` は `current_font_size: str` のままで、実際の値と型が食い違っている） |

### カバレッジ・設定（§0）

| 指摘 | 状況 |
|---|---|
| protocols.py の Protocol スタブ | ✅ omit に追加、`\.\.\.$` を除外対象に追加 |
| pyproject と `.coveragerc` の二重管理 | ✅ pyproject 側を削除 |
| mypy の `python_version` | ✅ 3.13 に変更 |
| GUI 11 ファイルの omit、`except OSError` の除外 | — 未対応 |

## 3. 細かい点

- `listing/operations.py:245-246`: `return` の後に「事前の unlink は行わない」というコメントがあり、到達しない位置に置かれている。if 文の外へ移すべき。
- `runner.py` の監視スレッドと読み取りループの両方が `terminate()` を呼ぶ。実害はないが、読み取りループ側の確認は不要になった。
- `core.py:135-136` に新しく `# pragma: no cover` が 2 行加わった。
- `.config/ui_settings.json` の差分（`"11"` → `11`）は、ローカルの設定ファイルの変更。コミットに含めるかどうか確認すること。

## 4. 推奨する次の対応

1. **G4**: 退避して DL し、失敗したら元に戻す方式にする。`--force-overwrites` は上書きを確認したときだけ付ける（URL モードの退行も同時に直る）。
2. **M4(3)**: `audio_only` を呼び出し元から渡す。
3. **G8(1)**: 保存済みの設定値で検索履歴を保存する。
4. **G9**: 判定をマウスイベントに限定する。
5. **H1**: `--print after_move:filepath` を追加するか、`on_output_path` を削除する。
