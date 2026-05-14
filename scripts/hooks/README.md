# Git Hooks

このディレクトリのフックを有効化するには：

```bash
cp scripts/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

または、リポジトリのセットアップ時に以下を実行：

```bash
git config core.hooksPath scripts/hooks
```
