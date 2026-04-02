# Claude Code 公式プラグインの取り込みと自動更新設定

## 目的

Claude Code の公式プラグインリポジトリ (`anthropics/claude-plugins-official`) が提供する
スキル・コマンド・エージェントを自分のローカル Claude Code 環境に導入し、
リポジトリが更新された際に自動で反映されるようにする。

---

## ゴール

1. Anthropic が公式管理するプラグインを Claude Code で利用できる状態にする
2. 公式リポジトリの更新が、次回セッション起動時に自動で反映される仕組みを構築する

---

## 背景

### 公式プラグインリポジトリ

- **URL**: https://github.com/anthropics/claude-plugins-official
- **説明**: Anthropic が管理する高品質な Claude Code プラグインのディレクトリ
- **構成**:
  - `plugins/` — Anthropic 製プラグイン（skills/commands/agents を含む）
  - `external_plugins/` — サードパーティ製プラグイン

### 主な公式プラグイン一覧

| プラグイン名 | 概要 |
|---|---|
| `code-review` | コードレビュー |
| `commit-commands` | git コミット操作 |
| `feature-dev` | フィーチャー開発支援 |
| `pr-review-toolkit` | PR レビュー |
| `security-guidance` | セキュリティガイド |
| `skill-creator` | スキル作成支援 |
| `typescript-lsp` | TypeScript LSP 統合 |
| `pyright-lsp` | Python LSP 統合 |
| `rust-analyzer-lsp` | Rust LSP 統合 |
| `hookify` | フック設定支援 |
| `plugin-dev` | プラグイン開発支援 |
| `claude-md-management` | CLAUDE.md 管理 |
| など | |

### プラグインの自動更新の仕組み

インストールされたプラグインは以下にバージョン固定でキャッシュされる。
公式リポジトリが更新されても自動では反映されない。

```
~/.claude/plugins/cache/claude-plugins-official/{plugin-name}/{version}/
```

`installed_plugins.json` にインストール時の `version` と `gitCommitSha` が記録される。

---

## 詳細手順

### ステップ 1: プラグインのインストール

Claude Code のインタラクティブセッション内でスラッシュコマンドを使用する。

```
# 個別インストール
/plugin install {plugin-name}@claude-plugins-official

# 例
/plugin install code-review@claude-plugins-official
/plugin install commit-commands@claude-plugins-official
```

または `/plugin > Discover` でブラウズしてインストールする。

### ステップ 2: 自動更新の設定

`~/.claude/settings.json` に `extraKnownMarketplaces` を追加し、`autoUpdate: true` を設定する。

**編集前:**
```json
{
  "language": "日本語",
  "voiceEnabled": true,
  "enabledPlugins": {
    "rust-analyzer-lsp@claude-plugins-official": true
  }
}
```

**編集後:**
```json
{
  "language": "日本語",
  "voiceEnabled": true,
  "enabledPlugins": {
    "rust-analyzer-lsp@claude-plugins-official": true
  },
  "extraKnownMarketplaces": {
    "claude-plugins-official": {
      "source": {
        "source": "github",
        "repo": "anthropics/claude-plugins-official"
      },
      "autoUpdate": true
    }
  }
}
```

**`autoUpdate: true` の効果:**
Claude Code 起動時に `anthropics/claude-plugins-official` リポジトリの最新状態を確認し、
インストール済みプラグインを自動でアップデートする。

### ステップ 3: 手動更新（任意）

自動更新を待たずに即時更新したい場合は、セッション内で以下を実行する。

```
# 特定プラグインを更新
/plugin update rust-analyzer-lsp@claude-plugins-official

# 全プラグインを更新
/plugin update --all
```

---

## 関連ファイル

| ファイル | 説明 |
|---|---|
| `~/.claude/settings.json` | ユーザー設定（autoUpdate 設定箇所） |
| `~/.claude/plugins/installed_plugins.json` | インストール済みプラグインの一覧とバージョン情報 |
| `~/.claude/plugins/known_marketplaces.json` | 登録済みマーケットプレイスの情報 |
| `~/.claude/plugins/cache/` | プラグインのローカルキャッシュ |

---

## 参考

- 公式リポジトリ: https://github.com/anthropics/claude-plugins-official
- コミュニティプラグイン: https://github.com/anthropics/claude-plugins-community
