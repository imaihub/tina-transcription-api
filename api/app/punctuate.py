"""Punctuation restoration + derived capitalization for transcribed text.

The MMS+KenLM transcriber emits lowercased text with no punctuation. This module
runs a fine-tuned token-classification model (the multilingual fullstop model,
fine-tuned on Frisian + Dutch) that predicts the punctuation following each word
(labels: 0 . , ? - :). Capitalization is *not* predicted — it is derived
deterministically from the predicted sentence boundaries (capitalize the first
letter of the text and the first letter after each . ? !).

Optional: if PUNCT_MODEL_DIR is not set (or fails to load) the API still works —
`restore()` becomes a no-op and transcripts stay lowercase/unpunctuated.
"""
import sys

from .config import MODEL_CACHE, PUNCT_MODEL_DIR
from .models import get_device

# Marks the model predicts that attach to the preceding word.
MARKS = (".", ",", "?", "-", ":")
# Marks that end a sentence (→ capitalize the next word).
_SENT_END = ".?!"

CHUNK_SIZE = 230
OVERLAP = 5

_model: "_PunctModel | None" = None


def punct_available() -> bool:
    return _model is not None


def load_punctuation() -> None:
    """Load the punctuation model at startup. No-op (with a warning) if PUNCT_MODEL_DIR
    is unset or the model can't be loaded — punctuation is an optional enhancement."""
    global _model
    if not PUNCT_MODEL_DIR:
        print("Punctuation disabled (PUNCT_MODEL_DIR not set); transcripts stay lowercase.")
        return
    try:
        import torch
        from transformers import pipeline

        pipe = pipeline(
            "ner", model=PUNCT_MODEL_DIR, aggregation_strategy="none",
            device=torch.device(get_device()),
            model_kwargs={"cache_dir": MODEL_CACHE} if MODEL_CACHE else None,
        )
        _model = _PunctModel(pipe)
        print(f"Punctuation model loaded from {PUNCT_MODEL_DIR} on {get_device()}")
    except Exception as e:
        print(
            f"\nWARNING: could not load punctuation model from PUNCT_MODEL_DIR={PUNCT_MODEL_DIR}: {e}\n"
            f"         Continuing without punctuation (transcripts stay lowercase).\n",
            file=sys.stderr,
        )
        _model = None


def restore(text: str) -> str:
    """Restore punctuation + sentence-start capitalization for one text."""
    if _model is None or not text or not text.strip():
        return text
    words = text.split()
    labels = [t[1] for t in _model.predict(words)]
    rebuilt = " ".join(w + (lbl if lbl in MARKS else "") for w, lbl in zip(words, labels))
    return _capitalize(rebuilt)


def restore_batch(texts: list[str]) -> list[str]:
    return [restore(t) for t in texts]


def _capitalize(text: str) -> str:
    """Capitalize the first letter and the first letter after each sentence end."""
    out = []
    cap = True
    for ch in text:
        if cap and ch.isalpha():
            out.append(ch.upper())
            cap = False
        else:
            out.append(ch)
        if ch in _SENT_END:
            cap = True
    return "".join(out)


def _overlap_chunks(lst, n, stride):
    for i in range(0, len(lst), n - stride):
        yield lst[i:i + n]


class _PunctModel:
    """Word-level wrapper over a token-classification pipeline. Returns
    [word, label, score] per input word (label "0" or one of . , ? - :)."""

    def __init__(self, pipe):
        self.pipe = pipe

    def predict(self, words: list[str]) -> list[list]:
        overlap = OVERLAP if len(words) > CHUNK_SIZE else 0
        batches = list(_overlap_chunks(words, CHUNK_SIZE, overlap))
        if len(batches) > 1 and len(batches[-1]) <= overlap:
            batches.pop()

        tagged: list[list] = []
        for bi, batch in enumerate(batches):
            cur_overlap = 0 if bi == len(batches) - 1 else overlap
            result = self.pipe(" ".join(batch))
            char_index = 0
            ri = 0
            for word in batch[:len(batch) - cur_overlap]:
                char_index += len(word) + 1
                label, score = "0", 1.0
                while ri < len(result) and char_index > result[ri]["end"]:
                    label = result[ri]["entity"]
                    score = float(result[ri]["score"])
                    ri += 1
                tagged.append([word, label, score])
        return tagged
