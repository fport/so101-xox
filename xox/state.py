"""Thread-safe game state shared between the game loop and the dashboard.

The game loop writes (``update``, ``add_event``, ``add_move``, ``set_frame``);
the dashboard server reads (``snapshot``, ``frame``, ``wait_frame``). Nothing in
here opens a camera, a serial port or a network connection.

Board convention: nine cells in row-major order, rows top/middle/bottom and
columns left/center/right, in the robot's frame (top row = far from the arm).
"""

from __future__ import annotations

import io
import re
import threading
import time
from collections import deque
from typing import Any, Callable, Optional

import numpy as np
from PIL import Image

CELLS = (
    "top_left", "top_center", "top_right",
    "middle_left", "middle_center", "middle_right",
    "bottom_left", "bottom_center", "bottom_right",
)

# Phase keys the dashboard knows how to describe. Other strings are allowed and
# are shown as-is.
PHASES = (
    "idle",
    "thinking",
    "waiting_for_x_in_slot",
    "arm_moving",
    "verifying",
    "waiting_for_o",
    "reading_board",
    "game_over",
    "stopped",
)

FRAME_NAMES = ("top", "wrist", "board")

_FRAME_NAME_RE = re.compile(r"^[a-z0-9_]{1,32}$")
_EMPTY_MARKS = {"", " ", ".", "-", "_", "0"}
_UNSET = object()


def cell_name(cell: Any) -> Optional[str]:
    """Normalise a cell given as a name, an index 0-8 or a (row, col) pair."""
    if cell is None:
        return None
    if isinstance(cell, (int, np.integer)) and not isinstance(cell, bool):
        if 0 <= int(cell) < 9:
            return CELLS[int(cell)]
        raise ValueError(f"cell index out of range: {cell!r}")
    if isinstance(cell, (tuple, list)) and len(cell) == 2:
        row, col = int(cell[0]), int(cell[1])
        if 0 <= row < 3 and 0 <= col < 3:
            return CELLS[row * 3 + col]
        raise ValueError(f"cell (row, col) out of range: {cell!r}")
    if isinstance(cell, str):
        key = re.sub(r"[\s\-]+", "_", cell.strip().lower())
        if key in ("center", "middle"):
            key = "middle_center"
        if key in CELLS:
            return key
    raise ValueError(f"unknown cell: {cell!r}")


def cell_index(cell: Any) -> Optional[int]:
    """Row-major index 0-8 of a cell, or None."""
    name = cell_name(cell)
    return None if name is None else CELLS.index(name)


def _normalise_board(board: Any) -> list[str]:
    cells = list(board)
    if len(cells) != 9:
        raise ValueError(f"board needs 9 cells, got {len(cells)}")
    out = []
    for mark in cells:
        text = "" if mark is None else str(mark).strip().upper()
        if text in ("X", "O"):
            out.append(text)
        elif text in _EMPTY_MARKS:
            out.append(" ")
        else:
            raise ValueError(f"board mark must be 'X', 'O' or ' ', got {mark!r}")
    return out


def _normalise_turn(turn: Any) -> Optional[str]:
    if turn is None:
        return None
    text = str(turn).strip().lower()
    if text in ("x", "o"):
        return text
    raise ValueError(f"turn must be 'x', 'o' or None, got {turn!r}")


def _normalise_winner(winner: Any) -> Optional[str]:
    if winner is None:
        return None
    text = str(winner).strip().lower()
    if text in ("x", "o"):
        return text.upper()
    if text == "draw":
        return "draw"
    raise ValueError(f"winner must be 'X', 'O', 'draw' or None, got {winner!r}")


def _to_rgb_array(image: Any) -> np.ndarray:
    """Copy an image-like array into a contiguous uint8 HxW or HxWx3 array."""
    arr = np.asarray(image)
    if arr.ndim == 3 and arr.shape[0] in (1, 3) and arr.shape[2] not in (1, 3, 4):
        arr = np.moveaxis(arr, 0, -1)  # channels-first -> channels-last
    if arr.ndim == 3 and arr.shape[2] == 1:
        arr = arr[:, :, 0]
    if arr.ndim == 3 and arr.shape[2] == 4:
        arr = arr[:, :, :3]
    if arr.ndim not in (2, 3) or (arr.ndim == 3 and arr.shape[2] != 3):
        raise ValueError(f"unsupported image shape: {arr.shape}")
    if arr.dtype != np.uint8:
        arr = arr.astype(np.float32)
        if arr.size and float(arr.max()) <= 1.0:
            arr = arr * 255.0
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    return np.array(arr, dtype=np.uint8, order="C", copy=True)


class _Frame:
    __slots__ = ("seq", "raw", "jpeg", "width", "height", "t", "encode_lock")

    def __init__(self) -> None:
        self.seq = 0
        self.raw: Any = None  # np.ndarray or PIL.Image waiting to be encoded
        self.jpeg: Optional[bytes] = None
        self.width = 0
        self.height = 0
        self.t = 0.0
        self.encode_lock = threading.Lock()


class GameState:
    """Everything the dashboard shows, guarded by one lock.

    Writers never block on JPEG encoding: ``set_frame`` only keeps a copy of
    the pixels, and the JPEG is produced once, on demand, when a viewer asks
    for that frame. Frames nobody watches are therefore never encoded.
    """

    def __init__(self, max_events: int = 200, jpeg_quality: int = 80) -> None:
        self._lock = threading.RLock()
        self._frame_cond = threading.Condition(threading.Lock())
        self._frames: dict[str, _Frame] = {}
        self._jpeg_quality = int(jpeg_quality)
        self._events: deque[dict] = deque(maxlen=int(max_events))
        self._event_id = 0
        self._version = 0
        self._started = time.time()
        self._stop_requested = False
        # Called (with no arguments) when someone presses Stop on the dashboard.
        self.on_stop: Optional[Callable[[], None]] = None
        self._board = [" "] * 9
        self._turn: Optional[str] = None
        self._phase = "idle"
        self._target_cell: Optional[str] = None
        self._message = ""
        self._winner: Optional[str] = None
        self._moves: list[dict] = []

    # ------------------------------------------------------------------ state

    def update(self, **fields: Any) -> int:
        """Set any of board, turn, phase, target_cell, message, winner.

        All given fields change together under the lock. Returns the state
        version, which only grows when something actually changed.
        """
        allowed = {"board", "turn", "phase", "target_cell", "message", "winner"}
        unknown = set(fields) - allowed
        if unknown:
            raise TypeError(f"unknown GameState field(s): {', '.join(sorted(unknown))}")
        new: dict[str, Any] = {}
        if "board" in fields:
            new["_board"] = _normalise_board(fields["board"])
        if "turn" in fields:
            new["_turn"] = _normalise_turn(fields["turn"])
        if "phase" in fields:
            new["_phase"] = str(fields["phase"] or "idle")
        if "target_cell" in fields:
            new["_target_cell"] = cell_name(fields["target_cell"])
        if "message" in fields:
            new["_message"] = "" if fields["message"] is None else str(fields["message"])
        if "winner" in fields:
            new["_winner"] = _normalise_winner(fields["winner"])
        with self._lock:
            changed = False
            for attr, value in new.items():
                if getattr(self, attr) != value:
                    setattr(self, attr, value)
                    changed = True
            if changed:
                self._version += 1
            return self._version

    def add_event(self, kind: str, text: str) -> None:
        """Append a line to the bounded event log shown on the dashboard."""
        with self._lock:
            self._event_id += 1
            self._events.append(
                {"id": self._event_id, "t": time.time(), "kind": str(kind), "text": str(text)}
            )
            self._version += 1

    def add_move(
        self,
        cell: Any,
        hit: Optional[bool] = None,
        seconds: Optional[float] = None,
        player: str = "X",
    ) -> int:
        """Record a move and return its position in ``moves``.

        ``hit`` is True when the piece landed in the cell, False for a miss and
        None while that is still unknown (see ``update_move``).
        """
        mark = str(player).strip().upper()
        if mark not in ("X", "O"):
            raise ValueError(f"player must be 'X' or 'O', got {player!r}")
        move = {
            "player": mark,
            "cell": cell_name(cell),
            "hit": None if hit is None else bool(hit),
            "seconds": None if seconds is None else round(float(seconds), 2),
        }
        with self._lock:
            self._moves.append(move)
            self._version += 1
            return len(self._moves) - 1

    def update_move(self, index: int = -1, *, hit: Any = _UNSET, seconds: Any = _UNSET) -> None:
        """Fill in ``hit`` and/or ``seconds`` of a recorded move (default: the last)."""
        with self._lock:
            move = self._moves[index]
            if hit is not _UNSET:
                move["hit"] = None if hit is None else bool(hit)
            if seconds is not _UNSET:
                move["seconds"] = None if seconds is None else round(float(seconds), 2)
            self._version += 1

    def reset(self) -> None:
        """Start a new game: clear board, moves, winner, target and message.

        The event log and the camera frames are kept.
        """
        with self._lock:
            self._board = [" "] * 9
            self._turn = None
            self._phase = "idle"
            self._target_cell = None
            self._message = ""
            self._winner = None
            self._moves = []
            self._stop_requested = False
            self._started = time.time()
            self._version += 1

    def snapshot(self) -> dict:
        """JSON-serialisable copy of the state, without image bytes."""
        with self._frame_cond:
            now = time.time()
            frames = {
                name: {
                    "seq": f.seq,
                    "age": round(now - f.t, 3),
                    "width": f.width,
                    "height": f.height,
                }
                for name, f in self._frames.items()
                if f.seq
            }
        with self._lock:
            target = self._target_cell
            return {
                "version": self._version,
                "time": time.time(),
                "started": self._started,
                "board": list(self._board),
                "turn": self._turn,
                "phase": self._phase,
                "target_cell": target,
                "target_index": None if target is None else CELLS.index(target),
                "message": self._message,
                "winner": self._winner,
                "moves": [dict(m) for m in self._moves],
                "events": [dict(e) for e in self._events],
                "frames": frames,
                "stop_requested": self._stop_requested,
                "can_stop": self.on_stop is not None,
            }

    # ------------------------------------------------------------------- stop

    @property
    def stop_requested(self) -> bool:
        """True once Stop was pressed; cleared by ``clear_stop`` or ``reset``."""
        with self._lock:
            return self._stop_requested

    def request_stop(self) -> bool:
        """Flag a stop request and call ``on_stop`` if one is set.

        Returns True when a callback ran without raising.
        """
        callback = self.on_stop
        with self._lock:
            self._stop_requested = True
            self._version += 1
        self.add_event("stop", "Stop requested from the dashboard")
        if callback is None:
            return False
        try:
            callback()
        except Exception as exc:  # the dashboard must survive a broken callback
            self.add_event("error", f"Stop callback failed: {exc!r}")
            return False
        return True

    def clear_stop(self) -> None:
        with self._lock:
            if self._stop_requested:
                self._stop_requested = False
                self._version += 1

    # ----------------------------------------------------------------- frames

    def set_frame(self, name: str, image: Any) -> None:
        """Publish the latest image for a camera (``top``, ``wrist``, ``board``).

        ``image`` is an RGB ``numpy`` array (HxWx3 uint8; float 0-1 and
        channels-first are converted), a PIL image, or ``bytes`` holding an
        already encoded JPEG. The pixels are copied, so the caller may reuse
        its buffer. Encoding is deferred until a viewer asks for the frame.
        """
        if not _FRAME_NAME_RE.match(name):
            raise ValueError(f"invalid frame name: {name!r}")
        raw: Any = None
        jpeg: Optional[bytes] = None
        if isinstance(image, (bytes, bytearray, memoryview)):
            jpeg = bytes(image)
            try:
                width, height = Image.open(io.BytesIO(jpeg)).size  # header only
            except Exception as exc:
                raise ValueError("bytes passed to set_frame must be an encoded image") from exc
        elif isinstance(image, Image.Image):
            raw = image.copy()
            width, height = raw.size
        else:
            raw = _to_rgb_array(image)
            height, width = raw.shape[:2]
        with self._frame_cond:
            frame = self._frames.get(name)
            if frame is None:
                frame = self._frames[name] = _Frame()
            frame.seq += 1
            frame.raw = raw
            frame.jpeg = jpeg
            frame.width = width
            frame.height = height
            frame.t = time.time()
            self._frame_cond.notify_all()

    def frame(self, name: str) -> Optional[bytes]:
        """Latest JPEG bytes for ``name``, or None if no frame was set yet."""
        return self._frame_with_seq(name)[1]

    def frame_seq(self, name: str) -> int:
        """How many frames were published under ``name`` (0 = none yet)."""
        with self._frame_cond:
            frame = self._frames.get(name)
            return frame.seq if frame else 0

    def wait_frame(
        self, name: str, after_seq: int = 0, timeout: float = 1.0
    ) -> tuple[int, Optional[bytes]]:
        """Block until a frame newer than ``after_seq`` exists, or ``timeout``.

        Returns ``(seq, jpeg)``; on timeout ``seq`` equals the current sequence
        number, which may still be ``after_seq``.
        """
        deadline = time.monotonic() + timeout
        with self._frame_cond:
            while True:
                frame = self._frames.get(name)
                if frame is not None and frame.seq > after_seq:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return (frame.seq if frame else 0), None
                self._frame_cond.wait(remaining)
        return self._frame_with_seq(name)

    def _frame_with_seq(self, name: str) -> tuple[int, Optional[bytes]]:
        with self._frame_cond:
            frame = self._frames.get(name)
            if frame is None or frame.seq == 0:
                return 0, None
            if frame.jpeg is not None:
                return frame.seq, frame.jpeg
        # Encode outside the shared lock; one encoder per camera at a time.
        with frame.encode_lock:
            with self._frame_cond:
                seq, raw, jpeg = frame.seq, frame.raw, frame.jpeg
            if jpeg is not None:
                return seq, jpeg
            jpeg = self._encode(raw)
            with self._frame_cond:
                if frame.seq == seq:
                    frame.jpeg = jpeg
                    frame.raw = None
            return seq, jpeg

    def _encode(self, raw: Any) -> bytes:
        image = raw if isinstance(raw, Image.Image) else Image.fromarray(raw)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=self._jpeg_quality)
        return buffer.getvalue()
