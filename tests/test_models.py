"""Bucket 8 tests — the model layer.

None of these load a checkpoint. What they protect is the part of bucket 8 that
would fail silently: pair construction that leaks the answer, a span that is
not verbatim, a calibration that is applied backwards, or a class attribution
that quietly disagrees with the corpus labels. A wrong number here would look
like a good result.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from vitera.agent.loop import run_pipeline
from vitera.agent.router import filter_spans
from vitera.contracts import (
    ClinicalText,
    DefectClass,
    Document,
    Episode,
    FlagSource,
    Remedy,
)
from vitera.generator.defects import CodedClaim
from vitera.models import calibrate
from vitera.models.bm25 import BM25, tokenise
from vitera.models.cross_encoder import CrossEncoderScorer, _classify
from vitera.models.pairs import (
    _strip_dx_list,
    attribute,
    build_pairs,
    evidence_lines,
    hypothesis,
)
from vitera.rules.engine import RuleContext

DATA = Path("data/generated")

RESUME = ClinicalText(
    "RESUME MEDIS PASIEN RAWAT INAP\n"
    "\n"
    "Lama perawatan: 5 hari.\n"
    "Diagnosis utama: Pneumonia dan influenza (J18.9).\n"
    "Diagnosis sekunder:\n"
    "  - Diabetes mellitus tipe 2 tanpa komplikasi (E11.9)\n"
    "  - Hipertensi esensial (primer) (I10)\n"
    "\n"
    "Perjalanan penyakit:\n"
    "  DM tipe 2 lama, mendapat terapi metformin.\n"
    "Pasien dipulangkan dalam keadaan perbaikan."
)

BERKAS = ClinicalText(
    "BERKAS KLAIM BPJS KESEHATAN — RAWAT INAP\n"
    "No. SEP: SEP999999\n"
    "Tanggal masuk: 2026-01-01\n"
    "Diagnosis masuk: Pneumonia dan influenza (J18.9)\n"
    "Dokumen wajib: resume medis, catatan perkembangan, "
    "hasil pemeriksaan penunjang."
)

CPPT = ClinicalText(
    "Hari perawatan ke-5.\n"
    "Diagnosis kerja: Pneumonia dan influenza.\n"
    "  - Gula darah sewaktu ↑ (200 mg/dL)\n"
    "  - Metformin 500 mg\n"
    "Keadaan umum tampak sakit sedang, kesadaran compos mentis."
)


def _ctx(*, claimed: tuple[str, ...]) -> RuleContext:
    ep = Episode(
        episode_id="EP999999",
        site_id="RS001",
        admission_date=date(2026, 1, 1),
        primary_dx="J18.9",
        secondary_dx=(),
        procedures=(),
        events=(),
        documents=(
            Document("berkas_klaim", 0, BERKAS),
            Document("cppt_hari_5", 5, CPPT),
            Document("resume_medis", 5, RESUME),
        ),
        discharge_day=5,
    )
    claim = CodedClaim(
        episode_id="EP999999",
        primary_dx="J18.9",
        secondary_dx=claimed,
        procedures=(),
        documents_present=("berkas_klaim", "cppt_hari_5", "resume_medis"),
        sep_number="SEP999999",
        admission_date_claimed=date(2026, 1, 1),
    )
    return RuleContext(ep, claim, 5)


# ---------------------------------------------------------------------------
# Pair construction
# ---------------------------------------------------------------------------


def test_evidence_excludes_the_diagnosis_list() -> None:
    """The single most important test in this file.

    If the `Diagnosis sekunder:` block survives into the evidence, the task
    collapses to substring matching and every number bucket 8 reports is an
    artifact of that, not a clinical result.
    """
    text = "\n".join(ln.text for ln in evidence_lines(_ctx(claimed=("E11.9",))))
    assert "Diagnosis sekunder" not in text
    assert "(E11.9)" not in text
    assert "(I10)" not in text
    # The narrative and the labs must survive — that is the actual evidence.
    assert "metformin" in text
    assert "Gula darah sewaktu" in text
    # And the primary diagnosis is context, not an answer key.
    assert "Diagnosis utama: Pneumonia dan influenza (J18.9)." in text


def test_strip_dx_list_keeps_cppt_bullets() -> None:
    """CPPT signal lines are also indented bullets. Dropping them would delete
    the evidence for every D4 finding."""
    lines = _strip_dx_list(
        [ln for ln in evidence_lines(_ctx(claimed=())) if ln.doc_id == "cppt_hari_5"]
    )
    assert any("Gula darah sewaktu" in ln.text for ln in lines)


def test_spans_are_verbatim() -> None:
    """Rule 6 is a filter downstream, but a scorer that produces bad offsets
    would have every flag silently dropped instead of loudly failing."""
    ctx = _ctx(claimed=("E11.9", "N18.3"))
    docs = {d.doc_id: d.text for d in ctx.episode.documents}
    for pair in build_pairs(ctx):
        anchor = pair.anchor
        assert anchor is not None
        span = anchor.span()
        assert docs[span.doc_id][span.start : span.end] == span.text


def test_label_is_documentation_not_presence() -> None:
    """A comorbidity with labs and no documentation is UNSUPPORTED. That is
    decision 2 in pairs.py and the D4 story depends on it."""
    ctx = _ctx(claimed=("E11.9", "N18.3"))
    pairs = {p.code: p for p in build_pairs(ctx, documented=("E11.9",))}
    assert pairs["E11.9"].label == 0
    assert pairs["N18.3"].label == 1


def test_empty_documented_is_not_the_same_as_unlabelled() -> None:
    ctx = _ctx(claimed=("E11.9",))
    assert build_pairs(ctx, documented=())[0].label == 1
    assert build_pairs(ctx)[0].label == -1


def test_hypothesis_needs_a_label() -> None:
    with pytest.raises(KeyError):
        hypothesis("Z99.9")


def test_has_signal_drives_remedy_not_the_model() -> None:
    ctx = _ctx(claimed=("E11.9", "A15.0"))
    pairs = {p.code: p for p in build_pairs(ctx)}
    assert pairs["E11.9"].has_signal is True  # glucose + metformin in the CPPT
    assert pairs["A15.0"].has_signal is False


# ---------------------------------------------------------------------------
# Class attribution — evaluation ground truth
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (DATA / "test.jsonl").exists(), reason="corpus not generated; run `make data`"
)
def test_attribution_agrees_with_the_corpus_labels() -> None:
    """Every attributed code must be a defective one, and every defective code
    must be attributed. A mismatch means per-class numbers are computed against
    the wrong pairs.
    """
    from vitera.models.pairs import iter_pairs

    with (DATA / "test.jsonl").open(encoding="utf-8") as fh:
        rows = [json.loads(x) for x in fh if x.strip()]

    for pair in iter_pairs(rows):
        # The reverse does not hold: D1 and D5 drop documents without touching
        # a code, so an unsupported code can carry no D2/D3/D4/D7 attribution.
        if pair.defect_class is not None:
            assert pair.label == 1, (
                f"{pair.episode_id}/{pair.code} attributed "
                f"{pair.defect_class} but labelled supported"
            )


def test_attribute_follows_the_d2_substitution() -> None:
    """D2's label names the code that was REPLACED; the claim carries the
    replacement. Attributing the original would score D2 against a code that
    is not on the claim."""
    row = {
        "claim": {"secondary_dx": ["E11.6", "I10"]},
        "defects": [
            {
                "defect_class": "D2",
                "detail": "E11.9 dikode sebagai E11.6",
                "target_code": "E11.9",
            }
        ],
    }
    assert attribute(row) == {"E11.6": "D2"}


def test_attribute_parses_the_d7_pattern() -> None:
    row = {
        "claim": {"secondary_dx": ["N18.3", "E11.9"]},
        "defects": [
            {
                "defect_class": "D7",
                "detail": "pola upcoding: N18.3, E11.9 ditambahkan tanpa bukti",
                "target_code": None,
            }
        ],
    }
    assert attribute(row) == {"N18.3": "D7", "E11.9": "D7"}


# ---------------------------------------------------------------------------
# Class and remedy assignment — deterministic, architectural rule 2
# ---------------------------------------------------------------------------


def test_signal_present_is_a_query_not_a_recode() -> None:
    """The remedy split is what a koder will judge. Labs present and no
    documentation must reach the DPJP, not the coder."""
    ctx = _ctx(claimed=("E11.9",))
    pair = build_pairs(ctx)[0]
    defect, remedy = _classify(pair, [pair])
    assert defect is DefectClass.D4
    assert remedy is Remedy.QUERY


def test_no_signal_anywhere_is_a_recode() -> None:
    ctx = _ctx(claimed=("A15.0",))
    pair = build_pairs(ctx)[0]
    defect, remedy = _classify(pair, [pair])
    assert defect is DefectClass.D3
    assert remedy is Remedy.RECODE


def test_sibling_of_an_evidenced_code_is_wrong_specificity() -> None:
    ctx = _ctx(claimed=("E11.6",))
    pair = build_pairs(ctx)[0]
    defect, _ = _classify(pair, [pair])
    assert defect is DefectClass.D2


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------


def test_bm25_keeps_icd_codes_as_single_tokens() -> None:
    assert "e11.9" in tokenise("Diagnosis (E11.9) ditegakkan")


def test_bm25_is_deterministic_and_ranks_the_matching_line() -> None:
    lines = ["Metformin 500 mg", "Keadaan umum tampak sakit sedang", "Amlodipin 10 mg"]
    bm = BM25().fit(tokenise(x) for x in lines)
    i, score = bm.best_line("terapi metformin", lines)
    assert i == 0
    assert score > 0
    assert bm.best_line("terapi metformin", lines) == (i, score)


def test_bm25_scores_zero_when_nothing_matches() -> None:
    lines = ["Metformin 500 mg"]
    bm = BM25().fit(tokenise(x) for x in lines)
    assert bm.best_line("tuberkulosis paru", lines) == (-1, 0.0)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def test_prior_shift_lowers_scores_when_deployment_is_cleaner() -> None:
    """the design brief data rule 4. Training at 41% positives and deploying at 10%
    without this correction is how a monitoring product over-flags itself into
    being switched off."""
    shifted = calibrate.prior_shift([0.5, 0.9], train_prior=0.41, deployment_prior=0.10)
    assert shifted[0] < 0.5
    assert shifted[1] < 0.9
    assert shifted[0] < shifted[1]  # monotone: rankings, and so AUCs, are unchanged


def test_prior_shift_is_identity_when_priors_match() -> None:
    same = calibrate.prior_shift([0.2, 0.8], train_prior=0.3, deployment_prior=0.3)
    assert same[0] == pytest.approx(0.2, abs=1e-6)
    assert same[1] == pytest.approx(0.8, abs=1e-6)


def test_temperature_flattens_an_overconfident_model() -> None:
    logits = [8.0, 7.0, -7.0, -8.0, 6.0, -6.0]
    labels = [1, 0, 1, 0, 1, 0]  # half the confident predictions are wrong
    assert calibrate.fit_temperature(logits, labels) > 1.0


def test_ece_is_zero_for_a_perfectly_calibrated_forecast() -> None:
    probs = [0.5] * 100
    labels = [1] * 50 + [0] * 50
    assert calibrate.ece(probs, labels) == pytest.approx(0.0, abs=1e-9)


def test_operating_point_respects_the_false_positive_budget() -> None:
    probs = [0.05] * 90 + [0.9] * 10
    labels = [0] * 90 + [1] * 10
    op = calibrate.recommend_thresholds(probs, labels, target_fpr=0.05)
    assert op.achieved_false_positive_rate <= 0.05
    assert op.abstain_below <= op.flag_at
    assert op.recall_at_flag_at == 1.0


def test_report_never_returns_accuracy() -> None:
    """Aggregate accuracy on imbalanced data is meaningless and the design brief
    forbids reporting it. Keep it unreachable rather than merely unused."""
    keys = calibrate.report([0.1, 0.9], [0, 1]).keys()
    assert "accuracy" not in keys
    assert {"pr_auc", "ece"} <= set(keys)


# ---------------------------------------------------------------------------
# Scorer integration — no checkpoint required
# ---------------------------------------------------------------------------


class _StubScorer(CrossEncoderScorer):
    """Everything except the neural net. Lets the flag-shaping contract be
    tested without a 124M-parameter download in CI."""

    def __init__(self, prob: float) -> None:  # noqa: D107
        self._prob = prob
        self.emit_floor = 0.4

    def probabilities(self, pairs):  # type: ignore[no-untyped-def, override]
        return [self._prob] * len(pairs)


def test_scorer_emits_flags_whose_spans_are_verbatim() -> None:
    ctx = _ctx(claimed=("E11.9", "A15.0"))
    docs = {d.doc_id: d.text for d in ctx.episode.documents}
    flags = _StubScorer(0.9).score(ctx)
    assert len(flags) == 2
    for f in flags:
        assert docs[f.span.doc_id][f.span.start : f.span.end] == f.span.text
        assert f.source is FlagSource.CROSS_ENCODER
        assert f.rationale


def test_scorer_stays_silent_below_the_emission_floor() -> None:
    assert _StubScorer(0.1).score(_ctx(claimed=("E11.9",))) == ()


def test_scorer_output_survives_the_pipeline_span_filter() -> None:
    """Rule 6 is enforced by `filter_spans`. A scorer whose spans do not survive
    it would silently produce an empty queue."""
    ctx = _ctx(claimed=("E11.9", "A15.0"))
    kept, dropped = filter_spans(_StubScorer(0.9).score(ctx), ctx.episode)
    assert dropped == 0
    assert len(kept) == 2


def test_pipeline_with_a_scorer_is_not_advisory() -> None:
    """Architectural rule 8 in the other direction: a run WITH the model layer
    up must not be labelled degraded, or the koder learns to ignore the label."""
    ctx = _ctx(claimed=("E11.9",))
    result = run_pipeline(ctx, scorer=_StubScorer(0.9))
    assert result.trace.degraded is False
    assert run_pipeline(ctx, scorer=None).trace.degraded is True
