"""The `eval` command: a small per-cell benchmark on the arm, judged locally from the top camera.

No Claude and no API key. The arm is asked for every cell `--trials` times in a shuffled order; after
each move the camera measures where the red X landed (`xox.vision.landing`) against a reference frame
of the empty board taken at the start. The operator only moves the X from the board back to the pick slot.

Everything of one run goes to `outputs/eval/<time>/`:

    results.jsonl             one line per move, appended as the run goes (fields: `FIELDS` below)
    summary.json              settings, thresholds, hits per cell, field descriptions; rewritten after every move
    reference.jpg             the empty board the run started from
    before_NN.jpg, after_NN.jpg   the top frame before and after move NN
    moveNN_<cell>/            the arm's own log of the move (steps.jsonl, top/wrist frames)
    events.jsonl              what the terminal and the dashboard showed
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from . import ROOT, i18n
from .arm import Arm
from .board import CELLS
from .game import session, stop_check
from .i18n import t
from .vision import (
    BLOB_JOIN,
    BOARD_BOX,
    GRIPPER_PIXELS,
    GRIPPER_REACH,
    MIN_PIECE_PIXELS,
    REFERENCE_MARGIN,
    SLOT_BOX,
    SLOT_THRESHOLD,
    STOP,
    crop_board,
    flip,
    landing,
    pieces_on_board,
    slot_has_x,
    still_frame,
)

ARM_JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")
# "The arm left the rest pose": the command of any arm joint is more than this far from the pose the move
# started in (the same rule as START_DEG in benchmarks/extract.py).
LEAVE_DEG = 10.0

MEANS = ("dx_cell", "dy_cell", "offset_cell", "leave_rest_s", "move_s")  # averaged per cell in summary.json

# What the fields of a line in results.jsonl mean (copied into summary.json).
FIELDS = {
    "trial": "number of the move in this run, from 1",
    "cell": "the cell the arm was asked for",
    "time": "local time the move was judged",
    "hit": "true if the X landed in the asked cell",
    "landed": "cell that holds the centre of the new red, 'none' (no piece seen) or 'several' (more than one piece)",
    "ended": "'returned' if the move ended with the arm back in the rest pose, 'timeout' if the time ran out",
    "dx_px": "centre of the X minus centre of the asked cell, pixels, positive to the robot's right",
    "dy_px": "the same along the other axis, positive towards the robot",
    "dx_cell": "dx_px as a fraction of the cell width",
    "dy_cell": "dy_px as a fraction of the cell width",
    "offset_cell": "distance of the X from the centre of the asked cell, in cell widths",
    "x": "centre of the X in the top frame rotated 180 degrees (the robot's view), pixels",
    "y": "the same, vertical",
    "red_pixels": "new red pixels of the piece(s) counted",
    "new_red_pixels": "all new red pixels in the board box, counted or not",
    "largest_other_group": "largest group of new red that was too small to be a piece (usually the gripper)",
    "pieces": "groups of new red large enough to be a piece",
    "near_gripper": "true if the piece is within 40 px of where the gripper rested in the reference: centre less exact",
    "touches_edge": "true if the piece reaches the edge of the board box: part may lie outside, centre less exact",
    "leave_rest_s": "seconds from the first command until the commanded pose was more than 10 degrees from rest",
    "move_s": "seconds the policy ran (the first move of a run includes connecting to the arm)",
    "log_s": "seconds from the first to the last command",
    "max_jump_deg": "largest change of a commanded arm joint between two consecutive steps, degrees",
    "max_jump_joint": "the joint of that change",
    "commands": "number of commands sent",
    "start_from_rest_deg": "how far the arm was from the first move's start pose when this move started, degrees",
    "before": "top frame before the move",
    "after": "top frame the landing was measured on",
    "log": "the arm's step log of the move",
}


def plan(cells: list[str], trials: int, seed: int) -> list[str]:
    """Every cell `trials` times, shuffled with `seed` so that the cells interleave."""
    order = [cell for cell in CELLS if cell in cells for _ in range(trials)]
    random.Random(seed).shuffle(order)
    return order


def step_metrics(path: Path | None) -> dict:
    """Timing and smoothness of one move from its steps.jsonl (blank if there is no usable log)."""
    out = {"leave_rest_s": None, "log_s": None, "max_jump_deg": None, "max_jump_joint": None, "commands": 0}
    out["start_pose"] = None

    def pose(values: dict) -> list[float]:
        return [float(values[f"{joint}.pos"]) for joint in ARM_JOINTS]

    try:
        rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
        start = pose(next(row["state"] for row in rows if "state" in row))
        commands = [row for row in rows if "command" in row]
        sent = np.array([pose(row["command"]) for row in commands])
        at = np.array([row["t"] for row in commands]) - commands[0]["t"]
    except (OSError, TypeError, ValueError, KeyError, IndexError, StopIteration):
        return out
    away = np.abs(sent - np.array(start)).max(axis=1)
    out |= {"start_pose": start, "commands": len(sent), "log_s": round(float(at[-1]), 2)}
    if (away > LEAVE_DEG).any():
        out["leave_rest_s"] = round(float(at[np.argmax(away > LEAVE_DEG)]), 2)
    if len(sent) > 1:
        change = np.abs(np.diff(sent, axis=0))
        out["max_jump_deg"] = round(float(change.max()), 2)
        out["max_jump_joint"] = ARM_JOINTS[int(change.max(axis=0).argmax())]
    return out


def table(results: list[dict], cells: list[str]) -> str:
    """Hits/moves per cell, drawn like the board."""
    lines = [i18n.MESSAGES["board_far_side"][i18n.LANG], "         ┌───────┬───────┬───────┐"]
    for r in range(3):
        texts = []
        for cell in CELLS[r * 3 : r * 3 + 3]:
            rows = [row for row in results if row["cell"] == cell]
            texts.append(f"{sum(bool(row['hit']) for row in rows)}/{len(rows)}" if rows or cell in cells else "-")
        lines.append("         │" + "│".join(f"{text:^7}" for text in texts) + "│")
        lines.append("         ├───────┼───────┼───────┤" if r < 2 else "         └───────┴───────┴───────┘")
    lines.append("                   ROBOT")
    return "\n".join(lines)


def summary(meta: dict, results: list[dict]) -> dict:
    """The run in one JSON object: settings, totals and one entry per cell."""

    def mean(rows: list[dict], key: str):
        values = [row[key] for row in rows if row.get(key) is not None]
        return round(sum(values) / len(values), 3) if values else None

    per_cell = {}
    for cell in meta["cells"]:
        rows = [row for row in results if row["cell"] == cell]
        per_cell[cell] = {
            "moves": len(rows),
            "hits": sum(bool(row["hit"]) for row in rows),
            "none": sum(row["landed"] == "none" for row in rows),
            "several": sum(row["landed"] == "several" for row in rows),
            "timeouts": sum(row["ended"] == "timeout" for row in rows),
            **{f"mean_{key}": mean(rows, key) for key in MEANS},
        }
    return {
        **meta,
        "played": len(results),
        "hits": sum(bool(row["hit"]) for row in results),
        "finished": len(results) == meta["planned"],
        "per_cell": per_cell,
        "fields": FIELDS,
    }


def print_table(results: list[dict], cells: list[str], planned: int) -> None:
    print("\n" + t("eval_table"))
    print(table(results, cells))
    print(t("eval_total", hits=sum(bool(row["hit"]) for row in results), done=len(results), total=planned))


def report(path: Path) -> None:
    """Prints the table of an earlier run again, from its folder or its results.jsonl."""
    path = path / "results.jsonl" if path.is_dir() else path
    try:
        results = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    except OSError:
        results = []
    if not results:
        sys.exit(t("eval_no_results", path=path))
    try:
        meta = json.loads(path.with_name("summary.json").read_text())
        cells, planned = meta["cells"], meta["planned"]
    except (OSError, ValueError, KeyError):
        cells, planned = sorted({row["cell"] for row in results}, key=CELLS.index), len(results)
    print_table(results, cells, planned)


def take_reference(arm: Arm, folder: Path) -> np.ndarray:
    """The flipped top frame of the empty board the run compares against; refuses a board with red on it."""
    input(t("eval_clear_board"))
    stop_check()
    print(t("eval_reference"))
    raw = still_frame(arm)
    reference = flip(raw)
    pieces = pieces_on_board(reference)
    if pieces:
        sys.exit(t("eval_not_empty", cells=", ".join(pieces)))
    folder.mkdir(parents=True, exist_ok=True)
    Image.fromarray(raw).save(folder / "reference.jpg", quality=95)
    return reference


def wait_until_ready(arm: Arm, reference: np.ndarray, journal):
    """Waits, camera only, until the board is empty again, the slot has an X and nothing moves; returns that frame."""
    said = None
    while True:
        raw = still_frame(arm)
        now = flip(raw)
        if landing(now, reference)["landed"] != "none":
            hint = t("eval_take_x", where=", ".join(pieces_on_board(now)) or "?")
        elif not slot_has_x(now):
            hint = t("slot_empty")
        else:
            return raw
        if hint != said:
            journal.say("vision", hint)
            said = hint


def describe(n: int, total: int, row: dict) -> str:
    """The line printed for one move."""

    def number(value, digits: int) -> str:
        return "?" if value is None else f"{value:.{digits}f}"

    if row["landed"] == "none":
        where = t("eval_none", pixels=row["new_red_pixels"])
    elif row["landed"] == "several":
        where = t("eval_several", count=row["pieces"])
    else:
        where = t(
            "eval_landed",
            landed=row["landed"],
            cell=row["cell"],
            dx=float(round(row["dx_px"])),  # rounded here so that a small negative does not print as "-0"
            dy=float(round(row["dy_px"])),
            fx=round(row["dx_cell"], 2) + 0.0,
            fy=round(row["dy_cell"], 2) + 0.0,
            pixels=row["red_pixels"],
        )
        where += t("eval_near_gripper") if row["near_gripper"] else t("eval_at_edge") if row["touches_edge"] else ""
    timing = t(
        "eval_timing",
        leave=number(row["leave_rest_s"], 1),
        seconds=number(row["move_s"], 0),
        jump=number(row["max_jump_deg"], 1),
        ended={"returned": t("eval_returned"), "timeout": t("eval_timeout")}.get(row["ended"], "?"),
    )
    return f"[{n}/{total}] {row['cell']}: {t('hit') if row['hit'] else t('missed')}; {where}; {timing}"


def run_trial(arm: Arm, journal, folder: Path, reference: np.ndarray, n: int, total: int, cell: str, home: list):
    """One move: wait for the operator, play, measure. Returns the results line, or None if the arm did not run."""
    journal.phase("waiting_for_x_in_slot", turn="x", target_cell=cell)
    before = wait_until_ready(arm, reference, journal)
    Image.fromarray(before).save(folder / f"before_{n:02d}.jpg", quality=90)
    journal.say("robot", t("eval_start", n=n, total=total, cell=cell))
    if STOP.wait(2.0):
        raise KeyboardInterrupt
    journal.phase("arm_moving", target_cell=cell, board=[" "] * 9)
    ran, note = arm.play(cell, confirm=False)
    if not ran and not STOP.is_set():  # the arm would not move (no connection, ...): the run ends here
        journal.say("error", t("move_not_played", reason=note))
        return None
    journal.say("robot", note)
    stop_check()  # a stopped move is not a result
    journal.arm_ran(cell, arm.last_seconds)
    journal.phase("verifying")
    after = still_frame(arm, duration=0.5)  # short: the operator may reach for the X as soon as the arm is back
    Image.fromarray(after).save(folder / f"after_{n:02d}.jpg", quality=90)
    found = landing(flip(after), reference, cell)
    steps = step_metrics(arm.last_log)
    start_pose = steps.pop("start_pose")
    if start_pose is not None and not home:
        home.extend(start_pose)
    row = {
        "trial": n,
        "cell": cell,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "hit": bool(found["hit"]),
        "landed": found["landed"],
        "ended": {True: "returned", False: "timeout"}.get(arm.last_returned),
        **{key: found[key] for key in ("dx_px", "dy_px", "dx_cell", "dy_cell", "offset_cell", "x", "y")},
        **{key: found[key] for key in ("red_pixels", "new_red_pixels", "largest_other_group", "pieces")},
        "near_gripper": found["near_gripper"],
        "touches_edge": found["touches_edge"],
        "leave_rest_s": steps["leave_rest_s"],
        "move_s": None if arm.last_seconds is None else round(arm.last_seconds, 2),
        "log_s": steps["log_s"],
        "max_jump_deg": steps["max_jump_deg"],
        "max_jump_joint": steps["max_jump_joint"],
        "commands": steps["commands"],
        "start_from_rest_deg": (
            None if start_pose is None else round(max(abs(a - b) for a, b in zip(start_pose, home)), 2)
        ),
        "before": f"before_{n:02d}.jpg",
        "after": f"after_{n:02d}.jpg",
        "log": None if arm.last_log is None else str(Path(arm.last_log).relative_to(folder)),
    }
    board = [" "] * 9
    if found["landed"] in CELLS:
        board[CELLS.index(found["landed"])] = "X"
    journal.frame("board", crop_board(after))
    journal.move("X", cell, board, hit=row["hit"])
    line = describe(n, total, row)
    journal.say("vision", line)
    journal.phase("verifying", message=line)
    return row


def eval_command(args: argparse.Namespace) -> None:
    if args.report:
        report(args.report)
        return
    cells = [cell for cell in CELLS if cell in (args.cells or CELLS)]
    order = plan(cells, args.trials, args.seed)
    print(t("eval_plan", total=len(order), trials=args.trials, cells=len(cells), seed=args.seed))
    if args.dry_run:
        print(t("eval_order", order=", ".join(order)))
        print(t("eval_rules"))
        print(t("dry_run"))
        return

    arm = Arm(args)
    folder = ROOT / "outputs" / "eval" / arm.folder.name
    arm.folder = folder  # the arm's per-move logs go next to the results
    meta = {
        "command": "eval",
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": args.model,
        "duration": args.duration,
        "trials": args.trials,
        "seed": args.seed,
        "cells": cells,
        "order": order,
        "planned": len(order),
        "thresholds": {
            "min_piece_pixels": MIN_PIECE_PIXELS,
            "reference_margin_px": REFERENCE_MARGIN,
            "blob_join_px": BLOB_JOIN,
            "gripper_pixels": GRIPPER_PIXELS,
            "gripper_reach_px": GRIPPER_REACH,
            "slot_threshold": SLOT_THRESHOLD,
            "leave_rest_deg": LEAVE_DEG,
        },
        "board_box": list(BOARD_BOX),
        "slot_box": list(SLOT_BOX),
        "cell_px": (BOARD_BOX[2] - BOARD_BOX[0]) / 3,
        "frame": "boxes and x/y are in the top frame rotated 180 degrees (the robot's view, top row far from the arm)",
    }
    results, home, state = [], [], {"reference": False, "shown": False}

    def save_summary() -> None:
        (folder / "summary.json").write_text(json.dumps(summary(meta, results), indent=2, ensure_ascii=False) + "\n")

    def show() -> None:
        state["shown"] = True
        print_table(results, cells, len(order))
        print(t("eval_saved", folder=folder))

    try:
        with session(args, arm, None) as journal:
            reference = take_reference(arm, folder)
            state["reference"] = True
            journal.path = folder / "events.jsonl"  # only a run that got its reference leaves a folder
            save_summary()
            print(t("eval_rules"))
            for n, cell in enumerate(order, 1):
                stop_check()
                row = run_trial(arm, journal, folder, reference, n, len(order), cell, home)
                if row is None:
                    break
                results.append(row)
                with (folder / "results.jsonl").open("a", encoding="utf-8") as file:
                    file.write(json.dumps(row, ensure_ascii=False) + "\n")
                save_summary()
            hits = sum(row["hit"] for row in results)
            journal.phase(
                "game_over" if len(results) == len(order) else "stopped",
                turn=None,
                target_cell=None,
                message=t("eval_total", hits=hits, done=len(results), total=len(order)),
            )
            show()
    finally:
        if state["reference"] and not state["shown"]:  # stopped: the table still comes, after the arm is closed
            save_summary()
            show()
