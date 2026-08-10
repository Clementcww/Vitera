"""Cohort selection and queue ordering. Scheduling only — sweep rule 11.

Two jobs, both deliberately dumb:

**Who gets run tonight.** Read from `config/sweep.yaml`, never from code. The
filter is BPJS inpatient episodes currently admitted with `los_so_far >= 2`,
because day 0–1 carries too little signal to be worth a run and flagging on
arrival trains the koder to ignore the queue.

**What order the koder sees them in.** By remedy decay first, then by expected
recoverable value, then by day of stay. That ordering encodes one clinical
fact and nothing else: **a repair window is a different length depending on who
has to act.**

    Query   the DPJP has to write something while the patient is on the ward.
            Shuts at discharge. Decays fastest, so it sorts first.
    Obtain  a document has to be found. Survives discharge.
    Recode  the koder fixes a code. Survives until submission.

Which is why value alone is the wrong sort. A Rp 5 juta recode will still be
sitting there next week; a Rp 2 juta query on a patient going home tomorrow
will not. Sorting by money would put the recoverable-but-not-urgent work at the
top every single morning and quietly let the urgent work expire underneath it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vitera.contracts import Episode, SweepDiff

__all__ = ["cohort_filter", "order_key", "order_queue", "CohortSpec"]


class CohortSpec:
    """`config/sweep.yaml`'s cohort block, as read. Nothing is defaulted in
    code: a missing key is a config error, not a silent fallback to a value
    nobody wrote down."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        c = cfg["cohort"]
        self.payer = str(c["payer"])
        self.setting = str(c["setting"])
        self.status = str(c["status"])
        self.min_los_so_far = int(c["min_los_so_far"])
        self.max_episodes_per_night = int(c["max_episodes_per_night"])

    def __repr__(self) -> str:  # pragma: no cover - diagnostics
        return (
            f"CohortSpec({self.payer}/{self.setting}/{self.status}, "
            f"los>={self.min_los_so_far}, cap={self.max_episodes_per_night})"
        )


def cohort_filter(
    episodes: Sequence[tuple[Episode, Any]], spec: CohortSpec, *, day: int | None = None
) -> list[tuple[Episode, Any]]:
    """Select tonight's cohort.

    `day` is the day of stay the sweep is running for; when it is None each
    episode is taken at its own latest day. The length-of-stay floor is checked
    against the day being run, not against the episode's eventual total —
    otherwise a 9-day episode would qualify on its first night, which is
    precisely the "flagging on arrival" the floor exists to prevent.

    The cap is applied last and, when it bites, the caller reports `partial`
    (sweep rule 7). It never silently truncates.
    """
    out = []
    for ep, claim in episodes:
        los = ep.los_so_far if day is None else day
        if los < spec.min_los_so_far:
            continue
        out.append((ep, claim))
    out.sort(key=lambda pair: pair[0].episode_id)
    return out[: spec.max_episodes_per_night]


def order_key(d: SweepDiff) -> tuple[int, float, int]:
    """`queue.order_by: [remedy_decay_rank, expected_value, day_of_stay]`.

    Returned as a sort key, so the ordering is one readable expression rather
    than a comparator spread across the runner. Negation is how "descending"
    is spelled here; day of stay ascends, so an episode admitted longer ago —
    with less time left before it discharges — breaks the tie upward.
    """
    if d.actionable:
        decay = min(f.remedy.decay_rank for f in d.actionable)
        if decay == 0 and not d.still_admitted:
            decay = 1  # the ward window already shut; stop pretending it has not
    else:
        decay = 9  # nothing to do — below everything that has something to do
    return (decay, -d.queue_weight(), -d.day_of_stay)


def order_queue(diffs: Sequence[SweepDiff]) -> list[SweepDiff]:
    """Order the night's diffs, dropping the ones with nothing in them.

    Sweep rule 3 again, at the last possible moment: an episode whose findings
    are unchanged since yesterday is not in tomorrow's queue at all.
    """
    return sorted((d for d in diffs if not d.is_empty), key=order_key)
