"""
Language identification using the trained dual-adapter LR classifier.

The classifier was produced by LANG_ID_VM/train_lid.py. It expects features
extracted by applying std/max/min pooling over the wav2vec2 encoder's
last_hidden_state for both the nld and fry adapters, concatenated in that order.
"""

import pickle
from pathlib import Path

import numpy as np
import torch

from .config import LANG_ID_MODEL_PATH


_state: dict = {
    "scaler":     None,
    "classifier": None,
    "stats":      ["std", "max", "min"],
}


def load_lang_id() -> None:
    path = Path(LANG_ID_MODEL_PATH) if LANG_ID_MODEL_PATH else None
    if not path or not path.exists():
        raise FileNotFoundError(f"Language ID model not found: {LANG_ID_MODEL_PATH!r}")
    with open(path, "rb") as f:
        payload = pickle.load(f)
    _state["scaler"]     = payload["scaler"]
    _state["classifier"] = payload["classifier"]
    _state["stats"]      = payload.get("stats", ["std", "max", "min"])


def lang_id_ready() -> bool:
    return _state["classifier"] is not None


def get_stats() -> list[str]:
    return _state["stats"]


def pool_hidden(hidden: torch.Tensor, stats: list[str]) -> np.ndarray:
    """Apply temporal pooling over encoder hidden states (shape: 1 × T × D)."""
    parts = []
    for s in stats:
        if s == "std":
            parts.append(hidden.std(dim=1))
        elif s == "max":
            parts.append(hidden.max(dim=1).values)
        elif s == "min":
            parts.append(hidden.min(dim=1).values)
        elif s == "mean":
            parts.append(hidden.mean(dim=1))
    return torch.cat(parts, dim=-1).squeeze(0).cpu().numpy()


def classify_from_embeddings(nld_emb: np.ndarray, fry_emb: np.ndarray) -> tuple[str, float]:
    """Run the classifier given pre-computed pooled embeddings.

    Accepts embeddings extracted from the nld and fry encoder passes in that
    order — matching the order used during training in train_lid.py.
    Returns (language, fry_probability).  Label 0 = fry, label 1 = nld.
    """
    scaler = _state["scaler"]
    clf    = _state["classifier"]
    emb    = np.concatenate([nld_emb, fry_emb])
    emb_s  = scaler.transform(emb.reshape(1, -1))
    proba  = clf.predict_proba(emb_s)[0]
    fry_prob = float(proba[0])
    return ("fry" if fry_prob >= 0.5 else "nld"), fry_prob


def classify_language(audio: np.ndarray, sr: int = 16000) -> tuple[str, float]:
    """Return (language, fry_probability) for the given audio clip.

    Runs both MMS encoder passes.  In the transcription pipeline, prefer
    classify_from_embeddings() with embeddings already computed by run_hybrid()
    to avoid a redundant second forward pass.
    """
    from .models import MODELS, get_device

    stats  = _state["stats"]
    device = get_device()

    embeddings: dict[str, np.ndarray] = {}
    for lang in ("nld", "fry"):  # order must match training
        info   = MODELS[f"mms-1b-all-{lang}"]
        proc   = info["processor"]
        model  = info["instance"]
        inputs = proc(audio, sampling_rate=sr, return_tensors="pt")
        iv     = inputs["input_values"].to(device)
        with torch.no_grad():
            hidden = model.wav2vec2(iv).last_hidden_state
        embeddings[lang] = pool_hidden(hidden, stats)

    return classify_from_embeddings(embeddings["nld"], embeddings["fry"])
