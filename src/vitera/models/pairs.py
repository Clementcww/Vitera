"""Pair construction for the cross-encoder — bucket 8.

The cross-encoder is the clinical judge (a locked decision). Its task is one
question, asked once per coded secondary diagnosis:

    does the clinical record support this code?

So the unit of work is a **pair**: a hypothesis rendered from the coded
diagnosis, and an evidence passage taken verbatim from the record. This module
builds those pairs, and it is the piece where a careless choice would produce a
strong-looking number that means nothing. Three decisions carry that weight.

**1. The evidence passage excludes the record's own diagnosis list.**
`resume_medis` contains a `Diagnosis sekunder:` block naming every documented
comorbidity and its code. Leaving that in would reduce the task to substring
matching — the model would score `E11.9` as supported because the string
`E11.9` is three lines further down, and the reported AUC would measure string
equality, not clinical reasoning. The block is the *restatement of the claim*,
not evidence for it, so it is removed. What is left is what a verifikator
actually reads: the lab and medication lines in the CPPT, and the DPJP's
narrative in `Perjalanan penyakit`.

**2. The label is documentation, not clinical presence.**
`label = 1` (unsupported) whenever the code is absent from
`ground_truth.documented_dx`. That deliberately labels a D4 target — a
comorbidity genuinely present in the patient, visible in the labs, never
written down — as unsupported. It is unsupported *as documentation*, which is
what BPJS pends on, and the remedy is a DPJP query rather than a recode. The
distinction is made deterministically by `has_signal`, never by the model:
architectural rule 2 leaves the model with the support judgement and nothing
else.

**3. Evidence is day-aware.**
`build_pairs(..., day=d)` sees only documents written by day `d`, so the same
function serves the discharge run and every concurrent run. Before discharge
there is no `resume_medis`, so a coded comorbidity backed only by labs reads as
undocumented — which is exactly the finding, arriving early enough to repair.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from vitera.contracts import Span
from vitera.generator import reference as ref
from vitera.generator.corpus import claim_from_dict, episode_from_dict
from vitera.generator.defects import _SIBLINGS
from vitera.rules.engine import RuleContext

# Lines that restate the claim rather than evidence it. See decision 1 above.
_DX_LIST_HEADER = "Diagnosis sekunder"
_BULLET = re.compile(r"^\s+-\s")

# Which single line a flag cites when the record holds no evidence at all.
_FALLBACK_ANCHORS = ("Diagnosis utama:", "Diagnosis masuk:", "Diagnosis kerja:")

CLASSES = ("D2", "D3", "D4", "D7")
"""The four classes deterministic rules cannot reach. Bucket 5 measured that;
this is the gap the cross-encoder exists to close."""


@dataclass(frozen=True, slots=True)
class EvidenceLine:
    """One line of the record, with the offsets that make it citable."""

    doc_id: str
    start: int
    end: int
    text: str

    def span(self) -> Span:
        return Span(self.doc_id, self.start, self.end, self.text)


@dataclass(frozen=True, slots=True)
class CodePair:
    """One (coded diagnosis, evidence) pair — the cross-encoder's input."""

    episode_id: str
    site_id: str
    code: str
    hypothesis: str
    evidence: str
    lines: tuple[EvidenceLine, ...]
    label: int  # 1 = not supported by the record, i.e. a defect
    defect_class: str | None  # evaluation only; never an input to any model
    has_signal: bool  # deterministic — decides QUERY vs RECODE, not the model
    split: str = ""

    @property
    def anchor(self) -> EvidenceLine | None:
        """The line a flag on this pair cites.

        With a signal present, cite the signal line: that is the whole point of
        a D4 query — *the labs say this, the notes do not*. With no signal
        anywhere, cite what the record does state as the diagnosis, so the
        absence is visible against something real. Rule 6 needs a verbatim
        span, and a fabricated one is worse than no flag.
        """
        if self.has_signal:
            for label in _signal_labels(self.code):
                for ln in self.lines:
                    if label in ln.text:
                        return ln
        for prefix in _FALLBACK_ANCHORS:
            for ln in self.lines:
                if ln.text.strip().startswith(prefix):
                    return ln
        return self.lines[0] if self.lines else None


def _signal_labels(code: str) -> tuple[str, ...]:
    try:
        return tuple(s.label for s in ref.comorbidity_by_code(code).signals)
    except KeyError:
        return ()


def _lines(doc_id: str, text: str) -> list[EvidenceLine]:
    out = []
    pos = 0
    for raw in text.split("\n"):
        if raw.strip():
            out.append(EvidenceLine(doc_id, pos, pos + len(raw), raw))
        pos += len(raw) + 1
    return out


def _strip_dx_list(lines: Sequence[EvidenceLine]) -> list[EvidenceLine]:
    """Drop the `Diagnosis sekunder:` block — decision 1.

    Structural rather than pattern-based: the header, then every indented
    bullet under it. A CPPT signal line is also an indented bullet, but it
    never follows this header, so nothing clinical is lost.
    """
    out: list[EvidenceLine] = []
    in_block = False
    for ln in lines:
        if ln.text.strip().startswith(_DX_LIST_HEADER):
            in_block = True
            continue
        if in_block and _BULLET.match(ln.text):
            continue
        in_block = False
        out.append(ln)
    return out


def evidence_lines(ctx: RuleContext) -> tuple[EvidenceLine, ...]:
    """The passage every pair for this episode is scored against.

    Only the LAST available CPPT is taken. Signals persist once they appear, so
    the final progress note is the union of everything visible by `ctx.day` —
    including the last fourteen days of a long stay, without fourteen
    near-identical copies eating the model's 256 tokens.
    """
    available = ctx.available
    cppts = [d for d in available if d.doc_id.startswith("cppt_")]
    latest = max(cppts, key=lambda d: d.day, default=None)
    chosen = [d for d in available if d.doc_id in ("berkas_klaim", "resume_medis")]
    if latest is not None:
        chosen.append(latest)

    lines: list[EvidenceLine] = []
    seen: set[str] = set()
    for doc in sorted(chosen, key=lambda d: (d.day, d.doc_id)):
        for ln in _strip_dx_list(_lines(doc.doc_id, doc.text)):
            key = ln.text.strip()
            if key in seen:
                continue
            seen.add(key)
            lines.append(ln)
    return tuple(lines)


def hypothesis(code: str) -> str:
    """The left side of the pair. Rendered from the label, never the code
    alone — a bare code is a token the model can memorise, a label is text it
    has to reconcile against the narrative."""
    return f"Diagnosis sekunder yang dikode: {ref.icd10_label(code)} ({code})."


def build_pairs(
    ctx: RuleContext,
    *,
    documented: Sequence[str] | None = None,
    attribution: dict[str, str] | None = None,
    split: str = "",
) -> tuple[CodePair, ...]:
    """One pair per coded secondary diagnosis.

    `documented` and `attribution` are ground truth, used only to label and to
    attribute a class for evaluation. At inference `documented` is None and
    every pair carries `label = -1`, which nothing downstream reads. Note the
    distinction from an empty tuple: an episode with nothing documented is a
    labelled episode where every coded diagnosis is unsupported.
    """
    lines = evidence_lines(ctx)
    text = "\n".join(ln.text for ln in lines)
    doc_set = set(documented or ())
    attribution = attribution or {}

    out = []
    for code in ctx.claim.secondary_dx:
        try:
            hyp = hypothesis(code)
        except KeyError:  # unlabelled code — scoring it would be guesswork
            continue
        out.append(
            CodePair(
                episode_id=ctx.episode.episode_id,
                site_id=ctx.episode.site_id,
                code=code,
                hypothesis=hyp,
                evidence=text,
                lines=lines,
                label=-1 if documented is None else (0 if code in doc_set else 1),
                defect_class=attribution.get(code),
                has_signal=any(s in text for s in _signal_labels(code)),
                split=split,
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# Class attribution — evaluation only
# ---------------------------------------------------------------------------


def attribute(row: dict[str, Any]) -> dict[str, str]:
    """Map each defective code on a claim to the defect class that put it there.

    Per-class results are the headline of bucket 8, so this has to be exact
    rather than inferred. Three of the four classes record the code they
    targeted in `DefectLabel.target_code`. D7 does not — its injector writes
    the pair of added codes into `detail` instead — so that one string, which
    our own generator formats deterministically, is parsed here.

    NOTE for the next regeneration: giving `DefectLabel` a `target_codes`
    tuple would delete this parse. Not worth refreezing the corpus for.
    """
    out: dict[str, str] = {}
    for d in row["defects"]:
        cls = d["defect_class"]
        if cls not in CLASSES:
            continue
        if cls == "D7":
            for code in _parse_d7(d["detail"]):
                out[code] = "D7"
        elif d.get("target_code"):
            out[d["target_code"]] = cls

    # D2 substitutes a sibling: the label names the code that was REPLACED,
    # while the claim carries the replacement. Follow the substitution.
    for d in row["defects"]:
        if d["defect_class"] != "D2" or not d.get("target_code"):
            continue
        original = d["target_code"]
        out.pop(original, None)
        claimed = set(row["claim"]["secondary_dx"])
        for sibling in _SIBLINGS.get(original, []):
            if sibling in claimed:
                out[sibling] = "D2"
    return out


def _parse_d7(detail: str) -> tuple[str, ...]:
    m = re.search(r"pola upcoding:\s*(.+?)\s+ditambahkan", detail)
    if not m:
        return ()
    return tuple(c.strip() for c in m.group(1).split(",") if c.strip())


def iter_pairs(
    rows: Iterable[dict[str, Any]],
    *,
    day: int | None = None,
    split: str = "",
) -> list[CodePair]:
    """Pairs for a whole corpus split. `day=None` means discharge day."""
    out: list[CodePair] = []
    for row in rows:
        ep = episode_from_dict(row["episode"])
        claim = claim_from_dict(row["claim"])
        d = ep.discharge_day or 0 if day is None else day
        ctx = RuleContext(ep, claim, d)
        out.extend(
            build_pairs(
                ctx,
                documented=tuple(row["ground_truth"]["documented_dx"]),
                attribution=attribute(row),
                split=split or row.get("split", ""),
            )
        )
    return out


__all__ = [
    "CLASSES",
    "CodePair",
    "EvidenceLine",
    "attribute",
    "build_pairs",
    "evidence_lines",
    "hypothesis",
    "iter_pairs",
]
