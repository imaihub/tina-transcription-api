"""
Speaker diarization via pyannote.audio.

The pipeline is loaded once and cached in _pipeline. Call load_pipeline() during
startup to avoid the cold-start delay on the first request.
"""

from pathlib import Path

import numpy as np
import torch

from .config import HF_TOKEN
from .models import get_device
from .utils import load_audio

_pipeline = None


def load_pipeline() -> None:
    """Load (or no-op if already loaded) the pyannote diarization pipeline."""
    global _pipeline
    if _pipeline is not None:
        return
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        raise RuntimeError("pyannote.audio is not installed")

    # PyTorch 2.6+ defaults weights_only=True, but pyannote checkpoints contain
    # custom classes not in the safe-globals allowlist. Patch torch.load to use
    # weights_only=False for this trusted HuggingFace checkpoint load only.
    _orig_torch_load = torch.load

    def _patched_torch_load(f, map_location=None, weights_only=None, **kwargs):
        return _orig_torch_load(f, map_location=map_location, weights_only=False, **kwargs)

    torch.load = _patched_torch_load
    try:
        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=HF_TOKEN or None,
        )
    finally:
        torch.load = _orig_torch_load
    device = get_device()
    if device != "cpu":
        _pipeline.to(torch.device(device))


def _is_overlapping(seg: dict, all_segs: list[dict]) -> bool:
    for other in all_segs:
        if other is seg:
            continue
        if seg["start"] < other["end"] and seg["end"] > other["start"]:
            return True
    return False


def diarize(audio_path: Path, min_segment_dur: float = 0.3) -> tuple[list[dict], np.ndarray]:
    """Run pyannote diarization and return annotated speaker turns.

    Each turn dict has: speaker, start, end, note
      note = "ok" | "overlapping_speech"
    Too-short segments (< min_segment_dur) are omitted entirely.
    """
    if _pipeline is None:
        raise RuntimeError("Diarization pipeline is not loaded — call load_pipeline() at startup")

    SR = 16_000
    audio, _ = load_audio(audio_path, target_sr=SR)
    waveform  = torch.from_numpy(audio).unsqueeze(0)
    result    = _pipeline({"waveform": waveform, "sample_rate": SR})
    annotation = result.speaker_diarization if hasattr(result, "speaker_diarization") else result

    raw_turns: list[dict] = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        raw_turns.append({
            "speaker": speaker,
            "start":   round(turn.start, 3),
            "end":     round(turn.end,   3),
        })
    raw_turns.sort(key=lambda s: s["start"])

    kept = [s for s in raw_turns if s["end"] - s["start"] >= min_segment_dur]
    for seg in kept:
        seg["note"] = "overlapping_speech" if _is_overlapping(seg, kept) else "ok"
    turns = kept

    return turns, audio
