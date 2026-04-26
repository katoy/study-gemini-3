#!/usr/bin/env python3
"""Source-tree convenience wrapper for the package CLI."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    from nhk_radio.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
