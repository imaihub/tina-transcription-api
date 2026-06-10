"""
Transcription API

POST /transcribe
  Input:  JSON with a filename (relative to AUDIO_BASE_DIR) and optional settings
  Output: JSON with per-segment transcriptions and speaker summary

POST /upload-transcribe
  Input:  multipart/form-data with an audio file upload and optional settings
  Output: JSON with per-segment transcriptions and speaker summary
          (uploaded file is deleted from the tmp folder after transcription)

All models are loaded at startup; requests are handled synchronously.
"""

import asyncio
import os
import sys
import tempfile
import warnings
from contextlib import asynccontextmanager

# Warnings from pyannote/speechbrain internals — not actionable
warnings.filterwarnings("ignore", message="torchaudio._backend.list_audio_backends has been deprecated")
warnings.filterwarnings("ignore", category=SyntaxWarning, module="pyannote")
from pathlib import Path

import mimetypes

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Security, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

from .config import API_KEY, AUDIO_BASE_DIR, BEAM_WIDTH, KENLM_MODEL_PATH, LANG_ID_MODEL_PATH, MIN_SEGMENT_DUR, PAD_S
from .diarize import diarize, load_pipeline
from .hybrid import run_hybrid
from .kenlm import decoder_ready, rebuild_decoder
from .lang_id import load_lang_id
from .models import load_model

_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(key: str | None = Security(_api_key_header)):
    if API_KEY and key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── Startup ────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load MMS models
    for lang in ("fry", "nld"):
        load_model(f"mms-1b-all-{lang}")

    # Build KenLM decoders using the shared ARPA model
    for lang in ("fry", "nld"):
        try:
            rebuild_decoder(lang)
        except Exception as e:
            print(
                f"\nERROR: Failed to build KenLM decoder for '{lang}': {e}\n"
                f"       Ensure KENLM_MODEL_PATH ({KENLM_MODEL_PATH}) points to a valid ARPA file.\n",
                file=sys.stderr,
            )
            os._exit(1)
        if not decoder_ready(lang):
            print(
                f"\nERROR: KenLM ARPA file not found: {KENLM_MODEL_PATH}\n"
                f"       Set KENLM_MODEL_PATH in .env to the shared ARPA file.\n",
                file=sys.stderr,
            )
            os._exit(1)

    # Load the language-ID classifier
    try:
        load_lang_id()
    except Exception as e:
        print(
            f"\nERROR: Failed to load language-ID classifier: {e}\n"
            f"       Set LANG_ID_MODEL_PATH ({LANG_ID_MODEL_PATH}) to the .pkl file produced by LANG_ID_VM.\n",
            file=sys.stderr,
        )
        os._exit(1)

    # Load pyannote diarization pipeline
    load_pipeline()

    yield


app = FastAPI(title="Transcription API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Files endpoint ─────────────────────────────────────────────────────────────

@app.get("/files", dependencies=[Depends(require_api_key)])
def list_files(limit: int | None = None):
    """Return audio filenames available in AUDIO_BASE_DIR, relative to that dir.

    All audio files are returned by default; pass ?limit=N to cap the count.
    """
    if not AUDIO_BASE_DIR or not AUDIO_BASE_DIR.is_dir():
        raise HTTPException(status_code=500, detail="AUDIO_BASE_DIR is not configured or does not exist")
    base = AUDIO_BASE_DIR.resolve()
    files = [
        str(p.relative_to(base))
        for p in base.rglob("*")
        if p.is_file() and p.suffix.lower() in _AUDIO_EXTENSIONS
    ]
    files.sort()
    if limit is not None and limit > 0:
        files = files[:limit]
    return {"files": files}


# ── Audio endpoint ─────────────────────────────────────────────────────────────

@app.get("/audio/{filename:path}", dependencies=[Depends(require_api_key)])
def serve_audio(filename: str):
    """Stream an audio file from AUDIO_BASE_DIR."""
    if not AUDIO_BASE_DIR or not AUDIO_BASE_DIR.is_dir():
        raise HTTPException(status_code=500, detail="AUDIO_BASE_DIR is not configured or does not exist")
    audio_path = (AUDIO_BASE_DIR / filename).resolve()
    if not str(audio_path).startswith(str(AUDIO_BASE_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Filename must not escape AUDIO_BASE_DIR")
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"Audio file not found: {filename}")
    media_type, _ = mimetypes.guess_type(str(audio_path))
    return FileResponse(audio_path, media_type=media_type or "application/octet-stream")


# ── Request / response schemas ─────────────────────────────────────────────────

class TranscribeRequest(BaseModel):
    filename:          str
    recording_context: str = "GENERAL"
    language:          str = "nld+fry"


class SegmentResult(BaseModel):
    speaker: str
    start:   float
    end:     float
    text:    str | None
    lang:    str | None
    note:    str


class SpeakerSummary(BaseModel):
    n_segments:    int
    total_dur_s:   float
    dominant_lang: str | None
    fry_pct:       float | None


class TranscribeResponse(BaseModel):
    segments:         list[SegmentResult]
    speakers:         dict[str, SpeakerSummary]
    total_duration_s: float
    n_speakers:       int


# ── Endpoint ───────────────────────────────────────────────────────────────────

@app.post("/transcribe", response_model=TranscribeResponse, dependencies=[Depends(require_api_key)])
async def transcribe(req: TranscribeRequest):
    if not AUDIO_BASE_DIR or not AUDIO_BASE_DIR.is_dir():
        raise HTTPException(status_code=500, detail="AUDIO_BASE_DIR is not configured or does not exist")

    audio_path = (AUDIO_BASE_DIR / req.filename).resolve()
    if not str(audio_path).startswith(str(AUDIO_BASE_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Filename must not escape AUDIO_BASE_DIR")
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"Audio file not found: {req.filename}")

    return await _transcribe_path(audio_path, req.language)


@app.post("/upload-transcribe", response_model=TranscribeResponse, dependencies=[Depends(require_api_key)])
async def upload_transcribe(
    file: UploadFile = File(...),
    recording_context: str = Form("GENERAL"),
    language: str = Form("nld+fry"),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or '(none)'}")

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        return await _transcribe_path(tmp_path, language)
    finally:
        tmp_path.unlink(missing_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _transcribe_path(audio_path: Path, language: str) -> TranscribeResponse:
    """Run diarization + per-segment transcription on a resolved audio file path."""
    try:
        turns, audio = await _run_in_thread(diarize, audio_path, MIN_SEGMENT_DUR)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diarization failed: {e}")

    SR        = 16_000
    n_samples = len(audio)
    segments: list[SegmentResult] = []

    for seg in turns:
        if seg["note"] == "overlapping_speech":
            segments.append(SegmentResult(
                speaker=seg["speaker"],
                start=seg["start"],
                end=seg["end"],
                text="inaudible",
                lang=None,
                note="overlapping_speech",
            ))
            continue

        s = max(0,         int((seg["start"] - PAD_S) * SR))
        e = min(n_samples, int((seg["end"]   + PAD_S) * SR))
        audio_slice = audio[s:e]

        try:
            lang, text, _ = await _run_in_thread(
                run_hybrid, audio_slice, SR, BEAM_WIDTH, language,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Transcription failed for segment {seg['start']:.2f}–{seg['end']:.2f}s: {exc}",
            )

        segments.append(SegmentResult(
            speaker=seg["speaker"],
            start=seg["start"],
            end=seg["end"],
            text=text,
            lang=lang,
            note="ok",
        ))

    speakers: dict[str, dict] = {}
    for seg in segments:
        spk = seg.speaker
        if spk not in speakers:
            speakers[spk] = {"n_segments": 0, "fry_count": 0, "nld_count": 0, "total_dur_s": 0.0}
        speakers[spk]["n_segments"]  += 1
        speakers[spk]["total_dur_s"] += seg.end - seg.start
        if seg.lang == "fry":
            speakers[spk]["fry_count"] += 1
        elif seg.lang == "nld":
            speakers[spk]["nld_count"] += 1

    speaker_summary: dict[str, SpeakerSummary] = {}
    for spk, stats in speakers.items():
        lang_total = stats["fry_count"] + stats["nld_count"]
        fry_pct    = stats["fry_count"] / lang_total if lang_total > 0 else None
        dominant   = ("fry" if (fry_pct or 0) >= 0.5 else "nld") if lang_total else None
        speaker_summary[spk] = SpeakerSummary(
            n_segments=stats["n_segments"],
            total_dur_s=round(stats["total_dur_s"], 2),
            dominant_lang=dominant,
            fry_pct=round(fry_pct, 3) if fry_pct is not None else None,
        )

    total_duration = max((seg.end for seg in segments), default=0.0)

    return TranscribeResponse(
        segments=segments,
        speakers=speaker_summary,
        total_duration_s=round(total_duration, 2),
        n_speakers=len(speaker_summary),
    )


async def _run_in_thread(fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, *args)
