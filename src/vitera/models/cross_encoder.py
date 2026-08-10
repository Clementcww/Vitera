"""The cross-encoder scorer — bucket 8.

This is the `Scorer` the bounded loop plugs in. It answers one question per
coded secondary diagnosis (*does the record support this code?*) and returns
`Flag`s carrying a verbatim span.

Where the boundaries sit, because they are the paper's claims:

- **The model decides support and nothing else** (architectural rule 2). It
  does not choose the defect class, the remedy, the span or the tariff. Class
  and remedy are assigned by `_classify` below, which is a deterministic
  fifteen lines readable in one screen.
- **Its output is a calibrated probability**, temperature-scaled on held-out
  sites and shifted to the deployment prior. The router compares that number
  to a threshold from `config/thresholds.yaml`; the scorer never decides
  anything (architectural rule 5).
- **Every flag cites a real line.** The span comes from `CodePair.anchor`,
  which selects a line of the record — never model-generated text. The
  pipeline's span filter re-checks it anyway; a filter, not a promise.
- **A missing checkpoint is not fatal** (architectural rule 8). `load` raises
  `ScorerUnavailable`, the caller passes `scorer=None`, and the pipeline runs
  rules-only and marks itself advisory.

The remedy split is the part a koder will judge us on. A code with its signals
sitting in the CPPT and no mention in the resume medis is a **Query** — the
care happened, the record does not show it, and the DPJP can still fix it
today. A code with no signal anywhere is a **Recode** — nobody should be asked
to document something that never happened. That distinction is deterministic,
which is why it is trustworthy.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vitera.contracts import DefectClass, Flag, FlagSource, Remedy
from vitera.generator import reference as ref
from vitera.generator.defects import _SIBLINGS
from vitera.models.pairs import CodePair, build_pairs
from vitera.rules.engine import RuleContext

DEFAULT_DIR = Path("models/cross_encoder")

# Reverse of the sibling table: which codes a claimed code could be a
# mis-specification OF. Built once; the table is static reference data.
_PARENT_OF: dict[str, tuple[str, ...]] = {}
for _parent, _kids in _SIBLINGS.items():
    for _kid in _kids:
        _PARENT_OF[_kid] = _PARENT_OF.get(_kid, ()) + (_parent,)


class ScorerUnavailable(RuntimeError):
    """No usable checkpoint. The caller degrades to rules-only, per rule 8."""


@dataclass(frozen=True, slots=True)
class Calibration:
    temperature: float
    train_prior: float
    deployment_prior: float

    @classmethod
    def load(cls, path: Path) -> Calibration:
        meta = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            temperature=float(meta["temperature"]),
            train_prior=float(meta["train_prior"]),
            deployment_prior=float(meta["deployment_prior"]),
        )


def _severity_weight(code: str) -> int:
    try:
        return ref.comorbidity_by_code(code).severity_weight
    except KeyError:
        return 0


def _classify(
    pair: CodePair, unsupported: Sequence[CodePair]
) -> tuple[DefectClass, Remedy]:
    """Assign defect class and remedy. Deterministic — rule 2.

    Order is the reasoning order a koder would use: is this the wrong version
    of a code the record does document; is it true but unwritten; is it part of
    a pattern; or is it simply not in the record at all.
    """
    claimed = {p.code for p in unsupported} | {pair.code}

    # D2 — a sibling of a code whose evidence IS in the record and which the
    # claim does not carry. Wrong specificity, not a wrong diagnosis.
    for parent in _PARENT_OF.get(pair.code, ()):
        if parent in claimed:
            continue
        if any(s.label in pair.evidence for s in _signals(parent)):
            return DefectClass.D2, Remedy.RECODE

    # D4 — clinically visible, never documented. The DPJP can still fix it.
    if pair.has_signal:
        return DefectClass.D4, Remedy.QUERY

    # D7 — two or more unevidenced major comorbidities is a pattern, not a slip.
    heavy = [
        p for p in unsupported if not p.has_signal and _severity_weight(p.code) >= 2
    ]
    if len(heavy) >= 2 and pair in heavy:
        return DefectClass.D7, Remedy.RECODE

    # D3 — coded, and the record says nothing about it.
    return DefectClass.D3, Remedy.RECODE


def _signals(code: str) -> tuple[Any, ...]:
    try:
        return ref.comorbidity_by_code(code).signals
    except KeyError:
        return ()


_RATIONALE = {
    DefectClass.D2: (
        "kode {code} kemungkinan salah spesifisitas; rekam medis mendukung "
        "kode lain pada kelompok yang sama"
    ),
    DefectClass.D3: (
        "kode {code} tidak didukung bukti apa pun pada rekam medis yang tersedia"
    ),
    DefectClass.D4: (
        "bukti klinis untuk {code} ada pada catatan, namun diagnosis tidak "
        "tertulis pada dokumentasi DPJP"
    ),
    DefectClass.D7: (
        "kode {code} termasuk pola penambahan komorbiditas berat tanpa bukti penunjang"
    ),
}


class CrossEncoderScorer:
    """`Scorer` for the bounded loop. Scores pairs, emits flags, decides nothing."""

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        calibration: Calibration,
        *,
        max_len: int,
        emit_floor: float | None = None,
    ) -> None:
        self.model = model
        self.tok = tokenizer
        self.calibration = calibration
        self.max_len = max_len
        if emit_floor is None:
            from vitera import config

            # NOT a decision — the router still owns the verdict. This is the
            # floor below which a finding is not worth carrying through the
            # trace at all, and it is read from config like every threshold.
            router = config.thresholds()["router"]["default"]
            emit_floor = float(router["abstain_below"])
        self.emit_floor = emit_floor

    # -- construction --------------------------------------------------

    @classmethod
    def load(cls, path: Path = DEFAULT_DIR, **kwargs: Any) -> CrossEncoderScorer:
        from vitera.models.train_cross_encoder import MAX_LEN

        if not (path / "calibration.json").exists():
            raise ScorerUnavailable(
                f"no cross-encoder checkpoint at {path}. Run `make train`. "
                "The pipeline runs rules-only and advisory without one."
            )
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ScorerUnavailable(f"model stack unavailable: {exc}") from exc

        from vitera.models.train_cross_encoder import device

        model = AutoModelForSequenceClassification.from_pretrained(path)
        model.to(device())
        model.eval()
        torch.set_grad_enabled(False)
        return cls(
            model,
            AutoTokenizer.from_pretrained(path),
            Calibration.load(path / "calibration.json"),
            max_len=kwargs.pop("max_len", MAX_LEN),
            **kwargs,
        )

    # -- scoring -------------------------------------------------------

    def probabilities(self, pairs: Sequence[CodePair]) -> list[float]:
        """Calibrated P(code is unsupported), at the deployment prior."""
        from vitera.models.calibrate import prior_shift, sigmoid
        from vitera.models.train_cross_encoder import predict_logits

        if not pairs:
            return []
        logits = predict_logits(self.model, self.tok, pairs, max_len=self.max_len)
        probs = sigmoid(logits / self.calibration.temperature)
        shifted = prior_shift(
            probs, self.calibration.train_prior, self.calibration.deployment_prior
        )
        return [float(x) for x in shifted]

    def score(self, ctx: RuleContext) -> tuple[Flag, ...]:
        pairs = build_pairs(ctx)
        probs = self.probabilities(pairs)
        above = [p for p, q in zip(pairs, probs, strict=True) if q >= self.emit_floor]

        out: list[Flag] = []
        for pair, prob in zip(pairs, probs, strict=True):
            if prob < self.emit_floor:
                continue
            anchor = pair.anchor
            if anchor is None:  # nothing verbatim to cite — rule 6 drops it
                continue
            defect, remedy = _classify(pair, above)
            out.append(
                Flag(
                    defect_class=defect,
                    remedy=remedy,
                    span=anchor.span(),
                    score=round(prob, 4),
                    source=FlagSource.CROSS_ENCODER,
                    rationale=_RATIONALE[defect].format(code=pair.code),
                    subject=pair.code,
                )
            )
        return tuple(out)


__all__ = ["Calibration", "CrossEncoderScorer", "ScorerUnavailable"]
