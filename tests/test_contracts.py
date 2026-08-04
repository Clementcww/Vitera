"""Contract tests.

These test the architectural rules, not the implementations. Several are
``xfail`` until the bucket that implements them lands — an xfail that starts
passing is the signal the bucket is done.
"""

from __future__ import annotations

from datetime import date

import pytest

from vitera.contracts import (
    DefectClass,
    Episode,
    Flag,
    FlagSource,
    GroupResult,
    LoopBudget,
    Remedy,
    SecondaryDiagnosis,
    Span,
    Verdict,
)

# --- rule 6: every flag carries a verbatim span ----------------------------


def test_flag_cannot_be_built_without_a_span() -> None:
    with pytest.raises(TypeError):
        Flag(  # type: ignore[call-arg]
            defect_class=DefectClass.D3,
            remedy=Remedy.RECODE,
            score=0.9,
            source=FlagSource.CROSS_ENCODER,
        )


def test_span_rejects_empty_evidence() -> None:
    with pytest.raises(ValueError):
        Span(doc_id="resume_medis", start=10, end=10, text="")


def test_evidence_hash_is_stable_and_text_sensitive() -> None:
    a = Span("resume_medis", 0, 20, "pasien mendapat insulin")
    b = Span("resume_medis", 400, 420, "pasien mendapat insulin")
    c = Span("resume_medis", 0, 20, "pasien mendapat metformin")
    # Sweep rule 4: suppression follows the evidence, not its position.
    assert a.evidence_hash == b.evidence_hash
    assert a.evidence_hash != c.evidence_hash


def test_suppression_key_combines_defect_and_evidence() -> None:
    span = Span("resume_medis", 0, 5, "DM t2")
    f1 = Flag(DefectClass.D4, Remedy.QUERY, span, 0.8, FlagSource.CROSS_ENCODER)
    f2 = Flag(DefectClass.D3, Remedy.RECODE, span, 0.8, FlagSource.CROSS_ENCODER)
    assert f1.suppression_key != f2.suppression_key


# --- rule 7: the grouper is authoritative, and never estimates --------------


def test_ungroupable_episode_cannot_carry_a_tariff() -> None:
    with pytest.raises(ValueError):
        GroupResult(
            cbg_code=None,
            severity=None,
            tariff_idr=4_500_000,
            ungroupable_reason="primary diagnosis missing",
        )


def test_ungroupable_without_tariff_is_fine() -> None:
    r = GroupResult(None, None, None, ungroupable_reason="primary diagnosis missing")
    assert not r.is_groupable


# --- rule 9: bounded loops --------------------------------------------------


def test_budget_reports_which_limit_was_breached() -> None:
    b = LoopBudget()
    assert b.exceeded(calls=3, reflections=0, elapsed=1.0) is None
    assert "max_tool_calls" in (b.exceeded(9, 0, 1.0) or "")
    assert "wall_clock" in (b.exceeded(1, 0, 21.0) or "")


# --- rule 10: abstention is reachable --------------------------------------


def test_abstain_is_a_verdict() -> None:
    assert Verdict.ABSTAIN in set(Verdict)


# --- score bounds -----------------------------------------------------------


@pytest.mark.parametrize("score", [-0.1, 1.1])
def test_flag_score_must_be_calibrated_range(score: float) -> None:
    with pytest.raises(ValueError):
        Flag(
            DefectClass.D2,
            Remedy.RECODE,
            Span("resume_medis", 0, 3, "DM2"),
            score,
            FlagSource.CROSS_ENCODER,
        )


# --- the temporal structure -------------------------------------------------


def test_undocumented_diagnosis_is_the_undercoding_defect() -> None:
    dx = SecondaryDiagnosis(icd10="E11.9", signal_day=3, documented_day=None)
    assert dx.is_undocumented
    assert dx.visible_window is None


def test_visible_window_is_the_value_vitera_creates() -> None:
    dx = SecondaryDiagnosis(icd10="E11.9", signal_day=3, documented_day=5)
    assert dx.visible_window == 2


# --- remedy decay ordering --------------------------------------------------


def test_query_decays_fastest() -> None:
    """A QUERY needs the DPJP while the patient is still on the ward; a RECODE
    survives until submission. Queue ordering depends on this."""
    order = sorted(Remedy, key=lambda r: r.decay_rank)
    assert order == [Remedy.QUERY, Remedy.OBTAIN, Remedy.RECODE]


# --- rules reach 3 of 8, and that is a measured claim ----------------------


def test_rules_reachable_taxonomy_matches_the_paper() -> None:
    fully = [d for d in DefectClass if d.rules_reachable is True]
    partly = [d for d in DefectClass if d.rules_reachable is None]
    assert {d.name for d in fully} == {"D1", "D6", "D8"}
    assert {d.name for d in partly} == {"D5"}


# --- the invariant the whole concurrent thesis rests on --------------------


def test_at_day_rejects_negative_days() -> None:
    ep = Episode(
        episode_id="EP1",
        site_id="RS001",
        admission_date=date(2026, 1, 1),
        primary_dx="A01.0",
        secondary_dx=(),
        procedures=(),
        events=(),
        documents=(),
        discharge_day=4,
    )
    with pytest.raises(ValueError):
        ep.at_day(-1)


def test_at_day_keeps_visible_but_undocumented_diagnoses() -> None:
    """The undercoding case must survive the temporal collapse.

    signal_day 2, never documented: on day 3 it is clinically present and
    missing from the notes. Filtering it out would erase the phenomenon the
    product exists to detect.
    """
    dx = SecondaryDiagnosis(icd10="E11.9", signal_day=2, documented_day=None)
    later = SecondaryDiagnosis(icd10="I10", signal_day=5, documented_day=6)
    ep = Episode(
        episode_id="EP1",
        site_id="RS001",
        admission_date=date(2026, 1, 1),
        primary_dx="A01.0",
        secondary_dx=(dx, later),
        procedures=(),
        events=(),
        documents=(),
        discharge_day=7,
    )
    at3 = ep.at_day(3)
    assert at3.secondary_dx == (dx,)  # visible
    assert at3.documented_dx_at(3) == ()  # but unwritten
    assert ep.documented_dx_at(7) == ("I10",)
    # The full-stay collapse is lossless.
    assert ep.at_day(7) == ep
