# Claims register

Every claim that appears in the paper, the deck or the demo narration is listed
here with its status. **If a sentence is not in this file, it does not go on a
slide.**

The distinction this file exists to protect:

- *"Undercoding costs Indonesian hospitals ~4.2% of claim revenue"* — a published
  finding about problem size.
- *"Vitera recovers 4.2%"* — **not something we have measured, ever.**

Anything projected from assumptions is labelled *projected under stated
assumptions*. Never *delivers*, never *saves*, never *recovers*.

Status values: `literature` · `measured` · `projected` · `not yet supported` · `dropped`

---

## Problem-size claims (literature)

| # | Claim | Source | Status |
|---|---|---|---|
| L1 | Only 5–15% of claims receive pre-submission review at hospitals above 1,000 claims/month | TODO — bucket 3 | literature |
| L2 | Claims pend at ~15% | TODO — bucket 3 | literature |
| L3 | Undercoding costs ~4.2% of claim revenue | TODO — bucket 3, verify against primary source | literature |
| L4 | Hospital bad debt from pended claims runs 8–12% | TODO — bucket 3, **verify against primary source before use** | literature |

## Product claims (must be measured)

| # | Claim | Evidence | Bucket | Status |
|---|---|---|---|---|
| P1 | Evidence-cited checking catches defects a rules-only checklist cannot | Arm C > B > A, bootstrap CIs, ≥3 seeds | 10 | not yet supported |
| P2 | Defects are detectable before discharge, early enough to repair | Detection-rate-by-day + lead-time distribution | 10 | not yet supported |
| P3 | Rules reach exactly 3 of 8 defect classes | Arm-A baseline, per class | 5 | not yet supported |
| P4 | Cross-encoder beats BM25 and zero-shot LLM | Per-class results on D2/D3/D4/D7 | 8 | not yet supported |
| P5 | The system does not over-flag clean claims | Clean-claim FPR, reported with recall | 10 | not yet supported |
| P6 | The generator does not leak the defect label through text | Text-only classifier at chance | 4 | not yet supported |
| P7 | The system degrades safely without the LLM | Rules-only advisory mode in `make demo` | 9 | not yet supported |
| P8 | Affordable at hospital volume | Latency, cost/claim, % zero-LLM episodes | 9, 13 | not yet supported |

## Forbidden phrasings

| Do not write | Write instead |
|---|---|
| "Vitera recovers X% of revenue" | "Undercoding is reported at X% in the literature; Vitera's measured detection rate is Y%" |
| "Fraud detection" | "Anomaly flagging" — there are no fraud labels |
| "Vitera saves hospitals Rp N" | "Projected under stated assumptions: Rp N" |
| "Accuracy of X%" on imbalanced data | PR-AUC, with calibration, and the clean-claim FPR |
| "Recall of X%" alone | Recall X% at clean-claim FPR Y% |
| "The model determined the diagnosis is unsupported" | "The cross-encoder scored the diagnosis unsupported; the router flagged it" |
| Any tariff figure when the grouper returns `UNGROUPABLE` | "Ungroupable — no tariff estimated" |

## Caveats that ship with every result

1. All data is synthetic. No practising-coder validation, no real BPJS
   pend-reason data. Caps what we may conclude.
2. `detection_lead_time` is measured on episodes whose timing our own generator
   sampled. Always reported *under stated generator assumptions*. See
   `docs/DATA_CARD.md` for the sampling parameters and their citations.
3. Hospital-level holdout, not row-level — but the hospitals are synthetic too,
   so external validity is untested.
