"""Integration tests for POST /transcribe."""

import numpy as np
import pytest
from unittest.mock import patch

from tests.conftest import _TEST_API_KEY

AUTH = {"X-API-Key": _TEST_API_KEY}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fake_diarize(audio_path, min_segment_dur=0.3):
    """Return two speaker turns and a dummy waveform."""
    audio = np.zeros(16_000 * 3, dtype=np.float32)
    turns = [
        {"speaker": "SPEAKER_00", "start": 0.0,  "end": 1.5,  "note": "ok"},
        {"speaker": "SPEAKER_01", "start": 2.0,  "end": 3.0,  "note": "ok"},
    ]
    return turns, audio


def _fake_diarize_with_overlap(audio_path, min_segment_dur=0.3):
    audio = np.zeros(16_000 * 4, dtype=np.float32)
    turns = [
        {"speaker": "SPEAKER_00", "start": 0.0, "end": 2.0, "note": "ok"},
        {"speaker": "SPEAKER_01", "start": 1.5, "end": 3.5, "note": "overlapping_speech"},
    ]
    return turns, audio


def _fake_hybrid(audio, sr=16000, beam_width=10, language="nld+fry"):
    return "fry", "goeie moarn", 0.85


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestAuth:

    def test_missing_key_returns_401(self, client):
        resp = client.post("/transcribe", json={"filename": "sample.wav"})
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, client):
        resp = client.post("/transcribe", json={"filename": "sample.wav"},
                           headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_correct_key_is_accepted(self, client, audio_dir):
        with (
            patch("app.main.diarize", side_effect=_fake_diarize),
            patch("app.main.run_hybrid", side_effect=_fake_hybrid),
        ):
            resp = client.post("/transcribe", json={"filename": "sample.wav"},
                               headers=AUTH)
        assert resp.status_code == 200

    def test_files_endpoint_requires_key(self, client):
        resp = client.get("/files")
        assert resp.status_code == 401


class TestTranscribeEndpoint:

    def test_missing_file_returns_404(self, client):
        with (
            patch("app.main.diarize", side_effect=_fake_diarize),
            patch("app.main.run_hybrid", side_effect=_fake_hybrid),
        ):
            resp = client.post("/transcribe", json={"filename": "nonexistent.wav"},
                               headers=AUTH)
        assert resp.status_code == 404

    def test_path_traversal_returns_400(self, client):
        resp = client.post("/transcribe", json={"filename": "../../etc/passwd"},
                           headers=AUTH)
        assert resp.status_code == 400

    def test_successful_transcription(self, client, audio_dir):
        with (
            patch("app.main.diarize", side_effect=_fake_diarize),
            patch("app.main.run_hybrid", side_effect=_fake_hybrid),
        ):
            resp = client.post("/transcribe", json={"filename": "sample.wav"},
                               headers=AUTH)

        assert resp.status_code == 200
        data = resp.json()
        assert data["n_speakers"] == 2
        assert len(data["segments"]) == 2
        assert data["segments"][0]["speaker"] == "SPEAKER_00"
        assert data["segments"][0]["lang"] == "fry"
        assert data["segments"][0]["text"] == "goeie moarn"
        assert data["segments"][0]["note"] == "ok"
        assert data["total_duration_s"] > 0

    def test_overlapping_segment_returns_inaudible(self, client, audio_dir):
        with (
            patch("app.main.diarize", side_effect=_fake_diarize_with_overlap),
            patch("app.main.run_hybrid", side_effect=_fake_hybrid),
        ):
            resp = client.post("/transcribe", json={"filename": "sample.wav"},
                               headers=AUTH)

        assert resp.status_code == 200
        segs = resp.json()["segments"]
        overlap = next(s for s in segs if s["note"] == "overlapping_speech")
        assert overlap["text"] == "inaudible"
        assert overlap["lang"] is None

    def test_speaker_summary_is_correct(self, client, audio_dir):
        with (
            patch("app.main.diarize", side_effect=_fake_diarize),
            patch("app.main.run_hybrid", side_effect=_fake_hybrid),
        ):
            resp = client.post("/transcribe", json={"filename": "sample.wav"},
                               headers=AUTH)

        speakers = resp.json()["speakers"]
        assert "SPEAKER_00" in speakers
        assert speakers["SPEAKER_00"]["dominant_lang"] == "fry"
        assert speakers["SPEAKER_00"]["n_segments"] == 1

    def test_recording_context_is_accepted(self, client, audio_dir):
        with (
            patch("app.main.diarize", side_effect=_fake_diarize),
            patch("app.main.run_hybrid", side_effect=_fake_hybrid),
        ):
            resp = client.post("/transcribe", json={
                "filename":          "sample.wav",
                "recording_context": "INTERVIEW",
            }, headers=AUTH)
        assert resp.status_code == 200

    def test_single_language_mode_accepted(self, client, audio_dir):
        for lang in ("fry", "nld", "nld+fry"):
            with (
                patch("app.main.diarize", side_effect=_fake_diarize),
                patch("app.main.run_hybrid", side_effect=_fake_hybrid),
            ):
                resp = client.post("/transcribe", json={
                    "filename": "sample.wav",
                    "language": lang,
                }, headers=AUTH)
            assert resp.status_code == 200, f"language={lang!r} returned {resp.status_code}"

    def test_diarization_error_returns_500(self, client, audio_dir):
        with patch("app.main.diarize", side_effect=RuntimeError("pipeline not loaded")):
            resp = client.post("/transcribe", json={"filename": "sample.wav"},
                               headers=AUTH)
        assert resp.status_code == 500
        assert "Diarization failed" in resp.json()["detail"]

    def test_transcription_error_returns_500(self, client, audio_dir):
        def _bad_hybrid(*args, **kwargs):
            raise RuntimeError("model crashed")

        with (
            patch("app.main.diarize", side_effect=_fake_diarize),
            patch("app.main.run_hybrid", side_effect=_bad_hybrid),
        ):
            resp = client.post("/transcribe", json={"filename": "sample.wav"},
                               headers=AUTH)
        assert resp.status_code == 500
        assert "Transcription failed" in resp.json()["detail"]
