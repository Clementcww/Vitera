"""Defect injection — bucket 4b.

**Negatives are created by changing codes, never by regenerating text.**
Regenerated text carries stylistic fingerprints and the model learns those
instead of clinical reasoning. Every function here mutates a code, drops a
document, or edits an administrative field. None of them rewrites clinical
prose, and `make leakage` is what proves it.

The submitted claim (`CodedClaim`) is separate from the episode: the episode is
what the hospital's record holds, the claim is what the koder sent to BPJS.
Defects live in the gap between them.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Sequence

from vitera import config
from vitera.contracts import DefectClass, Episode, Remedy
from vitera.generator import reference as ref
from vitera.generator.episode import GroundTruth

# Sibling codes for D2 — same parent, wrong specificity. A koder choosing one
# of these has made a real, plausible error rather than a random one.
_SIBLINGS: dict[str, list[str]] = {
    "E11.9": ["E11.6", "E11.8", "E14.9"],
    "I10": ["I11.9", "I15.9"],
    "N18.3": ["N18.2", "N18.4", "N18.9"],
    "D64.9": ["D50.9", "D62"],
    "E87.6": ["E87.5", "E87.1"],
    "E86": ["E87.0"],
    "J96.0": ["J96.9", "J80"],
    "A41.9": ["A41.5", "R65.2"],
    "K30": ["K29.7", "K21.0"],
    "E44.0": ["E44.1", "E46"],
    "A01.0": ["A01.4", "A02.0"],
    "A91": ["A90", "A97.0"],
    "J18.9": ["J15.9", "J12.9"],
    "I63.9": ["I64", "I63.5"],
    "I61.9": ["I62.9", "I60.9"],
    "N39.0": ["N30.0", "N10"],
    "A15.0": ["A15.3", "A16.2"],
    "A09": ["A08.4", "K52.9"],
}

# Wrong procedures for D6 — plausible neighbours that do not match the diagnosis.
_WRONG_PROCEDURES: dict[str, list[str]] = {
    "47.09": ["45.73", "54.11"],
    "74.1": ["74.4", "69.02"],
    "79.35": ["79.15", "78.55"],
}

_REQUIRED_DOCS = ("resume_medis",)


@dataclass(frozen=True, slots=True)
class CodedClaim:
    """What the koder submitted. Compare against GroundTruth to score."""

    episode_id: str
    primary_dx: str
    secondary_dx: tuple[str, ...]
    procedures: tuple[str, ...]
    documents_present: tuple[str, ...]
    sep_number: str
    admission_date_claimed: date


@dataclass(frozen=True, slots=True)
class DefectLabel:
    """Ground truth for one injected defect."""

    defect_class: DefectClass
    remedy: Remedy
    detail: str
    target_code: str | None = None


def clean_claim(ep: Episode, gt: GroundTruth) -> CodedClaim:
    """The claim a perfect koder would submit from this record.

    Note it codes only DOCUMENTED diagnoses. Undocumented comorbidities are a
    site-quality phenomenon, not an injected defect — they are already absent
    here, which is why undercoding shows up even in the defect-free arm.
    """
    return CodedClaim(
        episode_id=ep.episode_id,
        primary_dx=gt.primary_dx,
        secondary_dx=gt.documented_dx,
        procedures=gt.procedures,
        documents_present=tuple(d.doc_id for d in ep.documents),
        sep_number=f"SEP{ep.episode_id[2:]}",
        admission_date_claimed=ep.admission_date,
    )


# ---------------------------------------------------------------------------
# One injector per defect class. Each returns (claim, label) or None if the
# episode cannot carry that defect.
# ---------------------------------------------------------------------------


def _d1_berkas_tidak_lengkap(
    claim: CodedClaim, ep: Episode, gt: GroundTruth, rng: random.Random
) -> tuple[CodedClaim, DefectLabel] | None:
    present = [d for d in claim.documents_present if d in _REQUIRED_DOCS]
    if not present:
        return None
    dropped = rng.choice(present)
    return (
        replace(
            claim,
            documents_present=tuple(
                d for d in claim.documents_present if d != dropped
            ),
        ),
        DefectLabel(DefectClass.D1, Remedy.OBTAIN, f"berkas hilang: {dropped}"),
    )


def _d2_wrong_specificity(
    claim: CodedClaim, ep: Episode, gt: GroundTruth, rng: random.Random
) -> tuple[CodedClaim, DefectLabel] | None:
    candidates = [c for c in claim.secondary_dx if c in _SIBLINGS]
    if not candidates:
        return None
    target = rng.choice(candidates)
    wrong = rng.choice(_SIBLINGS[target])
    return (
        replace(
            claim,
            secondary_dx=tuple(wrong if c == target else c for c in claim.secondary_dx),
        ),
        DefectLabel(
            DefectClass.D2, Remedy.RECODE, f"{target} dikode sebagai {wrong}", target
        ),
    )


def _d3_unsupported_diagnosis(
    claim: CodedClaim, ep: Episode, gt: GroundTruth, rng: random.Random
) -> tuple[CodedClaim, DefectLabel] | None:
    """Code a diagnosis with no signal anywhere in the record."""
    present = set(gt.secondary_dx)
    options = [c.icd10 for c in ref.comorbidities() if c.icd10 not in present]
    if not options:
        return None
    invented = rng.choice(options)
    return (
        replace(claim, secondary_dx=claim.secondary_dx + (invented,)),
        DefectLabel(
            DefectClass.D3,
            Remedy.RECODE,
            f"{invented} dikode tanpa bukti di rekam medis",
            invented,
        ),
    )


def _d4_unsupported_severity(
    claim: CodedClaim, ep: Episode, gt: GroundTruth, rng: random.Random
) -> tuple[CodedClaim, DefectLabel] | None:
    """Code an UNDOCUMENTED major comorbidity to lift severity.

    Distinct from D3: the comorbidity is genuinely present in the record's
    signals — it was simply never documented. The claim is arguably clinically
    right and documentarily unsupported, which is exactly the hard case.
    """
    candidates = [
        c
        for c in gt.undocumented_dx
        if ref.comorbidity_by_code(c).severity_weight >= 2
    ]
    if not candidates:
        return None
    target = rng.choice(candidates)
    return (
        replace(claim, secondary_dx=claim.secondary_dx + (target,)),
        DefectLabel(
            DefectClass.D4,
            Remedy.QUERY,
            f"{target} dikode namun tidak terdokumentasi di resume medis",
            target,
        ),
    )


def _d5_missing_supporting_exam(
    claim: CodedClaim, ep: Episode, gt: GroundTruth, rng: random.Random
) -> tuple[CodedClaim, DefectLabel] | None:
    """Drop the CPPT pages carrying the lab evidence for a coded diagnosis."""
    lab_docs = [d for d in claim.documents_present if d.startswith("cppt_")]
    if len(lab_docs) < 2 or not claim.secondary_dx:
        return None
    dropped = rng.sample(lab_docs, k=max(1, len(lab_docs) // 2))
    return (
        replace(
            claim,
            documents_present=tuple(
                d for d in claim.documents_present if d not in dropped
            ),
        ),
        DefectLabel(
            DefectClass.D5,
            Remedy.OBTAIN,
            f"hasil pemeriksaan penunjang tidak dilampirkan ({len(dropped)} lembar)",
        ),
    )


def _d6_procedure_incoherence(
    claim: CodedClaim, ep: Episode, gt: GroundTruth, rng: random.Random
) -> tuple[CodedClaim, DefectLabel] | None:
    candidates = [p for p in claim.procedures if p in _WRONG_PROCEDURES]
    if not candidates:
        return None
    target = rng.choice(candidates)
    wrong = rng.choice(_WRONG_PROCEDURES[target])
    return (
        replace(
            claim,
            procedures=tuple(wrong if p == target else p for p in claim.procedures),
        ),
        DefectLabel(
            DefectClass.D6,
            Remedy.RECODE,
            f"prosedur {target} dikode {wrong}, tidak koheren dengan diagnosis",
            target,
        ),
    )


def _d7_upcoding(
    claim: CodedClaim, ep: Episode, gt: GroundTruth, rng: random.Random
) -> tuple[CodedClaim, DefectLabel] | None:
    """Add major comorbidities that are individually plausible but collectively
    inflate the CBG. Each is defensible alone; the pattern is not."""
    present = set(claim.secondary_dx)
    heavy = [
        c.icd10
        for c in ref.comorbidities()
        if c.severity_weight >= 2 and c.icd10 not in present
    ]
    if len(heavy) < 2:
        return None
    added = tuple(rng.sample(heavy, k=2))
    return (
        replace(claim, secondary_dx=claim.secondary_dx + added),
        DefectLabel(
            DefectClass.D7,
            Remedy.RECODE,
            f"pola upcoding: {', '.join(added)} ditambahkan tanpa bukti",
        ),
    )


def _d8_admin_mismatch(
    claim: CodedClaim, ep: Episode, gt: GroundTruth, rng: random.Random
) -> tuple[CodedClaim, DefectLabel] | None:
    kind = rng.choice(["sep", "tanggal"])
    if kind == "sep":
        return (
            replace(claim, sep_number=f"SEP{rng.randint(100000, 999999)}"),
            DefectLabel(
                DefectClass.D8, Remedy.OBTAIN, "nomor SEP tidak sesuai dengan episode"
            ),
        )
    return (
        replace(
            claim,
            admission_date_claimed=claim.admission_date_claimed
            + timedelta(days=rng.choice([-2, -1, 1, 2])),
        ),
        DefectLabel(
            DefectClass.D8, Remedy.OBTAIN, "tanggal masuk pada klaim tidak sesuai SEP"
        ),
    )


_INJECTORS = {
    DefectClass.D1: _d1_berkas_tidak_lengkap,
    DefectClass.D2: _d2_wrong_specificity,
    DefectClass.D3: _d3_unsupported_diagnosis,
    DefectClass.D4: _d4_unsupported_severity,
    DefectClass.D5: _d5_missing_supporting_exam,
    DefectClass.D6: _d6_procedure_incoherence,
    DefectClass.D7: _d7_upcoding,
    DefectClass.D8: _d8_admin_mismatch,
}


def inject(
    ep: Episode, gt: GroundTruth, rng: random.Random
) -> tuple[CodedClaim, tuple[DefectLabel, ...], tuple[str, ...]]:
    """Roll each defect class independently at its cited rate, among the
    episodes that could carry it.

    Returns ``(claim, labels, eligible_classes)``.

    **Order matters here, and getting it wrong leaks the label.**

    Not every episode can carry every defect: D6 needs a procedure, D4 needs an
    undocumented major comorbidity, D7 needs two spare heavy comorbidities. If
    the rate is rolled *before* eligibility is checked, then every ineligible
    episode is automatically a negative, and eligibility is visible in the
    clinical text — a classifier can then predict the label from episode
    composition without reading a single code. Our first leakage run failed at
    AUC 0.637 for exactly this reason.

    So eligibility is determined FIRST, and the rate is rolled only among
    eligible episodes. Positives and negatives for a class are then drawn from
    the same pool, and ``eligible_classes`` is recorded so every downstream
    evaluation can condition on it. See docs/DATA_CARD.md.
    """
    rates = config.defects(strict=True)["defects"]
    claim = clean_claim(ep, gt)
    labels: list[DefectLabel] = []
    eligible: list[str] = []

    for cls in DefectClass:
        # Probe eligibility on a throwaway RNG so the probe cannot shift the
        # main stream and make generation order-dependent.
        probe = _INJECTORS[cls](claim, ep, gt, random.Random(0))
        if probe is None:
            continue
        eligible.append(cls.name)

        if rng.random() >= float(rates[cls.name]["rate"]):
            continue
        result = _INJECTORS[cls](claim, ep, gt, rng)
        if result is None:  # defensive; probe said eligible
            continue
        claim, label = result
        labels.append(label)

    return claim, tuple(labels), tuple(eligible)


def visible_documents(ep: Episode, claim: CodedClaim) -> tuple[str, ...]:
    """Document text the pipeline may actually read, honouring D1/D5 drops."""
    return tuple(
        d.text for d in ep.documents if d.doc_id in set(claim.documents_present)
    )
