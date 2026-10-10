# Method: how to teach a robot tic-tac-toe

**English** · [Türkçe](tr/method.md)

From the conversation on 2026-10-05. What is right about the first plan that comes to mind, and what needs correcting.

## The first plan that comes to mind

Show picking an X and putting it in the 9 boxes, then put each of the 9 X pieces in the 9 boxes one by one, then do the same for the O pieces. At the end of the day train on this data: the robot learns to pick and to place. Connect an LLM behind it so it plays smartly.

## What is right

- **A separate task per cell:** 9 cells = 9 task sentences.
- **Teaching the O pieces too:** Step 7 in the plan.
- **An LLM behind it:** This is also the architecture in the PDF and in an earlier open SO-101 tic-tac-toe project. The LLM picks the cell, the robot places.

## Corrections

| First idea | In reality |
|---|---|
| "I put the 9 X pieces in the 9 boxes one by one" | The X pieces are identical; the robot does not look at which X it is. What matters is the **situation**: where the X is picked from, which cell it goes to, what is on the board. If the X is picked from 6 different slots, "slot × cell" = 54 situations, and each needs data. That is why there is a single pick slot. |
| "I show each one once" | Every situation needs dozens of repetitions. LeRobot: at least 50 episodes, 10 per position. The reference project: 195 episodes for 18 tasks (~11 per task). |
| "It learns picking and placing separately, then combines them" | The robot does not learn concepts; in a situation it has seen, it imitates the operator's motion. In a situation it has not seen, it flounders (in ring-v2 the arm stayed in the rest pose when the camera angle changed). If it is always recorded on an empty board, it hits the pieces on a full board. The situations it will meet in a game must be in the recording. |
| "I record everything and train once at the end" | Professional work runs in a loop: record a little, train, try on the arm, see where it makes mistakes, add data exactly there, train again. LeRobot: first get the basic job working reliably, add variation later; adding a lot of variation too fast ruins the result. |
| "More data = good" | Quality matters more than count. Always the same path, always grip the X at the same spot, the same speed, no hesitation. The main determinant of quality is the operator always making the same motion in the same situation (Belkhale et al.: "action divergence"). Bad episodes are deleted. |
| "If I connect an LLM it plays smartly" | The smartness comes from the LLM, but the robot only understands the sentences it saw in training; saying "put it in the corner" does not work. The LLM picks the cell, the code turns it into the exact training sentence. LLMs play tic-tac-toe badly; a minimax check is a must. And to see the board, a separate step that reads the 9 cells from the top camera is needed. |

## The professional flow

1. **Fix the scene:** camera, board, arm base.
2. **Decide what will vary:** In a game the target cell and the pieces on the board change; these are varied in the recording. The pick location and the light are fixed.
3. **Pilot:** 45 episodes. Only a test of the chain: recording → HF → Colab → trying on the arm.
4. **Main recording:** An equal number per cell (30–40), consistent demonstrations, the bad ones deleted. Equality matters; otherwise the model drifts towards the cell that was recorded more.
5. **Train and measure:** Success rate per cell with board layouts never seen in training.
6. **Targeted data for the failures:** When the robot makes a mistake, take over with the leader; the correction is recorded (`lerobot-rollout --strategy.type=dagger`).
7. **Controlled variation:** The O pieces, light, different pick slots; each one is added and measured one at a time.
8. **Game layer:** board reading + LLM + minimax check.

## Sources

- [LeRobot: Imitation Learning on Real-World Robots](https://huggingface.co/docs/lerobot/il_robots) (recording tips)
- [HF blog: What makes a good dataset](https://huggingface.co/blog/lerobot-datasets#what-makes-a-good-dataset)
- [Belkhale, Cui, Sadigh: Data Quality in Imitation Learning (NeurIPS 2023)](https://arxiv.org/abs/2306.02437)
- [Trossen Robotics: Robot Data Collection Best Practices](https://www.trossenrobotics.com/post/robot-data-collection-best-practices-imitation-learning)
