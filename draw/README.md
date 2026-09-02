# Gemini Excalidraw Web Chat Application

Google Gen AI SDK (`@google/genai`) を使った Gemini API と **Excalidraw** ホワイトボードを統合した Web チャットアプリケーションです。

## 🌟 特徴
- **対話型チャット**: 左側のチャット UI から Gemini と会話できます。
- **Excalidraw 統合キャンバス**: 右側のホワイトボードで図を直感的に閲覧・編集できます。
- **MCP (Model Context Protocol) 互換のツール呼び出し**: Gemini が Function Calling (`create_view`) を介してホワイトボード要素（矩形・楕円・矢印・テキスト・カメラ表示範囲・削除など）を自動生成・編集します。
- **リアルタイム同期**: バックエンドとフロントエンドが WebSocket で接続されており、Gemini が生成した図がリアルタイムにホワイトボードへ描画・アニメーション同期されます。
- **コンテキスト認識**: 現在ホワイトボード上にある図の要素情報を Gemini に送信するため、「この図に〇〇を追加して」「右の四角の色を変えて」などの対話的な図の修正が可能です。

## 📁 ディレクトリ構成

```text
draw/
├── index.html            # Vite HTML エントリポイント
├── package.json          # 依存関係・スクリプト設定
├── tsconfig.json         # TypeScript 設定
├── vite.config.ts        # Vite 設定 (プロキシ & WebSocket 転送設定)
├── server.ts             # Express & WebSocket バックエンド (Gemini API 連携)
├── src/
│   ├── main.tsx          # React エントリポイント
│   ├── App.tsx           # チャット UI & Excalidraw コンポーネント
│   ├── index.css         # スタイル定義
│   └── vite-env.d.ts     # 型定義
└── README.md
```

## 🔑 API キーの取得方法

1. [Google AI Studio](https://aistudio.google.com/) にアクセスして Google アカウントでログインします。
2. **「Get API key」** ボタンをクリックします。
3. **「Create API key」** を選択し、プロジェクトを指定または新規作成して API キーを発行します。
4. 発行された API キーをコピーして以下の環境変数設定に使用します。

## 🚀 起動方法

### 1. 依存ライブラリのインストール

```bash
npm install
```

### 2. 環境変数の設定

Gemini API Key を環境変数 `GEMINI_API_KEY` に設定します。

```bash
export GEMINI_API_KEY="your-gemini-api-key"
```

### 3. バックエンドサーバーの起動

Express API & WebSocket サーバー (ポート 3001) を起動します:

```bash
npm run dev:server
```

### 4. Vite フロントエンドの起動

別ターミナルで Vite 開発サーバー (ポート 3000) を起動します:

```bash
npm run dev:vite
```

ブラウザで [http://localhost:3000](http://localhost:3000) にアクセスしてください。

## 💬 使い方例

- **「マイクロサービス構成図を描いて」** -> Gemini が解説文を出力しつつ、Excalidraw 上に構成図を自動描画します。
- **「データベースを追加して接続線を引いて」** -> 現在の図の状態を把握した上で、要素を追加・更新します。
- **「フローチャートを作成して」** -> 処理フローを図示してくれます。
