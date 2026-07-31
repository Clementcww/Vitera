"""Config guards. These enforce claims discipline mechanically."""

from __future__ import annotations

import pytest

from vitera import config


def test_uncited_defect_rates_refuse_to_load() -> None:
    """Until bucket 3 cites every rate, `make data` must not run.

    When this test starts failing, bucket 3 is done — swap it for the
    positive assertion below it.
    """
    with pytest.raises(config.UncitedRateError):
        config.defects(strict=True)


def test_uncited_rates_are_still_readable_non_strictly() -> None:
    data = config.defects(strict=False)
    assert set(data["defects"]) == {f"D{i}" for i in range(1, 9)}


def test_negatives_are_made_by_code_mutation_only() -> None:
    """Regenerated text carries stylistic fingerprints and the model learns
    those instead of clinical reasoning."""
    assert config.defects(strict=False)["negative_construction"] == "code_mutation_only"


def test_thresholds_are_not_in_code() -> None:
    t = config.thresholds()
    assert t["router"]["default"]["flag_at"] > t["router"]["default"]["abstain_below"]
    assert t["budget"]["max_tool_calls"] == 8


def test_sweep_config_is_scheduling_only() -> None:
    """architectural rule 11 — the sweep grants no capability. If a severity
    threshold ever appears in sweep.yaml, that rule has been broken."""
    s = config.sweep()
    flat = str(s)
    assert "flag_at" not in flat
    assert "abstain" not in flat
    assert s["cohort"]["min_los_so_far"] == 2


def test_holdout_is_by_hospital_not_by_row() -> None:
    assert config.sites()["split_policy"]["by"] == "site_id"


def test_seeds_are_derived_deterministically_per_stage() -> None:
    s = config.seeds(20260731)
    assert s.for_stage("generator") == config.seeds(20260731).for_stage("generator")
    assert s.for_stage("generator") != s.for_stage("cross_encoder")


def test_llm_mode_rejects_nonsense(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VITERA_LLM_MODE", "yolo")
    with pytest.raises(ValueError):
        config.llm_mode()
