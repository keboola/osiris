#!/usr/bin/env python3
"""Dev shim: run the CLI without installing the package."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from osiris.cli import app  # noqa: E402

if __name__ == "__main__":
    app()
