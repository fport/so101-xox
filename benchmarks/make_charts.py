"""`benchmarks/data/` -> the charts in `docs/assets/benchmarks/`.

Needs nothing but the committed CSV files: no logs, no dataset, no arm, no model. Run from the repo root,
in a throwaway environment (matplotlib is not in the repo's virtualenvs and is not installed into them):

    uv run --no-project --with matplotlib --with pandas --with pyarrow --with numpy --with pillow \
        python benchmarks/make_charts.py

Every chart is written four times: `<name>.png` and `<name>.svg` with English labels, `<name>.tr.png` and
`<name>.tr.svg` with Turkish labels. All text on the charts comes from the label table `TEXT` below.
The PNGs are 1600 px wide and meant to be shown at 800 px.

One style for all charts: white background, dark grey text, blue for queued inference, orange for `sync`
inference, greys for everything else. Small samples are drawn as individual points; nothing is fitted and
no error bars are drawn.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import FuncFormatter
from matplotlib.transforms import blended_transform_factory

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
OUT = HERE.parent / "docs" / "assets" / "benchmarks"

# ---------------------------------------------------------------- style

INK = "#24292f"  # titles, values
TEXT_GREY = "#57606a"  # axis labels, captions
MUTED = "#8c959f"  # secondary marks
GRID = "#e4e6e8"  # hairlines
BAND = "#f1f2f3"  # light fills
QUEUED = "#2a78d6"  # queued inference (runs 2 and 3)
SYNC = "#eb6834"  # sync inference (run 4, every move after it)
MODE_COLOUR = {"queued": QUEUED, "sync": SYNC}
WIDTH_IN, DPI = 8.0, 200  # 1600 px wide

plt.rcParams.update({
    "font.family": "DejaVu Sans",  # ships with matplotlib and has the Turkish letters
    "font.size": 8.5,
    "text.color": INK,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": TEXT_GREY,
    "axes.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titlesize": 8.5,
    "xtick.color": TEXT_GREY,
    "ytick.color": TEXT_GREY,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "xtick.major.size": 3,
    "ytick.major.size": 3,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
    "legend.frameon": False,
    "legend.fontsize": 8,
    "svg.hashsalt": "so101-xox-benchmarks",  # stable ids, so the SVG is the same on every run
})

# ---------------------------------------------------------------- labels (English, Turkish)

TEXT = {
    # shared
    "time_axis": ("time since the first command (s)", "ilk komuttan beri geçen süre (sn)"),
    "queued": ("queued", "kuyruklu"),
    "sync": ("sync", "sync"),
    "run": ("run {n}", "{n}. koşu"),
    "move_n": ("move {n}", "{n}. hamle"),
    "seconds": ("{v} s", "{v} sn"),
    "target_cell": ("target cell", "hedef hücre"),
    # A
    "a_title": ("Jerky motion: how far the command moves in one step", "Sarsıntılı hareket: komut bir adımda ne kadar değişiyor"),
    "a_sub": (
        "Largest change among the five arm joints from one control step (1/30 s) to the next. One run per row, n = 3 runs.",
        "Bir kontrol adımından (1/30 sn) ötekine, beş kol ekleminden en çok değişenin değişimi. Her satır bir koşu, n = 3 koşu.",
    ),
    "a_y": ("change per step (°)", "adım başına değişim (°)"),
    "a_panel": ("{run} · {mode} · {steps} steps", "{run} · {mode} · {steps} adım"),
    "a_six": ("6°", "6°"),
    "a_leg_boundary": ("chunk boundary (every 50 steps)", "parça sınırı (her 50 adımda)"),
    "a_leg_on": ("step with a jump above 6°, on a chunk boundary", "6°'den büyük sıçramalı adım, parça sınırında"),
    "a_leg_off": ("step with a jump above 6°, elsewhere", "6°'den büyük sıçramalı adım, başka yerde"),
    "a_col_run": ("run", "koşu"),
    "a_col_steps": ("policy\nsteps", "politika\nadımı"),
    "a_col_bound": ("chunk\nboundaries", "parça\nsınırı"),
    "a_col_jumps": ("steps with a\njump above 6°", "6°'den büyük\nsıçramalı adım"),
    "a_col_on": ("of those, on a\nchunk boundary", "bunlardan parça\nsınırında olan"),
    "a_col_max": ("largest\njump", "en büyük\nsıçrama"),
    "a_col_median": ("median\nstep", "ortanca\nadım"),
    "a_row_both": ("runs 2 + 3", "2. + 3. koşu"),
    "a_row": ("{run} ({mode})", "{run} ({mode})"),
    # B
    "b_title": ("One successful move: commanded and measured joint angles, run 4", "Başarılı bir hamle: komut edilen ve ölçülen eklem açıları, 4. koşu"),
    "b_sub": (
        "sync inference, target cell middle center, {steps} control steps. One run, n = 1.",
        "sync çıkarım, hedef hücre middle center, {steps} kontrol adımı. Tek koşu, n = 1.",
    ),
    "b_cmd": ("commanded", "komut"),
    "b_meas": ("measured", "ölçülen"),
    "b_held": ("X in the gripper", "X tutucuda"),
    "b_pick": ("pick {v} s", "alma {v} sn"),
    "b_release": ("release {v} s", "bırakma {v} sn"),
    "b_deg": ("angle (°)", "açı (°)"),
    "b_grip": ("opening (% of range)", "açıklık (aralığın %'si)"),
    # C
    "c_title": ("How long the arm waits before it starts, and how long a move takes", "Kol başlamadan önce ne kadar bekliyor, bir hamle ne kadar sürüyor"),
    "c_sub": (
        "One row per logged move, n = {n}: {full} with the return in the log, {cut} whose log ends first. Time 0 is the first command.",
        "Her satır kayıtlı bir hamle, n = {n}: {full} tanesinde dönüş kayıtta, {cut} tanesinde kayıt daha önce bitiyor. 0 anı ilk komut.",
    ),
    "c_direct": ("Direct policy runs", "Doğrudan politika koşuları"),
    "c_move": ("move command, no Claude", "move komutu, Claude yok"),
    "c_game1": ("First game with Claude", "Claude ile ilk oyun"),
    "c_game2": ("Automatic game", "Otomatik oyun"),
    "c_start": ("arm starts", "kol harekete geçiyor"),
    "c_back": ("back at rest", "dinlenme pozuna döndü"),
    "c_cut": ("log ends before the return", "kayıt dönüşten önce bitiyor"),
    "c_logged": ("logged time", "kayıtlı süre"),
    "c_col_start": ("start", "başlangıç"),
    "c_col_back": ("back", "dönüş"),
    "c_none": ("not logged", "kayıtta yok"),
    "c_false_start": ("false start at {v} s, pulled back", "{v} sn'de yalancı başlangıç, geri çekildi"),
    "c_cutoff": ("20 s limit: cut off", "20 sn sınırı: kesildi"),
    "c_idle": ("idle at rest until the 60 s limit", "60 sn sınırına kadar dinlenmede"),
    # D
    "d_title": ("The 45 demonstrations: length, pause before moving, start boards", "45 gösterim: süre, hareketten önceki bekleme, başlangıç tahtaları"),
    "d_sub": (
        "One point per episode, n = 45, five per target cell. Cells in recording order; within a cell, left to right in recording order.",
        "Her nokta bir bölüm, n = 45, hedef hücre başına beş. Hücreler kayıt sırasıyla; hücre içinde soldan sağa kayıt sırası.",
    ),
    "d_len": ("episode length (s)", "bölüm süresi (sn)"),
    "d_pause": ("pause before the\nfirst motion (s)", "ilk hareketten önceki\nbekleme (sn)"),
    "d_pieces": ("pieces on the board\nat the start", "başlangıçta tahtadaki\ntaş sayısı"),
    "d_day1": ("recorded 2026-10-06 (n = {n})", "2026-10-06'da kaydedildi (n = {n})"),
    "d_day2": ("recorded 2026-10-10 (n = {n})", "2026-10-10'da kaydedildi (n = {n})"),
    "d_mean": ("mean {v} s", "ortalama {v} sn"),
    # E
    "e_title": ("Where the arm was asked to go: completed moves per cell", "Koldan nereye gitmesi istendi: hücre başına tamamlanan hamle"),
    "e_sub": (
        "X in the right cell / completed moves on the real arm, n = {n} moves in {cells} of 9 cells. A tally of what was tried, not a success rate.",
        "Doğru hücredeki X / gerçek kolda tamamlanan hamle, 9 hücrenin {cells} tanesinde n = {n} hamle. Denenenlerin dökümü; başarı oranı değil.",
    ),
    "e_not_tried": ("not tried", "denenmedi"),
    "e_far": ("far from the robot", "robottan uzak"),
    "e_base": ("arm base", "kol tabanı"),
    "e_left": ("robot's left", "robotun solu"),
    "e_right": ("robot's right", "robotun sağı"),
    "e_frame": ("X seen in the cell in a later frame on disk ({n})", "X sonraki bir karede hücrede görülüyor ({n})"),
    "e_notes": ("landed per the notes; the log ends at the release ({n})", "notlara göre kondu; kayıt bırakma anında bitiyor ({n})"),
    "e_kind_direct": ("direct run", "doğrudan koşu"),
    "e_kind_move": ("move command", "move komutu"),
    "e_kind_game": ("game", "oyun"),
    # F
    "f_title": ("The local detectors against their thresholds", "Yerel algılayıcılar ve eşikleri"),
    "f_sub": (
        "From top-camera frames on disk, with the game script's boxes and formulas. A point is one board cell (left) or one frame (right).",
        "Diskteki üst kamera karelerinden, oyun betiğinin kutuları ve formülleriyle. Bir nokta solda bir hücre, sağda bir kare.",
    ),
    "f_left": ("Did a cell change?", "Bir hücre değişti mi?"),
    "f_right": ("Is there an X in the pick slot?", "Alma yuvasında X var mı?"),
    "f_y_cell": ("mean grey difference of the cell (0–255)", "hücrenin ortalama gri farkı (0–255)"),
    "f_y_slot": ("share of red pixels in the slot box", "yuva kutusundaki kırmızı piksel oranı"),
    "f_threshold": ("threshold {v}", "eşik {v}"),
    "f_g_same": ("same scene,\nfive captures\n(n = {n})", "aynı sahne,\nbeş çekim\n(n = {n})"),
    "f_g_quiet": ("between moves:\nno new piece\n(n = {n})", "hamleler arasında:\nyeni taş yok\n(n = {n})"),
    "f_g_gripper": ("no new piece,\nunder the resting\ngripper (n = {n})", "yeni taş yok,\ndinlenen tutucunun\naltında (n = {n})"),
    "f_g_new": ("a piece was\nadded\n(n = {n})", "taş\neklendi\n(n = {n})"),
    "f_moved": ("an X already there was\nstraightened by hand", "tahtadaki bir X\nelle düzeltildi"),
    "f_s_x": ("X in the slot\n(n = {n} frames)", "yuvada X var\n(n = {n} kare)"),
    "f_s_empty": ("slot empty\n(n = {n} frames)", "yuva boş\n(n = {n} kare)"),
}

LANG = "en"


def T(key: str, **fmt) -> str:
    return TEXT[key][LANG == "tr"].format(**fmt)


def num(value: float, digits: int = 1) -> str:
    """A number with the decimal mark of the current language."""
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if LANG == "tr" else text


def tick_format(digits: int = 0) -> FuncFormatter:
    return FuncFormatter(lambda value, _: num(value, digits))


def run_name(run_id: str) -> str:
    return T("run", n=run_id[-1])


def header(fig, title: str, subtitle: str, top: float = 0.975) -> None:
    """Title and one-line caption, left-aligned at the figure edge."""
    fig.text(0.02, top, title, fontsize=11.5, fontweight="bold", va="top", ha="left")
    height = fig.get_size_inches()[1]
    fig.text(0.02, top - 0.27 / height, subtitle, fontsize=8.2, color=TEXT_GREY, va="top", ha="left")


def save(fig, name: str) -> None:
    suffix = ".tr" if LANG == "tr" else ""
    fig.savefig(OUT / f"{name}{suffix}.png", dpi=DPI, metadata={"Software": None})
    fig.savefig(OUT / f"{name}{suffix}.svg", metadata={"Date": None, "Creator": None})
    plt.close(fig)


def swarm(values: np.ndarray, radius_y: float, step_x: float) -> np.ndarray:
    """Horizontal offsets that keep points with close values from overlapping (deterministic)."""
    order = np.argsort(values, kind="stable")
    placed: list[tuple[float, float]] = []
    offsets = np.zeros(len(values))
    for i in order:
        k = 0
        while True:
            candidate = ((k + 1) // 2) * step_x * (1 if k % 2 else -1)
            if all(abs(values[i] - y) > radius_y or abs(candidate - x) >= step_x * 0.999 for x, y in placed):
                break
            k += 1
        offsets[i] = candidate
        placed.append((candidate, values[i]))
    return offsets


# ---------------------------------------------------------------- A: jerky motion


def chart_a() -> None:
    summary = pd.read_csv(DATA / "arm_run_summary.csv").set_index("run")
    bounds = pd.read_csv(DATA / "arm_chunk_boundaries.csv")
    fig = plt.figure(figsize=(WIDTH_IN, 7.0))
    header(fig, T("a_title"), T("a_sub"))
    grid = fig.add_gridspec(3, 1, left=0.075, right=0.975, top=0.825, bottom=0.345, hspace=0.2)
    axes = grid.subplots(sharex=True, sharey=True)
    for ax, (run_id, row) in zip(axes, summary.iterrows()):
        steps = pd.read_csv(DATA / f"arm_{run_id}_{row.inference}.csv")
        steps = steps[steps.phase == "policy"]
        command = steps[[c for c in steps.columns if c.startswith("cmd_")]].to_numpy()[:, :5]
        jump = np.concatenate([[0.0], np.abs(np.diff(command, axis=0)).max(axis=1)])
        big = np.where(jump > 6.0)[0]
        # The summary table was computed from the unrounded logs; the committed per-step file must agree.
        assert len(big) == row.jumps_over_6deg and (big % 50 == 0).sum() == row.jumps_over_6deg_on_chunk_boundary
        assert abs(jump.max() - row.max_jump_deg) < 0.01 and len(steps) == row.policy_steps
        colour = MODE_COLOUR[row.inference]
        ax.vlines(bounds[bounds.run == run_id].t_s, 0, 32, color=GRID, lw=0.7, zorder=1)
        ax.axhline(6, color=INK, lw=0.6, zorder=2)
        ax.plot(steps.t_s, jump, color=colour, lw=0.9, zorder=3, solid_joinstyle="round")
        on = big[big % 50 == 0]
        off = big[big % 50 != 0]
        ax.scatter(steps.t_s.to_numpy()[on], jump[on], s=22, color=colour, edgecolor="white", linewidth=0.8, zorder=4)
        ax.scatter(steps.t_s.to_numpy()[off], jump[off], s=22, facecolor="white", edgecolor=colour, linewidth=1.1, zorder=4)
        ax.text(0.995, 0.93, T("a_panel", run=run_name(run_id), mode=T(row.inference), steps=len(steps)), transform=ax.transAxes,
                ha="right", va="top", fontsize=8.5, fontweight="bold")
        ax.set_ylim(0, 32)
        ax.set_yticks([0, 10, 20, 30])
        ax.set_xlim(-0.5, 54.5)
        ax.text(54.3, 6.9, T("a_six"), ha="right", va="bottom", fontsize=7.5, color=TEXT_GREY)
    axes[1].set_ylabel(T("a_y"))
    axes[-1].set_xlabel(T("time_axis"))
    lines = [
        Line2D([], [], color=QUEUED, lw=1.6, label=T("queued")),
        Line2D([], [], color=SYNC, lw=1.6, label=T("sync")),
        Line2D([], [], color=MUTED, lw=0, marker="|", markersize=9, markeredgewidth=0.9, label=T("a_leg_boundary")),
    ]
    dots = [
        Line2D([], [], color=TEXT_GREY, lw=0, marker="o", markersize=5, label=T("a_leg_on")),
        Line2D([], [], color=TEXT_GREY, lw=0, marker="o", markersize=5, markerfacecolor="white", label=T("a_leg_off")),
    ]
    fig.add_artist(fig.legend(handles=lines, loc="upper left", bbox_to_anchor=(0.065, 0.917), ncol=3, columnspacing=1.6, handletextpad=0.5))
    fig.legend(handles=dots, loc="upper left", bbox_to_anchor=(0.065, 0.889), ncol=2, columnspacing=1.6, handletextpad=0.5)

    # The numbers behind the picture.
    table = fig.add_axes([0.02, 0.02, 0.96, 0.255])
    table.axis("off")
    table.set_xlim(0, 1)
    table.set_ylim(0, 1)
    columns = [0.02, 0.33, 0.45, 0.59, 0.75, 0.885, 0.985]
    names = ["a_col_run", "a_col_steps", "a_col_bound", "a_col_jumps", "a_col_on", "a_col_max", "a_col_median"]
    for x, name in zip(columns, names):
        table.text(x, 0.97, T(name), ha="left" if name == "a_col_run" else "right", va="top", fontsize=7.8, color=TEXT_GREY, linespacing=1.25)
    table.plot([0.0, 1.0], [0.70, 0.70], color=MUTED, lw=0.6)
    rows = [(run_id, T("a_row", run=run_name(run_id), mode=T(r.inference)), MODE_COLOUR[r.inference], r.policy_steps, r.chunk_boundaries,
             r.jumps_over_6deg, r.jumps_over_6deg_on_chunk_boundary, r.max_jump_deg, r.median_step_deg) for run_id, r in summary.iterrows()]
    queued = summary[summary.inference == "queued"]
    rows.append(("both", T("a_row_both"), QUEUED, queued.policy_steps.sum(), queued.chunk_boundaries.sum(), queued.jumps_over_6deg.sum(),
                 queued.jumps_over_6deg_on_chunk_boundary.sum(), queued.max_jump_deg.max(), None))
    for i, (run_id, label, colour, steps, boundaries, jumps, on, largest, median) in enumerate(rows):
        y = 0.56 - i * 0.165
        if run_id == "both":
            table.plot([0.0, 1.0], [y + 0.085, y + 0.085], color=GRID, lw=0.6)
        table.plot([0.0, 0.012], [y, y], color=colour, lw=2.2, solid_capstyle="butt")
        table.text(columns[0], y, label, va="center", fontsize=8.5, fontweight="bold" if run_id != "both" else "normal")
        cells = [f"{steps:d}", f"{boundaries:d}", f"{jumps:d}", f"{on:d}", f"{num(largest)}°", "" if median is None else f"{num(median)}°"]
        for x, value in zip(columns[1:], cells):
            table.text(x, y, value, ha="right", va="center", fontsize=8.5)
    save(fig, "a_jerky_motion")


# ---------------------------------------------------------------- B: one successful move


def chart_b() -> None:
    steps = pd.read_csv(DATA / "arm_run4_sync.csv")
    steps = steps[steps.phase == "policy"]
    events = pd.read_csv(DATA / "run4_events.csv").set_index("event").t_s
    joints = [c[4:] for c in steps.columns if c.startswith("cmd_")]
    fig = plt.figure(figsize=(WIDTH_IN, 6.5))
    header(fig, T("b_title"), T("b_sub", steps=len(steps)))
    axes = fig.add_gridspec(3, 2, left=0.075, right=0.975, top=0.83, bottom=0.075, hspace=0.34, wspace=0.2).subplots(sharex=True)
    for ax, joint in zip(axes.T.flat, joints):
        ax.axvspan(events.pick, events.release, color=BAND, lw=0, zorder=0)
        ax.plot(steps.t_s, steps[f"meas_{joint}"], color=MUTED, lw=2.4, zorder=2, solid_capstyle="round")
        ax.plot(steps.t_s, steps[f"cmd_{joint}"], color=SYNC, lw=0.9, zorder=3)
        ax.set_title(joint, loc="left", fontweight="bold", pad=4)
        ax.set_xlim(0, 30)
        ax.set_xticks([0, 5, 10, 15, 20, 25, 30])
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.margins(y=0.12)
        if joint == "gripper":
            ax.set_ylim(-1.5, 22)
            ax.set_yticks([0, 5, 10, 15, 20])
            ax.set_ylabel(T("b_grip"))
            ax.vlines([events.pick, events.release], -1.5, 22, color=INK, lw=0.7, zorder=1)
            ax.text(events.pick - 0.35, 21.3, T("b_pick", v=num(events.pick)), va="top", ha="right", fontsize=8)
            ax.text(events.release + 0.35, 21.3, T("b_release", v=num(events.release)), va="top", ha="left", fontsize=8)
    axes[1, 0].set_ylabel(T("b_deg"))
    for ax in axes[-1]:
        ax.set_xlabel(T("time_axis"))
    handles = [
        Line2D([], [], color=SYNC, lw=1.4, label=T("b_cmd")),
        Line2D([], [], color=MUTED, lw=2.6, label=T("b_meas")),
        Patch(facecolor=BAND, edgecolor=GRID, label=T("b_held")),
    ]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.065, 0.905), ncol=3, columnspacing=1.6)
    save(fig, "b_one_move")


# ---------------------------------------------------------------- C: waiting and move time


def chart_c() -> None:
    moves = pd.read_csv(DATA / "moves.csv")
    shown = moves[(moves.counted_as_completed == "yes") | (moves.move == "run2")].set_index("move")
    groups = [
        ("c_direct", ["run2", "run3", "run4"]),
        ("c_move", ["move_top_left", "move_bottom_left"]),
        ("c_game1", ["game1_move1", "game1_move2", "game1_move3"]),
        ("c_game2", ["game2_move1", "game2_move2", "game2_move3"]),
    ]
    assert sorted(m for _, g in groups for m in g) == sorted(shown.index)
    full = int((shown.returned_in_log == "yes").sum())
    fig = plt.figure(figsize=(WIDTH_IN, 5.6))
    header(fig, T("c_title"), T("c_sub", n=len(shown), full=full, cut=len(shown) - full))
    ax = fig.add_axes([0.335, 0.095, 0.49, 0.705])
    side = blended_transform_factory(fig.transFigure, ax.transData)  # x in figure fractions, y in rows
    limit = 31.0
    y, ticks = 0.0, []
    for title, members in groups:
        ax.text(0.02, y + 0.05, T(title), transform=side, fontsize=8.3, color=TEXT_GREY, va="center", ha="left")
        y -= 0.85
        for move_id in members:
            row = shown.loc[move_id]
            colour = MODE_COLOUR[row.inference]
            if move_id.startswith("run"):
                name = f"{run_name(move_id)} ({T(row.inference)})"
            elif move_id.startswith("game"):
                name = T("move_n", n=move_id[-1])
            else:
                name = "move"
            ax.text(0.035, y, name, transform=side, fontsize=8.5, va="center", ha="left", fontweight="bold")
            ax.text(0.326, y, row.cell, transform=side, fontsize=8.5, va="center", ha="right", color=TEXT_GREY)
            end = min(row.end_s, limit)
            ax.plot([0, end], [y, y], color=MUTED, lw=1.0, zorder=2, solid_capstyle="butt")
            stop = row.back_s if row.returned_in_log == "yes" else row.end_s
            ax.plot([row.start_s, stop], [y, y], color=colour, lw=4.2, zorder=3, solid_capstyle="butt")
            ax.scatter([row.start_s], [y], s=46, color=colour, edgecolor="white", linewidth=1.0, zorder=5)
            if row.returned_in_log == "yes":
                ax.scatter([row.back_s], [y], s=46, marker="s", color=colour, edgecolor="white", linewidth=1.0, zorder=5)
                back = T("seconds", v=num(row.back_s))
            else:
                ax.scatter([row.end_s], [y], s=44, marker="x", color=INK, linewidth=1.3, zorder=5)
                back = T("c_none")
            if row.end_s > limit:
                ax.annotate("", xy=(limit + 0.6, y), xytext=(limit - 0.9, y), arrowprops={"arrowstyle": "->", "color": MUTED, "lw": 1.0},
                            annotation_clip=False)
                ax.text(limit - 0.2, y + 0.33, T("c_idle"), fontsize=7.4, color=TEXT_GREY, ha="right", va="center")
            if move_id == "run2":
                ax.scatter([row.first_leave_s], [y], s=26, facecolor="white", edgecolor=colour, linewidth=1.1, zorder=4)
                ax.text(row.first_leave_s - 0.3, y + 0.36, T("c_false_start", v=num(row.first_leave_s)), fontsize=7.4, color=TEXT_GREY, ha="left", va="center")
                ax.text(row.end_s + 0.6, y, T("c_cutoff"), fontsize=7.4, color=TEXT_GREY, ha="left", va="center")
            ax.text(0.885, y, T("seconds", v=num(row.start_s)), transform=side, fontsize=8.5, va="center", ha="right")
            ax.text(0.985, y, back, transform=side, fontsize=8.5, va="center", ha="right",
                    color=INK if row.returned_in_log == "yes" else TEXT_GREY)
            ticks.append(y)
            y -= 1.0
        y -= 0.35
    ax.text(0.885, 0.05, T("c_col_start"), transform=side, fontsize=8.3, color=TEXT_GREY, va="center", ha="right")
    ax.text(0.985, 0.05, T("c_col_back"), transform=side, fontsize=8.3, color=TEXT_GREY, va="center", ha="right")
    ax.set_ylim(y + 0.75, 0.55)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlim(0, limit)
    ax.set_xticks([0, 5, 10, 15, 20, 25, 30])
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.set_xlabel(T("time_axis"))
    handles = [
        Line2D([], [], color=TEXT_GREY, lw=0, marker="o", markersize=6.5, label=T("c_start")),
        Line2D([], [], color=TEXT_GREY, lw=0, marker="s", markersize=6, label=T("c_back")),
        Line2D([], [], color=INK, lw=0, marker="x", markersize=6, markeredgewidth=1.3, label=T("c_cut")),
        Line2D([], [], color=QUEUED, lw=4.2, label=T("queued")),
        Line2D([], [], color=SYNC, lw=4.2, label=T("sync")),
        Line2D([], [], color=MUTED, lw=1.0, label=T("c_logged")),
    ]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.012, 0.895), ncol=6, columnspacing=1.3, handletextpad=0.5, handlelength=1.5)
    save(fig, "c_wait_and_move_time")


# ---------------------------------------------------------------- D: the demonstrations


def chart_d() -> None:
    episodes = pd.read_csv(DATA / "episodes.csv")
    cells = list(dict.fromkeys(episodes.sort_values("block").cell))  # recording order of the blocks
    fig = plt.figure(figsize=(WIDTH_IN, 7.2))
    header(fig, T("d_title"), T("d_sub"))
    axes = fig.add_gridspec(3, 1, left=0.105, right=0.975, top=0.845, bottom=0.085, hspace=0.16, height_ratios=[1.15, 1, 1]).subplots(sharex=True)
    x = np.zeros(len(episodes))
    for position, cell in enumerate(cells):
        index = episodes.index[episodes.cell == cell]  # already in recording order
        x[index] = position + np.linspace(-0.26, 0.26, len(index))
    first_day = (episodes.recorded_on == "2026-10-06").to_numpy()
    panels = [
        (axes[0], episodes.duration_s, T("d_len"), (0, 30), [0, 10, 20, 30]),
        (axes[1], episodes.first_motion_action_s, T("d_pause"), (0, 5.4), [0, 1, 2, 3, 4, 5]),
        (axes[2], episodes.pieces_at_start, T("d_pieces"), (-0.6, 8.6), [0, 2, 4, 6, 8]),
    ]
    for ax, values, label, limits, ticks in panels:
        values = values.to_numpy()
        for position in range(len(cells)):
            if position % 2 == 0:
                ax.axvspan(position - 0.5, position + 0.5, color=BAND, lw=0, zorder=0)
        ax.scatter(x[first_day], values[first_day], s=30, color=TEXT_GREY, edgecolor="white", linewidth=0.7, zorder=3)
        ax.scatter(x[~first_day], values[~first_day], s=24, facecolor="white", edgecolor=TEXT_GREY, linewidth=1.3, zorder=3)
        ax.set_ylabel(label)
        ax.set_ylim(*limits)
        ax.set_yticks(ticks)
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(axis="x", length=0)
    mean = episodes.first_motion_action_s.mean()
    axes[1].axhline(mean, color=INK, lw=0.7, zorder=2)
    axes[1].text(len(cells) - 0.52, mean + 0.12, T("d_mean", v=num(mean)), ha="right", va="bottom", fontsize=8)
    axes[2].set_xlim(-0.5, len(cells) - 0.5)
    axes[2].set_xticks(range(len(cells)))
    axes[2].set_xticklabels([c.replace(" ", "\n") for c in cells], color=INK)
    axes[2].set_xlabel(T("target_cell"))
    handles = [
        Line2D([], [], color=TEXT_GREY, lw=0, marker="o", markersize=6, label=T("d_day1", n=int(first_day.sum()))),
        Line2D([], [], color=TEXT_GREY, lw=0, marker="o", markersize=5.5, markerfacecolor="white", markeredgewidth=1.3,
               label=T("d_day2", n=int((~first_day).sum()))),
    ]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.095, 0.912), ncol=2, columnspacing=1.6)
    save(fig, "d_demonstrations")


# ---------------------------------------------------------------- E: where the arm was asked to go


def chart_e() -> None:
    tally = pd.read_csv(DATA / "cell_tally.csv").set_index("cell")
    moves = pd.read_csv(DATA / "moves.csv")
    done = moves[moves.counted_as_completed == "yes"]
    fig = plt.figure(figsize=(WIDTH_IN, 6.2))
    header(fig, T("e_title"), T("e_sub", n=int(tally.completed_moves.sum()), cells=int((tally.completed_moves > 0).sum())))
    side = 4.25 / 6.2  # the board is 4.25 in wide and high
    ax = fig.add_axes([(1 - 4.25 / WIDTH_IN) / 2, 0.135, 4.25 / WIDTH_IN, side])
    ax.set_xlim(0, 3)
    ax.set_ylim(3, 0)
    ax.axis("off")
    kinds = {"direct": "e_kind_direct", "move": "e_kind_move", "game 1": "e_kind_game", "game 2": "e_kind_game"}
    for r, row_name in enumerate(("top", "middle", "bottom")):
        for c, col_name in enumerate(("left", "center", "right")):
            cell = f"{row_name} {col_name}"
            count = tally.loc[cell]
            tried = count.completed_moves > 0
            ax.add_patch(Rectangle((c + 0.03, r + 0.03), 0.94, 0.94, facecolor=BAND if tried else "white", edgecolor=GRID if tried else MUTED,
                                   linewidth=0.8, linestyle="-" if tried else (0, (2, 2))))
            ax.text(c + 0.5, r + 0.17, cell, ha="center", va="center", fontsize=8.5, color=TEXT_GREY)
            if not tried:
                ax.text(c + 0.5, r + 0.52, T("e_not_tried"), ha="center", va="center", fontsize=9, color=MUTED)
                continue
            ax.text(c + 0.5, r + 0.45, f"{count.landed} / {count.completed_moves}", ha="center", va="center", fontsize=17, fontweight="bold")
            here = done[done.cell == cell]
            xs = c + 0.5 + (np.arange(len(here)) - (len(here) - 1) / 2) * 0.13
            seen = (here.landed_evidence == "frame").to_numpy()
            ax.scatter(xs[seen], np.full(seen.sum(), r + 0.655), s=42, color=TEXT_GREY, edgecolor="white", linewidth=0.8, zorder=3)
            ax.scatter(xs[~seen], np.full((~seen).sum(), r + 0.655), s=34, facecolor="white", edgecolor=TEXT_GREY, linewidth=1.3, zorder=3)
            names = here.kind.map(kinds)
            parts = [f"{T(k)} ×{n}" for k, n in names.value_counts(sort=False).items()]
            ax.text(c + 0.5, r + 0.85, "\n".join(parts), ha="center", va="center", fontsize=7.6, color=TEXT_GREY, linespacing=1.25)
    ax.text(1.5, -0.07, T("e_far"), ha="center", va="bottom", fontsize=8.3, color=TEXT_GREY)
    ax.text(1.5, 3.07, T("e_base"), ha="center", va="top", fontsize=8.3, color=TEXT_GREY)
    ax.text(-0.08, 1.5, T("e_left"), ha="right", va="center", fontsize=8.3, color=TEXT_GREY, rotation=90)
    ax.text(3.08, 1.5, T("e_right"), ha="left", va="center", fontsize=8.3, color=TEXT_GREY, rotation=270)
    handles = [
        Line2D([], [], color=TEXT_GREY, lw=0, marker="o", markersize=6.5, label=T("e_frame", n=int(tally.landed_seen_in_frame.sum()))),
        Line2D([], [], color=TEXT_GREY, lw=0, marker="o", markersize=6, markerfacecolor="white", markeredgewidth=1.3,
               label=T("e_notes", n=int(tally.landed_per_notes_only.sum()))),
    ]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.005), ncol=1, handletextpad=0.5)
    save(fig, "e_cells_tried")


# ---------------------------------------------------------------- F: the local detectors


def chart_f() -> None:
    cells = pd.read_csv(DATA / "detector_cells.csv")
    slot = pd.read_csv(DATA / "detector_slot.csv")
    numbers = pd.read_csv(DATA / "key_numbers.csv").set_index("key").value
    change, red = float(numbers.change_threshold), float(numbers.slot_threshold)
    game = cells[cells.group == "game"]
    no_piece = game.piece_added.isna()
    groups = [
        ("f_g_same", cells[cells.group == "unchanged"]),
        ("f_g_quiet", game[no_piece & (game.under_resting_gripper == "no")]),
        ("f_g_gripper", game[no_piece & (game.under_resting_gripper == "yes")]),
        ("f_g_new", game[~no_piece]),
    ]
    fig = plt.figure(figsize=(WIDTH_IN, 4.3))
    header(fig, T("f_title"), T("f_sub"))
    left = fig.add_axes([0.075, 0.185, 0.545, 0.6])
    right = fig.add_axes([0.725, 0.185, 0.25, 0.6])

    left.axhline(change, color=INK, lw=0.7, zorder=2)
    left.text(-0.44, change + 0.5, T("f_threshold", v=num(change, 0)), fontsize=8, va="bottom", ha="left")
    for position, (label, part) in enumerate(groups):
        values = part.mean_abs_grey_diff.to_numpy()
        if label == "f_g_same":  # too many near-equal values for a swarm: one column per frame pair
            pairs = part.pair.astype("category").cat.codes.to_numpy()
            left.scatter(position + (pairs - pairs.max() / 2) * 0.055, values, s=9, color=TEXT_GREY, alpha=0.75, linewidth=0, zorder=3)
            continue
        offsets = swarm(values, radius_y=0.75, step_x=0.05)
        moved = (part.existing_piece_moved == "yes").to_numpy()
        left.scatter(position + offsets[~moved], values[~moved], s=22, color=TEXT_GREY, edgecolor="white", linewidth=0.6, zorder=3)
        if moved.any():
            left.scatter(position + offsets[moved], values[moved], s=22, facecolor="white", edgecolor=TEXT_GREY, linewidth=1.2, zorder=3)
            left.annotate(T("f_moved"), xy=(position + offsets[moved][0] + 0.05, values[moved][0] + 0.3), xytext=(position - 0.38, 24.5),
                          fontsize=7.6, color=TEXT_GREY, ha="left", va="center",
                          arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.6, "shrinkA": 1, "shrinkB": 2})
    left.set_xlim(-0.5, len(groups) - 0.5)
    left.set_xticks(range(len(groups)))
    left.set_xticklabels([T(label, n=len(part)) for label, part in groups], color=INK, fontsize=7.8)
    left.tick_params(axis="x", length=0, pad=6)
    left.set_ylim(0, 32)
    left.set_yticks([0, 10, 20, 30])
    left.set_ylabel(T("f_y_cell"))
    left.grid(axis="y", color=GRID, lw=0.6)
    left.set_axisbelow(True)
    left.set_title(T("f_left"), loc="left", fontweight="bold", pad=8)

    right.axhline(red, color=INK, lw=0.7, zorder=2)
    right.text(1.46, red + 0.006, T("f_threshold", v=num(red, 3)), fontsize=8, va="bottom", ha="right")
    for position, (label, state) in enumerate((("f_s_x", "X"), ("f_s_empty", "empty"))):
        values = slot[slot.slot_by_eye == state].red_share.to_numpy()
        right.scatter(position + swarm(values, radius_y=0.008, step_x=0.06 if state == "empty" else 0.075), values, s=22, color=TEXT_GREY, edgecolor="white", linewidth=0.6, zorder=3)
    states = [("f_s_x", "X"), ("f_s_empty", "empty")]
    right.set_xlim(-0.5, 1.5)
    right.set_xticks([0, 1])
    right.set_xticklabels([T(label, n=int((slot.slot_by_eye == state).sum())) for label, state in states], color=INK, fontsize=7.8)
    right.tick_params(axis="x", length=0, pad=6)
    right.set_ylim(-0.012, 0.32)
    right.set_yticks([0, 0.1, 0.2, 0.3])
    right.yaxis.set_major_formatter(tick_format(1))
    right.set_ylabel(T("f_y_slot"))
    right.grid(axis="y", color=GRID, lw=0.6)
    right.set_axisbelow(True)
    right.set_title(T("f_right"), loc="left", fontweight="bold", pad=8)
    save(fig, "f_local_detectors")


def main() -> None:
    global LANG
    OUT.mkdir(parents=True, exist_ok=True)
    for LANG in ("en", "tr"):
        for chart in (chart_a, chart_b, chart_c, chart_d, chart_e, chart_f):
            chart()
    files = sorted(OUT.iterdir())
    print(f"{len(files)} files in {OUT} ({sum(f.stat().st_size for f in files) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
