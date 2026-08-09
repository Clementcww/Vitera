"""The corrected FPK: a draft, and never anything more than a draft.

The chain this file closes is: paper in, pipeline, paper out. It takes the
episodes an intake read matched to the record, runs the *existing* pipeline
over each one, and writes a second FPK carrying what the check found.

Three constraints shape every line of it.

**Rule 1 — the system drafts and stages, a human commits.** The output is
stamped DRAF on every page, its signature block is empty, and nothing is
written back to the claim of record, to E-Klaim or to BPJS. On paper that is
the strongest form the rule can take: the document is unusable until a person
signs it, which is exactly the property we want.

**Rule 7 — the grouper is authoritative for tariff.** Corrected amounts come
from `export.money_view`, the same two grouper calls the workbench renders, so
the printout and the screen cannot disagree. Only the `now` figure — what
survives a BPJS verifier today — goes into the JUMLAH row. The `if_confirmed`
figure, which depends on a DPJP documenting care the record only suggests, is
printed as a separate conditional line and never totalled. Putting a
conditional amount in the box a hospital submits would be the single most
damaging thing this file could do.

**No second pipeline.** `run_pipeline` here is the one `demo.py`, `export.py`
and the sweep call. Intake is a reader and a writer around it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from vitera.api.export import money_view
from vitera.contracts import PipelineResult
from vitera.generator.defects import CodedClaim
from vitera.grouper.grouper import Grouper
from vitera.intake.form import FPKForm, FPKLine, format_idr
from vitera.intake.render import render_fpk
from vitera.intake.validate import IntakeResult
from vitera.rules.engine import RuleContext

# Wording is the koder's, not the taxonomy's, and it says what the RECORD does
# not show rather than what anyone should have done — the same rule the
# workbench copy follows, and the same strings, so the two agree.
DEFECT_ID = {
    "D1": "Berkas klaim tidak lengkap",
    "D2": "Spesifisitas kode kurang, ada kode saudara",
    "D3": "Diagnosis tidak didukung narasi rekam medis",
    "D4": "Komorbiditas terbaca di catatan, belum terdokumentasi",
    "D5": "Pemeriksaan penunjang belum dilampirkan",
    "D6": "Prosedur tidak koheren dengan diagnosis",
    "D7": "Pola penambahan komorbiditas tanpa bukti",
    "D8": "Ketidakcocokan administratif (SEP, identitas, tanggal)",
}

REMEDY_ID = {
    "RECODE": ("Perbaiki kode", "Koder"),
    "OBTAIN": ("Lengkapi berkas", "Petugas berkas"),
    "QUERY": ("Konfirmasi ke DPJP", "DPJP"),
}


@dataclass(frozen=True, slots=True)
class Correction:
    """One episode, before and after. `after` is the grouper's figure."""

    episode_id: str
    sep_number: str
    cbg_before: str | None
    cbg_after: str | None
    biaya_before: int | None
    biaya_after: int | None
    biaya_if_confirmed: int | None
    flags: int

    @property
    def delta(self) -> int | None:
        if self.biaya_before is None or self.biaya_after is None:
            return None
        return self.biaya_after - self.biaya_before


@dataclass
class CorrectionRun:
    corrections: list[Correction]
    findings: list[dict[str, Any]]
    advisory: bool
    errors: list[str]

    @property
    def total_before(self) -> int:
        return sum(c.biaya_before or 0 for c in self.corrections)

    @property
    def total_after(self) -> int:
        return sum(c.biaya_after or 0 for c in self.corrections)

    @property
    def total_if_confirmed(self) -> int:
        return sum(
            c.biaya_if_confirmed if c.biaya_if_confirmed is not None else 0
            for c in self.corrections
        )


def _finding(episode_id: str, sep: str, flag: Any) -> dict[str, Any]:
    remedy, actor = REMEDY_ID.get(flag.remedy.name, (flag.remedy.name, "-"))
    return {
        # `episode_id` is the printed line's heading; `sep` and `episode` are
        # the same two identifiers unjoined, for the UI export.
        "episode_id": f"{sep} · {episode_id}",
        "sep": sep,
        "episode": episode_id,
        "defect_class": flag.defect_class.name,
        "label": DEFECT_ID.get(flag.defect_class.name, flag.defect_class.label),
        "remedy": remedy,
        "remedy_code": flag.remedy.name,
        "actor": actor,
        # Rule 6. The span reached the flag verbatim or the pipeline dropped
        # it; printing it is what lets the koder check the finding against the
        # record without opening the record.
        "quote": flag.span.text,
        "doc_id": flag.span.doc_id,
        "score": round(flag.score, 4),
    }


def run_corrections(
    intake: IntakeResult,
    index: dict[str, tuple[Any, CodedClaim]],
    *,
    model_dir: Path = Path("models/cross_encoder"),
    use_llm: bool = False,
) -> CorrectionRun:
    """Run the pipeline over every matched episode and collect the deltas.

    A missing model layer degrades the run to rules-only and marks the whole
    output advisory (rule 8); it does not abort. A single episode raising is
    recorded and skipped, exactly as in `demo.py` — one bad record must not
    cost a hospital its whole batch.
    """
    from vitera.agent.loop import run_pipeline

    scorer = None
    try:
        from vitera.models.cross_encoder import CrossEncoderScorer

        scorer = CrossEncoderScorer.load(model_dir)
    except Exception:
        scorer = None

    llm = None
    if use_llm:
        from vitera.agent.boundary import LLMClient

        llm = LLMClient()

    grouper = Grouper()
    corrections: list[Correction] = []
    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    advisory = scorer is None

    for sep, episode_id in sorted(intake.matched.items(), key=lambda kv: kv[1]):
        ep, claim = index[sep]
        day = ep.discharge_day if ep.discharge_day is not None else ep.los_so_far
        try:
            result: PipelineResult = run_pipeline(
                RuleContext(ep, claim, day), scorer=scorer, llm=llm
            )
        except Exception as exc:
            errors.append(f"{episode_id}: {type(exc).__name__}: {exc}")
            continue
        if result.trace.degraded:
            advisory = True

        before = grouper.group_codes(
            claim.primary_dx, claim.secondary_dx, claim.procedures
        )
        money = money_view(grouper, claim, result)
        corrections.append(
            Correction(
                episode_id=episode_id,
                sep_number=sep,
                cbg_before=before.cbg_code,
                cbg_after=money["now"]["cbg_code"],
                biaya_before=before.tariff_idr,
                biaya_after=money["now"]["tariff_idr"],
                biaya_if_confirmed=money["if_confirmed"]["tariff_idr"],
                flags=len(result.decision.flags),
            )
        )
        # Collapse findings that would print identically.
        #
        # `Flag` carries no subject field, so two flags about two different
        # secondary codes that cite the same span are indistinguishable by the
        # time they reach paper. Printing both gives the koder two lines they
        # cannot act on differently. Adding the subject is a contract change
        # across every module and belongs to bucket 13; until then, identical
        # output is one line.
        seen: set[tuple[str, str]] = set()
        for f in result.decision.flags:
            item = _finding(episode_id, sep, f)
            key = (str(item["label"]), str(item["quote"]))
            if key in seen:
                continue
            seen.add(key)
            findings.append(item)

    return CorrectionRun(
        corrections=corrections, findings=findings, advisory=advisory, errors=errors
    )


def corrected_form(original: FPKForm, run: CorrectionRun) -> FPKForm:
    """The same batch, re-priced by the grouper.

    Every other field is copied unchanged. A corrected FPK that quietly
    rewrote the card number or the service month would be impossible for the
    koder to diff against the sheet in their hand.
    """
    by_sep = {c.sep_number: c for c in run.corrections}
    lines = tuple(
        (
            FPKLine(
                episode_id=ln.episode_id,
                nama=ln.nama,
                no_kartu=ln.no_kartu,
                sep_number=ln.sep_number,
                tanggal_masuk=ln.tanggal_masuk,
                tanggal_pulang=ln.tanggal_pulang,
                hari=ln.hari,
                cbg_code=by_sep[ln.sep_number].cbg_after,
                biaya_idr=by_sep[ln.sep_number].biaya_after,
                ungroupable_reason=ln.ungroupable_reason,
            )
            if ln.sep_number in by_sep
            else ln
        )
        for ln in original.lines
    )
    return FPKForm(
        cabang=original.cabang,
        nama_ppk=original.nama_ppk,
        kode_ppk=original.kode_ppk,
        nama_pengaju=original.nama_pengaju,
        nama_penderita=original.nama_penderita,
        no_kartu_peserta=original.no_kartu_peserta,
        alamat=original.alamat,
        telpon=original.telpon,
        bulan_pelayanan=original.bulan_pelayanan,
        peserta=original.peserta,
        tempat=original.tempat,
        tanggal=original.tanggal,
        penanggung_jawab=original.penanggung_jawab,
        lines=lines,
        jenis_penagihan=original.jenis_penagihan,
        jenis_pelayanan=original.jenis_pelayanan,
        uraian_biaya=original.uraian_biaya,
    )


def _summary_notes(run: CorrectionRun, intake: IntakeResult) -> list[dict[str, Any]]:
    """The lines that go above the findings, as pseudo-findings so the renderer
    stays one code path."""
    delta = run.total_after - run.total_before
    arah = "turun" if delta < 0 else "naik"
    notes: list[dict[str, Any]] = [
        {
            "episode_id": "RINGKASAN",
            "label": (
                f"Nilai diajukan {format_idr(run.total_before)} → "
                f"draf setelah pemeriksaan {format_idr(run.total_after)} "
                f"({arah} {format_idr(abs(delta))})"
            ),
            "remedy": "Angka dari grouper INA-CBG",
            "actor": "bukan dari model",
            "quote": (
                "Hanya kode yang didukung rekam medis yang dihitung pada "
                "jumlah di atas."
            ),
        }
    ]
    conditional = run.total_if_confirmed - run.total_after
    if conditional > 0:
        notes.append(
            {
                "episode_id": "BERSYARAT",
                "label": (
                    f"Berpotensi {format_idr(conditional)} lebih tinggi BILA "
                    "DPJP melengkapi dokumentasi komorbiditas"
                ),
                "remedy": "Tidak dimasukkan ke JUMLAH",
                "actor": "menunggu konfirmasi DPJP",
                "quote": (
                    "Angka bersyarat tidak pernah ikut ditotalkan pada formulir "
                    "yang diajukan."
                ),
            }
        )
    unread = [f for f in intake.failures if f.severity == "needs_human_read"]
    if unread:
        notes.append(
            {
                "episode_id": "PEMINDAIAN",
                "label": (
                    f"{len(unread)} nilai tidak terbaca yakin oleh OCR dan "
                    "belum diverifikasi manusia"
                ),
                "remedy": "Periksa lembar asli",
                "actor": "Petugas berkas",
                "quote": unread[0].detail,
            }
        )
    if run.advisory:
        notes.append(
            {
                "episode_id": "ADVISORY",
                "label": (
                    "Lapisan model tidak aktif; pemeriksaan ini berbasis aturan "
                    "saja dan tidak menjangkau seluruh kelas temuan"
                ),
                "remedy": "Jalankan ulang dengan model aktif",
                "actor": "Operator",
                "quote": "Hasil ditandai advisory sesuai aturan arsitektur 8.",
            }
        )
    return notes


def write_corrected_fpk(
    original: FPKForm,
    intake: IntakeResult,
    run: CorrectionRun,
    path: Path,
    *,
    signed_on: date | None = None,
) -> Path:
    """Render the draft. Stamped, unsigned, and not submitted anywhere."""
    _ = signed_on
    form = corrected_form(original, run)
    return render_fpk(
        form,
        path,
        stamp="DRAF",
        findings=_summary_notes(run, intake) + run.findings,
        provenance=intake.extracted.provenance(),
        sign_blocks=("Koder", "Verifikator internal"),
    )


__all__ = [
    "DEFECT_ID",
    "REMEDY_ID",
    "Correction",
    "CorrectionRun",
    "corrected_form",
    "run_corrections",
    "write_corrected_fpk",
]
