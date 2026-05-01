# Hello World（多言語・音声対応）

Python で作成した多言語対応の Hello World プログラムです。テキスト出力と同時に音声読み上げも行います。

## 目次

- [機能](#機能)
- [動作環境](#動作環境)
- [使い方](#使い方)
  - [デフォルト実行（英語）](#デフォルト実行英語)
  - [言語を指定して実行](#言語を指定して実行)
  - [対応言語一覧の表示](#対応言語一覧の表示)
- [対応言語](#対応言語)
- [テスト](#テスト)
  - [テストの実行](#テストの実行)
  - [カバレッジレポート](#カバレッジレポート)
- [Docker](#docker)
  - [イメージのビルド](#イメージのビルド)
  - [コンテナの実行](#コンテナの実行)
- [ファイル構成](#ファイル構成)

---

## 機能

- 10言語での Hello World テキスト出力
- モールス信号モード（テキスト変換 + 800Hz サイン波での再生）
- macOS の `say` コマンドによるネイティブ音声読み上げ
- コマンドライン引数で言語を切り替え可能

## 動作環境

- macOS（`say` コマンドが必要）※ 非 macOS 環境では音声再生はスキップされ、テキスト出力のみ動作します
- Python 3.10+
- [uv](https://docs.astral.sh/uv/)

## セットアップ

```bash
# 依存関係のインストール（.python-version に基づき適切な Python が使用されます）
uv sync

# pre-commit のインストール（初回のみ）
pre-commit install
```

## 使い方

### デフォルト実行（英語）

```bash
uv run hello
```

出力:
```
Hello, World!
```

### 言語を指定して実行

```bash
uv run hello <言語コード>
```

例:
```bash
uv run hello ja   # 日本語
uv run hello zh   # 中国語
uv run hello es   # スペイン語
```

### 対応言語一覧の表示

```bash
uv run hello --list
```

出力:
```
en: Hello, World!  [Daniel]
ja: こんにちは、世界！  [Kyoko]
zh: 你好，世界！  [Tingting]
...
```

## 対応言語

| コード | 言語 | メッセージ | 音声 |
|---|---|---|---|
| `en` | 英語 | Hello, World! | Daniel |
| `ja` | 日本語 | こんにちは、世界！ | Kyoko |
| `zh` | 中国語 | 你好，世界！ | Tingting |
| `ko` | 韓国語 | 안녕하세요, 세계! | Yuna |
| `es` | スペイン語 | ¡Hola, Mundo! | Jorge |
| `fr` | フランス語 | Bonjour, le monde ! | Thomas |
| `de` | ドイツ語 | Hallo, Welt! | Anna |
| `pt` | ポルトガル語 | Olá, Mundo! | Joana |
| `ar` | アラビア語 | مرحبا بالعالم! | Maged |
| `ru` | ロシア語 | Привет, мир! | Milena |
| `morse` | モールス信号 | HELLO WORLD（モールスへ変換） | — |

## テスト

### テストの実行

```bash
uv run pytest
```

### カバレッジレポート

カバレッジ **100%** が必須となるよう設定されています。100% に満たない場合、テストは失敗します。

```bash
# pytest によるテスト実行と 100% カバレッジの確認
uv run pytest
```

## CI (継続的インテグレーション)

### ローカルでの CI 実行 (Docker)

GitHub Actions と同等の品質チェックをローカルの Docker 環境で実行できます。

```bash
./ci.sh
```

### コミット前の自動チェック (pre-commit)

`git commit` 時に `ruff` (Lint/Format) と `mypy` (型チェック) を自動的に実行します。

```bash
# 手動での全ファイルチェック
pre-commit run --all-files
```

---

## Docker

※ Docker 環境では `say` コマンドが使えないため、テキスト出力のみ動作します。

### 簡単な実行（推奨）

`run.sh` を使うと、イメージのビルドと実行をまとめて行えます。引数もそのまま渡せます。

```bash
./run.sh          # デフォルト（英語）
./run.sh ja       # 日本語
./run.sh --list   # 対応言語一覧
```

### 手動での実行

```bash
# イメージのビルド
docker build -t hello-world .

# コンテナの実行
docker run --rm hello-world
```

## ファイル構成

```
.
├── hello.py                  # メインプログラム
├── test_hello.py             # テストコード
├── pyproject.toml            # プロジェクト設定・依存関係・CI設定
├── uv.lock                   # 依存関係ロックファイル
├── .python-version           # 使用する Python バージョン指定
├── .pre-commit-config.yaml   # pre-commit 設定
├── Dockerfile                # 本番用 Docker イメージ定義
├── Dockerfile.ci             # CI 用 Docker イメージ定義
├── Dockerfile.ci.dockerignore # CI 用 Docker ビルド除外設定
├── ci.sh                     # ローカル CI 実行スクリプト
├── run.sh                    # Docker 実行スクリプト
├── .dockerignore             # Docker ビルド除外設定
├── .gitignore                # Git 管理除外設定
├── .github/workflows/ci.yml  # GitHub Actions 定義
├── prompt.md                 # プロジェクト構築プロンプト
├── LICENSE                   # ライセンスファイル
└── README.md                 # このファイル
```

## ライセンス

[MIT License](LICENSE)
