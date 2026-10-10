# Plan

**English** · [Türkçe](tr/plan.md)

Source: `SO-101_XOX_Proje_Plani.pdf` (October 2026). This file is the agreed version of it; where it conflicts with the PDF, this file wins.

![Scene](scene.png)

## Where we are (2026-10-11)

Steps 0–3 are done. Why we proceed this way: [`method.md`](method.md).

- **Round 1 (pilot) recording is complete:** 45 episodes (#0–#44), 9 tasks × 5, plus #45 (below). On HF in `fport/tic-tac-toe-so101-x-round1`, tagged `v3.0`.
- All 45 episodes were checked: the boards match [`rounds/round1.md`](rounds/round1.md), the X is in the right cell every time, the labels are correct, `top`/`wrist` are not swapped, no episode hit the 40 s limit.
- **#45** was recorded (2026-10-10): a new `middle center` episode with the board of #15 (X `middle left`, O `bottom left`), checked. 46 episodes in the raw repo.
- **The clean set is on HF:** `fport/tic-tac-toe-so101-x-round1-clean-v1` (2026-10-10), raw #15 deleted (its last 22 s were motionless), 45 episodes, 9 × 5, 28,707 frames, tagged `v3.0`; compared with the raw recording episode by episode. The numbers shift: raw #16–#45 → clean #15–#44. Training uses this repo.
- Blocks 1–5 were recorded on 2026-10-06, Blocks 6–9 on 2026-10-10. In the clean set the episodes recorded on the second day are shorter: median 18.7 s (21 episodes) against 22.6 s on the first day (24 episodes); over all 45, episode length is 14.3–27.1 s, median 22.0 s.
- Lessons: give the command in full for every call (in Block 5, #22–#24 were labelled wrongly by an old command from the shell history, fixed with `modify_tasks`); do not rename the repo while recording; keep the calls short (2 + 2 + 1).
- Visibility: on 2026-10-10 the user said "it can be public"; the raw and the clean repo are public. On 2026-10-11 the GitHub repo and the model were made public too.
- **Step 4 is ready (2026-10-10):** Colab notebook [`notebooks/train_smolvla_round1.ipynb`](../notebooks/train_smolvla_round1.ipynb): `lerobot/smolvla_base`, expert-only, batch 64, 20k steps, a checkpoint to the Hub every 5k, model `fport/smolvla-tic-tac-toe-so101-x-round1-20k` (private at first, public since 2026-10-11). The camera mapping is the same as in an earlier open SO-101 tic-tac-toe project used as a reference (`top` → `camera1`, `wrist` → `camera2`, `empty_cameras=1`). The same command was tried on the Mac for 3 steps (MPS, batch 2): the dataset, the mapping and checkpoint saving work; it has not been run in Colab yet.
- **Step 4 training finished (2026-10-10, 16:36 → ~20:20):** Colab A100 80 GB, 1.49 steps/s, 20k steps. Loss 0.479 at step 100, then 0.077. The final model is at the root of `fport/smolvla-tic-tac-toe-so101-x-round1-20k` (private at first, public since 2026-10-11), the intermediate checkpoints under `checkpoints/005000` … `020000`.
- **The final model was tried on the Mac without the arm (2026-10-10):** It loads from the Hub onto MPS, a 50-step chunk takes 0.35 s. On recorded frames the mean difference between the prediction and the recorded motion is ~0.4–1° (training data; it does not show success on the arm). When the sentence is swapped for another cell on the same frame, the prediction changes by up to 50° (noise with the same sentence is ~0.5°): the model listens to the sentence. The `lerobot-rollout` command was run with a port that does not exist: the flags are valid, the policy loads, it stops when it reaches the port.
- **First attempts on the arm (2026-10-10 evening, `middle center`):**
  - Run 1 (40 s): the arm stayed in the rest pose; only `wrist_flex` moved a few degrees now and then.
  - Run 2 (20 s, logged with [`scripts/rollout_logged.py`](../scripts/rollout_logged.py)): it waited 6.8 s, then picked the X from the slot and brought it over `middle center` at second 18; the time ran out at 20 s and it went back without being able to release. The duration was too short (my mistake); to be repeated with 60 s.
  - Run 3 (60 s, logged): **first full success.** It started right away, picked the X at ~second 7, released it in the `middle center` cell at ~second 22 and returned to the rest pose at second 30.
  - **The cause of the jerky motion was measured:** with `--inference.type=rtc --inference.rtc.enabled=false --inference.queue_threshold=18`, the new chunk is computed from an observation ~0.6–1 s old and appended to the end of the old chunk; every 50 steps the arm jumps backwards. In the two queued runs (runs 2 and 3), 17 of the 18 jumps larger than 6° are exactly at a chunk boundary (10 of 11 in run 3 alone), the largest being 29° (a normal step is ~1°). The same thing feeds the stalling at the start: the arm begins to move, and the chunk that comes from the old observation pulls it back to the rest pose (run 2, step 50: `wrist_flex` 53° → 78°). This setting had been taken from the reference recipe without measuring.
  - Three settings with a fake arm (fixed image), first 7.5 s: the current setting has a largest jump of 31° and no pause; `--inference.type=sync` 6.5°, a 0.4 s pause every 1.7 s; RTC on (`rtc.enabled=true`, `execution_horizon=10`, `queue_threshold=30`) 13°, 0.17 s. Next, `sync` will be tried on the arm.
  - Run 4 (`--inference.type=sync`, logged): **clean success.** It started at second 1.3, released the X in `middle center` at ~second 16 and returned to rest. The largest command jump was 4.6° (29° before), none larger than 6°; a 0.40 s pause at every chunk boundary (14 times). The user: "exactly as it should be". **From now on the default is `sync`.**
  - **The wait at the start:** in the rest pose the model is undecided between "wait" and "start". In the recordings the operator waited 2.4 s on average (4.6 s at most) before moving; the model learned that. On the same frame, with `wrist_flex` at 72° it plans a motion of 57–61° every time; at 74° (where the arm sits with torque on) 17–41°, sometimes none. In round 2 the motion will start as soon as recording starts; trimming the initial wait from the pilot data and retraining is also an option.
  - Diagnostic tools without the arm: [`scripts/capture_frames.py`](../scripts/capture_frames.py) (what the cameras see right now + the joint angles, does not enable torque), `scripts/rollout_logged.py` (log of commands and state).
- **Two moves on the arm through Strands, both landed (2026-10-10 21:37 and 21:41):** `scripts/strands_game.py move "top left"` (23 s) and `move "bottom left"` (24 s). The X was in the right cell, and when the arm returned to rest the script ended the move by itself; the largest command jump was 5.7°. Cells seen on the arm: `middle center` (2 times), `top left`, `bottom left`.
- **The Claude side was tried in dry-run mode:** a full game, a single `place_x` call per turn, it blocked and won. The key is read from `.env` at the repo root (does not go into git).
- **First game on the arm with Claude (2026-10-10 21:49):** Claude played `middle center`, `bottom right`, `middle left` (the O pieces were `top left`, `bottom left`); all three of the three moves were in the right cell (first to last command: 20.8, 16.5 and 16.7 s; in the automatic game later that evening 27.5, 26.3 and 18.9 s, so about 17 to 28 s over both games). The game was left unfinished. Cells seen on the arm: `middle center`, `top left`, `bottom left`, `bottom right`, `middle left`.
- **Board reading was added:** when Enter is pressed, Claude reads the 9 cells from the `top` frame; 16/16 correct on 8 real frames. At 22:10 live board reading worked (5 pieces, fully correct). Details in [`strands.md`](strands.md).
- **Automatic game on the arm (2026-10-10 22:58):** no prompts; the camera checks the pick slot, verifies the placed X and finds the human's O ([`strands.md`](strands.md)). Claude played `middle center`, `top right`, `middle left`; all three landed in the right cell. The game was stopped before the end. Cells seen working on the arm so far: 6 of 9 (`middle center`, `top left`, `bottom left`, `bottom right`, `middle left`, `top right`), every attempt a hit (10 moves: 4 with `lerobot-rollout`/`rollout_logged.py` counting only the two that ran to the end, 2 with `move`, 6 in games). For eight of the ten the arm's return to rest is in the log; in the other two (the third move of each game, both `middle left`) the log ends about 2.5 s after the release (2.3 s and 2.6 s after the gripper was commanded open), before the return: the game ended there, with the X already in the cell. Not tried yet: `top center`, `middle right`, `bottom center`.
- **Repo made English by default (2026-10-10):** code in English, docs and terminal messages in English and Turkish (`--lang tr`, `docs/tr/`).
- **Dashboard added (2026-10-10):** `xox/dashboard`, a local web page with both cameras, the board, whose turn it is, Claude's sentence, the move list and a stop button; `python -m xox.dashboard --demo` replays recorded frames.
- **Game code in the `xox` package, `play` drives the dashboard (2026-10-11):** the game moved from `scripts/strands_game.py` into the `xox` package; the script is now a thin wrapper and `python -m xox <command>` is the same program. `play` starts the dashboard and keeps it up to date, and writes `game.jsonl` next to the per-move logs. During a game the first Ctrl+C stops the arm. All of this was tested with a fake arm, fake cameras and a fake Claude; it has not been run on the real arm yet. Usage in [`strands.md`](strands.md).
- **`eval` command added (2026-10-11):** a per-cell benchmark on the arm, judged by the top camera, without Claude: `scripts/strands_game.py eval --trials 10` asks for every cell ten times on an empty board and writes `outputs/eval/<time>/results.jsonl`. This is the tool for the empty-board case of Step 6; start boards held out from training are still open. Tested with a fake arm and composed frames only, not yet run on the arm ([`strands.md`](strands.md)).
- **Next:** run `eval` on the arm; round 2 data (Step 5: start moving as soon as recording starts); the minimax check.

### Command for trying on the arm

First the ports and `lerobot-find-cameras` (index 0 must be `top`, 1 `wrist`). The arm in the rest pose, an X at the pick location. `--task` changes for each cell. To keep a log, use `python scripts/rollout_logged.py` instead of `lerobot-rollout` (same flags). `--rename_map` is required: without it the checkpoint's own mapping is overwritten by an empty mapping. Do not pass `max_relative_target`.

```bash
cd ~/www/so101-xox && source .venv/bin/activate
lerobot-rollout \
  --strategy.type=base \
  --policy.path=fport/smolvla-tic-tac-toe-so101-x-round1-20k \
  --inference.type=sync \
  --rename_map='{"observation.images.top": "observation.images.camera1", "observation.images.wrist": "observation.images.camera2"}' \
  --robot.type=so101_follower --robot.port=/dev/cu.usbmodem5AB01794851 --robot.id=follower --robot.calibration_dir=calibration \
  --robot.cameras="{ top: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}" \
  --task="put the red X in the middle center cell" \
  --duration=60 --display_data=false
```

When the time runs out or you stop it with Ctrl+C, the arm returns to the pose it started from and then the torque is cut; so start it from the rest pose. To try an intermediate checkpoint: `--policy.path=outputs/models/round1-20k/checkpoints/015000/pretrained_model` (15k is on the local disk).

## Decisions

| Topic | Decision | Why |
|---|---|---|
| Scope | First only X (9 tasks); once X works, O as well (9 more tasks) | From simple to hard. When O is added the X data is used as is; only new task sentences come. |
| Task sentence | `put the red X in the {top\|middle\|bottom} {left\|center\|right} cell` | It is embedded in every episode and not changed after recording. Exactly this, letter for letter. |
| Cell names | From the robot's point of view: `top` = the row farthest from the arm base, `left` = the robot's left | The operator is behind the arm and faces the same way as the robot. |
| Cameras | `top` (fixed, looking at the board) + `wrist` | Mapped to `camera1` / `camera2` in SmolVLA. |
| Pick location | A single pick slot; after the robot's move a human puts the next X there | With a fixed pick the policy mainly learns the place, and the data need drops (PDF Phase 0). |
| Episode | 40 s recording, 90 s reset, both end early with → | The first move took ~22 s when recording; 25/40 s was not enough (2026-10-06). |
| Starting model | `lerobot/smolvla_base` | The board and the pieces differ from the reference project's; its checkpoint gains little. |
| Dataset | HF, public (planned private until 2026-10-10); a separate raw repo per round (`fport/tic-tac-toe-so101-x-round1`), `-clean-vN` once cleaned and merged | The reference project's `tic-tac-toe-so101-<part>-clean-vN` scheme. The raw recording does not change. Details in [`operations.md`](operations.md) "Hugging Face". |
| Code | GitHub `fport/so101-xox`, public since 2026-10-11 (Apache 2.0) | Opened together with the write-up, the datasets and the model. |

## Scene

Nothing moves during recording. The model is only robust to the scene it saw in training; if the board shifts 3 cm or the camera angle changes, the policy meets a situation it has never seen (this happened in ring-center-v2: the arm stuck to the rest pose).

- The tape grid, the X slots (2×3), the O slots (2×3), the arm base, the `top` camera: their corners are marked with tape.
- The `top` camera looks from across the arm: in the image the `top` row is at the bottom and the robot's left is on the right.
- The only thing that moves in the frame is the follower. The leader and the operator are outside both cameras.

## Steps

- [x] **0 · Repo, environment, calibration** (2026-10-05)
- [x] **1 · Hardware check** (2026-10-05): `top` = index 0, `wrist` = index 1; the arm reaches the 9 cells and the 6 X slots
- [x] **2 · Pilot recording plan** (2026-10-05): [`recording.md`](recording.md) protocol and command, [`rounds/round1.md`](rounds/round1.md) 9 cells × 5 = 45 episodes
- [x] **3 · Pilot recording** (round 1, 2026-10-06 → 2026-10-10): 45 episodes → HF `fport/tic-tac-toe-so101-x-round1`
- [x] **4 · First training:** SmolVLA in Colab (expert-only, 20k steps) and the first runs on the arm on the Mac (2026-10-10). The goal is not success but the chain working end to end.
- [ ] **5 · Complete the dataset:** 30–40 episodes per cell; full boards, light variation, layouts held out for eval
- [ ] **6 · Evaluation:** 10 trials per cell, a 3×3 success map. For the empty board there is a tool since 2026-10-11, `eval --trials 10`; it has not been run on the arm yet. Start boards held out from training are still open.
- [ ] **7 · The O pieces:** `put the white O in the ... cell`, 9 tasks, a single pick slot for O too; added to the same dataset
- [ ] Afterwards (PDF Phases 2–5): ACT (target cell one-hot), pi0.5, board reading, LLM + minimax game layer. The user, 2026-10-10: once the first training is done we will try the game layer with `strands-robots` (PyPI `strands-robots`, `policy_provider="lerobot_local"`) and the Claude API.

## Why we do not expect success from the pilot

SmolVLA wants ~50 episodes even for a single task (LeRobot docs: 5 positions × 10; 25 was not enough). There are examples where it failed with 30 episodes while ACT worked (lerobot issue #1239). 45 episodes are split over 9 cells; the pilot only verifies the recording → Hub → Colab → Mac chain.
