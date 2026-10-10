# Recording protocol

**English** · [Türkçe](tr/recording.md)

Board layouts episode by episode: [`rounds/`](rounds/). Each round is generated with `scripts/recording_plan.py` (the Turkish version with `--lang tr`).

## One-time preparation

- **Pick slot:** The only place the robot takes an X from: the slot on the board side in the row of the X group closest to the robot. Draw the outline of the X with tape; in every episode the X is put there at the same angle. With a fixed pick the policy mainly learns the place part (PDF Phase 0). In a game too, once the robot has made its move a human puts the next X there. Seen from behind the arm:

  ```
  X pieces (the robot's right)
  [ ] [ ]   far
  [ ] [ ]
  [A] [ ]   close to the robot   (A = pick slot, the one close to the board)
  ```
- **Store:** The remaining 5 X and 6 O. Take the pieces you put on the board from the store.
- **Direction:** Cell names are from the robot's point of view. The boards in the round file are also drawn as seen from behind the arm; set up the board while looking at the table. The `top` camera is across from the arm, its image is rotated 180°:

  ```
              (robot)
  bottom right | bottom center | bottom left
  middle right | middle center | middle left
  top right    | top center    | top left
              (top camera)
  ```
- **Light:** The same throughout the round. Light changes will be added in a controlled way in later rounds.
- **You and the leader:** Outside both cameras, behind the arm.

## Every episode

1. **Start:** The arm in the rest pose. On the board the pieces from the plan, an X in the pick slot, the target cell (`*`) empty.
2. **Recording:** Move as soon as you hear "Recording episode N". Pick the X, release it in the middle of the target cell, open the gripper, bring the arm to the rest pose, press **→**. The N you hear must be the same as the # in the plan. Press → before the "Reset the environment" sound: if the time ran out and the reset has started, → now skips the reset and the next episode starts before it is ready (this happened on 2026-10-06).
3. **Reset** (at most 90 s, **→** when ready): Remove the X you released and the pieces on the board, set up the board of the next episode, put an X in the pick slot.
4. **Bad episode** (dropped it, wrong cell, hit a piece, got stuck): **←** during the episode or in the reset right after it. The same number is recorded again.
5. There is no reset after the last episode of the block. The command ends by itself and uploads the dataset to HF (private).

**Do not press Esc:** The half-finished episode gets saved. If a block is cut short, stop and let me know; we will fix the numbers together.

## Example: Block 1 from start to finish

The `--dataset.single_task` sentence is the label of these 5 episodes; it is already written in the command, you do not do anything. In all 5 boards of the block `*` is in the same cell (`middle right` in Block 1). The only thing that changes is the other pieces on the board. You control the arm with the leader, the follower imitates.

Cell names: `top` = the row far from the robot, `bottom` = the row close to the robot; `left` = the robot's left (the side of the O pieces), `right` = the robot's right (the side of the X pieces).

| # | X on the board | O on the board |
|---|---|---|
| 0 | top center, bottom left | top right, middle left, bottom right |
| 1 | top center, top right, middle left | middle center, bottom center, bottom right |
| 2 | top left, top right, middle center, bottom center | top center, middle left, bottom left, bottom right |
| 3 | none | top right |
| 4 | middle center | top center, top right |

1. **Before the command:** Set up the board for #0, put an X in the pick slot. Bring both arms to the rest pose; when the command starts the follower jumps to the leader's pose. Recording starts the moment the command starts, so everything must be ready beforehand.
2. **Run the `lerobot-record` command** (below, in the "Command" section). Not `lerobot-teleoperate`: that one moves the arm but records nothing. If it asks about calibration, ENTER.
3. **"Recording episode 0":** Check at a glance in Rerun that `top` and `wrist` are right. Then, with the leader, pick the X from the pick slot, release it in the middle of the `middle right` cell, open the gripper, bring the arm to the rest pose, press **→**.
4. **"Reset the environment":** Take the X the robot placed and put it back in the pick slot. Change the board to #1, keep the arm in the rest pose, press **→**.
5. **"Recording episode 1":** The same motion. Repeat steps 3–4 for #2, #3 and #4 as well.
6. **After #4** there is no reset. The command closes by itself and uploads the dataset to HF.

If an episode goes wrong (the X fell, it went to the wrong place, it hit a piece): press **←**. The reset comes; set up the same board again, the same number is recorded again.

## Command

Each block is one call. The only thing that changes is `--dataset.single_task` (written in the round file). `--resume=true` is added to every call after the first block.

```bash
cd ~/www/so101-xox && source .venv/bin/activate
lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/cu.usbmodem5AB01794851 --robot.id=follower --robot.calibration_dir=calibration \
  --robot.cameras="{ top: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}" \
  --teleop.type=so101_leader --teleop.port=/dev/cu.usbmodem5A7C1232561 --teleop.id=leader --teleop.calibration_dir=calibration \
  --dataset.repo_id=fport/tic-tac-toe-so101-x-round1 \
  --dataset.root=data/tic-tac-toe-so101-x-round1 \
  --dataset.single_task="put the red X in the middle right cell" \
  --dataset.num_episodes=5 --dataset.episode_time_s=40 --dataset.reset_time_s=90 \
  --dataset.streaming_encoding=true --dataset.encoder_threads=2 \
  --dataset.push_to_hub=true --dataset.private=true --dataset.no_stamp=true \
  --display_data=true
```

`--dataset.private=true` is required: without it the dataset is created public on a personal account. `--dataset.no_stamp=true` is required too: without it lerobot appends the date to the repo name (the first recording on 2026-10-06 went up as `fport/so101-xox_20261006_225957` and was moved by hand). Repo names and adding data later: the "Hugging Face" section in [`operations.md`](operations.md).

If the command is cut short, the episodes recorded up to that moment are kept and uploaded to HF. For the rest, the same command + `--resume=true`, `--dataset.num_episodes` = the number of remaining episodes.
