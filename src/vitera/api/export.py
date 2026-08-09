"""Export real pipeline output for the workbench UI — bucket 12.

The UI renders what the pipeline produced. It does not recompute anything, and
it never fabricates a number. That is not a style preference: three of the hard
architectural rules are only true if this file is the sole source of what the
screen shows.

    rule 6   a flag reaches the screen only with a verbatim span. Offsets are
             exported alongside the document text so the client can re-verify
             `text[start:end] == span.text` and drop what fails. The check runs
             twice, in two languages, because a fabricated citation that
             renders is worse than a finding that never appears.
    rule 7   every rupiah figure here comes from `Grouper`. `tariff_now` and
             `tariff_if_confirmed` are two grouper calls, not arithmetic on one.
             UNGROUPABLE exports a null and the client renders a dash.
    rule 8   `advisory` and the list of unchecked defect classes are exported,
             so a degraded run cannot render as a full one.

Two products of the same pipeline, per CLAUDE.md's rule that concurrent
monitoring is the discharge pipeline invoked N times:

    episodes   one run per episode at its latest available day — the workbench
    surface    one run per episode per day of stay — the day-of-stay surface

`surface` is deliberately NOT a diff. Diffing, ordering and suppression are the
sweep's job in bucket 13, and putting them here would build the second system
CLAUDE.md forbids.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from vitera.agent.loop import run_pipeline
from vitera.contracts import DefectClass, Episode, PipelineResult
from vitera.generator.corpus import claim_from_dict, episode_from_dict, load_jsonl
from vitera.generator.defects import CodedClaim
from vitera.grouper.grouper import Grouper
from vitera.rules.engine import RuleContext

DEFAULT_OUT = Path("src/vitera/ui/public/data/demo.json")
DETECTION_RESULTS = Path("results/detection_curve.json")

# Classes the rules layer alone reaches, measured in bucket 5. Everything else
# is unchecked when the model layer is down, and the banner has to say so.
_RULES_ONLY = ("D1", "D6", "D8")


def _scorer(model_dir: Path) -> tuple[Any, str | None]:
    """The cross-encoder, or None with the reason. Rule 8: a missing model
    degrades the run to advisory, it does not fail it."""
    try:
        from vitera.models.cross_encoder import CrossEncoderScorer

        return CrossEncoderScorer.load(model_dir), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _documents(ep: Episode, claim: CodedClaim, day: int) -> list[dict[str, Any]]:
    """What the koder may actually read: attached, and written by `day`.

    A document dropped by D1/D5 is exported as `absent` rather than omitted —
    the koder needs to see that the resume medis is missing, not to find a gap
    where it should have been.
    """
    present = set(claim.documents_present)
    out = []
    for d in sorted(ep.documents, key=lambda x: (x.day, x.doc_id)):
        if d.day > day:
            continue  # not written yet; a flag citing it would cite the future
        out.append(
            {
                "doc_id": d.doc_id,
                "day": d.day,
                "absent": d.doc_id not in present,
                "text": str(d.text) if d.doc_id in present else "",
            }
        )
    return out


def money_view(
    grouper: Grouper, claim: CodedClaim, result: PipelineResult
) -> dict[str, Any]:
    """Two grouper calls. Rule 7 — the model never produces a monetary figure.

    Public, and shared with `intake.correct`, deliberately. The workbench and
    the corrected FPK must show the same two figures for the same episode; two
    implementations of "what is this claim worth now" is how a screen and a
    printout end up disagreeing in front of a judge.

    `now` groups only the codes the pipeline did not flag as unsupported: that
    is what survives a BPJS verifier today. `if_confirmed` adds back the codes
    whose remedy is a DPJP query — care that the record suggests happened and
    that documentation would make claimable. Recodes are NOT added back; a
    wrong code does not become right by being confirmed.
    """
    flagged_codes = _flagged_codes(result)
    unsupported = set(flagged_codes)
    queryable = {c for c, remedy in flagged_codes.items() if remedy == "QUERY"}

    supported = tuple(c for c in claim.secondary_dx if c not in unsupported)
    confirmed = tuple(
        c for c in claim.secondary_dx if c not in unsupported or c in queryable
    )

    now = grouper.group_codes(claim.primary_dx, supported, claim.procedures)
    later = grouper.group_codes(claim.primary_dx, confirmed, claim.procedures)

    delta = None
    if now.tariff_idr is not None and later.tariff_idr is not None:
        delta = max(0, later.tariff_idr - now.tariff_idr)

    return {
        "now": _group_json(now),
        "if_confirmed": _group_json(later),
        "delta_idr": delta,
        "source": "grouper",
    }


def _group_json(g: Any) -> dict[str, Any]:
    return {
        "cbg_code": g.cbg_code,
        "severity": g.severity,
        "tariff_idr": g.tariff_idr,
        "ungroupable_reason": g.ungroupable_reason,
    }


def _flagged_codes(result: PipelineResult) -> dict[str, str]:
    """Which coded diagnosis each flag is about, and its remedy.

    Read off the rationale, which the scorer formats deterministically with the
    code in it. Fragile-looking and deliberate: the alternative is widening
    `Flag` to carry a subject, which changes a contract every module codes
    against, for one screen.
    """
    import re

    out: dict[str, str] = {}
    for f in result.decision.flags:
        m = re.search(r"\b([A-Z]\d{2}(?:\.\d+)?)\b", f.rationale)
        if m:
            out[m.group(1)] = f.remedy.name
    return out


def _flag_json(f: Any) -> dict[str, Any]:
    return {
        "defect_class": f.defect_class.name,
        "defect_label": f.defect_class.label,
        "remedy": f.remedy.name,
        "actor": f.remedy.actor,
        "decay_rank": f.remedy.decay_rank,
        "score": f.score,
        "source": f.source.value,
        "rationale": f.rationale,
        "span": {
            "doc_id": f.span.doc_id,
            "start": f.span.start,
            "end": f.span.end,
            "text": f.span.text,
            "evidence_hash": f.span.evidence_hash,
        },
    }


def _episode_json(
    ep: Episode, claim: CodedClaim, day: int, result: PipelineResult, grouper: Grouper
) -> dict[str, Any]:
    checked = (
        [d.name for d in DefectClass]
        if not result.trace.degraded
        else list(_RULES_ONLY)
    )
    return {
        "episode_id": ep.episode_id,
        "site_id": ep.site_id,
        "day": day,
        "los_so_far": ep.los_so_far,
        "discharge_day": ep.discharge_day,
        "still_admitted": ep.discharge_day is None or day < ep.discharge_day,
        "admission_date": ep.admission_date.isoformat(),
        "verdict": result.decision.verdict.value,
        "verdict_reason": result.decision.reason,
        "advisory": result.trace.degraded,
        "classes_checked": checked,
        "classes_unchecked": [d.name for d in DefectClass if d.name not in checked],
        "money": money_view(grouper, claim, result),
        "flags": [_flag_json(f) for f in result.decision.flags],
        "documents": _documents(ep, claim, day),
        "validation_failures": [
            {"check": v.check, "detail": v.detail} for v in result.validation_failures
        ],
        "trace": {
            "llm_calls": result.trace.llm_calls,
            "budget_breach": result.trace.budget_breach,
            "elapsed_seconds": result.trace.elapsed_seconds,
            "tool_calls": [
                {
                    "tool": t.tool,
                    "result_digest": t.result_digest,
                    "elapsed_seconds": t.elapsed_seconds,
                }
                for t in result.trace.tool_calls
            ],
        },
    }


def _select(
    rows: list[dict[str, Any]], *, cohort: int, seed: int, stratify: bool
) -> tuple[list[dict[str, Any]], str]:
    """Pick the demo cohort.

    A uniform sample of 36 episodes contains roughly two D4 cases and, drawn
    unluckily, none — and D4 is the entire concurrent argument: a comorbidity
    visible in the labs that nobody wrote down, repairable only while the
    patient is still on the ward. A demo queue with no Query row does not show
    the product.

    So the demo cohort is stratified to cover every defect class, and the
    payload says so in `cohort_selection`. This is presentation, not
    measurement — every number in `results/` comes from the full held-out
    split, never from here. Labelling it is what keeps the two apart.
    """
    rng = random.Random(seed)
    if not stratify:
        picked = rng.sample(rows, k=min(cohort, len(rows)))
        return picked, "uniform random sample of the held-out split"

    per_class = max(2, cohort // 12)
    chosen: dict[str, dict[str, Any]] = {}
    for cls in (d.name for d in DefectClass):
        pool = [
            r
            for r in rows
            if any(d["defect_class"] == cls for d in r["defects"])
            and r["episode"]["episode_id"] not in chosen
        ]
        rng.shuffle(pool)
        for r in pool[:per_class]:
            chosen[r["episode"]["episode_id"]] = r

    clean = [r for r in rows if not r["defects"]]
    rng.shuffle(clean)
    for r in clean:
        if len(chosen) >= cohort:
            break
        chosen[r["episode"]["episode_id"]] = r

    rest = [r for r in rows if r["episode"]["episode_id"] not in chosen]
    rng.shuffle(rest)
    for r in rest:
        if len(chosen) >= cohort:
            break
        chosen[r["episode"]["episode_id"]] = r

    return (
        list(chosen.values())[:cohort],
        f"stratified for demo coverage — up to {per_class} episodes per defect "
        "class, remainder clean claims. NOT a random sample; no measured "
        "result is computed from this cohort.",
    )


def build(
    rows: list[dict[str, Any]],
    *,
    cohort: int,
    seed: int,
    model_dir: Path,
    stratify: bool = True,
) -> dict[str, Any]:
    scorer, unavailable = _scorer(model_dir)
    grouper = Grouper()

    chosen, selection = _select(rows, cohort=cohort, seed=seed, stratify=stratify)
    chosen.sort(key=lambda r: r["episode"]["episode_id"])

    episodes: list[dict[str, Any]] = []
    surface: list[dict[str, Any]] = []

    for idx, row in enumerate(chosen):
        ep = episode_from_dict(row["episode"])
        claim = claim_from_dict(row["claim"])
        last_day = ep.discharge_day or ep.los_so_far

        # --- the workbench: one run at the latest available day -----------
        result = run_pipeline(RuleContext(ep, claim, last_day), scorer=scorer)
        episodes.append(_episode_json(ep, claim, last_day, result, grouper))

        # --- the surface: the SAME pipeline, once per day of stay ---------
        # Not a diff. Bucket 13 owns diffing, ordering and suppression.
        for day in range(0, last_day + 1):
            r = run_pipeline(RuleContext(ep, claim, day), scorer=scorer)
            codes = _flagged_codes(r)
            money = money_view(grouper, claim, r)
            top = min(
                (f for f in r.decision.flags),
                key=lambda f: (f.remedy.decay_rank, -f.score),
                default=None,
            )
            surface.append(
                {
                    "e": idx,
                    "episode_id": ep.episode_id,
                    "d": day,
                    "flags": len(r.decision.flags),
                    "verdict": r.decision.verdict.value,
                    "value_idr": money["delta_idr"] or 0,
                    "remedy": top.remedy.name.lower() if top else None,
                    "classes": sorted({f.defect_class.name for f in r.decision.flags}),
                    "codes": codes,
                }
            )

    # Headline metric, measured on the FULL held-out split by
    # experiments/detection_curve.py — never on this demo cohort. Embedded so
    # the hero can state it with its provenance; absent file, absent block,
    # and the UI renders nothing rather than a placeholder number.
    measured = None
    if DETECTION_RESULTS.exists():
        d = json.loads(DETECTION_RESULTS.read_text(encoding="utf-8"))
        measured = {
            "detection_rate": d["detection_rate"],
            "lead_time_median_days": d["lead_time_days"].get("median"),
            "lead_time_share_ge_2_days": d["lead_time_share_ge_2_days"],
            "n_episodes": d["n_episodes"],
            "source": "results/detection_curve.json — full held-out split",
        }

    return {
        "measured": measured,
        "generated": {
            "seed": seed,
            "cohort": len(chosen),
            "cohort_selection": selection,
            "model": str(model_dir) if scorer is not None else None,
            "model_unavailable": unavailable,
            "advisory": scorer is None,
            "note": (
                "Every figure is pipeline output. Rupiah come from the grouper "
                "(architectural rule 7); spans are verbatim and re-verified in "
                "the client (rule 6)."
            ),
        },
        "episodes": episodes,
        "surface": {
            "max_day": max((c["d"] for c in surface), default=0),
            "cells": surface,
        },
    }


def main() -> None:
    from vitera import config

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=Path("data/generated"))
    p.add_argument("--model", type=Path, default=Path("models/cross_encoder"))
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--cohort", type=int, default=36)
    p.add_argument("--seed", type=int, default=config.DEFAULT_SEED)
    p.add_argument(
        "--uniform",
        action="store_true",
        help="uniform sample instead of the stratified demo cohort",
    )
    a = p.parse_args()

    rows = load_jsonl(a.data / "test.jsonl")
    payload = build(
        rows,
        cohort=a.cohort,
        seed=a.seed,
        model_dir=a.model,
        stratify=not a.uniform,
    )

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    n_flags = sum(len(e["flags"]) for e in payload["episodes"])
    print(f"wrote {a.out}")
    print(f"  episodes      : {len(payload['episodes'])}")
    print(f"  flags         : {n_flags}")
    print(f"  surface cells : {len(payload['surface']['cells'])}")
    print(f"  selection     : {payload['generated']['cohort_selection']}")
    if payload["generated"]["advisory"]:
        print(f"  ADVISORY      : {payload['generated']['model_unavailable']}")


if __name__ == "__main__":
    main()
