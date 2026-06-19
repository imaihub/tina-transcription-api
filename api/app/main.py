"""
Transcription API

POST /v1/audio/transcriptions
  OpenAI-compatible transcription endpoint (response_format=diarized_json).
  Input:  multipart/form-data with an audio file upload and optional settings
  Output: OpenAI diarized_json; TINA-specific per-segment language/note and the
          speaker summary are returned in a separate top-level `tina` block.
          (uploaded file is deleted from the tmp folder after transcription)

POST /transcribe
  Input:  JSON with a filename (relative to AUDIO_BASE_DIR) and optional settings
  Output: JSON with per-segment transcriptions and speaker summary

POST /upload-transcribe
  Input:  multipart/form-data with an audio file upload and optional settings
  Output: JSON with per-segment transcriptions and speaker summary
          (uploaded file is deleted from the tmp folder after transcription)

POST /v1/audio/transcribe-segment
  Re-transcribe a single time range in a forced language (no diarization).
  Input:  multipart/form-data with an audio file, start, end, and language (fry|nld)
  Output: JSON with the segment's text and language

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
from .punctuate import load_punctuation, punct_available, restore, restore_batch
from .utils import load_audio

_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
# OpenAI SDK clients authenticate with `Authorization: Bearer <key>`; accept that too.
_bearer_header = APIKeyHeader(name="Authorization", auto_error=False)


async def require_api_key(
    key: str | None = Security(_api_key_header),
    authorization: str | None = Security(_bearer_header),
):
    if not API_KEY:
        return
    provided = key
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if provided != API_KEY:
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

    # Load the punctuation/capitalization model (optional — no-op if PUNCT_MODEL_DIR unset)
    load_punctuation()

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
    punctuate:         bool = True


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


# ── OpenAI-compatible schemas (POST /v1/audio/transcriptions) ────────────────────
# Mirrors OpenAI's `diarized_json` response. The standard segment objects are kept
# pure; TINA-specific data (per-segment language/note + speaker summary) lives in a
# separate top-level `tina` block, which spec-compliant OpenAI clients ignore.

class OpenAISegment(BaseModel):
    id:      str
    start:   float
    end:     float
    text:    str
    speaker: str
    type:    str = "transcript.text.segment"


class OpenAIUsage(BaseModel):
    type:    str = "duration"
    seconds: float


class TinaSegmentMeta(BaseModel):
    id:   str           # matches OpenAISegment.id
    lang: str | None
    note: str


class TinaBlock(BaseModel):
    segments_meta: list[TinaSegmentMeta]
    speakers:      dict[str, SpeakerSummary]


class TranscriptionDiarized(BaseModel):
    task:     str = "transcribe"
    duration: float
    text:     str
    segments: list[OpenAISegment]
    usage:    OpenAIUsage
    tina:     TinaBlock


_RESPONSE_FORMATS = {"diarized_json"}

# Map OpenAI/ISO language hints to this service's internal language modes.
_LANGUAGE_MAP = {
    "":            "nld+fry",
    "nl":          "nld",
    "nld":         "nld",
    "dutch":       "nld",
    "nederlands":  "nld",
    "fy":          "fry",
    "fry":         "fry",
    "frisian":     "fry",
    "frysk":       "fry",
    "nld+fry":     "nld+fry",
    "fy+nl":       "nld+fry",
    "nl+fy":       "nld+fry",
}


def _map_language(language: str | None) -> str:
    """Translate an OpenAI/ISO `language` hint to a `nld`/`fry`/`nld+fry` mode.

    Unknown or absent values fall back to dual-language mode.
    """
    return _LANGUAGE_MAP.get((language or "").strip().lower(), "nld+fry")


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

    return await _transcribe_path(audio_path, req.language, req.punctuate)


@app.post("/upload-transcribe", response_model=TranscribeResponse, dependencies=[Depends(require_api_key)])
async def upload_transcribe(
    file: UploadFile = File(...),
    recording_context: str = Form("GENERAL"),
    language: str = Form("nld+fry"),
    punctuate: bool = Form(True),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or '(none)'}")

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        return await _transcribe_path(tmp_path, language, punctuate)
    finally:
        tmp_path.unlink(missing_ok=True)


# ── OpenAI-compatible endpoint ───────────────────────────────────────────────────

@app.post(
    "/v1/audio/transcriptions",
    response_model=TranscriptionDiarized,
    dependencies=[Depends(require_api_key)],
)
async def openai_transcriptions(
    file: UploadFile = File(...),
    model: str = Form("tina-mms"),                 # accepted for compatibility; ignored
    language: str | None = Form(None),             # ISO hint, mapped to nld/fry/nld+fry
    response_format: str = Form("diarized_json"),
    prompt: str | None = Form(None),               # accepted for compatibility; ignored
    temperature: float | None = Form(None),        # accepted for compatibility; ignored
    punctuate: bool = Form(True),                  # restore punctuation + capitalization
):
    """OpenAI-compatible transcription endpoint.

    Mirrors `POST /v1/audio/transcriptions` with `response_format=diarized_json`.
    TINA-specific data (per-segment language/note, speaker summary) is returned in
    a separate top-level `tina` block.
    """
    if response_format not in _RESPONSE_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported response_format: {response_format!r}. Supported: diarized_json",
        )

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or '(none)'}")

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        segments, speakers, total_duration = await _process(tmp_path, _map_language(language), punctuate)
    finally:
        tmp_path.unlink(missing_ok=True)

    return _to_diarized(segments, speakers, total_duration)


# ── Single-segment re-transcription (no diarization) ─────────────────────────────

class SegmentTranscription(BaseModel):
    text:  str
    lang:  str
    start: float
    end:   float


@app.post("/v1/audio/transcribe-segment", response_model=SegmentTranscription, dependencies=[Depends(require_api_key)])
async def transcribe_segment(
    file: UploadFile = File(...),
    start: float = Form(...),
    end: float = Form(...),
    language: str = Form(...),
    punctuate: bool = Form(True),
):
    """Transcribe a single time range of an audio file in a forced language.

    Unlike the full endpoints, this runs no diarization — it slices [start, end]
    (with the usual padding) and forces `language`, so a single mis-classified
    segment can be re-transcribed cheaply without re-segmenting the audio.
    """
    if language not in ("fry", "nld"):
        raise HTTPException(status_code=400, detail="language must be 'fry' or 'nld'")
    if end <= start:
        raise HTTPException(status_code=400, detail="end must be greater than start")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or '(none)'}")

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        audio = await _run_in_thread(_load_audio_only, tmp_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read audio: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    SR = 16_000
    s = max(0,          int((start - PAD_S) * SR))
    e = min(len(audio), int((end   + PAD_S) * SR))
    if e <= s:
        raise HTTPException(status_code=400, detail="Segment range is outside the audio")

    try:
        lang, text, _ = await _run_in_thread(run_hybrid, audio[s:e], SR, BEAM_WIDTH, language)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")

    if text and punctuate and punct_available():
        text = await _run_in_thread(restore, text)

    return SegmentTranscription(text=text or "", lang=lang or language, start=start, end=end)


def _load_audio_only(path: Path):
    audio, _ = load_audio(path, target_sr=16_000)
    return audio


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _process(
    audio_path: Path, language: str, punctuate: bool = True,
) -> tuple[list[SegmentResult], dict[str, SpeakerSummary], float]:
    """Run diarization + per-segment transcription on a resolved audio file path.

    Returns the per-segment results, the per-speaker summary, and the total
    duration — the common core shared by every response shape.
    """
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

    # Restore punctuation + capitalization on the transcribed segments
    # (skipped when the caller sets punctuate=false or no model is configured).
    if punctuate and punct_available():
        idx = [i for i, s in enumerate(segments) if s.note == "ok" and s.text]
        if idx:
            restored = await _run_in_thread(restore_batch, [segments[i].text for i in idx])
            for i, text in zip(idx, restored):
                segments[i].text = text

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

    total_duration = round(max((seg.end for seg in segments), default=0.0), 2)

    return segments, speaker_summary, total_duration


async def _transcribe_path(audio_path: Path, language: str, punctuate: bool = True) -> TranscribeResponse:
    """Run the pipeline and return the native TINA response shape."""
    segments, speaker_summary, total_duration = await _process(audio_path, language, punctuate)
    return TranscribeResponse(
        segments=segments,
        speakers=speaker_summary,
        total_duration_s=total_duration,
        n_speakers=len(speaker_summary),
    )


def _to_diarized(
    segments: list[SegmentResult],
    speakers: dict[str, SpeakerSummary],
    total_duration: float,
) -> TranscriptionDiarized:
    """Build an OpenAI `diarized_json` response, with TINA extras in `tina`."""
    oai_segments: list[OpenAISegment] = []
    metas:        list[TinaSegmentMeta] = []
    texts:        list[str] = []

    for i, seg in enumerate(segments):
        sid = str(i)
        text = seg.text or ""
        oai_segments.append(OpenAISegment(
            id=sid, start=seg.start, end=seg.end, text=text, speaker=seg.speaker,
        ))
        metas.append(TinaSegmentMeta(id=sid, lang=seg.lang, note=seg.note))
        if text:
            texts.append(text)

    return TranscriptionDiarized(
        duration=total_duration,
        text=" ".join(texts),
        segments=oai_segments,
        usage=OpenAIUsage(seconds=total_duration),
        tina=TinaBlock(segments_meta=metas, speakers=speakers),
    )


async def _run_in_thread(fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, *args)
