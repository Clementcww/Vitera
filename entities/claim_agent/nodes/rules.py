"""R1-R3: code validity. Set membership and table joins.

Precision here is 1.0 because these classes are *definitional*, not because
anything was tuned. A code either is or is not in the master. That is the
argument for deciding them deterministically instead of asking a model.
"""

import logging

from dto.finding import DefectClass, Finding
from entities.claim_agent.state import ClaimAgentState
from service.masters import AGE_BAND, EXCLUSIVE_PAIRS, ICD9, ICD10, SEX_ONLY

logger = logging.getLogger("vitera.node.rules")


def rules_node(state: ClaimAgentState) -> ClaimAgentState:
    episode = state["episode"]
    claim = episode.claim
    out = []

    # R1 — set membership against the masters.
    for code in [claim.principal_dx] + claim.secondary_dx:
        if code not in ICD10:
            out.append(Finding(
                cls=DefectClass.R1_INVALID_CODE, src="rules", code=code,
                msg=f"{code} is not in the ICD-10 master.",
            ))
    for code in claim.procedures:
        if code not in ICD9:
            out.append(Finding(
                cls=DefectClass.R1_INVALID_CODE, src="rules", code=code,
                msg=f"{code} is not in the ICD-9-CM master.",
            ))

    # R2 — demographic conflict.
    for code in claim.codes():
        required_sex = SEX_ONLY.get(code)
        if required_sex and required_sex != episode.sex:
            out.append(Finding(
                cls=DefectClass.R2_DEMOGRAPHIC_CONFLICT, src="rules", code=code,
                msg=f"{code} is valid only for sex {required_sex}; patient is {episode.sex}.",
            ))
        band = AGE_BAND.get(code)
        if band and not band[0] <= episode.age_years <= band[1]:
            out.append(Finding(
                cls=DefectClass.R2_DEMOGRAPHIC_CONFLICT, src="rules", code=code,
                msg=f"{code} expects age {band[0]}-{band[1]}; patient is {episode.age_years}.",
            ))

    # R3 — structural violation.
    coded = set(claim.codes())
    for left, right in EXCLUSIVE_PAIRS:
        if left in coded and right in coded:
            out.append(Finding(
                cls=DefectClass.R3_STRUCTURAL_VIOLATION, src="rules", code=left,
                suggested=right,
                msg=f"{left} and {right} are mutually exclusive on one episode.",
            ))

    logger.info(f"[R] {len(out)} code-validity defect(s)")
    return {"findings": state.get("findings", []) + out}
