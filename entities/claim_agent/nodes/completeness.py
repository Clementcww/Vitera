"""C1-C3: berkas completeness. Metadata and stage checklists, no model.

The largest documented driver of pending BPJS claims is not mis-coding, it is
incomplete documentation — and that is decidable without asking anyone.
"""

import logging
import re

from dto.finding import DefectClass, Finding
from entities.claim_agent.state import ClaimAgentState
from service.masters import MUST_BE_SIGNED, ORDER_EVIDENCE, PROC_EVIDENCE, REQUIRED_DOCS

logger = logging.getLogger("vitera.node.completeness")


def completeness_node(state: ClaimAgentState) -> ClaimAgentState:
    episode = state["episode"]
    present = {doc.doc_type for doc in episode.docs}
    out = []

    stages = ["checkin", "instay"] + (["checkout"] if episode.discharged else [])
    for stage in stages:
        for required in REQUIRED_DOCS[stage]:
            if required not in present:
                out.append(Finding(
                    cls=DefectClass.C1_MISSING_DOC, src="rules",
                    msg=f"{required} missing for stage {stage}.",
                ))

    for doc in episode.docs:
        if doc.doc_type in MUST_BE_SIGNED and doc.signed is not True:
            out.append(Finding(
                cls=DefectClass.C2_MISSING_SIGNATURE, src="rules", doc=doc.doc_id,
                msg=f"{doc.doc_type} carries no DPJP signature.",
            ))

    for doc in episode.docs:
        for pattern, required, at_risk in ORDER_EVIDENCE:
            if re.search(pattern, doc.text, re.I) and required not in present:
                out.append(Finding(
                    cls=DefectClass.C1_MISSING_DOC, src="rules", doc=doc.doc_id,
                    risk=at_risk,
                    msg=f"Order found in {doc.doc_type}, no {required} result attached.",
                ))

    for procedure in episode.claim.procedures:
        if PROC_EVIDENCE.get(procedure) not in present:
            out.append(Finding(
                cls=DefectClass.C3_PROCEDURE_NO_EVIDENCE, src="rules", code=procedure,
                msg=f"Procedure {procedure} coded with no evidence document attached.",
            ))

    logger.info(f"[C] {len(out)} completeness defect(s)")
    return {"findings": state.get("findings", []) + out}
