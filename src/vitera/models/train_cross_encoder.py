"""Fine-tune the cross-encoder — bucket 8, `make train`.

IndoBERT-base (`indobenchmark/indobert-base-p1`, 124M params), self-hosted,
fine-tuned as a pair classifier over (coded diagnosis, clinical evidence). A
locked decision: the cross-encoder is the clinical judge, and it is the only
component allowed to decide whether free text supports a code.

Three things this script is careful about, each because getting it wrong makes
the headline number a lie rather than a result:

- **The dev split is by site, never by row.** Episodes from one hospital share
  a documentation style; splitting by row lets the model see that style in
  training and be rewarded for it at validation. Temperature is fitted on this
  dev split, so a leaky split would also produce a calibration plot that
  flatters the model.
- **Seeds are derived from the master seed** and recorded into
  `calibration.json` beside the weights, so a checkpoint can always be traced
  to the run that produced it.
- **Nothing here reads a threshold.** Thresholds come from
  `config/thresholds.yaml` and are chosen by `calibrate.recommend_thresholds`
  after the fact. A model that trains against its own operating point cannot
  be re-thresholded for a hospital that wants higher precision.

Runs on MPS on Apple silicon, CUDA if present, CPU otherwise. ~6k pairs and
three epochs is minutes, not hours — this is deliberately a small model.
"""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from vitera import config
from vitera.models.pairs import CodePair, iter_pairs

MODEL_NAME = "indobenchmark/indobert-base-p1"
DEFAULT_OUT = Path("models/cross_encoder")
MAX_LEN = 288  # p99 of the pair corpus is 261 tokens; nothing real is truncated


@dataclass(frozen=True, slots=True)
class TrainConfig:
    model_name: str = MODEL_NAME
    max_len: int = MAX_LEN
    batch_size: int = 16
    epochs: int = 3
    lr: float = 2e-5
    warmup_ratio: float = 0.1
    dev_site_share: float = 0.25


def device() -> Any:
    import torch

    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def split_by_site(
    pairs: Sequence[CodePair], *, dev_share: float, seed: int
) -> tuple[list[CodePair], list[CodePair]]:
    """Hold out whole hospitals. The design brief data rule 3, applied again inside
    the training split — the corpus already holds sites out for test, and dev
    must not borrow them back."""
    sites = sorted({p.site_id for p in pairs})
    rng = random.Random(seed)
    rng.shuffle(sites)
    n_dev = max(1, round(len(sites) * dev_share))
    dev_sites = set(sites[:n_dev])
    fit = [p for p in pairs if p.site_id not in dev_sites]
    dev = [p for p in pairs if p.site_id in dev_sites]
    return fit, dev


def encode(tok: Any, pairs: Sequence[CodePair], max_len: int) -> Any:
    """`truncation='only_second'` keeps the hypothesis whole and trims the
    evidence tail. The hypothesis is one short sentence; losing half of it
    would change the question being asked."""
    return tok(
        [p.hypothesis for p in pairs],
        [p.evidence for p in pairs],
        truncation="only_second",
        max_length=max_len,
        padding="max_length",
        return_tensors="pt",
    )


def predict_logits(
    model: Any,
    tok: Any,
    pairs: Sequence[CodePair],
    *,
    max_len: int,
    batch_size: int = 32,
) -> np.ndarray:
    """Margin logit for the positive (unsupported) class."""
    import torch

    dev = device()
    model.eval()
    out: list[float] = []
    with torch.no_grad():
        for i in range(0, len(pairs), batch_size):
            batch = encode(tok, pairs[i : i + batch_size], max_len)
            batch = {k: v.to(dev) for k, v in batch.items()}
            logits = model(**batch).logits
            out.extend((logits[:, 1] - logits[:, 0]).detach().cpu().tolist())
    return np.asarray(out, dtype=float)


def train(
    pairs: Sequence[CodePair], cfg: TrainConfig, *, seed: int, out_dir: Path
) -> dict[str, Any]:
    import torch
    from torch.utils.data import DataLoader, TensorDataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.manual_seed(seed)
    np.random.seed(seed % (2**31 - 1))
    random.seed(seed)

    fit, dev_pairs = split_by_site(pairs, dev_share=cfg.dev_site_share, seed=seed)
    if not fit or not dev_pairs:
        raise ValueError("site split produced an empty side; check the corpus")

    tok = AutoTokenizer.from_pretrained(cfg.model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        cfg.model_name, num_labels=2
    )
    dev = device()
    model.to(dev)

    enc = encode(tok, fit, cfg.max_len)
    labels = torch.tensor([p.label for p in fit], dtype=torch.long)
    ds = TensorDataset(
        enc["input_ids"], enc["attention_mask"], enc["token_type_ids"], labels
    )
    loader = DataLoader(
        ds,
        batch_size=cfg.batch_size,
        shuffle=True,
        generator=torch.Generator().manual_seed(seed),
    )

    steps = len(loader) * cfg.epochs
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt,
        max_lr=cfg.lr,
        total_steps=steps,
        pct_start=cfg.warmup_ratio,
        anneal_strategy="linear",
    )

    history: list[dict[str, float]] = []
    for epoch in range(cfg.epochs):
        model.train()
        running = 0.0
        for input_ids, attn, ttype, y in loader:
            opt.zero_grad()
            loss = model(
                input_ids=input_ids.to(dev),
                attention_mask=attn.to(dev),
                token_type_ids=ttype.to(dev),
                labels=y.to(dev),
            ).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            running += float(loss.item())
        mean_loss = running / max(1, len(loader))
        history.append({"epoch": epoch + 1, "train_loss": round(mean_loss, 4)})
        print(f"  epoch {epoch + 1}/{cfg.epochs}  train_loss={mean_loss:.4f}")

    # --- calibration, on held-out sites only ------------------------------
    from vitera.models.calibrate import fit_temperature, report, sigmoid

    dev_logits = predict_logits(model, tok, dev_pairs, max_len=cfg.max_len)
    dev_labels = [p.label for p in dev_pairs]
    temperature = fit_temperature(dev_logits, dev_labels)

    train_prior = float(np.mean([p.label for p in fit]))
    deployment_prior = 1.0 - float(
        config.thresholds()["deployment_prior"]["codes_correct"]
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir)
    tok.save_pretrained(out_dir)

    meta = {
        "model_name": cfg.model_name,
        "seed": seed,
        "config": asdict(cfg),
        "n_fit_pairs": len(fit),
        "n_dev_pairs": len(dev_pairs),
        "dev_sites": sorted({p.site_id for p in dev_pairs}),
        "train_prior": round(train_prior, 4),
        "deployment_prior": round(deployment_prior, 4),
        "temperature": round(temperature, 4),
        "history": history,
        "dev_uncalibrated": report(sigmoid(dev_logits), dev_labels),
        "dev_calibrated": report(sigmoid(dev_logits / temperature), dev_labels),
        "device": str(device()),
    }
    (out_dir / "calibration.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return meta


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=Path("data/generated"))
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--seed", type=int, default=config.DEFAULT_SEED)
    # `slots=True` means the class attributes are descriptors, not values —
    # read the defaults off an instance.
    d = TrainConfig()
    p.add_argument("--epochs", type=int, default=d.epochs)
    p.add_argument("--batch-size", type=int, default=d.batch_size)
    p.add_argument("--max-len", type=int, default=d.max_len)
    a = p.parse_args()

    with (a.data / "train.jsonl").open(encoding="utf-8") as fh:
        rows = [json.loads(x) for x in fh if x.strip()]
    pairs = iter_pairs(rows)
    print(
        f"cross-encoder: {len(pairs)} pairs from {len(rows)} train episodes, "
        f"positive rate {np.mean([q.label for q in pairs]):.3f}, device {device()}"
    )

    cfg = TrainConfig(epochs=a.epochs, batch_size=a.batch_size, max_len=a.max_len)
    stage_seed = config.seeds(a.seed).for_stage("cross_encoder")
    meta = train(pairs, cfg, seed=stage_seed, out_dir=a.out)

    print(f"\nsaved to {a.out}")
    print(f"  temperature      : {meta['temperature']}")
    print(f"  train prior      : {meta['train_prior']}")
    print(f"  deployment prior : {meta['deployment_prior']}")
    print(f"  dev PR-AUC       : {meta['dev_calibrated']['pr_auc']}")
    print(f"  dev ECE (raw)    : {meta['dev_uncalibrated']['ece']}")
    print(f"  dev ECE (scaled) : {meta['dev_calibrated']['ece']}")


if __name__ == "__main__":
    main()


__all__ = [
    "MAX_LEN",
    "MODEL_NAME",
    "TrainConfig",
    "device",
    "predict_logits",
    "split_by_site",
    "train",
]
