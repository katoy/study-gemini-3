# NHK ラジオ聞き逃しダウンローダー

NHK ラジオの聞き逃し番組を一覧表示し、番組ごとにエピソードを選んで保存できる Python スクリプトです。GUI で番組を探して複数話をまとめて保存する使い方と、URL を直接指定して保存する使い方の両方に対応しています。

## ⚠️ 重要: 注意事項

- **著作権について**: 本ツールは、個人利用や著作権法で認められた範囲での利用を前提としています。ダウンロードした音声の再配布や公開は行わないでください。
- **外部コマンド依存**: 実際の取得処理には `yt-dlp` を使用します。事前にインストールが必要です。
- **GUI について**: 番組一覧ブラウザは `tkinter` を使います。Python 実行環境に `tkinter` が入っていない場合、GUI モードは起動できません。

## 特徴

- **番組一覧を GUI で閲覧**: 番組一覧を表示し、検索しながら対象番組を選べます。
- **エピソード一覧を取得して複数選択**: 選択した番組の配信回一覧を取得し、必要な回だけまとめて保存できます。
- **URL 直接指定にも対応**: 番組 URL を引数で渡して、そのまま保存できます。
- **キャッシュ付き**: 番組一覧・エピソード一覧を `.cache/` に保持し、再取得を減らします。取得失敗時は期限切れキャッシュも再利用します。
- **重複保存を回避**: 保存済みファイルと `.downloaded.json` を使って、ダウンロード済みエピソードを追跡します。
- **ジャンル別に整理して保存**: `downloads/<ジャンル>/<番組名>/` 配下にファイルをまとめます。

## 動作環境

- **Python**: 3.11 以上推奨
- **外部コマンド**: `yt-dlp`
- **Python 標準ライブラリ**: `tkinter` を含む通常の Python 環境

## セットアップ

### 1. リポジトリを配置

このディレクトリに移動します。

```bash
cd radio
```

### 2. `yt-dlp` をインストール

```bash
brew install yt-dlp
```

または:

```bash
python3 -m pip install -U yt-dlp
```

### 3. 実行確認

```bash
python3 nhk_radio_dl.py --help
```

## 使い方

### GUI で番組を選んで保存

```bash
python3 nhk_radio_dl.py
```

- 上段で番組を選択
- ダブルクリックまたは Enter 相当の操作でエピソード一覧を取得
- 下段で複数選択してダウンロード

### URL を直接指定して保存

```bash
python3 nhk_radio_dl.py "https://www.nhk.or.jp/radio/ondemand/detail.html?p=XXXX_01"
```

### 直近 N 件だけ保存

```bash
python3 nhk_radio_dl.py "https://www.nhk.or.jp/radio/ondemand/detail.html?p=XXXX_01" -n 5
```

### 保存先ディレクトリを変更

```bash
python3 nhk_radio_dl.py -o ~/Downloads/nhk
```

### 特定ジャンルだけ表示

```bash
python3 nhk_radio_dl.py -g language
```

### キャッシュを削除

```bash
python3 nhk_radio_dl.py --clear-cache
```

## オプション

- `url`: 番組 URL。省略時は GUI モード
- `--output-dir`, `-o`: 保存先ディレクトリ (デフォルト: `./downloads`)
- `--max-items`, `-n`: 最大ダウンロード件数
- `--keep-video`: 音声変換せず元ファイルを保持
- `--clear-cache`: エピソード一覧キャッシュを削除して終了
- `--genre`, `-g`: `language`, `music`, `news`, `drama`, `sports`, `documentary`, `variety` のいずれかで絞り込み

## 保存先

デフォルトでは次のように保存されます。

```text
downloads/
└── <ジャンル>/
    └── <番組名>/
        ├── YYYYMMDD_<番組名>_<回タイトル>.mp3
        └── .downloaded.json
```

`-n` を付けて複数件ダウンロードする場合、先頭にプレイリスト順の番号が付くことがあります。

## キャッシュ

- 番組一覧キャッシュ: `.cache/programs/`
- エピソード一覧キャッシュ: `.cache/episodes/`
- GUI 設定: `.cache/ui_settings.json`

GUI のテーマ、文字サイズ、検索履歴もキャッシュ配下に保存されます。

番組 API の実装ベース仕様は `API.md` を参照してください。

## トラブルシューティング

### `yt-dlp` が見つからない

`yt-dlp` のインストール後、ターミナルを開き直すか、`yt-dlp --version` が通ることを確認してください。

### GUI を起動できない

- `python3 -m tkinter` が起動するか確認してください。
- `tkinter` を含まない Python を使っている場合は、標準の Python 実行環境を使ってください。

### ダウンロード済み扱いになる / 同じ回を再取得したい

保存先にある音声ファイルと `.downloaded.json` の両方が判定に使われます。必要なら対象番組ディレクトリ内のファイルや `.downloaded.json` を整理してください。

## ファイル構成

```text
radio/
├── API.md           # 番組 API の実装ベース仕様
├── nhk_radio_dl.py  # メインスクリプト
├── README.md        # このドキュメント
├── .cache/          # 番組一覧・エピソード一覧・UI 設定キャッシュ
└── downloads/       # ダウンロード保存先
```

## ライセンス

特に明記がなければ、このディレクトリのコードはリポジトリ全体の扱いに従ってください。
