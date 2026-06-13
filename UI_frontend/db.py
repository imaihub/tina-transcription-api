"""
SQLite persistence for the UI frontend.

Two tables: `folders` (named containers with settings) and `transcriptions`
(belong to a folder; hold the edited transcript plus the original API response).
A default folder, "My transcriptions", is seeded on first init so the New
Transcript flow always has somewhere to save to.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR") or (Path(__file__).parent / "data"))
DB_PATH = DATA_DIR / "app.db"
AUDIO_DIR = DATA_DIR / "audio"

DEFAULT_FOLDER_NAME = "My transcriptions"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create the data dirs and tables, and seed the default folder."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS folders (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL,
                created_at    TEXT    NOT NULL,
                settings_json TEXT    NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS transcriptions (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id          INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
                name               TEXT    NOT NULL,
                created_at         TEXT    NOT NULL,
                language           TEXT,
                status             TEXT    NOT NULL DEFAULT 'done',
                source_filename    TEXT,
                audio_filename     TEXT,
                duration_s         REAL,
                segments_json      TEXT    NOT NULL DEFAULT '[]',
                raw_response_json  TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_transcriptions_folder
                ON transcriptions(folder_id);
            """
        )
        row = conn.execute("SELECT COUNT(*) AS n FROM folders").fetchone()
        if row["n"] == 0:
            conn.execute(
                "INSERT INTO folders (name, created_at, settings_json) VALUES (?, ?, '{}')",
                (DEFAULT_FOLDER_NAME, _now()),
            )


# ── Folders ──────────────────────────────────────────────────────────────────

def list_folders() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT f.id, f.name, f.created_at, f.settings_json,
                   COUNT(t.id) AS count
            FROM folders f
            LEFT JOIN transcriptions t ON t.folder_id = f.id
            GROUP BY f.id
            ORDER BY f.created_at ASC, f.id ASC
            """
        ).fetchall()
    return [_folder_row(r) for r in rows]


def create_folder(name: str) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO folders (name, created_at, settings_json) VALUES (?, ?, '{}')",
            (name, _now()),
        )
        fid = cur.lastrowid
    return get_folder(fid)


def get_folder(folder_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT f.id, f.name, f.created_at, f.settings_json,
                   (SELECT COUNT(*) FROM transcriptions t WHERE t.folder_id = f.id) AS count
            FROM folders f WHERE f.id = ?
            """,
            (folder_id,),
        ).fetchone()
    return _folder_row(row) if row else None


def update_folder(folder_id: int, *, name: str | None = None, settings: dict | None = None) -> dict | None:
    sets, params = [], []
    if name is not None:
        sets.append("name = ?")
        params.append(name)
    if settings is not None:
        sets.append("settings_json = ?")
        params.append(json.dumps(settings))
    if sets:
        params.append(folder_id)
        with get_conn() as conn:
            conn.execute(f"UPDATE folders SET {', '.join(sets)} WHERE id = ?", params)
    return get_folder(folder_id)


def delete_folder(folder_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))


def _folder_row(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "created_at": r["created_at"],
        "settings": json.loads(r["settings_json"]),
        "count": r["count"],
    }


# ── Transcriptions ───────────────────────────────────────────────────────────

def list_transcriptions(folder_id: int | None = None, q: str | None = None, limit: int | None = None) -> list[dict]:
    where, params = [], []
    if folder_id is not None:
        where.append("t.folder_id = ?")
        params.append(folder_id)
    if q:
        where.append("(t.name LIKE ? OR f.name LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"""
        SELECT t.id, t.folder_id, t.name, t.created_at, t.language, t.status,
               t.duration_s, f.name AS folder_name
        FROM transcriptions t
        JOIN folders f ON f.id = t.folder_id
        {clause}
        ORDER BY t.created_at DESC, t.id DESC
    """
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_transcription_summary(r) for r in rows]


def get_transcription(transcription_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT t.*, f.name AS folder_name
            FROM transcriptions t
            JOIN folders f ON f.id = t.folder_id
            WHERE t.id = ?
            """,
            (transcription_id,),
        ).fetchone()
    return _transcription_full(row) if row else None


def create_transcription(
    *,
    folder_id: int,
    name: str,
    language: str | None,
    source_filename: str | None,
    audio_filename: str | None,
    duration_s: float | None,
    segments: list,
    raw_response: dict | None,
    status: str = "done",
) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO transcriptions
                (folder_id, name, created_at, language, status,
                 source_filename, audio_filename, duration_s,
                 segments_json, raw_response_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                folder_id, name, _now(), language, status,
                source_filename, audio_filename, duration_s,
                json.dumps(segments),
                json.dumps(raw_response) if raw_response is not None else None,
            ),
        )
        tid = cur.lastrowid
    return get_transcription(tid)


def update_transcription(
    transcription_id: int, *,
    name: str | None = None,
    folder_id: int | None = None,
    segments: list | None = None,
) -> dict | None:
    sets, params = [], []
    if name is not None:
        sets.append("name = ?"); params.append(name)
    if folder_id is not None:
        sets.append("folder_id = ?"); params.append(folder_id)
    if segments is not None:
        sets.append("segments_json = ?"); params.append(json.dumps(segments))
    if sets:
        params.append(transcription_id)
        with get_conn() as conn:
            conn.execute(f"UPDATE transcriptions SET {', '.join(sets)} WHERE id = ?", params)
    return get_transcription(transcription_id)


def delete_transcription(transcription_id: int) -> dict | None:
    """Delete the row and return it (so the caller can clean up the audio file)."""
    t = get_transcription(transcription_id)
    if t:
        with get_conn() as conn:
            conn.execute("DELETE FROM transcriptions WHERE id = ?", (transcription_id,))
    return t


def _transcription_summary(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "folder_id": r["folder_id"],
        "folder_name": r["folder_name"],
        "name": r["name"],
        "created_at": r["created_at"],
        "language": r["language"],
        "status": r["status"],
        "duration_s": r["duration_s"],
    }


def _transcription_full(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "folder_id": r["folder_id"],
        "folder_name": r["folder_name"],
        "name": r["name"],
        "created_at": r["created_at"],
        "language": r["language"],
        "status": r["status"],
        "source_filename": r["source_filename"],
        "audio_filename": r["audio_filename"],
        "duration_s": r["duration_s"],
        "segments": json.loads(r["segments_json"]),
        "raw_response": json.loads(r["raw_response_json"]) if r["raw_response_json"] else None,
    }
