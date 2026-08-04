"""Reading the frozen corpus back into contract types.

`make data` writes JSONL; everything downstream needs `Episode` and
`CodedClaim` objects. The deserialisers lived in `experiments/arm_a.py` until
bucket 8, which was the wrong direction of dependency — `experiments/` consumes
`src/`, never the reverse, or `src` stops being the thing that produces the
paper's numbers.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

from vitera.contracts import (
    ClinicalEvent,
    ClinicalText,
    Document,
    Episode,
    EventKind,
    SecondaryDiagnosis,
)
from vitera.generator.defects import CodedClaim


def episode_from_dict(d: dict[str, Any]) -> Episode:
    return Episode(
        episode_id=d["episode_id"],
        site_id=d["site_id"],
        admission_date=date.fromisoformat(d["admission_date"]),
        primary_dx=d["primary_dx"],
        secondary_dx=tuple(SecondaryDiagnosis(**s) for s in d["secondary_dx"]),
        procedures=tuple(d["procedures"]),
        events=tuple(
            ClinicalEvent(
                day=e["day"],
                kind=EventKind[e["kind"]] if isinstance(e["kind"], str) else e["kind"],
                code=e["code"],
                text=ClinicalText(e["text"]) if e["text"] else None,
            )
            for e in d["events"]
        ),
        documents=tuple(
            Document(doc_id=x["doc_id"], day=x["day"], text=ClinicalText(x["text"]))
            for x in d["documents"]
        ),
        discharge_day=d["discharge_day"],
    )


def claim_from_dict(d: dict[str, Any]) -> CodedClaim:
    return CodedClaim(
        episode_id=d["episode_id"],
        primary_dx=d["primary_dx"],
        secondary_dx=tuple(d["secondary_dx"]),
        procedures=tuple(d["procedures"]),
        documents_present=tuple(d["documents_present"]),
        sep_number=d["sep_number"],
        admission_date_claimed=date.fromisoformat(d["admission_date_claimed"]),
    )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


__all__ = ["claim_from_dict", "episode_from_dict", "iter_jsonl", "load_jsonl"]
