"""Tic-tac-toe with Strands Robots + Claude.

Claude picks the cell, the code turns it into the exact training sentence, SmolVLA moves the arm.
The game asks no questions: the top camera itself sees the X in the pick slot, the X the arm placed
and the O you placed. Runs in the `.venv-strands` environment.

    python scripts/strands_game.py move "top left"          # no agent, one move (asks to confirm)
    python scripts/strands_game.py play                     # Claude is X, you are O; the camera detects
    python scripts/strands_game.py play --confirm           # ask at every step, type the O by hand
    python scripts/strands_game.py play --dry-run           # no arm, only the flow
    python scripts/strands_game.py board                    # only read the board
    python scripts/strands_game.py eval                     # benchmark: every cell 3 times, the camera judges

`python -m xox <command>` is the same program. `play` needs ANTHROPIC_API_KEY and opens a local
dashboard in the browser (cameras, board, moves, a Stop button); `--no-dashboard` turns it off.
Cell names are in the robot's frame:
top = far from the arm base, left = the arm's left (same as the drawing in docs/rounds/round1.md).

Terminal messages are English by default; `--lang tr` or XOX_LANG=tr switches them to Turkish.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

from PIL import Image

from . import ROOT, i18n, load_env
from .arm import Arm
from .board import CELLS, draw
from .evaluate import eval_command
from .game import play_command
from .i18n import t
from .vision import crop_board, grab_frame, read_board

MODEL = "fport/smolvla-tic-tac-toe-so101-x-round1-20k"
PORT = "/dev/cu.usbmodem5AB01794851"
DASHBOARD_PORT = 8765


def move_command(args: argparse.Namespace) -> None:
    arm = Arm(args)
    try:
        ran, note = arm.play(args.cell)
        print(note if ran else t("move_not_played", reason=note))
    finally:
        arm.close()


def board_command(args: argparse.Namespace) -> None:
    """Reads the board without moving the arm: from a camera frame or from the file given with `--image`."""
    load_env()
    frame = Image.open(args.image) if args.image else grab_frame(args.top)
    if args.save:
        crop_board(frame).save(args.save)
    print(draw(read_board(frame, args.claude)))


def positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def add_dashboard_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-dashboard", action="store_true", help="do not start the local web dashboard")
    parser.add_argument(
        "--dashboard-port", type=int, default=DASHBOARD_PORT, help="dashboard port (default: 8765, 0 = any free)"
    )
    parser.add_argument("--no-open", action="store_true", help="do not open the dashboard in the browser")


def main(prog: str | None = None) -> None:
    p = argparse.ArgumentParser(
        prog=prog, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default=MODEL, help="HF repo name or local checkpoint folder")
    common.add_argument("--port", default=PORT, help="follower port")
    common.add_argument("--top", type=int, default=0, help="top camera index")
    common.add_argument("--wrist", type=int, default=1, help="wrist camera index")
    common.add_argument("--duration", type=float, default=45.0, help="at most this many seconds per move")
    common.add_argument("--device", default="mps")
    common.add_argument("--dry-run", action="store_true", help="do not move the arm, only show the flow")
    common.add_argument(
        "--lang",
        choices=["en", "tr"],
        default=i18n.LANG,
        help="terminal message language (default: en, or $XOX_LANG)",
    )
    sub = p.add_subparsers(dest="command", required=True)
    m = sub.add_parser("move", parents=[common], help="a single move without the agent")
    m.add_argument("cell", choices=CELLS, metavar="cell", help='e.g. "top left"')
    m.set_defaults(run=move_command)
    g = sub.add_parser("play", parents=[common], help="Claude is X, you are O")
    g.add_argument("--claude", default="claude-opus-5-5", help="Claude model name")
    g.add_argument("--first", choices=["x", "o"], default="x", help="who starts")
    g.add_argument("--confirm", action="store_true", help="ask at every step instead of camera detection")
    add_dashboard_flags(g)
    g.set_defaults(run=play_command)
    e = sub.add_parser("eval", parents=[common], help="benchmark the arm cell by cell, judged by the top camera")
    e.add_argument("--trials", type=positive, default=3, help="moves per cell (default: 3)")
    e.add_argument(
        "--cells",
        nargs="+",
        choices=CELLS,
        metavar="CELL",
        help='only these cells, e.g. --cells "top left" "top right"',
    )
    e.add_argument("--seed", type=int, default=0, help="seed of the shuffled move order (default: 0)")
    e.add_argument(
        "--report", type=Path, metavar="RUN", help="only print the table of an earlier run (folder or file)"
    )
    add_dashboard_flags(e)
    e.set_defaults(run=eval_command)
    b = sub.add_parser("board", parents=[common], help="read the board from the camera, do not move the arm")
    b.add_argument("--claude", default="claude-opus-5-5", help="Claude model name")
    b.add_argument("--image", type=Path, help="read this image file instead of the camera")
    b.add_argument("--save", type=Path, help="write the cropped image sent to Claude here")
    b.set_defaults(run=board_command)
    args = p.parse_args()
    i18n.set_language(args.lang)
    needs_arm = not getattr(args, "report", None)  # printing an old table needs neither the arm nor its venv
    if needs_arm and importlib.util.find_spec("strands_robots") is None:
        sys.exit(t("wrong_venv", python=ROOT / ".venv-strands" / "bin" / "python"))
    args.run(args)


if __name__ == "__main__":
    main()
