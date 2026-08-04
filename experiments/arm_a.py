"""Arm A — the rules-only baseline.

The paper claims rules reach 3 of 8 defect classes. This measures it instead of
asserting it, and reports the clean-claim false positive rate alongside recall,
because recall without it is meaningless for adoption.

**This baseline must not be a strawman.** If arm A is weak because we built it
weakly, the headline claim is worthless. The rules here use the full record and
cite verbatim spans; where they fail, they fail because deterministic lookup
cannot judge whether free text supports a code.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from vitera.generator.corpus import claim_from_dict as _claim
from vitera.generator.corpus import episode_from_dict as _episode
from vitera.generator.corpus import load_jsonl
from vitera.grouper.grouper import Grouper
from vitera.rules.engine import RuleContext, run

CLASSES = [f"D{i}" for i in range(1, 9)]


def evaluate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouper = Grouper()
    tp: defaultdict[str, int] = defaultdict(int)
    fp: defaultdict[str, int] = defaultdict(int)
    fn: defaultdict[str, int] = defaultdict(int)
    eligible: defaultdict[str, int] = defaultdict(int)

    clean_total = 0
    clean_flagged = 0
    ungroupable = 0
    spans_ok = 0
    spans_total = 0
    recoverable_idr = 0

    for r in rows:
        ep, claim = _episode(r["episode"]), _claim(r["claim"])
        truth = {d["defect_class"] for d in r["defects"]}
        for c in r["eligible_for"]:
            eligible[c] += 1

        ctx = RuleContext(ep, claim, ep.discharge_day or 0)
        flags, failures = run(ctx)
        found = {f.defect_class.name for f in flags}

        # Rule 6 as a measured property, not a promise.
        for f in flags:
            spans_total += 1
            doc = next((d for d in ep.documents if d.doc_id == f.span.doc_id), None)
            if doc and doc.text[f.span.start : f.span.end] == f.span.text:
                spans_ok += 1

        for c in CLASSES:
            if c in truth and c in found:
                tp[c] += 1
            elif c in found:
                fp[c] += 1
            elif c in truth:
                fn[c] += 1

        if not truth:
            clean_total += 1
            if found or failures:
                clean_flagged += 1

        # Recoverable value: what the claim groups to vs. what the full
        # clinical picture would group to. Grouper is authoritative (rule 7).
        gt = r["ground_truth"]
        as_claimed = grouper.group_codes(
            claim.primary_dx, claim.secondary_dx, claim.procedures
        )
        as_documented = grouper.group_codes(
            gt["primary_dx"], tuple(gt["secondary_dx"]), tuple(gt["procedures"])
        )
        if as_claimed.ungroupable_reason:
            ungroupable += 1
        if as_claimed.tariff_idr and as_documented.tariff_idr:
            recoverable_idr += max(0, as_documented.tariff_idr - as_claimed.tariff_idr)

    per_class = {}
    for c in CLASSES:
        prec = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else None
        rec = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) else None
        per_class[c] = {
            "eligible": eligible[c],
            "tp": tp[c],
            "fp": fp[c],
            "fn": fn[c],
            "precision": round(prec, 4) if prec is not None else None,
            "recall": round(rec, 4) if rec is not None else None,
            "reached": bool(rec is not None and rec >= 0.5),
        }

    reached = [c for c in CLASSES if per_class[c]["reached"]]
    return {
        "n": len(rows),
        "per_class": per_class,
        "classes_reached": reached,
        "n_classes_reached": len(reached),
        "clean_claim_false_positive_rate": (
            round(clean_flagged / clean_total, 4) if clean_total else None
        ),
        "clean_claims": clean_total,
        "span_verification_rate": (
            round(spans_ok / spans_total, 4) if spans_total else None
        ),
        "ungroupable_claims": ungroupable,
        "recoverable_idr_total": recoverable_idr,
        "recoverable_idr_mean": round(recoverable_idr / len(rows)),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("data/generated"))
    p.add_argument("--out", type=Path, default=Path("results/arm_a.json"))
    a = p.parse_args()

    rows = load_jsonl(a.data / "test.jsonl")

    res = evaluate(rows)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(f"ARM A — rules only, n={res['n']} test episodes\n")
    print(
        f"{'class':6} {'elig':>6} {'tp':>5} {'fp':>5} {'fn':>5} {'prec':>7} {'rec':>7}"
    )
    for c in CLASSES:
        m = res["per_class"][c]
        pr = f"{m['precision']:.3f}" if m["precision"] is not None else "  -  "
        rc = f"{m['recall']:.3f}" if m["recall"] is not None else "  -  "
        print(
            f"{c:6} {m['eligible']:>6} {m['tp']:>5} {m['fp']:>5} {m['fn']:>5} "
            f"{pr:>7} {rc:>7}"
        )
    print()
    print(
        f"classes reached (recall >= 0.5) : {res['n_classes_reached']} of 8 "
        f"— {', '.join(res['classes_reached'])}"
    )
    print(f"clean-claim false positive rate : {res['clean_claim_false_positive_rate']}")
    print(f"span verification rate          : {res['span_verification_rate']}")
    print(f"mean recoverable value / episode: Rp {res['recoverable_idr_mean']:,}")


if __name__ == "__main__":
    main()
