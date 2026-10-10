"""Tic-tac-toe with Strands Robots + Claude: `move`, `play` and `board`.

    python scripts/strands_game.py move "top left"          # no agent, one move (asks to confirm)
    python scripts/strands_game.py play                     # Claude is X, you are O; the camera detects
    python scripts/strands_game.py board                    # only read the board

The code lives in the `xox` package (`xox/cli.py` has the full help); this file only puts the repo
root on the import path, so `python -m xox <command>` run from the repo root is the same program.
Runs in the `.venv-strands` environment.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from xox.cli import main  # noqa: E402 - the path line above has to come first

if __name__ == "__main__":
    main()
