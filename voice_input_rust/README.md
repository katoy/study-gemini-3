# VoiceInput - 完全ローカル LLM 音声入力デスクトップアプリ (Rust版)

![Rust](https://img.shields.io/badge/Rust-1.80%2B-orange)
![macOS](https://img.shields.io/badge/Platform-macOS-lightgrey)
![Metal](https://img.shields.io/badge/Accelerate-Metal-blue)
![License MIT](https://img.shields.io/badge/License-MIT-green)

完全ローカル環境（プライバシー完全保護・オフライン動作）で動作する、高品質・低遅延な音声入力デスクトップアプリケーション（Rust / egui / whisper-rs）です。

参考：
- https://www.youtube.com/watch?v=7yst8Ee_lH0&t=1313s
  ローカルLLMを活用して無料で音声入力できるアプリを個人開発します！AIでアプリ開発をフルで実演します

---

## 🌟 主な特徴・アーキテクチャ

- **完全ローカル & プライバシー保護**: 音声データやテキストが外部サーバーに送信されることはありません。
- **Metal GPU アクセラレーション**: `whisper-rs` (whisper.cpp) の Metal バックエンドを利用し、Apple Silicon 上で高速な音声認識を実現。
- **プラグイン型 4層アーキテクチャ**:
  - `VadEngine`（音声区間検出）
  - `StreamingAsrEngine`（リアルタイムプレビュー）
  - `BatchAsrEngine`（高精度確定転写）
  - `RefinerEngine`（LLM / ルールベース整形）
- **テキスト自動挿入・クリップボード連携**: 音声認識・整形結果をアクティブウィンドウに自動挿入。
- **デスクトップ GUI (egui)**: クロスプラットフォームかつ軽量な GUI インターフェース。

---

## 📁 フォルダ構成

```text
voice_input_rust/
├── models/             # Whisper ggml モデル配置ディレクトリ (*.bin)
├── scripts/            # ユーティリティスクリプト
│   ├── download_models.sh  # Whisper モデルダウンロード用スクリプト
│   └── clean.sh            # ビルドキャッシュ・プロファイル削除
├── src/                # Rust ソースコード
│   ├── audio.rs        # 音声キャプチャ (cpal)
│   ├── dictionary.rs   # ユーザー辞書
│   ├── inserter.rs     # テキスト挿入 / クリップボード
│   ├── engine/         # 各種 ASR・VAD・Refiner エンジン
│   └── ui/             # egui インターフェース
└── docs/               # 要件定義書・仕様書
```

---

## 🚀 セットアップと実行方法

### 1. 準備 (モデルのダウンロード)

Whisper モデル（ggml 形式）をダウンロードします。付属のスクリプトを使用すると簡単にセットアップできます。

```bash
chmod +x scripts/download_models.sh
./scripts/download_models.sh
```

> **対話メニューで利用したいモデル（例: `3) small` など）を選択してください。**  
> モデルファイルは `models/` ディレクトリ配下に保存されます。

### 2. ビルド・実行

#### チェック
```bash
cargo check
```

#### デバッグ実行
```bash
cargo run
```

#### テスト実行
```bash
cargo test
```

#### リリースビルド
```bash
cargo build --release
```

### 3. 開発・メンテナンスタスク

#### コードフォーマット & 構文チェック
```bash
cargo fmt
cargo clippy
```

#### キャッシュ・一時ファイルのクリーンアップ
ビルド中間生成物（`target/`）、プロファイルデータ、一時ファイルを削除します。

```bash
./scripts/clean.sh
```


---

## 🛠️ 技術スタック

- **言語**: Rust (2021 edition)
- **GUI**: [egui](https://github.com/emilk/egui) / [eframe](https://github.com/emilk/egui/tree/master/crates/eframe)
- **ASR Engine**: [whisper-rs](https://github.com/tazzben/whisper-rs) (Metal 有効化)
- **Audio Capture**: [cpal](https://github.com/RustAudio/cpal)
- **Clipboard & Input**: [arboard](https://github.com/1st1/arboard), [enigo](https://github.com/enigo-rs/enigo)
- **Async Runtime**: [tokio](https://tokio.rs/)

---

## 📄 ライセンス

[MIT License](LICENSE)

