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


__all__ = ["BM25", "tokenise"]
