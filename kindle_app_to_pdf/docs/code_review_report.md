# コードおよびREADMEのレビュー報告書

本ツール（`kindle_app_to_pdf`）のコードと `README.md` をレビューしました。
全体的に、OSごとの動作の違い（Macの AppleScript と Windows の Win32API/PyAutoGUI）が適切に抽象化されており、`img2pdf` を用いたロスレスな PDF 結合処理など、非常に実用的かつ綺麗に設計されています。

一方で、**Windows の高 DPI 環境での挙動の不安定さ**や**一部オプション指定時の無限ループバグ**、**ファイル削除処理の安全性**など、実用性と堅牢性をさらに高めるための改善点がいくつか見つかりました。

以下に詳細な指摘事項と、具体的な修正コード案を提案します。

---

## 1. 主要な指摘事項と改善提案

### 指摘 1. 【バグ】Windows高DPI環境でのフォーカスクリック位置ズレ
* **現状**: 
  `kindle_capture.py` の 43行目付近で `SetProcessDpiAwareness(2)` を呼び出してプロセスを DPI-aware に設定しています。これにより、`GetWindowRect` などの Win32 API は「物理ピクセル座標」を返します。
  しかし、フォーカスを取得するために呼び出している `pyautogui.click()` は、OSの「論理ピクセル座標（スケーリング適用前）」を使用します。
* **問題点**: 
  Windows のディスプレイ設定で「テキスト、アプリ、その他の項目のサイズを変更する」が **100% 以外（例: 125% や 150%）** に設定されている場合、`window.left` などの物理座標をそのまま `pyautogui.click()` に渡すと、本来より右下をクリックしてしまい、Kindle ウィンドウのフォーカス取得に失敗したり、別のアプリを誤ってクリックしたりします。
* **改善案**: 
  取得した `dpi_scale` を用いて、`pyautogui` に渡す座標を論理ピクセルに変換（`座標 / dpi_scale`）します。また、重複しているフォーカス設定処理を1つの共通メソッドにまとめます。

### 指摘 2. 【バグ】`--images-dir` 指定時の不要な入力待ちと無限ループ
* **現状**: 
  `main.py` の `run()` 関数は `while True` ループ内で動作し、毎回「Kindle アプリで本を開き、最初のページを表示してください」とユーザーに Enter キーの入力を求めます。
* **問題点**: 
  1. `--images-dir` を指定して既存の画像から PDF を再生成したいだけのユーザーに対しても、この入力待ちが発生するため不要な操作を強いることになります。
  2. PDF 生成中にエラーが発生して `continue` された場合、`args.images_dir` が保持されたままのため、ユーザーが `q` で終了するまで同じ既存フォルダの処理を繰り返す無限ループになります。
* **改善案**: 
  `args.images_dir` が指定されている場合は、インタラクティブなループに入らず、1回だけ処理を実行して即座に終了するように制御フローを分岐させます。

### 指摘 3. 【機能向上】Windows版における終端検知ロジックの強化
* **現状**: 
  Mac版（`MacKindleCapturer`）では、過去5世代のハッシュ履歴（`hash_history`）を保持して重複検知を行っています。対して Windows版（`WindowsKindleCapturer`）は、直前の1ページ（`last_hash`）のみと比較しています。
* **問題点**: 
  Windows 環境でページめくりのアニメーション遅延やページのローディングにより、「ページA -> ページB -> ページA」のような微小な揺れや、ページ送りの失敗で1つ前に戻る事象が発生した場合、直前1枚との比較だけでは重複を検知できず、無限ループに陥る可能性があります。
* **改善案**: 
  Windows版でも Mac版と同様に `hash_history` リスト（過去5世代）を用いた重複検知を導入し、終端判定の堅牢性を高めます。また、終了時に余分に撮影された最後の重複元画像（ダイアログ等）を削除する処理も Windows版に移植します。

### 指摘 4. 【安全性】`shutil.rmtree` による画像フォルダ削除の危険性
* **現状**: 
  `main.py` の `_delete_screenshots` では、`shutil.rmtree(shot_dir, ignore_errors=True)` を使用して一時フォルダごと削除しています。
* **問題点**: 
  万が一、`shot_dir` が予期しない重要なディレクトリ（カレントディレクトリやデスクトップ全体など）を指してしまった場合、意図しないデータ消失が発生する危険性があります（データ保護の観点）。
* **改善案**: 
  フォルダ丸ごとの削除ではなく、本プログラムが生成した画像（`page_*.png`）のみを個別に `unlink()` で削除し、フォルダが空になった場合のみフォルダ自体を削除するように安全対策を施します。

---

## 2. 具体的な修正コード案

### A. `main.py` の修正案
`main.py` の `run` 関数および `_delete_screenshots` 関数を以下のように書き換えることを推奨します。

```python
def run(args: argparse.Namespace) -> None:
    """メイン実行フロー。"""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 【改善】既存の画像ディレクトリから生成する場合はループさせず、1回のみ実行して終了する
    if args.images_dir:
        try:
            book_title, screenshots, shot_dir = _prepare_screenshots(args, output_dir)
            _generate_pdf(output_dir, book_title, screenshots)
            # 既存画像指定時は screenshots の削除を行わない（args.screenshots にかかわらず保持）
            pdf_path = output_dir / (sanitize_filename(book_title) + '.pdf')
            _print_summary(pdf_path)
        except Exception as e:
            logger.error(f"PDF 再生成中にエラーが発生しました: {e}")
            sys.exit(1)
        return

    # 通常のキャプチャ実行ループ
    while True:
        print("\n" + "!" * 60)
        print("Kindle アプリで処理したい本を開き、最初のページを表示してください。")
        print("準備ができたら Enter キーを押してください。")
        print("（終了する場合は 'q' を入力して Enter）")
        print("!" * 60 + "\n")

        user_input = input(">> ").strip().lower()
        if user_input == 'q':
            break

        try:
            # Step 1: キャプチャ
            book_title, screenshots, shot_dir = _prepare_screenshots(args, output_dir)

            try:
                # Step 2: PDF 生成
                pdf_path = _generate_pdf(output_dir, book_title, screenshots)

                # Step 3: スクリーンショット削除（安全な削除処理へ）
                if args.screenshots == 'delete' and shot_dir is not None:
                    _delete_screenshots(shot_dir)

                _print_summary(pdf_path)
            except Exception as e:
                logger.error(f"PDF 生成中にエラーが発生しました: {e}")
                if shot_dir:
                    logger.info(f"キャプチャ済みの画像はここに残されています: {shot_dir}")
                continue

            print("\nNext book?")
        except Exception as e:
            logger.error(f"Error: {e}")
            print("Please fix and retry, or enter 'q' to quit.")


def _delete_screenshots(shot_dir: Path) -> None:
    """【改善】スクリーンショットフォルダ内の対象PNGのみを安全に削除します。"""
    logger.info(f"スクリーンショット一時ファイルを削除中: {shot_dir}")
    
    # page_*.png パターンのファイルのみを個別に削除
    png_files = list(shot_dir.glob('page_*.png'))
    for file_path in png_files:
        try:
            file_path.unlink()
        except Exception as e:
            logger.warning(f"ファイルの削除に失敗しました ({file_path.name}): {e}")

    # ディレクトリが空になった場合のみディレクトリ自体を削除
    try:
        if shot_dir.exists() and not any(shot_dir.iterdir()):
            shot_dir.rmdir()
            logger.info("      一時ディレクトリを削除しました")
        else:
            logger.info("      ファイルが残っているため、一時ディレクトリは保持されました")
    except Exception as e:
        logger.warning(f"ディレクトリの削除に失敗しました ({shot_dir}): {e}")
```

### B. `kindle_capture.py` の修正案
DPI座標ズレの修正、フォーカス処理の共通化、および `hash_history` の Windows への移植を行います。

```python
class WindowsKindleCapturer:
    """Windows 用の Kindle キャプチャ実装。"""

    def capture_pages(
        self,
        output_dir: str,
        page_delay: float = 1.5,
        direction: str = 'right',
    ) -> tuple[str, list[str]]:
        """Windows 用の Kindle ページキャプチャ処理。"""
        # Kindle ウィンドウを検出してフォーカスを当てる
        x, y, width, height, window = self._find_and_focus_kindle()
        bbox = (x, y, x + width, y + height)

        book_title = self._get_book_title()
        logger.info(f"書籍タイトル: {book_title}")

        book_dir = Path(output_dir) / book_title
        counter = 2
        while book_dir.exists():
            book_dir = Path(output_dir) / f"{book_title}_{counter}"
            counter += 1
        book_dir.mkdir(parents=True, exist_ok=True)

        screenshots: list[str] = []
        hash_history: list[str] = []  # 【改善】履歴管理を導入
        MAX_HISTORY = 5
        same_count = 0

        logger.info(f"キャプチャ開始 (方向: {direction})...")
        print("Windows Kindle をキャプチャ中です...")

        while True:
            shot_path = book_dir / f"page_{len(screenshots) + 1:04d}.png"

            try:
                self._capture_window_region(str(shot_path), bbox)
            except Exception as e:
                logger.error(f"キャプチャエラー: {e}")
                break

            cur_hash = _calculate_md5(shot_path)

            # 【改善】Mac版と同様の複数世代ハッシュ履歴チェック
            if cur_hash in hash_history:
                same_count += 1
                logger.debug(f"重複検出: {same_count}/{MAX_SAME_PAGES}")
                if shot_path.exists():
                    shot_path.unlink()
                if same_count >= MAX_SAME_PAGES:
                    print(f"\n終端を検出しました（画像重複による停滞）。合計 {len(screenshots)} ページ")
                    # 末尾の重複元画像（ダイアログや最終ページ）を除外
                    if screenshots:
                        last_path = screenshots.pop()
                        if Path(last_path).exists():
                            Path(last_path).unlink()
                        print(f"末尾の重複元画像を除外しました。最終合計: {len(screenshots)} ページ")
                    break
            else:
                same_count = 0
                screenshots.append(str(shot_path))
                hash_history.append(cur_hash)
                if len(hash_history) > MAX_HISTORY:
                    hash_history.pop(0)

                print(f"キャプチャ中: {len(screenshots)} ページ目...")

            # 次のページへ
            try:
                self._send_next_page(window, direction=direction)
            except Exception as e:
                logger.warning(f"ページ送り エラー: {e}")
                break

            time.sleep(page_delay)

        return book_title, screenshots

    def _get_dpi_scale(self) -> float:
        """Windows の DPI スケーリング係数を取得します。"""
        try:
            registry_path = r"Control Panel\Desktop"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path) as key:
                dpi_value, _ = winreg.QueryValueEx(key, "LogPixels")
                return float(dpi_value / 96.0)
        except Exception:
            try:
                hdc = ctypes.windll.user32.GetDC(0)
                dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
                ctypes.windll.user32.ReleaseDC(0, hdc)
                return float(dpi / 96.0)
            except Exception:
                return 1.0

    def _find_and_focus_kindle(self) -> tuple[int, int, int, int, Any]:
        """【改善】Kindle ウィンドウを検出し、DPIを考慮して確実にフォーカスを設定します。"""
        kindle_windows = gw.getWindowsWithTitle("Kindle")
        if not kindle_windows:
            raise RuntimeError("Kindle ウィンドウが見つかりません。Kindle アプリで本を表示した状態で実行してください。")

        window = kindle_windows[0]
        logger.info(f"Kindle ウィンドウを検出: {window.title}")

        self._focus_window(window)

        hwnd = window._hWnd
        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        client_rect = wintypes.RECT()
        ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(client_rect))

        pt = wintypes.POINT(0, 0)
        ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))

        x, y = pt.x, pt.y
        width = client_rect.right - client_rect.left
        height = client_rect.bottom - client_rect.top

        return x, y, width, height, window

    def _focus_window(self, window: Any) -> None:
        """【共通化】ウィンドウをアクティブにし、DPIスケーリングを考慮してクリックフォーカスを合わせます。"""
        try:
            window.activate()
        except Exception as e:
            logger.warning(f"Kindle ウィンドウの有効化に失敗しました (通常起動試行): {e}")
            try:
                window.restore()
                window.activate()
            except Exception as e2:
                logger.warning(f"ウィンドウの復元/有効化に失敗しました: {e2}")

        try:
            import pyautogui as py  # type: ignore
            time.sleep(0.2)
            
            # 【改善】pyautogui に渡す座標を DPI スケールで補正（物理ピクセル -> 論理ピクセル）
            dpi_scale = self._get_dpi_scale()
            click_x = int((window.left + 150) / dpi_scale)
            click_y = int((window.top + 15) / dpi_scale)
            
            py.click(click_x, click_y)
            time.sleep(0.1)
            py.press('esc')  # 本文へキーボードフォーカスを戻す
            logger.debug(f"フォーカスクリック完了: ({click_x}, {click_y})")
        except Exception as e:
            logger.warning(f"ウィンドウクリックによるアクティブ化に失敗しました: {e}")
        time.sleep(0.3)

    def _get_book_title(self) -> str:
        """Windows で Kindle ウィンドウのタイトルから本のタイトルを抽出します。"""
        kindle_windows = gw.getWindowsWithTitle("Kindle")
        if kindle_windows:
            title = kindle_windows[0].title
            if " - " in title:
                return sanitize_filename(title.split(" - ", 1)[1])
        return "kindle_book"

    def _capture_window_region(self, output_path: str, bbox: tuple[int, int, int, int]) -> None:
        """Windows で Kindle ウィンドウの領域をスクリーンショット撮影します。"""
        screenshot = ImageGrab.grab(bbox=bbox)
        screenshot.convert("RGB").save(output_path, "PNG")

    def _send_next_page(self, window: Any, direction: str = 'right') -> None:
        """Windows で Kindle ウィンドウにページめくりキーを送信します。"""
        import pyautogui as py  # type: ignore
        if not window.isActive:
            self._focus_window(window)

        key = 'left' if direction == 'left' else 'space' if direction == 'space' else 'right'
        py.press(key)
```

---

## 3. README.md の改善点

現在記載されている手順は非常に丁寧で、特に `uv` ツールによるセットアップ手順が分かりやすく書かれています。さらに実用性を高めるために、以下の点を README に補強することをおすすめします。

1. **高 DPI 環境でのトラブルシューティングの追記**:
   現行の README には「スケール 100% を推奨」としかありませんが、DPIスケーリングによる座標のズレで誤作動する場合の対処法として、以下のように具体例を記載すると親切です。
   * 例: 「Windows の設定で画面スケールが 150% などになっている場合、クリック位置がずれてフォーカスがうまく当たりません。上記修正を行ったコードを使用するか、Windows のディスプレイ設定で一時的にスケーリングを 100% に変更してください。」
2. **依存パッケージのバージョン指定**:
   `pyproject.toml` や `requirements.txt` で、各ライブラリのバージョンが固定されていません。将来のライブラリのアップデートによる破壊的変更を防ぐため、以下のようなバージョン範囲の指定を検討してください。
   * `img2pdf>=0.5.0`
   * `pypdf>=4.0.0`
   * `pyautogui>=0.9.50`
   * `pygetwindow>=0.0.9` (Windows用)
   * `pillow>=10.0.0`
3. **必要なパーミッションエラー発生時のメッセージ例の追記**:
   macOS でアクセシビリティ権限が不足している場合に発生するエラー（`osascript` 経由の `Application is not allowed to send keystrokes` など）を記載しておくと、ユーザーが対処しやすくなります。
