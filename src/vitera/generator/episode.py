"""Clean episode generation — bucket 4a.

Produces clinically coherent inpatient episodes with **no injected defects**.
Defect injection is bucket 4b and operates on the output of this module by
mutating codes, never by regenerating text.

The mechanic this module exists to create:

    a comorbidity's SIGNALS (labs, meds, orders) enter the record on
    `signal_day`; its DOCUMENTATION enters on `documented_day`, which may be
    later, or never.

Signals always appear. Documentation appears with a probability driven by the
site's documentation quality. The window between the two is what Vitera
operates in, and `documented_day is None` is the undercoding case that
Opitasari & Nurwahyuni (2018) measured at 68.6% of episodes.

**Site quality is not a defect.** Sparse documentation is a property of the
hospital and is labelled separately from injected defects, so that the fairness
analysis can attribute an error to one or the other.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

from vitera import config
from vitera.contracts import (
    ClinicalEvent,
    ClinicalText,
    Document,
    Episode,
    EventKind,
    SecondaryDiagnosis,
)
from vitera.generator import reference as ref

# Mean documentation quality across hospital classes in config/sites.yaml.
# Used to centre the site adjustment so the corpus-wide undocumented rate
# reproduces the measured 68.6% rather than drifting from it.
_MEAN_DOC_QUALITY = 0.75


@dataclass(frozen=True, slots=True)
class GroundTruth:
    """What is clinically true, before any coding or defect injection.

    Kept alongside the episode rather than inside it: the episode is what the
    hospital's system would hold, this is what a perfect coder would produce.
    Bucket 5's arm-A baseline and bucket 10's scoring both compare against it.
    """

    cbg: str
    primary_dx: str
    secondary_dx: tuple[str, ...]  # every comorbidity clinically present
    documented_dx: tuple[str, ...]  # the subset actually written down
    procedures: tuple[str, ...]
    severity: int
    site_class: str
    # Separate label, per CLAUDE.md: this is a property of the site, not a defect.
    undocumented_dx: tuple[str, ...]

    @property
    def has_undercoding(self) -> bool:
        return bool(self.undocumented_dx)


def _pick_group(rng: random.Random) -> ref.CBGGroup:
    return rng.choice(ref.cbg_groups())


def _pick_comorbidities(
    rng: random.Random, group: ref.CBGGroup
) -> tuple[ref.Comorbidity, ...]:
    """Draw plausible comorbidities for this group, weighted by prevalence."""
    allowed = ref.plausible_comorbidities(group.cbg)
    chosen = [
        ref.comorbidity_by_code(code)
        for code in allowed
        if rng.random() < ref.comorbidity_by_code(code).prevalence
    ]
    return tuple(chosen)


def _signal_day(rng: random.Random, los: int, params: dict) -> int:
    """When a comorbidity becomes clinically visible.

    ASSUMED distribution — no Indonesian study reports this. See
    config/defects.yaml temporal.signal_day_model and honesty note 1.
    Beta(1.5, 3.0) scaled to LOS: skewed early, since most comorbidities are
    present on admission or surface in the first days of workup.
    """
    a, b = params.get("a", 1.5), params.get("b", 3.0)
    return min(los, int(rng.betavariate(a, b) * (los + 1)))


def _documented_day(
    rng: random.Random, signal_day: int, los: int, p_undocumented: float, gap: dict
) -> int | None:
    """When it appears in the notes — or never.

    ASSUMED gap distribution. Geometric with p from config, capped, so most
    documentation follows within a day or two and a tail runs longer.
    """
    if rng.random() < p_undocumented:
        return None
    p = gap.get("p", 0.45)
    cap = gap.get("max", 7)
    delay = min(cap, rng.geometric(p) - 1 if hasattr(rng, "geometric") else _geom(rng, p, cap))
    day = signal_day + delay
    # Documentation cannot arrive after the patient has gone home.
    return day if day <= los else None


def _geom(rng: random.Random, p: float, cap: int) -> int:
    """Geometric draw, 0-indexed, capped. random.Random has no geometric()."""
    k = 0
    while k < cap and rng.random() >= p:
        k += 1
    return k


def _undocumented_probability(base_rate: float, doc_quality: float) -> float:
    """Site documentation quality scales the undocumented rate.

    Centred on the mean class quality so the corpus reproduces the measured
    68.6% overall while still varying by hospital class. This is the SITE
    quality generator — deliberately separate from defect injection.
    """
    scaled = base_rate * ((1.0 + _MEAN_DOC_QUALITY) - doc_quality)
    return max(0.0, min(0.95, scaled))


def _severity(documented: Sequence[str]) -> int:
    """Severity from DOCUMENTED comorbidities only.

    This is the whole financial point: a comorbidity that is clinically present
    but unwritten cannot lift severity, so the episode groups and pays lower.
    """
    weight = sum(ref.comorbidity_by_code(c).severity_weight for c in documented)
    if weight >= 4:
        return 3
    if weight >= 2:
        return 2
    return 1


# ---------------------------------------------------------------------------
# Text — templated, deterministic, never model-generated
# ---------------------------------------------------------------------------


def _cppt(day: int, group: ref.CBGGroup, active: Sequence[ref.Comorbidity]) -> str:
    """Catatan Perkembangan Pasien Terintegrasi — the daily progress note.

    Signals appear here whether or not the comorbidity is ever documented as a
    diagnosis. That is the asymmetry the cross-encoder has to learn to read.
    """
    lines = [f"Hari perawatan ke-{day}.", f"Diagnosis kerja: {group.label}."]
    for c in active:
        for s in c.signals:
            lines.append(f"  - {s.render()}")
    lines.append("Keadaan umum tampak sakit sedang, kesadaran compos mentis.")
    return "\n".join(lines)


def _resume_medis(
    group: ref.CBGGroup,
    documented: Sequence[ref.Comorbidity],
    los: int,
    rng: random.Random,
) -> str:
    """Discharge summary. Contains ONLY the documented comorbidities.

    Undocumented ones are absent here while their signals sit in the CPPT —
    which is exactly the record a koder would have to reconcile by hand.
    """
    parts = [
        "RESUME MEDIS PASIEN RAWAT INAP",
        "",
        f"Lama perawatan: {los} hari.",
        f"Diagnosis utama: {group.label} ({group.primary}).",
    ]
    if documented:
        parts.append("Diagnosis sekunder:")
        for c in documented:
            parts.append(f"  - {c.label} ({c.icd10})")
    else:
        parts.append("Diagnosis sekunder: tidak ada.")
    if group.required_procedure:
        parts.append(f"Tindakan: {group.procedure_label} ({group.required_procedure}).")
    parts.append("")
    parts.append("Perjalanan penyakit:")
    for c in documented:
        parts.append(f"  {rng.choice(c.doc_phrases)}")
    parts.append("Pasien dipulangkan dalam keadaan perbaikan.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# The generator
# ---------------------------------------------------------------------------


def generate_episode(
    episode_id: str,
    site_id: str,
    site_class: str,
    doc_quality: float,
    rng: random.Random,
    admission_date: date,
) -> tuple[Episode, GroundTruth]:
    """One clean episode plus its ground truth. No defects injected."""
    defects = config.defects(strict=False)
    base_undoc = defects["temporal"]["undocumented_rate"]["rate"]
    gap = defects["temporal"]["signal_to_doc_gap_days"]["distribution"]
    signal_params = defects["temporal"]["signal_day_model"]["distribution"]

    group = _pick_group(rng)
    los = rng.randint(group.los_min, group.los_max)
    comorbid = _pick_comorbidities(rng, group)
    p_undoc = _undocumented_probability(base_undoc, doc_quality)

    secondary: list[SecondaryDiagnosis] = []
    for c in comorbid:
        sig = _signal_day(rng, los, signal_params)
        doc = _documented_day(rng, sig, los, p_undoc, gap)
        secondary.append(
            SecondaryDiagnosis(icd10=c.icd10, signal_day=sig, documented_day=doc)
        )

    # Events: every signal fires on its comorbidity's signal_day and persists.
    events: list[ClinicalEvent] = [
        ClinicalEvent(day=0, kind=EventKind.ADMIN, code="SEP", text=None)
    ]
    for c, sd in zip(comorbid, secondary, strict=True):
        assert sd.signal_day is not None
        for s in c.signals:
            events.append(
                ClinicalEvent(
                    day=sd.signal_day,
                    kind=EventKind[s.kind],
                    code=s.code,
                    text=ClinicalText(s.render()),
                )
            )
    if group.required_procedure:
        events.append(
            ClinicalEvent(
                day=min(1, los),
                kind=EventKind.PROCEDURE,
                code=group.required_procedure,
                text=ClinicalText(group.procedure_label or ""),
            )
        )

    # Documents: a CPPT per day, resume medis at discharge.
    documents: list[Document] = []
    for day in range(los + 1):
        active = [
            c
            for c, sd in zip(comorbid, secondary, strict=True)
            if sd.signal_day is not None and sd.signal_day <= day
        ]
        documents.append(
            Document(
                doc_id=f"cppt_hari_{day}",
                day=day,
                text=ClinicalText(_cppt(day, group, active)),
            )
        )

    documented_codes = tuple(
        sd.icd10 for sd in secondary if sd.documented_day is not None
    )
    documented_comorbid = [c for c in comorbid if c.icd10 in documented_codes]
    documents.append(
        Document(
            doc_id="resume_medis",
            day=los,
            text=ClinicalText(_resume_medis(group, documented_comorbid, los, rng)),
        )
    )

    episode = Episode(
        episode_id=episode_id,
        site_id=site_id,
        admission_date=admission_date,
        primary_dx=group.primary,
        secondary_dx=tuple(secondary),
        procedures=(group.required_procedure,) if group.required_procedure else (),
        events=tuple(events),
        documents=tuple(documents),
        discharge_day=los,
    )

    truth = GroundTruth(
        cbg=group.cbg,
        primary_dx=group.primary,
        secondary_dx=tuple(sd.icd10 for sd in secondary),
        documented_dx=documented_codes,
        procedures=episode.procedures,
        severity=_severity(documented_codes),
        site_class=site_class,
        undocumented_dx=tuple(
            sd.icd10 for sd in secondary if sd.documented_day is None
        ),
    )
    return episode, truth


def generate_corpus(
    n: int, seed: int | None = None
) -> list[tuple[Episode, GroundTruth]]:
    """Generate ``n`` clean episodes across the configured sites."""
    ref.warn_if_unverified()
    seeds = config.seeds(seed)
    rng = seeds.rng("generator")
    sites = config.sites()
    classes = sites["classes"]
    site_list = sites["sites"]
    start = date(2026, 1, 1)

    out = []
    for i in range(n):
        site = site_list[i % len(site_list)]
        out.append(
            generate_episode(
                episode_id=f"EP{i:06d}",
                site_id=site["id"],
                site_class=site["class"],
                doc_quality=float(classes[site["class"]]["doc_quality"]),
                rng=rng,
                admission_date=start + timedelta(days=rng.randint(0, 300)),
            )
        )
    return out
