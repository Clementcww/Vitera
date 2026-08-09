"""Observations to fields. Deterministic, and readable in one screen per rule.

`scan.py` says *where the ink is*. This says *what it means*, and it does so
with anchored geometry and regular expressions — no model, no LLM, nothing
learned. That is not conservatism for its own sake:

  - architectural rule 2 keeps clinical determination out of the LLM, and an
    OCR field feeding the grouper and the D8 rule is upstream of every
    determination the system makes. A hallucinated SEP number would propagate
    into a claim.
  - a wrong value here has to be attributable to either a bad *read* or a bad
    *rule*, and you can only tell the two apart if the rule is inspectable.

The anchoring works the way a person reads the form: find the label, then take
what sits on the same printed line to its right, stopping at the next label.
That last clause is what keeps `JENIS PENAGIHAN` from swallowing `NAMA PPK`
across the two-column layout, without hard-coding a single x coordinate — so a
form photographed at a slight angle, or a slightly different print run, still
parses.

Every field carries the confidence and the bounding box it came from. A field
the extractor could not find is `None` and is listed in `missing`; it is never
guessed and never defaulted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher

from vitera.intake.scan import Observation, Page

# --- normalisation ---------------------------------------------------------

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def norm(text: str) -> str:
    """Uppercase, alphanumerics only.

    Absorbs the OCR noise that does not change meaning: spacing around the
    slash in `BLN/ THN`, the stray full stop in `NO . SEP`, and the mixed-script
    substitutions Vision makes on all-caps Indonesian (`MPKP` read with a
    Cyrillic Р). What it deliberately does not absorb is a wrong letter, which
    is what the similarity threshold is for.
    """
    return _NON_ALNUM.sub("", text.upper())


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


# --- field specifications --------------------------------------------------


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    labels: tuple[str, ...]
    page: int = 0


HEADER_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("cabang", ("BPJS KESEHATAN CABANG",)),
    FieldSpec("jenis_penagihan", ("JENIS PENAGIHAN",)),
    FieldSpec("jenis_pelayanan", ("JENIS PELAYANAN",)),
    FieldSpec("nama_pengaju", ("NAMA PENGAJU",)),
    FieldSpec("nama_penderita", ("NAMA PENDERITA",)),
    FieldSpec("no_kartu_peserta", ("NO. KARTU PESERTA",)),
    FieldSpec("alamat", ("ALAMAT",)),
    FieldSpec("telpon", ("TELPON/ HP", "TELPON/HP")),
    FieldSpec("nama_ppk", ("NAMA PPK",)),
    FieldSpec("kode_ppk", ("KODE PPK",)),
    FieldSpec("bulan_pelayanan", ("BLN/ THN PELAYANAN", "BLN/THN PELAYANAN")),
    FieldSpec("peserta", ("PESERTA",)),
)

# Anything that is a label somewhere on the form terminates another label's
# value. Including the BPJS-clerk strip matters: those labels sit in the same
# horizontal bands as nothing else, but a skewed scan can drift a line.
_TERMINATORS = tuple(
    norm(x)
    for spec in HEADER_FIELDS
    for x in spec.labels
    if spec.name not in ("cabang",)
) + tuple(
    norm(x)
    for x in (
        "TANGGAL MASUK",
        "NO. REG MASUK",
        "TGL. TERIMA MPKP",
        "NO. REG KLAIM MPKP",
        "TGL. TERIMA KEU",
        "NO. REG KLAIM KEU",
        "KASUS",
        "HR/ TINDAKAN",
        "BIAYA(Rp)",
        "KODE AKUN",
        "JUMLAH",
        "URAIAN BIAYA",
    )
)

LABEL_MATCH = 0.86  # anchor similarity floor; below this the field is missing


# --- results ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FieldRead:
    """One extracted value and everything needed to audit it."""

    name: str
    value: str
    confidence: float
    anchor_similarity: float
    page: int
    bbox: tuple[float, float, float, float]

    @property
    def suspect(self) -> bool:
        return self.confidence < 0.5 or self.anchor_similarity < 0.95


@dataclass(frozen=True, slots=True)
class LineRead:
    """One rincian row, as read. Every value may be None — nothing is guessed."""

    index: int
    sep_number: str | None
    nama: str | None
    no_kartu: str | None
    tanggal_masuk: date | None
    hari: int | None
    cbg_code: str | None
    biaya_idr: int | None
    confidence: float


@dataclass
class ExtractedFPK:
    fields: dict[str, FieldRead] = field(default_factory=dict)
    lines: list[LineRead] = field(default_factory=list)
    totals: dict[str, int | None] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    engine: str = ""
    pages: int = 0

    def get(self, name: str) -> str | None:
        f = self.fields.get(name)
        return f.value if f else None

    @property
    def mean_confidence(self) -> float:
        vals = [f.confidence for f in self.fields.values()]
        return sum(vals) / len(vals) if vals else 0.0

    def provenance(self) -> list[tuple[str, str, float]]:
        return [(k, v.value, v.confidence) for k, v in sorted(self.fields.items())]


# --- header extraction -----------------------------------------------------


def _is_terminator(text: str) -> bool:
    n = norm(text).lstrip(":")
    if not n:
        return False
    return any(similar(n[: len(t)], t) >= LABEL_MATCH for t in _TERMINATORS if t)


def _find_anchor(
    obs: list[Observation], labels: tuple[str, ...]
) -> tuple[int, float, int]:
    """Best anchor index, its similarity, and how many characters of the
    observation the label consumed.

    Matching is on a prefix so that an observation which ran the label and the
    value together — Vision does this whenever the printed gap is small, e.g.
    `BLN/ THN PELAYANAN : MARET/ 2026` — still anchors, and the consumed length
    tells the caller where the value starts inside it.
    """
    best_i, best_score, best_len = -1, 0.0, 0
    for i, o in enumerate(obs):
        n = norm(o.text)
        for label in labels:
            t = norm(label)
            score = similar(n[: len(t)], t)
            if score > best_score:
                best_i, best_score, best_len = i, score, len(t)
    return best_i, best_score, best_len


def _tail_after_label(text: str, consumed: int) -> str:
    """The part of the anchor observation that is value, not label.

    `consumed` counts normalised characters, so walk the raw text until that
    many alphanumerics have gone by; everything after is the value.
    """
    seen = 0
    for i, ch in enumerate(text):
        if ch.isalnum():
            seen += 1
            if seen == consumed:
                return text[i + 1 :].strip().lstrip(":").strip()
    return ""


def _value_from(
    obs: list[Observation], i: int, consumed: int
) -> tuple[str, float, Observation]:
    """The text belonging to the anchor at `i`.

    Right-hand observations are walked in x order, not in the list's order.
    The two differ: OCR line boxes on one printed row rarely share a y to the
    third decimal, so a global (y, x) sort can put the far-right value of the
    second column before the label that should have terminated the first.
    """
    anchor = obs[i]
    parts: list[str] = []
    confs: list[float] = []
    right = anchor

    tail = _tail_after_label(anchor.text, consumed)
    if tail:
        parts.append(tail)
        confs.append(anchor.confidence)

    candidates = sorted(
        (o for j, o in enumerate(obs) if j != i and o.x0 >= anchor.x1 - 0.005),
        key=lambda o: o.x0,
    )
    # Chained, comparing each candidate to the last one accepted rather than
    # to the anchor. On a sheet fed in a degree off square, the printed line
    # drifts vertically as it crosses the page — far enough at the width of an
    # A4 to exceed a line height — so a fixed comparison against the anchor
    # loses the right-hand half of every row. Neighbour-to-neighbour, the
    # drift per step stays small and the row holds together.
    ref = anchor
    for o in candidates:
        if not ref.same_band(o):
            continue
        if _is_terminator(o.text):
            break
        parts.append(o.text)
        confs.append(o.confidence)
        ref = right = o

    value = " ".join(parts).strip().lstrip(":").strip()
    return value, (min(confs) if confs else 0.0), right


def extract_header(page: Page) -> tuple[dict[str, FieldRead], list[str]]:
    obs = sorted(page.observations, key=lambda o: (round(o.y0, 3), o.x0))
    fields: dict[str, FieldRead] = {}
    missing: list[str] = []

    for spec in HEADER_FIELDS:
        i, score, consumed = _find_anchor(obs, spec.labels)
        if i < 0 or score < LABEL_MATCH:
            missing.append(spec.name)
            continue
        value, conf, right = _value_from(obs, i, consumed)
        if not value:
            missing.append(spec.name)
            continue
        a = obs[i]
        fields[spec.name] = FieldRead(
            name=spec.name,
            value=value,
            confidence=conf,
            anchor_similarity=round(score, 3),
            page=page.index,
            bbox=(a.x0, a.y0, right.x1, max(a.y1, right.y1)),
        )
    return fields, missing


# --- value parsing ---------------------------------------------------------

_RP = re.compile(r"Rp\s*([\d.,\s]+)")
_INT = re.compile(r"\d+")
# `[\dOolI]` in the numeric part is not sloppiness. These fields are
# format-constrained — SEP is the literal SEP followed by digits, a BPJS card
# number is thirteen digits — and the letter/digit confusions an OCR makes on
# a 7pt sans-serif are exactly O/0 and l/I/1. Correcting inside a field whose
# alphabet is known to be numeric is deterministic and reversible; guessing at
# a free-text field would not be, and is not done anywhere here.
_SEP = re.compile(r"\bSEP\s?[\dOolI]{3,}\b")
_KARTU = re.compile(r"\b[\dOolI]{13}\b")
_ISO = re.compile(r"\b(\d{4})[-/](\d{2})[-/](\d{2})\b")
# An INA-CBG code is <letter>-<digit>-<2 digits>-<severity in roman>. The
# recogniser confuses I with 1 and with a bare pipe in both the leading letter
# and the severity, so both positions accept the confusion set and are mapped
# back; the shape is rigid enough that nothing else can match it.
_CBG = re.compile(r"(?<![A-Z0-9])([A-Z01l|])-(\d)-(\d{2})-([I1l|]{1,3})(?![A-Z0-9])")

_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1"})
_ROMAN_FIX = str.maketrans({"1": "I", "l": "I", "|": "I"})
# The leading position of a CBG code is a letter by construction, so a digit
# there is a misread of its look-alike and can be mapped back without guessing.
_LETTER_FIX = str.maketrans({"0": "O", "1": "I", "l": "I", "|": "I"})


def fix_digits(token: str) -> str:
    """Repair OCR letter/digit confusion inside a known-numeric run."""
    return token.translate(_DIGIT_FIX)


def fix_roman(token: str) -> str:
    """The inverse, for the severity suffix of a CBG code."""
    return token.translate(_ROMAN_FIX)


def fix_letter(token: str) -> str:
    """The inverse, for the leading CBG group letter."""
    return token.translate(_LETTER_FIX)


def parse_idr(text: str) -> int | None:
    """`Rp 441.985.000,-` -> 441985000.

    Returns None rather than a partial number: a half-read tariff that still
    parses is worse than one that visibly failed, because the first goes onto
    a form and the second raises a validation failure.
    """
    m = _RP.search(text)
    body = m.group(1) if m else text
    body = body.split(",")[0]  # drop the ,- suffix
    digits = re.sub(r"\D", "", body)
    return int(digits) if digits else None


def parse_hari(text: str) -> int | None:
    m = _INT.search(text)
    return int(m.group()) if m else None


def parse_tanggal(text: str) -> date | None:
    m = _ISO.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# --- cost table ------------------------------------------------------------


def extract_totals(page: Page) -> dict[str, int | None]:
    """The JUMLAH row: cases, bed-days, rupiah.

    Taken from the JUMLAH row rather than the RITL row because that is the
    figure BPJS reconciles against, and on a multi-row form the two differ.
    """
    obs = sorted(page.observations, key=lambda o: (round(o.y0, 3), o.x0))
    row: list[Observation] = []
    for o in obs:
        if norm(o.text) == "JUMLAH" and o.x0 < 0.35 and o.y0 > 0.30:
            row = [x for x in obs if o.same_band(x) and x.x0 > o.x0]
            break
    out: dict[str, int | None] = {"kasus": None, "hari": None, "biaya_idr": None}
    for o in row:
        if o.x1 > 0.55:
            continue  # the DISETUJUI half is BPJS's to fill, and is blank
        if "Rp" in o.text or "." in o.text and len(re.sub(r"\D", "", o.text)) > 5:
            out["biaya_idr"] = parse_idr(o.text)
        elif "HARI" in o.text.upper():
            out["hari"] = parse_hari(o.text)
        elif o.text.strip().isdigit():
            out["kasus"] = int(o.text.strip())
    return out


# --- rincian annex ---------------------------------------------------------


def _bands(obs: list[Observation]) -> list[list[Observation]]:
    """Group observations into printed lines.

    Observations more than three times the median height are dropped first.
    They are never body text; in practice they are the rotated watermark,
    which one OCR pass renders as a single box covering seven tenths of the
    page. Left in, it lands in a band with every row on the sheet.
    """
    if not obs:
        return []
    heights = sorted(o.height for o in obs)
    median = heights[len(heights) // 2]
    body = [o for o in obs if median <= 0 or o.height <= 3.0 * median]

    # Grown left to right, each observation compared to the rightmost one
    # already in the band. A sheet fed a degree off square drifts vertically as
    # the line crosses the page; comparing to the band's first member splits
    # every row in half at roughly the point the drift exceeds a line height.
    # Neighbour-to-neighbour, the drift per step is a fraction of that.
    rows: list[list[Observation]] = []
    for o in sorted(body, key=lambda x: x.x0):
        best: list[Observation] | None = None
        best_gap = 0.0
        for row in rows:
            last = row[-1]
            if last.same_band(o):
                gap = abs(last.cy - o.cy)
                if best is None or gap < best_gap:
                    best, best_gap = row, gap
        if best is None:
            rows.append([o])
        else:
            best.append(o)
    rows.sort(key=lambda r: min(x.cy for x in r))
    return rows


def extract_lines(pages: list[Page]) -> list[LineRead]:
    """Read the rincian rows off every annex page.

    Column assignment is by regular expression rather than by x position: a
    SEP number, a 13-digit card number, an ISO date and an INA-CBG code are
    each unambiguous on sight, and matching on shape survives a skewed scan
    that shifts every column by a few points.
    """
    out: list[LineRead] = []
    for page in pages:
        for row in _bands(list(page.observations)):
            text = " ".join(o.text for o in row)
            sep = _SEP.search(text)
            if not sep:
                continue  # not a rincian row
            kartu = _KARTU.search(text)
            cbg = _CBG.search(text)
            tanggal = parse_tanggal(text)
            biaya = parse_idr(text) if "Rp" in text else None

            head = row[0].text.strip()
            index = int(head) if head.isdigit() else len(out) + 1

            # HARI is read out of the text after the admission date rather
            # than by column position, because the recogniser frequently emits
            # the date and the day count as one observation (`2026-03-02 14`)
            # and a positional rule then misses it on exactly those rows.
            hari = None
            m = _ISO.search(text) if tanggal else None
            if m:
                stop = min(
                    x
                    for x in (
                        cbg.start() if cbg else len(text),
                        text.find("Rp") if "Rp" in text else len(text),
                        len(text),
                    )
                )
                # Bounded on both sides. Without the upper bound the search
                # runs into the CBG code and reads its middle digit as a day
                # count on exactly the rows where HARI failed to be read at
                # all — a wrong number where None was the truthful answer.
                window = text[m.end() : stop] if stop > m.end() else ""
                m2 = re.search(
                    r"\b(\d{1,3})\s*(?:hari|hr)\b", window, re.I
                ) or re.search(r"\b(\d{1,3})\b", window)
                if m2:
                    hari = int(m2.group(1))

            nama = None
            for o in row:
                t = o.text.strip()
                if re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+)*", t) and len(t) > 3:
                    nama = t
                    break

            out.append(
                LineRead(
                    index=index,
                    sep_number="SEP" + fix_digits(sep.group()[3:].strip()),
                    nama=nama,
                    no_kartu=fix_digits(kartu.group()) if kartu else None,
                    tanggal_masuk=tanggal,
                    hari=hari,
                    cbg_code=(
                        f"{fix_letter(cbg.group(1))}-{cbg.group(2)}-"
                        f"{cbg.group(3)}-{fix_roman(cbg.group(4))}"
                        if cbg
                        else None
                    ),
                    biaya_idr=biaya,
                    confidence=min(o.confidence for o in row),
                )
            )
    return out


# --- entry point -----------------------------------------------------------


def extract(pages: list[Page]) -> ExtractedFPK:
    if not pages:
        raise ValueError("no pages to extract from")
    fields, missing = extract_header(pages[0])
    return ExtractedFPK(
        fields=fields,
        lines=extract_lines(pages[1:]),
        totals=extract_totals(pages[0]),
        missing=missing,
        engine=pages[0].engine,
        pages=len(pages),
    )


__all__ = [
    "ExtractedFPK",
    "FieldRead",
    "FieldSpec",
    "HEADER_FIELDS",
    "LineRead",
    "extract",
    "extract_header",
    "extract_lines",
    "extract_totals",
    "norm",
    "parse_hari",
    "parse_idr",
    "parse_tanggal",
]
