"""Thresholds, and nothing else. ~30 lines on purpose.

Every number this node reads comes from config.yaml. If a threshold is written
here, the config file has stopped being the single place thresholds live.
"""

import logging

from dto.report import ClaimReviewResponse
from entities.claim_agent.nodes.grouper import apply_finding
from entities.claim_agent.state import ClaimAgentState
from service.config import config
from service.masters import tariff

logger = logging.getLogger("vitera.node.router")


def router_node(state: ClaimAgentState) -> ClaimAgentState:
    cfg = config()["router"]
    episode = state["episode"]
    baseline = state["baseline"]

    shown = [
        f for f in state.get("findings", [])
        if f.src == "rules" or (f.conf or 0.0) >= cfg["model_threshold"]
    ]

    codes = episode.claim.codes()
    for finding in shown:
        if finding.delta:
            codes = apply_finding(codes, finding)
    _, adjusted = tariff(codes)

    at_risk = sum(f.risk for f in shown)
    urgent = any(
        abs(f.delta) >= cfg["urgent_tariff_idr"] or f.risk >= cfg["urgent_tariff_idr"]
        for f in shown
    )

    report = ClaimReviewResponse(
        episode_id=episode.episode_id,
        hospital_day=episode.hospital_day,
        status="urgent" if urgent else ("review" if shown else "clean"),
        findings=shown,
        filtered_count=len(state.get("dropped", [])),
        dropped_docs=episode.dropped_docs,
        baseline=baseline,
        adjusted=adjusted or baseline,
        at_risk=at_risk,
    )
    logger.info(
        f"[ROUTE] {report.status.upper()} — {len(shown)} finding(s), "
        f"Rp {baseline:,} -> Rp {report.adjusted:,}, Rp {at_risk:,} at risk"
    )
    return {"report": report}
