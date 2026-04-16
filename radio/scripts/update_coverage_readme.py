#!/usr/bin/env python3
"""テストカバレッジを計測して README.md の「テストカバレッジ」セクションを更新するスクリプト。"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

RADIO_DIR = Path(__file__).parent.parent
README = RADIO_DIR / "README.md"
COVERAGE_JSON = RADIO_DIR / "coverage.json"

# README 内のカバレッジセクションの区切りマーカー
BEGIN_MARKER = "<!-- COVERAGE-BEGIN -->"
END_MARKER = "<!-- COVERAGE-END -->"


def run_coverage() -> dict:
    """pytest --cov を実行して coverage.json を生成し、読み込む。"""
    subprocess.run(
        [
            "uv", "run", "pytest",
            "tests/",
            "--cov=src/nhk_radio",
            "--cov-report=json",
            "-q",
            "--tb=short",
        ],
        cwd=RADIO_DIR,
        check=True,
    )
    with open(COVERAGE_JSON) as f:
        return json.load(f)


def build_table(data: dict) -> str:
    """coverage.json から Markdown テーブルを生成する。"""
    files = data["files"]
    today = date.today().isoformat()

    rows = []
    for path, info in sorted(files.items()):
        # src/nhk_radio/ を除いた相対パス
        rel = path.replace("src/nhk_radio/", "")
        stmts = info["summary"]["num_statements"]
        pct = info["summary"]["percent_covered"]
        rows.append((rel, stmts, pct))

    totals = data["totals"]
    total_stmts = totals["num_statements"]
    total_pct = totals["percent_covered"]

    lines = [
        f"最終計測: {today}",
        "",
        "| モジュール | ステートメント数 | カバレッジ |",
        "|:----------|----------------:|----------:|",
    ]
    for rel, stmts, pct in rows:
        lines.append(f"| `{rel}` | {stmts} | {pct:.0f}% |")
    lines.append(f"| **合計** | **{total_stmts}** | **{total_pct:.0f}%** |")

    return "\n".join(lines)


def update_readme(table: str) -> None:
    """README.md のカバレッジセクションを差し替える。"""
    text = README.read_text()

    new_section = f"{BEGIN_MARKER}\n{table}\n{END_MARKER}"

    if BEGIN_MARKER in text and END_MARKER in text:
        before = text[: text.index(BEGIN_MARKER)]
        after = text[text.index(END_MARKER) + len(END_MARKER) :]
        updated = before + new_section + after
    else:
        # セクションがなければ「## ライセンス」の直前に挿入
        insert_at = text.rfind("\n## ライセンス")
        if insert_at == -1:
            updated = text + f"\n\n## テストカバレッジ\n\n{new_section}\n"
        else:
            updated = (
                text[:insert_at]
                + f"\n\n## テストカバレッジ\n\n{new_section}"
                + text[insert_at:]
            )

    README.write_text(updated)
    print(f"README.md を更新しました（カバレッジ {table.splitlines()[-1]}）")


def main() -> None:
    print("カバレッジを計測中...")
    try:
        data = run_coverage()
    except subprocess.CalledProcessError:
        print("テスト失敗。README は更新しません。", file=sys.stderr)
        sys.exit(1)

    table = build_table(data)
    update_readme(table)

    # 一時ファイルを削除
    COVERAGE_JSON.unlink(missing_ok=True)

    # README を git add
    subprocess.run(["git", "add", str(README)], cwd=RADIO_DIR, check=True)


if __name__ == "__main__":
    main()
