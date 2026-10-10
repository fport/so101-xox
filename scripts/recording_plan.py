"""Writes the episode-by-episode plan of a recording round.

Each cell is one block (a single `lerobot-record` call). Within a block the number of X pieces on
the board cycles through 0..4, the number of O pieces follows the turn order (as many as X or one more),
the target cell is empty and nobody has won on the board.

    python scripts/recording_plan.py --round 1 --episodes 5 --seed 1 > docs/rounds/round1.md
    python scripts/recording_plan.py --round 1 --episodes 5 --seed 1 --lang tr > docs/tr/rounds/round1.md

The same seed gives the same boards in either language; `--lang` only changes the text around them.
"""

import argparse
import random

ROWS = ["top", "middle", "bottom"]
COLS = ["left", "center", "right"]
CELLS = [(r, c) for r in range(3) for c in range(3)]
LINES = (
    [[(r, c) for c in range(3)] for r in range(3)]
    + [[(r, c) for r in range(3)] for c in range(3)]
    + [[(i, i) for i in range(3)], [(i, 2 - i) for i in range(3)]]
)

# Text of the generated document. English is the default; `--lang tr` selects Turkish.
MESSAGES = {
    "switch": {
        "en": "**English** · [Türkçe](../tr/rounds/round{round}.md)\n",
        "tr": "[English](../../rounds/round{round}.md) · **Türkçe**\n",
    },
    "title": {
        "en": "# Round {round} · {blocks} blocks × {episodes} episodes = {total} episodes\n",
        "tr": "# Tur {round} · {blocks} blok × {episodes} bölüm = {total} bölüm\n",
    },
    "generated": {
        "en": "Generated: `{command}`\n",
        "tr": "Üretildi: `{command}`\n",
    },
    "explanation": {
        "en": """Each box is the **starting** board of one episode. Before the episode starts, put that piece in the cells marked `X` and `O`.
`*` is the target cell: leave it empty, the robot will put the X there. An empty box is an empty cell.

The boxes are drawn as if you were looking at the table from behind the arm:

```
          far from robot (top)
         ┌───┬───┬───┐
         │   │   │   │
 O's     ├───┼───┼───┤   X's
         │   │   │   │
         ├───┼───┼───┤
         │   │   │   │
         └───┴───┴───┘
             ROBOT
```
""",
        "tr": """Her kutu bir bölümün **başlangıç** tahtası. Bölüm başlamadan önce `X` ve `O` yazan hücrelere o taşı koy,
`*` hedef hücre: boş bırak, robot X'i oraya koyacak. Boş kutu boş hücre.

Kutular masaya kolun arkasından bakıyormuş gibi çizili:

```
          robottan uzak (top)
         ┌───┬───┬───┐
         │   │   │   │
 O'lar   ├───┼───┼───┤   X'ler
         │   │   │   │
         ├───┼───┼───┤
         │   │   │   │
         └───┴───┴───┘
             ROBOT
```
""",
    },
    "block": {
        "en": "## Block {block} · episodes #{first}–{last}\n",
        "tr": "## Blok {block} · bölüm #{first}–{last}\n",
    },
    "first_block": {
        "en": " (first block: no `--resume`)",
        "tr": " (ilk blok: `--resume` yok)",
    },
}

LANG = "en"


def t(key: str, **fmt) -> str:
    """Text `key` in the selected language."""
    return MESSAGES[key][LANG].format(**fmt)


def task(cell):
    r, c = cell
    return f"put the red X in the {ROWS[r]} {COLS[c]} cell"


def has_winner(board):
    return any(board.get(a) and board.get(a) == board.get(b) == board.get(c) for a, b, c in LINES)


def build_board(target, x_count, rng):
    for _ in range(1000):
        o_count = rng.choice([x_count, x_count + 1])
        free = [cell for cell in CELLS if cell != target]
        if x_count + o_count > len(free):
            continue
        rng.shuffle(free)
        board = {cell: "X" for cell in free[:x_count]}
        board |= {cell: "O" for cell in free[x_count : x_count + o_count]}
        if not has_winner(board):
            return board
    raise ValueError(f"could not build a board with {x_count} X pieces for: {task(target)}")


def draw(board, target):
    def row(r):
        return "│" + "│".join(f" {'*' if (r, c) == target else board.get((r, c), ' ')} " for c in range(3)) + "│"

    return ["┌───┬───┬───┐", row(0), "├───┼───┼───┤", row(1), "├───┼───┼───┤", row(2), "└───┴───┴───┘"]


def main():
    global LANG
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--round", type=int, required=True, help="round number")
    ap.add_argument("--episodes", type=int, default=5, help="episodes per cell")
    ap.add_argument("--first", type=int, default=0, help="first episode number of the round (dataset episode_index)")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--lang", choices=["en", "tr"], default="en", help="language of the generated document")
    args = ap.parse_args()
    LANG = args.lang

    rng = random.Random(args.seed)
    cells = CELLS[:]
    rng.shuffle(cells)

    command = (
        f"python scripts/recording_plan.py --round {args.round} --episodes {args.episodes} "
        f"--first {args.first} --seed {args.seed}" + ("" if args.lang == "en" else f" --lang {args.lang}")
    )
    total = len(cells) * args.episodes
    print(t("title", round=args.round, blocks=len(cells), episodes=args.episodes, total=total))
    print(t("switch", round=args.round))
    print(t("generated", command=command))
    print(t("explanation"))

    no = args.first
    for b, target in enumerate(cells, 1):
        x_counts = [i % 5 for i in range(args.episodes)]
        rng.shuffle(x_counts)
        boards = [(no + i, draw(build_board(target, k, rng), target)) for i, k in enumerate(x_counts)]
        print(t("block", block=b, first=no, last=no + args.episodes - 1))
        resume = t("first_block") if b == 1 and args.first == 0 else " `--resume=true`"
        print(f'`--dataset.single_task="{task(target)}"`' + resume + "\n")
        print("```")
        print("   ".join(f"#{n:<12}" for n, _ in boards))
        for line in range(7):
            print("   ".join(board[line] for _, board in boards))
        print("```\n")
        no += args.episodes


if __name__ == "__main__":
    main()
