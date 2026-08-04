"""Config guards. These enforce claims discipline mechanically."""

from __future__ import annotations

import pytest

from vitera import config


def test_every_defect_rate_is_cited() -> None:
    """Bucket 3 landed: strict load now succeeds. If this ever raises again,
    someone added a rate without a source."""
    data = config.defects(strict=True)
    assert set(data["defects"]) == {f"D{i}" for i in range(1, 9)}
    for name, entry in data["defects"].items():
        assert entry["rate"] is not None, name
        assert 0.0 < entry["rate"] < 1.0, name
        assert len(entry["citation"]) > 40, f"{name} citation is too thin to be one"
        assert entry["derivation"] in {"measured", "apportioned", "assumed"}, name


def test_the_guard_still_fires_on_an_uncited_rate() -> None:
    """The mechanism, not the current data. Guards rot when nothing tests them."""
    poisoned = {
        "defects": {"D1": {"rate": None, "citation": "TODO"}},
        "temporal": {},
    }
    with pytest.raises(config.UncitedRateError):
        config._assert_all_cited(poisoned)


def test_undercoding_outnumbers_overcoding() -> None:
    """Opitasari & Nurwahyuni (2018) Table 4: 13.3% undercoded vs 6.7%
    overcoded. The generator must preserve that asymmetry — it is the empirical
    basis for the paper's undercoding narrative."""
    d = config.defects(strict=False)
    assert d["directionality"]["undercode_to_overcode_ratio"] > 1.0


def test_the_lead_time_assumption_is_labelled_as_one() -> None:
    """No Indonesian study reports the gap between clinical signal and
    documentation. If this ever claims to be `measured`, someone has invented a
    source — and detection_lead_time becomes an unsupportable claim."""
    t = config.defects(strict=False)["temporal"]
    assert t["signal_to_doc_gap_days"]["derivation"] == "assumed"
    assert "NO SOURCE" in t["signal_to_doc_gap_days"]["citation"]
    # By contrast, the undocumented rate IS measured.
    assert t["undocumented_rate"]["derivation"] == "measured"
    assert t["undocumented_rate"]["rate"] == 0.686


def test_lowest_resourced_hospital_class_is_held_out() -> None:
    """Class D appears only in test. Degradation there is the fairness finding,
    not a bug to be trained away."""
    s = config.sites()
    class_d = [x["id"] for x in s["sites"] if x["class"] == "D"]
    assert class_d
    assert all(i in s["split_policy"]["test"] for i in class_d)


def test_no_site_appears_in_both_splits() -> None:
    s = config.sites()["split_policy"]
    assert not set(s["train"]) & set(s["test"])


def test_negatives_are_made_by_code_mutation_only() -> None:
    """Regenerated text carries stylistic fingerprints and the model learns
    those instead of clinical reasoning."""
    assert config.defects(strict=False)["negative_construction"] == "code_mutation_only"


def test_thresholds_are_not_in_code() -> None:
    t = config.thresholds()
    assert t["router"]["default"]["flag_at"] >= t["router"]["default"]["abstain_below"]
    assert t["budget"]["max_tool_calls"] == 8


def test_an_empty_abstention_band_is_declared_not_stumbled_into() -> None:
    """`abstain_below == flag_at` empties the grey zone.

    That is a legitimate state — bucket 8's cross-encoder separates the
    synthetic corpus so cleanly that the recall threshold sits above the
    false-positive threshold — but it must never happen by accident. If the two
    coincide, the results file has to say so (`bands_crossed`), and the
    thresholds file has to explain why.
    """
    import json
    from pathlib import Path

    t = config.thresholds()["router"]["default"]
    if t["flag_at"] > t["abstain_below"]:
        return

    results = Path("results/cross_encoder.json")
    assert results.exists(), (
        "thresholds leave no abstention band, and no bucket-8 result file "
        "explains it. Run `make baselines` or restore a band."
    )
    op = json.loads(results.read_text(encoding="utf-8"))["operating_point"]["default"]
    assert op["bands_crossed"] is True
    assert op["flag_at"] == t["flag_at"]


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
