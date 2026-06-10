"""Tests for app/utils.py — load_audio."""

import numpy as np
import pytest
import soundfile as sf

from app.utils import load_audio


def test_load_audio_returns_float32_array(audio_dir):
    path = audio_dir / "sample.wav"
    audio, sr = load_audio(path, target_sr=16_000)
    assert sr == 16_000
    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.ndim == 1


def test_load_audio_resamples(audio_dir):
    """Writing at 8 kHz and loading at 16 kHz should double the sample count."""
    sr_orig = 8_000
    samples = np.zeros(sr_orig, dtype=np.float32)  # 1 second of silence
    path = audio_dir / "8khz.wav"
    sf.write(str(path), samples, sr_orig)

    audio, sr = load_audio(path, target_sr=16_000)
    assert sr == 16_000
    assert len(audio) == pytest.approx(16_000, rel=0.05)


def test_load_audio_file_not_found(tmp_path):
    with pytest.raises(Exception):
        load_audio(tmp_path / "nonexistent.wav")
