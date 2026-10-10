# benchmarks/data

Small tables derived from the raw logs and the training set, so that the charts in
[`docs/benchmarks.md`](../../docs/benchmarks.md) can be redrawn without the git-ignored `outputs/` and
`data/` folders. Every CSV file here is written by [`../extract.py`](../extract.py); none is edited by hand.
Times are seconds, angles are degrees, the gripper is its opening in percent of its calibrated range.
`yes`/`no` are booleans, an empty field means "not available".

| File | What it is | Raw source (under the repo root) |
|---|---|---|
| `arm_run2_queued.csv`, `arm_run3_queued.csv`, `arm_run4_sync.csv` | One row per log line of a direct policy run: time since the first command, commanded and measured angle of the six joints. `phase` is `policy` or `return` (the scripted drive back to the start pose at the end of a run; the measured angles are frozen there because the arm is no longer read). | `outputs/rollout_gunluk/20261010-211122`, `-211639`, `-212220`, file `adimlar.jsonl` |
| `arm_run_summary.csv` | Per run: policy steps, lines of the scripted return, steps whose command changes by more than 6°, how many of those are on a chunk boundary, the largest and the median per-step change, pauses. | same |
| `arm_jumps.csv` | Every step of runs 2 to 4 whose command changes by more than 6°: time, size, joint, on a chunk boundary or not. | same |
| `arm_chunk_boundaries.csv` | Every chunk boundary (step divisible by 50) of runs 2 to 4: the command change at it and the gap since the previous command. | same |
| `run4_events.csv` | Run 4: start, pick, release and return, each with its definition. | `outputs/rollout_gunluk/20261010-212220/adimlar.jsonl` |
| `moves.csv` | One row per logged run of the policy on the arm (13): when the arm started, when it was back, where the log ends, the largest command change, pauses. `counted_as_completed` and `landed_evidence` are not computed, see below. | the three files above and `outputs/strands_gunluk/<run>/hamleNN_<cell>/adimlar.jsonl` |
| `cell_tally.csv` | `moves.csv` counted per board cell. | same |
| `episodes.csv` | One row per demonstration of the clean training set: target cell, length, pause before the first motion (from the recorded action and from the measured state), pieces on the start board, recording day. | `data/tic-tac-toe-so101-x-round1-clean-v1/` (`meta/info.json`, `meta/episodes/`, `data/`; the videos are not read), `docs/rounds/round1.md` |
| `detector_cells.csv` | Mean absolute grey difference of each board cell between two top-camera frames, for frame pairs of an unchanged scene and for pairs between which pieces were added. | `outputs/canli/top_0.png` … `top_4.png`; `outputs/strands_gunluk/*/hamle*/top_001.jpg`, `top_002.jpg` |
| `detector_slot.csv` | Share of red pixels in the pick-slot box for frames in which the slot is in plain view. | `outputs/canli/top_*.png`, first and last `top_*.jpg` of every logged run |
| `key_numbers.csv` | Every number quoted on the benchmark pages, with its unit and what it is. | all of the above |

## What is entered by hand

Four things in these tables are not computed. They are constants at the top of `extract.py`:

- `counted_as_completed` in `moves.csv`: whether `docs/writeup.md` counts the move among its ten completed moves.
- `landed_evidence` in `moves.csv`: `frame` means the X is visible in the target cell in a later top frame on
  disk (looked at by eye); `notes` means only the project notes say so, because the log ends while the gripper
  is still over the cell.
- `piece_added`, `under_resting_gripper`, `existing_piece_moved` in `detector_cells.csv` and `slot_by_eye` in
  `detector_slot.csv`: read off the frames by eye. Which cell got the arm's X follows from the move's folder
  name; which cell got the human's O was read off the frame.
- `recorded_on` in `episodes.csv`: the recording day of each block of five episodes, from `docs/plan.md`.

## Definitions

- **Policy step / scripted return.** A direct run ends with the script driving the arm back to its start pose
  along a straight line in joint space. Those trailing lines (150 in runs 2 and 3, 6 in run 4, whose log stops
  early) are marked `return` and left out of every statistic.
- **Jump.** The change of the commanded pose from one step to the next, taking the largest change among the five
  arm joints. A step counts as a jump above 6° on that value. A chunk boundary is a step whose index is
  divisible by 50.
- **Start** (`start_s`). Time 0 is the first command. The rest pose is the first measured pose in the log. The arm
  has started when the commanded pose of any arm joint is more than 10° from rest; if it comes back within 10°
  before travelling to its farthest point, the last departure counts and the first one is kept in `first_leave_s`.
  `start_far20_s` is the game script's own stricter test (`shoulder_lift` or `elbow_flex` more than 20° away).
- **Back** (`back_s`). The game script's rule: the first of 45 consecutive commands (1.5 s) whose `shoulder_lift`
  and `elbow_flex` are within 8° of rest, after they had been more than 20° away.
- **First motion** in a demonstration. The first frame in which any arm joint differs by more than 3° from its
  value in the episode's first frame, in the recorded action (`first_motion_action_s`, what the operator's hand
  did on the leader arm) and in the measured state (`first_motion_state_s`, the follower arm).
- **Cell difference, red share.** As in `scripts/strands_game.py`: the frame is rotated by 180°, the grid box
  `(160, 40, 478, 358)` is cut into 3×3 cells and the mean absolute difference of the grey value is taken per
  cell (the script compares the largest of the nine with 8); the slot box is `(485, 250, 560, 325)` and a pixel
  is red if `R > 110`, `R > 1.5 G` and `R > 1.5 B` (the script compares the share with 0.015).
