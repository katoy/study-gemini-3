# Kindle App to PDF 開発計画

本プロジェクトの品質向上、機能拡張、およびメンテナンス性向上のための詳細な作業計画です。

## 1. プロジェクトの現状分析

現状、macOS 専用の Kindle キャプチャ・PDF 化ツールとして基本機能（キャプチャ、重複検知、PDF 結合、分割）は実装されています。
AppleScript と `screencapture` コマンドに依存しており、UI 操作の自動化とロスレスな PDF 生成を実現しています。

### 改善の余地がある点:
- **堅牢性**: AppleScript の失敗時や、予期しない UI 要素が出現した際のエラーハンドリング。
- **UX**: キャプチャ中の進捗状況（プログレスバーなど）や、設定（待機時間、出力先）の管理。
- **品質管理**: 型定義の徹底、ユニットテストの導入、静的解析の適用。
- **保守性**: 設定ファイル（YAML/JSON）による永続的な設定管理。

## 2. 作業項目 (Task List)

### A. 基盤強化と品質向上
- [ ] **静的解析の導入**: `mypy`, `ruff` (または `flake8`, `black`, `isort`) を導入し、コード品質を担保する。
- [ ] **型ヒントの徹底**: 全関数に型ヒントを付加し、`mypy` でチェックする。
- [ ] **ユニットテストの整備**:
    - [ ] `sanitize_filename` 等のユーティリティ関数のテスト。
    - [ ] AppleScript 実行部をモックし、キャプチャフローのロジックをテスト可能にする。
- [ ] **ドキュメント整備**: 各モジュールの docstring を充実させ、`README.md` に開発者向けの情報を追記する。

### B. 機能拡張と UX 向上
- [ ] **進捗表示の改善**: `tqdm` 等を使用したプログレスバーの導入（ページ数未定の場合はカウンタ表示）。
- [ ] **プレビュー機能**: キャプチャ開始前に、現在の Kindle ウィンドウ位置とキャプチャ範囲を赤枠などで示す（または 1 枚だけ撮って確認させる）機能。
- [ ] **設定ファイルの導入**: CLI 引数だけでなく、`config.yaml` 等で `page-delay` や `direction` を保存できるようにする。
- [ ] **ログの出力改善**: 標準出力とファイル出力を分離し、デバッグ用の詳細ログをファイルに残す。

### C. キャプチャ・PDF 生成の安定化
- [ ] **高度なウィンドウ検知**: Kindle アプリが複数起動している場合（稀ですが）や、名称が異なる場合への対応強化。
- [ ] **UI スキャンの強化**: 評価ダイアログ以外の「おすすめ」ポップアップ等に対する検知パターンの追加。
- [ ] **PDF 生成時のバリデーション**: 生成された PDF が破損していないか、ページ数が画像枚数と一致しているかのチェック。

## 3. 実装の優先順位

1. **Phase 1: 品質向上 (Quality First)**
   - 静的解析ツールの導入、型ヒント、基本的なユニットテスト。
2. **Phase 2: UX 改善 (UX Boost)**
   - 進捗表示、プレビュー機能、設定ファイルのサポート。
3. **Phase 3: 安定性・機能拡張 (Stability & Features)**
   - ログの高度化、UI 検知の強化、PDF バリデーション。

## 5. Windows 対応に向けた詳細分析

現状 macOS に強く依存しているため、Windows 対応には主要コンポーネントの再実装が必要です。

### A. 主要な技術的課題と代替案
- **UI 操作 (AppleScript の代替)**:
    - **課題**: Windows には AppleScript のような標準的な OS 全体の自動化スクリプトがありません。
    - **案 1**: `PyAutoGUI` を使用したキー送信 (`press('space')` 等)。シンプルですが、ウィンドウが最前面である保証が必要です。
    - **案 2**: `pywin32` (Win32 API) を使用。特定のウィンドウハンドルに対して直接メッセージを送る (`SendMessage`, `PostMessage`) ことで、より確実に操作可能です。
- **ウィンドウ検知・領域取得**:
    - **課題**: `osascript` でウィンドウ境界を取得している箇所を Win32 API に置き換える必要があります。
    - **ツール**: `pygetwindow` または `pywin32` の `GetWindowRect` 等。
- **スクリーンキャプチャ**:
    - **課題**: `screencapture` コマンドがありません。
    - **ツール**: `Pillow` (PIL) の `ImageGrab`、または `pywin32` を使用したビットマップ取得。高 DPI (Retina 相当) 環境でのスケーリング対応が重要になります。

### B. 実装戦略 (クロスプラットフォーム化)
1. **抽象化レイヤーの導入**:
   - `kindle_capture.py` をリファクタリングし、OS ごとに異なる実装を呼び出すインターフェース（Abstract Base Class 等）を定義します。
   - `OSProvider` クラスを作成し、`activate_app()`, `get_window_bounds()`, `capture_region()`, `send_key()` 等のメソッドを定義。
2. **依存関係の分離**:
   - `pyproject.toml` や `requirements.txt` で、OS ごとの依存関係 (`pywin32` 等) を条件付きで管理します。

### C. Windows 特有の留意事項
- **Kindle for PC の挙動**: macOS 版と異なり、メニューバーの消去（Escape キー）の挙動や、評価ダイアログの UI 構造（クラス名やアクセシビリティ要素）が異なるため、Windows 版の実機での詳細なプロファイリングが必要です。
- **権限**: macOS の「アクセシビリティ」に相当する厳しい制限は少ないですが、管理者権限が必要になるケースや、ウイルス対策ソフトによるブロックへの配慮が必要です。

## 7. 具体的なコード変更案

抽象化レイヤーを導入し、OS 固有の実装を分離する際のデザイン案です。

### A. `kindle_capture.py` の構造変更

```python
from abc import ABC, abstractmethod

class BaseCaptureProvider(ABC):
    """OS 共通のキャプチャプロバイダーインターフェース"""

    @abstractmethod
    def activate_kindle(self) -> str:
        """アプリを前面に出し、プロセス名を返す"""
        pass

    @abstractmethod
    def get_window_bounds(self, process_name: str) -> tuple[int, int, int, int]:
        """ウィンドウの (x, y, w, h) を取得"""
        pass

    @abstractmethod
    def capture_screen(self, process_name: str, output_path: str):
        """指定領域をキャプチャして保存"""
        pass

    @abstractmethod
    def send_key(self, process_name: str, key_type: str):
        """キー入力を送信 (next, back, dismiss)"""
        pass

    @abstractmethod
    def is_dialog_active(self, process_name: str, book_title: str) -> bool:
        """ダイアログや終了画面を検知"""
        pass

class MacOSCaptureProvider(BaseCaptureProvider):
    """現行の AppleScript + screencapture 実装をここに移動"""
    # ... (既存のロジックを移植)

class WindowsCaptureProvider(BaseCaptureProvider):
    """Windows 用実装 (pywin32, Pillow 等を使用)"""
    def activate_kindle(self) -> str:
        # win32gui.SetForegroundWindow 等
        pass
    # ...
```

### B. ファクトリ関数の導入

実行環境の OS を自動判別して適切なプロバイダーを生成します。

```python
import sys

def get_provider() -> BaseCaptureProvider:
    if sys.platform == "darwin":
        return MacOSCaptureProvider()
    elif sys.platform == "win32":
        return WindowsCaptureProvider()
    else:
        raise NotImplementedError(f"Unsupported OS: {sys.platform}")
```

### C. `capture_kindle_pages` のリファクタリング

具体的な実装をプロバイダーに委譲することで、メインロジックをシンプルに保ちます。

```python
def capture_kindle_pages(output_dir: str, ...):
    provider = get_provider()
    process_name = provider.activate_kindle()

    while True:
        if provider.is_dialog_active(process_name, title):
            # ...
        provider.capture_screen(process_name, path)
        provider.send_key(process_name, "next")
```

## 8. 注意事項
- macOS のアクセシビリティ許可、画面収録許可が必要である点は不変。
- OS アップデート等による AppleScript 仕様変更への追随が必要になる可能性がある。
- Windows 対応は開発工数が大幅に増加するため、まずは macOS 版の抽象化（リファクタリング）から着手することを推奨。

