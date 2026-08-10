"""Bucket 8 — the headline technical result.

One question, three ways of answering it: *does this record support this coded
diagnosis?*

    bm25            lexical retrieval over the same evidence passage
    cross_encoder   IndoBERT-base, fine-tuned (the locked clinical judge)
    llm_zero_shot   a frontier model asked directly, no fine-tuning

Reported per defect class, because the aggregate hides the finding. Rules
already reach D1, D6 and D8 (bucket 5 measured it). What matters here is
D2, D3, D4 and D7 — and within those, D4 is the one the product is really
about: a comorbidity whose labs are in the record and whose diagnosis nobody
wrote down. Lexical retrieval cannot separate "the notes describe managing
this" from "the labs suggest this", because both mention the same words.

Reporting rules from the design brief, applied without exception:

- PR-AUC and calibration, never aggregate accuracy — the classes are imbalanced
  and accuracy would flatter every arm equally.
- Recall never without the clean-claim false positive rate; here that is the
  false positive rate on *supported* codes, which is what a koder experiences
  as noise.
- Bootstrap CIs on every headline number.
- Nothing is capped silently: if the LLM arm is sampled rather than run in
  full, the sample size is in the output.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from vitera import config
from vitera.generator.corpus import load_jsonl
from vitera.models import calibrate
from vitera.models.bm25 import BM25, tokenise
from vitera.models.pairs import CLASSES, CodePair, iter_pairs

DEFAULT_MODEL_DIR = Path("models/cross_encoder")


# ---------------------------------------------------------------------------
# Arm 1 — BM25
# ---------------------------------------------------------------------------


def bm25_probabilities(
    train: Sequence[CodePair], test: Sequence[CodePair]
) -> tuple[list[float], dict[str, Any]]:
    """Retrieval score, Platt-scaled into a probability on the training split.

    The neural arm gets temperature scaling; this arm gets logistic scaling.
    Both end up calibrated, so the comparison is between what the two can
    *separate*, not between how their raw outputs happen to be distributed.
    """
    from sklearn.linear_model import LogisticRegression

    bm = BM25().fit(tokenise(ln.text) for p in train for ln in p.lines)

    def raw(pairs: Sequence[CodePair]) -> np.ndarray:
        out = []
        for p in pairs:
            _, s = bm.best_line(p.hypothesis, [ln.text for ln in p.lines])
            out.append(s)
        return np.asarray(out, dtype=float).reshape(-1, 1)

    x_tr, y_tr = raw(train), [p.label for p in train]
    clf = LogisticRegression(max_iter=1000).fit(x_tr, y_tr)
    probs = clf.predict_proba(raw(test))[:, 1]
    return [float(x) for x in probs], {
        "idf_vocabulary": len(bm.idf),
        "idf_documents": bm.n_docs,
        "platt_coef": round(float(clf.coef_[0][0]), 4),
        "platt_intercept": round(float(clf.intercept_[0]), 4),
    }


# ---------------------------------------------------------------------------
# Arm 2 — the cross-encoder
# ---------------------------------------------------------------------------


def cross_encoder_probabilities(
    test: Sequence[CodePair], model_dir: Path
) -> tuple[list[float], dict[str, Any]]:
    from vitera.models.cross_encoder import CrossEncoderScorer

    scorer = CrossEncoderScorer.load(model_dir)
    meta = json.loads((model_dir / "calibration.json").read_text(encoding="utf-8"))
    return scorer.probabilities(test), {
        "checkpoint": str(model_dir),
        "model_name": meta["model_name"],
        "seed": meta["seed"],
        "temperature": meta["temperature"],
        "train_prior": meta["train_prior"],
        "deployment_prior": meta["deployment_prior"],
        "dev_sites_held_out": meta["dev_sites"],
    }


# ---------------------------------------------------------------------------
# Shortcut controls — run whenever the headline number is high
# ---------------------------------------------------------------------------


def controls(test: Sequence[CodePair], model_dir: Path, *, seed: int) -> dict[str, Any]:
    """Two ablations that must FAIL, or the headline result is a shortcut.

    A PR-AUC near 1.0 on synthetic data is exactly the number a judge will
    attack, and the two ways it could be hollow are both testable:

    `hypothesis_only` — evidence blanked, so the model sees only the coded
    diagnosis. Code identity correlates with the label in this corpus by
    construction (D7 adds *heavy* comorbidities; D3 adds unused ones), so a
    model that learned a per-code prior instead of reading the record would
    still score well here. Above chance means part of the headline is that
    shortcut and the per-class numbers need discounting.

    `evidence_shuffled` — each hypothesis paired with another episode's record.
    A model that reads the pair must lose all signal; one that learned a
    marginal cue in the evidence would keep some.

    Both are reported next to the headline whether they pass or not. An
    unreported control is not a control.
    """
    from dataclasses import replace

    from vitera.models.cross_encoder import CrossEncoderScorer

    scorer = CrossEncoderScorer.load(model_dir)
    labels = [p.label for p in test]

    blanked = [replace(p, evidence="", lines=()) for p in test]

    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(test))
    # A derangement in practice: any pair left with its own evidence would
    # leak a genuine signal into a control that is supposed to have none.
    perm = np.array([j if j != i else (j + 1) % len(test) for i, j in enumerate(perm)])
    shuffled = [
        replace(p, evidence=test[j].evidence, lines=test[j].lines)
        for p, j in zip(test, perm, strict=True)
    ]

    out = {}
    for name, pairs in (("hypothesis_only", blanked), ("evidence_shuffled", shuffled)):
        probs = scorer.probabilities(pairs)
        rep = calibrate.report(probs, labels)
        lo, hi = calibrate.bootstrap_ci(probs, labels, metric="roc_auc")
        out[name] = {
            "roc_auc": rep["roc_auc"],
            "roc_auc_ci95": [lo, hi],
            "pr_auc": rep["pr_auc"],
            "chance_roc_auc": 0.5,
            "chance_pr_auc": rep["positive_rate"],
            "passes": bool(lo <= 0.5 <= hi),
        }
    return out


# ---------------------------------------------------------------------------
# Arm 3 — zero-shot LLM
# ---------------------------------------------------------------------------

_ZERO_SHOT = """Anda membantu verifikator internal klaim BPJS di rumah sakit Indonesia.

Berikut kutipan rekam medis rawat inap seorang pasien:
---
{evidence}
---

Pada klaim, koder menuliskan: {hypothesis}

Apakah dokumentasi di atas mendukung kode diagnosis tersebut?
Jawab HANYA dengan satu angka antara 0.00 dan 1.00, yaitu probabilitas bahwa
diagnosis tersebut TIDAK didukung oleh dokumentasi. Tanpa penjelasan."""


def llm_probabilities(
    test: Sequence[CodePair], *, sample: int, seed: int
) -> tuple[list[float], list[int], dict[str, Any]]:
    """Zero-shot arm. Returns (probs, indices scored, metadata).

    Runs through `agent.boundary.LLMClient`, so it inherits pseudonymisation
    (architectural rule 3) and `VITERA_LLM_MODE`. In `cache` mode a prompt that
    was never recorded raises rather than silently going live — which is why
    this arm reports `not_run` instead of a number until bucket 9 binds a
    provider and a rehearsal in `record` mode populates the cache.
    """
    from vitera.agent.boundary import LLMClient, pseudonymise

    rng = np.random.default_rng(seed)
    n = min(sample, len(test))
    idx = sorted(rng.choice(len(test), size=n, replace=False).tolist())
    client = LLMClient()

    probs: list[float] = []
    scored: list[int] = []
    errors: list[str] = []
    for i in idx:
        p = test[i]
        prompt = pseudonymise(
            _ZERO_SHOT.format(evidence=p.evidence, hypothesis=p.hypothesis)
        )
        try:
            text = client.complete(prompt, max_tokens=8).text
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            if len(errors) >= 3:  # not a transient failure; stop spending
                break
            continue
        value = _parse_probability(text)
        if value is None:
            errors.append(f"unparseable: {text!r}")
            continue
        probs.append(value)
        scored.append(i)

    return (
        probs,
        scored,
        {
            "mode": config.llm_mode(),
            "requested_sample": sample,
            "scored": len(scored),
            "errors": errors[:3],
            "cache_hits": client.cache_hits,
            "live_calls": client.calls,
        },
    )


def _parse_probability(text: str) -> float | None:
    import re

    m = re.search(r"[01](?:\.\d+)?", text.strip())
    if not m:
        return None
    v = float(m.group(0))
    return v if 0.0 <= v <= 1.0 else None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def per_class(
    probs: Sequence[float], pairs: Sequence[CodePair], flag_at: float
) -> dict[str, Any]:
    """Each class against the same negatives: every supported code.

    Restricting negatives to a class-specific pool would let a class look good
    because its negatives are easy. The negative pool is what the koder faces
    in production — all the codes that are fine.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray([q.label for q in pairs], dtype=int)
    cls = np.asarray([q.defect_class or "" for q in pairs])
    neg = y == 0

    out: dict[str, Any] = {}
    for c in CLASSES:
        m = neg | (cls == c)
        if not (cls == c).any():
            continue
        sub_p, sub_y = p[m], y[m]
        tp = int(((sub_p >= flag_at) & (sub_y == 1)).sum())
        block = calibrate.report(sub_p, sub_y)
        lo, hi = calibrate.bootstrap_ci(sub_p, sub_y, metric="pr_auc")
        block.update(
            {
                "positives": int((cls == c).sum()),
                "pr_auc_ci95": [lo, hi],
                "recall_at_flag_at": round(tp / max(1, int((sub_y == 1).sum())), 4),
                "precision_at_flag_at": round(
                    tp / max(1, int((sub_p >= flag_at).sum())), 4
                ),
            }
        )
        out[c] = block
    return out


def code_conditional(
    probs: Sequence[float], pairs: Sequence[CodePair]
) -> dict[str, Any]:
    """Separation *within* each ICD-10 code, pooled.

    The unconditional numbers above are inflated by a per-code prior: in this
    corpus some codes are far likelier to be defective than others (D7 adds
    severity-weighted comorbidities, D3 draws from the ones the group did not
    have, supported codes are drawn by prevalence), and the
    `hypothesis_only` control shows a model can exploit that without reading a
    record at all.

    Conditioning on the code removes the prior completely: for each code, only
    supported-vs-unsupported instances *of that same code* are compared. What
    survives is separation that had to come from the evidence. This is the
    number the paper should lead with, and it is lower than the headline.

    Pooled as a Mann-Whitney estimate weighted by each code's positive-negative
    pair count, which is what an unconditional ROC-AUC would be if the prior
    carried no information.
    """
    from sklearn.metrics import roc_auc_score

    p = np.asarray(probs, dtype=float)
    y = np.asarray([q.label for q in pairs], dtype=int)
    codes = np.asarray([q.code for q in pairs])

    per_code: dict[str, Any] = {}
    num = den = 0.0
    for code in sorted(set(codes.tolist())):
        m = codes == code
        yc, pc = y[m], p[m]
        n_pos, n_neg = int((yc == 1).sum()), int((yc == 0).sum())
        if n_pos == 0 or n_neg == 0:
            continue
        auc = float(roc_auc_score(yc, pc))
        weight = n_pos * n_neg
        num += auc * weight
        den += weight
        per_code[code] = {
            "n_positive": n_pos,
            "n_negative": n_neg,
            "roc_auc": round(auc, 4),
        }
    return {
        "pooled_roc_auc": round(num / den, 4) if den else None,
        "codes_scorable": len(per_code),
        "codes_unscorable": len(set(codes.tolist())) - len(per_code),
        "per_code": per_code,
    }


def score_arm(
    name: str,
    probs: Sequence[float],
    pairs: Sequence[CodePair],
    *,
    target_fpr: float,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Score one arm at its **own** budget-matched threshold.

    Not at a shared numeric threshold: the arms produce probabilities on
    different scales (temperature scaling vs. Platt scaling on a BM25 score),
    so a single cut-off would compare calibration accident rather than
    separation. Every arm is instead asked the question a hospital asks — *at
    the false-positive rate we are willing to live with, how much do you
    catch?* — and answers it at whatever threshold that costs it.
    """
    labels = [p.label for p in pairs]
    op = calibrate.recommend_thresholds(probs, labels, target_fpr=target_fpr)
    overall = calibrate.report(probs, labels)
    lo, hi = calibrate.bootstrap_ci(probs, labels, metric="pr_auc")
    neg = np.asarray(probs)[np.asarray(labels) == 0]
    return {
        "arm": name,
        "status": "ok",
        "meta": meta,
        "overall": overall | {"pr_auc_ci95": [lo, hi]},
        "operating_point": _asdict(op),
        "supported_code_false_positive_rate": round(
            float((neg >= op.flag_at).mean()), 4
        ),
        "recall_at_budget": op.recall_at_flag_at,
        "code_conditional": code_conditional(probs, pairs),
        "per_class": per_class(probs, pairs, op.flag_at),
        "reliability": calibrate.reliability(probs, labels),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=Path("data/generated"))
    p.add_argument("--model", type=Path, default=DEFAULT_MODEL_DIR)
    p.add_argument("--out", type=Path, default=Path("results/cross_encoder.json"))
    p.add_argument("--seed", type=int, default=config.DEFAULT_SEED)
    p.add_argument("--target-fpr", type=float, default=0.10)
    p.add_argument("--llm-sample", type=int, default=300)
    p.add_argument("--skip-llm", action="store_true")
    p.add_argument("--skip-controls", action="store_true")
    a = p.parse_args()

    train = iter_pairs(load_jsonl(a.data / "train.jsonl"), split="train")
    test = iter_pairs(load_jsonl(a.data / "test.jsonl"), split="test")
    labels = [q.label for q in test]
    print(
        f"pairs: {len(train)} train / {len(test)} test, "
        f"test positive rate {np.mean(labels):.3f}"
    )

    arms: dict[str, Any] = {}

    # --- the operating point comes from the deployed arm ------------------
    try:
        ce_probs, ce_meta = cross_encoder_probabilities(test, a.model)
    except Exception as exc:
        print(f"cross-encoder unavailable: {exc}")
        ce_probs, ce_meta = None, {"error": str(exc)}

    if ce_probs is None:
        raise SystemExit(
            "no cross-encoder checkpoint — run `make train` first. "
            "Bucket 8's result is the comparison, and it needs the model."
        )

    op = calibrate.recommend_thresholds(ce_probs, labels, target_fpr=a.target_fpr)
    op_hp = calibrate.recommend_thresholds(ce_probs, labels, target_fpr=0.02)

    arms["cross_encoder"] = score_arm(
        "cross_encoder", ce_probs, test, target_fpr=a.target_fpr, meta=ce_meta
    )

    bm_probs, bm_meta = bm25_probabilities(train, test)
    arms["bm25"] = score_arm(
        "bm25", bm_probs, test, target_fpr=a.target_fpr, meta=bm_meta
    )

    if a.skip_llm:
        arms["llm_zero_shot"] = {
            "arm": "llm_zero_shot",
            "status": "skipped",
            "reason": "--skip-llm",
        }
    else:
        llm_probs, idx, llm_meta = llm_probabilities(
            test, sample=a.llm_sample, seed=a.seed
        )
        if len(llm_probs) < 30:
            arms["llm_zero_shot"] = {
                "arm": "llm_zero_shot",
                "status": "not_run",
                "meta": llm_meta,
                "reason": (
                    "no provider binding yet (bucket 9) and no recorded cache. "
                    "The third arm is unmeasured; it is not zero."
                ),
            }
        else:
            subset = [test[i] for i in idx]
            arms["llm_zero_shot"] = score_arm(
                "llm_zero_shot",
                llm_probs,
                subset,
                target_fpr=a.target_fpr,
                meta=llm_meta,
            )

    ctrl = {} if a.skip_controls else controls(test, a.model, seed=a.seed)

    result = {
        "n_test_pairs": len(test),
        "target_false_positive_rate": a.target_fpr,
        "n_train_pairs": len(train),
        "test_positive_rate": round(float(np.mean(labels)), 4),
        "operating_point": {
            "default": _asdict(op),
            "high_precision": _asdict(op_hp),
        },
        "arms": arms,
        "shortcut_controls": ctrl,
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    _print(result)


def _asdict(op: calibrate.OperatingPoint) -> dict[str, Any]:
    return {f: getattr(op, f) for f in op.__slots__}


def _print(result: dict[str, Any]) -> None:
    print(f"\nBUCKET 8 — code-support scoring, n={result['n_test_pairs']} test pairs\n")
    header = (
        f"{'arm':16} {'PR-AUC':>16} {'ROC-AUC':>8} {'ECE':>7} {'FPR':>6} {'recall':>7}"
    )
    print(header)
    print("-" * len(header))
    for name, arm in result["arms"].items():
        if arm.get("status") != "ok":
            print(f"{name:16} {arm['status']:>16}   {arm.get('reason', '')[:40]}")
            continue
        o = arm["overall"]
        ci = o["pr_auc_ci95"]
        print(
            f"{name:16} {o['pr_auc']:>7.3f} [{ci[0]:.3f},{ci[1]:.3f}] "
            f"{o['roc_auc']:>7.3f} {o['ece']:>7.3f} "
            f"{arm['supported_code_false_positive_rate']:>6.3f} "
            f"{arm['recall_at_budget']:>7.3f}"
        )

    print(
        f"\nevery arm cut at its own threshold for a "
        f"{result['target_false_positive_rate']:.0%} false-positive budget"
    )
    print("\nper class (PR-AUC)")
    print(f"{'class':6} " + " ".join(f"{n:>22}" for n in result["arms"]))
    for c in CLASSES:
        cells = []
        for arm in result["arms"].values():
            block = (arm.get("per_class") or {}).get(c)
            cells.append(
                f"{block['pr_auc']:.3f} (n={block['positives']:>3})".rjust(22)
                if block
                else "—".rjust(22)
            )
        print(f"{c:6} " + " ".join(cells))

    print("\ncode-conditional ROC-AUC (per-code prior removed)")
    for name, arm in result["arms"].items():
        cc = (arm.get("code_conditional") or {}).get("pooled_roc_auc")
        if cc is not None:
            uncond = arm["overall"]["roc_auc"]
            print(f"  {name:16} {cc:.3f}   (unconditional {uncond:.3f})")

    for name, c in (result.get("shortcut_controls") or {}).items():
        verdict = "at chance (good)" if c["passes"] else "ABOVE CHANCE — shortcut"
        print(
            f"\ncontrol {name:18} ROC-AUC {c['roc_auc']:.3f} "
            f"[{c['roc_auc_ci95'][0]:.3f},{c['roc_auc_ci95'][1]:.3f}] -> {verdict}"
        )

    op = result["operating_point"]["default"]
    print(
        f"\ndeployed operating point (default profile): flag_at={op['flag_at']} "
        f"abstain_below={op['abstain_below']}"
    )
    print(
        f"  target FPR {op['target_false_positive_rate']} -> achieved "
        f"{op['achieved_false_positive_rate']}, recall {op['recall_at_flag_at']}, "
        f"precision {op['precision_at_flag_at']}"
    )
    hp = result["operating_point"]["high_precision"]
    print(
        f"operating point (high_precision): flag_at={hp['flag_at']} "
        f"abstain_below={hp['abstain_below']} "
        f"(FPR {hp['achieved_false_positive_rate']}, recall {hp['recall_at_flag_at']})"
    )


if __name__ == "__main__":
    main()
