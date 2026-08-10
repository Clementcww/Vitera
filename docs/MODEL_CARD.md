# Model Card — Vitera cross-encoder

Bucket 8. Companion to [`DATA_CARD.md`](DATA_CARD.md), which documents the
corpus this model is trained and evaluated on.

> **All numbers below come from synthetic data whose clinical reference tables
> are not yet domain-verified** (`domain_verified: false`). They are engineering
> results about a corpus, not clinical evidence about Indonesian hospitals. See
> *Limitations*.

---

## 1. What it is

| | |
|---|---|
| **Base model** | `indobenchmark/indobert-base-p1`, 124M parameters |
| **Task** | binary pair classification |
| **Input** | `[CLS] <coded diagnosis> [SEP] <clinical evidence from the record> [SEP]` |
| **Output** | calibrated P(the record does **not** support this code) |
| **Serving** | self-hosted; no clinical text leaves the hospital boundary |
| **Max sequence** | 288 tokens (p99 of the pair corpus is 261; nothing real is truncated) |
| **Code** | `src/vitera/models/` — `pairs.py`, `train_cross_encoder.py`, `cross_encoder.py`, `calibrate.py` |
| **Reproduce** | `make train` then `make baselines` |

The model is the **clinical judge** and only that. It decides whether free text
supports a code. It does not choose the defect class, the remedy, the span, the
verdict or the tariff — those are deterministic (architectural rules 2, 5, 6, 7).

## 2. Intended use

Assisting a *petugas casemix / koder klinis* at an Indonesian hospital to find
claim defects before submission to BPJS, during the admission where possible.
Every output is a draft for a human to accept or reject; nothing is submitted,
and nothing leaves the system (architectural rule 1).

**Out of scope:** outpatient claims, iDRG, insurers, patients, any use where a
model output reaches a payer or a patient without a human commit, and any use as
a clinical decision support tool. It says nothing about the patient; it says
something about the record.

## 3. The task, precisely

Given one coded secondary diagnosis and the evidence passage from the record,
score whether the record documents that diagnosis.

Three construction decisions determine what the number means. They are argued in
full in `src/vitera/models/pairs.py`; in brief:

1. **The evidence passage excludes the record's own `Diagnosis sekunder:` list.**
   That block restates the claim rather than evidencing it. Left in, the task
   would be substring matching and the reported scores would measure string
   equality.
2. **The label is documentation, not clinical presence.** A comorbidity that is
   visible in the labs and never written down is labelled *unsupported* — which
   is what BPJS pends on. Whether the remedy is a DPJP query or a recode is
   decided deterministically from signal presence, not by the model.
3. **Evidence is day-aware.** The same function serves the discharge run and
   every concurrent run, so a concurrent result is the discharge pipeline
   invoked earlier, not a second system.

## 4. Training

| | |
|---|---|
| Corpus | `data/generated/train.jsonl`, 2 668 episodes → 2 180 pairs |
| Positive rate (train) | 0.412 |
| Split | **by site**, never by row — dev is 25% of training hospitals |
| Optimiser | AdamW, lr 2e-5, one-cycle schedule, 10% warmup, grad clip 1.0 |
| Batch / epochs | 16 / 3 |
| Seed | derived from master seed 20260731 via `config.seeds(...).for_stage("cross_encoder")` |
| Hardware | Apple silicon, MPS |

Seeds, the dev site list, the loss history and the calibration constants are
written to `models/cross_encoder/calibration.json` beside the weights, and
copied into `results/cross_encoder.json`.

## 5. Calibration and the deployment prior

Two corrections, in order:

1. **Temperature scaling**, fitted on the held-out dev *sites*. Fitting it on
   training episodes returns T≈1 and a reliability diagram that flatters the
   model.
2. **Prior shift.** The pair corpus is ~41% positive; a hospital's is ~10%
   (`config/thresholds.yaml: deployment_prior.codes_correct`). Probabilities are
   shifted in log-odds space, per the design brief's fourth data rule. Without this the
   system over-flags by roughly a factor of four, the koder stops reading the
   queue, and the adoption argument fails.

Prior shift is monotone, so it changes calibration and thresholds but not
ranking — every AUC in `results/cross_encoder.json` is unaffected by it.

The shift assumes only the class prior changes between corpus and deployment,
not the class-conditional distributions. That assumption is stated, not tested.

## 6. Results

Measured on `data/generated/test.jsonl` — **held-out hospitals**, 1 332
episodes → 1 064 pairs, 43.6% positive. Full numbers, reliability bins and
bootstrap CIs: [`results/cross_encoder.json`](../results/cross_encoder.json).

Every arm is cut at **its own** threshold for a shared 10% false-positive
budget on supported codes. A shared numeric cut-off would compare calibration
accident rather than separation, since the arms' probabilities are on different
scales.

| Arm | PR-AUC (95% CI) | ROC-AUC | ECE | FPR | Recall |
|---|---|---|---|---|---|
| **cross_encoder** | **0.994** [0.988, 0.999] | 0.996 | 0.065 | 0.098 | **0.998** |
| bm25 | 0.769 [0.732, 0.805] | 0.809 | 0.180 | 0.078 | 0.429 |
| llm_zero_shot | *not run* | — | — | — | — |

Per defect class — PR-AUC, and recall at the same budget:

| Class | n | cross-encoder | BM25 | CE recall | BM25 recall |
|---|---|---|---|---|---|
| D2 wrong specificity | 53 | **0.940** | 0.256 | 0.981 | 0.283 |
| D3 unsupported diagnosis | 124 | **0.966** | 0.614 | 1.000 | 0.516 |
| D4 severity undocumented | 101 | **0.948** | 0.474 | 1.000 | 0.485 |
| D7 upcoding pattern | 186 | **0.994** | 0.574 | 1.000 | 0.382 |

The margin is largest exactly where the design predicted: D2 (a sibling code
shares almost all its vocabulary with the right one) and D4 (labs present,
documentation absent — both mention the same words).

### 6.1 Shortcut controls — one passes nothing

Two ablations, both reported whether or not they are flattering:

| Control | ROC-AUC (95% CI) | Chance | Verdict |
|---|---|---|---|
| `hypothesis_only` — evidence blanked | 0.852 [0.830, 0.873] | 0.500 | **above chance** |
| `evidence_shuffled` — another episode's record | 0.768 [0.737, 0.798] | 0.500 | **above chance** |

**The corpus carries a strong per-code prior.** Code identity alone predicts
the label at 0.852, because injection is not code-neutral: D7 draws
severity-weighted comorbidities, D3 draws ones the group did not have, and
supported codes are drawn by prevalence. A model can exploit that without
reading a record.

### 6.2 What survives when the prior is removed

Conditioning on the code removes the prior completely — only supported vs.
unsupported instances *of the same code* are compared:

| Arm | code-conditional ROC-AUC | unconditional |
|---|---|---|
| cross_encoder | **0.999** | 0.996 |
| bm25 | 0.940 | 0.809 |

The cross-encoder's separation does **not** depend on the shortcut: it is as
strong within a code as across codes. The shortcut exists in the corpus and the
model also learned it, but it is not what is carrying the result.

**Caveat that limits this defence:** only 9 of 25 codes are scorable
code-conditionally. Sibling and invented codes (the D2 and D3 targets) never
appear as supported, so they have no negatives to condition against — which
means **D2 is not covered by this de-confounding at all**.

### 6.3 How to read the absolute numbers

**The gap between arms is the result. The level is not.** A PR-AUC of 0.994 and
a code-conditional 0.999 are a ceiling imposed by the generator, not evidence
of clinical competence: a documented comorbidity is marked by one of exactly
two templated `doc_phrases`, drawn from 20 sentences across 10 comorbidities.
Detecting a template is easy and does not transfer.

Report as: *on this corpus, a fine-tuned cross-encoder separates supported from
unsupported codes far better than lexical retrieval, on every defect class the
rules layer cannot reach.* Not as: *the model judges code support with 99%
accuracy.*

## 7. Baselines

| Arm | What it is | Why it is here |
|---|---|---|
| `bm25` | Okapi BM25 over the same evidence lines, Platt-scaled | The honest lexical ceiling. If the neural model does not beat it, the neural model is not earning its place |
| `cross_encoder` | This model | — |
| `llm_zero_shot` | A frontier model asked the same question directly | Tests whether fine-tuning is necessary at all |

Both baselines receive the **identical evidence passage** and the same
calibration treatment, so the comparison is about separation, not output scale.
BM25's IDF is fitted on the training split only.

**A weak baseline would make the headline claim worthless**, which is the same
reason the arm-A rules baseline in bucket 5 was built to be as strong as
deterministic rules can be.

## 8. Limitations

1. **Synthetic corpus, unverified clinical tables.** `data/reference/*.yaml`
   carry `verified: false`. Every ICD-10 code, severity weight and lab threshold
   is a plausible placeholder pending domain review.
2. **Templated text caps the result.** Clinical prose is generated from
   templates — 20 `doc_phrases` across 10 comorbidities. That is why the
   absolute scores sit near 1.0, and it is why the gap between arms is likely
   *narrower* on real records than reported here, not wider. See §6.3.
   Widening the phrase pool is the highest-value generator change available.
3. **No practising-coder validation.** No koder has judged whether these flags
   would be acted on.
4. **The sibling table is small, and D2 is unprotected by the code-conditional
   control.** D2 draws from an 18-code substitution table; real
   mis-specification is broader. Sibling codes never appear as supported, so
   §6.2's de-confounding cannot cover them, and D2's 0.940 retains whatever
   per-code prior the corpus carries.
5. **Prior shift is an assumption**, and the 90% figure it uses is itself
   flagged in `config/thresholds.yaml` as needing a citation.
6. **One seed.** Bucket 10 repeats the three-arm experiment across three seeds
   with bootstrap CIs; this card reports a single training run.
7. **The zero-shot LLM arm has not been run.** It is built and wired through
   the pseudonymisation boundary, but there is no provider binding yet
   (bucket 9) and no recorded cache, so it reports `not_run`. Unmeasured is not
   zero: nothing here shows fine-tuning was necessary rather than merely
   sufficient.

## 9. Safety and failure modes

- **A missing checkpoint is not an outage.** `CrossEncoderScorer.load` raises
  `ScorerUnavailable`, the pipeline runs rules-only and marks its output
  `advisory` (architectural rule 8). A degraded run must never render as a full
  one.
- **Every flag cites a verbatim line.** The span comes from the record, and the
  pipeline re-verifies it as a filter, not as an instruction (rule 6).
- **Abstention is reachable but currently unexercised** (rule 10). Scores
  between `abstain_below` and `flag_at` return `Verdict.ABSTAIN`, but on this
  corpus the two thresholds coincide (`bands_crossed: true`) because the model
  separates it too cleanly for a grey zone to exist. The mechanism is tested;
  the band is empty. On real prose it will not be.
- **The model never sees re-identified text** (rule 3) — though note the
  cross-encoder is self-hosted, so pseudonymisation matters most for the LLM
  path, not this one.
- **Over-flagging is the failure mode that kills adoption**, not missed
  defects. That is why the operating point is chosen from a false-positive
  budget rather than from a symmetric metric.
