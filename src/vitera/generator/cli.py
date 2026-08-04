"""`make data` — build and freeze the corpus.

Writes JSONL plus a MANIFEST.json carrying the seed, the config hashes, the
domain-verification state and the corpus statistics. The manifest is what makes
a figure traceable back to the run that produced it.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from vitera import config
from vitera.generator import reference as ref
from vitera.generator.defects import inject
from vitera.generator.episode import generate_corpus

CONFIG_FILES = ("defects.yaml", "sites.yaml", "thresholds.yaml", "sweep.yaml")
REFERENCE_FILES = ("comorbidities.yaml", "cbg_groups.yaml", "icd10_labels.yaml")


def _default(o: Any) -> Any:
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    if isinstance(o, date):
        return o.isoformat()
    if hasattr(o, "name") and hasattr(o, "value"):  # Enum
        return o.name
    raise TypeError(f"not serialisable: {type(o)}")


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def build(n: int, seed: int, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    seeds = config.seeds(seed)
    rng = seeds.rng("defect_injection")

    corpus = generate_corpus(n, seed=seed)
    sites = {s["id"]: s for s in config.sites()["sites"]}

    rows = []
    for ep, gt in corpus:
        claim, labels, eligible = inject(ep, gt, rng)
        rows.append(
            {
                "episode": ep,
                "ground_truth": gt,
                "claim": claim,
                "defects": labels,
                "eligible_for": eligible,
                "split": sites[ep.site_id]["split"],
            }
        )

    for split in ("train", "test"):
        path = out / f"{split}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for r in rows:
                if r["split"] == split:
                    fh.write(json.dumps(r, default=_default, ensure_ascii=False) + "\n")

    stats = _stats(rows)
    manifest = {
        "generated_by": "vitera.generator.cli",
        "seed": seed,
        "n_episodes": n,
        "stage_seeds": {
            s: seeds.for_stage(s) for s in ("generator", "defect_injection")
        },
        "domain_verified": ref.domain_verified(),
        "config_hashes": {f: _hash_file(config.CONFIG_DIR / f) for f in CONFIG_FILES},
        "reference_hashes": {
            f: _hash_file(ref.REFERENCE_DIR / f) for f in REFERENCE_FILES
        },
        "holdout": "by site_id, never by row",
        "negative_construction": "code_mutation_only",
        "stats": stats,
    }
    (out / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def _stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    defect_counts: Counter[str] = Counter()
    for r in rows:
        for d in r["defects"]:
            defect_counts[d.defect_class.name] += 1
    sec_total = sum(len(r["ground_truth"].secondary_dx) for r in rows)
    undoc = sum(len(r["ground_truth"].undocumented_dx) for r in rows)
    return {
        "episodes": n,
        "train": sum(1 for r in rows if r["split"] == "train"),
        "test": sum(1 for r in rows if r["split"] == "test"),
        "clean_claims": sum(1 for r in rows if not r["defects"]),
        "clean_claim_share": round(sum(1 for r in rows if not r["defects"]) / n, 4),
        "defects_per_class": {k: defect_counts[k] for k in sorted(defect_counts)},
        # Configured vs realised, because they differ and the difference matters.
        # An injector returns None when the episode cannot carry that defect —
        # D6 needs a procedure, and only 3 of 18 CBG groups have one, so its
        # realised rate is a fraction of the configured rate. Reporting only the
        # configured rate would misstate the corpus in the data card.
        "defect_rate_per_class": {
            k: {
                "configured": float(config.defects(strict=False)["defects"][k]["rate"]),
                "realised": round(defect_counts[k] / n, 4),
            }
            for k in sorted(defect_counts)
        },
        "mean_secondary_dx": round(sec_total / n, 3),
        "undocumented_secondary_dx_rate": round(undoc / sec_total, 4),
        "severity_distribution": {
            str(k): v
            for k, v in sorted(
                Counter(r["ground_truth"].severity for r in rows).items()
            )
        },
        "mean_los": round(sum(r["episode"].discharge_day or 0 for r in rows) / n, 2),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Generate the frozen Vitera corpus")
    p.add_argument("--n", type=int, default=4000)
    p.add_argument("--seed", type=int, default=config.DEFAULT_SEED)
    p.add_argument("--out", type=Path, default=Path("data/generated"))
    a = p.parse_args()

    m = build(a.n, a.seed, a.out)
    print(json.dumps(m["stats"], indent=2))
    print(f"\nwrote {a.out}/train.jsonl, {a.out}/test.jsonl, {a.out}/MANIFEST.json")
    if not m["domain_verified"]:
        print(
            "\n*** domain_verified: FALSE — clinical reference data is unreviewed. "
            "No number from this corpus may appear in the paper. ***"
        )


if __name__ == "__main__":
    main()
