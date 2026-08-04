"""Verbatim-quote enforcement. The model may not claim what it cannot quote.

A model finding whose span is not literally present in the document it cites is
deleted, not down-weighted. Whitespace and case normalisation only — no fuzzy
matching, because fuzzy matching is exactly the hole a confident hallucination
walks through.

Deleted findings are counted and reported. `test_narrator_cannot_lie.py` is the
test that defends this.
"""

import logging
import re

from entities.claim_agent.state import ClaimAgentState

logger = logging.getLogger("vitera.node.spanfilter")


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def spanfilter_node(state: ClaimAgentState) -> ClaimAgentState:
    episode = state["episode"]
    text_by_doc = {doc.doc_id: _normalise(doc.text) for doc in episode.docs}

    kept, dropped = [], []
    for finding in state.get("findings", []):
        if finding.src == "rules" or finding.span is None:
            kept.append(finding)
        elif _normalise(finding.span) in text_by_doc.get(finding.doc, ""):
            kept.append(finding)
        else:
            dropped.append(finding)

    if dropped:
        logger.warning(f"[SPAN] deleted {len(dropped)} finding(s) that could not quote the record")
    return {"findings": kept, "dropped": dropped}
