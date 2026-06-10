"""
KenLM beam-search decoder state and helpers.

Both the fry and nld decoders share a single ARPA model (trained on both
languages). Call rebuild_decoder(lang) after loading the corresponding MMS
model to build the in-memory pyctcdecode decoder.
"""

import math
import re
import unicodedata
from pathlib import Path

from .config import KENLM_MODEL_PATH


# ── Per-language state ─────────────────────────────────────────────────────────

def _empty_state() -> dict:
    return {
        "status":    "not_built",  # not_built | arpa_ready | ready | error
        "arpa_path": None,
        "ngram_order": 4,
        "decoder":   None,
        "decoder_alpha": 0.5,
        "decoder_beta":  1.5,
    }


def _init_state() -> dict[str, dict]:
    """Initialise state using the shared KENLM_MODEL_PATH."""
    state = {"fry": _empty_state(), "nld": _empty_state()}
    arpa_path = KENLM_MODEL_PATH
    if not arpa_path or not arpa_path.exists():
        return state
    m = re.search(r"(\d+)gram", arpa_path.name)
    ngram_order = int(m.group(1)) if m else 4
    for lang in state:
        state[lang]["arpa_path"]   = str(arpa_path)
        state[lang]["ngram_order"] = ngram_order
        state[lang]["status"]      = "arpa_ready"
    return state


_LM_STATE: dict[str, dict] = _init_state()

# Shared state loaded once from the ARPA file, reused by both decoders.
_KENLM_MODEL = None   # kenlm.Model instance
_KENLM_UNIGRAMS = None  # unigram set extracted from the ARPA


def _get_shared_lm():
    """Load the kenlm model and unigrams once, cache for reuse."""
    global _KENLM_MODEL, _KENLM_UNIGRAMS
    if _KENLM_MODEL is None:
        import kenlm
        from pyctcdecode.language_model import load_unigram_set_from_arpa
        arpa_path = _LM_STATE["fry"]["arpa_path"]  # same path for both languages
        _KENLM_MODEL    = kenlm.Model(arpa_path)
        _KENLM_UNIGRAMS = load_unigram_set_from_arpa(arpa_path)
    return _KENLM_MODEL, _KENLM_UNIGRAMS


# ── Vocab helper ───────────────────────────────────────────────────────────────

def _get_vocab_for_lang(lang: str) -> list[str] | None:
    """Return the ordered character vocabulary from the loaded MMS processor."""
    from .models import MODELS
    model_key = f"mms-1b-all-{lang}"
    info = MODELS.get(model_key, {})
    if info.get("status") != "loaded":
        return None
    processor = info.get("processor")
    if processor is None:
        return None

    vocab_dict = processor.tokenizer.get_vocab()
    id_to_tok  = {v: k for k, v in vocab_dict.items()}
    n          = max(id_to_tok.keys()) + 1
    blank_id   = processor.tokenizer.pad_token_id or 0

    labels  = []
    pua_idx = 0
    for i in range(n):
        tok = id_to_tok.get(i, "<unk>")
        if i == blank_id:
            tok = ""
        elif tok == "|":
            tok = " "
        elif len(tok) > 1:
            tok = chr(0xE000 + pua_idx)
            pua_idx += 1
        labels.append(tok)
    return labels


# ── Decoder build / query ──────────────────────────────────────────────────────

def _build_decoder(lang: str, alpha: float, beta: float):
    from pyctcdecode.alphabet import Alphabet
    from pyctcdecode.decoder import BeamSearchDecoderCTC
    from pyctcdecode.language_model import LanguageModel

    state = _LM_STATE[lang]
    if not state["arpa_path"] or not Path(state["arpa_path"]).exists():
        raise FileNotFoundError(f"ARPA file not found for '{lang}': {state['arpa_path']}")

    labels = _get_vocab_for_lang(lang)
    if labels is None:
        raise RuntimeError(f"mms-1b-all-{lang} must be loaded before building the decoder")

    kenlm_model, unigrams = _get_shared_lm()
    alphabet = Alphabet.build_alphabet(labels)
    lm       = LanguageModel(kenlm_model, unigrams, alpha=alpha, beta=beta)
    return BeamSearchDecoderCTC(alphabet, lm)


def rebuild_decoder(lang: str) -> None:
    """Build (or rebuild) the in-memory decoder from the on-disk ARPA file."""
    state = _LM_STATE[lang]
    if state["status"] not in ("arpa_ready", "ready"):
        return  # no ARPA on disk — nothing to do
    decoder = _build_decoder(lang, state["decoder_alpha"], state["decoder_beta"])
    state["decoder"] = decoder
    state["status"]  = "ready"


def decoder_ready(lang: str) -> bool:
    return _LM_STATE[lang]["decoder"] is not None


# ── Beam decode ────────────────────────────────────────────────────────────────

def beam_decode_top_n(lang: str, logits: "torch.Tensor", beam_width: int = 100, n: int = 5) -> list[dict]:
    """Return top-n beams. beam_width controls the pyctcdecode search width directly."""

    def _safe(v):
        try:
            f = float(v)
            return round(f, 3) if math.isfinite(f) else None
        except (TypeError, ValueError):
            return None

    decoder   = _LM_STATE[lang]["decoder"]
    if decoder is None:
        raise RuntimeError(f"Decoder for '{lang}' not built")
    logits_np = logits[0].cpu().numpy()
    beams     = decoder.decode_beams(logits_np, beam_width=beam_width)
    result    = []
    for i, b in enumerate(beams[:n]):
        text        = b.text        if hasattr(b, "text")        else b[0]
        logit_score = b.logit_score if hasattr(b, "logit_score") else b[3]
        lm_score    = b.lm_score    if hasattr(b, "lm_score")    else b[4]
        ls  = _safe(logit_score)
        lms = _safe(lm_score)
        result.append({
            "rank":        i + 1,
            "text":        text,
            "logit_score": ls,
            "lm_score":    lms,
            "lm_delta":    _safe(lm_score - logit_score)
                           if (ls is not None and lms is not None) else None,
        })
    return result
