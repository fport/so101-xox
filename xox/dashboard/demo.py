"""Scripted fake game for viewing the dashboard without the robot.

Replays recorded camera frames (or generated placeholders) and walks a
GameState through one full game, over and over. No camera, no serial port,
no model, no API call.
"""

from __future__ import annotations

import io
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from PIL import Image, ImageDraw

from ..state import GameState, cell_index

# Board region in the top camera image after rotating it 180 degrees.
BOARD_BOX = (160, 40, 478, 358)
BOARD_UPSCALE = 2

# Recorded moves of one real game plus one policy rollout, relative to the repo.
DEFAULT_FRAME_DIRS = (
    "outputs/strands_gunluk/20261010-214926/hamle01_middle_center",
    "outputs/strands_gunluk/20261010-214926/hamle02_bottom_right",
    "outputs/strands_gunluk/20261010-214926/hamle03_middle_left",
    "outputs/rollout_gunluk/20261010-212220",
)

# (robot cell, what Claude says, human reply). The first three robot moves are
# the ones in the default recordings; the fourth has no matching recording.
SCRIPT = (
    ("middle_center", "I'll open in the center.", "top_left"),
    ("bottom_right", "You took a corner, so I'll take the opposite one.", "bottom_left"),
    ("middle_left", "Two O's in the left column. I have to block middle left.", "top_right"),
    ("middle_right", "You left the middle row open. Middle right wins it.", None),
)

WIN_LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))


@dataclass
class Clip:
    """Camera frames of one arm move, as JPEG bytes."""

    top: list[bytes]
    wrist: list[bytes]
    seconds: float
    source: str = "placeholder"
    recorded: bool = False


@dataclass
class _Cameras:
    """The frame pair a real camera thread would be publishing right now."""

    top: Optional[bytes] = None
    wrist: Optional[bytes] = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class _Interrupted(Exception):
    pass


def board_crop(top_jpeg: bytes) -> Image.Image:
    """The board image Claude sees: rotate 180, crop the board, upscale 2x."""
    image = Image.open(io.BytesIO(top_jpeg)).convert("RGB")
    crop = image.transpose(Image.Transpose.ROTATE_180).crop(BOARD_BOX)
    size = (crop.width * BOARD_UPSCALE, crop.height * BOARD_UPSCALE)
    return crop.resize(size, Image.Resampling.BICUBIC)


def winner_of(board: Sequence[str]) -> Optional[str]:
    for a, b, c in WIN_LINES:
        if board[a] != " " and board[a] == board[b] == board[c]:
            return board[a]
    return None if " " in board else "draw"


# ------------------------------------------------------------ recorded frames


def _candidate_roots() -> list[Path]:
    """Where ``outputs/`` may live: this checkout, the cwd, the main worktree."""
    repo = Path(__file__).resolve().parents[2]
    roots = [repo, Path.cwd()]
    git_link = repo / ".git"
    if git_link.is_file():  # linked worktree: outputs/ stays in the main one
        try:
            gitdir = Path(git_link.read_text().split("gitdir:", 1)[1].strip())
            roots.append(gitdir.parents[2])
        except (OSError, IndexError):
            pass
    return roots


def default_frame_dirs() -> list[Path]:
    for root in _candidate_roots():
        found = [root / rel for rel in DEFAULT_FRAME_DIRS if (root / rel).is_dir()]
        if found:
            return found
    return []


def _recorded_seconds(directory: Path, frame_count: int) -> float:
    """Real duration of the move from the joint log, else about 2 s a frame."""
    log = directory / "adimlar.jsonl"
    try:
        with log.open("rb") as handle:
            first = handle.readline()
            last = first
            for last in handle:
                pass
        return round(json.loads(last)["t"] - json.loads(first)["t"], 1)
    except (OSError, ValueError, KeyError, TypeError):
        return frame_count * 2.0


def load_clip(directory: Path) -> Optional[Clip]:
    """Read top_NNN.jpg / wrist_NNN.jpg pairs from a folder (read-only)."""
    tops = sorted(directory.glob("top_*.jpg"))
    if not tops:
        return None
    top_frames: list[bytes] = []
    wrist_frames: list[bytes] = []
    for top_path in tops:
        wrist_path = top_path.with_name(top_path.name.replace("top_", "wrist_", 1))
        try:
            top_frames.append(top_path.read_bytes())
            wrist_frames.append(wrist_path.read_bytes())
        except OSError:
            if len(top_frames) > len(wrist_frames):  # top without its wrist pair
                wrist_frames.append(wrist_frames[-1] if wrist_frames else _wrist_placeholder(0.0))
    if not top_frames:
        return None
    return Clip(
        top=top_frames,
        wrist=wrist_frames,
        seconds=_recorded_seconds(directory, len(top_frames)),
        source=str(directory),
        recorded=True,
    )


# ---------------------------------------------------------- placeholder frames


def _jpeg(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=82)
    return buffer.getvalue()


def _cell_centre(index: int) -> tuple[float, float]:
    left, top, right, bottom = BOARD_BOX
    step_x, step_y = (right - left) / 3, (bottom - top) / 3
    return left + step_x * (index % 3 + 0.5), top + step_y * (index // 3 + 0.5)


def _draw_x(draw: ImageDraw.ImageDraw, x: float, y: float, r: float, width: int) -> None:
    draw.line((x - r, y - r, x + r, y + r), fill=(214, 62, 40), width=width)
    draw.line((x - r, y + r, x + r, y - r), fill=(214, 62, 40), width=width)


def _top_placeholder(board: Sequence[str], tip: tuple[float, float], carrying: bool) -> bytes:
    """A drawn top view in the robot's frame, flipped like the real camera."""
    image = Image.new("RGB", (640, 480), (171, 137, 102))
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = BOARD_BOX
    for k in (1, 2):
        x = left + (right - left) * k / 3
        y = top + (bottom - top) * k / 3
        draw.rounded_rectangle((x - 7, top + 4, x + 7, bottom - 4), 7, fill=(28, 28, 30))
        draw.rounded_rectangle((left + 4, y - 7, right - 4, y + 7), 7, fill=(28, 28, 30))
    for index, mark in enumerate(board):
        cx, cy = _cell_centre(index)
        if mark == "X":
            _draw_x(draw, cx, cy, 26, 13)
        elif mark == "O":
            draw.ellipse((cx - 30, cy - 30, cx + 30, cy + 30), outline=(240, 238, 232), width=10)
    draw.line((330, 520, tip[0], tip[1]), fill=(196, 198, 202), width=58)
    draw.rounded_rectangle((tip[0] - 26, tip[1] - 26, tip[0] + 26, tip[1] + 26), 6, fill=(34, 34, 36))
    if carrying:
        _draw_x(draw, tip[0], tip[1] - 30, 22, 11)
    draw.text((12, 10), "placeholder frame (no recording found)", fill=(60, 44, 30))
    return _jpeg(image.transpose(Image.Transpose.ROTATE_180))


def _wrist_placeholder(progress: float) -> bytes:
    """A drawn wrist view: the held X growing as the gripper comes down."""
    image = Image.new("RGB", (640, 480), (182, 150, 116))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 60, 640, 120), fill=(26, 26, 28))
    draw.rectangle((40, 60, 100, 480), fill=(26, 26, 28))
    draw.rectangle((520, 60, 580, 480), fill=(26, 26, 28))
    size = 90 + 70 * progress
    draw.line((320 - size, 300, 320 + size, 300), fill=(214, 62, 40), width=44)
    draw.line((320, 300 - size, 320, 300 + size), fill=(214, 62, 40), width=44)
    draw.text((12, 10), "placeholder frame (no recording found)", fill=(60, 44, 30))
    return _jpeg(image)


def placeholder_clip(board: Sequence[str], target: int, frames: int = 10) -> Clip:
    """Draw an arm carrying an X from its rest pose to ``target`` and back."""
    rest = (330.0, 400.0)
    goal = _cell_centre(target)
    tops, wrists = [], []
    placed = list(board)
    for i in range(frames):
        phase = i / (frames - 1)
        reach = min(1.0, phase / 0.6) if phase < 0.6 else max(0.0, (1.0 - phase) / 0.4)
        if phase >= 0.6:
            placed[target] = "X"
        tip = (rest[0] + (goal[0] - rest[0]) * reach, rest[1] + (goal[1] - rest[1]) * reach)
        tops.append(_top_placeholder(placed, tip, carrying=phase < 0.6))
        wrists.append(_wrist_placeholder(min(1.0, phase / 0.6)))
    return Clip(top=tops, wrist=wrists, seconds=frames * 2.0)


# ------------------------------------------------------------------ the script


class Demo:
    """Runs the scripted game against a GameState until ``close`` is called."""

    def __init__(self, state: GameState, clips: Sequence[Clip], speed: float = 1.0) -> None:
        self.state = state
        self.clips = list(clips)
        self.speed = max(0.1, float(speed))
        self._cameras = _Cameras()
        self._quit = threading.Event()
        self._stop_pressed = threading.Event()
        self._threads: list[threading.Thread] = []
        state.on_stop = self._stop_pressed.set

    def start(self) -> "Demo":
        for target, name in ((self._publish_cameras, "xox-demo-cameras"), (self._run, "xox-demo-game")):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)
        return self

    def close(self, timeout: float = 3.0) -> None:
        self._quit.set()
        for thread in self._threads:
            thread.join(timeout)
        self._threads.clear()

    # A real game has camera threads publishing all the time; this stands in.
    def _publish_cameras(self) -> None:
        while not self._quit.wait(0.2):
            with self._cameras.lock:
                top, wrist = self._cameras.top, self._cameras.wrist
            if top is not None:
                self.state.set_frame("top", top)
            if wrist is not None:
                self.state.set_frame("wrist", wrist)

    def _show(self, clip: Clip, index: int) -> None:
        index = max(0, min(index, len(clip.top) - 1))
        with self._cameras.lock:
            self._cameras.top = clip.top[index]
            self._cameras.wrist = clip.wrist[min(index, len(clip.wrist) - 1)]
        self.state.set_frame("top", clip.top[index])
        self.state.set_frame("wrist", clip.wrist[min(index, len(clip.wrist) - 1)])

    def _sleep(self, seconds: float) -> None:
        for _ in range(max(1, int(seconds / self.speed / 0.05))):
            if self._quit.wait(0.05) or self._stop_pressed.is_set():
                raise _Interrupted

    def _clip_for(self, move_number: int, board: Sequence[str], target: int) -> Clip:
        if self.clips:
            return self.clips[move_number % len(self.clips)]
        return placeholder_clip(board, target)

    def _run(self) -> None:
        state = self.state
        while not self._quit.is_set():
            try:
                self._play_one_game()
                self._sleep(10.0)
            except _Interrupted:
                if self._quit.is_set():
                    return
                state.update(phase="stopped", turn=None, target_cell=None)
                state.add_event("demo", "Stopped. A new demo game starts in 5 seconds.")
                self._quit.wait(5.0)
                self._stop_pressed.clear()

    def _play_one_game(self) -> None:
        state = self.state
        board = [" "] * 9
        clip = self._clip_for(0, board, cell_index(SCRIPT[0][0]))
        state.reset()
        self._show(clip, 0)
        state.set_frame("board", board_crop(clip.top[0]))
        state.add_event("game", "New game. The robot plays X, the human plays O.")
        self._sleep(1.5)

        for number, (cell, sentence, reply) in enumerate(SCRIPT):
            target = cell_index(cell)
            label = cell.replace("_", " ")
            if self.clips and number >= 3:
                state.add_event("demo", "No recording of this move: replaying another clip.")

            state.update(turn="x", phase="thinking", target_cell=None)
            self._sleep(2.0)
            state.update(message=sentence, target_cell=cell, phase="waiting_for_x_in_slot")
            state.add_event("claude", f"Picked {label}.")
            self._sleep(1.6)
            state.add_event("vision", "X piece detected in the pick slot.")

            state.update(phase="arm_moving")
            state.add_event("robot", f"Task: pick up the X and place it in the {label} cell.")
            move = state.add_move(cell, hit=None, player="X")
            for index in range(len(clip.top)):
                self._show(clip, index)
                self._sleep(0.7)

            state.update(phase="verifying")
            self._sleep(1.4)
            board[target] = "X"
            state.set_frame("board", board_crop(clip.top[-1]))
            state.update_move(move, hit=True, seconds=clip.seconds)
            state.update(board=board, target_cell=None)
            state.add_event("vision", f"X landed in {label}: hit ({clip.seconds:.0f} s).")
            if self._finish_if_over(board):
                return

            state.update(turn="o", phase="waiting_for_o")
            self._sleep(3.0)
            board[cell_index(reply)] = "O"
            # The next clip opens on the board as the human left it.
            clip = self._clip_for(number + 1, board, cell_index(SCRIPT[number + 1][0]))
            self._show(clip, 0)
            state.update(phase="reading_board")
            self._sleep(1.2)
            state.set_frame("board", board_crop(clip.top[0]))
            state.add_move(reply, player="O")
            state.update(board=board)
            state.add_event("vision", f"Human placed O in {reply.replace('_', ' ')}.")
            if self._finish_if_over(board):
                return

    def _finish_if_over(self, board: Sequence[str]) -> bool:
        result = winner_of(board)
        if result is None:
            return False
        text = {"X": "The robot wins.", "O": "The human wins.", "draw": "Draw."}[result]
        self.state.update(phase="game_over", winner=result, turn=None, target_cell=None)
        self.state.add_event("game", f"Game over. {text}")
        return True


def load_clips(frame_dirs: Optional[Sequence[str]] = None) -> list[Clip]:
    """Clips from the given folders, or from the default recordings if any."""
    directories = [Path(d).expanduser() for d in frame_dirs] if frame_dirs else default_frame_dirs()
    clips = [clip for clip in (load_clip(d) for d in directories) if clip is not None]
    return clips


__all__ = ["BOARD_BOX", "Clip", "Demo", "board_crop", "load_clips", "placeholder_clip"]
