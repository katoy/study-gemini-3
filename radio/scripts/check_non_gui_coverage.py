#!/usr/bin/env python3
"""Fail when non-GUI source files are not fully covered."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _is_non_gui_module(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized.startswith("src/nhk_radio/") and not normalized.startswith("src/nhk_radio/gui/")


def main() -> int:
    coverage_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("coverage.json")
    if not coverage_path.exists():
        print(f"coverage file not found: {coverage_path}", file=sys.stderr)
        return 1

    with coverage_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    files: dict[str, dict] = payload.get("files", {})
    non_gui_files = {
        path: info for path, info in files.items() if _is_non_gui_module(path)
    }
    if not non_gui_files:
        print("no non-GUI source files were found in coverage data", file=sys.stderr)
        return 1

    failures: list[tuple[str, float]] = []
    for path, info in sorted(non_gui_files.items()):
        percent = float(info["summary"]["percent_covered"])
        if percent < 100.0:
            failures.append((path, percent))

    if failures:
        print("non-GUI coverage check failed:", file=sys.stderr)
        for path, percent in failures:
            print(f"  {path}: {percent:.2f}%", file=sys.stderr)
        return 1

    print(f"non-GUI coverage OK: {len(non_gui_files)} files at 100%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
