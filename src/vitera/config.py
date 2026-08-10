"""Configuration loading, and the guards that make config a contract.

Two rules from the design brief are enforced here rather than trusted:

  - Thresholds live in ``config/thresholds.yaml``, never in code and never in
    a prompt. ``thresholds()`` is the only way to read one.
  - Every defect injection rate carries a citation. ``defects(strict=True)``
    refuses to return a config with an uncited rate, so ``make data`` fails
    loudly rather than producing a dataset whose prevalences are invented.
"""

from __future__ import annotations

import os
import random
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

DEFAULT_SEED = 20260731


class UncitedRateError(ValueError):
    """Raised when a defect rate has no citation. See the design brief, claims discipline."""


@dataclass(frozen=True, slots=True)
class Seeds:
    """Seeds are fixed and recorded everywhere. Recorded into every artifact
    so a figure can always be traced back to the run that made it."""

    master: int

    def for_stage(self, stage: str) -> int:
        """Deterministic per-stage seed, derived from the master.

        Using one master seed and deriving per stage means a change to the
        model stage cannot silently shift the generator's output.
        """
        return (self.master * 31 + sum(stage.encode())) % (2**31 - 1)

    def rng(self, stage: str) -> random.Random:
        return random.Random(self.for_stage(stage))


def seeds(master: int | None = None) -> Seeds:
    if master is None:
        master = int(os.environ.get("VITERA_SEED", DEFAULT_SEED))
    return Seeds(master=master)


@cache
def _load(name: str) -> Mapping[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"missing config: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not parse to a mapping")
    return data


def thresholds() -> Mapping[str, Any]:
    """The only route to a threshold value."""
    return _load("thresholds.yaml")


def sweep() -> Mapping[str, Any]:
    """Cadence and cohort filters. Scheduling only — never severity."""
    return _load("sweep.yaml")


def sites() -> Mapping[str, Any]:
    return _load("sites.yaml")


def defects(*, strict: bool = True) -> Mapping[str, Any]:
    """Load defect injection rates.

    With ``strict=True`` (the default, and what ``make data`` uses), a rate
    without a citation raises. Bucket 3 fills these in; until then the
    generator cannot run, which is the intended behaviour.
    """
    data = _load("defects.yaml")
    if strict:
        _assert_all_cited(data)
    return data


def _assert_all_cited(data: Mapping[str, Any]) -> None:
    uncited: list[str] = []

    for key, entry in (data.get("defects") or {}).items():
        if not isinstance(entry, dict):
            continue
        if entry.get("rate") is None or _is_todo(entry.get("citation")):
            uncited.append(f"defects.{key}")

    for key, entry in (data.get("temporal") or {}).items():
        if not isinstance(entry, dict):
            continue
        if _is_todo(entry.get("citation")):
            uncited.append(f"temporal.{key}")

    if uncited:
        raise UncitedRateError(
            "uncited or unset rates in config/defects.yaml: "
            + ", ".join(sorted(uncited))
            + "\nBucket 3 fills these from the literature synthesis. An uncited "
            "rate becomes a fabricated prevalence claim in the paper."
        )


def _is_todo(value: object) -> bool:
    return value is None or (
        isinstance(value, str) and value.strip().upper().startswith("TODO")
    )


def llm_mode() -> str:
    """``live`` | ``record`` | ``cache``. Rehearsing in ``record`` populates the
    cache that ``demo-offline`` replays."""
    mode = os.environ.get("VITERA_LLM_MODE", "cache").lower()
    if mode not in {"live", "record", "cache"}:
        raise ValueError(f"VITERA_LLM_MODE must be live|record|cache, got {mode!r}")
    return mode
