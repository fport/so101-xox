"""Runs `lerobot-rollout` as is and additionally logs the commands sent to the arm and the arm's state.

The flags are exactly those of `lerobot-rollout`; only the name of the command changes:

    python scripts/rollout_logged.py --strategy.type=base --policy.path=... (the rest is the same)

Output goes to `outputs/rollout_logs/<time>/`: `steps.jsonl` (joint angles and the command sent at every step),
one `top` / `wrist` frame per second. At the end it prints a short summary: did the model ask for motion,
did the arm follow.

Terminal messages are English by default; `--lang tr` or XOX_LANG=tr switches them to Turkish
(`--lang` is removed before the remaining flags are handed to `lerobot-rollout`).
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

import lerobot.rollout.context as context
from lerobot.scripts.lerobot_rollout import main as rollout

ROOT = Path(__file__).resolve().parent.parent

# Terminal messages. English is the default; `--lang tr` or XOX_LANG=tr selects Turkish.
MESSAGES = {
    "no_commands": {
        "en": "No command was sent to the arm.",
        "tr": "Kola hiç komut gitmedi.",
    },
    "totals": {
        "en": "\n{count} commands, {seconds:.1f} s",
        "tr": "\n{count} komut, {seconds:.1f} sn",
    },
    "joints": {
        "en": "joints                          :",
        "tr": "eklemler                        :",
    },
    "start_pose": {
        "en": "start pose                      :",
        "tr": "başlangıç pozu                  :",
    },
    "command_max": {
        "en": "commands, max from start        :",
        "tr": "komutlar başlangıçtan en çok    :",
    },
    "arm_max": {
        "en": "arm, max from start             :",
        "tr": "kol başlangıçtan en çok         :",
    },
    "log_folder": {
        "en": "Log: {folder}",
        "tr": "Kayıt: {folder}",
    },
    "bad_lang": {
        "en": "--lang must be en or tr",
        "tr": "--lang en ya da tr olmalı",
    },
}

LANG = os.environ.get("XOX_LANG", "en").strip().lower()
if LANG not in ("en", "tr"):
    LANG = "en"


def t(key: str, **fmt) -> str:
    """Message `key` in the selected language."""
    return MESSAGES[key][LANG].format(**fmt)


def pop_lang(argv: list[str]) -> tuple[str, list[str]]:
    """Takes `--lang` out of the arguments; everything else stays, in order, for `lerobot-rollout`."""
    lang, rest = LANG, []
    args = iter(argv)
    for arg in args:
        if arg == "--lang":
            lang = next(args, "")
        elif arg.startswith("--lang="):
            lang = arg.split("=", 1)[1]
        else:
            rest.append(arg)
    if lang not in ("en", "tr"):
        sys.exit(t("bad_lang"))
    return lang, rest


def logged(make_robot, folder: Path, steps: list):
    """Wraps the robot factory: logs the `get_observation` and `send_action` calls."""

    def make(cfg):
        robot = make_robot(cfg)
        read, write = robot.get_observation, robot.send_action
        last = {}
        file = (folder / "steps.jsonl").open("w")

        def get_observation():
            last["obs"] = read()
            return last["obs"]

        def send_action(action):
            sent = write(action)
            obs = last.get("obs", {})
            step = {
                "t": time.time(),
                "state": {k: float(v) for k, v in obs.items() if k.endswith(".pos")},
                "command": {k: float(v) for k, v in action.items() if k.endswith(".pos")},
            }
            steps.append(step)
            file.write(json.dumps(step) + "\n")
            if len(steps) % 30 == 1:
                for name, value in obs.items():
                    if isinstance(value, np.ndarray) and value.ndim == 3:
                        Image.fromarray(value).save(folder / f"{name}_{len(steps) // 30:03d}.jpg", quality=90)
            return sent

        robot.get_observation = get_observation
        robot.send_action = send_action
        return robot

    return make


def summary(steps: list) -> None:
    if not steps:
        print(t("no_commands"))
        return
    names = list(steps[0]["command"])
    state = np.array([[s["state"].get(k, np.nan) for k in names] for s in steps])
    command = np.array([[s["command"][k] for k in names] for s in steps])
    np.set_printoptions(precision=1, suppress=True)
    print(t("totals", count=len(steps), seconds=steps[-1]["t"] - steps[0]["t"]))
    print(t("joints"), [k.removesuffix(".pos") for k in names])
    print(t("start_pose"), state[0])
    print(t("command_max"), np.abs(command - state[0]).max(0))
    print(t("arm_max"), np.abs(state - state[0]).max(0))


def main() -> None:
    global LANG
    LANG, sys.argv[1:] = pop_lang(sys.argv[1:])
    folder = ROOT / "outputs" / "rollout_logs" / time.strftime("%Y%m%d-%H%M%S")
    folder.mkdir(parents=True)
    steps: list = []
    context.make_robot_from_config = logged(context.make_robot_from_config, folder, steps)
    try:
        rollout()
    finally:
        summary(steps)
        print(t("log_folder", folder=folder))


if __name__ == "__main__":
    main()
