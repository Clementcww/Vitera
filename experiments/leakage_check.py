"""`make leakage` — does the generator leak the defect label through text?

If a classifier reading ONLY the clinical narrative — no codes — can predict
whether a claim carries a defect, then the generator has left a stylistic
fingerprint and every downstream result is void. The model would be reading our
generation process, not clinical evidence.

**Two tests, because they answer different questions.**

1. *Code-mutation defects* (D2, D3, D4, D6, D7). These change codes only; the
   narrative is byte-identical to the clean version. A classifier must score at
   chance. **This is the test that can void the corpus.**

2. *Document-availability defects* (D1, D5). These remove pages, so the text
   genuinely differs — that is the defect, not a fingerprint, and a rules
   engine is supposed to catch it. Reported separately so the honest number is
   not diluted by the trivially-detectable one.

Reports ROC-AUC with a bootstrap CI. Chance is 0.50.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

DOC_DEFECTS = {"D1", "D5"}
CODE_DEFECTS = {"D2", "D3", "D4", "D6", "D7"}


def _load(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _narrative(row: dict[str, Any]) -> str:
    """Clinical text only. No codes, no claim fields, nothing structured."""
    present = set(row["claim"]["documents_present"])
    return "\n".join(
        d["text"] for d in row["episode"]["documents"] if d["doc_id"] in present
    )


def _labels(row: dict[str, Any], classes: set[str]) -> int:
    return int(any(d["defect_class"] in classes for d in row["defects"]))


# --- classifier, in numpy -------------------------------------------------
# Deliberately dependency-light: TF-IDF + regularised logistic regression is
# more than strong enough to expose a stylistic fingerprint, and keeping scipy
# off the critical path means this runs on any machine on day one.


def _tokenise(text: str) -> list[str]:
    out, cur = [], []
    for ch in text.lower():
        if ch.isalnum():
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out + [f"{a}_{b}" for a, b in zip(out, out[1:])]  # unigrams + bigrams


def _tfidf(train: list[str], test: list[str], max_features: int = 20000):
    import math

    import numpy as np

    df: dict[str, int] = {}
    tok_tr = [_tokenise(t) for t in train]
    for toks in tok_tr:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    vocab_terms = sorted(df, key=lambda t: (-df[t], t))[:max_features]
    vocab = {t: i for i, t in enumerate(vocab_terms)}
    n = len(train)
    idf = np.array([math.log((1 + n) / (1 + df[t])) + 1.0 for t in vocab_terms])

    def vec(docs: list[list[str]]):
        m = np.zeros((len(docs), len(vocab)), dtype=np.float32)
        for i, toks in enumerate(docs):
            counts: dict[int, int] = {}
            for t in toks:
                j = vocab.get(t)
                if j is not None:
                    counts[j] = counts.get(j, 0) + 1
            for j, c in counts.items():
                m[i, j] = (1.0 + math.log(c)) * idf[j]  # sublinear tf
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        return m / np.maximum(norms, 1e-9)

    return vec(tok_tr), vec([_tokenise(t) for t in test])


def _fit_logreg(x, y, epochs: int = 300, lr: float = 0.5, l2: float = 1e-3):
    import numpy as np

    y = np.asarray(y, dtype=np.float32)
    w = np.zeros(x.shape[1], dtype=np.float32)
    b = np.float32(0.0)
    # class_weight="balanced"
    pos, neg = float(y.sum()), float(len(y) - y.sum())
    sw = np.where(y == 1, len(y) / (2 * max(pos, 1)), len(y) / (2 * max(neg, 1)))
    for _ in range(epochs):
        p = 1.0 / (1.0 + np.exp(-(x @ w + b)))
        g = (p - y) * sw
        w -= lr * ((x.T @ g) / len(y) + l2 * w)
        b -= lr * float(g.mean())
    return w, b


def _roc_auc(y: list[int], scores) -> float:
    import numpy as np

    y_arr = np.asarray(y)
    order = np.argsort(np.asarray(scores))
    ranks = np.empty(len(y_arr), dtype=np.float64)
    ranks[order] = np.arange(1, len(y_arr) + 1)
    pos, neg = y_arr.sum(), len(y_arr) - y_arr.sum()
    if pos == 0 or neg == 0:
        return float("nan")
    return float((ranks[y_arr == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


def run(train_rows: list, test_rows: list, cls: str, name: str) -> dict:
    """Leakage test for ONE defect class.

    The pool is: episodes ELIGIBLE for `cls`, carrying no defect other than
    `cls`. Positives and negatives are then structurally identical — same
    comorbidities, same procedures, same narrative — differing only in whether
    a code was mutated. Any AUC above chance in that pool is a genuine
    stylistic fingerprint.

    Testing several classes jointly does NOT work, and our first two runs
    failed because of it: an episode eligible for more classes is more likely
    to carry some defect, eligibility is visible in the text, and the
    classifier reads that instead of the mutation. Per-class is the only
    conditioning that removes the confound.
    """
    import numpy as np

    def prep(rows: list) -> tuple[list[str], list[int]]:
        keep = [
            r
            for r in rows
            if cls in r["eligible_for"]
            and all(d["defect_class"] == cls for d in r["defects"])
        ]
        return (
            [_narrative(r) for r in keep],
            [int(any(d["defect_class"] == cls for d in r["defects"])) for r in keep],
        )

    xtr_raw, ytr = prep(train_rows)
    xte_raw, yte = prep(test_rows)

    if len(set(ytr)) < 2 or len(set(yte)) < 2:
        return {"test": name, "auc": None, "note": "insufficient class balance"}

    xtr, xte = _tfidf(xtr_raw, xte_raw)
    w, b = _fit_logreg(xtr, ytr)
    scores = list(1.0 / (1.0 + np.exp(-(xte @ w + b))))
    auc = _roc_auc(yte, scores)

    rng = random.Random(0)
    boots = []
    idx = list(range(len(yte)))
    for _ in range(400):
        s = [rng.choice(idx) for _ in idx]
        if len(set(yte[i] for i in s)) < 2:
            continue
        boots.append(_roc_auc([yte[i] for i in s], [scores[i] for i in s]))
    boots.sort()
    lo, hi = boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]

    return {
        "test": name,
        "n_train": len(ytr),
        "n_test": len(yte),
        "positive_rate_test": round(sum(yte) / len(yte), 4),
        "auc": round(auc, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "chance_in_ci": bool(lo <= 0.5 <= hi),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("data/generated"))
    p.add_argument("--out", type=Path, default=Path("results/leakage_check.json"))
    a = p.parse_args()

    train, test = _load(a.data / "train.jsonl"), _load(a.data / "test.jsonl")

    results = [
        run(train, test, c, f"{c} ({'code mutation' if c in CODE_DEFECTS else 'document availability'})")
        for c in sorted(CODE_DEFECTS | DOC_DEFECTS)
    ]

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"{'class':6} {'n_test':>7} {'pos':>7} {'AUC':>7}  {'95% CI':<18} verdict")
    for r in results:
        if r.get("auc") is None:
            print(f"{r['test'][:2]:6} {'-':>7} {'-':>7} {'-':>7}  {'-':<18} inconclusive")
            continue
        ci = f"[{r['ci95'][0]:.3f}, {r['ci95'][1]:.3f}]"
        ok = "at chance" if r["chance_in_ci"] else "LEAKS"
        print(
            f"{r['test'][:2]:6} {r['n_test']:>7} {r['positive_rate_test']:>7.3f} "
            f"{r['auc']:>7.3f}  {ci:<18} {ok}"
        )

    code_results = [r for r in results if r["test"][:2] in CODE_DEFECTS and r.get("auc")]
    leaking = [r["test"][:2] for r in code_results if not r["chance_in_ci"]]
    print()
    if leaking:
        print(
            f"FAIL — code-mutation classes leaking: {', '.join(leaking)}.\n"
            "Text alone predicts the label, so the model would read our generation\n"
            "process rather than clinical evidence. Downstream results are void\n"
            "until this is fixed."
        )
        raise SystemExit(1)
    print(
        "PASS — no code-mutation class is detectable from narrative alone.\n"
        "D1/D5 are expected above chance: they remove pages, so the text really\n"
        "does differ. That is the defect, not a fingerprint, and the rules engine\n"
        "is supposed to catch it."
    )


if __name__ == "__main__":
    main()
