"""D8 step 1: trigger phrases -> candidate codes.

Deliberately over-proposes. Recall lives here, precision lives in the encoder,
and that split is the tunable knob: loosen a pattern to chase more revenue and
the model absorbs the false positives. No retrain.

`prior` is what the stub encoder returns when no weights are loaded, so the
pipeline runs end to end before the model exists. Once weights are configured
the prior is ignored.
"""

import re
from typing import List, NamedTuple

from dto.episode import SafeEpisode


class Candidate(NamedTuple):
    code: str
    doc: str
    span: str
    prior: float
    ocr_confidence: float | None


# (pattern, candidate code, prior). Patterns are Indonesian clinical shorthand.
# ponytail: the eGFR bands are encoded in the regex (a 1-2 digit reading means
# <100). Parse the number properly if a third band is ever needed.
TRIGGERS = [
    (r"transfusi\s+prc(?:\s+\d+\s+kolf)?", "99.04", 0.87),
    (r"egfr\s+(?:[12]?\d)(?:\s|$|\D)", "N18.4", 0.91),   # eGFR < 30 -> stage 4
    (r"egfr\s+(?:[3-5]\d)(?:\s|$|\D)", "N18.3", 0.88),   # eGFR 30-59 -> stage 3
    (r"konjungtiva\s+anemis", "D64.9", 0.64),
    (r"mri\s+kepala", "88.91", 0.70),
]


def propose(episode: SafeEpisode) -> List[Candidate]:
    out: List[Candidate] = []
    for doc in episode.docs:
        for pattern, code, prior in TRIGGERS:
            match = re.search(pattern, doc.text, re.I)
            if match:
                out.append(
                    Candidate(
                        code=code,
                        doc=doc.doc_id,
                        span=match.group(0).strip(),
                        prior=prior,
                        ocr_confidence=doc.ocr_confidence,
                    )
                )
    return out
