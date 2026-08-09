"""The gate between a scanned sheet and the rest of the system.

Architectural rule 4 says the validation gate precedes every model. Paper
intake is where that rule earns its keep: an OCR read is the only input to
Vitera that can be wrong *without anyone having made a mistake*, and if a
misread SEP number or a dropped digit in a tariff reaches the pipeline it
arrives wearing the same clothes as a genuine claim defect.

So this module answers two separate questions and never lets them blur:

    is the sheet legible?     completeness, confidence floors, whether the
                              printed total and the rows are the same number.
                              Failures here mean *scan it again*.

    does it match the record? SEP, admission date, card number and tariff
                              against what the hospital's system holds.
                              Mismatches here are candidate D8 findings.

The blur is the danger. A tariff that does not reconcile is a claim finding if
the figure was read cleanly, and a *read* failure if it was not — and reporting
the second as the first would put an OCR bug in front of a koder as a claim
defect. Every reconciliation therefore checks the read quality of the fields it
depends on first, and downgrades itself to `needs_human_read` when they are
weak. That downgrade is the whole point of the module.

Nothing here calls a model, and nothing here is learned. Thresholds come from
`config/thresholds.yaml`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from vitera import config
from vitera.intake.extract import ExtractedFPK, LineRead
from vitera.intake.form import Identity

Severity = Literal["blocking", "advisory", "needs_human_read"]


@dataclass(frozen=True, slots=True)
class IntakeFailure:
    check: str
    detail: str
    severity: Severity = "blocking"
    subject: str | None = None  # SEP number or field name, when there is one


@dataclass
class IntakeResult:
    extracted: ExtractedFPK
    failures: list[IntakeFailure] = field(default_factory=list)
    matched: dict[str, str] = field(default_factory=dict)  # sep -> episode_id
    unmatched: list[str] = field(default_factory=list)
    rows_complete: float = 0.0

    @property
    def blocking(self) -> list[IntakeFailure]:
        return [f for f in self.failures if f.severity == "blocking"]

    @property
    def passed(self) -> bool:
        """Rule 4: nothing downstream runs while this is False."""
        return not self.blocking

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for f in self.failures:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return {
            "passed": self.passed,
            "engine": self.extracted.engine,
            "pages": self.extracted.pages,
            "fields_read": len(self.extracted.fields),
            "fields_missing": list(self.extracted.missing),
            "mean_field_confidence": round(self.extracted.mean_confidence, 3),
            "rows": len(self.extracted.lines),
            "rows_complete_share": round(self.rows_complete, 3),
            "matched_episodes": len(self.matched),
            "unmatched_sep": list(self.unmatched),
            "failures": counts,
        }


_REQUIRED = ("nama_ppk", "kode_ppk", "bulan_pelayanan", "jenis_pelayanan")

_LINE_FIELDS = ("sep_number", "no_kartu", "tanggal_masuk", "hari", "cbg_code")


def _cfg() -> dict[str, Any]:
    return dict(config.thresholds()["intake"])


def _complete(line: LineRead) -> bool:
    return all(getattr(line, f) is not None for f in _LINE_FIELDS)


def _digit_distance(a: str, b: str) -> int:
    """Positional differences between two fixed-width numeric strings."""
    if len(a) != len(b):
        return max(len(a), len(b))
    return sum(1 for x, y in zip(a, b, strict=True) if x != y)


# ---------------------------------------------------------------------------
# Is the sheet legible?
# ---------------------------------------------------------------------------


def check_legibility(x: ExtractedFPK) -> tuple[list[IntakeFailure], float]:
    cfg = _cfg()
    out: list[IntakeFailure] = []

    for name in _REQUIRED:
        if name not in x.fields:
            out.append(
                IntakeFailure(
                    "field_missing",
                    f"kolom wajib '{name}' tidak terbaca pada lembar pindaian",
                    "blocking",
                    name,
                )
            )

    floor = float(cfg["min_field_confidence"])
    for name, f in sorted(x.fields.items()):
        if f.confidence < floor:
            out.append(
                IntakeFailure(
                    "low_confidence",
                    f"'{name}' terbaca '{f.value}' dengan keyakinan "
                    f"{f.confidence:.2f} < {floor:.2f}; perlu diperiksa manusia",
                    "needs_human_read",
                    name,
                )
            )

    jenis = (x.get("jenis_pelayanan") or "").upper()
    accepted = [str(a).upper() for a in cfg["accepted_jenis_pelayanan"]]
    if jenis and not any(a in jenis for a in accepted):
        out.append(
            IntakeFailure(
                "out_of_scope",
                f"jenis pelayanan '{jenis}' di luar cakupan build ini "
                f"({', '.join(accepted)}, rawat inap tingkat lanjutan). "
                "FPK FKTP (RITP) dan rawat jalan tidak diproses.",
                "blocking",
                "jenis_pelayanan",
            )
        )

    if not x.lines:
        out.append(
            IntakeFailure("no_rows", "tidak ada baris rincian yang terbaca", "blocking")
        )
        return out, 0.0

    complete = sum(1 for ln in x.lines if _complete(ln))
    share = complete / len(x.lines)
    if share < float(cfg["min_rows_complete"]):
        out.append(
            IntakeFailure(
                "rows_incomplete",
                f"hanya {complete}/{len(x.lines)} baris terbaca lengkap "
                f"({share:.0%} < {float(cfg['min_rows_complete']):.0%}); "
                "pindai ulang pada resolusi lebih tinggi",
                "blocking",
            )
        )
    for ln in x.lines:
        if not _complete(ln):
            gaps = [f for f in _LINE_FIELDS if getattr(ln, f) is None]
            out.append(
                IntakeFailure(
                    "row_incomplete",
                    f"baris {ln.index} ({ln.sep_number or '?'}): "
                    f"{', '.join(gaps)} tidak terbaca",
                    "needs_human_read",
                    ln.sep_number,
                )
            )

    seps = [ln.sep_number for ln in x.lines if ln.sep_number]
    if len(set(seps)) != len(seps):
        out.append(
            IntakeFailure(
                "duplicate_sep",
                "nomor SEP muncul lebih dari sekali pada satu FPK",
                "blocking",
            )
        )

    out.extend(_check_totals(x))
    return out, share


def _check_totals(x: ExtractedFPK) -> list[IntakeFailure]:
    """The printed JUMLAH against the rows it claims to summarise.

    This is the cheapest real check on the whole sheet: the two numbers are the
    same number by construction, so any disagreement is either a misread or an
    arithmetic error on the form, and both stop the batch.
    """
    cfg = _cfg()
    out: list[IntakeFailure] = []
    kasus = x.totals.get("kasus")
    hari = x.totals.get("hari")
    biaya = x.totals.get("biaya_idr")

    if kasus is not None and kasus != len(x.lines):
        out.append(
            IntakeFailure(
                "kasus_mismatch",
                f"JUMLAH KASUS pada formulir {kasus}, baris rincian terbaca "
                f"{len(x.lines)}",
                "blocking",
            )
        )
    if hari is not None and all(ln.hari is not None for ln in x.lines):
        total = sum(ln.hari or 0 for ln in x.lines)
        if total != hari:
            out.append(
                IntakeFailure(
                    "hari_mismatch",
                    f"JUMLAH HR/TINDAKAN pada formulir {hari}, jumlah baris {total}",
                    "blocking",
                )
            )
    if biaya is not None and all(ln.biaya_idr is not None for ln in x.lines):
        total = sum(ln.biaya_idr or 0 for ln in x.lines)
        if abs(total - biaya) > int(cfg["max_total_mismatch_idr"]):
            out.append(
                IntakeFailure(
                    "biaya_mismatch",
                    f"JUMLAH BIAYA pada formulir Rp {biaya:,}, jumlah baris "
                    f"Rp {total:,}",
                    "blocking",
                )
            )
    return out


# ---------------------------------------------------------------------------
# Does it match the record?
# ---------------------------------------------------------------------------


def reconcile(
    x: ExtractedFPK,
    index: dict[str, tuple[Any, Any]],
    *,
    grouper: Any | None = None,
) -> tuple[list[IntakeFailure], dict[str, str], list[str]]:
    """Cross-check each read row against the episode the hospital holds.

    `index` maps SEP number to `(Episode, CodedClaim)`.

    Every comparison is guarded by the read quality of the field it depends on.
    A row whose card number failed to parse cannot produce an identity-mismatch
    finding; it produces a `needs_human_read`. Without that guard this function
    would manufacture D8 findings out of OCR noise, which is worse than not
    checking at all — the koder would learn to ignore the category.
    """
    from vitera.grouper.grouper import Grouper

    grouper = grouper or Grouper()
    failures: list[IntakeFailure] = []
    matched: dict[str, str] = {}
    unmatched: list[str] = []

    for ln in x.lines:
        if not ln.sep_number:
            continue
        pair = index.get(ln.sep_number)
        if pair is None:
            unmatched.append(ln.sep_number)
            failures.append(
                IntakeFailure(
                    "sep_not_found",
                    f"{ln.sep_number} tidak ada pada rekam episode rumah sakit",
                    "blocking",
                    ln.sep_number,
                )
            )
            continue
        ep, claim = pair
        matched[ln.sep_number] = ep.episode_id

        if ln.tanggal_masuk is None:
            failures.append(
                IntakeFailure(
                    "date_unreadable",
                    f"{ln.sep_number}: tanggal masuk tidak terbaca, "
                    "tidak dapat dicocokkan",
                    "needs_human_read",
                    ln.sep_number,
                )
            )
        elif ln.tanggal_masuk != claim.admission_date_claimed:
            failures.append(
                IntakeFailure(
                    "admission_date_mismatch",
                    f"{ln.sep_number}: tanggal masuk pada FPK "
                    f"{ln.tanggal_masuk}, pada klaim "
                    f"{claim.admission_date_claimed} (kandidat D8)",
                    "advisory",
                    ln.sep_number,
                )
            )

        expected_kartu = Identity.of(ep.episode_id).no_kartu
        if ln.no_kartu is None:
            failures.append(
                IntakeFailure(
                    "kartu_unreadable",
                    f"{ln.sep_number}: nomor kartu tidak terbaca",
                    "needs_human_read",
                    ln.sep_number,
                )
            )
        elif ln.no_kartu != expected_kartu:
            # One differing digit in a thirteen-digit field is far more often a
            # misread than a wrong card, and calling it a D8 candidate would
            # teach the koder to distrust the category. Two or more is a
            # difference no single OCR slip produces.
            near = _digit_distance(ln.no_kartu, expected_kartu) <= 1
            failures.append(
                IntakeFailure(
                    "kartu_mismatch",
                    f"{ln.sep_number}: nomor kartu pada FPK {ln.no_kartu}, "
                    f"pada rekam {expected_kartu}"
                    + (
                        " — beda satu digit, periksa hasil pindaian sebelum "
                        "menyimpulkan"
                        if near
                        else " (kandidat D8)"
                    ),
                    "needs_human_read" if near else "advisory",
                    ln.sep_number,
                )
            )

        group = grouper.group_codes(
            claim.primary_dx, claim.secondary_dx, claim.procedures
        )
        if ln.biaya_idr is None or ln.cbg_code is None:
            failures.append(
                IntakeFailure(
                    "tariff_unreadable",
                    f"{ln.sep_number}: kode CBG atau biaya tidak terbaca, "
                    "tarif tidak dapat direkonsiliasi",
                    "needs_human_read",
                    ln.sep_number,
                )
            )
        elif group.tariff_idr is None:
            failures.append(
                IntakeFailure(
                    "ungroupable",
                    f"{ln.sep_number}: {group.ungroupable_reason}. "
                    "Tarif tidak diperkirakan.",
                    "advisory",
                    ln.sep_number,
                )
            )
        elif ln.biaya_idr != group.tariff_idr:
            # Rule 7: the grouper is authoritative. The form is what was
            # submitted; the difference is the finding, and the direction of
            # the difference is left to the koder to read.
            failures.append(
                IntakeFailure(
                    "tariff_mismatch",
                    f"{ln.sep_number}: biaya pada FPK Rp {ln.biaya_idr:,}, "
                    f"grouper Rp {group.tariff_idr:,} untuk {group.cbg_code}",
                    "advisory",
                    ln.sep_number,
                )
            )

    return failures, matched, unmatched


def build_index(rows: list[dict[str, Any]]) -> dict[str, tuple[Any, Any]]:
    """SEP number -> (Episode, CodedClaim), from the corpus JSONL."""
    from vitera.generator.corpus import claim_from_dict, episode_from_dict

    out: dict[str, tuple[Any, Any]] = {}
    for r in rows:
        claim = claim_from_dict(r["claim"])
        out[claim.sep_number] = (episode_from_dict(r["episode"]), claim)
    return out


def validate(
    x: ExtractedFPK,
    index: dict[str, tuple[Any, Any]] | None = None,
) -> IntakeResult:
    """Run the gate. Reconciliation is skipped when the sheet is illegible —
    there is nothing to be gained from cross-checking values we could not read.
    """
    failures, share = check_legibility(x)
    result = IntakeResult(extracted=x, failures=list(failures), rows_complete=share)
    if result.passed and index is not None:
        extra, matched, unmatched = reconcile(x, index)
        result.failures.extend(extra)
        result.matched = matched
        result.unmatched = unmatched
    return result


__all__ = [
    "IntakeFailure",
    "IntakeResult",
    "build_index",
    "check_legibility",
    "reconcile",
    "validate",
]
