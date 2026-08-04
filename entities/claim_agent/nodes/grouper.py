"""INA-CBG grouping: code set -> group -> tariff, and what each finding is worth.

The money is the product. A finding with no rupiah attached is a coder's chore;
a finding with a delta is a decision.
"""

import logging

from dto.finding import DefectClass
from entities.claim_agent.state import ClaimAgentState
from service.masters import tariff

logger = logging.getLogger("vitera.node.grouper")


def apply_finding(codes: list[str], finding) -> list[str]:
    """The code set as it would be if this finding were acted on."""
    if finding.cls == DefectClass.M1_WRONG_SPECIFICITY:
        return [finding.suggested if c == finding.code else c for c in codes]
    if finding.cls == DefectClass.D8_UNDERCODED:
        return codes + [finding.suggested]
    return codes


def grouper_node(state: ClaimAgentState) -> ClaimAgentState:
    codes = state["episode"].claim.codes()
    group, baseline = tariff(codes)

    for finding in state.get("findings", []):
        if not finding.suggested:
            continue
        _, adjusted = tariff(apply_finding(codes, finding))
        finding.delta = adjusted - baseline if adjusted else 0

    logger.info(f"[GRP] {group or 'ungrouped'} baseline Rp {baseline:,}")
    return {"baseline": baseline}
