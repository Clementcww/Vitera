"""The deterministic rules layer — validation gate plus rule-based checks.

This is **arm A** of the three-arm experiment, and the paper's central claim
depends on it being a fair baseline rather than a strawman. So the rules here
are written to be as good as deterministic rules can be at what they reach:
they use the full record, they cite verbatim spans, and they are not
artificially crippled.

What they cannot reach is the point. D2, D3, D4 and D7 require judging whether
free-text clinical evidence supports a code. No lookup table does that, and
that gap is measured in bucket 10 rather than asserted.

Architectural rule 4: `validate` runs before any model. Architectural rule 6:
every flag carries a verbatim span, which is why the generator emits a
`berkas_klaim` cover sheet — administrative and absence-based findings need
something real to point at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vitera.contracts import (
    DefectClass,
    Document,
    Episode,
    Flag,
    FlagSource,
    Remedy,
    Span,
    ValidatedEpisode,
    ValidationFailure,
)
from vitera.generator import reference as ref
from vitera.generator.defects import CodedClaim

REQUIRED_DOCS = ("resume_medis", "berkas_klaim")


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Everything the rules may read: the record, and what was submitted."""

    episode: Episode
    claim: CodedClaim
    day: int

    @property
    def available(self) -> tuple[Document, ...]:
        present = set(self.claim.documents_present)
        return tuple(
            d
            for d in self.episode.documents
            if d.doc_id in present and d.day <= self.day
        )

    def find_span(self, needle: str, prefer: str | None = None) -> Span | None:
        """Locate a verbatim quotation. Returns None if it is not in the record,
        which causes the caller to drop the flag — rule 6 as a filter."""
        docs = sorted(
            self.available, key=lambda d: (d.doc_id != prefer, d.doc_id)
        )
        for d in docs:
            i = d.text.find(needle)
            if i >= 0:
                return Span(d.doc_id, i, i + len(needle), d.text[i : i + len(needle)])
        return None

    def line_containing(self, needle: str, prefer: str | None = None) -> Span | None:
        """Cite the whole line, not the fragment — a koder needs the context."""
        docs = sorted(
            self.available, key=lambda d: (d.doc_id != prefer, d.doc_id)
        )
        for d in docs:
            for m in re.finditer(r"[^\n]*", d.text):
                if needle in m.group(0) and m.group(0).strip():
                    return Span(d.doc_id, m.start(), m.end(), m.group(0))
        return None


# ---------------------------------------------------------------------------
# The validation gate — architectural rule 4
# ---------------------------------------------------------------------------


def validate(ctx: RuleContext) -> tuple[ValidatedEpisode | None, tuple[ValidationFailure, ...]]:
    """Deterministic checks that must pass before any model runs.

    A failure here is not a defect flag — it means the record is not in a state
    where scoring it would mean anything. The episode is handed back to a human
    with the reason.
    """
    failures: list[ValidationFailure] = []
    passed: list[str] = []

    if not ctx.episode.episode_id:
        failures.append(ValidationFailure("identitas", "episode_id kosong"))
    else:
        passed.append("identitas")

    if not ctx.claim.primary_dx:
        failures.append(
            ValidationFailure("diagnosis_utama", "klaim tanpa diagnosis utama")
        )
    else:
        passed.append("diagnosis_utama")

    if "berkas_klaim" not in ctx.claim.documents_present:
        failures.append(
            ValidationFailure("berkas_klaim", "lembar berkas klaim tidak dilampirkan")
        )
    else:
        passed.append("berkas_klaim")

    if ctx.day < 0 or (
        ctx.episode.discharge_day is not None and ctx.day > ctx.episode.discharge_day
    ):
        failures.append(ValidationFailure("temporal", f"hari {ctx.day} di luar episode"))
    else:
        passed.append("temporal")

    if failures:
        return None, tuple(failures)
    return ValidatedEpisode(ctx.episode, ctx.day, tuple(passed)), ()


# ---------------------------------------------------------------------------
# Rules. Each returns flags, every one carrying a verbatim span.
# ---------------------------------------------------------------------------


def _r_d1_berkas_tidak_lengkap(ctx: RuleContext) -> list[Flag]:
    """Required documents absent from the claim file."""
    out = []
    present = set(ctx.claim.documents_present)
    for doc_id in REQUIRED_DOCS:
        if doc_id in present:
            continue
        if not any(d.doc_id == doc_id and d.day <= ctx.day for d in ctx.episode.documents):
            continue  # not yet written; not a defect
        span = ctx.line_containing("Dokumen wajib", prefer="berkas_klaim")
        if span is None:
            continue
        out.append(
            Flag(
                DefectClass.D1,
                Remedy.OBTAIN,
                span,
                score=1.0,
                source=FlagSource.RULES,
                rationale=f"{doc_id} tidak dilampirkan pada berkas klaim",
            )
        )
    return out


def _r_d8_administrasi(ctx: RuleContext) -> list[Flag]:
    """SEP number or admission date on the claim disagrees with the berkas."""
    out = []
    expected_sep = f"No. SEP: {ctx.claim.sep_number}"
    if ctx.find_span(expected_sep, prefer="berkas_klaim") is None:
        span = ctx.line_containing("No. SEP:", prefer="berkas_klaim")
        if span is not None:
            out.append(
                Flag(
                    DefectClass.D8,
                    Remedy.OBTAIN,
                    span,
                    score=1.0,
                    source=FlagSource.RULES,
                    rationale=(
                        f"nomor SEP pada klaim ({ctx.claim.sep_number}) "
                        "tidak sesuai dengan berkas"
                    ),
                )
            )

    claimed = ctx.claim.admission_date_claimed.isoformat()
    if ctx.find_span(f"Tanggal masuk: {claimed}", prefer="berkas_klaim") is None:
        span = ctx.line_containing("Tanggal masuk:", prefer="berkas_klaim")
        if span is not None:
            out.append(
                Flag(
                    DefectClass.D8,
                    Remedy.OBTAIN,
                    span,
                    score=1.0,
                    source=FlagSource.RULES,
                    rationale=f"tanggal masuk pada klaim ({claimed}) tidak sesuai SEP",
                )
            )
    return out


def _r_d6_prosedur_tidak_koheren(ctx: RuleContext) -> list[Flag]:
    """A coded procedure that the record does not evidence."""
    out = []
    performed = {e.code for e in ctx.episode.events if e.code}
    for proc in ctx.claim.procedures:
        if proc in performed:
            continue
        span = ctx.line_containing("Tindakan:", prefer="resume_medis")
        if span is None:
            continue
        out.append(
            Flag(
                DefectClass.D6,
                Remedy.RECODE,
                span,
                score=1.0,
                source=FlagSource.RULES,
                rationale=(
                    f"prosedur {proc} dikode namun tidak tercatat dilakukan "
                    "pada rekam medis"
                ),
            )
        )
    return out


def _r_d5_penunjang_tidak_lengkap(ctx: RuleContext) -> list[Flag]:
    """A coded diagnosis whose supporting examinations are not in the file.

    Partial coverage by design: rules can see that the lab line is absent, but
    cannot judge whether the remaining narrative supports the diagnosis anyway.
    """
    out = []
    text = "\n".join(d.text for d in ctx.available)
    for code in ctx.claim.secondary_dx:
        try:
            com = ref.comorbidity_by_code(code)
        except KeyError:
            continue
        lab_signals = [s for s in com.signals if s.kind == "LAB"]
        if not lab_signals:
            continue
        if any(s.label in text for s in lab_signals):
            continue
        span = ctx.line_containing(code, prefer="resume_medis") or ctx.line_containing(
            "Dokumen wajib", prefer="berkas_klaim"
        )
        if span is None:
            continue
        out.append(
            Flag(
                DefectClass.D5,
                Remedy.OBTAIN,
                span,
                score=1.0,
                source=FlagSource.RULES,
                rationale=(
                    f"diagnosis {code} dikode, hasil pemeriksaan penunjang "
                    f"({', '.join(s.label for s in lab_signals)}) tidak dilampirkan"
                ),
            )
        )
    return out


_RULES = (
    _r_d1_berkas_tidak_lengkap,
    _r_d8_administrasi,
    _r_d6_prosedur_tidak_koheren,
    _r_d5_penunjang_tidak_lengkap,
)


def check(ctx: RuleContext) -> tuple[Flag, ...]:
    """Run every rule. Flags without a verbatim span were already dropped."""
    out: list[Flag] = []
    for rule in _RULES:
        out.extend(rule(ctx))
    return tuple(out)


def run(ctx: RuleContext) -> tuple[tuple[Flag, ...], tuple[ValidationFailure, ...]]:
    """Gate, then check. The gate always runs first — architectural rule 4."""
    validated, failures = validate(ctx)
    if validated is None:
        return (), failures
    return check(ctx), ()
