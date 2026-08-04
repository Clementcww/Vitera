"""Deterministic layer tests — bucket 5.

Two things these protect: that the grouper never invents money, and that arm A
is a fair baseline rather than a strawman.
"""

from __future__ import annotations

import pytest

from vitera.contracts import DefectClass
from vitera.generator import reference as ref
from vitera.generator.defects import clean_claim, inject
from vitera.generator.episode import generate_corpus
from vitera.grouper.grouper import Grouper
from vitera.rules.engine import RuleContext, run, validate

pytestmark = pytest.mark.filterwarnings(
    "ignore::vitera.generator.reference.UnverifiedReferenceWarning"
)


@pytest.fixture(scope="module")
def corpus() -> list:
    return generate_corpus(200, seed=20260731)


# --- grouper: architectural rule 7 ----------------------------------------


def test_grouper_is_deterministic(corpus: list) -> None:
    g1, g2 = Grouper(), Grouper()
    for ep, gt in corpus:
        a = g1.group_codes(gt.primary_dx, gt.documented_dx, gt.procedures)
        b = g2.group_codes(gt.primary_dx, gt.documented_dx, gt.procedures)
        assert a == b


def test_grouper_reproduces_generator_severity(corpus: list) -> None:
    """Exact match against ground truth. The grouper is authoritative, so a
    disagreement here means one of the two is wrong about the tariff."""
    g = Grouper()
    for ep, gt in corpus:
        assert g.severity(gt.documented_dx) == gt.severity, ep.episode_id


def test_unknown_primary_diagnosis_is_ungroupable_and_carries_no_tariff() -> None:
    r = Grouper().group_codes("Z99.9", (), ())
    assert not r.is_groupable
    assert r.tariff_idr is None


def test_missing_required_procedure_is_ungroupable() -> None:
    surgical = next(g for g in ref.cbg_groups() if g.required_procedure)
    r = Grouper().group_codes(surgical.primary, (), ())
    assert not r.is_groupable
    assert "prosedur" in (r.ungroupable_reason or "")


def test_undocumented_comorbidity_cannot_lift_severity(corpus: list) -> None:
    """The financial core: clinically present but unwritten pays less."""
    g = Grouper()
    for ep, gt in corpus:
        if not gt.undocumented_dx:
            continue
        claimed = g.group_codes(gt.primary_dx, gt.documented_dx, gt.procedures)
        full = g.group_codes(gt.primary_dx, gt.secondary_dx, gt.procedures)
        if claimed.tariff_idr and full.tariff_idr:
            assert claimed.tariff_idr <= full.tariff_idr
        return


def test_severity_three_spread_is_between_two_and_three_times() -> None:
    m = ref.severity_multipliers()
    assert 2.0 <= m[3] / m[1] <= 3.0


# --- validation gate: architectural rule 4 --------------------------------


def test_gate_blocks_when_berkas_klaim_is_missing(corpus: list) -> None:
    from dataclasses import replace

    ep, gt = corpus[0]
    claim = clean_claim(ep, gt)
    stripped = replace(
        claim,
        documents_present=tuple(
            d for d in claim.documents_present if d != "berkas_klaim"
        ),
    )
    validated, failures = validate(RuleContext(ep, stripped, ep.discharge_day or 0))
    assert validated is None
    assert any(f.check == "berkas_klaim" for f in failures)


def test_gate_rejects_a_day_outside_the_episode(corpus: list) -> None:
    ep, gt = corpus[0]
    v, f = validate(RuleContext(ep, clean_claim(ep, gt), (ep.discharge_day or 0) + 5))
    assert v is None and any(x.check == "temporal" for x in f)


# --- rules: arm A ----------------------------------------------------------


def test_every_flag_cites_a_verbatim_span(corpus: list) -> None:
    """Architectural rule 6, measured rather than promised. A flag whose span
    does not match the record byte for byte is a fabricated citation."""
    import random as _r

    for ep, gt in corpus:
        claim, _, _ = inject(ep, gt, _r.Random(13))
        flags, _ = run(RuleContext(ep, claim, ep.discharge_day or 0))
        for f in flags:
            doc = next((d for d in ep.documents if d.doc_id == f.span.doc_id), None)
            assert doc is not None, f"{ep.episode_id}: span cites unknown document"
            assert doc.text[f.span.start : f.span.end] == f.span.text


def test_rules_never_flag_a_clean_claim(corpus: list) -> None:
    """The adoption-critical metric. A checker that cries wolf is switched off."""
    for ep, gt in corpus:
        flags, failures = run(RuleContext(ep, clean_claim(ep, gt), ep.discharge_day or 0))
        assert not failures, ep.episode_id
        assert not flags, f"{ep.episode_id}: {[f.rationale for f in flags]}"


def test_rules_catch_the_classes_we_claim_they_catch(corpus: list) -> None:
    """D1, D6 and D8 must be reachable. If one stops being caught, the arm-A
    baseline has silently changed and claim 3 needs re-measuring."""
    import random as _r

    caught: set[str] = set()
    for ep, gt in corpus:
        # NOT hash(episode_id): str hashing is salted per interpreter run, so
        # that made this test pass or fail depending on PYTHONHASHSEED. Seeds
        # are fixed and recorded everywhere — including in tests.
        claim, labels, _ = inject(ep, gt, _r.Random(int(ep.episode_id[2:]) % 997))
        truth = {x.defect_class.name for x in labels}
        flags, _ = run(RuleContext(ep, claim, ep.discharge_day or 0))
        caught |= {f.defect_class.name for f in flags} & truth
    assert {"D1", "D6", "D8"} <= caught


def test_rules_cannot_reach_the_judgment_classes(corpus: list) -> None:
    """D2, D3, D4 and D7 need someone to read the narrative. No lookup does
    that, and that gap is the product's reason to exist."""
    import random as _r

    for ep, gt in corpus:
        claim, _, _ = inject(ep, gt, _r.Random(5))
        flags, _ = run(RuleContext(ep, claim, ep.discharge_day or 0))
        found = {f.defect_class.name for f in flags}
        assert not (found & {"D2", "D3", "D4", "D7"})


def test_rules_run_at_any_day_of_stay(corpus: list) -> None:
    """The same code path serves the sweep. Running at day < discharge must not
    raise, and must not cite a document that does not exist yet."""
    ep, gt = corpus[0]
    claim = clean_claim(ep, gt)
    for day in range(ep.discharge_day or 0):
        flags, _ = run(RuleContext(ep, claim, day))
        for f in flags:
            doc = next(d for d in ep.documents if d.doc_id == f.span.doc_id)
            assert doc.day <= day


def test_defect_taxonomy_matches_measured_reach() -> None:
    """The `rules_reachable` field on DefectClass is a claim. Keep it honest."""
    assert {d.name for d in DefectClass if d.rules_reachable is True} == {
        "D1",
        "D6",
        "D8",
    }
