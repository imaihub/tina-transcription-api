from functools import lru_cache
from pathlib import Path

import torch

from .config import ADAPTER_DIR, HF_TOKEN, MODEL_CACHE

MODELS: dict = {
    "mms-1b-all-fry": {
        "hf_id":        "facebook/mms-1b-all",
        "adapter_lang": "fry",
        "instance":     None,
        "processor":    None,
        "status":       "not_loaded",
    },
    "mms-1b-all-nld": {
        "hf_id":        "facebook/mms-1b-all",
        "adapter_lang": "nld",
        "instance":     None,
        "processor":    None,
        "status":       "not_loaded",
    },
}


@lru_cache(maxsize=1)
def get_device() -> str:
    """Detect the compute device once; the result is cached for the process."""
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def load_model(model_key: str) -> None:
    info = MODELS[model_key]
    if info["status"] == "loaded":
        return

    info["status"] = "loading"
    device = get_device()

    try:
        from transformers import AutoProcessor, Wav2Vec2ForCTC

        hf_id        = info["hf_id"]
        adapter_lang = info["adapter_lang"]
        kwargs       = dict(token=HF_TOKEN or None, cache_dir=MODEL_CACHE)

        try:
            processor = AutoProcessor.from_pretrained(hf_id, **kwargs, local_files_only=True)
            model     = Wav2Vec2ForCTC.from_pretrained(hf_id, **kwargs, local_files_only=True)
        except EnvironmentError:
            processor = AutoProcessor.from_pretrained(hf_id, **kwargs)
            model     = Wav2Vec2ForCTC.from_pretrained(hf_id, **kwargs)

        processor.tokenizer.set_target_lang(adapter_lang)

        # Point load_adapter at the local directory so it finds
        # adapter.{lang}.safetensors there instead of on the HF hub.
        model.config._name_or_path = str(ADAPTER_DIR)
        model.load_adapter(adapter_lang)

        model = model.to(device)
        model.eval()

        info["instance"]  = model
        info["processor"] = processor
        info["status"]    = "loaded"

    except Exception as e:
        info["status"] = f"error: {e}"
        raise
