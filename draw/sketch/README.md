# Gemini Sketch Web Chat Application (Sketch-mcp)

Google Gen AI SDK (`@google/genai`) を使った Gemini API と **Sketch (Sketch-mcp)** を統合した Web チャットアプリケーションです。

## 🌟 特徴
- **対話型チャット**: 左側のチャット UI から Gemini と自然言語で会話できます。
- **Sketch キャンバス統合**: 右側のキャンバスでワイヤーフレームやアーキテクチャ図、UIコンポーネントを直感的に閲覧・編集できます。
- **Sketch-mcp 互換**:
  - Mac の **Sketch アプリ内蔵 MCP サーバー** (`http://localhost:31126/mcp`) と連携可能。
  - Sketch アプリが起動していなくても、内蔵のベクターレンダラーによりブラウザ上で図の描画・アニメーション確認が完結。
  - Gemini が Function Calling (`draw_dsl`, `create_view`, `run_sketch_code`) を介して Sketch 要素（Artboard、矩形、楕円、矢印、テキスト、グループ等）を自動生成・編集します。
- **リアルタイム同期**: バックエンドとフロントエンドが WebSocket で接続されており、Gemini が生成した図がリアルタイムにキャンバスへ描画・アニメーション同期されます。
- **コンテキスト認識**: 現在キャンバス上にある図のレイヤー情報を Gemini に送信するため、「この要素に〇〇を追加して」「配置を右にずらして」などの対話的な図の修正が可能です。
- **マルチフォーマット出力**: JSON、PNG、SVG へのエクスポートに対応。

## 📁 ディレクトリ構成

```text
sketch/
├── index.html            # Vite HTML エントリポイント
├── package.json          # 依存関係・スクリプト設定
├── tsconfig.json         # TypeScript 設定
├── vite.config.ts        # Vite 設定 (ポート 3010, プロキシ & WebSocket 転送)
├── vitest.config.ts      # Vitest 単体テスト設定
├── playwright.config.ts  # Playwright E2E 設定
├── server.ts             # Express & WebSocket バックエンド (ポート 3011, Gemini API 連携)
├── dsl.ts                # Sketch DSL パーサー & ヘルパー
├── src/
│   ├── main.tsx          # React エントリポイント
│   ├── App.tsx           # チャット UI & Sketch キャンバスコンポーネント
│   ├── index.css         # スタイル定義
│   ├── mergeServerElements.ts # 要素マージロジック
│   └── vite-env.d.ts     # 型定義
├── scripts/
│   ├── dev-all.sh        # バックエンド・フロントエンド一括管理スクリプト
│   ├── server-control.sh # バックエンド単体管理スクリプト
│   └── frontend-control.sh # フロントエンド単体管理スクリプト
├── tests/
│   └── unit/             # 単体テスト群
└── README.md
```

## 🔑 API キーの取得方法

1. [Google AI Studio](https://aistudio.google.com/) にアクセスして Google アカウントでログインします。
2. **「Get API key」** ボタンをクリックします。
3. **「Create API key」** を選択し、プロジェクトを指定または新規作成して API キーを発行します。
4. 発行された API キーをコピーして以下の環境変数設定に使用します。

## 💎 Sketch MCP Server の連携設定（任意）

Mac の Sketch デスクトップアプリをお持ちの場合、Sketch 組み込みの MCP サーバーと連携できます。

1. Sketch アプリを起動（バージョン 2025.2.4 以降）。
2. `⌘K` を押し「**Start MCP Server**」を選択、または「**Settings > General > MCP Server**」を有効化。
3. ローカルサーバー（デフォルト: `http://localhost:31126/mcp`）が起動します。
4. Antigravity / Gemini CLI の設定ファイル (`~/.gemini/config/mcp_config.json`) に以下が登録されています：
   ```json
   {
     "mcpServers": {
       "sketch": {
         "serverUrl": "http://localhost:31126/mcp"
       }
     }
   }
   ```

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

### 3. サーバーの起動

#### 方法 A: 一括起動スクリプト（推奨）

バックエンド＆フロントエンドを同時にバックグラウンドで起動：

```bash
./scripts/dev-all.sh start
```

状態確認・停止・再起動：

```bash
./scripts/dev-all.sh status    # サーバー状態確認
./scripts/dev-all.sh stop      # 全サーバー停止
./scripts/dev-all.sh restart   # 全サーバー再起動
```

#### 方法 B: 個別起動

バックエンドサーバーのみ（Express API & WebSocket, ポート 3011）:

```bash
./scripts/server-control.sh start
```

フロントエンドサーバーのみ（Vite, ポート 3010）:

```bash
./scripts/frontend-control.sh start
```

#### 方法 C: npm スクリプト（フォアグラウンド実行）

別々のターミナルで実行：

```bash
# ターミナル1: バックエンド
npm run dev:server

# ターミナル2: フロントエンド
npm run dev:vite
```

### 4. ブラウザアクセス

[http://localhost:3010](http://localhost:3010) にアクセスしてください。

#### サーバー情報

| サーバー | URL | 用途 |
|---------|-----|------|
| フロントエンド | http://localhost:3010 | Vite React UI |
| バックエンド API | http://localhost:3011 | Express API & WebSocket |
| WebSocket | ws://localhost:3011/api/ws | リアルタイム要素更新 |
| Sketch MCP ステータス | http://localhost:3011/api/sketch-mcp/status | Sketch MCP 接続状態確認 |

#### ログファイル

バックグラウンド起動時のログ：

```
logs/backend.log   # バックエンドログ
logs/frontend.log  # フロントエンドログ
```

## 💬 使い方例

- **「ECサイトの商品詳細ページのワイヤーフレームを描いて」** -> Gemini がレイアウトを思考し、Sketch キャンバス上にカードやボタン、画像プレースホルダを段階的に自動描画します。
- **「右側に購入手続きフローを追加して」** -> 現在のキャンバス状態を把握した上で、既存要素と重複しないようにフロー要素を追加します。
- **「全体をオレンジ基調のデザインに変更して」** -> 既存要素の色スタイルを Sketch 風に一括更新します。
