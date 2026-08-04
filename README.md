# Vitera

Hospital-side BPJS claim integrity engine. Reads the berkas klaim as it
accumulates during a stay, checks it against the codes the hospital is about to
submit, and reports two numbers: **tariff the documentation already supports but
the claim does not carry**, and **tariff at risk of a pend if it is submitted as
is**.

The hospital is the customer. When a code is wrong the hospital eats the
difference, so every finding carries rupiah, not a severity label.

## Run

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python -m pytest             # 3 tests, ~1s
./venv/bin/python main.py               # http://localhost:8000/docs
```

```bash
curl -X POST localhost:8000/api/v1/claims/review \
  -H 'content-type: application/json' \
  -d @sample-data/EP-2026-04471.json
```

On the sample episode: `Rp 18.400.000 → Rp 21.950.000` recoverable,
`Rp 4.800.000` at risk.

`torch` and `transformers` are in `requirements.txt` but unused while
`encoder.model_path` is `null` — the pipeline runs end to end without weights.

## Layout

```
main.py                     FastAPI app
config.yaml                 every threshold in the system, nowhere else
dto/                        pydantic contracts + RFC9457 errors
  types.py                    SafeText — the PII guarantee, at type level
  episode.py                  RawEpisode (has PII) / SafeEpisode (structurally cannot)
service/                    data and external dependencies
  redact.py                   the ONLY producer of SafeText
  masters.py                  ICD-10, ICD-9-CM, INA-CBG tariff, doc checklists
  lexicon.py                  D8 trigger phrases -> candidate codes
  crossencoder.py             the one model. stubbed until weights are configured
  extract.py                  PDF text layer; OCR hook, not yet wired
entities/claim_agent/       the pipeline, as a LangGraph
src/claim/                  delivery -> usecase -> repository
tests/                      one test per architectural claim
```

## Pipeline

```
START → completeness → rules → candidates → encoder → spanfilter → grouper → router → END
```

Everything left of `encoder` is deterministic. `encoder` is the only node that
runs a model. Everything right of it constrains what that model is allowed to
have said.

| Node | Defect classes | How |
|---|---|---|
| `completeness` | C1 missing doc · C2 missing DPJP signature · C3 procedure with no evidence | stage checklists, metadata |
| `rules` | R1 invalid code · R2 demographic conflict · R3 structural violation | set membership, table joins |
| `candidates` | — | trigger lexicon proposes codes; over-proposes on purpose |
| `encoder` | M1 wrong specificity · M2 unsupported dx · M4 upcoding · D8 under-coded | cross-encoder: *does this text support this code?* |
| `spanfilter` | — | deletes any model finding that cannot quote its document verbatim |
| `grouper` | — | code set → INA-CBG group → tariff delta per finding |
| `router` | — | confidence and rupiah thresholds → clean / review / urgent |

**Why one cross-encoder and not five classifiers:** M1, M2, M4 and D8 are the
same question with different inputs. Asked of a candidate code, yes means
under-coded. Asked of a submitted code, no means unsupported. The model is a
reusable verifier, so recall is tuned in `lexicon.py` — a config edit, not a
retrain.

## What is deliberately not built yet

| | Where | Unblocks |
|---|---|---|
| OCR for scanned pages | `service/extract.py:ocr_pages` | scanned SPRI, resume medis, CPPT |
| Fine-tuned cross-encoder | `config.yaml:encoder.model_path` | real confidences instead of lexicon priors; M2 and M4 |
| Real masters | `service/masters.py` | currently a hardcoded slice; swap for CSVs under `data/masters/` |
| Nightly re-run + cross-day diff | — | "what changed since yesterday" during the stay |
| Console | — | worklist UI over the same API |

Handwriting is out of scope. A page that will not OCR is marked unreadable and
surfaced — never silently dropped.
