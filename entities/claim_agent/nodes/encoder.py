"""The model node. One question, asked twice.

    "Does this clinical text support this code?"

Asked of a *candidate* code, a yes means the episode is under-coded (D8) — or,
when the candidate is a more specific sibling of something already coded, that
the specificity is wrong (M1). Asked of a *submitted* code, a no means the
diagnosis is unsupported (M2).

Same encoder, same question, four defect classes. That is the whole argument
for a cross-encoder over a per-class classifier.
"""

import logging

from dto.finding import DefectClass, Finding
from dto.types import SafeText
from entities.claim_agent.state import ClaimAgentState
from service.config import config
from service.crossencoder import is_stubbed, verify
from service.masters import MORE_SPECIFIC, describe

logger = logging.getLogger("vitera.node.encoder")


def _specificity_parent(candidate_code: str, coded: list[str]) -> str | None:
    """The coded code this candidate is a more specific version of, if any."""
    return next((c for c in coded if candidate_code in MORE_SPECIFIC.get(c, [])), None)


def encoder_node(state: ClaimAgentState) -> ClaimAgentState:
    episode = state["episode"]
    coded = episode.claim.codes()
    text_by_doc = {doc.doc_id: doc.text for doc in episode.docs}
    out = []

    # --- Pass 1: candidates the record may support but the claim does not carry.
    candidates = [c for c in state.get("candidates", []) if c.code not in coded]
    scores = verify(
        [(describe(c.code), text_by_doc[c.doc]) for c in candidates],
        [c.prior for c in candidates],
    )
    for candidate, score in zip(candidates, scores):
        parent = _specificity_parent(candidate.code, coded)
        if parent:
            out.append(Finding(
                cls=DefectClass.M1_WRONG_SPECIFICITY, src="model",
                code=parent, suggested=candidate.code, conf=round(score, 3),
                doc=candidate.doc, span=candidate.span,
                msg=f"Record supports {describe(candidate.code)}, not the coded {parent}.",
            ))
        else:
            out.append(Finding(
                cls=DefectClass.D8_UNDERCODED, src="model",
                suggested=candidate.code, conf=round(score, 3),
                doc=candidate.doc, span=candidate.span,
                msg=f"{describe(candidate.code)} is documented but was never coded.",
            ))

    # --- Pass 2: submitted codes the record may not support at all.
    if is_stubbed():
        # The stub has no opinion on a code no lexicon proposed, and inventing
        # one would make the model look better than it is.
        logger.warning("[M2] skipped — encoder is stubbed, no weights configured")
    else:
        joined = SafeText("\n".join(doc.text for doc in episode.docs))
        support = verify([(describe(code), joined) for code in coded], [0.0] * len(coded))
        threshold = config()["router"]["model_threshold"]
        for code, score in zip(coded, support):
            if score < 1 - threshold:
                out.append(Finding(
                    cls=DefectClass.M2_UNSUPPORTED_DIAGNOSIS, src="model",
                    code=code, conf=round(1 - score, 3),
                    msg=f"No documentation in the berkas supports {code}.",
                ))

    logger.info(f"[M] {len(out)} model finding(s){' (STUBBED)' if is_stubbed() else ''}")
    return {"findings": state.get("findings", []) + out}
