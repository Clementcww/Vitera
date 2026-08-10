"""Sweep tests — bucket 13.

These test the sweep rules from the design brief, not the runner's plumbing. Each one
names the rule it protects, because every one of them was a real failure at
some point in this session:

    rule 2  idempotent on (episode_id, sweep_date)
    rule 3  the diff is the output — an unchanged finding does not re-queue
    rule 4  a dismissal is keyed on evidence and never expires on a timer
    rule 5  per-episode failure isolation; a partial sweep says so
    rule 11 the sweep schedules, diffs and orders. No inference.

The two-key split (`finding_key` vs `suppression_key`) has the most tests of
anything here, because collapsing them is the mistake that looks correct and
quietly floods the queue.
"""

from __future__ import annotations

from datetime import date

import pytest

from vitera.contracts import (
    DefectClass,
    Flag,
    FlagSource,
    GroupResult,
    PipelineResult,
    Remedy,
    RouterDecision,
    Span,
    Trace,
    Verdict,
)
from vitera.sweep.diff import churn_rate, diff_results
from vitera.sweep.queue import order_key, order_queue

DAY_A = date(2026, 3, 1)
DAY_B = date(2026, 3, 2)


def _flag(
    cls: DefectClass = DefectClass.D4,
    subject: str = "E11.9",
    text: str = "GDS 240 mg/dL",
    score: float = 0.8,
    remedy: Remedy = Remedy.QUERY,
) -> Flag:
    span = Span("cppt_hari_2", 0, len(text), text)
    return Flag(cls, remedy, span, score, FlagSource.CROSS_ENCODER, subject=subject)


def _result(flags: tuple[Flag, ...], day: int = 3) -> PipelineResult:
    return PipelineResult(
        episode_id="EP0001",
        day=day,
        decision=RouterDecision(Verdict.FLAGGED, flags, "default", "test"),
        grouping=GroupResult("A-4-15-I", 1, 10_000_000, None),
        validation_failures=(),
        trace=Trace("EP0001", day, (), 0, None, False, 0.01),
    )


def _diff(current, previous, **kw):
    return diff_results(
        episode_id="EP0001",
        sweep_date=DAY_B,
        current=current,
        previous=previous,
        previous_sweep_date=DAY_A if previous else None,
        escalate_at=0.75,
        **kw,
    )


# --- rule 3: the diff is the output ----------------------------------------


def test_first_sweep_reports_everything_as_new() -> None:
    d = _diff(_result((_flag(),)), None)
    assert len(d.new) == 1
    assert d.previous_successful_sweep is None


def test_unchanged_finding_does_not_re_enter_the_queue() -> None:
    """Sweep rule 3. Re-presenting yesterday's findings every morning is how a
    monitoring product gets switched off in week two."""
    f = _flag()
    d = _diff(_result((f,)), _result((f,)))
    assert d.is_empty
    assert not d.actionable


def test_moved_citation_is_not_a_new_finding() -> None:
    """The bug that put churn at 0.79.

    A comorbidity visible in the record gets re-cited from a newer CPPT every
    night as the notes accumulate. Keyed on evidence, the identical finding is
    reported as resolved AND new every morning.
    """
    yesterday = _flag(text="GDS 240 mg/dL")
    today = _flag(text="GDS 251 mg/dL — insulin dinaikkan")
    assert yesterday.span.evidence_hash != today.span.evidence_hash
    assert yesterday.finding_key == today.finding_key

    d = _diff(_result((today,)), _result((yesterday,)))
    assert d.is_empty, "same finding, fresher quotation — not queue work"
    assert d.citation_moved == 1


def test_different_subject_is_a_different_finding() -> None:
    """Before `subject` existed these collided, and staging or dismissing one
    silently applied to the other."""
    a = _flag(subject="E11.9")
    b = _flag(subject="N18.3")
    assert a.finding_key != b.finding_key
    d = _diff(_result((a, b)), _result((a,)))
    assert [f.subject for f in d.new] == ["N18.3"]


def test_escalation_is_a_band_crossing_not_a_score_wobble() -> None:
    below = _flag(score=0.60)
    drifted = _flag(score=0.70)
    crossed = _flag(score=0.80)

    assert _diff(_result((drifted,)), _result((below,))).is_empty
    assert len(_diff(_result((crossed,)), _result((below,))).escalated) == 1


# --- the documented / churned split ----------------------------------------


def test_finding_closed_by_new_documentation_is_not_churn() -> None:
    """The product working must not read as the product failing.

    A finding that disappears because the DPJP wrote the comorbidity into the
    record is the outcome Vitera exists to produce. Counting it as instability
    would make the metric worse every time the system succeeded.
    """
    f = _flag(subject="E11.9")
    d = _diff(_result(()), _result((f,)), newly_mentioned={"E11.9"})
    assert [x.subject for x in d.documented] == ["E11.9"]
    assert not d.resolved
    assert churn_rate([d]) == 0.0


def test_unexplained_disappearance_counts_as_churn() -> None:
    f = _flag(subject="E11.9")
    gone = _diff(_result(()), _result((f,)), newly_mentioned=set())
    appeared = _diff(_result((f,)), None)
    assert [x.subject for x in gone.resolved] == ["E11.9"]
    assert churn_rate([appeared, gone]) == 1.0


def test_churn_is_zero_when_nothing_was_ever_flagged() -> None:
    assert churn_rate([]) == 0.0


# --- rule 4: dismissal follows the evidence --------------------------------


def test_dismissal_silences_the_same_evidence() -> None:
    f = _flag()
    d = _diff(_result((f,)), None, dismissed={f.suppression_key})
    assert d.is_empty


def test_dismissal_does_not_survive_new_evidence() -> None:
    """Rule 4, the half people forget. "Not this, on this evidence" must not
    silence the same problem once the record says something different."""
    yesterday = _flag(text="GDS 240 mg/dL")
    today = _flag(text="HbA1c 9.8% — insulin basal dimulai")
    d = _diff(_result((today,)), None, dismissed={yesterday.suppression_key})
    assert len(d.new) == 1


# --- rule 2: idempotence ---------------------------------------------------


def test_rerunning_a_sweep_key_is_byte_identical() -> None:
    """What makes retry safe and the demo replayable."""
    import json

    from vitera.api.export import _flag_json
    from vitera.sweep.diff import diff_json

    flags = (_flag(subject="N18.3"), _flag(subject="E11.9", score=0.9))
    a = _diff(_result(flags), None)
    b = _diff(_result(flags), None)
    assert json.dumps(diff_json(a, _flag_json)) == json.dumps(diff_json(b, _flag_json))


def test_diff_order_is_deterministic_regardless_of_input_order() -> None:
    f1 = _flag(subject="A", score=0.9)
    f2 = _flag(subject="B", score=0.5)
    f3 = _flag(subject="C", score=0.7, remedy=Remedy.RECODE)
    forward = _diff(_result((f1, f2, f3)), None)
    reverse = _diff(_result((f3, f2, f1)), None)
    assert [f.subject for f in forward.new] == [f.subject for f in reverse.new]


# --- queue ordering --------------------------------------------------------


def test_query_outranks_a_larger_recode() -> None:
    """The ordering encodes one clinical fact: a repair window is a different
    length depending on who has to act. Sorting by money alone would bury the
    only findings that expire."""
    query = _diff(
        _result((_flag(remedy=Remedy.QUERY),)), None, recoverable_idr=2_000_000
    )
    recode = _diff(
        _result((_flag(remedy=Remedy.RECODE, subject="X"),)),
        None,
        recoverable_idr=5_000_000,
    )
    assert order_queue([recode, query])[0] is query


def test_a_shut_ward_window_stops_outranking_an_open_one() -> None:
    """A QUERY on a discharged patient cannot be traded against one that can
    still be answered, so it drops to the OBTAIN horizon rather than sitting at
    the top of the queue forever."""
    on_ward = _diff(
        _result((_flag(remedy=Remedy.QUERY),)), None, recoverable_idr=1_000_000
    )
    discharged = diff_results(
        episode_id="EP0002",
        sweep_date=DAY_B,
        current=_result((_flag(remedy=Remedy.QUERY),)),
        previous=None,
        previous_sweep_date=None,
        escalate_at=0.75,
        recoverable_idr=9_000_000,
        still_admitted=False,
    )
    assert order_key(on_ward)[0] < order_key(discharged)[0]


def test_empty_diffs_never_reach_the_queue() -> None:
    f = _flag()
    unchanged = _diff(_result((f,)), _result((f,)))
    assert order_queue([unchanged]) == []


# --- rule 11: the sweep contains no transport ------------------------------


@pytest.mark.parametrize(
    "module", ["vitera.sweep.runner", "vitera.sweep.diff", "vitera.sweep.queue"]
)
def test_sweep_imports_nothing_that_can_send(module: str) -> None:
    """Sweep rule 1: nothing leaves the system, and unattended execution is
    exactly when that matters most. The enforcement is the ABSENCE of a
    transport, which is checkable rather than merely stated."""
    import ast
    import importlib
    import pathlib

    src = importlib.import_module(module).__file__
    assert src is not None
    tree = ast.parse(pathlib.Path(src).read_text(encoding="utf-8"))

    banned = {
        "smtplib",
        "email",
        "requests",
        "httpx",
        "urllib",
        "http.client",
        "socket",
        "ftplib",
        "subprocess",
        "webbrowser",
    }
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            seen.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            seen.add(node.module.split(".")[0])
    assert not (seen & banned), f"{module} imports a transport: {seen & banned}"


def test_queue_weight_is_zero_with_nothing_to_do() -> None:
    f = _flag()
    unchanged = _diff(_result((f,)), _result((f,)), recoverable_idr=5_000_000)
    assert unchanged.queue_weight() == 0.0
