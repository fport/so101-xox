"""The real arm: a Strands robot + the SmolVLA policy, the per-move log and the cameras.

`strands_robots` and `lerobot` are imported on first use, so the rest of the package also loads in
an environment that does not have them.
"""

import argparse
import json
import os
import threading
import time

from PIL import Image

from . import ROOT
from .board import task_sentence
from .i18n import t, yes
from .vision import STOP

# Both must be set before `strands_robots` is imported (that happens in `Arm._setup`).
os.environ.setdefault("STRANDS_TRUST_REMOTE_CODE", "1")
# On macOS strands_robots restarts the process for torchcodec; that makes the questions get asked twice.
os.environ.setdefault("STRANDS_ROBOTS_NO_DYLD_SHIM", "1")

# Camera names the checkpoint expects (same as --rename_map in training).
CAMERA_MAP = {
    "top": "observation.images.camera1",
    "wrist": "observation.images.camera2",
    "front": None,
}


class CamerasBusy(RuntimeError):
    """The cameras are being handed to the robot (or the arm is closed): nobody may open or read them."""


class Arm:
    """The real arm + the policy. Both are loaded on the first move and stay open between moves.

    Every command sent to the arm is written under `outputs/strands_logs/`. Once the arm has gone
    to the cell and returned to the rest pose, the move is finished before the time runs out.

    Cameras: until the robot connects (inside the first `run_policy`) we open the cameras ourselves;
    after that we read the robot's. The hand-off in between is guarded, see `release_camera`.
    """

    # The shoulder and the elbow give the rest pose away; the wrist ends up to 10° off in the recordings too.
    JOINTS = ("shoulder_lift.pos", "elbow_flex.pos")
    FAR = 20.0  # degrees: once the arm has moved this far away, the move counts as started
    NEAR = 8.0  # degrees: commands this close to the start pose count as returned
    NEAR_STEPS = 45  # this many near commands in a row (1.5 s) end the move
    REOPEN_SECONDS = 5.0  # a background reader waits this long before it retries a camera that failed to open

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.robot = None
        self.policy = None
        self.folder = ROOT / "outputs" / "strands_logs" / time.strftime("%Y%m%d-%H%M%S")
        self.move_no = 0
        self.last_seconds = None  # how long the last `run_policy` took
        self.last_log = None  # steps.jsonl of the last move
        self.last_returned = None  # True: the last move ended back in the rest pose; False: the time ran out
        self.before_cleanup = None  # called just before the robot is disconnected (stops the camera pump)
        self._file = None
        self._stop_sent = False
        self._cameras = {}  # name -> a camera we opened ourselves before the arm connects
        self._camera_lock = threading.Lock()  # guards opening, reading and releasing those cameras
        self._handoff = False  # released for the robot, which has not connected yet
        self._closed = False
        self._retry_at = {}  # name -> earliest time a background reader may try to open it again
        self.reference = None  # the frame sent to Claude in the last verification (flipped)
        self.last_seen = None  # the board Claude read in that verification

    def _setup(self) -> None:
        from strands_robots import Robot
        from strands_robots.policies import create_policy

        a = self.args
        camera = {"type": "opencv", "width": 640, "height": 480, "fps": 30}
        self.robot = Robot(
            "so101",
            mode="real",
            driver="lerobot",
            port=a.port,
            id="follower",
            calibration_dir=ROOT / "calibration",
            control_frequency=30.0,
            cameras={
                "top": {**camera, "index_or_path": a.top},
                "wrist": {**camera, "index_or_path": a.wrist},
            },
        )
        # Wrap the reads and writes of the lerobot robot that Strands drives, and log them.
        inner = self.robot.robot
        read, write = inner.get_observation, inner.send_action

        def get_observation():
            obs = read()
            self._log_observation(obs)
            return obs

        def send_action(action):
            result = write(action)
            self._log_command(action)
            # A stop that arrived before the task started is forgotten by Strands; ask again from inside the loop.
            if STOP.is_set() and not self._stop_sent:
                self._stop_sent = True
                self.robot.stop_task()
            return result

        inner.get_observation, inner.send_action = get_observation, send_action
        print(t("loading_policy", model=a.model))
        self.policy = create_policy(
            "lerobot_local",
            pretrained_name_or_path=a.model,
            embodiment="so101_real",
            device=a.device,
            obs_rename_override=CAMERA_MAP,
        )

    def _log_observation(self, obs: dict) -> None:
        if self._file is None:
            return
        state = {k: float(v) for k, v in obs.items() if k.endswith(".pos")}
        if self._start is None:
            self._start = state
        self._observation_no += 1
        self._file.write(json.dumps({"t": time.time(), "state": state}) + "\n")
        for name in ("top", "wrist"):
            if name in obs:
                Image.fromarray(obs[name]).save(
                    self._move_folder / f"{name}_{self._observation_no:03d}.jpg", quality=90
                )

    def _log_command(self, action: dict) -> None:
        if self._file is None or self._start is None:
            return
        command = {k: float(v) for k, v in action.items() if k.endswith(".pos")}
        self._file.write(json.dumps({"t": time.time(), "command": command}) + "\n")
        diff = max(abs(command[k] - self._start[k]) for k in self.JOINTS)
        if diff > self.FAR:
            self._moved_away = True
        self._near = self._near + 1 if self._moved_away and diff < self.NEAR else 0
        if self._near >= self.NEAR_STEPS and not self._done:
            self._done = True
            self.robot.stop_task()

    def play(self, cell: str, confirm: bool = True) -> tuple[bool, str]:
        """Plays a single move; with `confirm` on it asks the operator first. Returns (did the arm run, note)."""
        task = task_sentence(cell)
        print(t("task_sentence", task=task))
        if self.args.dry_run:
            return True, t("dry_run")
        if confirm and not yes(t("confirm_move")):
            return False, t("not_confirmed")
        self.release_camera(handoff=True)
        try:
            if self.robot is None:
                self._setup()
            if STOP.is_set():  # stopped while the policy was loading: do not start the move
                return False, t("stopped")
            self.move_no += 1
            self._move_folder = self.folder / f"move{self.move_no:02d}_{cell.replace(' ', '_')}"
            self._move_folder.mkdir(parents=True)
            self._start, self._observation_no, self._moved_away, self._near, self._done = None, 0, False, 0, False
            self._stop_sent = False
            self.last_log, self.last_returned = self._move_folder / "steps.jsonl", None
            self._file = self.last_log.open("w")
            t0 = time.time()
            try:
                result = self.robot.run_policy(self.policy, instruction=task, duration=self.args.duration)
            except KeyboardInterrupt:
                self.robot.stop_task()
                return False, t("stopped_ctrl_c")
            finally:
                self.last_seconds = time.time() - t0
                self._file.close()
                self._file = None
        finally:
            # Connected or not, the connection attempt is over: frames may be asked for again.
            self._handoff = False
        if STOP.is_set():
            return False, t("stopped")
        if self._done:
            self.last_returned = True
            return True, t("returned_to_rest", seconds=self.last_seconds)
        if result["status"] == "success":
            self.last_returned = False
            return True, t("time_ran_out", seconds=self.args.duration)
        return False, result["content"][0]["text"]

    # ------------------------------------------------------------------ cameras

    def _robot_connected(self) -> bool:
        """True once the robot holds the cameras. Only reads flags: no camera frame, no serial traffic."""
        try:
            return self.robot is not None and bool(self.robot.robot.is_connected)
        except Exception:  # noqa: BLE001 - a robot that cannot answer is not connected
            return False

    def _open(self, name: str):
        """Opens the camera `name` ourselves (the caller holds the camera lock)."""
        from lerobot.cameras.opencv import OpenCVCamera, OpenCVCameraConfig

        index = {"top": self.args.top, "wrist": self.args.wrist}[name]
        camera = OpenCVCamera(OpenCVCameraConfig(index_or_path=index, width=640, height=480, fps=30))
        camera.connect()
        self._cameras[name] = camera
        time.sleep(1.0)
        return camera

    def _grab(self, name: str, may_open: bool):
        """One frame of the camera `name`, from the robot if it is connected, else from our own camera."""
        with self._camera_lock:
            if self._robot_connected():
                return self.robot.robot.cameras[name].read_latest()
            if self._handoff or self._closed:
                raise CamerasBusy(name)
            camera = self._cameras.get(name)
            if camera is None:
                if not may_open:
                    raise CamerasBusy(name)
                camera = self._open(name)
            return camera.read_latest()

    def frame(self, name: str = "top"):
        """Current frame from the `top` camera: the arm's camera if it is connected, else the one we opened.

        While the cameras are being handed to the robot this waits instead of opening them again.
        """
        for attempt in range(10):
            try:
                while True:
                    try:
                        return self._grab(name, may_open=True)
                    except CamerasBusy:
                        if STOP.is_set() or self._closed:
                            raise KeyboardInterrupt from None
                        time.sleep(0.1)
            except TimeoutError:
                if attempt == 9:
                    raise
                time.sleep(0.2)

    def peek(self, name: str):
        """A frame for a background reader (the dashboard's camera pump), or None if there is none to give.

        Never waits for a hand-off and never raises for a busy, stale or broken camera. It opens our own
        cameras only before the robot exists; from then on the robot's cameras are the only source.
        """
        may_open = self.robot is None and time.monotonic() >= self._retry_at.get(name, 0.0)
        try:
            return self._grab(name, may_open)
        except CamerasBusy:
            return None
        except TimeoutError:  # stale frame
            return None
        except Exception:  # noqa: BLE001 - the video is a convenience; the game must not notice
            if may_open and name not in self._cameras:
                self._retry_at[name] = time.monotonic() + self.REOPEN_SECONDS
            return None

    def release_camera(self, handoff: bool = False) -> None:
        """Closes the cameras we opened ourselves before the arm connects; the arm will open the same cameras.

        With `handoff` the cameras now belong to the robot: until it reports connected (or the
        connection attempt ends), `frame` waits and `peek` returns None instead of opening them again.
        """
        with self._camera_lock:
            if handoff:
                self._handoff = True
            cameras, self._cameras = self._cameras, {}
            errors = []
            for camera in cameras.values():
                try:
                    camera.disconnect()
                except Exception as error:  # noqa: BLE001 - still close the other camera, then report
                    errors.append(error)
            if errors:
                raise errors[0]

    def close(self) -> None:
        with self._camera_lock:
            self._closed = True
        self.release_camera()
        if self.robot is None:
            return
        input(t("closing"))
        if self.before_cleanup is not None:
            self.before_cleanup()
        self.robot.cleanup()
        print(t("log_folder", folder=self.folder))
