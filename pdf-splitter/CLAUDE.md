# Project Rules: PDF Splitter

## Commands (Token-Optimized)
- Test suite: `uv run --python 3.12 --with pytest --with pypdf pytest tests/ -q` (always use `-q` to save tokens)
- Formatter/Lint: `uv run ruff check --fix`

## Agent Token Optimization Guidelines
To keep token consumption 60-90% lower, all executing agents must follow these rules:

1. **Concise Communication**
   - Keep explanations minimal. Skip long intros, greetings, and repetitive summaries.
   - Prefer pointing to the target files using `file://` scheme links rather than duplicating large code blocks in chat responses.
   - When editing files, only show/discuss the exact diffs or modified lines.

2. **Context Engineering**
   - Do NOT load large source files in their entirety. Always specify a precise range of lines (`StartLine` and `EndLine`) when calling `view_file`.
   - Aim to keep the active loaded context under 2,000 lines. Start a fresh session if the chat context grows stale.

3. **Quiet Command Execution**
   - When running CLI tests or build scripts, always append quiet flags (`-q`, `--quiet`, `--silent`) to prevent long logs from filling the context window.
   - Use `rtk` (Rust Token Killer) commands directly if the automatic hook is bypassed.

4. **Surgical Code Modifications**
   - Prefer `replace_file_content` over `write_to_file` with `Overwrite: true` for edits to minimize system write tokens, unless rewriting/creating the file from scratch.
