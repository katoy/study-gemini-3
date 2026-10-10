# コードレビュー報告書（2026-10-11）

対象: `kindle_app_to_pdf/` 全体（`main.py` / `kindle_capture.py` / `pdf_maker.py` / `split_pdf.py` / `output/pdf-chapter-splitter/split_pdf.py` / セットアップ・実行スクリプト / `pyproject.toml` 等）

前回レポート（`docs/code_review_report.md`）の指摘 1〜4 はコミット `9defa34` / `fda6051` で対応済みです。本レポートは**現時点のコード**に対する新たなレビューです。

## 0. サマリー

| 区分 | 結果 |
|---|---|
| `ruff check .` | ✅ 指摘なし |
| `ruff format --check .` | ⚠️ `output/pdf-chapter-splitter/split_pdf.py` が未整形（タブ混在） |
| `mypy`（strict、主要 4 ファイル） | ✅ 指摘なし（ただし `Any` / `type: ignore` 多用で実質的な型保護は弱い） |
| テスト | ❌ `tests/` が存在せず、テストは 0 件 |

| 重要度 | 件数 | 主な内容 |
|---|---|---|
| 🔴 High | 4 | 長いタイトルで Windows のキャプチャが即終了／DPI 補正が逆効果／正常終了時に最終ページが削除される／テストなし |
| 🟠 Medium | 8 | Mac でタイトル取得に失敗するとキャプチャが即終了／Mac の部分結果喪失／無限ループ防止なし／PDF 名の表示ずれ 等 |
| 🟡 Low | 10 | 設定ファイル間の不整合、重複コード、ドキュメントの誤記 等 |

---

## 1. 🔴 High

### H-1. Windows: 書名が長いとキャプチャ開始直後に「ダイアログ検知」で終了する
- **場所**: `kindle_capture.py:568-575`, `kindle_capture.py:590-596`
- **内容**: `book_title` は「タイトルの ` - ` 以降」を `sanitize_filename()` で **80 文字に切り詰めた値**です。一方、`_is_dialog_active()` は `sanitize_filename(current_title)` を使います。これは「`Kindle - ` 接頭辞を含むタイトル全体」を 80 文字に切り詰めた値です。書名が約 71 文字を超えると、前者が後者の部分文字列にならず、`not in` が常に True になります。
- **再現（検証済み）**:
  ```python
  t = "Kindle - " + "あ" * 75
  bt = sanitize_filename(t.split(" - ", 1)[1])
  bt in sanitize_filename(t)   # => False → 毎回「タイトル変化」と判定
  ```
- **影響**: 1 枚目の撮影直後にループを抜け、0 ページで終わります（`main.py` の「キャプチャされたページがありません」エラーになります）。サブタイトル付きの日本語技術書などで発生しやすい問題です。
- **修正案**: 判定用の生タイトル（`window.title`）をキャプチャ開始時に保持します。比較はその生タイトル同士（`raw_title in window.title`、またはタイトルが変化したかどうか）で行い、ディレクトリ名用の `sanitize` 済みタイトルとは分けます。Mac 版は既に `raw_book_title` を判定に使っているので、同じ方式に揃えられます。

### H-2. Windows: フォーカス用クリック座標の DPI 補正が逆効果になっている
- **場所**: `kindle_capture.py:555-560`
- **内容**: 現行コードは「pyautogui は論理ピクセル座標を使う」という前提で `window.left / dpi_scale` に変換しています。しかし pyautogui の Windows バックエンドは、import 時に `SetProcessDPIAware()` を呼んでプロセスを DPI-aware にします（`pyautogui/_pyautogui_win.py` 冒頭）。本モジュール自身も `SetProcessDpiAwareness(2)` を呼んでいます。そのため `window.left`（GetWindowRect の値）、`ImageGrab`、`pyautogui.click`（SetCursorPos）はすべて**物理ピクセル**で一致しており、割り算は不要です。
- **影響**: 拡大率 125% / 150% の環境では、Kindle ウィンドウより左上の点（別アプリや デスクトップ）をクリックしてしまいます。その直後の `esc` も別アプリに送られ、Kindle がフォーカスを失ったままになり、ページ送りが効きません。前回レビューの指摘 1 にもとづく修正が、逆にバグを生んだ可能性が高いです。
- **修正案**: `/ dpi_scale` を外して `window.left + 150`, `window.top + 15` をそのまま渡します。その結果 `_get_dpi_scale` / `_get_window_dpi_scale` が不要になれば削除します。**要実機確認**（100% / 150% の 2 環境）。

### H-3. 終端を検出すると、本物の最終ページまで削除される
- **場所**: `kindle_capture.py:146-158`（Mac）, `kindle_capture.py:451-463`（Windows）
- **内容**: 同じ画像が `MAX_SAME_PAGES` 回続くと、`screenshots.pop()` で最後に保存したページを無条件に削除します。コメントは「重複の起点となったダイアログ等」を削除する想定です。しかし、通常の終わり方（最終ページでキーを押しても画面が変わらない）では、最後に保存したのは**本物の最終ページ**です。ダイアログは撮影直後のチェック（131-137 行）で別途検出・破棄されるので、ここで削るのは過剰です。
- **影響**: ダイアログが出ない書籍・環境では、生成した PDF から毎回最終ページ（奥付など）が欠けます。
- **修正案**: 無条件の `pop()` をやめます。消すのは「最後のページが既知のダイアログ判定に該当する場合」に限るか、`--trim-last` のような明示オプションにします。少なくとも削除したファイル名をログに出し、ユーザーが気付けるようにします。

### H-4. 自動テストが 1 件もない
- **場所**: リポジトリ全体（`pyproject.toml` の dev 依存に `pytest` はある）
- **内容**: GUI 操作の部分は別にしても、純粋関数やフロー制御はテストできます。H-1 や H-3 のような「判定ロジックのバグ」はユニットテストで検出できる種類のものです。
- **最低限のテスト候補**:
  - `sanitize_filename`（禁止文字、80 文字切り詰め、空文字 → `kindle_book`）
  - `_escape_applescript_string`
  - キャプチャループ: `_capture_window_region` / `_send_next_page` / `_is_dialog_active` をフェイクに差し替え、終端検出・ページ数・削除ファイルを検証する（ループの共通化（L-4）でテストしやすくなる）
  - `main._generate_pdf` の同名回避、`_delete_screenshots` の安全削除、`_prepare_screenshots` の `--images-dir` 分岐
  - `split_pdf.split_pdf`（小さな PDF を生成して分割数・ページ範囲を検証）

---

## 2. 🟠 Medium

### M-1. Mac: タイトル取得に失敗すると、キャプチャ開始直後に終了する
- **場所**: `kindle_capture.py:223-227`, `kindle_capture.py:334-336`
- **内容**: `_get_window_title` が失敗すると `"kindle_book"` を返します。その後の `_is_dialog_active` は「前面ウィンドウのタイトルが `kindle_book` を含まない」ので、常に `title_mismatch` と判定します。その結果、撮影前に Esc を送り、撮影後に画像を破棄してループを抜けます。Windows 版にある `book_title != "kindle_book"` のガードが Mac 版にはありません。
- **修正案**: タイトルを取得できなかったときはタイトル比較を省きます。

### M-2. Mac: ダイアログ判定のキーワードが部分一致で、誤検知しやすい
- **場所**: `kindle_capture.py:338-353`
- **内容**: 前面ウィンドウの全 UI 要素の名前を連結した文字列に対して、「完了」「閉じる」「Review」「Done」「Close」などを `contains` で照合しています。ツールバーのボタン名や、本文・タイトルを含む要素名にこれらの語が入っていると、通常ページでも終端と判定して停止します。
- **修正案**: 判定対象を `AXButton` などのロールに限定し、名前は部分一致ではなく完全一致にします。または、ダイアログのロール判定（356-362 行）だけで足りるかを実機で確認し、キーワード判定を削ります。

### M-3. Mac: 途中でエラーが起きると、それまでのキャプチャ結果をすべて失う
- **場所**: `kindle_capture.py:128`, `kindle_capture.py:169`, `kindle_capture.py:280`
- **内容**: `_capture_window_region`（`check=True`）と `_send_next_page`（`RuntimeError`）の例外が `capture_pages` の外へ送出されます。そのため `screenshots` が返らず、PDF は生成されません。Windows 版は `break` で部分結果を返すので、OS 間で挙動が異なります。
- **影響**: 長い本で 1 回だけ AppleScript が一時的に失敗すると、それまでの全ページが PDF 化されません（PNG は残るため、`--images-dir` で復旧はできます）。
- **修正案**: Windows 版と同じく、ログを出して `break` し、部分結果を返します。あわせて `main.py` 側で「途中終了」の警告を出します。

### M-4. 無限ループを防ぐ仕組みがない
- **場所**: 両 OS の `while True`（`kindle_capture.py:118`, `412`）
- **内容**: 終端は「完全に同一の MD5」が 3 回続いた場合のみ検出します。読み込みスピナーなど、撮影ごとに 1 ピクセルでも変わる要素があると、永遠に終わりません。
- **修正案**: `--max-pages`（例: デフォルト 2000）を追加し、上限に達したら警告して終了します。

### M-5. `--images-dir` 指定時、完了表示の PDF パスが実際のファイルと異なる
- **場所**: `main.py:67-71`
- **内容**: `_generate_pdf()` は同名ファイルがあると `_2.pdf` などに名前を変えて保存し、そのパスを返します。しかし戻り値を捨て、`book_title + ".pdf"` を再計算して表示しています。2 回目以降の再生成では、**既存の古い PDF のパス**を表示してしまいます。
- **修正案**: `pdf_path = _generate_pdf(...)` の戻り値を使います（ここで未使用の変数 `shot_dir` も `_` にします）。

### M-6. Windows: キャプチャ領域を開始時に 1 回しか計算せず、マルチモニタにも未対応
- **場所**: `kindle_capture.py:391-392`, `kindle_capture.py:603-606`
- **内容**: `bbox` は開始時に固定されるので、キャプチャ中にウィンドウが移動・リサイズされると別の領域を撮影します。また、`ImageGrab.grab()` は `all_screens=True` を付けないとプライマリモニタしか撮影しません。ウィンドウが負の座標にあるサブモニタにある場合、真っ黒な画像または失敗になります。
- **修正案**: 毎ページ（または `_focus_window` の後）に領域を取り直し、`ImageGrab.grab(bbox=..., all_screens=True)` を使います。

### M-7. Windows: タイトルに "Kindle" を含む別のウィンドウを掴む可能性がある
- **場所**: `kindle_capture.py:512-518`, `kindle_capture.py:570-572`
- **内容**: `gw.getWindowsWithTitle("Kindle")` は大文字小文字を区別しない部分一致です。そのため、ブラウザの Amazon Kindle ページや、パスに `kindle_app_to_pdf` を含むエクスプローラー・ターミナルも候補になり、`[0]` がどれになるかは不定です。さらに `_get_book_title()` は**別途検索し直す**ので、フォーカスしたウィンドウとタイトルを取ったウィンドウが一致する保証がありません。
- **修正案**: 候補を「タイトルが `Kindle` で始まる」「プロセス名が `Kindle.exe`」などで絞り込みます。書名は `_find_and_focus_kindle` で得た `window.title` から抽出します。

### M-8. `output/pdf-chapter-splitter/split_pdf.py` が出力先を無条件に `rmtree` する
- **場所**: `output/pdf-chapter-splitter/split_pdf.py:126-129`
- **内容**: 前回レビューの指摘 4 で `main.py` から除いたものと同じ危険なパターンが残っています。`output_directory` を書き換え間違えると、既存データを確認なしで削除します。
- **修正案**: 対象を `*.pdf` に限定して削除するか、既存ディレクトリが空でなければエラーにします。

---

## 3. 🟡 Low

| # | 場所 | 指摘 | 提案 |
|---|---|---|---|
| L-1 | `.python-version`(3.12) / `.tool-versions`(3.14.2) / `pyproject.toml`(>=3.11) | Python のバージョン指定が 3 か所で食い違う | 1 つに揃える（例: 3.12） |
| L-2 | `requirements.txt` | `pyautogui` / `pygetwindow` に環境マーカーがなく、Mac でも入る（`pyproject.toml` には `sys_platform == 'win32'` がある） | `; sys_platform == "win32"` を付ける。または `uv sync` に一本化して `requirements.txt` を廃止 |
| L-3 | `setup.sh:58` | 「デフォルト: space」と表示されるが、実際のデフォルトは `right` | 表記を修正する |
| L-4 | `kindle_capture.py:90-172` と `383-482` | キャプチャループ（ディレクトリ採番、ハッシュ履歴、終端処理）が約 60 行重複している。H-3 のような修正を 2 か所に入れる必要がある | 共通ループを関数化し、OS 依存部分（撮影・ページ送り・ダイアログ判定）だけを差し替える。テスト容易性も上がる |
| L-5 | `pdf_maker.py:37-38` | `img2pdf.convert()` が PDF 全体をメモリ上の bytes として作る。Retina の数百ページで数 GB に達する可能性がある。失敗すると 0 バイトの PDF が残る | `img2pdf.convert(paths, outputstream=f)` で逐次書き出す。失敗時は出力ファイルを削除する |
| L-6 | `kindle_capture.py:628-634` | Windows 以外はすべて Mac 実装になる。Linux では `osascript` が見つからず `FileNotFoundError` になる（`run.sh` は "macOS/Linux" と表記） | `Darwin` 以外では「未対応 OS」と明示的に例外を出す |
| L-7 | `kindle_capture.py:197-211` | `name contains "Kindle"` なので Kindle Previewer / Kindle Create を拾う可能性がある | 完全一致（`"Kindle"`）を優先する |
| L-8 | `kindle_capture.py:113`, `406` | `MAX_HISTORY` がメソッド内のローカル「定数」として 2 回定義されている | モジュール定数にする |
| L-9 | `kindle_capture.py:389` | docstring の誤記 "Windows 用 of Kindle" | 「Windows 用の」に直す |
| L-10 | `output/pdf-chapter-splitter/split_pdf.py` | 型ヒントがない、タブが混在（ruff format NG）、PyPDF2 へのフォールバックが不要、入力パスがハードコードされている。gitignore 対象の `output/` 配下に置かれ、ルートの `split_pdf.py` と役割が重複している | ルートの `split_pdf.py` に「章範囲指定」モードとして統合するか、`tools/` などに移して CLI 引数化する |

### 補足（問題ではないが記録しておく点）
- Mac 版は 1 ページごとに `osascript` を約 5 回起動しています（撮影前後のダイアログ判定、最前面化、領域取得、キー送信）。ページ送りの待ち時間（1.5 秒）に比べれば小さいものの、領域取得はループの外に出すなどで減らせます。
- `_calculate_md5` は改ざん検知ではなく同一性判定の用途なので MD5 で問題ありません（`hashlib.md5(usedforsecurity=False)` と書くと意図が明確になります）。
- `run.bat` は `Activate.bat` で仮想環境を有効化した後に `uv run` を呼んでいるので、有効化は冗長です。
- `main.py` の `input()` で EOF（パイプ入力の終端など）になると、`EOFError` がトレースバック付きの critical ログになります。

---

## 4. 良い点
- OS ごとの差分を `KindleCapturer` Protocol と 2 つの実装クラスに分けており、エントリポイント（`capture_kindle_pages`）が簡潔です。
- AppleScript に文字列を埋め込む箇所はすべて `_escape_applescript_string` を通しており、インジェクション対策が一貫しています。
- `img2pdf` で画像を再エンコードせずに PDF 化しており、画質劣化がありません。
- `_delete_screenshots` は `page_*.png` だけを削除し、空になったディレクトリだけを削除する安全な実装になっています。
- 出力ディレクトリ名と PDF 名の衝突を連番で回避しており、既存の成果物を上書きしません。
- `ruff` / `mypy --strict` を通過する状態が保たれています。

---

## 5. 推奨対応順

1. **H-1, H-2, M-1**: キャプチャ自体が動かないケースの修正（小さな差分で効果が大きい）
2. **H-3, M-5**: 出力結果の欠損・誤表示の修正
3. **L-4 → H-4**: キャプチャループを共通化し、フェイクを使ったループのテストを追加する
4. **M-3, M-4, M-6, M-7**: 堅牢性の向上
5. **M-8, L-1〜L-3, L-10**: 周辺スクリプト・設定の整理
