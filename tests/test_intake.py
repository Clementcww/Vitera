"""Paper intake — bucket 14.

The tests worth having here are not "does reportlab draw a rectangle". They
are the four claims the package makes that would be embarrassing to get wrong:

  - the FPK never prints a tariff the grouper did not produce, and never
    estimates one for an UNGROUPABLE episode (rule 7);
  - the extractor reports what it could not read rather than guessing;
  - the gate stops an illegible or out-of-scope sheet before anything runs
    (rule 4);
  - an OCR misread is never dressed up as a claim defect.

The OCR engine itself is not exercised — that needs an engine and an image, and
it is measured, not asserted, by `make intake-eval`. Everything below runs on
synthetic `Observation`s, so the suite stays fast and platform-independent.
"""

from __future__ import annotations

from datetime import date

import pytest

from vitera.contracts import GroupResult
from vitera.generator.defects import CodedClaim
from vitera.intake import extract as ex
from vitera.intake import validate as val
from vitera.intake.form import FPKLine, Identity, build_form, format_idr
from vitera.intake.scan import Observation, Page


def obs(
    text: str, x0: float, y: float, *, conf: float = 1.0, w: float = 0.1
) -> Observation:
    """One recognised line, at a normalised position, 0.012 tall."""
    return Observation(text=text, confidence=conf, x0=x0, y0=y, x1=x0 + w, y1=y + 0.012)


# --- form and money --------------------------------------------------------


def test_ungroupable_line_carries_no_tariff_and_is_excluded_from_the_total() -> None:
    """Rule 7. `Never estimate a tariff when the grouper returns UNGROUPABLE`."""
    good = FPKLine(
        "EP1", "A", "0001", "SEP1", date(2026, 3, 1), None, 3, "K-1-20-I", 5_000_000
    )
    bad = FPKLine(
        "EP2",
        "B",
        "0002",
        "SEP2",
        date(2026, 3, 2),
        None,
        4,
        None,
        None,
        "diagnosis utama tidak dikenali",
    )
    from vitera.intake.form import FPKForm

    f = FPKForm(
        cabang="BANDUNG",
        nama_ppk="RS SINTETIS RS001",
        kode_ppk="1234R001",
        nama_pengaju="RS SINTETIS RS001",
        nama_penderita="A dkk",
        no_kartu_peserta="0001",
        alamat=("JL. X",),
        telpon="-",
        bulan_pelayanan="MARET/ 2026",
        peserta="P",
        tempat="Bandung",
        tanggal=date(2026, 4, 1),
        penanggung_jawab="X",
        lines=(good, bad),
    )
    assert f.jumlah_kasus == 2
    assert f.jumlah_biaya == 5_000_000  # the ungroupable line contributes nothing
    assert len(f.ungroupable) == 1
    assert format_idr(None) == "—"
    assert format_idr(5_000_000) == "Rp 5.000.000,-"


def test_form_money_comes_from_the_grouper() -> None:
    """Every rupiah on the sheet is a `GroupResult` field, copied."""
    ep = _episode("EP1", "RS001")
    claim = _claim("EP1", "SEP000001")
    group = GroupResult(cbg_code="K-1-20-II", severity=2, tariff_idr=7_650_000)
    line = FPKLine.build(ep, claim, group)
    assert line.biaya_idr == group.tariff_idr
    assert line.cbg_code == group.cbg_code


def test_identity_is_deterministic_from_the_episode_id() -> None:
    """The OCR round trip is only a test if the identity does not move."""
    a, b = Identity.of("EP000123"), Identity.of("EP000123")
    assert a == b
    assert len(a.no_kartu) == 13 and a.no_kartu.isdigit()
    assert Identity.of("EP000124") != a


def test_one_fpk_covers_one_ppk() -> None:
    with pytest.raises(ValueError, match="one PPK"):
        build_form(
            [
                (_episode("EP1", "RS001"), _claim("EP1", "SEP1")),
                (_episode("EP2", "RS002"), _claim("EP2", "SEP2")),
            ]
        )


# --- extraction ------------------------------------------------------------


def test_label_anchoring_stops_at_the_next_label() -> None:
    """The two-column layout: `JENIS PENAGIHAN` must not swallow `NAMA PPK`."""
    page = Page(
        0,
        "test",
        (
            obs("JENIS PENAGIHAN", 0.07, 0.20, w=0.12),
            obs(": KOLEKTIF", 0.23, 0.20, w=0.07),
            obs("NAMA PPK", 0.52, 0.201, w=0.07),
            obs(": RS SINTETIS RS009", 0.67, 0.201, w=0.13),
        ),
    )
    fields, _ = ex.extract_header(page)
    assert fields["jenis_penagihan"].value == "KOLEKTIF"
    assert fields["nama_ppk"].value == "RS SINTETIS RS009"


def test_label_and_value_in_one_observation() -> None:
    """The recogniser merges them whenever the printed gap is small."""
    page = Page(0, "test", (obs("BLN/ THN PELAYANAN : MARET/ 2026", 0.5, 0.24, w=0.3),))
    fields, _ = ex.extract_header(page)
    assert fields["bulan_pelayanan"].value == "MARET/ 2026"


def test_missing_field_is_reported_not_invented() -> None:
    page = Page(0, "test", (obs("NAMA PPK", 0.5, 0.2),))
    fields, missing = ex.extract_header(page)
    assert "kode_ppk" in missing
    assert "kode_ppk" not in fields


def test_rows_survive_a_skewed_scan() -> None:
    """A sheet a degree off square drifts vertically across the page.

    Banding compares each observation to the last one accepted rather than to
    the row's first, so the drift per step stays small. Without that the row
    splits in half and every column past the middle is lost.
    """
    drift = 0.008  # more than a line height, less than a row pitch
    page = Page(
        1,
        "test",
        (
            obs("1", 0.07, 0.20),
            obs("SEP000224", 0.11, 0.2015, w=0.07),
            obs("Joko Anggraini", 0.25, 0.203, w=0.09),
            obs("0003036079620", 0.39, 0.2045, w=0.10),
            obs("2026-03-02 14 hari", 0.50, 0.206, w=0.11),
            obs("I-4-15-I", 0.70, 0.20 + drift, w=0.06),
            obs("Rp 12.400.000,-", 0.83, 0.209, w=0.10),
        ),
    )
    (line,) = ex.extract_lines([page])
    assert line.sep_number == "SEP000224"
    assert line.no_kartu == "0003036079620"
    assert line.tanggal_masuk == date(2026, 3, 2)
    assert line.hari == 14
    assert line.cbg_code == "I-4-15-I"
    assert line.biaya_idr == 12_400_000


def test_ocr_digit_confusion_is_repaired_only_where_the_format_is_numeric() -> None:
    page = Page(
        1,
        "test",
        (
            obs("SEPOO1400", 0.11, 0.20, w=0.07),
            obs("Eko Wijaya", 0.25, 0.201, w=0.08),
            obs("00023802516l3", 0.39, 0.202, w=0.10),
            obs("2026-03-30 10 hari", 0.50, 0.203, w=0.11),
            obs("1-4-15-1", 0.70, 0.204, w=0.06),
            obs("Rp 20.540.000,-", 0.83, 0.205, w=0.10),
        ),
    )
    (line,) = ex.extract_lines([page])
    assert line.sep_number == "SEP001400"
    assert line.no_kartu == "0002380251613"
    # Both ends of a CBG code are letters by construction, so the digits the
    # recogniser produced there map back rather than being taken literally.
    assert line.cbg_code == "I-4-15-I"


def test_hari_is_none_rather_than_the_cbg_middle_digit() -> None:
    """When the day count is lost, `None` is the truthful answer.

    The bounded window exists for exactly this row: an unbounded search runs
    into the CBG code and reports its middle digit as a length of stay.
    """
    page = Page(
        1,
        "test",
        (
            obs("SEP000656", 0.11, 0.20, w=0.07),
            obs("Dewi Pratama", 0.25, 0.201, w=0.08),
            obs("0009932916394", 0.39, 0.202, w=0.10),
            obs("2026-03-27", 0.50, 0.203, w=0.08),
            obs("E-4-10-I", 0.70, 0.204, w=0.06),
            obs("Rp 5.800.000,-", 0.83, 0.205, w=0.10),
        ),
    )
    (line,) = ex.extract_lines([page])
    assert line.hari is None
    assert line.cbg_code == "E-4-10-I"


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("Rp 441.985.000,-", 441_985_000),
        ("Rp 5.000.000,-", 5_000_000),
        ("Rp0", 0),
        ("—", None),
        ("", None),
    ],
)
def test_parse_idr(text: str, want: int | None) -> None:
    assert ex.parse_idr(text) == want


# --- the gate --------------------------------------------------------------


def _extracted(**kw: object) -> ex.ExtractedFPK:
    fields = {
        name: ex.FieldRead(name, str(value), 1.0, 1.0, 0, (0.0, 0.0, 0.1, 0.1))
        for name, value in {
            "nama_ppk": "RS SINTETIS RS009",
            "kode_ppk": "3483R223",
            "bulan_pelayanan": "MARET/ 2026",
            "jenis_pelayanan": "RITL (RAWAT INAP TINGKAT LANJUTAN)",
        }.items()
    }
    line = ex.LineRead(
        1,
        "SEP000001",
        "A",
        "0001234567890",
        date(2026, 3, 1),
        3,
        "K-1-20-I",
        5_000_000,
        1.0,
    )
    x = ex.ExtractedFPK(
        fields=fields,
        lines=[line],
        totals={"kasus": 1, "hari": 3, "biaya_idr": 5_000_000},
        engine="test",
        pages=2,
    )
    for k, v in kw.items():
        setattr(x, k, v)
    return x


def test_gate_passes_a_clean_sheet() -> None:
    result = val.validate(_extracted())
    assert result.passed
    assert not result.blocking


def test_gate_blocks_when_the_printed_total_disagrees_with_the_rows() -> None:
    x = _extracted()
    x.totals["biaya_idr"] = 9_999_999
    result = val.validate(x)
    assert not result.passed
    assert any(f.check == "biaya_mismatch" for f in result.blocking)


def test_gate_blocks_an_out_of_scope_form() -> None:
    """An FKTP RITP form is out of scope by design, and says so."""
    x = _extracted()
    x.fields["jenis_pelayanan"] = ex.FieldRead(
        "jenis_pelayanan",
        "RITP (RAWAT INAP TINGKAT PERTAMA)",
        1.0,
        1.0,
        0,
        (0.0, 0.0, 0.1, 0.1),
    )
    result = val.validate(x)
    assert not result.passed
    assert any(f.check == "out_of_scope" for f in result.blocking)


def test_gate_blocks_a_required_field_it_could_not_read() -> None:
    x = _extracted()
    del x.fields["kode_ppk"]
    result = val.validate(x)
    assert not result.passed
    assert any(f.check == "field_missing" for f in result.blocking)


def test_reconciliation_never_runs_on_a_sheet_the_gate_stopped() -> None:
    """Rule 4: no downstream work on a record that failed a deterministic check."""
    x = _extracted()
    x.totals["kasus"] = 99
    result = val.validate(x, index={})
    assert not result.passed
    assert result.matched == {}


def test_unreadable_tariff_is_a_read_failure_not_a_claim_finding() -> None:
    """The distinction the whole module exists to keep.

    A row whose tariff did not parse cannot produce a tariff mismatch; it
    produces `needs_human_read`. Reporting the first would put an OCR bug in
    front of a koder wearing the clothes of a claim defect.
    """
    x = _extracted()
    x.lines = [
        ex.LineRead(
            1, "SEP000001", "A", "0001234567890", date(2026, 3, 1), 3, None, None, 1.0
        )
    ]
    x.totals = {"kasus": 1, "hari": 3, "biaya_idr": None}
    index = {"SEP000001": (_episode("EP1", "RS009"), _claim("EP1", "SEP000001"))}
    failures, matched, _ = val.reconcile(x, index)
    kinds = {f.check: f.severity for f in failures}
    assert kinds.get("tariff_unreadable") == "needs_human_read"
    assert "tariff_mismatch" not in kinds
    assert matched == {"SEP000001": "EP1"}


def test_one_digit_card_difference_is_a_read_failure_not_a_d8_candidate() -> None:
    ep = _episode("EP1", "RS009")
    real = Identity.of("EP1").no_kartu
    near = real[:3] + ("0" if real[3] != "0" else "1") + real[4:]
    x = _extracted()
    x.lines = [
        ex.LineRead(
            1, "SEP000001", "A", near, date(2026, 3, 1), 3, "K-1-20-I", 5_000_000, 1.0
        )
    ]
    failures, _, _ = val.reconcile(x, {"SEP000001": (ep, _claim("EP1", "SEP000001"))})
    mismatch = [f for f in failures if f.check == "kartu_mismatch"]
    assert mismatch and mismatch[0].severity == "needs_human_read"


def test_an_sep_the_hospital_does_not_hold_blocks_the_batch() -> None:
    failures, _, unmatched = val.reconcile(_extracted(), {})
    assert unmatched == ["SEP000001"]
    assert any(
        f.check == "sep_not_found" and f.severity == "blocking" for f in failures
    )


# --- fixtures --------------------------------------------------------------


def _episode(episode_id: str, site_id: str):  # type: ignore[no-untyped-def]
    from vitera.contracts import ClinicalText, Document, Episode

    return Episode(
        episode_id=episode_id,
        site_id=site_id,
        admission_date=date(2026, 3, 1),
        primary_dx="K35.8",
        secondary_dx=(),
        procedures=(),
        events=(),
        documents=(Document("resume_medis", 3, ClinicalText("Diagnosis utama.")),),
        discharge_day=3,
    )


def _claim(episode_id: str, sep: str) -> CodedClaim:
    return CodedClaim(
        episode_id=episode_id,
        primary_dx="K35.8",
        secondary_dx=(),
        procedures=(),
        documents_present=("resume_medis",),
        sep_number=sep,
        admission_date_claimed=date(2026, 3, 1),
    )
