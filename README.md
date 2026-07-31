# Vitera

Concurrent BPJS claim verification for Indonesian hospital inpatient episodes.

> We red-team the claim before BPJS does, while there is still time to fix it.

An agent runs BPJS claim verification against an inpatient episode — continuously,
while the patient is still admitted — finds what would cause the claim to be
pended, and hands the medical coder (*petugas casemix / koder klinis*) a ranked
fix list with evidence cited from the patient record.

All data in this repository is **synthetic**. See `docs/DATA_CARD.md`.

---

## Quickstart

```bash
make setup          # editable install + dev deps
make test           # contract tests
make data           # generate the frozen dataset  (fails until bucket 3 cites every rate)
make demo-offline   # end-to-end run, replayed from the LLM cache
```

Python 3.11+. Training runs on Apple silicon via MPS.

## Commands

| Target | Does |
|---|---|
| `make data` | Generate the frozen synthetic dataset |
| `make leakage` | Text-only leakage check; prints the number |
| `make train` | Fine-tune the cross-encoder |
| `make arm-a` | Rules-only baseline (arm A) |
| `make eval` | Three-arm experiment across 3 seeds |
| `make demo` | End-to-end discharge path, live LLM |
| `make demo-offline` | Same path, replayed from cache |
| `make sweep` | One night against the configured cohort |
| `make sweep-demo` | Replay 7 seeded days in under a minute |
| `make figures` | Regenerate every paper figure |
| `make freeze-check` | Verify the sealed adversarial set is untouched |

`VITERA_LLM_MODE` = `live` | `record` | `cache`. Rehearse in `record` to
populate the cache that `demo-offline` replays. Never demo by waiting for a clock.

## Reproduction table

Every figure and headline number in the paper maps to a command. **Keep this
current as you go** — a number that cannot be reproduced does not go in the paper.

| # | Artifact | Command | Bucket | Status |
|---|---|---|---|---|
| F1 | Defect prevalence, literature-weighted | `docs/LITERATURE.md` | 3 | **done** |
| T1 | Dataset summary + hospital holdout | `make data` | 4 | **done** |
| N1 | Leakage check (text-only classifier) | `make leakage` | 4 | **done** |
| T2 | Arm A: rules reach 3 of 8 | `make arm-a` | 5 | **done** |
| T3 | Cross-encoder vs. BM25 vs. zero-shot, per class | `make eval` | 8 | not started |
| F2 | Calibration curve | `make figures` | 8 | not started |
| T4 | Three arms, bootstrap CIs across 3 seeds | `make eval` | 10 | not started |
| N2 | Clean-claim false positive rate | `make eval` | 10 | not started |
| F3 | Detection rate by day of stay | `make figures` | 10 | not started |
| F4 | Detection lead time distribution | `make figures` | 10 | not started |
| T5 | Fairness by hospital class and region | `make eval` | 10 | not started |
| N3 | Latency, cost per claim, % zero-LLM episodes | `make demo` | 9 | not started |
| T6 | Adversarial set results | `make eval` | 11 | not started |
| F5 | Sweep: alerts/episode/day and churn | `make sweep-demo` | 13 | not started |

## Layout

```
config/      defects.yaml (a citation per rate) · sites.yaml · thresholds.yaml · sweep.yaml
data/        reference/ · generated/ (+ seeds + LLM cache) · adversarial/ (SEALED)
src/vitera/  contracts.py · config.py · generator · rules · grouper · models · agent · sweep · api · ui
experiments/ arm_a · arm_b · arm_c · ablations · leakage_check
results/     committed figures + metrics JSON
docs/        ARCHITECTURE · DATA_CARD · MODEL_CARD · CLAIMS
```

`src/vitera/contracts.py` is the interface every module codes against. The hard
architectural rules from `CLAUDE.md` are encoded there as types, so they fail at
the type checker rather than at review.

Notebooks explore. `src/` produces. A number that came from a notebook is not
reproducible.

## Working documents

- `CLAUDE.md` — domain, locked decisions, architectural rules. Read fully first.
- `intent-anchor.md` — locked goal, core decision, claims ledger, cut list.
- `CRITERIA_PROGRESS.md` — scoring against the judged criteria.

## Claims discipline

A literature figure about problem size is never a measured product result.
Permitted phrasing lives in `docs/CLAIMS.md`. Anything projected from
assumptions is labelled *projected under stated assumptions*.

## License

TBD before publication.
