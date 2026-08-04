import logging

from fastapi import APIRouter

from dto.episode import RawEpisode
from dto.exceptions import BadRequestError
from dto.report import ClaimReviewResponse
from src.claim.usecase import ClaimUsecase

logger = logging.getLogger("vitera.delivery")

router = APIRouter(prefix="/api/v1/claims", tags=["Vitera Claim Integrity Agent"])

usecase = ClaimUsecase()


@router.post("/review", response_model=ClaimReviewResponse)
async def review_claim(episode: RawEpisode) -> ClaimReviewResponse:
    """Review one episode's berkas against its submitted codes.

    Deterministic completeness and code-validity checks, cross-encoder
    verification of everything else, and a rupiah figure on each finding.
    """
    logger.info(f"Received review request for episode {episode.episode_id}")
    return usecase.review_episode(episode)


@router.get("/review/{episode_id}", response_model=ClaimReviewResponse)
async def get_review(episode_id: str) -> ClaimReviewResponse:
    record = usecase.repository.get_review(episode_id)
    if not record:
        raise BadRequestError(detail=f"No review stored for {episode_id}.", instance=episode_id)
    return ClaimReviewResponse(**record["report"])
