"""Shared building blocks for the SO-101 tic-tac-toe game."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # the repo: calibration/, outputs/ and .env live here


def load_env() -> None:
    """Loads KEY=value lines from the .env file at the repo root into the environment (if any, no overwrite)."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            os.environ.setdefault(name.removeprefix("export ").strip(), value.strip().strip("'\""))
