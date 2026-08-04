import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Lightweight in-memory store, so the AI pipeline stays the focus. The nightly
# scheduler's cross-day diff is what will need real persistence.
_in_memory_db: Dict[str, Dict[str, Any]] = {}


class ClaimRepository:
    def save_review(self, episode_id: str, report: Dict[str, Any]) -> Dict[str, Any]:
        previous = _in_memory_db.get(episode_id)
        record = {
            "episode_id": episode_id,
            "report": report,
            "previous": previous["report"] if previous else None,
        }
        _in_memory_db[episode_id] = record
        return record

    def get_review(self, episode_id: str) -> Optional[Dict[str, Any]]:
        return _in_memory_db.get(episode_id)
