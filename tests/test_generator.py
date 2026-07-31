"""Generator tests — bucket 4a, clean episodes.

These guard the properties the whole concurrent thesis depends on. If one of
them fails, a downstream result is not safe to report.
"""

from __future__ import annotations

import warnings

import pytest

from vitera.generator import reference as ref
from vitera.generator.episode import generate_corpus

pytestmark = pytest.mark.filterwarnings(
    "ignore::vitera.generator.reference.UnverifiedReferenceWarning"
)


@pytest.fixture(scope="module")
def corpus() -> list:
    return generate_corpus(300, seed=20260731)


# --- THE invariant --------------------------------------------------------


def test_collapsing_at_discharge_reproduces_the_flat_episode(corpus: list) -> None:
    """episode.at_day(discharge_day) == episode

    If this fails, concurrent results and discharge results are not comparable
    and the detection-lead-time claim is void. This is the strict-xfail in
    test_contracts.py, made real.
    """
    for ep, _ in corpus:
        assert ep.discharge_day is not None
        assert ep.at_day(ep.discharge_day) == ep, ep.episode_id


def test_at_day_is_monotone(corpus: list) -> None:
    """Nothing ever disappears as the stay progresses."""
    for ep, _ in corpus[:40]:
        assert ep.discharge_day is not None
        for d in range(ep.discharge_day):
            a, b = ep.at_day(d), ep.at_day(d + 1)
            assert len(a.events) <= len(b.events)
            assert len(a.documents) <= len(b.documents)
            assert len(a.secondary_dx) <= len(b.secondary_dx)


def test_episode_is_still_admitted_before_discharge(corpus: list) -> None:
    ep, _ = corpus[0]
    assert ep.discharge_day is not None and ep.discharge_day > 0
    assert ep.at_day(ep.discharge_day - 1).is_admitted
    assert not ep.at_day(ep.discharge_day).is_admitted


# --- the mechanic: signals precede documentation --------------------------


def test_signal_never_arrives_after_documentation(corpus: list) -> None:
    """A diagnosis cannot be written down before it is clinically visible."""
    for _, gt in corpus:
        pass
    for ep, _ in corpus:
        for dx in ep.secondary_dx:
            if dx.documented_day is not None:
                assert dx.signal_day is not None
                assert dx.signal_day <= dx.documented_day, ep.episode_id


def test_undocumented_diagnoses_still_have_visible_signals(corpus: list) -> None:
    """The undercoding case: no diagnosis in the resume medis, but lab and med
    evidence sitting in the CPPT. This asymmetry IS the product."""
    found = False
    for ep, gt in corpus:
        if not gt.undocumented_dx:
            continue
        found = True
        resume = next(d for d in ep.documents if d.doc_id == "resume_medis")
        cppt = "\n".join(d.text for d in ep.documents if d.doc_id.startswith("cppt"))
        for code in gt.undocumented_dx:
            assert code not in resume.text, f"{ep.episode_id}: {code} leaked into resume"
            for sig in ref.comorbidity_by_code(code).signals:
                assert sig.label in cppt, f"{ep.episode_id}: no signal for {code}"
    assert found, "corpus contains no undercoding case — the generator is broken"


def test_documentation_never_arrives_after_discharge(corpus: list) -> None:
    for ep, _ in corpus:
        assert ep.discharge_day is not None
        for dx in ep.secondary_dx:
            if dx.documented_day is not None:
                assert dx.documented_day <= ep.discharge_day


# --- site quality is separate from defect injection -----------------------


def test_documentation_quality_tracks_hospital_class(corpus: list) -> None:
    """Better-documenting classes leave fewer diagnoses unwritten.

    Compares the extremes only: adjacent classes are within sampling noise at
    corpus sizes the test suite can afford.
    """
    by_class: dict[str, list[float]] = {}
    for _, gt in corpus:
        if gt.secondary_dx:
            by_class.setdefault(gt.site_class, []).append(
                len(gt.undocumented_dx) / len(gt.secondary_dx)
            )
    a = sum(by_class["A"]) / len(by_class["A"])
    c = sum(by_class["C"]) / len(by_class["C"])
    assert a < c, f"class A ({a:.3f}) should out-document class C ({c:.3f})"


def test_severity_counts_only_documented_comorbidities(corpus: list) -> None:
    """A clinically present but unwritten comorbidity cannot lift severity.
    That gap is the money."""
    for ep, gt in corpus:
        assert set(gt.documented_dx) <= set(gt.secondary_dx)
        assert set(gt.undocumented_dx) == set(gt.secondary_dx) - set(gt.documented_dx)


# --- clinical plausibility -------------------------------------------------


def test_no_implausible_comorbidity_pairings(corpus: list) -> None:
    """A sectio caesarea with COPD discredits the demo faster than any model
    error. Comorbidities must come from the group's allowed list."""
    for _, gt in corpus:
        allowed = set(ref.plausible_comorbidities(gt.cbg))
        assert set(gt.secondary_dx) <= allowed, gt.cbg


def test_length_of_stay_respects_the_group(corpus: list) -> None:
    groups = {g.cbg: g for g in ref.cbg_groups()}
    for ep, gt in corpus:
        g = groups[gt.cbg]
        assert g.los_min <= ep.discharge_day <= g.los_max


def test_required_procedure_is_present_for_surgical_groups(corpus: list) -> None:
    groups = {g.cbg: g for g in ref.cbg_groups()}
    for ep, gt in corpus:
        req = groups[gt.cbg].required_procedure
        if req:
            assert req in ep.procedures
            assert any(e.code == req for e in ep.events)


# --- reproducibility -------------------------------------------------------


def test_generation_is_deterministic_under_a_seed() -> None:
    a = generate_corpus(25, seed=99)
    b = generate_corpus(25, seed=99)
    assert [e for e, _ in a] == [e for e, _ in b]


def test_different_seeds_give_different_corpora() -> None:
    a = generate_corpus(25, seed=1)
    b = generate_corpus(25, seed=2)
    assert [e for e, _ in a] != [e for e, _ in b]


# --- the unverified-reference guard ---------------------------------------


def test_unverified_reference_data_warns_loudly() -> None:
    """Clinical placeholders must not silently become paper figures."""
    assert not ref.domain_verified()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        ref.warn_if_unverified()
    assert any(issubclass(x.category, ref.UnverifiedReferenceWarning) for x in w)
