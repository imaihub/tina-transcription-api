"""
Shared fixtures.

Heavy model loading (MMS, KenLM, pyannote) is patched to a no-op so tests run
without GPU or downloaded weights.
"""

import numpy as np
import pytest
import soundfile as sf
from unittest.mock import patch, MagicMock


# ── Audio fixture ──────────────────────────────────────────────────────────────

@pytest.fixture()
def audio_dir(tmp_path):
    """Temporary directory with a short synthetic WAV file."""
    sr = 16_000
    duration = 3.0  # seconds
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Two-tone signal — just enough for the pipeline to process
    audio = (0.4 * np.sin(2 * np.pi * 220 * t) +
             0.4 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    wav_path = tmp_path / "sample.wav"
    sf.write(str(wav_path), audio, sr)
    return tmp_path


# ── Model-loading patches ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_model_loading():
    """Prevent any heavy model loading during tests."""
    with (
        patch("app.models.load_model"),
        patch("app.kenlm.rebuild_decoder"),
        patch("app.kenlm.decoder_ready", return_value=True),
        patch("app.lang_id.load_lang_id"),
        patch("app.diarize.load_pipeline"),
    ):
        yield


# ── FastAPI test client ────────────────────────────────────────────────────────

_TEST_API_KEY = "test-key"


@pytest.fixture()
def client(audio_dir, monkeypatch):
    """
    Starlette TestClient with AUDIO_BASE_DIR pointed at the temp audio dir.
    API_KEY is set to a fixed test value.
    diarize() and run_hybrid() are mocked so no actual inference runs.
    """
    import app.config as cfg
    monkeypatch.setattr(cfg, "AUDIO_BASE_DIR", audio_dir)
    monkeypatch.setattr(cfg, "API_KEY", _TEST_API_KEY)

    import app.main as main_module
    monkeypatch.setattr(main_module, "AUDIO_BASE_DIR", audio_dir)
    monkeypatch.setattr(main_module, "API_KEY", _TEST_API_KEY)

    from starlette.testclient import TestClient
    with TestClient(main_module.app) as c:
        yield c
