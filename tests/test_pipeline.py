"""The three claims the architecture makes, one test each.

    pytest
"""

import json
from pathlib import Path

from dto.episode import RawEpisode
from dto.finding import DefectClass, Finding
from entities.claim_agent.nodes.spanfilter import spanfilter_node
from service.redact import PII_PATTERNS, to_safe_episode
from src.claim.usecase import ClaimUsecase

SAMPLE = Path(__file__).resolve().parent.parent / "sample-data" / "EP-2026-04471.json"


def _sample() -> RawEpisode:
    return RawEpisode(**json.loads(SAMPLE.read_text()))


def test_redaction_removes_pii():
    """Claim: no name, NIK or SEP can reach the model."""
    raw = _sample()
    safe = to_safe_episode(raw)

    blob = " ".join(doc.text for doc in safe.docs)
    for label, pattern in PII_PATTERNS.items():
        assert not pattern.search(blob), f"{label} survived redaction"
    for part in raw.demographics.name.split():
        assert part.lower() not in blob.lower(), f"patient name '{part}' survived redaction"
    # Structural, not just blanked: SafeEpisode has no field to leak from.
    assert not hasattr(safe, "demographics")


def test_narrator_cannot_lie():
    """Claim: a finding that cannot quote the record is deleted, not down-weighted."""
    episode = to_safe_episode(_sample())
    honest = Finding(
        cls=DefectClass.D8_UNDERCODED, src="model", suggested="99.04", conf=0.87,
        doc="d4", span="Transfusi PRC 2 kolf", msg="documented, never coded",
    )
    fabricated = Finding(
        cls=DefectClass.M2_UNSUPPORTED_DIAGNOSIS, src="model", code="A41.9", conf=0.99,
        doc="d4", span="riwayat diabetes mellitus tipe 2", msg="not in any document",
    )

    result = spanfilter_node({"episode": episode, "findings": [honest, fabricated]})

    assert result["findings"] == [honest]
    assert result["dropped"] == [fabricated]


def test_review_recovers_documented_tariff():
    """Claim: the pipeline finds money the record already supports."""
    report = ClaimUsecase().review_episode(_sample())

    classes = {f.cls for f in report.findings}
    assert DefectClass.M1_WRONG_SPECIFICITY in classes   # eGFR 22 -> N18.4, not N18.3
    assert DefectClass.D8_UNDERCODED in classes          # transfusion never coded
    assert DefectClass.C1_MISSING_DOC in classes         # MRI ordered, no result attached

    assert report.adjusted > report.baseline
    # The unattached MRI result is Rp 4.8jt exposed — under the Rp 5jt urgent
    # threshold in config.yaml, so it lands on the worklist, not the pager.
    assert report.at_risk == 4_800_000
    assert report.status == "review"

    # Every model finding shown to a coder quotes the document it cites.
    for finding in report.findings:
        if finding.src == "model":
            assert finding.span
            doc = next(d for d in to_safe_episode(_sample()).docs if d.doc_id == finding.doc)
            assert finding.span.casefold() in doc.text.casefold()
