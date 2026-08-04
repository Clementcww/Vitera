"""D8 step 1: candidate generation. A lookup, not a model.

Allowed to over-propose, because step 2 (the encoder) is the filter.
"""

import logging

from entities.claim_agent.state import ClaimAgentState
from service.lexicon import propose

logger = logging.getLogger("vitera.node.candidates")


def candidates_node(state: ClaimAgentState) -> ClaimAgentState:
    candidates = propose(state["episode"])
    logger.info(f"[D8] lexicon proposed {len(candidates)} candidate code(s)")
    return {"candidates": candidates}
