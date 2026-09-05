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

バックエンドサーバーのみ（Express API & WebSocket, ポート 3001）:

```bash
./scripts/server-control.sh start
```

フロントエンドサーバーのみ（Vite, ポート 3000）:

```bash
./scripts/frontend-control.sh start
```

個別スクリプトの操作：

```bash
./scripts/server-control.sh {start|stop|restart|status}
./scripts/frontend-control.sh {start|stop|restart|status}
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

[http://localhost:3000](http://localhost:3000) にアクセスしてください。

#### サーバー情報

| サーバー | URL | 用途 |
|---------|-----|------|
| フロントエンド | http://localhost:3000 | Vite React UI |
| バックエンド API | http://localhost:3001 | Express API |
| WebSocket | ws://localhost:3001/api/ws | リアルタイム要素更新 |

#### ログファイル

バックグラウンド起動時のログ：

```
logs/backend.log   # バックエンドログ
logs/frontend.log  # フロントエンドログ
```

## 💬 使い方例

- **「マイクロサービス構成図を描いて」** -> Gemini が解説文を出力しつつ、Excalidraw 上に構成図を自動描画します。
- **「データベースを追加して接続線を引いて」** -> 現在の図の状態を把握した上で、要素を追加・更新します。
- **「フローチャートを作成して」** -> 処理フローを図示してくれます。

## 📐 Excalidraw DSL 仕様

Excalidraw の図形を簡潔かつ高速に生成するためのパイプ区切り DSL です。

### 1. 基本図形・盤面コマンド
- `CHESSBOARD|id|x|y|size|lightColor|darkColor|pieces|styles`: チェス盤（全32駒・座標ラベル付きを1行で描画）
- `GRID|id|x|y|w|h|rows,cols|color1|color2|styles`: グリッド・市松模様盤（オセロ・将棋・チェスなど）
- `RECT|id|x|y|w|h|color|label|angle|styles`: 矩形
- `CIRCLE|id|cx|cy|radius|color|label|styles`: 正円
- `ELLIPSE|id|x|y|w|h|color|label|angle|styles`: 楕円
- `DIAMOND|id|x|y|w|h|color|label|angle|styles`: ひし形
- `STAR|id|cx,cy,radius|color|label|styles`: 星型
- `CLOUD|id|x|y|w|h|color|label|styles`: 雲型・クラウド
- `FRAME|id|x|y|w|h|color|label|styles`: コンテナ枠（点線外枠＋タイトル）
- `CARD|id|x|y|w|h|color|title|body|styles`: カード UI（枠＋タイトル＋本文）
- `TRIANGLE|id|x1,y1|x2,y2|x3,y3|color|label|styles`: 三角形
- `POLYGON|id|x1,y1|x2,y2|...|xn,yn|color|label|styles`: 閉じた多角形
- `POLYLINE|id|x1,y1|x2,y2|...|xn,yn|color|label|styles`: 開いた折れ線

### 2. コネクタ・矢印・線
- `ARROW|id|from|to|color|label|styles`: 単方向矢印
- `BIARROW|id|from|to|color|label|styles`: 双方向矢印（両端矢頭）
- `ELBOW|id|from|to|color|label|styles`: 直角に折れ曲がるクランク型矢印
- `LINE|id|from|to|color|label|styles`: 直線（矢頭なし）
> `from` や `to` は要素 ID（例: `box1`）または座標 `x,y` を直接指定できます。

### 3. 要素操作コマンド（移動・拡大縮小・回転・表示制御・削除）
- `MOVE|id|x,y`: 指定 ID の要素を絶対座標 (x, y) へ移動
- `MOVE_BY|id|dx,dy`: 指定 ID の要素を相対移動（dx, dy 分シフト）
- `RESIZE|id|w,h`: 指定 ID の幅・高さを変更
- `SCALE|id|factor`: 指定 ID のサイズを倍率変更（例: `SCALE|box1|1.5` で 1.5 倍）
- `ROTATE|id|angle`: 絶対角度を設定（度数法・ラジアン自動変換）
- `ROTATE_BY|id|angle`: 相対回転
- `HIDE|id1,id2,...`: 要素を非表示（透明度 0%）
- `SHOW|id1,id2,...|opacity`: 非表示要素を再表示（デフォルト 100%）
- `DEL|id1,id2,...`: 要素を完全削除

### 4. テキスト
- `TEXT|id|x|y|fontSize|color|text|styles`: テキストラベル

### 5. プログラマブル構文・マクロ（DSL v2）
AI（LLM）がコンパクトなトークン数で複雑な図や反復パターンを描画できるように設計されたマクロ構文です。
- **変数定義**: `LET|var=val`
  - 例: `LET|w=140`、`LET|h=70` と宣言後、`{w}` や `{h}` で参照可能。
  - `{100 + i * 150}` のように四則演算の安全な式展開にも対応。
- **メソッド・コンポーネント定義**: `DEF|name(p1, p2, ...)|cmd1;cmd2;...`
  - 再利用可能なパーツ（ノードやカード）をテンプレート化。
  - 例: `DEF|step(id,x,y,label)|RECT|{id}|{x}|{y}|140|70|blue|{label}`
- **コンポーネント呼び出し**: `CALL|name|arg1|arg2|...`
  - 例: `CALL|step|s1|100|100|Input`
- **範囲ループ**: `FOR|var|start..end|cmd1;cmd2;...`
  - 例: `FOR|i|0..3|RECT|b_{i}|{100 + i * 160}|100|140|70|blue|Step {i + 1}`
- **回数ループ**: `REPEAT|count|cmd1;cmd2;...`
  - 変数 `{i}` (0-indexed) が自動的に提供されます。
  - 例: `REPEAT|3|CIRCLE|c_{i}|{100 + i * 80}|200|30|orange|C{i}`
- **オートレイアウト（自動整列）**:
  - `ROW|x,y,gap|cmd1;cmd2;...`: 要素を水平方向に自動インクリメント配置
  - `COL|x,y,gap|cmd1;cmd2;...`: 要素を垂直方向に自動インクリメント配置
  - 例: `ROW|100,100,20|RECT|r1||||120|60|blue|A;RECT|r2||||120|60|green|B;RECT|r3||||120|60|purple|C`
- **連鎖接続**: `CONNECT|id1 -> id2 -> id3 ...|color|label|styles`
  - パイプラインや一連の処理フローを 1 行で矢印接続。
  - 例: `CONNECT|step1 -> step2 -> step3|dark|next|dashed`

### 6. Excalidraw MCP 連携・キャンバス拡張操作
- `GROUP|groupId|id1,id2,...`: 複数要素を 1 つのグループにバインド
- `UNGROUP|id1,id2,...`: 要素のグループ化を解除
- `LINK|id|url`: 要素にクリック可能なハイパーリンクを設定（Excalidraw の link プロパティ）
- `FRONT|id1,id2,...`: 指定要素を最前面（レイヤー最上位）に移動
- `BACK|id1,id2,...`: 指定要素を最背面（レイヤー最下位）に移動

### 7. スタイル指定オプション (`styles`)
カンマ・セミコロン区切りで指定可能:
- **線種**: `solid`, `dashed` (破線), `dotted` (点線)
- **塗り**: `solid`, `hachure` (斜線ハッチング), `cross-hatch` (格子), `dots` (ドット)
- **角丸**: `round` / `rounded` (角丸), `sharp` (角尖り)
- **線幅**: `w=1`, `w=2`, `w=3`, `w=4` など
- **透明度**: `opacity=0` 〜 `opacity=100`
- **フォント**: `font=virgil` (手書き風), `font=sans` (標準ゴシック), `font=mono` (等幅)
- **文字揃え**: `align=left`, `align=center`, `align=right`

### 8. カラーパレット
- 定義済みカラー: `blue`, `green`, `orange`, `purple`, `red`, `yellow`, `teal`, `dark`, `gray`, `white`, `black`, `pink`, `cyan`, `violet`, `lime`, `indigo`
- HEX カラー指定（例: `#ff5722`）にも対応しています。

