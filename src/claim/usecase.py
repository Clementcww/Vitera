import logging

from dto.episode import RawEpisode
from dto.exceptions import BadRequestError
from dto.report import ClaimReviewResponse
from entities.claim_agent.graph import claim_agent_graph
from service.redact import to_safe_episode
from src.claim.repository import ClaimRepository

logger = logging.getLogger("vitera.usecase")


class ClaimUsecase:
    def __init__(self) -> None:
        self.repository = ClaimRepository()

    def review_episode(self, raw: RawEpisode) -> ClaimReviewResponse:
        logger.info(f"--- [START REVIEW: {raw.episode_id} | day {raw.hospital_day}] ---")

        # 1. Redact. The only PII boundary in the system — everything downstream
        #    takes SafeEpisode, which has no field for a name or a NIK to sit in.
        logger.info("[Step 1/2] Redacting berkas...")
        episode = to_safe_episode(raw)
        if not episode.docs:
            raise BadRequestError(
                detail=(
                    f"Every document in {raw.episode_id} was withheld by fail-closed "
                    "redaction, so no analysis was produced. Reviewing an episode with "
                    "no readable text would return fabricated findings."
                ),
                instance=raw.episode_id,
            )
        if episode.dropped_docs:
            logger.warning(f"[Redact] withheld {len(episode.dropped_docs)} doc(s): {episode.dropped_docs}")

        # 2. Run the pipeline: deterministic checks, then the encoder, then the
        #    constraints on what the encoder is allowed to have said.
        logger.info("[Step 2/2] Invoking claim-integrity graph...")
        final_state = claim_agent_graph.invoke({"episode": episode, "findings": []})
        report: ClaimReviewResponse = final_state["report"]

        self.repository.save_review(raw.episode_id, report.model_dump())
        logger.info(f"--- [FINISH REVIEW: {raw.episode_id}] status {report.status} ---")
        return report
