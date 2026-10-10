"""The `play` command: Claude is X and picks the cell, the arm places it, the human answers with an O.

`session` is the frame around any run on the arm (dashboard, Stop, Ctrl+C, closing); `eval` uses it too.

The loop also keeps a `GameState` up to date for the dashboard (unless `--no-dashboard` or
`--dry-run`) and writes every event to `outputs/strands_logs/<time>/game.jsonl`.
"""

import argparse
import contextlib
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

from . import ROOT, load_env
from .arm import Arm
from .board import CELLS, draw, task_sentence, winner
from .i18n import t, yes
from .vision import STOP, Console, verify_x, wait_for_o, wait_for_slot

SYSTEM_PROMPT = """You play tic-tac-toe as X against a human who plays O. A robot arm places your X.

Cells are named "<row> <column>" with rows top, middle, bottom and columns left, center, right.
On your turn you get the current board. Pick the best empty cell and call place_x exactly once
with that cell name. Win if you can, otherwise block the human's winning move.
After the tool returns, reply with one short sentence. Do not call the tool again in the same turn."""


class Journal(Console):
    """What happens in a game, sent to the dashboard's state and appended to `game.jsonl`.

    Both are optional: without a state and a path this is a plain `Console` (the dry run).
    Safe to call from any thread; the tool runs in another thread than the game loop.
    """

    def __init__(self, state=None, path: Path | None = None):
        self.state = state
        self.path = path
        self._file = None
        self._lock = threading.Lock()
        self._pending_x = None  # index of the X move whose hit is not known yet

    def write(self, kind: str, text: str, **extra) -> None:
        """Appends one line to `game.jsonl`; `extra` carries the board when it changes."""
        line = {"t": time.time(), "kind": kind, "text": text, **extra}
        with self._lock:
            if self.path is None:  # no log (dry run), or the game is over
                return
            if self._file is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._file = self.path.open("a", encoding="utf-8")
            self._file.write(json.dumps(line, ensure_ascii=False) + "\n")
            self._file.flush()

    def note(self, kind: str, text: str, **extra) -> None:
        if self.state is not None:
            self.state.add_event(kind, text)
        self.write(kind, text, **extra)

    def phase(self, phase: str, **fields) -> None:
        """Sets the phase and any other `GameState` field (turn, target_cell, board, message, winner)."""
        if self.state is not None:
            self.state.update(phase=phase, **fields)
        self.write("phase", phase, **fields)

    def frame(self, name: str, image) -> None:
        if self.state is not None:
            self.state.set_frame(name, image)

    def message(self, text: str) -> None:
        """Claude's closing sentence of the turn."""
        if self.state is not None:
            self.state.update(message=text)
        self.note("claude", text)

    def arm_ran(self, cell: str, seconds: float | None) -> None:
        """The arm finished its move: an X move appears, its hit still unknown."""
        if self.state is not None:
            self._pending_x = self.state.add_move(cell, hit=None, seconds=seconds, player="X")

    def move(self, player: str, cell: str, board: list[str], hit: bool | None = None) -> None:
        """A move was accepted onto the board."""
        if self.state is not None:
            if player == "X" and self._pending_x is not None:
                self.state.update_move(self._pending_x, hit=hit)
            else:
                self.state.add_move(cell, hit=hit, player=player)
            self._pending_x = None
            self.state.update(board=board, target_cell=None)
        extra = {} if hit is None else {"hit": bool(hit)}
        self.write("move", f"{player} {cell}", board=list(board), **extra)

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None
            self.path = None


class CameraPump:
    """A daemon thread that publishes the `top` and `wrist` frames to the dashboard about 10 times a second.

    It only ever asks `Arm.peek`, which hands out a frame when one can be had without disturbing the
    robot and None otherwise; a failed read skips that frame. It never touches the serial bus.
    """

    def __init__(self, arm: Arm, state, names=("top", "wrist"), interval: float = 0.1):
        self.arm, self.state, self.names, self.interval = arm, state, names, interval
        self._quit = threading.Event()
        self._thread = None

    def start(self) -> "CameraPump":
        self._thread = threading.Thread(target=self._run, name="xox-camera-pump", daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        wait = 0.0
        while not self._quit.wait(wait):
            started = time.monotonic()
            for name in self.names:
                try:
                    image = self.arm.peek(name)
                    if image is not None:
                        self.state.set_frame(name, image)
                except Exception:  # noqa: BLE001 - one bad frame is only a skipped frame
                    pass
            wait = max(0.01, self.interval - (time.monotonic() - started))

    def stop(self, timeout: float = 10.0) -> None:
        """Ends the thread and waits for it (it may be in the middle of opening a camera)."""
        self._quit.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None


def start_dashboard(args: argparse.Namespace):
    """Starts the dashboard for a real game; returns (state, server), or (None, None) without one."""
    if args.dry_run or args.no_dashboard:
        return None, None
    from .dashboard import start_dashboard as serve
    from .state import GameState

    state = GameState()
    try:
        server = serve(state, port=args.dashboard_port)
    except OSError as error:
        print(t("dashboard_failed", port=args.dashboard_port, error=error))
        return None, None
    print(t("dashboard_url", url=server.url))
    if not args.no_open:
        import webbrowser

        try:
            webbrowser.open(server.url)
        except Exception:  # noqa: BLE001 - the URL is printed above
            pass
    return state, server


@contextlib.contextmanager
def session(args: argparse.Namespace, arm: Arm, log: Path | None):
    """Everything around a run on the arm (`play`, `eval`): yields the `Journal` to report through.

    Starts the dashboard (unless `--dry-run` / `--no-dashboard`) with its camera pump and Stop button,
    makes Ctrl+C stop the arm, and on the way out closes the arm (the operator gets the "torque will be
    cut" prompt) and shuts the pump and the server down. A Ctrl+C or Stop inside the block ends it
    without an error: the code after the `with` still runs.
    """
    state, server = start_dashboard(args)
    journal = Journal(state, log)
    pump = None
    if state is not None:

        def stop_pressed() -> None:
            # Runs in the dashboard's thread. The loop notices STOP and ends as it does on Ctrl+C.
            STOP.set()
            journal.write("stop", "Stop requested from the dashboard")
            if arm.robot is not None:
                arm.robot.stop_task()

        state.on_stop = stop_pressed
        pump = CameraPump(arm, state).start()
        arm.before_cleanup = pump.stop

    def on_sigint(signum, frame) -> None:
        # Strands absorbs the first Ctrl+C while a tool is running, and the arm would finish its move.
        # Stop the arm here, in the signal handler, before anything else sees the interrupt.
        STOP.set()
        if arm.robot is not None:
            arm.robot.stop_task()
        raise KeyboardInterrupt

    previous_sigint = signal.signal(signal.SIGINT, on_sigint)
    try:
        try:
            yield journal
        except KeyboardInterrupt:
            # Usually the SIGINT handler above has already stopped the arm; repeat it for the Stop button path.
            STOP.set()
            if arm.robot is not None:
                arm.robot.stop_task()
            pressed = state is not None and state.stop_requested
            journal.say("stop", t("stop_pressed") if pressed else t("ctrl_c"))
            journal.phase("stopped", turn=None, target_cell=None)
        finally:
            arm.close()
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        if pump is not None:
            pump.stop()
        journal.close()
        if server is not None:
            server.stop()


def stop_check() -> None:
    """Leaves the loop the way Ctrl+C does once STOP is set (the dashboard's Stop only sets the flag)."""
    if STOP.is_set():
        raise KeyboardInterrupt


def play_command(args: argparse.Namespace) -> None:
    from strands import Agent, tool
    from strands.models.anthropic import AnthropicModel

    load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(t("no_api_key", path=ROOT / ".env"))

    arm = Arm(args)
    automatic = not args.confirm and not args.dry_run  # the camera detects, no questions are asked
    board = [" "] * 9
    turn = {"played": None}
    hits = []

    with session(args, arm, None if args.dry_run else arm.folder / "game.jsonl") as journal:
        @tool
        def place_x(cell: str) -> str:
            """Place your X in one empty cell of the board. The robot arm does the move.

            Args:
                cell: Cell name, "<row> <column>", e.g. "top left" or "middle center".
            """
            cell = cell.strip().lower()
            if turn["played"] is not None:
                return f"Refused: you already played {turn['played']} this turn."
            if cell not in CELLS:
                return f"Refused: unknown cell. Use one of: {', '.join(CELLS)}."
            i = CELLS.index(cell)
            if board[i] != " ":
                return f"Refused: {cell} is taken. Empty cells: {', '.join(empty())}."
            journal.note("claude", t("claude_picked", cell=cell))
            try:
                return play_x(i, cell)
            except KeyboardInterrupt:
                if not STOP.is_set():
                    raise
                # Stopped while this thread was waiting on the camera: let the agent call return.
                turn["played"] = "cancelled"
                return f"The move was not executed: {t('stopped')}"

        def play_x(i: int, cell: str) -> str:
            landed = None
            if automatic:
                journal.phase("waiting_for_x_in_slot", target_cell=cell)
                wait_for_slot(arm, journal)
                journal.say("robot", t("arm_plays_soon", cell=cell))
                if STOP.wait(2.0):
                    raise KeyboardInterrupt
            journal.phase("arm_moving", target_cell=cell)
            journal.note("robot", t("task_sentence", task=task_sentence(cell)).strip())
            ran, note = arm.play(cell, confirm=not automatic)
            journal.say("robot", note)
            if not ran:
                turn["played"] = "cancelled"
                return f"The move was not executed: {note}"
            journal.arm_ran(cell, arm.last_seconds)
            if automatic:
                journal.phase("verifying")
                landed = verify_x(arm, i, cell, args.claude, journal)
                hits.append((cell, landed))
            elif not args.dry_run:
                journal.phase("verifying")
                landed = yes(t("x_landed", cell=cell))
                hits.append((cell, landed))
                journal.note("human", t("operator_says", cell=cell, verdict=t("hit") if landed else t("missed")))
                if not landed:
                    input(t("put_x_by_hand", cell=cell))
                    journal.note("human", t("x_fixed_by_hand", cell=cell))
            board[i] = "X"
            turn["played"] = cell
            journal.move("X", cell, board, hit=landed)
            return f"X is now in {cell}."

        def empty() -> list[str]:
            return [c for c, v in zip(CELLS, board) if v == " "]

        agent = Agent(
            model=AnthropicModel(model_id=args.claude, max_tokens=1024),
            tools=[place_x],
            system_prompt=SYSTEM_PROMPT,
        )

        to_move = args.first
        while winner(board) is None and empty():
            stop_check()
            print("\n" + draw(board))
            if to_move == "x":
                turn["played"] = None
                journal.phase("thinking", turn="x", target_cell=None)
                try:
                    # Claude always gets the English drawing, whatever the terminal language is.
                    result = agent(
                        f"Board (X is you):\n{draw(board, lang='en')}\n"
                        f"Empty cells: {', '.join(empty())}\nYour move."
                    )
                except Exception as error:  # noqa: BLE001 - on an API error close the arm properly and quit
                    journal.say("error", t("claude_failed", error=str(error)[:300]))
                    break
                print()
                stop_check()
                if result is not None and str(result).strip():
                    journal.message(str(result).strip())
                if turn["played"] is None:
                    journal.say("error", t("claude_no_move"))
                    break
                if turn["played"] == "cancelled":
                    journal.say("error", t("move_cancelled"))
                    break
            else:
                journal.phase("waiting_for_o", turn="o", target_cell=None)
                if automatic:
                    cell = wait_for_o(arm, board, args.claude, journal)
                else:
                    cell = input(t("your_move")).strip().lower()
                stop_check()
                if cell not in empty():
                    print(t("not_allowed", cells=", ".join(empty())))
                    continue
                if not automatic:
                    journal.note("human", t("o_typed", cell=cell))
                board[CELLS.index(cell)] = "O"
                journal.move("O", cell, board)
            to_move = "o" if to_move == "x" else "x"
        print("\n" + draw(board))
        if winner(board):
            journal.phase("game_over", winner=winner(board), turn=None, target_cell=None)
            journal.say("game", t("winner", winner=winner(board)))
        elif not empty():
            journal.phase("game_over", winner="draw", turn=None, target_cell=None)
            journal.say("game", t("draw"))
        else:  # the loop was left early: a Claude error or a cancelled move
            journal.phase("stopped", turn=None, target_cell=None)
        if hits:
            journal.say("game", t("arm_accuracy", hits=sum(ok for _, ok in hits), total=len(hits)))
            for cell, ok in hits:
                print(f"  {cell}: {t('hit') if ok else t('missed')}")
