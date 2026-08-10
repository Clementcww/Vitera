# Vitera

Concurrent BPJS claim verification for Indonesian hospital inpatient episodes.

> We red-team the claim before BPJS does, while there is still time to fix it.

An agent runs BPJS claim verification against an inpatient episode — continuously,
while the patient is still admitted — finds what would cause the claim to be
pended, and hands the medical coder (*petugas casemix / koder klinis*) a ranked
fix list with evidence cited from the patient record.

All data in this repository is **synthetic**. See [`docs/DATA_CARD.md`](docs/DATA_CARD.md) — note `domain_verified: false`.

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
| `make baselines` | Cross-encoder vs. BM25 vs. zero-shot LLM, per class |
| `make detection` | Detection lead time, rate-by-day curve, fairness strata |
| `make arm-a` | Rules-only baseline (arm A) |
| `make eval` | Three-arm experiment across 3 seeds |
| `make demo` | End-to-end discharge path, live LLM |
| `make demo-offline` | Same path, replayed from cache |
| `make sweep` | One night against the configured cohort |
| `make sweep-demo` | Replay 7 seeded days in under a minute |
| `make fpk` | Render FPK forms (BPJS claim submission form) from the cohort |
| `make intake` | Read a scanned FPK back in and write the corrected DRAF |
| `make intake-eval` | Measured OCR accuracy per scan profile |
| `make ui-data` | Export real pipeline output for the workbench |
| `make ui-intake` | Export the scanned-FPK view for the workbench |
| `make ui-install` | Install the workbench toolchain (network, once) |
| `make ui-build` | Build the workbench bundle |
| `make ui` | Serve the workbench on :5188 — static, offline |
| `make figures` | Regenerate every paper figure |
| `make freeze-check` | Verify the sealed adversarial set is untouched |

`VITERA_LLM_MODE` = `live` | `record` | `cache`. Rehearse in `record` to
populate the cache that `demo-offline` replays. Never demo by waiting for a clock.

`VITERA_OCR_MODE` = `auto` | `cache`. Same idea for paper intake. `make intake`
defaults to `cache` and reads the committed sample scan in
`data/intake/scan_rs009_maret2026/`, so it runs with no OCR engine installed.
`make intake-live` renders a fresh form, simulates a scan of it and reads that,
which needs Apple Vision (`pip install -e ".[intake-macos]"`) or tesseract.

The provider needs `VITERA_LLM_API_KEY` (or `OPENAI_API_KEY`) in the
environment; `VITERA_LLM_BASE_URL` and `VITERA_LLM_MODEL` override endpoint and
model, which is the seam the SEA-LION / Sahabat-AI production path uses. No key
is ever read from a file, and none is committed. The LLM writes rationale prose
only: with it switched off, detection, scores, citations and tariffs are
unchanged and the run is marked `advisory`.

Judges can supply their own key in the workbench itself, from the header panel.
It is held in `sessionStorage`, dies with the tab, is never written to disk, and
the request goes from their browser straight to the provider. Text is
pseudonymised client-side first, by a port of the same patterns the Python
boundary uses.

## Reproduction table

Every figure and headline number in the paper maps to a command. **Keep this
current as you go** — a number that cannot be reproduced does not go in the paper.

| # | Artifact | Command | Bucket | Status |
|---|---|---|---|---|
| F1 | Defect prevalence, literature-weighted | `docs/LITERATURE.md` | 3 | **done** |
| T1 | Dataset summary + hospital holdout | `make data` | 4 | **done** |
| N1 | Leakage check (text-only classifier) | `make leakage` | 4 | **done** |
| T2 | Arm A: rules reach 3 of 8 | `make arm-a` | 5 | **done** |
| T3 | Cross-encoder vs. BM25, per class | `make train && make baselines` | 8 | **done** |
| N4 | Shortcut controls + code-conditional AUC | `make baselines` | 8 | **done** |
| T3b | Zero-shot LLM arm | `make baselines` | 8, 9 | provider wired; arm not yet run |
| F2 | Calibration curve (bins in `results/cross_encoder.json`) | `make figures` | 8 | **done** — `results/figures/f2_calibration.png` |
| T4 | Three arms, paired bootstrap CIs at a matched FP budget | `make eval` | 10 | **done** — macro recall A 0.399 → B 0.700 → C 0.875, every step separated |
| F6 | Three arms, per defect class | `make eval && make figures` | 10 | **done** |
| N2 | Clean-claim false positive rate | `make eval` · `make detection` | 10 | **done** — 3.7% at discharge (arm C), 0.0% arm A, 6.2% arm B |
| F3 | Detection rate by share of stay | `make detection` | 10 | **done** — rises 63.9% → 86.7% |
| F4 | Detection lead time distribution | `make detection` | 10 | **done** — median 5 days, 86.7% detected |
| F7 | Clean-claim FPR by share of stay | `make detection && make figures` | 10 | **done** — 36.6% on admission → 3.7% at discharge |
| T5 | Fairness by hospital class | `make detection` | 10 | **done** (rules+CE; region pending) |
| N3 | Latency, cost/claim, % zero-LLM episodes | `make demo` | 9 | **done** — 30 ms/episode offline, ~Rp 0.68/claim prose-only |
| E1 | End-to-end run, 20 cases, no crash | `make demo-offline` | 9 | **done** — `results/demo_run.json`, asserted in `tests/test_demo.py` |
| T6 | Adversarial set results | `make eval` | 11 | not started |
| F5 | Sweep: alerts/episode/day and churn | `make sweep-demo && make figures` | 13 | **done** — 0.34 alerts/episode/day (ceiling 3.0); **churn 0.214 BREACHES its 0.15 ceiling**, reported as a defect |
| P1 | FPK OCR intake: cell accuracy per scan profile | `make intake-eval` | 14 | **done** — office 0.994, photocopy 0.990, phone 0.863 (`results/intake_ocr.json`) |
| P2 | Paper round trip: scan in, corrected DRAF out | `make intake` | 14 | **done** — 47 episodes, gate passes, `results/intake/fpk_draf_perbaikan.pdf` |
| U1 | Coder workbench: queue, verdict, span highlighting | `make ui-data && make ui` | 12 | **done** |
| U2 | Detection surface (episode × day × recoverable value) | `make ui-data && make ui` | 12 | **done** (landing card) |
| U3 | Scanned-FPK view: OCR boxes, confidences, gate verdict | `make ui-intake && make ui` | 14 | **done** |
| U4 | Generated report: draft, citations, print to PDF | `make ui-intake && make ui` | 14 | **done** |
| U5 | Unit dashboard over the detection surface | `make ui-data && make ui` | 14 | **done** |

## Layout

```
config/      defects.yaml (a citation per rate) · sites.yaml · thresholds.yaml · sweep.yaml
data/        reference/ · generated/ (+ seeds + LLM/OCR cache) · intake/ (sample scan) · adversarial/ (SEALED)
src/vitera/  contracts.py · config.py · generator · rules · grouper · models · agent · sweep · intake · api · ui
experiments/ arm_a · arm_b · arm_c · ablations · leakage_check
results/     committed figures + metrics JSON
docs/        ARCHITECTURE · DATA_CARD · MODEL_CARD · CLAIMS
```

### The sweep

`src/vitera/sweep/` is the automation layer, and it is deliberately the dumbest
component in the system: it selects a cohort, calls the existing `run_pipeline`
once per episode, diffs each result against that episode's last successful run,
orders the diffs and writes them to a draft workspace. Cohort, diff, order,
retry — that is the whole surface. No inference lives here, and nothing leaves
the system: there is no transport imported anywhere in the package, and a test
asserts it by parsing the imports rather than by trusting the prose.

```bash
make sweep-demo   # 7 nights over a seeded cohort, ~5s, no clock involved
```

Three things it measures that a discharge-time product cannot:

- **The queue is a diff, not a standing list.** Night one carries the whole
  backlog; after that the koder gets what changed. Re-presenting yesterday's
  findings every morning is how a monitoring product gets switched off in
  week two.
- **A finding that goes away is split in two.** `documented` — a note arrived
  that names what the finding was about, which is the outcome the product
  exists to produce — and `resolved`, which is the model saying something
  different about unchanged evidence. Reported as one number, the successes
  were indistinguishable from the defects.
- **`flag_churn_rate` currently BREACHES its ceiling: 0.214 against 0.15.** It
  is on the screen, in `results/`, and in F5. Most of the remainder is an
  attribution blind spot — a D3 or D5 that resolves because the narrative or a
  lab result arrived is not matched by code, so it counts as unexplained and
  the figure is an upper bound. Closing that needs code-to-signal reference
  lookup, which belongs in the pipeline and not in a scheduler. `make sweep`
  passes `--strict` and exits non-zero on a breach; `make sweep-demo` does not,
  so a judge can watch the replay finish with the breach on screen.

### Workbench

`src/vitera/ui/` is a React + three.js single-page app. It **renders pipeline
output and computes nothing** — `src/vitera/api/export.py` runs the real
pipeline over a demo cohort and writes the JSON the app reads. Rupiah figures
are grouper output; spans are re-verified against the document text in the
browser before a flag is allowed to render, which is architectural rule 6
enforced a second time on the surface that a poisoned note would have to reach.

It is a single page. The landing and the workbench are the same DOM: the dark
bento card is the hinge, and entering the queue morphs that card into the
workbench rather than routing to another screen.

The **unit summary** is not a pane of the workbench. It opens from the accent
card, over the day-of-stay surface that card already draws — the bars are the
runs, the numbers are what the runs found, and separating them made the reader
hold one in their head while looking at the other. Aggregates only, and the
screen says so: there is no per-coder cut and there will not be one.

The 3D layer is fenced three ways: lazy chunk, WebGL capability probe, error
boundary. The canvas only mounts once its card is open, so a closed landing
never touches WebGL, and losing the 3D layer costs an animation rather than a
screen.

Two panes sit behind the header switch. **Antrean** is the koder's day, and
**Berkas pindaian** is the paper the batch arrived on: the scanned FPK with
every recognised line drawn back onto it as a box, coloured by the engine's own
confidence, next to the extracted values and the validation gate's verdict.
Showing every observation — not only the ones a field used — is the point; a
view that drew only the successful reads would hide the half a koder needs.

**Buat laporan** renders the corrected draft in the browser from the same
export `make intake` prints as a PDF, and prints through the page rather than a
popup. It is stamped DRAF, its signature block is empty, and the amount that
would only become claimable if a DPJP documents care the record suggests is
printed apart from the total and never added into it.

### Language

**The whole product speaks Bahasa Indonesia** — workbench, CLI and printed FPK
alike. The user is a *petugas casemix / koder klinis*, usually D-3 Perekam
Medis, and CLAUDE.md's plain-language layer is written for them.

Only two kinds of string are exempt, and both for the same reason: they are
quotations, not copy. **Quoted record text stays verbatim** — rule 6 is void the
moment a citation is paraphrased — and the field labels beside the scanned form
keep the wording printed on the sheet, since that panel exists so a reader can
find the same words on the paper.

Code comments and the docs are in English. That is a repository convention for
the people who maintain it, and it never reaches a screen.

`docs/ui/workbench-mockup.html` is the no-build-step fallback and the design
spec the app implements.

### Paper intake

`src/vitera/intake/` closes the loop at the two ends the hospital actually
touches: paper in, paper out. The FPK — *Formulir Pengajuan Klaim*, the cover
form submitted with a batch of claims — is rendered in the layout of the real
form, read back off a scan with OCR, checked at the validation gate, and
returned as a corrected **draft**.

It is not a second pipeline. `intake/correct.py` calls the same `run_pipeline`
as `demo.py`, `export.py` and the sweep, and takes its rupiah figures from the
same `export.money_view` the workbench renders, so the printout and the screen
cannot disagree.

Four properties are load-bearing:

- **OCR is perception, extraction is deterministic.** `scan.py` returns text
  with a box and a confidence. `extract.py` decides what it means with anchored
  geometry and regular expressions — no model. A wrong value is therefore
  attributable to either a bad read or a bad rule, and you can tell which.
- **The gate runs before anything else** (rule 4). An illegible sheet, a total
  that disagrees with its own rows, or an out-of-scope form (FKTP RITP) is
  stopped rather than reasoned over.
- **A misread is never dressed up as a claim defect.** Every reconciliation
  checks the read quality of the fields it depends on and downgrades itself to
  `needs_human_read` when they are weak.
- **The output is a draft** (rule 1). Stamped DRAF on every page, signature
  block empty, nothing written back to the claim of record and nothing sent to
  BPJS. The corrected form also prints, separately and untotalled, the amount
  that would only become claimable if a DPJP documents care the record merely
  suggests.

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
