"""The FPK as a data structure.

`FPKForm` is what gets rendered to paper and what gets read back off paper, so
it is deliberately the *administrative* view of a batch and nothing more: who
submitted, for which month, how many cases, how many bed-days, how much money.
No clinical content lives here.

Two properties matter more than the rest.

**Rule 7 has no exceptions on the form either.** `FPKLine.biaya_idr` is copied
from a `GroupResult`; nothing in this module multiplies, estimates or
apportions. An episode the grouper could not group carries `biaya_idr = None`,
is excluded from the total, and is *counted on the form* as ungroupable. A
printed total that quietly absorbed an estimate would be the exact failure
The design brief names.

**Identity is synthesised here, not in the episode.** The corpus has no patient
names because nothing upstream of this file needs one; an FPK does. Names, card
numbers and addresses are generated deterministically from `episode_id` from a
small fixed pool, are obviously synthetic, and exist so the OCR path has real
identifier-shaped strings to read — and so the pseudonymiser has something to
strip before any of it reaches a model.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from vitera.contracts import Episode, GroupResult
from vitera.generator.defects import CodedClaim
from vitera.grouper.grouper import Grouper

BULAN = (
    "JANUARI",
    "FEBRUARI",
    "MARET",
    "APRIL",
    "MEI",
    "JUNI",
    "JULI",
    "AGUSTUS",
    "SEPTEMBER",
    "OKTOBER",
    "NOVEMBER",
    "DESEMBER",
)

# Obviously-synthetic name pool. Common Indonesian given names, no surnames, so
# nothing here collides with a plausible real individual.
_DEPAN = (
    "Siti",
    "Budi",
    "Ratna",
    "Agus",
    "Dewi",
    "Hendra",
    "Yanti",
    "Slamet",
    "Nurul",
    "Bambang",
    "Indah",
    "Joko",
    "Sri",
    "Rudi",
    "Wati",
    "Eko",
)
_BELAKANG = (
    "Wijaya",
    "Santoso",
    "Pratama",
    "Lestari",
    "Kusuma",
    "Hartono",
    "Maulana",
    "Anggraini",
)
_JALAN = ("Melati", "Kenanga", "Cempaka", "Merdeka", "Diponegoro", "Sudirman")

# BPJS branch cities, one per region present in config/sites.yaml. Real place
# names; the mapping is ours and is not authoritative.
_CABANG = {
    "Jawa": "BANDUNG",
    "Sumatera": "MEDAN",
    "Sulawesi": "MAKASSAR",
    "Kalimantan": "BANJARMASIN",
    "NTT": "KUPANG",
}


def _rng(episode_id: str) -> random.Random:
    """Identity must be stable across runs or the OCR round-trip test is not a
    test. Seeded from the id alone, never from process state."""
    return random.Random(int.from_bytes(episode_id.encode(), "big") % (2**31 - 1))


@dataclass(frozen=True, slots=True)
class Identity:
    """Synthetic administrative identity for one episode. Not clinical data."""

    nama: str
    no_kartu: str
    alamat: str
    kabupaten: str

    @staticmethod
    def of(episode_id: str) -> Identity:
        r = _rng(episode_id)
        return Identity(
            nama=f"{r.choice(_DEPAN)} {r.choice(_BELAKANG)}",
            # 13 digits, the BPJS card length. Prefix 000 as on the real card.
            no_kartu=f"000{r.randrange(10**9, 10**10)}",
            alamat=f"JL. {r.choice(_JALAN).upper()} NO. {r.randrange(1, 120)}",
            kabupaten=f"KEC. {r.choice(_JALAN).upper()}",
        )


@dataclass(frozen=True, slots=True)
class FPKLine:
    """One episode on the rincian annex.

    `biaya_idr is None` means UNGROUPABLE. It is not zero, and it is not an
    estimate; the annex prints the reason.
    """

    episode_id: str
    nama: str
    no_kartu: str
    sep_number: str
    tanggal_masuk: date
    tanggal_pulang: date | None
    hari: int
    cbg_code: str | None
    biaya_idr: int | None
    ungroupable_reason: str | None = None

    @staticmethod
    def build(ep: Episode, claim: CodedClaim, group: GroupResult) -> FPKLine:
        ident = Identity.of(ep.episode_id)
        los = ep.discharge_day if ep.discharge_day is not None else ep.los_so_far
        return FPKLine(
            episode_id=ep.episode_id,
            nama=ident.nama,
            no_kartu=ident.no_kartu,
            sep_number=claim.sep_number,
            tanggal_masuk=claim.admission_date_claimed,
            tanggal_pulang=(
                ep.admission_date + timedelta(days=ep.discharge_day)
                if ep.discharge_day is not None
                else None
            ),
            # A same-day admission still consumes one bed-day on the FPK.
            hari=max(1, los),
            cbg_code=group.cbg_code,
            biaya_idr=group.tariff_idr,
            ungroupable_reason=group.ungroupable_reason,
        )


@dataclass(frozen=True, slots=True)
class FPKForm:
    """The cover form for a batch, plus the rincian it summarises."""

    cabang: str
    nama_ppk: str
    kode_ppk: str
    nama_pengaju: str
    nama_penderita: str
    no_kartu_peserta: str
    alamat: tuple[str, ...]
    telpon: str
    bulan_pelayanan: str
    peserta: str
    tempat: str
    tanggal: date
    penanggung_jawab: str
    lines: tuple[FPKLine, ...]
    jenis_penagihan: str = "KOLEKTIF"
    # RITL, not the RITP on an FKTP form: our scope is hospital inpatient
    # under INA-CBG, which is tingkat lanjutan by definition.
    jenis_pelayanan: str = "RITL (RAWAT INAP TINGKAT LANJUTAN)"
    uraian_biaya: str = "RITL"

    @property
    def jumlah_kasus(self) -> int:
        return len(self.lines)

    @property
    def jumlah_hari(self) -> int:
        return sum(x.hari for x in self.lines)

    @property
    def jumlah_biaya(self) -> int:
        """Sum of grouper tariffs over groupable lines only."""
        return sum(x.biaya_idr or 0 for x in self.lines)

    @property
    def ungroupable(self) -> tuple[FPKLine, ...]:
        return tuple(x for x in self.lines if x.biaya_idr is None)


def build_form(
    pairs: list[tuple[Episode, CodedClaim]],
    *,
    grouper: Grouper | None = None,
    site_meta: dict[str, str] | None = None,
    signed_on: date | None = None,
) -> FPKForm:
    """Assemble one FPK for one site's batch.

    `pairs` must be from a single site; an FPK is per PPK, per month, and
    mixing sites would produce a form no hospital could submit. The caller
    groups the cohort — see `render.forms_for_cohort`.
    """
    if not pairs:
        raise ValueError("an FPK needs at least one episode")
    grouper = grouper or Grouper()

    site_id = pairs[0][0].site_id
    if any(ep.site_id != site_id for ep, _ in pairs):
        raise ValueError("one FPK covers one PPK; split the cohort by site first")

    lines = tuple(
        FPKLine.build(
            ep,
            claim,
            grouper.group_codes(claim.primary_dx, claim.secondary_dx, claim.procedures),
        )
        for ep, claim in sorted(pairs, key=lambda p: p[0].episode_id)
    )

    meta = site_meta or {}
    region = meta.get("region", "Jawa")
    first = lines[0]
    ident = Identity.of(first.episode_id)
    # Service month is the month most of the batch was admitted in.
    months = [x.tanggal_masuk for x in lines]
    ref_month = max(set(months), key=months.count)
    r = _rng(site_id)

    return FPKForm(
        cabang=_CABANG.get(region, "BANDUNG"),
        nama_ppk=f"RS SINTETIS {site_id}",
        # Imitates the BPJS kode PPK shape (4 digits, facility letter, 3
        # digits). R for rumah sakit. Not an authoritative code.
        kode_ppk=f"{r.randrange(1000, 9999)}R{r.randrange(1, 999):03d}",
        nama_pengaju=f"RS SINTETIS {site_id}",
        nama_penderita=f"{first.nama} dkk",
        no_kartu_peserta=first.no_kartu,
        alamat=(ident.alamat + ",", f"{ident.kabupaten}, {region.upper()}"),
        telpon="-",
        bulan_pelayanan=f"{BULAN[ref_month.month - 1]}/ {ref_month.year}",
        peserta="P",
        tempat=_CABANG.get(region, "BANDUNG").title(),
        tanggal=signed_on or (max(months) + timedelta(days=30)),
        penanggung_jawab="TEUKU DIAN, SE",
        lines=lines,
    )


def format_idr(value: int | None) -> str:
    """The form's money format: `Rp 12.600.000,-`, or a dash for UNGROUPABLE."""
    if value is None:
        return "—"
    return "Rp " + f"{value:,}".replace(",", ".") + ",-"


__all__ = ["BULAN", "FPKForm", "FPKLine", "Identity", "build_form", "format_idr"]
