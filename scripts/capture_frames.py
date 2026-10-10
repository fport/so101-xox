"""Saves what the arm sees right now: frames from both cameras and the joint angles.

Opens the cameras with the same settings as `lerobot-rollout`. Writes nothing to the motors, does not enable torque.

    python scripts/capture_frames.py                 # writes under outputs/live/
    python scripts/capture_frames.py --top 0 --wrist 1

Terminal messages are English by default; `--lang tr` or XOX_LANG=tr switches them to Turkish.
"""

import argparse
import json
import os
import time
from pathlib import Path

from PIL import Image

from lerobot.cameras.opencv import OpenCVCamera, OpenCVCameraConfig
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

ROOT = Path(__file__).resolve().parent.parent

# Terminal messages. English is the default; `--lang tr` or XOX_LANG=tr selects Turkish.
MESSAGES = {
    "written": {
        "en": "{count} frames x 2 cameras and the joint angles were written: {out}",
        "tr": "{count} kare x 2 kamera ve eklem açıları yazıldı: {out}",
    },
}

LANG = os.environ.get("XOX_LANG", "en").strip().lower()
if LANG not in ("en", "tr"):
    LANG = "en"


def t(key: str, **fmt) -> str:
    """Message `key` in the selected language."""
    return MESSAGES[key][LANG].format(**fmt)


def main() -> None:
    global LANG
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", default="/dev/cu.usbmodem5AB01794851", help="follower port")
    p.add_argument("--top", type=int, default=0, help="top camera index")
    p.add_argument("--wrist", type=int, default=1, help="wrist camera index")
    p.add_argument("--count", type=int, default=5, help="number of frames per camera")
    p.add_argument("--out", type=Path, default=ROOT / "outputs" / "live")
    p.add_argument(
        "--lang", choices=["en", "tr"], default=LANG, help="terminal message language (default: en, or $XOX_LANG)"
    )
    args = p.parse_args()
    LANG = args.lang

    args.out.mkdir(parents=True, exist_ok=True)
    cameras = {
        name: OpenCVCamera(OpenCVCameraConfig(index_or_path=i, width=640, height=480, fps=30))
        for name, i in (("top", args.top), ("wrist", args.wrist))
    }
    for camera in cameras.values():
        camera.connect()
    try:
        time.sleep(1.0)
        for n in range(args.count):
            for name, camera in cameras.items():
                Image.fromarray(camera.read_latest()).save(args.out / f"{name}_{n}.png")
            time.sleep(0.4)
    finally:
        for camera in cameras.values():
            camera.disconnect()

    arm = SO101Follower(SO101FollowerConfig(port=args.port, id="follower", calibration_dir=ROOT / "calibration"))
    arm.bus.connect()
    try:
        joints = {f"{motor}.pos": float(value) for motor, value in arm.bus.sync_read("Present_Position").items()}
    finally:
        arm.bus.disconnect(disable_torque=False)
    (args.out / "joints.json").write_text(json.dumps(joints, indent=2))

    print(t("written", count=args.count, out=args.out))
    print({k: round(v, 1) for k, v in joints.items()})


if __name__ == "__main__":
    main()
