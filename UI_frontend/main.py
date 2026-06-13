"""
TINA Transcription — user-facing UI backend.

Serves the static frontend and a small REST API over SQLite. Transcription
itself is delegated to the transcription API (the FastAPI app in /api) via a
server-to-server call, so the transcription API key never reaches the browser.

  Browser ──REST──> this backend ──/v1/audio/transcriptions──> transcription API
                        │
                        └── SQLite (metadata + edited transcript) + disk (audio)
"""

import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db

load_dotenv()

TRANSCRIPTION_API_URL = os.getenv("TRANSCRIPTION_API_URL", "http://localhost:8001").rstrip("/")
TRANSCRIPTION_API_KEY = os.getenv("TRANSCRIPTION_API_KEY", "")

_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="TINA Transcription UI", lifespan=lifespan)


# ── Folders ──────────────────────────────────────────────────────────────────

class FolderCreate(BaseModel):
    name: str


class FolderUpdate(BaseModel):
    name: str | None = None
    settings: dict | None = None


@app.get("/api/folders")
def api_list_folders():
    return db.list_folders()


@app.post("/api/folders")
def api_create_folder(body: FolderCreate):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Folder name is required")
    return db.create_folder(name)


@app.patch("/api/folders/{folder_id}")
def api_update_folder(folder_id: int, body: FolderUpdate):
    if body.name is not None and not body.name.strip():
        raise HTTPException(status_code=400, detail="Folder name cannot be empty")
    folder = db.update_folder(
        folder_id,
        name=body.name.strip() if body.name is not None else None,
        settings=body.settings,
    )
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@app.delete("/api/folders/{folder_id}")
def api_delete_folder(folder_id: int):
    folder = db.get_folder(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    # Remove stored audio for the folder's transcriptions before cascade delete.
    for t in db.list_transcriptions(folder_id=folder_id):
        full = db.get_transcription(t["id"])
        _remove_audio(full)
    db.delete_folder(folder_id)
    return {"ok": True}


# ── Transcriptions ───────────────────────────────────────────────────────────

class TranscriptionUpdate(BaseModel):
    name: str | None = None
    folder_id: int | None = None
    segments: list | None = None


class SegmentRetranscribe(BaseModel):
    language: str


@app.get("/api/transcriptions")
def api_list_transcriptions(folder_id: int | None = None, q: str | None = None, limit: int | None = None):
    return db.list_transcriptions(folder_id=folder_id, q=q, limit=limit)


@app.get("/api/transcriptions/{transcription_id}")
def api_get_transcription(transcription_id: int):
    t = db.get_transcription(transcription_id)
    if not t:
        raise HTTPException(status_code=404, detail="Transcription not found")
    return t


@app.post("/api/transcriptions")
async def api_create_transcription(
    file: UploadFile = File(...),
    folder_id: int = Form(...),
    name: str | None = Form(None),
    language: str = Form("nld+fry"),
):
    if not db.get_folder(folder_id):
        raise HTTPException(status_code=400, detail="Folder not found")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or '(none)'}")

    content = await file.read()
    raw = await _call_transcription_api(content, file.filename or "audio", language)

    segments = _merge_segments(raw)
    audio_filename = f"{uuid.uuid4().hex}{suffix}"
    (db.AUDIO_DIR / audio_filename).write_bytes(content)

    display_name = (name or "").strip() or Path(file.filename or "transcription").stem
    return db.create_transcription(
        folder_id=folder_id,
        name=display_name,
        language=language,
        source_filename=file.filename,
        audio_filename=audio_filename,
        duration_s=raw.get("duration"),
        segments=segments,
        raw_response=raw,
    )


@app.patch("/api/transcriptions/{transcription_id}")
def api_update_transcription(transcription_id: int, body: TranscriptionUpdate):
    if body.folder_id is not None and not db.get_folder(body.folder_id):
        raise HTTPException(status_code=400, detail="Target folder not found")
    t = db.update_transcription(
        transcription_id,
        name=body.name.strip() if body.name is not None else None,
        folder_id=body.folder_id,
        segments=body.segments,
    )
    if not t:
        raise HTTPException(status_code=404, detail="Transcription not found")
    return t


@app.delete("/api/transcriptions/{transcription_id}")
def api_delete_transcription(transcription_id: int):
    t = db.delete_transcription(transcription_id)
    if not t:
        raise HTTPException(status_code=404, detail="Transcription not found")
    _remove_audio(t)
    return {"ok": True}


@app.post("/api/transcriptions/{transcription_id}/segments/{segment_id}/retranscribe")
async def api_retranscribe_segment(transcription_id: int, segment_id: str, body: SegmentRetranscribe):
    if body.language not in ("fry", "nld"):
        raise HTTPException(status_code=400, detail="language must be 'fry' or 'nld'")
    t = db.get_transcription(transcription_id)
    if not t:
        raise HTTPException(status_code=404, detail="Transcription not found")
    if not t.get("audio_filename"):
        raise HTTPException(status_code=400, detail="No stored audio for this transcription")

    segments = t["segments"]
    seg = next((s for s in segments if str(s.get("id")) == str(segment_id)), None)
    if seg is None:
        raise HTTPException(status_code=404, detail="Segment not found")

    audio_path = db.AUDIO_DIR / t["audio_filename"]
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing on disk")

    result = await _call_transcribe_segment(
        audio_path.read_bytes(), t["audio_filename"], seg["start"], seg["end"], body.language,
    )

    seg["text"] = result["text"]
    seg["lang"] = result["lang"]
    seg["note"] = "ok"
    db.update_transcription(transcription_id, segments=segments)
    return seg


@app.get("/api/transcriptions/{transcription_id}/audio")
def api_get_audio(transcription_id: int):
    t = db.get_transcription(transcription_id)
    if not t or not t.get("audio_filename"):
        raise HTTPException(status_code=404, detail="Audio not found")
    path = db.AUDIO_DIR / t["audio_filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing on disk")
    return FileResponse(path)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _call_transcription_api(content: bytes, filename: str, language: str) -> dict:
    """POST the audio to the transcription API and return its diarized_json body."""
    headers = {"X-API-Key": TRANSCRIPTION_API_KEY} if TRANSCRIPTION_API_KEY else {}
    files = {"file": (filename, content)}
    data = {"response_format": "diarized_json", "language": language}
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            resp = await client.post(
                f"{TRANSCRIPTION_API_URL}/v1/audio/transcriptions",
                headers=headers, files=files, data=data,
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach transcription API: {e}")
    if resp.status_code != 200:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=f"Transcription API error: {detail}")
    return resp.json()


async def _call_transcribe_segment(content: bytes, filename: str, start: float, end: float, language: str) -> dict:
    """Forced-language transcription of one time range (no diarization)."""
    headers = {"X-API-Key": TRANSCRIPTION_API_KEY} if TRANSCRIPTION_API_KEY else {}
    files = {"file": (filename, content)}
    data = {"start": str(start), "end": str(end), "language": language}
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            resp = await client.post(
                f"{TRANSCRIPTION_API_URL}/v1/audio/transcribe-segment",
                headers=headers, files=files, data=data,
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach transcription API: {e}")
    if resp.status_code != 200:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=f"Transcription API error: {detail}")
    return resp.json()


def _merge_segments(raw: dict) -> list[dict]:
    """Flatten OpenAI diarized_json + the `tina` meta block into UI segments."""
    meta_by_id = {m["id"]: m for m in raw.get("tina", {}).get("segments_meta", [])}
    segments = []
    for s in raw.get("segments", []):
        m = meta_by_id.get(s["id"], {})
        segments.append({
            "id": s["id"],
            "speaker": s.get("speaker"),
            "start": s.get("start"),
            "end": s.get("end"),
            "text": s.get("text", ""),
            "lang": m.get("lang"),
            "note": m.get("note", "ok"),
        })
    return segments


def _remove_audio(transcription: dict | None) -> None:
    if transcription and transcription.get("audio_filename"):
        (db.AUDIO_DIR / transcription["audio_filename"]).unlink(missing_ok=True)


# Serve the static frontend — mounted last so /api routes are not shadowed.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
