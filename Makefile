.DEFAULT_GOAL := help
SHELL := /bin/bash
PY := python3
SEED ?= 20260731
VITERA_LLM_MODE ?= cache
export VITERA_LLM_MODE

.PHONY: help setup data train eval arm-a demo demo-offline sweep sweep-demo \
        leakage figures test lint clean freeze-check

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-16s\033[0m %s\n", $$1, $$2}'

setup:  ## Install the package and dev dependencies
	$(PY) -m pip install -e ".[dev]"

## --- data ------------------------------------------------------------------

data:  ## Generate the frozen synthetic dataset            [bucket 4]
	$(PY) -m vitera.generator.cli --seed $(SEED) --out data/generated

leakage:  ## Text-only classifier leakage check; prints a number  [bucket 4]
	$(PY) -m experiments.leakage_check --data data/generated --seed $(SEED)

## --- models ----------------------------------------------------------------

train:  ## Fine-tune the cross-encoder (MPS on Apple silicon)  [bucket 8]
	$(PY) -m vitera.models.train_cross_encoder --data data/generated --seed $(SEED)

arm-a:  ## Rules-only baseline (arm A)                        [bucket 5]
	$(PY) experiments/arm_a.py --data data/generated

eval:  ## Three-arm experiment + per-component baselines     [bucket 10]
	$(PY) -m experiments.run_arms --data data/generated --seeds 3 --out results/

## --- running ---------------------------------------------------------------

demo:  ## End-to-end discharge path, live LLM                 [bucket 9]
	VITERA_LLM_MODE=live $(PY) -m vitera.api.demo

demo-offline:  ## Same path, replayed from the LLM cache      [bucket 9]
	VITERA_LLM_MODE=cache $(PY) -m vitera.api.demo --offline

sweep:  ## One night against the configured cohort           [bucket 13]
	$(PY) -m vitera.sweep.runner --config config/sweep.yaml

sweep-demo:  ## Replay 7 seeded days in under a minute       [bucket 13]
	VITERA_LLM_MODE=cache $(PY) -m vitera.sweep.runner --replay 7 --seed $(SEED)

## --- outputs ---------------------------------------------------------------

figures:  ## Regenerate every paper figure into results/
	$(PY) -m experiments.figures --out results/

## --- quality ---------------------------------------------------------------

test:  ## Run the test suite
	$(PY) -m pytest -q

lint:  ## Format check and type check
	$(PY) -m ruff check src tests experiments
	$(PY) -m ruff format --check src tests experiments
	$(PY) -m mypy src

freeze-check:  ## Fail if data/adversarial/ has been modified (sealed set)
	@git diff --quiet HEAD -- data/adversarial/ \
	  || (echo "data/adversarial/ is sealed until final evaluation"; exit 1)
	@echo "adversarial set intact"

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache **/__pycache__
