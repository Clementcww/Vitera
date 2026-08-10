"""BM25 — the retrieval baseline the cross-encoder has to beat.

Implemented here rather than pulled from `rank-bm25` for three reasons: it is
forty lines, it removes a dependency from a reproducibility claim, and the
tokeniser has to be ours anyway (Indonesian clinical shorthand, arrows, unit
strings and ICD codes all tokenise badly under a default splitter).

**This baseline is not a strawman**, for the same reason arm A is not: if BM25
loses because we crippled it, the headline result is worthless. It gets the
identical evidence passage the cross-encoder gets, its IDF is fitted on the
training split only, and its raw score is turned into a probability by the same
logistic calibration the neural model receives. What it cannot do is decide
that "gula darah terkontrol dengan insulin" documents E11.9 while "Gula darah
sewaktu ↑ (200 mg/dL)" only suggests it. That gap is the experiment.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vitera.contracts import Flag

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?", re.IGNORECASE)


def tokenise(text: str) -> list[str]:
    """Lowercase word and code tokens. `E11.9` survives as one token; `↑` and
    punctuation are dropped, since neither carries retrieval signal."""
    return [m.group(0).lower() for m in _TOKEN.finditer(text)]


@dataclass
class BM25:
    """Okapi BM25 with the usual constants. Fitted on a line corpus."""

    k1: float = 1.5
    b: float = 0.75
    idf: dict[str, float] = field(default_factory=dict)
    avg_len: float = 1.0
    n_docs: int = 0

    def fit(self, documents: Iterable[Sequence[str]]) -> BM25:
        df: Counter[str] = Counter()
        total = 0
        n = 0
        for doc in documents:
            n += 1
            total += len(doc)
            df.update(set(doc))
        self.n_docs = n
        self.avg_len = (total / n) if n else 1.0
        # Robertson/Sparck-Jones IDF, floored so a term present in every
        # document contributes nothing rather than something negative.
        self.idf = {
            t: max(0.0, math.log(1.0 + (n - c + 0.5) / (c + 0.5)))
            for t, c in df.items()
        }
        return self

    def score(self, query: Sequence[str], doc: Sequence[str]) -> float:
        if not doc:
            return 0.0
        freq = Counter(doc)
        norm = self.k1 * (1 - self.b + self.b * len(doc) / self.avg_len)
        total = 0.0
        for term in query:
            f = freq.get(term, 0)
            if not f:
                continue
            total += self.idf.get(term, 0.0) * f * (self.k1 + 1) / (f + norm)
        return total

    def best_line(self, query: str, lines: Sequence[str]) -> tuple[int, float]:
        """Index and score of the line that best matches the query.

        Line-level rather than passage-level: a fourteen-day CPPT would drown
        one supporting sentence in length normalisation, which would make the
        baseline weak for a reason that has nothing to do with retrieval.
        """
        q = tokenise(query)
        best_i, best_s = -1, 0.0
        for i, line in enumerate(lines):
            s = self.score(q, tokenise(line))
            if s > best_s:
                best_i, best_s = i, s
        return best_i, best_s


# ---------------------------------------------------------------------------
# The pipeline-shaped baseline — arm B of the three-arm experiment
# ---------------------------------------------------------------------------


class BM25Scorer:
    """A `Scorer` for the bounded loop, backed by BM25 instead of the neural model.

    This exists so that arm B of the three-arm experiment is *the same product*
    with one component swapped, rather than a different measurement taken on a
    different object. Arm A runs `run_pipeline` with no scorer, arm B runs it
    with this, arm C runs it with the cross-encoder — same rules, same span
    filter, same router, same thresholds from the same file.

    That matters because the headline claim is a comparison. If arm B were
    scored at the pair level in a notebook while arm C ran through the pipeline,
    the gap between them would include every difference between the two
    harnesses, and none of it would be attributable to the thing being claimed.

    **It is not a strawman**, which is the other half of the claim being worth
    anything. It gets the identical evidence lines the cross-encoder gets, the
    identical `_classify` for defect class and remedy, the identical anchor for
    the span, and the identical emit floor. Its IDF is fitted on the training
    split only, and its raw score is turned into a probability by logistic
    scaling on that same split, so the comparison is between what the two can
    SEPARATE and not between how their raw outputs happen to be distributed.

    What it cannot do is decide that "gula darah terkontrol dengan insulin"
    documents E11.9 while "Gula darah sewaktu ↑ (200 mg/dL)" only suggests it.
    Both contain the same terms. That gap is the experiment.
    """

    def __init__(self, bm: BM25, coef: float, intercept: float, emit_floor: float):
        self.bm = bm
        self.coef = coef
        self.intercept = intercept
        self.emit_floor = emit_floor

    @classmethod
    def fit(
        cls,
        train_rows: Sequence[dict[str, Any]],
        *,
        emit_floor: float | None = None,
    ) -> BM25Scorer:
        """Fit IDF and the Platt scaler on the TRAINING split only.

        Fitting on test would leak, and would leak in the direction that makes
        the baseline look better — which is the direction that would make our
        own headline look worse, so it is worth being explicit that it is not
        happening rather than merely not doing it.
        """
        from sklearn.linear_model import LogisticRegression

        from vitera.models.pairs import iter_pairs

        if emit_floor is None:
            from vitera import config

            emit_floor = float(
                config.thresholds()["router"]["default"]["abstain_below"]
            )

        pairs = list(iter_pairs(train_rows))
        bm = BM25().fit(tokenise(ln.text) for p in pairs for ln in p.lines)
        x = [[cls._raw(bm, p)] for p in pairs]
        y = [p.label for p in pairs]
        clf = LogisticRegression(max_iter=1000).fit(x, y)
        return cls(
            bm,
            float(clf.coef_[0][0]),
            float(clf.intercept_[0]),
            emit_floor,
        )

    @staticmethod
    def _raw(bm: BM25, pair: Any) -> float:
        _, s = bm.best_line(pair.hypothesis, [ln.text for ln in pair.lines])
        return float(s)

    def _probability(self, pair: Any) -> float:
        """Platt-scaled BM25, then inverted.

        BM25 high means the evidence matches the hypothesis, and the label
        being predicted is *unsupported* — so the logistic fit carries the sign,
        and no manual flip is applied here. Getting that backwards would have
        produced a baseline that scores best on the codes it understands least,
        which is a bug that looks like a result.
        """
        z = self.coef * self._raw(self.bm, pair) + self.intercept
        return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, z))))

    def score(self, ctx: Any) -> tuple[Flag, ...]:
        # `Flag` is imported here at RUNTIME, not only under TYPE_CHECKING.
        # It is constructed below, and a type-only import made this raise
        # NameError — which `BoundedRunner` catches per tool by design, so the
        # arm silently produced zero flags and looked like a rules-only
        # baseline instead of failing. Exactly the class of bug that gets
        # written into a paper.
        from vitera.contracts import Flag, FlagSource
        from vitera.models.cross_encoder import _RATIONALE, _classify
        from vitera.models.pairs import build_pairs

        pairs = build_pairs(ctx)
        probs = [self._probability(p) for p in pairs]
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
                    score=round(min(1.0, max(0.0, prob)), 4),
                    source=FlagSource.CROSS_ENCODER,
                    rationale=_RATIONALE[defect].format(code=pair.code),
                    subject=pair.code,
                )
            )
        return tuple(out)


__all__ = ["BM25", "BM25Scorer", "tokenise"]
