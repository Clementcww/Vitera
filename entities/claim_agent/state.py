from typing import List, Optional, TypedDict

from dto.episode import SafeEpisode
from dto.finding import Finding
from dto.report import ClaimReviewResponse
from service.lexicon import Candidate


class ClaimAgentState(TypedDict, total=False):
    episode: SafeEpisode
    findings: List[Finding]
    dropped: List[Finding]          # model findings that failed the span filter
    candidates: List[Candidate]
    baseline: int
    report: Optional[ClaimReviewResponse]
