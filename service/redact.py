"""The only producer of SafeText in the codebase.

Redaction runs AFTER extraction and BEFORE any model call. `fail_closed` means
a document whose redaction cannot be verified is dropped from model input
entirely rather than passed through — and the drop is reported, never hidden.
"""

import re
from typing import List

from dto.episode import RawEpisode, SafeDoc, SafeEpisode
from dto.exceptions import RedactionError
from dto.types import SafeText
from service.config import config

PII_PATTERNS = {
    "NIK": re.compile(r"\b\d{16}\b"),
    "SEP": re.compile(r"\b\d{4}[A-Z]\d{10}[A-Z]\d{6}\b"),
}


def _scrub(text: str, name: str) -> str:
    out = text
    for part in name.split():
        if len(part) > 2:
            out = re.sub(rf"\b{re.escape(part)}\b", "[NAMA]", out, flags=re.I)
    for label, pattern in PII_PATTERNS.items():
        out = pattern.sub(f"[{label}]", out)
    return out


def _surviving_pii(text: str) -> str | None:
    for label, pattern in PII_PATTERNS.items():
        if pattern.search(text):
            return label
    return None


def to_safe_episode(raw: RawEpisode) -> SafeEpisode:
    cfg = config()["redaction"]
    docs: List[SafeDoc] = []
    dropped: List[str] = []

    for doc in raw.docs:
        low_confidence = (
            doc.extraction == "ocr"
            and (doc.ocr_confidence or 0.0) < cfg["min_ocr_confidence"]
        )
        if low_confidence and cfg["fail_closed"]:
            # OCR noise defeats pattern matching — a NIK read with an O for a 0
            # no longer matches \d{16}. Withhold rather than gamble.
            dropped.append(doc.doc_id)
            continue

        scrubbed = _scrub(doc.text, raw.demographics.name)
        survivor = _surviving_pii(scrubbed)
        if survivor:
            if cfg["fail_closed"]:
                dropped.append(doc.doc_id)
                continue
            raise RedactionError(
                detail=f"{survivor} survived redaction in {doc.doc_id}",
                instance=raw.episode_id,
            )

        docs.append(
            SafeDoc(
                doc_id=doc.doc_id,
                doc_type=doc.doc_type,
                stage=doc.stage,
                extraction=doc.extraction,
                ocr_confidence=doc.ocr_confidence,
                signed=doc.signed,
                text=SafeText(scrubbed),
            )
        )

    return SafeEpisode(
        episode_id=raw.episode_id,
        sex=raw.demographics.sex,
        age_years=raw.demographics.age_years,
        hospital_day=raw.hospital_day,
        discharged=raw.discharged_at is not None,
        docs=docs,
        claim=raw.claim,
        dropped_docs=dropped,
    )
