# Kindle to PDF Tools

このリポジトリには、Kindle の書籍を高品質な PDF に変換するための 2 つのツールが含まれています。どちらも macOS の「テキスト認識表示 (Live Text)」に最適化された、画像ベースの PDF を生成します。

## 🛠 ツール一覧

用途に合わせて以下のいずれかを選択してください。

### 1. [Kindle App to PDF](./kindle_app_to_pdf/) (推奨)
**Mac 版 Kindle デスクトップアプリ**を使用してキャプチャを行うツールです。
- **特徴**: アプリのネイティブな動作を利用するため、ブラウザ版より安定して高画質なキャプチャが可能です。
- **仕組み**: `osascript` (AppleScript) でアプリを操作し、`screencapture` で画面を保存します。
- **主な機能**: 自動ページ送り、終端判定、PDF 分割機能。

### 2. [Kindle to PDF](./kindle_to_pdf/)
**Kindle Cloud Reader (ブラウザ)** を使用してキャプチャを行うツールです。
- **特徴**: アプリをインストールすることなく、ブラウザ上で動作します。
- **仕組み**: `Playwright` を使用してブラウザを自動操作します。
- **主な機能**: 自動 Chrome 起動、リモートデバッグ接続、レンダリング安定待機。

---

## 🚀 共通の特長

- **無劣化・最高画質**: `img2pdf` を使用し、キャプチャした PNG 画像を再エンコードなしで PDF に結合します。
- **macOS Live Text 対応**: 生成された PDF は、macOS のプレビューアプリなどで開くと自動的に文字認識（OCR）が行われ、テキストの選択やコピーが可能です。
- **スマートな自動停止**: ページのハッシュ値を比較し、書籍の終わりに到達すると自動でキャプチャを終了します。

---

## 📋 動作環境

- **OS**: macOS (Apple Silicon 推奨)
- **Python**: 3.11 以上
- **共通依存**: `img2pdf`, `Pillow`
- **個別依存**:
    - `kindle_app_to_pdf`: 特になし (macOS 標準機能を使用)
    - `kindle_to_pdf`: `playwright`

---

## 📖 クイックスタート

各ディレクトリに移動し、`setup.sh` を実行して環境を構築してください。

### Kindle App 版を使用する場合
```bash
cd kindle_app_to_pdf
bash setup.sh
python main.py
```

### Kindle Cloud Reader 版を使用する場合
```bash
cd kindle_to_pdf
bash setup.sh
python main.py --launch-chrome
```

---

## 📂 リポジトリ構成

```text
.
├── .gitignore
├── README.md                # 本ファイル
├── kindle_app_to_pdf/       # デスクトップアプリ用ツール
│   ├── main.py
│   ├── setup.sh
│   └── README.md
├── kindle_to_pdf/           # クラウドリーダー用ツール
│   ├── main.py
│   ├── setup.sh
│   └── README.md
└── memo/                    # 関連メモ・資料
```

---

## ⚠️ 注意事項

- **私的利用の範囲内で**: 本ツールは著作権法第30条（私的使用のための複製）に基づき、個人的な学習や資料管理を目的として作成されています。生成した PDF の再配布等は厳禁です。
- **自己責任で**: Amazon Kindle の利用規約を確認の上、自己責任でご利用ください。
