"""The decision router and the span filter.

Architectural rule 5: the router is deterministic and readable in one screen.
Models score; this decides. Every threshold comes from
`config/thresholds.yaml` — none appears in code, and none is ever put in a
prompt.

Architectural rule 6: `filter_spans` drops any flag whose cited span does not
appear verbatim in the record. It is a **filter, not a prompt instruction** —
a model cannot talk its way past it, and a poisoned note cannot manufacture a
citation.

Architectural rule 10: `Verdict.ABSTAIN` is reachable and is returned whenever
the evidence sits between the thresholds.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vitera.contracts import (
    Episode,
    Flag,
    GroupResult,
    RouterDecision,
    Verdict,
)


def filter_spans(
    flags: Sequence[Flag], episode: Episode
) -> tuple[tuple[Flag, ...], int]:
    """Keep only flags whose span is verbatim in the record.

    Returns (kept, dropped_count). A dropped flag is not an error to report to
    the user — it is a fabricated citation that never reaches them.
    """
    by_doc = {d.doc_id: d.text for d in episode.documents}
    kept = []
    for f in flags:
        text = by_doc.get(f.span.doc_id)
        if text is None:
            continue
        if text[f.span.start : f.span.end] != f.span.text:
            continue
        kept.append(f)
    return tuple(kept), len(flags) - len(kept)


class Router:
    """Deterministic. The whole decision is the ten lines of `decide`."""

    def __init__(
        self,
        thresholds: Mapping[str, Any] | None = None,
        profile: str = "default",
    ) -> None:
        from vitera import config

        t = thresholds or config.thresholds()
        self.profile = profile
        block = t["router"][profile]
        self.flag_at = float(block["flag_at"])
        self.abstain_below = float(block["abstain_below"])
        self.max_flags = int(block["max_flags_per_episode"])
        self.escalate_at = float(t["severity"]["escalate_at"])

    def decide(
        self,
        flags: Sequence[Flag],
        grouping: GroupResult,
        *,
        degraded: bool = False,
    ) -> RouterDecision:
        kept = [f for f in flags if f.score >= self.flag_at]
        borderline = [f for f in flags if self.abstain_below <= f.score < self.flag_at]

        if kept:
            verdict = Verdict.FLAGGED
            reason = f"{len(kept)} temuan di atas ambang {self.flag_at}"
        elif borderline:
            verdict = Verdict.ABSTAIN
            reason = (
                f"{len(borderline)} temuan di zona abu-abu "
                f"[{self.abstain_below}, {self.flag_at}), perlu penilaian koder"
            )
        elif not grouping.is_groupable:
            verdict = Verdict.ABSTAIN
            reason = f"tidak dapat dikelompokkan: {grouping.ungroupable_reason}"
        else:
            verdict = Verdict.CLEAN
            reason = "tidak ada temuan di atas ambang"

        if degraded:
            reason += " (mode advisory: lapisan model tidak aktif)"

        ordered = sorted(kept, key=lambda f: (f.remedy.decay_rank, -f.score))[
            : self.max_flags
        ]

        return RouterDecision(
            verdict=verdict,
            flags=tuple(ordered),
            threshold_set=self.profile,
            reason=reason,
        )

    def is_escalated(self, flag: Flag) -> bool:
        """Used by the sweep diff to distinguish `escalated` from `new`."""
        return flag.score >= self.escalate_at
