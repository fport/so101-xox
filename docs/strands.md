# Game layer with Strands Robots + Claude

**English** · [Türkçe](tr/strands.md)

Source: [GitHub](https://github.com/strands-labs/robots), [docs](https://strands-labs.github.io/robots/). Installed versions: `strands-robots 0.5.3`, `strands-agents 1.59.0`.

Status (2026-10-10): the environment is set up, the script is written, and two moves in a row were tried with a fake arm (the images replayed from a real run). On the real arm `move` ran twice and both landed (`top left`, `bottom left`); two games with Claude were played on the arm the same evening, six arm moves, all in the right cell, neither game played to the end ([`plan.md`](plan.md)).

Status (2026-10-11): the game code moved from `scripts/strands_game.py` into the `xox` package, `play` drives a local dashboard, the first Ctrl+C stops the arm, and a fourth command, `eval`, runs a per-cell benchmark. All of this has been tested with a fake arm, fake cameras and a fake Claude; none of it has been run on the real arm yet.

## Architecture

```
Claude (Strands Agent)  →  picks the cell: place_x("top left")
code                    →  the exact training sentence: "put the red X in the top left cell"
Strands Robot + policy  →  SmolVLA moves the arm
```

Claude does not drive the arm directly, it only picks the cell. The policy only understands the 9 sentences it saw in training; the code produces the sentence ([`method.md`](method.md)). Claude is not given Strands' raw `so101` tool, because that tool takes free text and a free `policy_config`. Instead there is a single-parameter `place_x(cell)` tool; it refuses a taken or an unknown cell.

## Where the code is

The game is the `xox` package at the repo root. `scripts/strands_game.py` is a thin wrapper that puts the repo root on the import path and calls the package; `python -m xox <command>`, run from the repo root, is the same program.

| File | What it holds |
|---|---|
| `xox/board.py` | Cell names, the task sentence, the terminal drawing of the board, the winner |
| `xox/vision.py` | What the top camera tells the game: the pixel checks for the pick slot, a changed cell and motion, Claude's board reading, and the landing measurement of `eval` |
| `xox/arm.py` | The Strands robot and the SmolVLA policy, the per-move log, the cameras |
| `xox/game.py` | The `play` loop: the agent, the `place_x` tool, the dashboard state, `game.jsonl`, Stop and Ctrl+C |
| `xox/evaluate.py` | The `eval` command |
| `xox/cli.py` | The four commands and their flags |
| `xox/i18n.py` | Terminal messages in English and Turkish |
| `xox/state.py` | The game state shared between the game loop and the dashboard |
| `xox/dashboard/` | The local web page and its server; `python -m xox.dashboard --demo` runs it alone |

## Setup

A separate environment; it does not touch the repo's `.venv`:

```bash
cd ~/www/so101-xox
uv venv .venv-strands --python 3.12
source .venv-strands/bin/activate
uv pip install "strands-robots[lerobot,smolvla]" "strands-agents[anthropic]"
```

`strands-robots doctor` reports FAIL on three things, none of which we need: `mujoco` (simulation), `torchcodec` (video decoding), the simulation smoke test.

## Usage

```bash
cd ~/www/so101-xox && source .venv-strands/bin/activate   # or call it directly with .venv-strands/bin/python

# 1. No agent, a single move (tries the Strands connection); asks to confirm before the arm moves
python scripts/strands_game.py move "middle center"

# 2. Claude is X, you are O (the key is read from the .env file at the repo root: ANTHROPIC_API_KEY=...)
python scripts/strands_game.py play

# 3. Only read the board from the top camera; the arm does not move (needs the key too)
python scripts/strands_game.py board

# 4. A per-cell benchmark on the arm, without Claude and without a key (see "Per-cell benchmark" below)
python scripts/strands_game.py eval

# The same program without the wrapper script
python -m xox play
```

Options are written after the command name:

| Flag | Command | What it does |
|---|---|---|
| `--model` | all | HF repo or local checkpoint folder |
| `--port` | all | follower port |
| `--top`, `--wrist` | all | camera indices |
| `--duration` | all | seconds per move at most, default 45 |
| `--device` | all | default `mps` |
| `--dry-run` | all | does not move the arm, only shows the flow |
| `--lang en\|tr` | all | language of the terminal messages, default `en`; the environment variable `XOX_LANG=tr` works too |
| `--claude` | `play`, `board` | Claude model name |
| `--first x\|o` | `play` | who starts |
| `--confirm` | `play` | ask at every step instead of camera detection |
| `--no-dashboard`, `--dashboard-port`, `--no-open` | `play`, `eval` | see "The dashboard" below |
| `--image`, `--save` | `board` | read an image file instead of the camera; write the crop that is sent to Claude |
| `--trials`, `--cells`, `--seed`, `--report` | `eval` | see "Per-cell benchmark" below |

Every command accepts the first seven; `board` only uses `--top` and `--lang` of them.

**A move.** Once the arm has gone to the cell and returned to the rest pose (shoulder and elbow within 8° of the start, for 1.5 s) the code ends the move before the time runs out; if it does not return, the move ends when `--duration` (default 45 s) runs out. `move` asks for confirmation before the arm moves. `play` does not ask before a move (see "Automatic game" below); it asks only when the camera check after a move fails. With `--confirm` it behaves as it did at first: it asks before every move, asks after the move whether the X landed in the cell, and you type the O move in the terminal. At the end of a game it prints the hit count. With `--dry-run`, `play` does not move the arm, starts no dashboard and writes no log, and you type the O moves.

**The dashboard.** `play` and `eval` start a local web page, print its address (`http://127.0.0.1:8765/` by default) and open it in the browser. It shows both cameras, the board, whose turn it is, Claude's sentence, the move list, the events and a Stop button, and it can be switched between English and Turkish. `--dashboard-port` picks another port (0 = any free one), `--no-open` does not open the browser, `--no-dashboard` does not start the page. If the port is taken, a message is printed and the game goes on without the dashboard. `move` and `board` do not start it. `python -m xox.dashboard --demo` runs the page alone with a scripted fake game (its own flags: `--host`, `--port`, `--speed`, and `--frames DIR` for the recorded frames of a move; without recorded frames it draws placeholder frames). So far the dashboard has only been run with a fake arm and with this replay.

**Stopping.** During `play` and `eval` the first Ctrl+C stops the arm at once: a signal handler sets the stop flag and tells the robot to stop before anything else sees the interrupt. Strands absorbs the first Ctrl+C while a tool is running, and without the handler the arm finished its move. This was tested with a fake arm and has not been tried on the real arm yet. The Stop button on the dashboard ends the run the same way. In `--confirm` mode a terminal prompt still has to be answered before the game ends. In `move`, Ctrl+C stops the arm. Whenever the arm was connected, the terminal asks for Enter before the connection is closed: closing cuts the torque, so hold the arm by hand if it is not in the rest pose.

**Logs.** Each run gets a folder `outputs/strands_logs/<time>/`. Every move has its own folder in it, `moveNN_<cell>/`, with the commands and one observation per chunk (`steps.jsonl`) and the `top` / `wrist` frames. For `play`, `game.jsonl` is written next to the per-move folders: one line per event (the phases, Claude's pick and sentence, every move with the board after it, a stop). `eval` writes to its own folder, see below.

## Automatic game (2026-10-10)

`play` no longer asks questions (the old behaviour: `--confirm`). A turn goes like this:

1. Claude picks the cell.
2. The code looks at the pick slot from the top camera (is there red inside `SLOT_BOX`). If it is empty it says "put an X in the slot" and waits; once the X shows up and the image has not moved for 1 s, it counts 2 s and moves the arm.
3. When the arm has returned to rest, Claude reads the board: if the X is in the target cell it counts as a hit, otherwise you are asked to fix it by hand.
4. Your turn: you place your O. The code compares frames locally (no API call); once a cell has changed and the image has settled, it has Claude read the board and counts the single new O as your move. If it cannot find one it keeps waiting; Enter makes it read again, typing a cell name enters it by hand. If you put the O down while the arm is still returning, the verification read in step 3 already shows it and it is taken from there without waiting. With no change seen for 30 s, Claude reads the board anyway.

The local thresholds were measured on real frames: cell difference ~2 for the same scene, 16–22 for a new piece (8 cells measured; threshold 8); block difference 25–54 while the arm or a hand moves, ~2 when still (threshold 6); red ratio 0.045–0.30 with an X in the slot (16 frames), 0.00 when empty (threshold 0.015). A cell under the resting gripper reached up to 30 without a new piece when the gripper settled differently, which is why a triggered read is still judged by Claude.

Claude image reads per game: one per arm move (verification) and one per O move; 9 in a five-move fake game.

Tried: local detection with real frames; the full flow with a fake arm + fake agent + fake reading (it finishes without asking a question). On the real arm (2026-10-10 22:58) one automatic game was played: three arm moves, all verified in the right cell, stopped before the end; the early-O shortcut and the 30 s recheck were added after it and have only run with the fake arm. Known weakness: the `bottom center` cell lies under the resting gripper; verification may say "I could not see" for an X there.

## Reading the board from the camera (2026-10-10)

In a game the O move no longer has to be typed: the code takes a frame from the `top` camera (by itself in the automatic game above; Enter makes it read at once), rotates it to the robot's view (180°), crops it to the grid (`BOARD_BOX`) and shows it to Claude; Claude reports the 9 cells with the `report_board` tool. The code compares this with the board it knows: if there is exactly one new O and everything else is the same it accepts it, otherwise it asks or has you type it. Typing the cell name is still possible.

```bash
.venv-strands/bin/python scripts/strands_game.py board            # read the board without moving the arm
.venv-strands/bin/python scripts/strands_game.py board --image outputs/live/top_4.png
```

- 8 frames from real runs (empty board, 1–4 pieces, one of them an X half covered by the gripper) were each read twice: 16/16 fully correct, 3–8 s per read (`claude-opus-5-5`).
- Not tried: a piece in the `bottom center` cell. In the rest pose the gripper covers most of that cell.
- `claude-opus-5-5` does not accept a forced tool choice (`tool_choice` `tool` / `any`); the tool was left free, and if it does not report, the script falls back to manual entry.
- `BOARD_BOX` is fixed; if the camera or the board moves, look with `board --save crop.png` and update it.
- Reading from the live camera was tried (2026-10-10 22:10): a board with 5 pieces (2 O, 3 X, one of them next to the gripper) was read fully correctly.

## Per-cell benchmark: `eval` (2026-10-11)

`eval` asks the arm for every cell several times and lets the top camera judge where the X landed. It uses no Claude and no API key. It has been tested with a fake arm and composed frames only; it has not been run on the real arm yet, so there are no results from it.

```bash
python scripts/strands_game.py eval                                  # every cell 3 times
python scripts/strands_game.py eval --trials 10                      # every cell 10 times
python scripts/strands_game.py eval --cells "top left" "top right"   # only these cells
python scripts/strands_game.py eval --dry-run --trials 2             # print the plan and the rules, open nothing
python scripts/strands_game.py eval --report outputs/eval/<time>     # print the table of an earlier run
```

- `--trials`: moves per cell, default 3.
- `--cells`: only these cells.
- `--seed`: seed of the shuffled move order, default 0. The same seed gives the same order.
- `--report RUN`: only print the table of an earlier run, from its folder or its `results.jsonl`; the arm is not used.
- The flags shared by all commands and the three dashboard flags work as in `play`.

**The operator's routine.**

1. Clear the board (no X and no O on it), leave the arm in the rest pose, put one X in the pick slot and press Enter. The code takes a reference picture of the empty board; keep your hands out of the camera's view. If it sees a red piece on the board it does not start.
2. The arm starts by itself 2 s after the board is empty, the slot has an X and nothing moves.
3. When the arm is back, one result line is printed: hit or miss, the cell the X is in, its offset from the centre of the asked cell, and the timing of the move.
4. After each result line, take the X off the board and put it back in the pick slot. Not before the line: the camera is still measuring.
5. Ctrl+C or Stop on the dashboard ends the run and keeps the results so far. At the end a table of hits per cell is printed.

**Output.** Everything of one run goes to `outputs/eval/<time>/`:

| File | Contents |
|---|---|
| `results.jsonl` | One line per move, appended as the run goes |
| `summary.json` | Settings, thresholds, hits per cell and what each field means; rewritten after every move |
| `reference.jpg` | The empty board the run started from |
| `before_NN.jpg`, `after_NN.jpg` | The top frame before and after move NN |
| `moveNN_<cell>/` | The arm's own log of the move (`steps.jsonl`, `top` / `wrist` frames) |
| `events.jsonl` | What the terminal and the dashboard showed |

**How a landing is judged.** The code looks for red that is new compared with the reference frame of the empty board, inside the board box (`BOARD_BOX`); the reference's red is first widened by a few pixels (`REFERENCE_MARGIN`) against edge noise. The orange part of the gripper passes the same red rule, rests over the bottom row and never rests in exactly the same place, so subtracting the reference is not enough: only a group of at least 1100 new red pixels (`MIN_PIECE_PIXELS`) counts as a piece. In the recorded frames an X shows 1650–2060 red pixels with the arm at rest and 1340 at the least while the arm still covers part of it; the gripper's orange part shows 490–610, and up to 690 of it are new against a reference. The cell that holds the centre of the piece is where the X landed, and the move is a hit if that is the asked cell. The offset from the centre of the asked cell is reported in pixels and in cell widths.

**Limits, as stated in the code.**

- Empty board only. The reference is the empty board and each move starts from it; start boards with other pieces on them, as in a game, are not covered.
- `near_gripper` is set when the piece is within 40 px (`GRIPPER_REACH`) of where the gripper rested in the reference. Part of the piece may then be hidden, or part of the gripper counted with it, and the centre is less exact. The resting gripper partly covers `bottom center` and `bottom right`.
- `touches_edge` is set when the piece reaches the edge of the board box: part of it may lie outside, and the centre is less exact.
- When no group is large enough the result is `none`, and with more than one it is `several`; both are counted as a miss.
- The centre of the X is measured, not its rotation.
- The thresholds come from recorded frames. How they hold up in a run on the arm is not known yet.

## Tried (without the arm)

| What | Result |
|---|---|
| Does the policy load through Strands | Yes. `create_policy("lerobot_local", embodiment="so101_real", device="mps", obs_rename_override=...)` |
| Prediction on a recorded frame (15k and the final model) | A 50-step chunk, 0.35 s. Mean difference from the recorded motion 0.4–1.6°, the same level as on the `lerobot` path. This is training data; it does not show success on the arm. |
| `Robot(...)` construction | It is constructed, finds the calibration file, leaves the connection to the first motion. |
| Full path with a fake port | The policy loads; it fails cleanly when it reaches the port. |
| Game loop | With a fake agent in dry-run mode: a taken cell, an unknown cell and a second move in the same turn are refused, the winner is found. |
| Real call with Claude | A full game was played in dry-run mode (2026-10-10, `claude-opus-5-5`): it called `place_x` once per turn, blocked and won. |

## Accidental run on the real arm (2026-10-10 21:28)

While writing the fake arm test the patch did not take, and the script connected to the real arm on the default port; the test input answered "e" (yes) to the confirmation question. The arm stayed under torque for 45 s and the policy sent commands. Because an X from the previous run was sitting in the target cell (`middle center`), the model saw the "job done": the commands moved at most 5° (wrist) from the rest pose, the arm did not leave its place. Log: `outputs/strands_gunluk/20261010-212846` (the folder's name at the time; new logs are written under `outputs/strands_logs/`).

Lesson: every test done without the arm is run with `--port /dev/cu.YOK`. Side findings: the step interval in the Strands loop is 35 ms (~28.5 Hz), ~2.15 s per chunk; when the target cell is taken the model stays put.

## Lessons learned

- **Camera names:** The `so101_real` embodiment expects `front` / `wrist` and converts to `observation.images.image`. Our checkpoint wants `camera1` / `camera2`; solved with `obs_rename_override={"top": "...camera1", "wrist": "...camera2", "front": None}`.
- **Control rate:** The default is 50 Hz. The data is 30 fps, so `control_frequency=30.0` is passed.
- **`calibration_dir`:** Must be a `Path`; given a string, `lerobot` raises an error.
- **`max_relative_target`:** The driver does not apply it by itself; if you do not pass it, it is off. We do not pass it (it locks the elbow, [`operations.md`](operations.md) "Known pitfalls").
- **Device:** `device="mps"` must be passed explicitly; without CUDA, Strands falls back to CPU.
- **The process restarts:** On macOS, `import strands_robots` restarts the process for `torchcodec`; the script was asking its questions twice. Turned off with `STRANDS_ROBOTS_NO_DYLD_SHIM=1`.
- **Confirmation gate:** Strands' gate is only on the agent tool path (`execute` / `start`). We call `robot.run_policy(...)`, which does not go through that gate; the code asks for confirmation itself, in `move` always and in `play` only with `--confirm`.
- **Shutdown:** When `cleanup()` drops the connection the torque goes off. In the recordings the arm returns to the rest pose it started from, and the policy should too; before closing, the code asks for Enter so that the arm can be held by hand if it is not there.

## Open questions (to be seen on the arm)

- The loop is synchronous: every 50 steps (1.7 s) it stops ~0.4 s for the new chunk. This is the same behaviour as `lerobot-rollout --inference.type=sync`, which works well on the arm (2026-10-10); the queued setting made the arm jump.
- The loop sleeps 1/30 s after every step and does not subtract the write time; the real rate stays a little below 30 Hz.
- Answered on 2026-10-10: the move no longer runs for a fixed time; it ends once the arm is back at rest, measured at 17–28 s per move on the arm.
- On macOS the camera index shuffle applies as is; `lerobot-find-cameras` in every session.

## Order

1. The model is first tried on the arm with plain `lerobot-rollout` (the command is in [`plan.md`](plan.md)). If we move to Strands without knowing what the policy does on its own, we cannot tell whether a fault is in the policy or in the bridge.
2. A single move with `strands_game.py move`.
3. Claude with `strands_game.py play`.
4. Board reading and minimax.
5. A per-cell benchmark with `strands_game.py eval`.

## Parts of Strands we do not use

Simulation (MuJoCo, Isaac), recording and `verify-dataset`, episode labelling, training wrappers, fleet networking, Strands' own browser dashboard, ROS 2 bridges. The dashboard that `play` opens is this project's own code in `xox/dashboard/`, not the one that comes with Strands; it now does what Strands' dashboard was noted for here, seeing the cameras on one screen. Possibly useful later: `verify-dataset` (checking the round 2 recordings).
