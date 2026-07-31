"""Reference data loaders for the generator.

Everything clinical lives in ``data/reference/*.yaml`` so that domain review
happens in YAML, not in Python. The loaders here are deliberately thin.

They also carry the unverified-content guard: while any reference entry has
``verified: false``, the generator warns loudly on every run and stamps
``domain_verified: false`` into the dataset manifest, so a corpus built from
unreviewed clinical mappings cannot quietly become a paper figure.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

REFERENCE_DIR = Path(__file__).resolve().parents[3] / "data" / "reference"


class UnverifiedReferenceWarning(UserWarning):
    """Clinical reference data has not been reviewed by the domain owner."""


@dataclass(frozen=True, slots=True)
class Signal:
    """Clinical evidence that makes a comorbidity visible before it is written."""

    kind: str  # LAB | MED | VITALS | PROCEDURE
    code: str
    label: str
    direction: str | None = None  # high | low | abnormal
    threshold: str | None = None

    def render(self) -> str:
        """How this appears as a line in the record."""
        if self.direction is None:
            return f"{self.label}"
        arrow = {"high": "↑", "low": "↓", "abnormal": "abnormal"}[self.direction]
        return f"{self.label} {arrow} ({self.threshold})"


@dataclass(frozen=True, slots=True)
class Comorbidity:
    icd10: str
    label: str
    prevalence: float
    severity_weight: int
    signals: tuple[Signal, ...]
    doc_phrases: tuple[str, ...]
    verified: bool


@dataclass(frozen=True, slots=True)
class CBGGroup:
    cbg: str
    label: str
    primary: str
    los_min: int
    los_max: int
    base_tariff_idr: int
    required_procedure: str | None
    procedure_label: str | None
    verified: bool


def _load(name: str) -> Mapping[str, Any]:
    path = REFERENCE_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"missing reference data: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not parse to a mapping")
    return data


@lru_cache(maxsize=None)
def comorbidities() -> tuple[Comorbidity, ...]:
    raw = _load("comorbidities.yaml")
    out = []
    for c in raw["comorbidities"]:
        out.append(
            Comorbidity(
                icd10=c["icd10"],
                label=c["label"],
                prevalence=float(c["prevalence"]),
                severity_weight=int(c["severity_weight"]),
                signals=tuple(
                    Signal(
                        kind=s["kind"],
                        code=s["code"],
                        label=s["label"],
                        direction=s.get("direction"),
                        threshold=s.get("threshold"),
                    )
                    for s in c["signals"]
                ),
                doc_phrases=tuple(c["doc_phrases"]),
                verified=bool(c.get("verified", False)),
            )
        )
    return tuple(out)


@lru_cache(maxsize=None)
def cbg_groups() -> tuple[CBGGroup, ...]:
    raw = _load("cbg_groups.yaml")
    return tuple(
        CBGGroup(
            cbg=g["cbg"],
            label=g["label"],
            primary=g["primary"],
            los_min=int(g["los"][0]),
            los_max=int(g["los"][1]),
            base_tariff_idr=int(g["base_tariff_idr"]),
            required_procedure=g.get("required_procedure"),
            procedure_label=g.get("procedure_label"),
            verified=bool(g.get("verified", False)),
        )
        for g in raw["groups"]
    )


@lru_cache(maxsize=None)
def severity_multipliers() -> Mapping[int, float]:
    raw = _load("cbg_groups.yaml")
    return {int(k): float(v) for k, v in raw["severity_multipliers"].items()}


@lru_cache(maxsize=None)
def plausible_comorbidities(cbg: str) -> tuple[str, ...]:
    """Which comorbidities may co-occur with a given group.

    Without this the generator produces clinically absurd episodes — a sectio
    caesarea with COPD — which a koder spots instantly and which would
    discredit the demo faster than any model error.
    """
    raw = _load("cbg_groups.yaml")["plausible_comorbidities"]
    return tuple(raw.get(cbg, raw["default"]))


def comorbidity_by_code(code: str) -> Comorbidity:
    for c in comorbidities():
        if c.icd10 == code:
            return c
    raise KeyError(f"unknown comorbidity: {code}")


def domain_verified() -> bool:
    """True only when every clinical reference entry has been domain-reviewed."""
    files_ok = all(
        bool(_load(n).get("verified", False))
        for n in ("comorbidities.yaml", "cbg_groups.yaml")
    )
    entries_ok = all(c.verified for c in comorbidities()) and all(
        g.verified for g in cbg_groups()
    )
    return files_ok and entries_ok


def warn_if_unverified() -> None:
    """Called once per generator run. Loud by design."""
    if domain_verified():
        return
    unverified_c = [c.icd10 for c in comorbidities() if not c.verified]
    unverified_g = [g.cbg for g in cbg_groups() if not g.verified]
    warnings.warn(
        "\n"
        + "=" * 72
        + "\nCLINICAL REFERENCE DATA IS NOT DOMAIN-VERIFIED.\n"
        + f"  comorbidities unverified: {len(unverified_c)}\n"
        + f"  CBG groups unverified:    {len(unverified_g)}\n"
        + "Codes, thresholds, severity weights and tariffs are PLACEHOLDERS\n"
        + "written without a tariff reference. No number from this corpus may\n"
        + "appear in the paper or the deck until data/reference/*.yaml has been\n"
        + "reviewed and `verified` set to true.\n"
        + "The dataset manifest records domain_verified: false.\n"
        + "=" * 72,
        UnverifiedReferenceWarning,
        stacklevel=2,
    )


def signals_for(codes: Sequence[str]) -> tuple[Signal, ...]:
    out: list[Signal] = []
    for c in codes:
        out.extend(comorbidity_by_code(c).signals)
    return tuple(out)
