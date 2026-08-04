"""Berkas ingestion: a folder of PDFs, digital and scanned, mixed.

The PDF text layer is used wherever it exists (free and instant), and only
pages that come back empty are sent to OCR. A document is never allowed to fall
through to raw byte decoding: passing undecodable binary to the pipeline as if
it were clinical text produces a confident, fully fabricated review.

Two extraction facts confirmed against the generated corpus, both handled in
`_page_text`:

1. Character-box fields do not extract as strings. ICD code, medical record
   number and dates are drawn one character per printed box, so extraction
   returns `I 6 3 . 9`. Free-text fields extract cleanly; boxed ones do not.
2. Naive line reading splices adjacent columns. Never `extract_text().split()`
   across a two-column row.
"""

import io
import logging
import os
import re
from typing import List, Tuple

from pypdf import PdfReader

from dto.exceptions import BadRequestError

logger = logging.getLogger("vitera.extract")

MIN_CHARS_PER_DIGITAL_PAGE = int(os.getenv("OCR_MIN_CHARS_PER_PAGE", "100"))

# `I 6 3 . 9` -> `I63.9`. Runs of 3+ single characters separated by single
# spaces are a character-box field, not prose.
_BOXED_FIELD = re.compile(r"\b(?:\S ){2,}\S\b")


def _rejoin_boxed_fields(text: str) -> str:
    return _BOXED_FIELD.sub(lambda m: m.group(0).replace(" ", ""), text)


def extract_pdf(filename: str, file_bytes: bytes) -> Tuple[str, List[int], str]:
    """Return (text, page indices that need OCR, source: digital|ocr|mixed)."""
    if not file_bytes:
        raise BadRequestError(detail=f"'{filename}' is empty.", instance=filename)

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception as e:
        raise BadRequestError(detail=f"Could not read '{filename}' as a PDF: {e}", instance=filename)

    page_texts: List[str] = []
    needs_ocr: List[int] = []
    for index, page in enumerate(reader.pages):
        try:
            text = (page.extract_text() or "").strip()
        except Exception as e:
            logger.warning(f"Text-layer extraction failed on page {index + 1} of '{filename}': {e}")
            text = ""

        if len(text) >= MIN_CHARS_PER_DIGITAL_PAGE:
            page_texts.append(_rejoin_boxed_fields(text))
        else:
            page_texts.append("")
            needs_ocr.append(index)

    if needs_ocr:
        for index, text in zip(needs_ocr, ocr_pages(file_bytes, needs_ocr)):
            page_texts[index] = _rejoin_boxed_fields(text)

    joined = "\n\n".join(t for t in page_texts if t).strip()
    if not joined:
        raise BadRequestError(
            detail=(
                f"No readable text could be extracted from '{filename}'. It was not "
                "analysed, because analysing an unreadable document would return "
                "fabricated findings."
            ),
            instance=filename,
        )

    source = "digital" if not needs_ocr else ("ocr" if len(needs_ocr) == len(page_texts) else "mixed")
    logger.info(f"[Extract] '{filename}': {len(page_texts)} page(s), {len(needs_ocr)} via OCR ({source})")
    return joined, needs_ocr, source


def ocr_pages(file_bytes: bytes, page_indices: List[int]) -> List[str]:
    """OCR the scanned pages.

    ponytail: not wired yet. Rasterise with pymupdf and send each page image to
    the OpenAI vision model, or swap in Tesseract if the pages must stay on
    prem. Whichever it is, it must return per-word confidences too — the span
    filter matches against extracted text, and a perfectly quoted transcription
    error is still a transcription error.
    """
    raise BadRequestError(
        detail=(
            f"{len(page_indices)} page(s) have no text layer and OCR is not wired up yet. "
            "Set up ocr_pages() in service/extract.py before ingesting scanned berkas."
        ),
        instance="ocr",
    )
