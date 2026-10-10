"""Run the dashboard on its own.

    python -m xox.dashboard --demo [--port N] [--frames DIR ...] [--speed S]

``--demo`` plays a scripted fake game with recorded (or placeholder) camera
frames. Without it the dashboard starts on an empty, idle game state.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading

from ..state import GameState
from .demo import Demo, load_clips
from .server import start_dashboard


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m xox.dashboard",
        description="Local dashboard for the SO-101 tic-tac-toe game.",
    )
    parser.add_argument("--demo", action="store_true", help="play a scripted fake game")
    parser.add_argument("--host", default="127.0.0.1", help="address to bind (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="port to bind (default 8765, 0 = any free)")
    parser.add_argument(
        "--frames", action="append", metavar="DIR",
        help="folder with top_NNN.jpg / wrist_NNN.jpg of one arm move; repeat for more moves",
    )
    parser.add_argument("--speed", type=float, default=1.0, help="demo speed multiplier (default 1)")
    args = parser.parse_args(argv)

    state = GameState()
    try:
        server = start_dashboard(state, host=args.host, port=args.port)
    except OSError as exc:
        print(f"Cannot listen on {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 2

    demo = None
    if args.demo:
        clips = load_clips(args.frames)
        if clips:
            print(f"Demo: replaying {len(clips)} recorded move(s).")
        else:
            print("Demo: no recorded frames found, drawing placeholder frames.")
        demo = Demo(state, clips, speed=args.speed).start()
    else:
        state.add_event("game", "Dashboard started without a game. Use --demo for a fake one.")

    done = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: done.set())
    print(f"Dashboard: {server.url}  (Ctrl+C to quit)", flush=True)
    try:
        while not done.wait(0.5):
            pass
    finally:
        if demo is not None:
            demo.close()
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
