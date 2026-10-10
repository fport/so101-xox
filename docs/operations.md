# Operations

**English** · [Türkçe](tr/operations.md)

Day-to-day notes for the hardware, the datasets on Hugging Face and the training run: what to check at the start of a session, the commands for the dataset repos, and the pitfalls met so far. The ports and camera indices are those of the setup the data was recorded on. All commands are run from the repo root, in the `.venv` environment (`uv sync`, then `source .venv/bin/activate`).

## Hardware

| | |
|---|---|
| Follower | `/dev/cu.usbmodem5AB01794851`, id `follower`, ~12.5 V |
| Leader | `/dev/cu.usbmodem5A7C1232561`, id `leader`, ~5.5 V |
| Calibration | `calibration/{follower,leader}.json` (2026-09-13), `--robot.calibration_dir=calibration` |
| Camera `top` | OpenCV index `0`, 640×480 @ 30, looks at the board from across the arm |
| Camera `wrist` | OpenCV index `1`, 640×480 @ 30, on the wrist |

Port names can change when a cable is plugged in again: `ls /dev/cu.usbmodem*`. Which one is which can be told from the voltage.

Camera indices can change too: the wrist used to be 0 and the top 1; on 2026-10-06, in the first attempt, the top moved to 1. The MacBook camera and the iPhone (Continuity Camera) also show up in the list. Run the check below at the start of every session.

## Hugging Face

The datasets are under the `fport` account, **public** (decided on 2026-10-10; the plan had been to keep them private while recording). Naming follows the `tic-tac-toe-so101-<part>-clean-vN` scheme of an earlier open SO-101 tic-tac-toe project:

| Repo | Contents |
|---|---|
| `fport/tic-tac-toe-so101-x-round1` | Raw recording of round 1 (pilot): 46 episodes, 9 blocks × 5 + #45 (a repeat of #15). Locally `data/tic-tac-toe-so101-x-round1`. |
| `fport/tic-tac-toe-so101-x-round1-clean-v1` | Clean version of round 1 (2026-10-10): raw #15 deleted, 45 episodes, 5 per cell. The numbers shift: raw #16–#45 → clean #15–#44. Locally `data/tic-tac-toe-so101-x-round1-clean-v1`. |
| `fport/tic-tac-toe-so101-x-round2` … | Raw recordings of later rounds (none yet) |
| `fport/tic-tac-toe-so101-x-clean-v1` | Training set: the cleaned rounds merged (none yet) |

Raw repos are not touched after recording. Cleaning and merging always produce a new `-clean-vN` repo; if something goes wrong the raw recording is still there. When the O pieces come, the same scheme continues with `-o-` / `-xo-`.

**Once:** `hf auth login` (a token with write access); check with `hf auth whoami`.

**Adding episodes to the same round:** The recording command ([`recording.md`](recording.md)) + `--resume=true`, `--dataset.num_episodes` = the number of episodes to add. When recording ends, lerobot uploads the whole dataset to HF by itself. A local copy is required; if you are on another computer, download it first:

```bash
hf download fport/tic-tac-toe-so101-x-round1 --repo-type dataset --local-dir data/tic-tac-toe-so101-x-round1
```

**A new round:** In the command, change `--dataset.repo_id` and `--dataset.root` to `-round2` and start without `--resume`. Always keep `--dataset.private=true --dataset.no_stamp=true`.

**Uploading by hand** (if recording closed without uploading):

```bash
hf upload fport/tic-tac-toe-so101-x-round1 data/tic-tac-toe-so101-x-round1 . --repo-type dataset --private
```

**Deleting bad episodes and making a clean copy** (the numbers are an example):

```bash
lerobot-edit-dataset \
  --repo_id=fport/tic-tac-toe-so101-x-round1 --root=data/tic-tac-toe-so101-x-round1 \
  --new_repo_id=fport/tic-tac-toe-so101-x-round1-clean-v1 --new_root=data/tic-tac-toe-so101-x-round1-clean-v1 \
  --operation.type=delete_episodes --operation.episode_indices="[3, 17]"
hf upload fport/tic-tac-toe-so101-x-round1-clean-v1 data/tic-tac-toe-so101-x-round1-clean-v1 . --repo-type dataset --private
hf repos tag create fport/tic-tac-toe-so101-x-round1-clean-v1 v3.0 --repo-type dataset
```

**Merging rounds:**

```bash
lerobot-edit-dataset \
  --new_repo_id=fport/tic-tac-toe-so101-x-clean-v1 --new_root=data/tic-tac-toe-so101-x-clean-v1 \
  --operation.type=merge \
  --operation.repo_ids="['fport/tic-tac-toe-so101-x-round1-clean-v1', 'fport/tic-tac-toe-so101-x-round2-clean-v1']" \
  --operation.roots="['data/tic-tac-toe-so101-x-round1-clean-v1', 'data/tic-tac-toe-so101-x-round2-clean-v1']"
hf upload fport/tic-tac-toe-so101-x-clean-v1 data/tic-tac-toe-so101-x-clean-v1 . --repo-type dataset --private
hf repos tag create fport/tic-tac-toe-so101-x-clean-v1 v3.0 --repo-type dataset
```

**Fixing a wrong task label** (changes in place; back up the folder first):

```bash
lerobot-edit-dataset --repo_id=fport/tic-tac-toe-so101-x-round1 --root=data/tic-tac-toe-so101-x-round1 \
  --operation.type=modify_tasks \
  --operation.episode_tasks='{"22": "put the red X in the middle left cell"}'
```

Then to HF: `python -c "from lerobot.datasets.lerobot_dataset import LeRobotDataset as D; D('fport/tic-tac-toe-so101-x-round1', root='data/tic-tac-toe-so101-x-round1').push_to_hub(private=True)"` (if the repo already exists it does not change the visibility; it moves the `v3.0` tag to the last commit).

- **Do not use** `lerobot-edit-dataset --push_to_hub=true`: it uploads without the private setting, and on a personal account the repo is created public. Upload with `hf upload --private` as above.
- The `v3.0` tag is needed for LeRobot to find the dataset on the Hub by its version. `lerobot-record` adds it by itself; for a manual upload the command above adds it.
- **Making it public** (once the cleaned version is ready): `hf repos settings fport/<repo> --repo-type dataset --public` (`--no-private` changes nothing), or on HF the repo page → Settings.
- **Renaming a repo:** `hf repos move fport/<old> fport/<new> --repo-type dataset`. Move the local folder to the same name too.

## Training (Colab)

[`notebooks/train_smolvla_round1.ipynb`](../notebooks/train_smolvla_round1.ipynb): SmolVLA on the round 1 clean set, 20k steps on an A100 (3 h 45 min measured on an 80 GB A100). In Colab open it with File → Upload notebook, set the Runtime to A100, add an `HF_TOKEN` with write access to Secrets, run the cells in order. The model is uploaded as `fport/smolvla-tic-tac-toe-so101-x-round1-20k` (private at first, public since 2026-10-11); intermediate checkpoints are in the repo under `checkpoints/<step>/`.

## At the start of every session (if the cables were unplugged)

1. **Positions:** Are the arm base, the board and the `top` camera on their tape marks? If the camera angle changes, the recordings no longer match each other. The easiest is to never move the camera and its stand, and to unplug the cable on the Mac side.
2. **Power:** Is the follower's 12 V adapter plugged in?
3. **Ports:** The output of `ls /dev/cu.usbmodem*` must contain `5AB01794851` (follower) and `5A7C1232561` (leader). The names come from the serial number of the USB chip and usually do not change. If they did, update the ports in the commands.
4. **Cameras:** Run `lerobot-find-cameras opencv` and look at the pictures in `outputs/captured_images/`. Is `top` still 0 and `wrist` still 1? The indices can swap depending on the plugging order; if an iPhone is nearby, Continuity Camera can enter the list as well. Compare the new `top` frame with [`reference_top.png`](reference_top.png) (2026-10-06, start of the pilot recording): are the board and the slots in the same place in the frame? `outputs/` does not go to git, the MacBook camera's frame can stay there.
5. **Calibration:** Do nothing. Unplugging a cable does not break the calibration; it is needed again only if a motor is taken out and put back.
6. **Light:** The same light throughout the pilot: the same lamps, the curtain in the same state.

## Known pitfalls

- Do not pass `--robot.max_relative_target`: at a value of 2 the elbow locked up against gravity.
- While teleop or recording is running, do not read anything else from the same port; the connection drops.
- At the calibration question press ENTER (use the file). `c` recalibrates.
- `lerobot-find-cameras` needs the macOS camera permission; run it from your own terminal.
- torchcodec does not load with the FFmpeg on this Mac: use `--dataset.video_backend=pyav` for training and reading.
- When recording, `--dataset.streaming_encoding=true --dataset.encoder_threads=2` removes the freeze between episodes.
- The `Exceeded gRPC proxy server memory limit` message in Rerun and the `Record loop is running slower` warning at the start of recording are harmless (in episode 0, 750 frames were recorded in 25 s, no loss).
