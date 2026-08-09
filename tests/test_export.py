"""Bucket 12 — the UI export boundary.

The workbench renders whatever this exporter writes, so three architectural
rules survive to the screen only if they survive this file. These tests do not
need a checkpoint: they run the rules-only path, which is also the path a
hospital sees when the model layer is down.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from vitera.api.export import _documents, build, money_view
from vitera.contracts import (
    ClinicalText,
    Document,
    Episode,
    SecondaryDiagnosis,
)
from vitera.generator.corpus import load_jsonl
from vitera.generator.defects import CodedClaim
from vitera.grouper.grouper import Grouper

DATA = Path("data/generated")
NO_MODEL = Path("models/does-not-exist")

pytestmark = pytest.mark.skipif(
    not (DATA / "test.jsonl").exists(),
    reason="corpus not generated; run `make data`",
)


@pytest.fixture(scope="module")
def payload() -> dict:
    rows = load_jsonl(DATA / "test.jsonl")
    return build(rows, cohort=6, seed=1, model_dir=NO_MODEL)


# ---------------------------------------------------------------------------
# Rule 6 — every flag that reaches the screen cites the record verbatim
# ---------------------------------------------------------------------------


def test_every_exported_span_verifies_against_the_exported_document(
    payload: dict,
) -> None:
    """The client re-runs exactly this check before rendering. If the exporter
    can emit a span that fails it, the browser silently drops findings and the
    queue looks shorter than it is — which is the worst of both worlds."""
    checked = 0
    for ep in payload["episodes"]:
        docs = {d["doc_id"]: d for d in ep["documents"]}
        for f in ep["flags"]:
            s = f["span"]
            doc = docs.get(s["doc_id"])
            assert doc is not None, f"{ep['episode_id']}: span cites a missing doc"
            assert not doc["absent"], (
                f"{ep['episode_id']}: span cites a document dropped from the claim"
            )
            assert doc["text"][s["start"] : s["end"]] == s["text"]
            checked += 1
    assert checked, "no flags exported — this test would pass vacuously"


def test_documents_never_include_the_future() -> None:
    """On day 3 there is no resume medis. Exporting it would let a flag cite a
    document the DPJP has not written yet."""
    ep = Episode(
        episode_id="EP1",
        site_id="RS001",
        admission_date=date(2026, 1, 1),
        primary_dx="J18.9",
        secondary_dx=(SecondaryDiagnosis("E11.9", 1, None),),
        procedures=(),
        events=(),
        documents=(
            Document("berkas_klaim", 0, ClinicalText("berkas")),
            Document("cppt_hari_3", 3, ClinicalText("hari 3")),
            Document("resume_medis", 7, ClinicalText("resume")),
        ),
        discharge_day=7,
    )
    claim = CodedClaim(
        episode_id="EP1",
        primary_dx="J18.9",
        secondary_dx=(),
        procedures=(),
        documents_present=("berkas_klaim", "cppt_hari_3", "resume_medis"),
        sep_number="SEP1",
        admission_date_claimed=date(2026, 1, 1),
    )
    ids = [d["doc_id"] for d in _documents(ep, claim, 3)]
    assert ids == ["berkas_klaim", "cppt_hari_3"]


def test_a_dropped_document_is_exported_as_absent_not_omitted() -> None:
    """The koder needs to see that the resume medis is missing. An omitted row
    is a gap they have to notice; an absent row is a finding they can read."""
    ep = Episode(
        episode_id="EP1",
        site_id="RS001",
        admission_date=date(2026, 1, 1),
        primary_dx="J18.9",
        secondary_dx=(),
        procedures=(),
        events=(),
        documents=(
            Document("berkas_klaim", 0, ClinicalText("berkas")),
            Document("resume_medis", 2, ClinicalText("rahasia")),
        ),
        discharge_day=2,
    )
    claim = CodedClaim(
        episode_id="EP1",
        primary_dx="J18.9",
        secondary_dx=(),
        procedures=(),
        documents_present=("berkas_klaim",),
        sep_number="SEP1",
        admission_date_claimed=date(2026, 1, 1),
    )
    docs = {d["doc_id"]: d for d in _documents(ep, claim, 2)}
    assert docs["resume_medis"]["absent"] is True
    # And its text does not leak: a document not on the claim file is not
    # something the verifier is looking at.
    assert docs["resume_medis"]["text"] == ""


# ---------------------------------------------------------------------------
# Rule 7 — the grouper is the only source of money
# ---------------------------------------------------------------------------


def test_ungroupable_exports_no_tariff(payload: dict) -> None:
    for ep in payload["episodes"]:
        for block in (ep["money"]["now"], ep["money"]["if_confirmed"]):
            if block["ungroupable_reason"] is not None:
                assert block["tariff_idr"] is None
                assert block["cbg_code"] is None


def test_money_is_never_negative_and_is_badged_grouper(payload: dict) -> None:
    for ep in payload["episodes"]:
        assert ep["money"]["source"] == "grouper"
        d = ep["money"]["delta_idr"]
        assert d is None or d >= 0


def test_confirming_a_query_never_lowers_the_tariff() -> None:
    """`if_confirmed` adds back only codes whose remedy is a DPJP query, so it
    can only hold severity level or raise it. A negative delta would mean the
    strip is telling a koder that documenting care costs them money."""
    grouper = Grouper()
    claim = CodedClaim(
        episode_id="EP1",
        primary_dx="J18.9",
        secondary_dx=("E11.9", "I10"),
        procedures=(),
        documents_present=("berkas_klaim",),
        sep_number="SEP1",
        admission_date_claimed=date(2026, 1, 1),
    )

    class _Fake:
        class decision:  # noqa: N801 - test double
            flags = ()

    money = money_view(grouper, claim, _Fake)  # type: ignore[arg-type]
    assert money["delta_idr"] == 0
    assert money["now"]["tariff_idr"] == money["if_confirmed"]["tariff_idr"]


# ---------------------------------------------------------------------------
# Rule 8 — a degraded run must not render as a full one
# ---------------------------------------------------------------------------


def test_without_a_checkpoint_the_export_is_advisory_and_says_what_it_missed(
    payload: dict,
) -> None:
    assert payload["generated"]["advisory"] is True
    assert payload["generated"]["model_unavailable"]
    for ep in payload["episodes"]:
        assert ep["advisory"] is True
        # The judgment classes are exactly what rules cannot reach (bucket 5).
        assert {"D2", "D3", "D4", "D7"} <= set(ep["classes_unchecked"])
        assert set(ep["classes_checked"]) == {"D1", "D6", "D8"}


# ---------------------------------------------------------------------------
# Cohort honesty
# ---------------------------------------------------------------------------


def test_the_demo_cohort_declares_that_it_is_not_a_random_sample(
    payload: dict,
) -> None:
    """The demo cohort is stratified so the queue actually shows the product.
    That is fine, and it is only fine because the payload says so — no measured
    result is ever computed from it."""
    assert "NOT a random sample" in payload["generated"]["cohort_selection"]


def test_surface_is_the_pipeline_per_day_not_a_diff(payload: dict) -> None:
    """Concurrent monitoring is the discharge pipeline invoked N times. Every
    day of every episode's stay must be present — a diff would have gaps.

    The surface always spans the WHOLE stay, day 0 to the last day known. The
    workbench's own `day` may be earlier than that, because a share of the
    cohort is evaluated mid-stay, which is the concurrent product rather than
    an inconsistency; asserting against `ep["day"]` would silently forbid it.
    """
    by_ep: dict[str, set[int]] = {}
    for c in payload["surface"]["cells"]:
        by_ep.setdefault(c["episode_id"], set()).add(c["d"])
    for ep in payload["episodes"]:
        days = by_ep[ep["episode_id"]]
        last = (
            ep["discharge_day"] if ep["discharge_day"] is not None else ep["los_so_far"]
        )
        assert days == set(range(last + 1))
        assert ep["day"] in days


def test_a_share_of_the_cohort_is_still_on_the_ward(payload: dict) -> None:
    """The one repair window that actually expires needs a patient on a ward.

    A cohort evaluated entirely at discharge makes every Query row point at
    someone who has already gone home, and makes the unit summary's lead figure
    structurally zero. `still_admitted` must therefore be true for some of it,
    and each such episode must have been run before its own discharge day.
    """
    admitted = [e for e in payload["episodes"] if e["still_admitted"]]
    assert admitted, "no episode is mid-stay; the concurrent claim has no demo"
    assert payload["generated"]["on_ward"] == len(admitted)
    for e in admitted:
        assert e["discharge_day"] is None or e["day"] < e["discharge_day"]
        # Days 0-1 carry too little signal to run, per config/sweep.yaml.
        assert e["day"] >= 2


def test_payload_is_json_serialisable(payload: dict) -> None:
    """It is written to disk and fetched by a browser; a stray dataclass or
    Enum here fails at `make ui-data`, not at review."""
    json.dumps(payload, ensure_ascii=False)
