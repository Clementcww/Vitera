"""The one deep learning component: (code description, clinical text) -> supported?

Same question for every judgement class. M1, M2, M4 and D8 are all this call
with different inputs, which is why there is one model and not five classifiers.

With `encoder.model_path: null` in config.yaml the stub answers instead, so the
pipeline is runnable before any weights exist. The stub returns the lexicon's
own prior — it invents nothing, and it never makes the model look better than
it is.
"""

import logging
from typing import List, Sequence, Tuple

from dto.types import SafeText
from service.config import config

logger = logging.getLogger("vitera.crossencoder")

_model = None
_tokenizer = None


def _load():
    """Lazy load. Import torch only when weights are actually configured."""
    global _model, _tokenizer
    if _model is not None:
        return _model, _tokenizer

    path = config()["encoder"]["model_path"]
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    logger.info(f"[Encoder] loading cross-encoder from {path}")
    _tokenizer = AutoTokenizer.from_pretrained(path)
    _model = AutoModelForSequenceClassification.from_pretrained(path)
    _model.eval()
    return _model, _tokenizer


def is_stubbed() -> bool:
    return config()["encoder"]["model_path"] is None


def verify(pairs: Sequence[Tuple[str, SafeText]], priors: Sequence[float]) -> List[float]:
    """Score each (code description, redacted text) pair in [0, 1].

    `priors` is only read by the stub. It stays in the signature so switching
    weights on is a config edit and not a call-site edit.
    """
    if not pairs:
        return []

    if is_stubbed():
        logger.warning(f"[Encoder] STUBBED — returning lexicon priors for {len(pairs)} pair(s)")
        return list(priors)

    import torch

    model, tokenizer = _load()
    batch = tokenizer(
        [description for description, _ in pairs],
        [str(text) for _, text in pairs],
        padding=True,
        truncation=True,
        max_length=config()["encoder"]["max_length"],
        return_tensors="pt",
    )
    with torch.no_grad():
        logits = model(**batch).logits
    return torch.softmax(logits, dim=-1)[:, 1].tolist()
