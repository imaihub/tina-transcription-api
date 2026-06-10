"""
Hybrid transcription: run the fry and nld encoders to extract language-ID
embeddings, use the classifier to select the winning language, then run the
KenLM beam search only for that winner.

Encoding and decoding are kept separate so that in nld+fry mode we pay for two
encoder passes (both are needed for language ID) but only one beam search — the
beam search is the dominant CPU cost, so decoding only the winner roughly halves
it versus decoding both languages and discarding the loser.
"""

import numpy as np
import torch

from .kenlm import beam_decode_top_n, decoder_ready
from .lang_id import classify_from_embeddings, get_stats, pool_hidden
from .models import MODELS, get_device


def _encode(lang: str, audio, sr: int) -> tuple[torch.Tensor, np.ndarray]:
    """Run one encoder forward pass; return (ctc_logits, pooled_embedding)."""
    stats = get_stats()
    info  = MODELS[f"mms-1b-all-{lang}"]
    proc  = info["processor"]
    model = info["instance"]

    inputs = proc(audio, sampling_rate=sr, return_tensors="pt")
    inputs = {k: v.to(get_device()) for k, v in inputs.items()}

    with torch.inference_mode():
        hidden = model.wav2vec2(inputs["input_values"]).last_hidden_state
        logits = model.lm_head(model.dropout(hidden))

    return logits, pool_hidden(hidden, stats)


def _decode(lang: str, logits: torch.Tensor, beam_width: int) -> str:
    """Decode CTC logits to text via KenLM beam search, or argmax as fallback."""
    if decoder_ready(lang):
        beams = beam_decode_top_n(lang, logits, beam_width=beam_width)
        return beams[0].get("text", "") if beams else ""
    proc = MODELS[f"mms-1b-all-{lang}"]["processor"]
    return proc.batch_decode(torch.argmax(logits, dim=-1))[0]


def run_hybrid(
    audio,
    sr:         int  = 16000,
    beam_width: int  = 10,
    language:   str  = "nld+fry",
) -> tuple[str | None, str | None, float | None]:
    """Return (winner_lang, winner_text, fry_prob).

    language:
      "nld+fry" — encode both models, classify, then beam-decode only the winner.
      "fry"     — run only the Frisian model; skip classifier.
      "nld"     — run only the Dutch model; skip classifier.
    """
    if language == "fry":
        logits, _ = _encode("fry", audio, sr)
        return "fry", _decode("fry", logits, beam_width), 1.0

    if language == "nld":
        logits, _ = _encode("nld", audio, sr)
        return "nld", _decode("nld", logits, beam_width), 0.0

    # nld+fry: both encoder passes feed the classifier; decode only the winner.
    logits:     dict[str, torch.Tensor] = {}
    embeddings: dict[str, np.ndarray]   = {}
    for lang in ("fry", "nld"):
        logits[lang], embeddings[lang] = _encode(lang, audio, sr)

    winner_lang, fry_prob = classify_from_embeddings(embeddings["nld"], embeddings["fry"])
    return winner_lang, _decode(winner_lang, logits[winner_lang], beam_width), fry_prob
