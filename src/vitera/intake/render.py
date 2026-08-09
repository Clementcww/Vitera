"""Rendering an `FPKForm` to PDF, in the layout of the real BPJS form.

The layout is copied from a submitted FPK so that the OCR path is tested
against the thing it will actually meet: the same field order, the same
`LABEL : value` colon convention, the same DIAJUKAN / DISETUJUI split with the
right-hand half left empty for BPJS to fill. An OCR system tuned on a form of
our own invention would prove nothing.

Two marks are drawn on every page and are not optional:

    SINTETIS   this is generated from synthetic episodes. A file that looks
               like a submitted claim and is not one should say so on its face,
               not in a README nobody opens.
    DRAF       on corrected output only. Rule 1 — the system drafts and stages,
               a human commits. The stamp and the empty signature block are
               what "a human commits" looks like on paper.

Nothing here computes money. `form.py` copied it from the grouper; this file
formats it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from vitera.intake.form import BULAN, FPKForm, FPKLine, format_idr

# Page geometry, points. A4 portrait, one outer box like the original.
PAGE_W, PAGE_H = 595.276, 841.89
BOX_L, BOX_R = 42.0, 553.0
BOX_TOP = 88.0  # measured from the top of the page, like every y in this file

SMALL = 6.6
BODY = 7.4
HEAD = 8.2

SYNTHETIC_NOTE = (
    "DOKUMEN SINTETIS — dihasilkan dari data uji Vitera. Bukan klaim sebenarnya."
)


def _fmt_tanggal(d: date) -> str:
    return f"{d.day:02d} {BULAN[d.month - 1].title()} {d.year}"


class _Sheet:
    """Thin top-down wrapper over a reportlab canvas.

    reportlab measures y from the bottom of the page and every coordinate in
    this file is more legible measured from the top, so the conversion lives in
    one place instead of in forty call sites.
    """

    def __init__(self, canvas: Any) -> None:
        self.c = canvas

    def text(
        self, x: float, y: float, s: str, *, bold: bool = False, size: float = BODY
    ) -> None:
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.drawString(x, PAGE_H - y, s)

    def centre(
        self, y: float, s: str, *, bold: bool = True, size: float = HEAD
    ) -> None:
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.drawCentredString((BOX_L + BOX_R) / 2, PAGE_H - y, s)

    def right(
        self, x: float, y: float, s: str, *, bold: bool = False, size: float = BODY
    ) -> None:
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.drawRightString(x, PAGE_H - y, s)

    def hline(self, y: float, x0: float = BOX_L, x1: float = BOX_R) -> None:
        self.c.setLineWidth(0.6)
        self.c.line(x0, PAGE_H - y, x1, PAGE_H - y)

    def vline(self, x: float, y0: float, y1: float) -> None:
        self.c.setLineWidth(0.6)
        self.c.line(x, PAGE_H - y0, x, PAGE_H - y1)

    def box(self, y0: float, y1: float, x0: float = BOX_L, x1: float = BOX_R) -> None:
        self.c.setLineWidth(0.8)
        self.c.rect(x0, PAGE_H - y1, x1 - x0, y1 - y0, stroke=1, fill=0)

    def field(self, x: float, y: float, label: str, value: str, gap: float) -> None:
        """`LABEL : value`, the convention the extractor anchors on."""
        self.text(x, y, label, bold=False)
        self.text(x + gap, y, f": {value}")


def _marks(sh: _Sheet, stamp: str | None, *, diagonal: bool = True) -> None:
    """The synthetic / draft marks.

    `diagonal=False` on data-dense sheets, and that is not an aesthetic choice.
    A rotated watermark is recognised by the OCR as one tall observation over
    whatever column it crosses; on the rincian annex it sat on KODE INA-CBG and
    took the entire column with it. The cover page has the whitespace to
    absorb it, the tables do not, so they get a corner label instead.
    """
    c = sh.c
    c.saveState()
    c.setFillGray(0.93)
    if diagonal:
        c.setFont("Helvetica-Bold", 46)
        c.translate(PAGE_W / 2, PAGE_H / 2)
        c.rotate(32)
        c.drawCentredString(0, 0, stamp or "SINTETIS")
    else:
        c.setFont("Helvetica-Bold", 11)
        c.setFillGray(0.72)
        c.drawRightString(BOX_R, PAGE_H - 40, stamp or "SINTETIS")
    c.restoreState()

    c.saveState()
    c.setFont("Helvetica-Oblique", 6.2)
    c.setFillGray(0.35)
    c.drawCentredString(PAGE_W / 2, 24, SYNTHETIC_NOTE)
    c.restoreState()


def _letterhead(sh: _Sheet) -> None:
    """Text only. The real form carries the BPJS mark; reproducing a national
    insurer's logo on a synthetic document is not something to do casually."""
    sh.text(BOX_L + 4, 48, "BPJS Kesehatan", bold=True, size=13)
    sh.text(BOX_L + 4, 58, "Badan Penyelenggara Jaminan Sosial", size=6)


def _header(sh: FPKForm, s: _Sheet, y: float) -> float:
    s.centre(y + 12, "FORMULIR PENGAJUAN KLAIM (FPK)")
    s.centre(y + 23, "BIAYA PELAYANAN KESEHATAN")
    s.centre(y + 34, f"BPJS KESEHATAN CABANG {sh.cabang}")
    y += 44
    s.hline(y)
    return y


def _petugas_block(s: _Sheet, y: float) -> float:
    """The strip the BPJS clerk fills by hand. Rendered empty, as submitted."""
    s.c.setFont("Helvetica-Oblique", SMALL)
    s.c.drawString(BOX_L + 6, PAGE_H - (y + 12), "Di isi ole Petugas BPJS")
    cols = (BOX_L + 6, 240.0, 400.0)
    rows = (
        ("TANGGAL MASUK", "TGL. TERIMA MPKP", "TGL. TERIMA KEU"),
        ("NO. REG MASUK", "NO. REG KLAIM MPKP", "NO. REG KLAIM KEU"),
    )
    for i, row in enumerate(rows):
        yy = y + 24 + i * 12
        for x, label in zip(cols, row, strict=True):
            s.text(x, yy, label, size=SMALL)
            s.text(x + 78, yy, ": ...............", size=SMALL)
    y += 42
    s.hline(y)
    return y


def _particulars(f: FPKForm, s: _Sheet, y: float) -> float:
    left = BOX_L + 6
    right = 318.0
    gap = 96.0
    rows_l = [
        ("JENIS PENAGIHAN", f.jenis_penagihan),
        ("JENIS PELAYANAN", f.jenis_pelayanan),
        ("NAMA PENGAJU", f.nama_pengaju),
        ("NAMA PENDERITA", f.nama_penderita),
        ("NO. KARTU PESERTA", f.no_kartu_peserta),
        ("ALAMAT", f.alamat[0] if f.alamat else "-"),
    ]
    rows_r = [
        ("NAMA PPK", f.nama_ppk),
        ("KODE PPK", f.kode_ppk),
        ("BLN/ THN PELAYANAN", f.bulan_pelayanan),
        ("PESERTA", f.peserta),
    ]
    for i, (label, value) in enumerate(rows_l):
        s.field(left, y + 14 + i * 15, label, value, gap)
    for i, (label, value) in enumerate(rows_r):
        s.field(right, y + 14 + i * 15, label, value, 88)

    if len(f.alamat) > 1:
        s.text(left + gap + 6, y + 14 + 6 * 15, f.alamat[1])
    s.field(left, y + 14 + 7 * 15, "TELPON/ HP", f.telpon, gap)
    y += 14 + 7 * 15 + 8
    s.hline(y)
    return y


def _cost_table(f: FPKForm, s: _Sheet, y: float) -> float:
    """DIAJUKAN on the left, DISETUJUI empty on the right, as submitted."""
    mid = 320.0
    s.c.setFont("Helvetica-Bold", SMALL)
    s.c.drawCentredString(
        (BOX_L + mid) / 2, PAGE_H - (y + 10), "DIAJUKAN (DIISI PENGAJU KLAIM)"
    )
    s.c.drawCentredString(
        (mid + BOX_R) / 2, PAGE_H - (y + 10), "DISETUJUI (DIISI BPJS KESEHATA)"
    )
    y += 14
    s.hline(y)

    # Column edges. The right half mirrors the left minus the NO column and
    # plus KODE AKUN, exactly as the printed form does.
    xs_l = [BOX_L, 64.0, 146.0, 196.0, 250.0, mid]
    xs_r = [mid, 368.0, 424.0, 486.0, BOX_R]
    head_top = y
    hdr = y + 10
    s.c.setFont("Helvetica-Bold", SMALL)
    s.c.drawCentredString((xs_l[0] + xs_l[1]) / 2, PAGE_H - hdr, "NO")
    s.c.drawCentredString((xs_l[1] + xs_l[2]) / 2, PAGE_H - hdr, "URAIAN BIAYA")
    s.c.drawCentredString((xs_l[2] + xs_l[5]) / 2, PAGE_H - hdr, "JUMLAH")
    s.c.drawCentredString((xs_r[0] + xs_r[1]) / 2, PAGE_H - hdr, "KODE")
    s.c.drawCentredString((xs_r[0] + xs_r[1]) / 2, PAGE_H - (hdr + 8), "AKUN")
    y += 12
    s.hline(y, xs_l[2], mid)

    sub = y + 10
    s.c.setFont("Helvetica-Bold", SMALL)
    for x0, x1, label in (
        (xs_l[2], xs_l[3], "KASUS"),
        (xs_l[3], xs_l[4], "HR/ TINDAKAN"),
        (xs_l[4], xs_l[5], "BIAYA(Rp)"),
        (xs_r[1], xs_r[2], "KASUS"),
        (xs_r[2], xs_r[3], "HR/ TINDAKAN"),
        (xs_r[3], xs_r[4], "BIAYA(Rp)"),
    ):
        s.c.drawCentredString((x0 + x1) / 2, PAGE_H - sub, label)
    y += 14
    s.hline(y)
    head_bot = y

    row_h = 14.0
    s.c.setFont("Helvetica", SMALL)
    s.c.drawCentredString((xs_l[0] + xs_l[1]) / 2, PAGE_H - (y + 10), "1")
    s.c.drawString(xs_l[1] + 6, PAGE_H - (y + 10), f.uraian_biaya)
    s.c.drawCentredString(
        (xs_l[2] + xs_l[3]) / 2, PAGE_H - (y + 10), str(f.jumlah_kasus)
    )
    s.c.drawCentredString(
        (xs_l[3] + xs_l[4]) / 2, PAGE_H - (y + 10), f"{f.jumlah_hari} HARI"
    )
    s.c.drawRightString(xs_l[5] - 6, PAGE_H - (y + 10), format_idr(f.jumlah_biaya))
    y += row_h
    s.hline(y)
    for _ in range(2):  # blank rows, as on the printed form
        y += row_h
        s.hline(y)

    s.c.setFont("Helvetica-Bold", SMALL)
    s.c.drawCentredString((xs_l[0] + xs_l[2]) / 2, PAGE_H - (y + 10), "JUMLAH")
    s.c.drawCentredString(
        (xs_l[2] + xs_l[3]) / 2, PAGE_H - (y + 10), str(f.jumlah_kasus)
    )
    s.c.drawCentredString(
        (xs_l[3] + xs_l[4]) / 2, PAGE_H - (y + 10), f"{f.jumlah_hari} HARI"
    )
    s.c.drawRightString(xs_l[5] - 6, PAGE_H - (y + 10), format_idr(f.jumlah_biaya))
    y += row_h
    s.hline(y)

    for x in xs_l[1:-1]:
        s.vline(x, head_top, y)
    for x in xs_r:
        s.vline(x, head_top, y)
    s.vline(xs_l[2], head_top, y)
    s.hline(head_bot, BOX_L, BOX_R)

    if f.ungroupable:
        y += 12
        s.text(
            BOX_L + 6,
            y,
            f"Catatan: {len(f.ungroupable)} kasus UNGROUPABLE, tidak ditotal "
            "(tarif tidak boleh diperkirakan).",
            size=SMALL,
        )
        y += 4
    return y


def _signatures(f: FPKForm, s: _Sheet, y: float, blocks: Sequence[str]) -> float:
    """Left: who signed and when. Right: the blanks a human still has to fill.

    On a corrected draft the right-hand blocks are the whole point — the form
    is unsubmittable until somebody puts a pen on them, which is rule 1
    expressed in the only way a paper workflow can express it.
    """
    dots = "................................."
    width = (BOX_R - 320.0) / max(1, len(blocks))
    y += 24
    s.text(BOX_L + 6, y, f"{f.tempat}, {_fmt_tanggal(f.tanggal)}")
    for i, label in enumerate(blocks):
        x = 320.0 + i * width
        s.text(x, y - 10, label, size=SMALL)
        s.text(x, y, dots, size=SMALL)
    y += 50
    s.text(BOX_L + 6, y, f.penanggung_jawab, bold=True)
    for i in range(len(blocks)):
        s.text(320.0 + i * width, y, f"({dots})", size=SMALL)
    y += 14
    return y


def render_fpk(
    form: FPKForm,
    path: Path,
    *,
    stamp: str | None = None,
    annex: bool = True,
    findings: Sequence[Any] = (),
    provenance: Sequence[tuple[str, str, float]] = (),
    sign_blocks: Sequence[str] = ("Pengaju klaim",),
) -> Path:
    """Write the FPK, and optionally the rincian annex, to `path`."""
    from reportlab.pdfgen import canvas as _canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    c = _canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"FPK {form.nama_ppk} {form.bulan_pelayanan}")
    s = _Sheet(c)

    _marks(s, stamp)
    _letterhead(s)

    y = BOX_TOP
    y = _header(form, s, y)
    y = _petugas_block(s, y)
    y = _particulars(form, s, y)
    y = _cost_table(form, s, y)
    y = _signatures(form, s, y, sign_blocks)
    s.box(BOX_TOP, y)

    y += 22
    s.text(BOX_L, y, "Distribusi :", bold=True, size=SMALL)
    for i, (a, b) in enumerate(
        (
            ("Lembaran Asli", "Unit Keuangan"),
            ("Lembaran ke-2", "Unit MPK"),
            ("Lembaran ke-3", "Pengaju Klaim"),
        )
    ):
        s.text(BOX_L + 28, y + 10 + i * 9, a, size=SMALL)
        s.text(BOX_L + 100, y + 10 + i * 9, f": {b}", size=SMALL)

    if annex:
        c.showPage()
        _annex(form, c, stamp)
    if findings or provenance:
        c.showPage()
        _appendix(c, stamp, findings, provenance)

    c.save()
    return path


BOTTOM = 792.0  # last usable y, measured from the top

# The rincian is the sheet the OCR has to read, so it is set larger than the
# cover form rather than smaller. At 7pt a 150 dpi scan leaves roughly fifteen
# pixels of glyph height and the recogniser starts dropping whole columns; the
# measured accuracy per scan profile in `results/intake_ocr.json` is what this
# number was chosen against, not appearance.
ANNEX_PT = 8.2
ANNEX_ROW = 13.5


ANNEX_COLS = [BOX_L, 66.0, 150.0, 232.0, 300.0, 348.0, 420.0, BOX_R]
ANNEX_HEADS = (
    "NO",
    "NO. SEP",
    "NAMA",
    "NO. KARTU",
    "TGL MASUK",
    "HARI",
    "KODE INA-CBG",
    "BIAYA(Rp)",
)


def _annex(form: FPKForm, c: Any, stamp: str | None) -> None:
    """Per-episode rincian: what the cover form's single row is made of.

    This page is also what makes the OCR path worth building. The cover form
    carries three numbers; the rincian carries the SEP number, the admission
    date and the card number per episode, which is what an administrative
    cross-check (D8) actually needs.
    """

    def new_page(part: int) -> tuple[_Sheet, float]:
        s = _Sheet(c)
        _marks(s, stamp, diagonal=False)
        s.centre(60, f"RINCIAN KLAIM — {form.nama_ppk}", size=10)
        s.centre(
            72,
            f"{form.bulan_pelayanan}   ·   KODE PPK {form.kode_ppk}"
            + (f"   ·   hal. {part}" if part > 1 else ""),
            bold=False,
            size=7,
        )
        y = 92.0
        s.hline(y)
        y += 12
        s.c.setFont("Helvetica-Bold", ANNEX_PT)
        for i, h in enumerate(ANNEX_HEADS):
            if i == len(ANNEX_HEADS) - 1:
                s.c.drawRightString(BOX_R - 4, PAGE_H - y, h)
            else:
                s.c.drawString(ANNEX_COLS[i] + 4, PAGE_H - y, h)
        y += 4
        s.hline(y)
        return s, y

    part = 1
    s, y = new_page(part)
    for i, ln in enumerate(form.lines, start=1):
        if y > BOTTOM - 40:
            s.hline(y + 4)
            c.showPage()
            part += 1
            s, y = new_page(part)
        y += ANNEX_ROW
        s.c.setFont("Helvetica", ANNEX_PT)
        cells = (
            str(i),
            ln.sep_number,
            ln.nama,
            ln.no_kartu,
            ln.tanggal_masuk.isoformat(),
            # The unit is printed, as it is in the cover form's `311 HARI`.
            # A bare one- or two-digit number surrounded by whitespace is the
            # single least reliable thing on the sheet for a recogniser to
            # find; the same digits followed by a word are read every time.
            f"{ln.hari} hari",
            ln.cbg_code or "UNGROUPABLE",
        )
        for j, v in enumerate(cells):
            s.c.drawString(ANNEX_COLS[j] + 4, PAGE_H - y, v)
        s.c.drawRightString(BOX_R - 4, PAGE_H - y, format_idr(ln.biaya_idr))
    y += 4
    s.hline(y)
    y += ANNEX_ROW
    s.c.setFont("Helvetica-Bold", ANNEX_PT)
    s.c.drawString(ANNEX_COLS[1] + 4, PAGE_H - y, "JUMLAH")
    s.c.drawString(ANNEX_COLS[5] + 4, PAGE_H - y, str(form.jumlah_hari))
    s.c.drawRightString(BOX_R - 4, PAGE_H - y, format_idr(form.jumlah_biaya))
    y += 4
    s.hline(y)


def _appendix(
    c: Any,
    stamp: str | None,
    findings: Sequence[Any],
    provenance: Sequence[tuple[str, str, float]],
) -> None:
    """Findings and OCR provenance, on their own sheets.

    Kept off the rincian because the two are read by different people at
    different moments: the rincian is checked against E-Klaim, the findings are
    worked through case by case.
    """
    s = _Sheet(c)
    _marks(s, stamp, diagonal=False)
    y = 60.0
    if findings:
        s.text(BOX_L, y, "TEMUAN PEMERIKSAAN INTERNAL (DRAF)", bold=True, size=9)
        y += 6
        s.hline(y)
        for f in findings:
            if y > BOTTOM - 40:
                c.showPage()
                s = _Sheet(c)
                _marks(s, stamp, diagonal=False)
                y = 60.0
            y += 14
            s.text(BOX_L, y, f"{f['episode_id']}   {f['label']}", bold=True, size=SMALL)
            y += 9
            s.text(BOX_L + 10, y, f"Tindakan: {f['remedy']} — {f['actor']}", size=SMALL)
            y += 9
            s.text(
                BOX_L + 10,
                y,
                f"Kutipan rekam medis: “{str(f['quote'])[:120]}”",
                size=SMALL,
            )
            y += 4
    if provenance:
        y += 24
        if y > BOTTOM - 80:
            c.showPage()
            s = _Sheet(c)
            _marks(s, stamp, diagonal=False)
            y = 60.0
        s.text(BOX_L, y, "ASAL DATA HASIL PEMINDAIAN (OCR)", bold=True, size=9)
        y += 9
        s.text(
            BOX_L,
            y,
            "Nilai di bawah ini dibaca mesin dari lembar pindaian, bukan "
            "diketik ulang. Angka terakhir adalah keyakinan mesin (0-1).",
            size=SMALL,
        )
        y += 5
        s.hline(y)
        for field, value, conf in provenance:
            if y > BOTTOM - 20:
                c.showPage()
                s = _Sheet(c)
                _marks(s, stamp, diagonal=False)
                y = 60.0
            y += 11
            s.text(BOX_L, y, field, size=SMALL)
            s.text(BOX_L + 150, y, str(value)[:56], size=SMALL)
            s.right(BOX_R, y, f"{conf:.2f}", size=SMALL)


def forms_for_cohort(
    pairs: list[tuple[Any, Any]],
    *,
    site_meta: dict[str, dict[str, str]] | None = None,
) -> list[FPKForm]:
    """One FPK per PPK per service month, largest batch first.

    Both halves of that key are regulatory, not stylistic: an FPK covers one
    facility and one BLN/THN PELAYANAN. Splitting only by site would produce a
    form whose header month contradicts most of its own rincian rows.
    """
    from vitera.intake.form import build_form

    batches: dict[tuple[str, str], list[tuple[Any, Any]]] = {}
    for ep, claim in pairs:
        month = claim.admission_date_claimed.strftime("%Y-%m")
        batches.setdefault((ep.site_id, month), []).append((ep, claim))
    meta = site_meta or {}
    forms = [
        build_form(v, site_meta=meta.get(k[0], {})) for k, v in sorted(batches.items())
    ]
    return sorted(forms, key=lambda f: -f.jumlah_kasus)


__all__ = ["FPKLine", "forms_for_cohort", "render_fpk"]
