"""Raw logs and dataset -> small derived tables in `benchmarks/data/`.

Reads only files that already exist on disk. It never touches the arm, a camera, a serial port, `.env`,
the network or a model. The raw material lives in two git-ignored folders of the repo, `outputs/` and
`data/`, so this script is the only step that needs them; `make_charts.py` works from `benchmarks/data/`
alone.

Run from the repo root, in a throwaway environment (nothing is installed into the repo's virtualenvs):

    uv run --no-project --with matplotlib --with pandas --with pyarrow --with numpy --with pillow \
        python benchmarks/extract.py

`--raw-root PATH` points at the checkout that holds `outputs/` and `data/` when the script is run from
another worktree (default: the repo this file is in). `docs/rounds/round1.md` is always read from the
repo this file is in.

Every definition used for a number on the benchmark pages is a constant or a function in this file.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = HERE / "data"

JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
ARM = slice(0, 5)  # the five arm joints, in degrees; the gripper is logged as 0-100 % of its range
LIFT_ELBOW = slice(1, 3)  # shoulder_lift and elbow_flex: the joints the game script watches

FPS = 30  # control rate of the policy loop and frame rate of the dataset
CHUNK = 50  # SmolVLA action chunk: 50 steps
JUMP_DEG = 6.0  # a per-step change of the commanded pose above this is counted as a jump
PAUSE_S = 0.2  # a gap between two commands above this is counted as a pause (a normal step is 0.033 s)

# "The arm starts": the commanded pose of any arm joint is more than this far from the rest pose.
START_DEG = 10.0
# "The arm is back": the rule of scripts/strands_game.py (Arm.FAR, Arm.NEAR, Arm.NEAR_STEPS), applied to
# shoulder_lift and elbow_flex of the commanded pose.
FAR_DEG = 20.0
NEAR_DEG = 8.0
NEAR_STEPS = 45
GRIPPER_OPEN = 8.0  # % of range; the gripper counts as open above this

# "First motion" in a demonstration: an arm joint is more than this far from its value in the first frame.
FIRST_MOTION_DEG = 3.0

# Local detectors, reimplemented from scripts/strands_game.py (same boxes, same thresholds).
BOARD_BOX = (160, 40, 478, 358)  # the grid in the 180° rotated top frame (left, top, right, bottom)
SLOT_BOX = (485, 250, 560, 325)  # the pick slot in the same frame
SLOT_THRESHOLD = 0.015
CHANGE_THRESHOLD = 8.0
ROWS, COLS = ("top", "middle", "bottom"), ("left", "center", "right")
CELLS = [f"{r} {c}" for r in ROWS for c in COLS]

# Folder and file names of the logs on disk. They were written before the repo switched to English;
# the current scripts write `rollout_logs/`, `strands_logs/`, `steps.jsonl`, `state`, `command`, `moveNN_`.
ROLLOUT_DIR = "outputs/rollout_gunluk"
STRANDS_DIR = "outputs/strands_gunluk"
CAPTURE_DIR = "outputs/canli"
STEPS_FILE = "adimlar.jsonl"
STATE_KEYS, COMMAND_KEYS = ("durum", "state"), ("komut", "command")
DATASET_DIR = "data/tic-tac-toe-so101-x-round1-clean-v1"

# The logged runs. `counted` and `landed` are not computed: `counted` says whether docs/writeup.md counts
# the move among the ten completed ones, `landed` how the placement is known ("frame": the X is visible in
# the target cell in a later top frame on disk, checked by eye; "notes": only the project notes say so,
# because the log ends while the gripper is still over the cell).
ARM_RUNS = [
    # folder, id, short label, inference setting
    ("20261010-211122", "run2", "run 2", "queued"),
    ("20261010-211639", "run3", "run 3", "queued"),
    ("20261010-212220", "run4", "run 4", "sync"),
]
MOVES = [
    # id, kind, folder (relative to the raw root), cell, inference, counted, landed, note
    ("run2", "direct", f"{ROLLOUT_DIR}/20261010-211122", "middle center", "queued", False, "", "20 s limit: cut off before release"),
    ("run3", "direct", f"{ROLLOUT_DIR}/20261010-211639", "middle center", "queued", True, "frame", "60 s limit; the arm idles at rest after the move"),
    ("run4", "direct", f"{ROLLOUT_DIR}/20261010-212220", "middle center", "sync", True, "frame", ""),
    ("accidental", "accidental", f"{STRANDS_DIR}/20261010-212846/hamle01_middle_center", "middle center", "sync", False, "", "accidental run: an X was already in the target cell, the slot was empty"),
    ("move_top_left", "move", f"{STRANDS_DIR}/20261010-213748/hamle01_top_left", "top left", "sync", True, "frame", ""),
    ("move_bottom_left", "move", f"{STRANDS_DIR}/20261010-214112/hamle01_bottom_left", "bottom left", "sync", True, "frame", ""),
    ("empty_slot", "empty slot", f"{STRANDS_DIR}/20261010-214728/hamle01_bottom_left", "bottom left", "sync", False, "", "the pick slot was empty; the arm did not move"),
    ("game1_move1", "game 1", f"{STRANDS_DIR}/20261010-214926/hamle01_middle_center", "middle center", "sync", True, "frame", ""),
    ("game1_move2", "game 1", f"{STRANDS_DIR}/20261010-214926/hamle02_bottom_right", "bottom right", "sync", True, "frame", ""),
    ("game1_move3", "game 1", f"{STRANDS_DIR}/20261010-214926/hamle03_middle_left", "middle left", "sync", True, "notes", "the log ends at the release; the return is not logged"),
    ("game2_move1", "game 2", f"{STRANDS_DIR}/20261010-225839/hamle01_middle_center", "middle center", "sync", True, "frame", ""),
    ("game2_move2", "game 2", f"{STRANDS_DIR}/20261010-225839/hamle02_top_right", "top right", "sync", True, "frame", ""),
    ("game2_move3", "game 2", f"{STRANDS_DIR}/20261010-225839/hamle03_middle_left", "middle left", "sync", True, "notes", "the log ends at the release; the return is not logged"),
]

# Frame pairs for the change detector: the first top frame of consecutive moves of a game. Between the two
# frames the arm placed its X (the earlier move's cell) and the human placed an O. The O cells and the two
# remarks were read off the frames by eye.
GAME_PAIRS = [
    # pair id, earlier move folder, later move folder, cell of the new X, cell of the new O
    ("game1_1to2", "20261010-214926/hamle01_middle_center", "20261010-214926/hamle02_bottom_right", "middle center", "top left"),
    ("game1_2to3", "20261010-214926/hamle02_bottom_right", "20261010-214926/hamle03_middle_left", "bottom right", "bottom left"),
    ("game2_1to2", "20261010-225839/hamle01_middle_center", "20261010-225839/hamle02_top_right", "middle center", "bottom left"),
    ("game2_2to3", "20261010-225839/hamle02_top_right", "20261010-225839/hamle03_middle_left", "top right", "top left"),
]
GRIPPER_CELLS = ("bottom center", "bottom right")  # the resting gripper covers part of these two cells
MOVED_PIECES = {("game1_2to3", "middle center")}  # an X already on the board was straightened by hand

# Which recording day a block of five episodes belongs to (docs/plan.md, "Where we are").
BLOCK_DAY = {1: "2026-10-06", 2: "2026-10-06", 3: "2026-10-06", 4: "2026-10-06", 5: "2026-10-06",
             6: "2026-10-10", 7: "2026-10-10", 8: "2026-10-10", 9: "2026-10-10"}
RERECORDED_RAW, RERECORDED_BOARD, RERECORDED_DAY = 45, 15, "2026-10-10"


# ---------------------------------------------------------------- reading the logs


def pick(row: dict, keys: tuple[str, ...]):
    """The value stored under the first of `keys` that is present (old Turkish or current English name)."""
    return next((row[k] for k in keys if k in row), None)


def angles(values: dict) -> list[float]:
    return [float(values[f"{j}.pos"]) for j in JOINTS]


def read_steps(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def return_start(command: np.ndarray, state: np.ndarray) -> int:
    """Index of the first line of the scripted return to the start pose, or len(command) if there is none.

    When a `lerobot-rollout` run ends, the script drives the arm back to the pose it started from along a
    straight line in joint space (150 equal steps at 50 Hz). Those lines are not policy output. They are
    the trailing lines whose command changes by the same amount every step; the logged state is frozen
    there, because the robot is no longer read.
    """
    step = np.diff(command, axis=0)
    first = len(command) - 1
    while first > 1 and np.allclose(step[first - 1], step[-1], atol=1e-6) and np.allclose(step[first - 2], step[-1], atol=1e-6):
        first -= 1
    if first == len(command) - 1:
        return len(command)
    first -= 1  # the line before the first constant step is the first point of the straight line
    assert np.allclose(command[first] - state[first], step[-1], atol=1e-6), "return does not start at the state"
    assert (state[first:] == state[first]).all(), "the logged state changes during the return"
    return first


def load_rollout(folder: Path) -> dict:
    """A `rollout_logged.py` log: one line per control step with the measured state and the command."""
    rows = read_steps(folder / STEPS_FILE)
    t = np.array([r["t"] for r in rows])
    state = np.array([angles(pick(r, STATE_KEYS)) for r in rows])
    command = np.array([angles(pick(r, COMMAND_KEYS)) for r in rows])
    n = return_start(command, state)
    return {
        "lines": len(rows), "n": n, "t_all": t - t[0], "state_all": state, "command_all": command,
        "t": t[:n] - t[0], "command": command[:n], "rest": state[0],
        "state_t": t[:n] - t[0], "state": state[:n], "first_obs_to_first_cmd": float("nan"), "n_obs": n,
    }


def load_strands(folder: Path) -> dict:
    """A `strands_game.py` log: a state line per observation (one per chunk), a command line per step."""
    rows = read_steps(folder / STEPS_FILE)
    obs = [r for r in rows if pick(r, STATE_KEYS) is not None]
    cmd = [r for r in rows if pick(r, COMMAND_KEYS) is not None]
    t = np.array([r["t"] for r in cmd])
    state_t = np.array([r["t"] for r in obs])
    return {
        "lines": len(rows), "n": len(cmd), "t": t - t[0], "command": np.array([angles(pick(r, COMMAND_KEYS)) for r in cmd]),
        "rest": np.array(angles(pick(obs[0], STATE_KEYS))),
        "state_t": state_t - t[0], "state": np.array([angles(pick(r, STATE_KEYS)) for r in obs]),
        "first_obs_to_first_cmd": float(t[0] - state_t[0]), "n_obs": len(obs),
    }


# ---------------------------------------------------------------- definitions


def step_jumps(command: np.ndarray) -> np.ndarray:
    """Per-step change of the commanded pose: the largest change among the five arm joints, in degrees.

    Entry i is the change from step i-1 to step i; entry 0 is 0.
    """
    return np.concatenate([[0.0], np.abs(np.diff(command[:, ARM], axis=0)).max(axis=1)])


def first_run(mask: np.ndarray, length: int) -> int | None:
    """Index where the first run of `length` consecutive True values starts."""
    run = 0
    for i, value in enumerate(mask):
        run = run + 1 if value else 0
        if run >= length:
            return i - length + 1
    return None


def crossings(t: np.ndarray, values: np.ndarray, level: float) -> tuple[np.ndarray, np.ndarray]:
    """Times at which `values` rises above and falls back to or below `level`."""
    above = values > level
    return t[1:][above[1:] & ~above[:-1]], t[1:][~above[1:] & above[:-1]]


def move_summary(log: dict) -> dict:
    """Timing and smoothness of one logged move. Time 0 is the first command sent to the arm."""
    t, command, rest = log["t"], log["command"], log["rest"]
    away = np.abs(command[:, ARM] - rest[ARM]).max(axis=1)  # any arm joint, for "the arm starts"
    lift = np.abs(command[:, LIFT_ELBOW] - rest[LIFT_ELBOW]).max(axis=1)  # for the game script's rule
    out = {"commands": len(t), "end_s": t[-1], "max_from_rest_deg": away.max()}

    # Start: the beginning of the departure that led to the farthest point. An earlier excursion that was
    # pulled back to rest (run 2) is reported separately as `first_leave_s`.
    out["first_leave_s"] = out["start_s"] = out["start_far_s"] = float("nan")
    if (away > START_DEG).any():
        out["first_leave_s"] = t[np.argmax(away > START_DEG)]
        near = np.where(away[: away.argmax()] <= START_DEG)[0]
        out["start_s"] = t[near[-1] + 1 if len(near) else 0]
    far = int(np.argmax(lift > FAR_DEG)) if (lift > FAR_DEG).any() else None
    if far is not None:
        out["start_far_s"] = t[far]

    # Back: first of 45 consecutive commands within 8° of the rest pose after the arm was 20° away.
    out["back_s"] = float("nan")
    if far is not None:
        k = first_run(lift[far:] < NEAR_DEG, NEAR_STEPS)
        if k is not None:
            out["back_s"] = t[far + k]
    out["returned_in_log"] = not np.isnan(out["back_s"])

    jump = step_jumps(command)
    big = np.where(jump > JUMP_DEG)[0]
    out |= {
        "max_jump_deg": jump.max(), "max_jump_step": int(jump.argmax()),
        "max_jump_joint": JOINTS[int(np.abs(np.diff(command[:, ARM], axis=0))[jump.argmax() - 1].argmax())],
        "median_step_deg": float(np.median(jump[1:])), "mean_step_deg": float(jump[1:].mean()),
        "jumps_over_6": len(big), "jumps_over_6_on_boundary": int((big % CHUNK == 0).sum()),
        "chunk_boundaries": (len(t) - 1) // CHUNK,
    }
    gap = np.diff(t)
    pauses = np.where(gap > PAUSE_S)[0] + 1
    out |= {
        "pauses": len(pauses), "pauses_on_boundary": int((pauses % CHUNK == 0).sum()),
        "mean_pause_s": float(gap[pauses - 1].mean()) if len(pauses) else float("nan"),
    }
    opened, closed = crossings(t, command[:, 5], GRIPPER_OPEN)
    out |= {
        "gripper_cmd_openings": len(opened),
        "gripper_cmd_first_open_s": opened[0] if len(opened) else float("nan"),
        "gripper_cmd_last_open_s": opened[-1] if len(opened) else float("nan"),
        "gripper_cmd_last_close_s": closed[-1] if len(closed) else float("nan"),
    }
    return out


def flip(path: Path) -> np.ndarray:
    """The top frame rotated to the robot's view (180°), as signed integers (strands_game.flip)."""
    return np.asarray(Image.open(path).convert("RGB").rotate(180)).astype(np.int16)


def cell_diffs(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Mean absolute grey difference of each of the nine board cells between two frames, shape (3, 3).

    strands_game.cell_diff returns the largest of these nine values and compares it with CHANGE_THRESHOLD.
    """
    left, top, right, bottom = BOARD_BOX
    diff = np.abs(a[top:bottom, left:right].mean(2) - b[top:bottom, left:right].mean(2))
    h, w = diff.shape[0] // 3, diff.shape[1] // 3
    return np.array([[diff[r * h : (r + 1) * h, c * w : (c + 1) * w].mean() for c in range(3)] for r in range(3)])


def slot_red(a: np.ndarray) -> float:
    """Share of red pixels in the pick slot box (strands_game.slot_has_x compares it with SLOT_THRESHOLD)."""
    left, top, right, bottom = SLOT_BOX
    box = a[top:bottom, left:right]
    red = (box[..., 0] > 110) & (box[..., 0] > 1.5 * box[..., 1]) & (box[..., 0] > 1.5 * box[..., 2])
    return float(red.mean())


# ---------------------------------------------------------------- writing


def write_csv(name: str, header: list[str], rows: list[list]) -> None:
    def cell(value):
        if isinstance(value, (bool, np.bool_)):
            return "yes" if value else "no"
        if isinstance(value, (float, np.floating)):
            return "" if np.isnan(value) else f"{value:.3f}"
        return value

    with (OUT / name).open("w", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(header)
        writer.writerows([[cell(v) for v in row] for row in rows])


KEY: list[list] = []  # rows of key_numbers.csv: every number quoted on the benchmark pages


def key(name: str, value, unit: str, what: str) -> None:
    assert name not in [row[0] for row in KEY], name
    if isinstance(value, (float, np.floating)):
        value = repr(float(value))  # already rounded by the caller; keeps "6.8" from becoming "6.800"
    KEY.append([name, value, unit, what])


# ---------------------------------------------------------------- the tables


def arm_runs(raw: Path) -> None:
    """One CSV per `lerobot-rollout` run, a per-run summary, the jumps and the chunk boundaries."""
    summary, jumps, boundaries = [], [], []
    for folder, run_id, label, inference in ARM_RUNS:
        log = load_rollout(raw / ROLLOUT_DIR / folder)
        n, t, command = log["n"], log["t"], log["command"]
        header = ["step", "t_s", "phase"] + [f"cmd_{j}" for j in JOINTS] + [f"meas_{j}" for j in JOINTS]
        rows = [
            [i, log["t_all"][i], "policy" if i < n else "return", *log["command_all"][i], *log["state_all"][i]]
            for i in range(log["lines"])
        ]
        write_csv(f"arm_{run_id}_{inference}.csv", header, rows)

        s = move_summary(log)
        jump = step_jumps(command)
        with_gripper = np.concatenate([[0.0], np.abs(np.diff(command, axis=0)).max(axis=1)])
        big6 = np.where(with_gripper > JUMP_DEG)[0]
        summary.append([
            run_id, label, inference, f"{ROLLOUT_DIR}/{folder}/{STEPS_FILE}", log["lines"], n, log["lines"] - n,
            t[-1], s["jumps_over_6"], s["jumps_over_6_on_boundary"], s["max_jump_deg"], s["max_jump_step"],
            s["max_jump_joint"], s["median_step_deg"], s["mean_step_deg"], s["chunk_boundaries"], s["pauses"],
            s["pauses_on_boundary"], s["mean_pause_s"], len(big6), int((big6 % CHUNK == 0).sum()),
        ])
        delta = np.abs(np.diff(command[:, ARM], axis=0))
        for i in np.where(jump > JUMP_DEG)[0]:
            jumps.append([run_id, inference, int(i), t[i], jump[i], JOINTS[int(delta[i - 1].argmax())], i % CHUNK == 0])
        gap = np.concatenate([[0.0], np.diff(t)])
        for i in range(CHUNK, n, CHUNK):
            boundaries.append([run_id, inference, i, t[i], jump[i], gap[i]])

        key(f"{run_id}_policy_steps", n, "steps", f"{label}: control steps sent by the policy")
        key(f"{run_id}_return_lines", log["lines"] - n, "lines", f"{label}: trailing log lines of the scripted return, excluded")
        key(f"{run_id}_policy_duration", round(float(t[-1]), 1), "s", f"{label}: first to last policy command")
        key(f"{run_id}_jumps_over_6", s["jumps_over_6"], "steps", f"{label}: steps whose command change exceeds 6° (five arm joints)")
        key(f"{run_id}_jumps_on_boundary", s["jumps_over_6_on_boundary"], "steps", f"{label}: of those, on a chunk boundary (step divisible by 50)")
        key(f"{run_id}_max_jump", round(float(s["max_jump_deg"]), 1), "deg", f"{label}: largest per-step command change")
        key(f"{run_id}_median_step", round(float(s["median_step_deg"]), 1), "deg", f"{label}: median per-step command change")
        key(f"{run_id}_chunk_boundaries", s["chunk_boundaries"], "boundaries", f"{label}: chunk boundaries in the policy part")
        key(f"{run_id}_pauses", s["pauses"], "pauses", f"{label}: gaps between commands longer than {PAUSE_S} s")
        if s["pauses"]:
            key(f"{run_id}_mean_pause", round(s["mean_pause_s"], 2), "s", f"{label}: mean length of those gaps")
        key(f"{run_id}_jumps_over_6_with_gripper", len(big6), "steps", f"{label}: the same count with the gripper channel (0-100) included")
        key(f"{run_id}_jumps_on_boundary_with_gripper", int((big6 % CHUNK == 0).sum()), "steps", f"{label}: of those, on a chunk boundary")
        if run_id == "run2":
            key("run2_step50_wrist_flex_before", round(float(command[49, 3]), 0), "deg", "run 2: commanded wrist_flex at step 49")
            key("run2_step50_wrist_flex_after", round(float(command[50, 3]), 0), "deg", "run 2: commanded wrist_flex at step 50")
        if run_id == "run4":
            # Pick and release from the measured gripper opening.
            opened, closed = crossings(t, log["state"][:, 5], GRIPPER_OPEN)
            hold = log["state"][(t > closed[0] + 0.5) & (t < opened[-1] - 0.5), 5]
            after = log["state"][t > closed[-1] + 0.5, 5]
            write_csv("run4_events.csv", ["event", "t_s", "definition"], [
                ["gripper_opens_at_slot", opened[0], "measured gripper opening rises above 8 % for the first time"],
                ["pick", closed[0], "measured gripper opening falls back below 8 %: the gripper closes on the X"],
                ["release", opened[-1], "measured gripper opening rises above 8 % for the last time: the gripper lets go"],
                ["gripper_closed_again", closed[-1], "measured gripper opening falls below 8 % for the last time"],
                ["start", s["start_s"], f"commanded pose leaves the rest pose by more than {START_DEG:.0f}° (see moves.csv)"],
                ["back", s["back_s"], "commanded pose back within 8° of rest (see moves.csv)"],
            ])
            key("run4_pick", round(float(closed[0]), 1), "s", "run 4: the gripper closes on the X (measured opening back below 8 %)")
            key("run4_release", round(float(opened[-1]), 1), "s", "run 4: the gripper opens over the cell (measured opening above 8 %)")
            key("run4_gripper_closed_again", round(float(closed[-1]), 1), "s", "run 4: the gripper is closed again after the release")
            key("run4_gripper_holding", round(float(np.median(hold)), 1), "%", "run 4: median measured gripper opening while it holds the X")
            key("run4_gripper_empty", round(float(np.median(after)), 1), "%", "run 4: median measured gripper opening after the release")
            resting = t > s["back_s"] + 2.0
            offset = np.median(command[resting, 3] - log["state"][resting, 3])
            key("run4_wrist_flex_rest_offset", round(float(offset), 1), "deg", "run 4, arm back at rest: median of commanded minus measured wrist_flex")

    write_csv("arm_run_summary.csv", [
        "run", "label", "inference", "source", "log_lines", "policy_steps", "return_lines", "policy_duration_s",
        "jumps_over_6deg", "jumps_over_6deg_on_chunk_boundary", "max_jump_deg", "max_jump_step", "max_jump_joint",
        "median_step_deg", "mean_step_deg", "chunk_boundaries", "pauses_over_0p2s", "pauses_on_chunk_boundary",
        "mean_pause_s", "jumps_over_6_with_gripper", "jumps_over_6_with_gripper_on_chunk_boundary",
    ], summary)
    write_csv("arm_jumps.csv", ["run", "inference", "step", "t_s", "jump_deg", "joint", "on_chunk_boundary"], jumps)
    write_csv("arm_chunk_boundaries.csv", ["run", "inference", "step", "t_s", "jump_deg", "gap_before_s"], boundaries)

    queued = [r for r in summary if r[2] == "queued"]
    key("queued_jumps_over_6", sum(r[8] for r in queued), "steps", "runs 2 and 3 together: steps with a command change above 6°")
    key("queued_jumps_on_boundary", sum(r[9] for r in queued), "steps", "runs 2 and 3 together: of those, on a chunk boundary")
    key("queued_max_jump", round(max(float(r[10]) for r in queued), 1), "deg", "runs 2 and 3: largest per-step command change")
    key("queued_boundaries", sum(r[15] for r in queued), "boundaries", "runs 2 and 3 together: chunk boundaries")
    key("queued_boundaries_over_6", sum(1 for b in boundaries if b[1] == "queued" and b[4] > JUMP_DEG), "boundaries", "runs 2 and 3 together: chunk boundaries with a jump above 6°")


def moves(raw: Path) -> None:
    """One row per logged move: when the arm started, when it was back, how smooth the commands were."""
    rows = []
    for move_id, kind, folder, cell, inference, counted, landed, note in MOVES:
        log = (load_rollout if kind == "direct" else load_strands)(raw / folder)
        s = move_summary(log)
        rows.append([
            move_id, kind, cell, inference, f"{folder}/{STEPS_FILE}", s["commands"], log["n_obs"],
            log["first_obs_to_first_cmd"], s["first_leave_s"], s["start_s"], s["start_far_s"], s["back_s"], s["end_s"],
            s["returned_in_log"], s["max_from_rest_deg"], s["max_jump_deg"], s["max_jump_step"], s["jumps_over_6"],
            s["jumps_over_6_on_boundary"], s["pauses"], s["mean_pause_s"], s["gripper_cmd_openings"],
            s["gripper_cmd_last_open_s"], s["gripper_cmd_last_close_s"], counted, landed, note,
        ])
    header = [
        "move", "kind", "cell", "inference", "source", "commands", "observations", "first_obs_to_first_cmd_s",
        "first_leave_s", "start_s", "start_far20_s", "back_s", "end_s", "returned_in_log", "max_from_rest_deg",
        "max_jump_deg", "max_jump_step", "jumps_over_6deg", "jumps_over_6deg_on_chunk_boundary", "pauses_over_0p2s",
        "mean_pause_s", "gripper_cmd_openings", "gripper_cmd_last_open_s", "gripper_cmd_last_close_s",
        "counted_as_completed", "landed_evidence", "note",
    ]
    write_csv("moves.csv", header, rows)

    table = pd.DataFrame(rows, columns=header)
    done = table[table.counted_as_completed]
    tally = []
    for cell in CELLS:
        here = done[done.cell == cell]
        tally.append([
            cell, len(here), int((here.landed_evidence != "").sum()), int((here.landed_evidence == "frame").sum()),
            int((here.landed_evidence == "notes").sum()), " + ".join(f"{k} x{n}" for k, n in here.kind.value_counts(sort=False).items()),
        ])
    write_csv("cell_tally.csv", ["cell", "completed_moves", "landed", "landed_seen_in_frame", "landed_per_notes_only", "by_kind"], tally)

    key("moves_logged", len(table), "logs", "logged runs of the policy on the arm (run 1 was not logged)")
    key("moves_completed", len(done), "moves", "moves the project notes count as completed")
    key("moves_landed", int((done.landed_evidence != "").sum()), "moves", "of those, X in the right cell")
    key("moves_landed_seen_in_frame", int((done.landed_evidence == "frame").sum()), "moves", "landing visible in a later top frame on disk")
    key("moves_landed_notes_only", int((done.landed_evidence == "notes").sum()), "moves", "landing known from the project notes only")
    key("cells_tried", sum(1 for r in tally if r[1]), "cells", "cells with at least one completed move")
    key("moves_return_logged", int(done.returned_in_log.sum()), "moves", "completed moves whose return to rest is in the log")
    timed = done[done.returned_in_log]
    sync = timed[timed.inference == "sync"]
    key("sync_moves_timed", len(sync), "moves", "sync moves with start and return in the log")
    key("sync_start_min", round(float(sync.start_s.min()), 1), "s", "sync moves: shortest wait before the arm starts")
    key("sync_start_max", round(float(sync.start_s.max()), 1), "s", "sync moves: longest wait before the arm starts")
    key("sync_start_median", round(float(sync.start_s.median()), 1), "s", "sync moves: median wait before the arm starts")
    key("sync_back_min", round(float(sync.back_s.min()), 1), "s", "sync moves: shortest time until the arm is back")
    key("sync_back_max", round(float(sync.back_s.max()), 1), "s", "sync moves: longest time until the arm is back")
    key("sync_back_median", round(float(sync.back_s.median()), 1), "s", "sync moves: median time until the arm is back")
    started = done[done.inference == "sync"]
    key("sync_moves_started", len(started), "moves", "completed sync moves (start time available for all)")
    key("sync_start_all_min", round(float(started.start_s.min()), 1), "s", "all completed sync moves: shortest wait before the start")
    key("sync_start_all_max", round(float(started.start_s.max()), 1), "s", "all completed sync moves: longest wait before the start")
    key("sync_start_all_median", round(float(started.start_s.median()), 1), "s", "all completed sync moves: median wait before the start")
    what = {
        "first_leave_s": "first command more than 10° from the rest pose",
        "start_s": "the arm starts (start of the departure that leads to the farthest point)",
        "start_far20_s": "first command with shoulder_lift or elbow_flex more than 20° from rest",
        "back_s": "the arm is back (first of 45 consecutive commands within 8° of rest)",
        "end_s": "last policy command in the log",
    }
    for _, row in table.iterrows():
        for column, text in what.items():
            if not pd.isna(row[column]):
                key(f"{row.move}_{column[:-2]}", round(float(row[column]), 1), "s", f"{row.move}: {text}")
        if row.kind != "direct":
            key(f"{row.move}_max_jump", round(float(row.max_jump_deg), 1), "deg", f"{row.move}: largest per-step command change")
    game = table[(table.inference == "sync") & (table.kind != "direct")]
    key("sync_game_logs", len(game), "logs", "logs written by the game script (all sync)")
    key("sync_game_max_jump", round(float(game.max_jump_deg.max()), 1), "deg", "game-script logs: largest per-step command change")
    key("sync_game_jumps_over_6", int(game.jumps_over_6deg.sum()), "steps", "game-script logs: steps with a command change above 6°")
    key("sync_first_inference_min", round(float(game.first_obs_to_first_cmd_s.min()), 2), "s", "game-script logs: shortest first observation to first command")
    key("sync_first_inference_max", round(float(game.first_obs_to_first_cmd_s.max()), 2), "s", "game-script logs: longest first observation to first command")
    for name in ("game1_move3", "game2_move3"):
        row = table[table.move == name].iloc[0]
        key(f"{name}_end_after_gripper_open", round(float(row.end_s - row.gripper_cmd_last_open_s), 1), "s", f"{name}: the log ends this long after the gripper was last commanded open")


def boards(text: str) -> dict[int, dict]:
    """The start boards of docs/rounds/round1.md: raw episode number -> block, target cell, X and O counts."""
    found = {}
    for block in re.finditer(r"## Block (\d+) .*?\n\n`--dataset\.single_task=\"put the red X in the (.*?) cell\".*?```\n(.*?)```", text, re.S):
        number, cell, drawing = int(block[1]), block[2], block[3].splitlines()
        episodes = [int(e) for e in re.findall(r"#(\d+)", drawing[0])]
        grid = [[] for _ in episodes]
        for line in drawing:
            if "│" not in line:
                continue
            parts = line.split("│")[1:]  # per board: three cells, then the gap to the next board
            for b in range(len(episodes)):
                grid[b] += [p.strip() for p in parts[4 * b : 4 * b + 3]]
        for episode, cells in zip(episodes, grid):
            assert len(cells) == 9 and cells.count("*") == 1 and CELLS[cells.index("*")] == cell, (episode, cells)
            found[episode] = {"block": number, "cell": cell, "x": cells.count("X"), "o": cells.count("O")}
    assert sorted(found) == list(range(45)), "expected the boards of raw episodes #0-#44"
    return found


def episodes(raw: Path) -> None:
    """One row per demonstration of the clean training set."""
    root = raw / DATASET_DIR
    info = json.loads((root / "meta/info.json").read_text())
    names = info["features"]["action"]["names"]
    assert names == [f"{j}.pos" for j in JOINTS] == info["features"]["observation.state"]["names"]
    fps = info["fps"]
    meta = pd.concat(pd.read_parquet(p) for p in sorted((root / "meta/episodes").rglob("*.parquet"))).sort_values("episode_index")
    frames = pd.concat(
        pd.read_parquet(p, columns=["action", "observation.state", "episode_index", "frame_index", "timestamp"])
        for p in sorted((root / "data").rglob("*.parquet"))
    ).sort_values(["episode_index", "frame_index"])
    plan = boards((REPO / "docs/rounds/round1.md").read_text())

    def first_motion(values: np.ndarray, t: np.ndarray) -> float:
        """Time of the first frame in which an arm joint is more than 3° from its value in frame 0."""
        return float(t[np.argmax(np.abs(values[:, ARM] - values[0, ARM]).max(axis=1) > FIRST_MOTION_DEG)])

    rows = []
    for (index, group), (_, m) in zip(frames.groupby("episode_index"), meta.iterrows()):
        assert index == m.episode_index and len(group) == m.length
        cell = re.fullmatch(r"put the red X in the (.*) cell", m.tasks[0])[1]
        # The clean set dropped raw #15 and appended its re-recording (raw #45, same board) at the end.
        raw_episode = index if index < 15 else index + 1
        board = plan[RERECORDED_BOARD if raw_episode == RERECORDED_RAW else raw_episode]
        assert board["cell"] == cell, (index, cell, board)
        day = RERECORDED_DAY if raw_episode == RERECORDED_RAW else BLOCK_DAY[board["block"]]
        t = group.timestamp.to_numpy()
        action, state = np.stack(group.action.to_numpy()), np.stack(group["observation.state"].to_numpy())
        rows.append([
            index, raw_episode, board["block"], day, cell, m.length, m.length / fps, first_motion(action, t),
            first_motion(state, t), board["x"], board["o"], board["x"] + board["o"],
        ])
    header = [
        "episode", "raw_episode", "block", "recorded_on", "cell", "frames", "duration_s", "first_motion_action_s",
        "first_motion_state_s", "x_at_start", "o_at_start", "pieces_at_start",
    ]
    write_csv("episodes.csv", header, rows)

    table = pd.DataFrame(rows, columns=header)
    assert len(table) == info["total_episodes"] and table.frames.sum() == info["total_frames"]
    key("episodes", len(table), "episodes", "demonstrations in the clean set")
    key("episode_frames", int(table.frames.sum()), "frames", "frames in the clean set")
    key("episode_minutes", round(table.frames.sum() / fps / 60, 1), "min", "total length of the clean set")
    key("episode_duration_min", round(table.duration_s.min(), 1), "s", "shortest demonstration")
    key("episode_duration_max", round(table.duration_s.max(), 1), "s", "longest demonstration")
    key("episode_duration_median", round(table.duration_s.median(), 1), "s", "median demonstration length")
    for day, part in table.groupby("recorded_on"):
        tag = day.replace("-", "")
        key(f"episodes_{tag}", len(part), "episodes", f"demonstrations recorded on {day}")
        key(f"episode_duration_median_{tag}", round(part.duration_s.median(), 1), "s", f"median length, recorded on {day}")
    for block, part in table.groupby("block"):
        key(f"block{block}_duration_min", round(part.duration_s.min(), 1), "s", f"block {block} ({part.cell.iloc[0]}): shortest demonstration")
        key(f"block{block}_duration_max", round(part.duration_s.max(), 1), "s", f"block {block} ({part.cell.iloc[0]}): longest demonstration")
    for column, tag, what in (("first_motion_action_s", "action", "recorded action (leader arm)"), ("first_motion_state_s", "state", "measured state (follower arm)")):
        key(f"pause_{tag}_mean", round(table[column].mean(), 1), "s", f"pause before the first motion, {what}: mean")
        key(f"pause_{tag}_median", round(table[column].median(), 1), "s", f"pause before the first motion, {what}: median")
        key(f"pause_{tag}_min", round(table[column].min(), 1), "s", f"pause before the first motion, {what}: shortest")
        key(f"pause_{tag}_max", round(table[column].max(), 1), "s", f"pause before the first motion, {what}: longest")
    key("pause_state_under_half_second", int((table.first_motion_state_s < 0.5).sum()), "episodes", "episodes whose follower arm moves more than 3° in the first 0.5 s")
    key("pause_action_under_half_second", int((table.first_motion_action_s < 0.5).sum()), "episodes", "episodes whose recorded action moves more than 3° in the first 0.5 s")
    key("pieces_at_start_min", int(table.pieces_at_start.min()), "pieces", "fewest pieces on a start board")
    key("pieces_at_start_max", int(table.pieces_at_start.max()), "pieces", "most pieces on a start board")
    per_cell = table.groupby("cell").pieces_at_start
    key("pieces_cell_emptiest_max", int(per_cell.min().max()), "pieces", "the emptiest start board of a cell has at most this many pieces, in every cell")
    key("pieces_cell_fullest_min", int(per_cell.max().min()), "pieces", "the fullest start board of a cell has at least this many pieces, in every cell")


def detectors(raw: Path) -> None:
    """Per-cell grey differences and pick-slot red shares on frames that are on disk."""
    strands = raw / STRANDS_DIR
    cells = []

    def add(group: str, pair: str, a: str, b: str, labels: dict | None = None) -> np.ndarray:
        diff = cell_diffs(flip(raw / a), flip(raw / b))
        for r, row in enumerate(ROWS):
            for c, col in enumerate(COLS):
                cell = f"{row} {col}"
                piece, moved = (labels or {}).get(cell, ""), (pair, cell) in MOVED_PIECES
                cells.append([group, pair, a, b, cell, diff[r, c], piece, bool(labels) and cell in GRIPPER_CELLS, moved])
        return diff

    # 1. The same scene five times within two seconds (capture_frames.py, PNG).
    captures = sorted((raw / CAPTURE_DIR).glob("top_*.png"))
    for a, b in itertools.combinations(captures, 2):
        add("unchanged", f"capture_{a.stem[-1]}_{b.stem[-1]}", str(a.relative_to(raw)), str(b.relative_to(raw)))
    # 2. The first two top frames of a move, both taken before the first command (JPEG, as in the game
    #    logs). In most moves the camera returned the same frame twice; those pairs are skipped.
    skipped = 0
    for move in sorted(strands.glob("*/*/")):
        a, b = move / "top_001.jpg", move / "top_002.jpg"
        if a.read_bytes() == b.read_bytes():
            skipped += 1
            continue
        add("unchanged_game_frames", f"{move.parent.name}_{move.name}", str(a.relative_to(raw)), str(b.relative_to(raw)))
    # 3. First frames of consecutive moves of a game: one X and one O were added in between.
    for pair, earlier, later, new_x, new_o in GAME_PAIRS:
        add("game", pair, f"{STRANDS_DIR}/{earlier}/top_001.jpg", f"{STRANDS_DIR}/{later}/top_001.jpg", {new_x: "X", new_o: "O"})
    write_csv("detector_cells.csv", [
        "group", "pair", "frame_a", "frame_b", "cell", "mean_abs_grey_diff", "piece_added", "under_resting_gripper",
        "existing_piece_moved",
    ], cells)

    table = pd.DataFrame(cells, columns=["group", "pair", "a", "b", "cell", "diff", "piece", "gripper", "moved"])
    same = table[table.group == "unchanged"]
    game = table[table.group == "game"]
    new = game[game.piece != ""]
    quiet = game[(game.piece == "") & ~game.gripper & ~game.moved]
    under = game[(game.piece == "") & game.gripper]
    key("change_threshold", CHANGE_THRESHOLD, "grey levels", "CHANGE_THRESHOLD of scripts/strands_game.py")
    key("unchanged_pairs", same.pair.nunique(), "frame pairs", "pairs among five captures of one unchanged scene")
    key("unchanged_cells", len(same), "values", "per-cell differences in those pairs")
    key("unchanged_min", round(same["diff"].min(), 1), "grey levels", "unchanged scene: smallest per-cell difference")
    key("unchanged_max", round(same["diff"].max(), 1), "grey levels", "unchanged scene: largest per-cell difference")
    key("unchanged_mean", round(same["diff"].mean(), 1), "grey levels", "unchanged scene: mean per-cell difference")
    jpeg = table[table.group == "unchanged_game_frames"]
    key("unchanged_jpeg_pairs", jpeg.pair.nunique(), "frame pairs", "distinct first-two-frame pairs in the game logs (JPEG)")
    key("unchanged_jpeg_pairs_skipped", skipped, "frame pairs", "first-two-frame pairs that are the same frame saved twice")
    key("unchanged_jpeg_max", round(jpeg["diff"].max(), 1), "grey levels", "those JPEG pairs: largest per-cell difference")
    key("game_pairs", game.pair.nunique(), "frame pairs", "pairs of first frames of consecutive game moves")
    key("new_piece_cells", len(new), "cells", "cells that received a piece between the two frames")
    key("new_piece_min", round(new["diff"].min(), 1), "grey levels", "cell with a new piece: smallest difference")
    key("new_piece_max", round(new["diff"].max(), 1), "grey levels", "cell with a new piece: largest difference")
    key("new_piece_over_threshold", int((new["diff"] > CHANGE_THRESHOLD).sum()), "cells", "cells with a new piece above the threshold")
    key("quiet_cells", len(quiet), "cells", "cells with no new piece, away from the resting gripper, nothing moved")
    key("quiet_min", round(quiet["diff"].min(), 1), "grey levels", "those cells: smallest difference")
    key("quiet_max", round(quiet["diff"].max(), 1), "grey levels", "those cells: largest difference")
    key("gripper_cells", len(under), "cells", "cells with no new piece that the resting gripper partly covers")
    key("gripper_min", round(under["diff"].min(), 1), "grey levels", "those cells: smallest difference")
    key("gripper_max", round(under["diff"].max(), 1), "grey levels", "those cells: largest difference")
    key("gripper_over_threshold", int((under["diff"] > CHANGE_THRESHOLD).sum()), "cells", "those cells above the threshold")
    key("moved_piece_diff", round(game[game.moved]["diff"].iloc[0], 1), "grey levels", "cell whose X was straightened by hand between the frames")

    # Pick slot: frames in which the slot is in plain view (the arm at rest), labelled by eye.
    slot = []
    for path in captures:
        slot.append([str(path.relative_to(raw)), "capture", "X", slot_red(flip(path))])
    for folder, run_id, *_ in ARM_RUNS:
        tops = sorted((raw / ROLLOUT_DIR / folder).glob("top_*.jpg"))
        slot.append([str(tops[0].relative_to(raw)), f"{run_id} first frame", "X", slot_red(flip(tops[0]))])
        slot.append([str(tops[-1].relative_to(raw)), f"{run_id} last frame", "empty", slot_red(flip(tops[-1]))])
    for move_id, kind, folder, *_ in MOVES:
        if kind == "direct":
            continue
        tops = sorted((raw / folder).glob("top_*.jpg"))
        empty_at_start = kind in ("accidental", "empty slot")
        slot.append([str(tops[0].relative_to(raw)), f"{move_id} first frame", "empty" if empty_at_start else "X", slot_red(flip(tops[0]))])
        slot.append([str(tops[-1].relative_to(raw)), f"{move_id} last frame", "empty", slot_red(flip(tops[-1]))])
    write_csv("detector_slot.csv", ["frame", "where", "slot_by_eye", "red_share"], [[f, w, s, round(v, 4)] for f, w, s, v in slot])
    with_x = [v for *_, s, v in slot if s == "X"]
    empty = [v for *_, s, v in slot if s == "empty"]
    key("slot_threshold", SLOT_THRESHOLD, "share", "SLOT_THRESHOLD of scripts/strands_game.py")
    key("slot_x_frames", len(with_x), "frames", "frames with an X in the pick slot")
    key("slot_x_min", round(min(with_x), 3), "share", "X in the slot: smallest red share")
    key("slot_x_max", round(max(with_x), 3), "share", "X in the slot: largest red share")
    key("slot_empty_frames", len(empty), "frames", "frames with an empty pick slot")
    key("slot_empty_max", round(max(empty), 3), "share", "empty slot: largest red share")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-root", type=Path, default=REPO, help="checkout that holds outputs/ and data/")
    raw = parser.parse_args().raw_root.resolve()
    for needed in (ROLLOUT_DIR, STRANDS_DIR, CAPTURE_DIR, DATASET_DIR):
        if not (raw / needed).exists():
            raise SystemExit(f"missing raw material: {raw / needed} (pass --raw-root)")
    OUT.mkdir(parents=True, exist_ok=True)
    arm_runs(raw)
    moves(raw)
    episodes(raw)
    detectors(raw)
    write_csv("key_numbers.csv", ["key", "value", "unit", "what"], KEY)
    size = sum(p.stat().st_size for p in OUT.iterdir())
    print(f"{len(list(OUT.glob('*.csv')))} CSV files in {OUT} ({size / 1e6:.2f} MB), {len(KEY)} key numbers")


if __name__ == "__main__":
    main()
