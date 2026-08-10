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

Sources and evidence grades in `docs/LITERATURE.md`.

| # | Permitted phrasing | Source | Grade | Status |
|---|---|---|---|---|
| L1 | ~~"Only 5–15% of claims receive pre-submission review"~~ → **"A casemix unit of 2–5 staff cannot review 30–50 claims a day at volume — our estimate from staffing arithmetic, not a measured figure"** | vendor blog only | D | **downgraded to our own estimate** |
| L2 | "Inpatient claims pend at 12–17% across single-site Indonesian studies" — never "~15% nationally" | Maulida & Djunawan 2022; Dewi & Wirajaya 2024 | A / B | literature |
| L3 | "Incomplete discharge summaries and inaccurate coding cost one South Jakarta hospital ~4% of INA-CBG claim value (n=105)" | Opitasari & Nurwahyuni 2018, Table 4 | A | literature |
| L4 | ~~"Bad debt from pended claims runs 8–12%"~~ | **not located** | — | **unsupported — do not use** |
| L5 | "Secondary diagnoses fail to carry from the medical record into the discharge summary in 68.6% of inpatient episodes" | Opitasari & Nurwahyuni 2018, Table 2 | A | literature |
| L6 | "Undercoding outnumbers overcoding roughly 2:1 (13.3% vs 6.7% of episodes)" | Opitasari & Nurwahyuni 2018, Table 4 | A | literature |
| L7 | "ICD-10 coding accuracy in Indonesian hospitals ranges 21–81% across 45 studies" | systematic review, RMIK 2021 | C | literature |

**L5 and L6 are the strongest cards we hold.** They are grade A, inpatient,
Indonesian, and they establish the undercoding narrative from primary data
rather than assertion. Lead with them, not with L1.

## Product claims (must be measured)

| # | Claim | Evidence | Bucket | Status |
|---|---|---|---|---|
| P1 | Evidence-cited checking catches defects a rules-only checklist cannot | Arm C > B > A, bootstrap CIs, ≥3 seeds | 10 | **supported** — macro recall 0.399 → 0.700 → 0.875, every step separated by paired bootstrap, at a matched clean-claim FP budget. Say "at a matched false-positive budget", never the bare recall numbers |
| P2 | Defects are detectable before discharge, early enough to repair | Detection-rate-by-day + lead-time distribution | 10 | **supported** — 86.7% detected by discharge, median 5 days early, 86.1% with ≥2 days. Always carry "under stated generator assumptions"; the timing is sampled by our own generator |
| P3 | Rules reach exactly 3 of 8 defect classes | Arm-A baseline, per class | 5 | **supported** — D1, D6, D8 at recall 1.0; D5 partial at 0.191; D2/D3/D4/D7 at 0.000. Say "reach" = recall ≥ 0.5, and say so |
| P4 | Cross-encoder beats BM25 and zero-shot LLM | Per-class results on D2/D3/D4/D7 | 8 | not yet supported |
| P5 | The system does not over-flag clean claims | Clean-claim FPR, reported with recall | 10 | **partly supported, and the honest form is two numbers.** 3.7% at discharge. **36.6% early in the stay**, which is where the sweep runs. Quoting only 3.7% while selling concurrent monitoring is the exact error this register exists to prevent — both, always, or neither |
| P6 | The generator does not leak the defect label through text | Text-only classifier at chance | 4 | not yet supported |
| P7 | The system degrades safely without the LLM | Rules-only advisory mode in `make demo` | 9 | **supported** — zero-LLM share 1.0 by construction; detection, scores, citations and tariffs are identical with the LLM off, and the run is marked `advisory` with the unchecked classes named |
| P8 | Affordable at hospital volume | Latency, cost/claim, % zero-LLM episodes | 9, 13 | **supported** — 18 ms/run on Apple silicon, 100% zero-LLM episodes, Rp 0 per sweep night. Label the hardware; do not extrapolate to a hospital's server without saying it is an extrapolation |

## Forbidden phrasings

| Do not write | Write instead |
|---|---|
| "Vitera recovers X% of revenue" | "Undercoding is reported at X% in the literature; Vitera's measured detection rate is Y%" |
| "Fraud detection" | "Anomaly flagging" — there are no fraud labels |
| "Vitera saves hospitals Rp N" | "Projected under stated assumptions: Rp N" |
| "Accuracy of X%" on imbalanced data | PR-AUC, with calibration, and the clean-claim FPR |
| "Recall of X%" alone | Recall X% at clean-claim FPR Y% |
| "Clean-claim false positive rate is 3.7%" | "3.7% at discharge, 36.6% early in the stay" — one number alone misrepresents a product that runs nightly |
| "Arm C beats arm B on recall" | "at a matched false-positive budget, arm C beats arm B" — without the match, arm B reaches C's recall by flagging 51% of clean claims |
| "Bootstrap CIs across 3 seeds" | "paired bootstrap over episodes; one checkpoint, so training-seed variance is not measured" |
| "Churn is 21%" | "21%, above our own 15% ceiling, and an upper bound — see the attribution caveat" |
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
