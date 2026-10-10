"""The tic-tac-toe board: cell names, the task sentence, the terminal drawing and the winner.

Cell names are in the robot's frame: top = far from the arm base, left = the arm's left.
"""

from . import i18n

ROWS = ["top", "middle", "bottom"]
COLS = ["left", "center", "right"]
CELLS = [f"{r} {c}" for r in ROWS for c in COLS]
LINES = (
    [[r * 3 + c for c in range(3)] for r in range(3)]
    + [[r * 3 + c for r in range(3)] for c in range(3)]
    + [[0, 4, 8], [2, 4, 6]]
)


def task_sentence(cell: str) -> str:
    """The exact sentence the policy was trained on."""
    return f"put the red X in the {cell} cell"


def draw(board: list[str], lang: str | None = None) -> str:
    lines = [i18n.MESSAGES["board_far_side"][lang or i18n.LANG], "         ┌───┬───┬───┐"]
    for r in range(3):
        lines.append("         │ " + " │ ".join(board[r * 3 + c] for c in range(3)) + " │")
        lines.append("         ├───┼───┼───┤" if r < 2 else "         └───┴───┴───┘")
    lines.append("             ROBOT")
    return "\n".join(lines)


def winner(board: list[str]) -> str | None:
    for a, b, c in LINES:
        if board[a] != " " and board[a] == board[b] == board[c]:
            return board[a]
    return None
