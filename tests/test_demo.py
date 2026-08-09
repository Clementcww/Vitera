"""Bucket 9 — the end-to-end path, as a test rather than a promise.

Criterion 8 asks for a run that does not crash across 20 consecutive cases and
that degrades gracefully when the model layer is down. Both are properties a
rehearsal can only sample; here they are asserted, so a regression on day 7
fails CI instead of being discovered on stage.

No provider is called. `use_llm=False` exercises the path a judge sees with no
key, which is also the path that has to survive a dead provider.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vitera.api.demo import run
from vitera.generator.corpus import load_jsonl

DATA = Path("data/generated")
NO_MODEL = Path("models/does-not-exist")

pytestmark = pytest.mark.skipif(
    not (DATA / "test.jsonl").exists(),
    reason="corpus not generated; run `make data`",
)


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return load_jsonl(DATA / "test.jsonl")[:20]


def test_twenty_consecutive_cases_do_not_crash(rows: list[dict]) -> None:
    tally, detail = run(rows, model_dir=NO_MODEL, use_llm=False, verbose=False)
    assert tally.errors == 0, "an episode raised; the demo is not stage-safe"
    assert tally.episodes == len(rows)
    assert len(detail) == len(rows)


def test_missing_model_degrades_to_advisory_rather_than_failing(
    rows: list[dict],
) -> None:
    """Rule 8. The run completes, and every episode says out loud that the
    model layer was not there. Silence here is the dangerous outcome: a
    rules-only pass rendering as a full check."""
    tally, _ = run(rows, model_dir=NO_MODEL, use_llm=False, verbose=False)
    assert tally.errors == 0
    assert tally.advisory == tally.episodes


def test_every_flag_shown_carries_a_verbatim_span(rows: list[dict]) -> None:
    """Rule 6, measured at the point of display."""
    tally, _ = run(rows, model_dir=NO_MODEL, use_llm=False, verbose=False)
    assert tally.spans_dropped == 0
    assert tally.spans_ok == tally.flags


def test_budgets_are_never_breached_on_the_demo_cohort(rows: list[dict]) -> None:
    """Rule 9. A breach is not a crash, but on a 20-episode demo it means the
    bounds are set wrong, and it would show as a truncated fix list on stage."""
    tally, _ = run(rows, model_dir=NO_MODEL, use_llm=False, verbose=False)
    assert tally.breaches == 0
