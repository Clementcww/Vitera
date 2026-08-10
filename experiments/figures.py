"""`make figures` — every paper figure, from committed results JSON.

One rule governs this file: **it reads, it does not measure.** Each figure is a
rendering of a number that already exists in `results/`, produced by the
command named in the README reproduction table. Nothing here runs a model,
resamples anything, or computes a statistic that is not already on disk.

That is not tidiness. A figure that computes its own number is a second
implementation of that number, and the two drift — the paper says one thing,
the artifact says another, and the discrepancy is found by a reviewer rather
than by us. If a figure below has no input file, it is skipped and reported as
skipped; it never falls back to a plausible-looking default.

    F2   calibration + reliability      results/cross_encoder.json
    F3   detection rate by day of stay  results/detection_curve.json
    F4   lead time by defect class      results/detection_curve.json
    F5   sweep: queue, churn, ceiling   results/sweep/metrics.json
    F6   three arms, per class + CIs    results/three_arms.json
    F7   clean-claim FPR by share       results/detection_curve.json

Colour follows the same rule the workbench does: hues carry entity identity,
never rank or size, and the three arm colours are the validated palette from
`src/vitera/ui/src/tokens.css` so a figure in the paper and a panel on the
screen cannot disagree about what blue means.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # no display on CI, and none needed
import matplotlib.pyplot as plt  # noqa: E402

# The validated palette, copied from the workbench tokens. Checked there:
# lightness band, chroma floor, CVD separation, normal-vision separation and
# contrast all pass against a light surface.
QUERY = "#b4611c"
OBTAIN = "#1a6fae"
RECODE = "#3d7a2e"
INK = "#141413"
MUTED = "#6d7c80"
LINE = "#d8dfe0"

ARM_COLOUR = {"A": MUTED, "B": OBTAIN, "C": QUERY}

plt.rcParams.update(
    {
        "figure.dpi": 160,
        "savefig.dpi": 160,
        "font.size": 9,
        "axes.edgecolor": LINE,
        "axes.labelcolor": INK,
        "axes.titlesize": 10,
        "axes.titleweight": "600",
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.color": LINE,
        "grid.linewidth": 0.6,
    }
)


def _load(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _save(fig: Any, out: Path, name: str, made: list[str]) -> None:
    path = out / f"{name}.png"
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    made.append(str(path))


# ---------------------------------------------------------------------------


def f2_calibration(res: Any, out: Path, made: list[str]) -> None:
    """Reliability diagram. A model whose 0.8 does not mean 0.8 cannot have a
    threshold set from a false-positive budget, which is how ours is set."""
    ce = res["arms"]["cross_encoder"]
    bins = ce.get("reliability") or []
    if not bins:
        return
    fig, ax = plt.subplots(figsize=(4.2, 3.4))
    x = [b["mean_predicted"] for b in bins]
    y = [b["observed_rate"] for b in bins]
    n = [b["n"] for b in bins]
    ax.plot([0, 1], [0, 1], color=LINE, lw=1, ls="--", zorder=1)
    ax.scatter(x, y, s=[max(12, min(160, k / 4)) for k in n], color=QUERY, zorder=3)
    ax.plot(x, y, color=QUERY, lw=1.6, zorder=2)
    ax.set_xlabel("mean predicted probability")
    ax.set_ylabel("observed rate")
    ax.set_title(
        f"F2 · Calibration — ECE {ce['overall']['ece']}, Brier {ce['overall']['brier']}"
    )
    ax.grid(True, lw=0.5)
    _save(fig, out, "f2_calibration", made)


def f3_detection_by_day(res: Any, out: Path, made: list[str]) -> None:
    """The curve the concurrent claim rests on.

    Plotted against SHARE of stay rather than absolute day, because episodes
    have different lengths and a raw per-day count falls as the cohort
    discharges — a denominator artefact that reads as declining detection.
    """
    curve = res.get("detection_rate_by_share_of_stay") or []
    if not curve:
        return
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    x = [p["share_of_stay"] * 100 for p in curve]
    y = [p["detection_rate"] * 100 for p in curve]
    ax.fill_between(x, y, color=QUERY, alpha=0.14)
    ax.plot(x, y, color=QUERY, lw=2)
    ax.set_ylim(0, 100)
    ax.set_xlabel("share of stay elapsed (%)")
    ax.set_ylabel("defect classes detected (%)")
    ax.set_title(
        f"F3 · Cumulative detection — {res['detection_rate'] * 100:.1f}% by discharge, "
        f"median {res['lead_time_days'].get('median')} days early"
    )
    ax.grid(True, lw=0.5, axis="y")
    _save(fig, out, "f3_detection_by_day", made)


def f4_lead_time(res: Any, out: Path, made: list[str]) -> None:
    """Lead time per defect class, as p25–p75 with the median marked.

    Boxes, not bars: the summary in `results/` carries quartiles, and drawing a
    mean as a bar would throw away the spread that decides whether a repair
    window is usable. D1, D6 and D8 sit at zero by construction — the rules see
    them the moment the claim file exists — and that is worth showing rather
    than hiding, because it is where the neural arm adds nothing.
    """
    by_class = res.get("lead_time_by_class") or {}
    if not by_class:
        return
    names = sorted(by_class)
    fig, ax = plt.subplots(figsize=(5.0, 3.2))
    for i, c in enumerate(names):
        s = by_class[c]
        if not s.get("n"):
            continue
        lo, hi, med = s["p25"], s["p75"], s["median"]
        ax.plot([lo, hi], [i, i], color=OBTAIN, lw=6, alpha=0.35, solid_capstyle="butt")
        ax.plot([med], [i], marker="|", color=OBTAIN, ms=14, mew=2)
        ax.annotate(
            f"n={s['n']}",
            (hi, i),
            xytext=(6, -3),
            textcoords="offset points",
            color=MUTED,
            fontsize=7.5,
        )
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.set_xlabel("days before discharge (p25 – p75, median marked)")
    ax.set_title("F4 · Detection lead time by defect class")
    ax.grid(True, lw=0.5, axis="x")
    _save(fig, out, "f4_lead_time", made)


def f5_sweep(metrics: Any, out: Path, made: list[str]) -> None:
    """Alert load and churn against their ceilings.

    The ceilings are drawn as lines rather than mentioned in a caption, because
    a breach is a defect and a defect that needs a caption to notice is one
    nobody notices.
    """
    m = metrics["metrics"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.4, 2.9))

    ax1.bar(["terukur"], [m["alerts_per_episode_per_day"]], color=OBTAIN, width=0.45)
    ax1.axhline(m["alerts_ceiling"], color=QUERY, lw=1.4, ls="--")
    ax1.annotate(
        f"batas {m['alerts_ceiling']}",
        (0, m["alerts_ceiling"]),
        xytext=(0, 5),
        textcoords="offset points",
        ha="center",
        color=QUERY,
        fontsize=8,
    )
    ax1.set_ylim(0, max(m["alerts_ceiling"] * 1.3, 1))
    ax1.set_title("alerts / episode / day")

    breach = m["flag_churn_rate"] > m["churn_ceiling"]
    ax2.bar(
        ["terukur"],
        [m["flag_churn_rate"]],
        color=QUERY if breach else RECODE,
        width=0.45,
    )
    ax2.axhline(m["churn_ceiling"], color=QUERY, lw=1.4, ls="--")
    ax2.annotate(
        f"batas {m['churn_ceiling']}",
        (0, m["churn_ceiling"]),
        xytext=(0, 5),
        textcoords="offset points",
        ha="center",
        color=QUERY,
        fontsize=8,
    )
    ax2.set_ylim(0, max(m["flag_churn_rate"] * 1.3, m["churn_ceiling"] * 2))
    ax2.set_title("flag churn rate" + ("  — BREACH" if breach else ""))

    for ax in (ax1, ax2):
        ax.grid(True, lw=0.5, axis="y")
    fig.suptitle(
        f"F5 · Sweep over {m['nights']} nights, {m['episode_days_run']} pipeline runs, "
        f"{m['sweep_wall_clock_seconds']}s",
        fontsize=9.5,
    )
    _save(fig, out, "f5_sweep", made)


def f6_three_arms(res: Any, out: Path, made: list[str]) -> None:
    """The headline. Per-class recall by arm, at a MATCHED false-positive budget.

    The budget match is in the subtitle rather than the caption because it is
    the load-bearing part: without it arm B reaches arm C's recall by flagging
    half of all clean claims, which is not a baseline.
    """
    classes = [f"D{i}" for i in range(1, 9)]
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(7.6, 3.2), gridspec_kw={"width_ratios": [2.6, 1]}
    )

    width = 0.26
    for k, arm in enumerate(("A", "B", "C")):
        pc = res["arms"][arm]["per_class"]
        vals = [(pc[c]["recall"] or 0) for c in classes]
        ax1.bar(
            [i + (k - 1) * width for i in range(len(classes))],
            vals,
            width=width,
            color=ARM_COLOUR[arm],
            label=f"arm {arm} — {res['arms'][arm]['label']}",
        )
    ax1.set_xticks(range(len(classes)))
    ax1.set_xticklabels(classes)
    ax1.set_ylim(0, 1.05)
    ax1.set_ylabel("recall")
    # Below the axes, not inside them: D1, D6 and D8 are at 1.0 for every arm,
    # so an in-plot legend sits on top of the bars it is labelling.
    ax1.legend(
        fontsize=7.5,
        frameon=False,
        ncol=3,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
    )
    ax1.grid(True, lw=0.5, axis="y")
    ax1.set_title("recall by defect class")

    arms = ("A", "B", "C")
    fprs = [res["arms"][a]["clean_claim_false_positive_rate"] or 0 for a in arms]
    ax2.bar(list(arms), fprs, color=[ARM_COLOUR[a] for a in arms], width=0.55)
    for i, v in enumerate(fprs):
        ax2.annotate(
            f"{v * 100:.1f}%",
            (i, v),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            color=INK,
            fontsize=8,
        )
    ax2.set_ylim(0, max(fprs) * 1.4 if max(fprs) else 1)
    ax2.grid(True, lw=0.5, axis="y")
    ax2.set_title("clean-claim FPR")

    b = res.get("budget_match", {})
    fig.suptitle(
        f"F6 · Three arms, n={res['n_episodes']} held-out episodes — "
        f"matched budget: arm B floor {b.get('chosen_emit_floor')} "
        f"({b.get('achieved_clean_fpr_on_train')} vs "
        f"{b.get('arm_c_clean_fpr_on_train')} clean FPR on train)",
        fontsize=8.5,
    )
    _save(fig, out, "f6_three_arms", made)


def f7_clean_fpr(res: Any, out: Path, made: list[str]) -> None:
    """The counterweight to F3, deliberately on F3's axis.

    Share of stay, not day of stay. The per-day series in `results/` has a
    cohort that shrinks and changes composition along the axis — day 13 holds
    only the episodes that stayed thirteen days — so its slope mixes a change
    of behaviour with a change of population. Read together with F3 the two
    curves answer the only question that matters for adoption: as the record
    fills in, detection rises and false alarms fall.

    Plotted from 0 rather than from the data's own floor. A truncated y-axis on
    a rate is the standard way to make 37% look like 3%.
    """
    share = res.get("clean_fp_rate_by_share_of_stay") or []
    if not share:
        return
    x = [p["share_of_stay"] * 100 for p in share]
    y = [p["clean_fp_rate"] * 100 for p in share]
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    ax.fill_between(x, y, color=INK, alpha=0.10)
    ax.plot(x, y, color=INK, lw=2)
    ax.set_ylim(0, max(50, max(y) * 1.3))
    ax.set_xlabel("share of stay elapsed (%)")
    ax.set_ylabel("clean claims carrying ≥ 1 flag (%)")
    disc = res.get("clean_fp_rate_at_discharge")
    tail = (
        f"{disc * 100:.1f}% at discharge"
        if disc is not None
        else f"{y[-1]:.0f}% at the end"
    )
    ax.set_title(f"F7 · Clean-claim false positives — {y[0]:.0f}% on admission, {tail}")
    ax.grid(True, lw=0.5, axis="y")
    _save(fig, out, "f7_clean_fpr", made)


# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("results"))
    p.add_argument("--results", type=Path, default=Path("results"))
    a = p.parse_args()

    figures = a.out / "figures"
    figures.mkdir(parents=True, exist_ok=True)

    made: list[str] = []
    skipped: list[str] = []

    jobs = [
        ("F2 calibration", a.results / "cross_encoder.json", f2_calibration),
        (
            "F3 detection by day",
            a.results / "detection_curve.json",
            f3_detection_by_day,
        ),
        ("F4 lead time", a.results / "detection_curve.json", f4_lead_time),
        ("F5 sweep", a.results / "sweep" / "metrics.json", f5_sweep),
        ("F6 three arms", a.results / "three_arms.json", f6_three_arms),
        ("F7 clean FPR", a.results / "detection_curve.json", f7_clean_fpr),
    ]

    for label, src, fn in jobs:
        data = _load(src)
        if data is None:
            skipped.append(f"{label} — no {src}")
            continue
        before = len(made)
        fn(data, figures, made)
        if len(made) == before:
            skipped.append(f"{label} — {src} has no data for it")

    print(f"FIGURES → {figures}\n")
    for m in made:
        print(f"  wrote   {m}")
    for s in skipped:
        # Named, never silent. A figure missing from the paper because its
        # command has not been run is a different problem from a figure that
        # rendered wrong, and only one of them is visible without this line.
        print(f"  SKIPPED {s}")
    print(f"\n{len(made)} figures, {len(skipped)} skipped")


if __name__ == "__main__":
    main()
