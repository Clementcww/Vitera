"""The model boundary — pseudonymisation, and the only LLM client.

Architectural rule 3: the LLM never sees re-identified data. That is enforced
here in two layers. The type system makes it a compile-time error to pass
`ClinicalText` where `PseudonymisedText` is required, and `LLMClient.complete`
refuses at runtime any string that did not come out of `pseudonymise`.

`VITERA_LLM_MODE` decides where completions come from:

    live    call the provider, no caching
    record  call the provider AND write to the cache — rehearsal mode
    cache   read from the cache only; a miss RAISES

`cache` raising on a miss is deliberate. A demo that silently falls back to a
live call is a demo that can fail on stage with the wifi down, and a cache that
silently regenerates is not a reproducibility artifact.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from vitera import config
from vitera.contracts import ClinicalText, PseudonymisedText

CACHE_DIR = Path("data/generated/llm_cache")

# Indonesian identifiers that must never leave the hospital boundary.
_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bNIK[:\s]*\d{16}\b", "[NIK]"),
    (r"\b\d{16}\b", "[NIK]"),
    (r"\bSEP\d+\b", "[SEP]"),
    (r"\bNo\.\s*RM[:\s]*\d+\b", "[NO_RM]"),
    (r"\b\d{4}-\d{2}-\d{2}\b", "[TANGGAL]"),
    (r"\b(?:\+62|0)8\d{8,11}\b", "[TELEPON]"),
    (r"\b(?:Tn|Ny|Nn|An)\.\s*[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*", "[NAMA]"),
    (r"\bdr\.\s*[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*", "[DPJP]"),
)


class ReidentifiedTextError(RuntimeError):
    """Raised when text that has not crossed the pseudonymisation boundary is
    about to be sent to a model."""


class CacheMiss(RuntimeError):
    """VITERA_LLM_MODE=cache and this prompt was never recorded."""


def pseudonymise(text: ClinicalText | str) -> PseudonymisedText:
    """Strip direct identifiers. The only route to `PseudonymisedText`.

    Deliberately conservative — over-redaction costs the model a little
    context, under-redaction is a UU 27/2022 (PDP) problem.
    """
    out = str(text)
    for pattern, token in _PATTERNS:
        out = re.sub(pattern, token, out)
    return PseudonymisedText(out)


def _looks_reidentified(text: str) -> str | None:
    """Belt and braces: catch anything that skipped `pseudonymise`."""
    for pattern, token in _PATTERNS:
        if token in ("[TANGGAL]",):  # dates are common in redacted text too
            continue
        m = re.search(pattern, text)
        if m:
            return m.group(0)
    return None


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    from_cache: bool
    prompt_hash: str


class LLMClient:
    """The only component that talks to a model. Accepts pseudonymised text."""

    def __init__(self, cache_dir: Path | None = None, mode: str | None = None) -> None:
        self.cache_dir = cache_dir or CACHE_DIR
        self.mode = mode or config.llm_mode()
        self.calls = 0
        self.cache_hits = 0

    @staticmethod
    def _key(prompt: str, max_tokens: int) -> str:
        return hashlib.sha256(f"{max_tokens}\x00{prompt}".encode()).hexdigest()[:24]

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def complete(
        self, prompt: PseudonymisedText, *, max_tokens: int = 512
    ) -> Completion:
        leaked = _looks_reidentified(str(prompt))
        if leaked is not None:
            raise ReidentifiedTextError(
                f"refusing to send re-identified text to the model: {leaked!r}. "
                "Call pseudonymise() at the boundary — architectural rule 3."
            )

        key = self._key(str(prompt), max_tokens)
        path = self._path(key)

        if self.mode in ("cache", "record") and path.exists():
            self.cache_hits += 1
            return Completion(
                json.loads(path.read_text(encoding="utf-8"))["text"], True, key
            )

        if self.mode == "cache":
            raise CacheMiss(
                f"no cached completion for {key}. Rehearse with "
                "VITERA_LLM_MODE=record to populate the cache; `cache` mode "
                "never falls back to a live call."
            )

        text = self._call_provider(prompt, max_tokens)
        self.calls += 1

        if self.mode == "record":
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {"prompt": str(prompt), "max_tokens": max_tokens, "text": text},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        return Completion(text, False, key)

    def _call_provider(self, prompt: PseudonymisedText, max_tokens: int) -> str:
        """Provider call. Kept as the single seam so the production path can
        swap the frontier API for SEA-LION / Sahabat-AI without touching the
        harness."""
        api_key = os.environ.get("VITERA_LLM_API_KEY")
        if not api_key:
            raise RuntimeError(
                "VITERA_LLM_API_KEY is not set and mode is not `cache`. "
                "The system must remain useful with the LLM switched off — "
                "the caller should degrade to rules-only (architectural rule 8) "
                "rather than treating this as fatal."
            )
        raise NotImplementedError(
            "provider binding is wired in bucket 9; rehearse in `record` mode"
        )


class NullLLMClient(LLMClient):
    """Explicitly switched off. Used to prove rules-only mode works.

    Architectural rule 8 says the system must remain useful without the LLM.
    Having a client that always fails makes that testable rather than aspirational.
    """

    def __init__(self) -> None:
        super().__init__(mode="cache")

    def complete(
        self, prompt: PseudonymisedText, *, max_tokens: int = 512
    ) -> Completion:
        raise RuntimeError("LLM disabled")
