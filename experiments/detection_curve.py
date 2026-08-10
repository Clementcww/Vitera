"""Detection lead time — the headline metric of the concurrent thesis.

CLAUDE.md defines it: ``detection_lead_time = discharge_day - detection_day``,
reported alongside a detection-rate-versus-day-of-stay curve. This script
measures both, on the full held-out split, by doing exactly what the design
demands: **invoking the discharge pipeline once per day of stay** (rules + the
trained cross-encoder — no LLM; the LLM writes prose and prose does not detect).

For every (episode, defect class) pair that is true at discharge, we record the
first day of stay on which the pipeline flags that class. The gap to discharge
is the repair window Vitera buys. A flag is only counted when the same class is
still flagged at discharge — a finding that appears on day 3 and vanishes by
day 7 is churn, not detection, and counting it would inflate the headline.

Also measured here, because they fall out of the same sweep of runs and each
one is a criteria commitment:

- **clean-claim false positive rate by day** — the alert-fatigue guard. Recall
  without this number is meaningless for adoption, so they travel together.
- **fairness stratification by hospital class** — lead time and clean FPR per
  class A/B/C. Documentation quality varies by class in the generator, so if
  the product only works for well-documented hospitals, this is where it shows.
- **latency per pipeline run and the zero-LLM share** — measured on this
  hardware, stated as such. The zero-LLM share is 100% by construction here
  and is reported that way, not as a discovery.

Undercoding (site-quality, ``documented_day = null``) is measured separately
from injected defects: an undocumented comorbidity is detected when a QUERY
flag cites it from ``signal_day`` onward. That window between clinical
visibility and documentation is the value the product exists to create.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from vitera import config
from vitera.agent.loop import run_pipeline
from vitera.generator.corpus import claim_from_dict, episode_from_dict, load_jsonl
from vitera.rules.engine import RuleContext

_CODE = re.compile(r"^[A-Z]\d{2}(?:\.\d+)?$")


def _flagged(result: Any) -> tuple[set[str], dict[str, str]]:
    """Classes flagged, and code -> remedy, both off structured fields.

    `Flag.subject`, not the rationale: prose is LLM-writable under rule 2, and
    a measurement that parses prose measures the prose.
    """
    classes = {f.defect_class.name for f in result.decision.flags}
    codes = {
        f.subject: f.remedy.name
        for f in result.decision.flags
        if _CODE.match(f.subject)
    }
    return classes, codes


def evaluate(
    rows: list[dict[str, Any]], scorer: Any, site_class: dict[str, str]
) -> dict[str, Any]:
    lead_times: list[int] = []
    detect_day_rel: list[float] = []  # detection day / discharge day, for the curve
    by_class_lead: defaultdict[str, list[int]] = defaultdict(list)
    by_site_lead: defaultdict[str, list[int]] = defaultdict(list)
    by_site_fp: defaultdict[str, list[int]] = defaultdict(list)
    undercode_lead: list[int] = []
    clean_fp_by_day: defaultdict[int, list[int]] = defaultdict(list)
    clean_fp_by_share: defaultdict[int, list[int]] = defaultdict(list)
    clean_fp_at_discharge: list[int] = []
    detected_pairs = 0
    truth_pairs = 0
    runs = 0
    t_total = 0.0

    for r in rows:
        ep = episode_from_dict(r["episode"])
        claim = claim_from_dict(r["claim"])
        last = ep.discharge_day or ep.los_so_far
        truth = {d["defect_class"] for d in r["defects"]}
        undoc = {
            s["icd10"]: s["signal_day"]
            for s in r["episode"]["secondary_dx"]
            if s["documented_day"] is None and s["signal_day"] is not None
        }
        sc = site_class.get(ep.site_id, "?")

        first_seen: dict[str, int] = {}
        undoc_seen: dict[str, int] = {}
        final_classes: set[str] = set()
        is_clean = not truth

        for day in range(0, last + 1):
            t0 = time.monotonic()
            result = run_pipeline(RuleContext(ep, claim, day), scorer=scorer)
            t_total += time.monotonic() - t0
            runs += 1

            classes, codes = _flagged(result)
            for c in classes:
                first_seen.setdefault(c, day)
            for code, remedy in codes.items():
                if code in undoc and remedy == "QUERY":
                    undoc_seen.setdefault(code, day)
            if day == last:
                final_classes = classes
            if is_clean:
                clean_fp_by_day[day].append(1 if classes else 0)
                if last > 0:
                    # Binned by SHARE of stay, so every clean episode
                    # contributes across the whole axis. The by-day series
                    # cannot be read as a trend on its own: its cohort changes
                    # composition as the axis advances — day 13 contains only
                    # episodes that stayed 13 days — so a decline there is
                    # partly a change of population rather than of behaviour.
                    # This is the same denominator artefact that made the raw
                    # per-day flag count look like falling detection.
                    clean_fp_by_share[round(10 * day / last)].append(
                        1 if classes else 0
                    )

        if is_clean and last > 0:
            by_site_fp[sc].append(1 if final_classes else 0)
            clean_fp_at_discharge.append(1 if final_classes else 0)

        # A detection counts only if the class is still flagged at discharge.
        for c in truth:
            truth_pairs += 1
            if c in final_classes and c in first_seen:
                detected_pairs += 1
                lead = last - first_seen[c]
                lead_times.append(lead)
                by_class_lead[c].append(lead)
                by_site_lead[sc].append(lead)
                if last > 0:
                    detect_day_rel.append(first_seen[c] / last)

        for day in undoc_seen.values():
            undercode_lead.append(last - day)

    lt = np.asarray(lead_times)
    curve = []
    if len(detect_day_rel):
        rel = np.asarray(detect_day_rel)
        for frac in np.linspace(0, 1, 11):
            curve.append(
                {
                    "share_of_stay": round(float(frac), 2),
                    "detection_rate": round(float((rel <= frac + 1e-9).mean()), 4),
                }
            )

    def _stats(a: list[int]) -> dict[str, Any]:
        if not a:
            return {"n": 0}
        x = np.asarray(a)
        return {
            "n": int(x.size),
            "mean": round(float(x.mean()), 2),
            "median": float(np.median(x)),
            "p25": float(np.percentile(x, 25)),
            "p75": float(np.percentile(x, 75)),
        }

    return {
        "n_episodes": len(rows),
        "pipeline_runs": runs,
        "truth_pairs": truth_pairs,
        "detected_at_discharge": detected_pairs,
        "detection_rate": round(detected_pairs / max(1, truth_pairs), 4),
        "lead_time_days": _stats(lead_times),
        "lead_time_share_ge_2_days": (
            round(float((lt >= 2).mean()), 4) if lt.size else None
        ),
        "undercoding_query_lead_time_days": _stats(undercode_lead),
        "detection_rate_by_share_of_stay": curve,
        "lead_time_by_class": {k: _stats(v) for k, v in sorted(by_class_lead.items())},
        "fairness_by_hospital_class": {
            k: {
                "lead_time_days": _stats(by_site_lead[k]),
                "clean_claim_false_positive_rate": (
                    round(float(np.mean(by_site_fp[k])), 4) if by_site_fp[k] else None
                ),
                "clean_claims": len(by_site_fp[k]),
            }
            for k in sorted(set(by_site_lead) | set(by_site_fp))
        },
        # THE adoption-critical number. Reported three ways because one way is
        # not enough to read it honestly:
        #
        #   at_discharge   what a discharge-time review would produce. The
        #                  figure comparable to arm A/B/C in run_arms.py.
        #   by_share       the trend. Every clean episode contributes across
        #                  the whole axis, so a change here is behaviour.
        #   by_day         raw, WITH its denominator, because the cohort
        #                  shrinks and changes composition along it. Kept for
        #                  completeness and explicitly not a trend.
        "clean_fp_rate_at_discharge": (
            round(float(np.mean(clean_fp_at_discharge)), 4)
            if clean_fp_at_discharge
            else None
        ),
        "clean_fp_rate_by_share_of_stay": [
            {
                "share_of_stay": round(k / 10, 2),
                "clean_fp_rate": round(float(np.mean(v)), 4),
                "n": len(v),
            }
            for k, v in sorted(clean_fp_by_share.items())
            if len(v) >= 30
        ],
        "clean_fp_rate_by_day": {
            str(d): {"rate": round(float(np.mean(v)), 4), "n": len(v)}
            for d, v in sorted(clean_fp_by_day.items())
            if len(v) >= 30  # below that the rate is noise, not a rate
        },
        "clean_fp_by_day_caveat": (
            "Not a trend. The cohort at day d is only the episodes that stayed "
            "at least d days, so its composition changes along the axis. Read "
            "`clean_fp_rate_by_share_of_stay` for the trend and "
            "`clean_fp_rate_at_discharge` for the comparable point estimate."
        ),
        "latency": {
            "seconds_per_run_mean": round(t_total / max(1, runs), 4),
            "hardware": "Apple silicon (MPS), local",
            "llm_calls": 0,
            "zero_llm_share": 1.0,
            "note": (
                "rules + cross-encoder only, by construction: the LLM layer "
                "writes prose and does not detect. Not a discovery; a design "
                "property, measured to substantiate the scalability argument."
            ),
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=Path("data/generated"))
    p.add_argument("--model", type=Path, default=Path("models/cross_encoder"))
    p.add_argument("--out", type=Path, default=Path("results/detection_curve.json"))
    p.add_argument("--limit", type=int, default=0, help="episodes cap, 0 = all")
    a = p.parse_args()

    rows = load_jsonl(a.data / "test.jsonl")
    if a.limit:
        rows = rows[: a.limit]

    from vitera.models.cross_encoder import CrossEncoderScorer

    scorer = CrossEncoderScorer.load(a.model)

    sites = {s["id"]: s["class"] for s in config.sites()["sites"]}
    res = evaluate(rows, scorer, sites)
    res["seed"] = config.DEFAULT_SEED
    res["model"] = str(a.model)

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(
        f"DETECTION LEAD TIME — n={res['n_episodes']} episodes, "
        f"{res['pipeline_runs']} pipeline runs\n"
    )
    print(f"detection rate at discharge : {res['detection_rate']}")
    print(
        f"lead time (days)            : median {res['lead_time_days'].get('median')}, "
        f"mean {res['lead_time_days'].get('mean')}"
    )
    print(f"share with >= 2 days window : {res['lead_time_share_ge_2_days']}")
    print(
        f"undercoding query lead time : median "
        f"{res['undercoding_query_lead_time_days'].get('median')}"
    )
    print(
        f"latency per run             : {res['latency']['seconds_per_run_mean']} s, "
        f"zero-LLM share {res['latency']['zero_llm_share']}"
    )
    print(f"clean-claim FPR at discharge: {res['clean_fp_rate_at_discharge']}")
    share = res["clean_fp_rate_by_share_of_stay"]
    if share:
        print(
            f"clean-claim FPR by share    : {share[0]['clean_fp_rate']} at admission "
            f"-> {share[-1]['clean_fp_rate']} at discharge"
        )
    print("\nfairness by hospital class:")
    for k, v in res["fairness_by_hospital_class"].items():
        print(
            f"  {k}: lead median {v['lead_time_days'].get('median')}, "
            f"clean FPR {v['clean_claim_false_positive_rate']}"
        )


if __name__ == "__main__":
    main()
