"""What the top camera tells the game: is there an X in the pick slot, did the X land, where is the new O.

Cheap pixel checks (red in the slot, change in a cell, motion in the frame) decide when to look;
Claude then reads the cropped board. `landing` needs no Claude: it finds the X the arm just placed
from the red that is new compared with a reference frame of the empty board (the `eval` command).
Nothing here opens a camera except `grab_frame`; the waiting loops get their frames from the arm
(`arm.frame()`).
"""

import base64
import io
import select
import sys
import threading
import time
from functools import partial

import numpy as np
from PIL import Image, ImageFilter

from .board import CELLS, draw
from .i18n import t, yes

# Box of the grid in the 180° rotated `top` frame (left, top, right, bottom). Update it if the scene moves.
BOARD_BOX = (160, 40, 478, 358)
FIELDS = [c.replace(" ", "_") for c in CELLS]
# The slot the X is picked from, in the same frame. Red pixel ratio in the box: 0.00 when empty, 0.045-0.30 with an X (16 frames).
SLOT_BOX = (485, 250, 560, 325)
SLOT_THRESHOLD = 0.015
# Mean gray difference per cell: ~2 for the same scene, 16-22 once a piece is put in the cell
# (a cell under the resting gripper reached 30 without one, which is why Claude judges every triggered read).
CHANGE_THRESHOLD = 8.0
# Largest change among 4x4 blocks between two consecutive frames: grows while a hand or the arm is in view.
MOTION_THRESHOLD = 6.0
# With no change seen, have Claude read the board anyway this often while waiting for the O.
RECHECK_SECONDS = 30.0
# A red piece on the board, for the `eval` command. Measured on the recorded frames: an X shows 1650-2060
# red pixels with the arm at rest (17 sightings in 15 frames) and 1340 at the least while the arm still
# covers part of it; the orange part of the resting gripper 490-610, and up to 690 of it are "new" against
# a reference frame, because the arm never rests in exactly the same place (30 px apart over 10 rest poses).
MIN_PIECE_PIXELS = 1100
# The reference's red is widened by this (odd, pixels across) before it is subtracted: 5 removes the
# 2-6 pixels of edge noise seen between frames of an unchanged scene.
REFERENCE_MARGIN = 5
BLOB_JOIN = 5  # red pixels closer than this (odd, pixels across) belong to the same blob
# A red group of at least GRIPPER_PIXELS in the reference is the gripper's orange part; a piece within
# GRIPPER_REACH pixels of it may have part of the gripper (resting elsewhere now) counted with it.
GRIPPER_PIXELS = 200
GRIPPER_REACH = 40
STOP = threading.Event()  # Ctrl+C or the dashboard's Stop: waiting loops exit through this
BOARD_PROMPT = """This is a top-down photo of a tic-tac-toe board: a 3x3 grid made of black bars on a wooden table.
Pieces are red X shapes and white rings (O). A robot gripper (a black plate with an orange part) may cover
part of the bottom row; it is not a piece. A piece hidden partly by the gripper still counts.
Report what is in each of the nine cells with the report_board tool: "X", "O" or "empty"."""


class Console:
    """Where the waiting loops report what they see: here, only the terminal.

    The game passes a subclass (`xox.game.Journal`) that also feeds the dashboard and `game.jsonl`.
    """

    def say(self, kind: str, text: str, **extra) -> None:
        """Prints `text` and records it as an event of this `kind`."""
        print(text)
        self.note(kind, text.strip(), **extra)

    def note(self, kind: str, text: str, **extra) -> None:
        """Records an event without printing it."""

    def phase(self, phase: str, **fields) -> None:
        """The game moved to another phase (see `xox.state.PHASES`)."""

    def frame(self, name: str, image) -> None:
        """A new image for the dashboard (`top`, `wrist` or `board`)."""


CONSOLE = Console()


def crop_board(frame) -> Image.Image:
    """Rotates the `top` frame to the robot's view (top row at the top) and crops it to the grid."""
    image = Image.fromarray(frame) if not isinstance(frame, Image.Image) else frame
    crop = image.convert("RGB").rotate(180).crop(BOARD_BOX)
    return crop.resize((crop.width * 2, crop.height * 2), Image.BICUBIC)


def read_board(frame, model: str, on_crop=None) -> list[str]:
    """Shows Claude the photo of the board, returns the 9 cells ("X", "O" or " ").

    `on_crop` gets the cropped image that is sent to Claude (the dashboard shows it).
    """
    import anthropic

    crop = crop_board(frame)
    if on_crop is not None:
        on_crop(crop)
    buffer = io.BytesIO()
    crop.save(buffer, format="JPEG", quality=92)
    response = anthropic.Anthropic().messages.create(
        model=model,
        max_tokens=512,
        tools=[
            {
                "name": "report_board",
                "description": "Report the contents of the nine cells of the board.",
                "input_schema": {
                    "type": "object",
                    "properties": {f: {"type": "string", "enum": ["X", "O", "empty"]} for f in FIELDS},
                    "required": FIELDS,
                },
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64.b64encode(buffer.getvalue()).decode(),
                        },
                    },
                    {"type": "text", "text": BOARD_PROMPT},
                ],
            }
        ],
    )
    reported = next((b.input for b in response.content if b.type == "tool_use"), None)
    if reported is None or any(reported.get(f) not in ("X", "O", "empty") for f in FIELDS):
        raise ValueError(t("board_not_reported"))
    return [" " if reported[f] == "empty" else reported[f] for f in FIELDS]


def flip(frame) -> np.ndarray:
    """Rotates the `top` frame to the robot's view (180°), as signed integers for the grayscale maths."""
    return np.asarray(Image.fromarray(frame).convert("RGB").rotate(180)).astype(np.int16)


def cell_diff(a: np.ndarray, b: np.ndarray) -> float:
    """Mean gray difference of the board cell that changed most between two frames."""
    left, top, right, bottom = BOARD_BOX
    diff = np.abs(a[top:bottom, left:right].mean(2) - b[top:bottom, left:right].mean(2))
    h, w = diff.shape[0] // 3, diff.shape[1] // 3
    return max(float(diff[r * h : (r + 1) * h, c * w : (c + 1) * w].mean()) for r in range(3) for c in range(3))


def motion(a: np.ndarray, b: np.ndarray) -> float:
    """Mean gray difference of the block that changed most between two frames, with the frame split 4x4."""
    diff = np.abs(a.mean(2) - b.mean(2))
    h, w = diff.shape[0] // 4, diff.shape[1] // 4
    return max(float(diff[r * h : (r + 1) * h, c * w : (c + 1) * w].mean()) for r in range(4) for c in range(4))


def red(a: np.ndarray) -> np.ndarray:
    """Mask of the pixels that count as red: the X pieces, and the orange part of the gripper."""
    return (a[..., 0] > 110) & (a[..., 0] > 1.5 * a[..., 1]) & (a[..., 0] > 1.5 * a[..., 2])


def slot_has_x(a: np.ndarray) -> bool:
    left, top, right, bottom = SLOT_BOX
    return float(red(a[top:bottom, left:right]).mean()) > SLOT_THRESHOLD


def grow(mask: np.ndarray, size: int) -> np.ndarray:
    """Widens a mask: every pixel within `size // 2` of a set pixel becomes set (`size` is odd)."""
    return np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(size))) > 0


def groups(mask: np.ndarray) -> list[np.ndarray]:
    """Connected groups of set pixels, each as an array of (y, x) rows, largest first.

    Pixels closer than `BLOB_JOIN // 2` count as connected, so a piece crossed by a wire stays one group.
    """
    joined = grow(mask, BLOB_JOIN)
    ys, xs = np.nonzero(joined)
    todo = set(zip(ys.tolist(), xs.tolist()))
    found = []
    while todo:
        stack = [todo.pop()]
        members = list(stack)
        while stack:
            y, x = stack.pop()
            for near in ((y + dy, x + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
                if near in todo:
                    todo.remove(near)
                    stack.append(near)
                    members.append(near)
        members = np.array(members)
        real = members[mask[members[:, 0], members[:, 1]]]
        if len(real):
            found.append(real)
    return sorted(found, key=len, reverse=True)


def cell_at(x: float, y: float) -> int:
    """Index of the board cell that holds the point (x, y), given in pixels inside `BOARD_BOX`."""
    left, top, right, bottom = BOARD_BOX
    col = min(2, max(0, int(x // ((right - left) / 3))))
    row = min(2, max(0, int(y // ((bottom - top) / 3))))
    return row * 3 + col


def pieces_on_board(a: np.ndarray) -> list[str]:
    """Cells of the board that hold a red piece in this frame, judged by size alone (no reference)."""
    left, top, right, bottom = BOARD_BOX
    found = groups(red(a[top:bottom, left:right]))
    return [CELLS[cell_at(g[:, 1].mean(), g[:, 0].mean())] for g in found if len(g) >= MIN_PIECE_PIXELS]


def landing(a: np.ndarray, reference: np.ndarray, target: str | None = None) -> dict:
    """Where the red X is on the board in frame `a`, compared with the `reference` frame of the empty board.

    Both frames are flipped (`flip`). New red is what passes `red` now and did not in the reference
    (widened by `REFERENCE_MARGIN` against pixel noise), inside `BOARD_BOX`. Only groups of at least
    `MIN_PIECE_PIXELS` count as a piece: the orange part of the gripper rests over the bottom row, never
    exactly where it was in the reference, and shows up as a smaller group of new red.

    Returns `landed` (a cell name, "none" or "several"), the red pixel counts and, for a single piece,
    its centre and, with a `target` cell, `hit` and the offset from the centre of that cell: `dx_px` grows
    to the robot's right, `dy_px` towards the robot; `dx_cell` / `dy_cell` are the same in cell widths.
    `near_gripper` warns that the gripper's red in the reference is within `GRIPPER_REACH` of the piece:
    part of the piece is then hidden or part of the gripper counted with it, and the centre is less exact.
    `touches_edge` warns that the piece reaches the edge of the board box, so part of it may lie outside.
    """
    left, top, right, bottom = BOARD_BOX
    before = red(reference[top:bottom, left:right])
    new = red(a[top:bottom, left:right]) & ~grow(before, REFERENCE_MARGIN)
    found = groups(new)
    pieces = [g for g in found if len(g) >= MIN_PIECE_PIXELS]
    out = {
        "landed": "none" if not pieces else "several" if len(pieces) > 1 else None,
        "hit": None if target is None else False,
        "pieces": len(pieces),
        "red_pixels": sum(len(g) for g in pieces),
        "new_red_pixels": int(new.sum()),
        "largest_other_group": max((len(g) for g in found if len(g) < MIN_PIECE_PIXELS), default=0),
        "x": None, "y": None, "dx_px": None, "dy_px": None, "dx_cell": None, "dy_cell": None, "offset_cell": None,
        "near_gripper": None,
        "touches_edge": None,
    }
    if len(pieces) != 1:
        return out
    piece = pieces[0]
    x, y = float(piece[:, 1].mean()), float(piece[:, 0].mean())
    out["landed"] = CELLS[cell_at(x, y)]
    out["x"], out["y"] = round(left + x, 1), round(top + y, 1)  # in the flipped full frame
    # A piece that hangs over the edge of the board box is only seen in part.
    out["touches_edge"] = bool(
        piece.min() == 0 or piece[:, 0].max() == bottom - top - 1 or piece[:, 1].max() == right - left - 1
    )
    gripper = [g for g in groups(before) if len(g) >= GRIPPER_PIXELS]
    out["near_gripper"] = any(
        bool((np.abs(piece[:, None, :] - g[None, :, :]).max(axis=2) <= GRIPPER_REACH).any()) for g in gripper
    )
    if target is not None:
        cell = (right - left) / 3
        i = CELLS.index(target)
        dx, dy = x - (i % 3 + 0.5) * cell, y - (i // 3 + 0.5) * cell
        out |= {
            "hit": out["landed"] == target,
            "dx_px": round(dx, 1), "dy_px": round(dy, 1),
            "dx_cell": round(dx / cell, 3), "dy_cell": round(dy / cell, 3),
            "offset_cell": round(float(np.hypot(dx, dy)) / cell, 3),
        }
    return out


def still_frame(arm, duration: float = 1.0):
    """Waits until the image has not moved for `duration` seconds (hand withdrawn), returns the last frame."""
    previous = flip(arm.frame())
    still_since = time.time()
    while not STOP.is_set():
        time.sleep(0.3)
        raw = arm.frame()
        current = flip(raw)
        if motion(current, previous) > MOTION_THRESHOLD:
            still_since = time.time()
        previous = current
        if time.time() - still_since >= duration:
            return raw
    raise KeyboardInterrupt


def wait_for_slot(arm, journal: Console | None = None) -> None:
    """Waits until an X shows up in the pick slot and the hand is withdrawn."""
    journal = journal or CONSOLE
    warned = False
    while True:
        if slot_has_x(flip(still_frame(arm))):
            journal.note("vision", t("slot_filled"))
            return
        if not warned:
            journal.say("vision", t("slot_empty"))
            warned = True


def keyboard() -> str | None:
    """Checks the keyboard without waiting: returns the typed line, or None."""
    if keyboard.closed or not select.select([sys.stdin], [], [], 0)[0]:
        return None
    line = sys.stdin.readline()
    if line == "":  # input closed (pipe ended)
        keyboard.closed = True
        return None
    return line.strip().lower()


keyboard.closed = False


def wait_for_o(arm, board: list[str], model: str, journal: Console | None = None) -> str:
    """Has Claude read the board once it sees a change; returns the cell of the new O."""
    journal = journal or CONSOLE
    empty = [c for c, v in zip(CELLS, board) if v == " "]
    # The O may have been placed while the arm's move was verified; so compare against the frame used there.
    reference = getattr(arm, "reference", None)
    if reference is None:
        reference = flip(still_frame(arm))
    arm.reference = None
    # People put their O down while the arm is still returning; then the verification read already shows it.
    seen = getattr(arm, "last_seen", None)
    arm.last_seen = None
    if seen is not None:
        new = [c for c, old, now in zip(CELLS, board, seen) if old == " " and now == "O"]
        if len(new) == 1:
            journal.say("human", t("camera_o", cell=new[0]))
            return new[0]
    print(t("your_turn"))
    last_read = time.time()
    while True:
        # Nothing triggered for a while: look anyway.
        force = time.time() - last_read > RECHECK_SECONDS
        typed = keyboard()
        if typed in empty:
            journal.note("human", t("o_typed", cell=typed))
            return typed
        if typed:
            print(t("not_allowed", cells=", ".join(empty)))
        elif typed == "":
            force = True
        raw = still_frame(arm)
        current = flip(raw)
        if not force and cell_diff(current, reference) < CHANGE_THRESHOLD:
            continue
        reference = current
        last_read = time.time()
        journal.phase("reading_board")
        try:
            seen = read_board(raw, model, on_crop=partial(journal.frame, "board"))
        except Exception as error:  # noqa: BLE001 - keep waiting on an API error, manual entry stays open
            journal.say("error", t("read_failed_type", error=str(error)[:200]))
            journal.phase("waiting_for_o")
            continue
        new = [c for c, old, now in zip(CELLS, board, seen) if old == " " and now == "O"]
        if len(new) == 1:
            journal.say("human", t("camera_o", cell=new[0]))
            return new[0]
        print(draw(seen))
        journal.say("vision", t("no_single_o"), seen=seen)
        journal.phase("waiting_for_o")


def verify_x(arm, i: int, cell: str, model: str, journal: Console | None = None) -> bool:
    """After the arm's move, looks through the camera whether the X is in the target cell."""
    journal = journal or CONSOLE
    raw = still_frame(arm)
    arm.reference = flip(raw)
    try:
        seen = read_board(raw, model, on_crop=partial(journal.frame, "board"))
    except Exception as error:  # noqa: BLE001 - ask the operator if it cannot be read
        journal.say("error", t("read_failed", error=str(error)[:200]))
        landed = yes(t("x_landed", cell=cell))
        journal.note("human", t("operator_says", cell=cell, verdict=t("hit") if landed else t("missed")))
        return landed
    arm.last_seen = seen
    if seen[i] == "X":
        journal.say("vision", t("camera_x", cell=cell))
        return True
    print(draw(seen))
    journal.note("vision", t("x_missing", cell=cell), seen=seen)
    input(t("x_not_seen", cell=cell))
    journal.note("human", t("x_fixed_by_hand", cell=cell))
    return False


def grab_frame(index: int):
    """Takes a single frame from the `top` camera while the arm is not connected."""
    from lerobot.cameras.opencv import OpenCVCamera, OpenCVCameraConfig

    camera = OpenCVCamera(OpenCVCameraConfig(index_or_path=index, width=640, height=480, fps=30))
    camera.connect()
    try:
        time.sleep(1.0)
        return camera.read_latest()
    finally:
        camera.disconnect()
