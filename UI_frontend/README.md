# TINA Transcribe — UI frontend

User-facing frontend for the TINA transcription service. It organizes transcriptions
into **folders**, runs new transcriptions via the transcription API, and stores the
results so they can be reopened and edited.

This is a separate, more polished app from the developer test UI in `api_frontend/`.
The browser talks only to this backend, which persists data in SQLite and calls the
transcription API server-to-server (so the API key never reaches the browser).

```
browser ──REST──> UI_frontend (FastAPI) ──/v1/audio/transcriptions──> transcription API
                       │
                       └── SQLite (metadata + transcript) + disk (audio)
```

See `ARCHITECTURE.md` for the full design and `DESCRIPTION.md` for the spec/roadmap.

## Features
- **Folders** — group transcriptions; create/rename/delete. A default folder
  ("My transcriptions") is always present. The sidebar has search, a folder filter, and
  a recent-files list.
- **New Transcript** — upload an audio file (file picker or drag & drop), choose the
  target folder and language (Dutch / Frisian / both), and transcribe.
- **Reading-view editor** (the transcription detail page):
  - Flowing, editable text grouped per speaker turn; edits autosave. Each segment stays
    a distinct editable run, so per-segment language and timestamps are preserved.
  - **Rename a speaker** by clicking its label — renames it across all its segments.
  - **Split a turn** by pressing Enter mid-text — snaps to a real segment boundary when
    the caret is at a segment edge, otherwise interpolates the split time by character
    position. Both halves keep the speaker (rename one to re-attribute).
  - **Playback** — play a single segment, "play from here" to the end of the turn, or
    play a whole turn; the currently-playing segment is highlighted. Playback is
    continuous (the real pauses in the recording are preserved).
  - **Re-transcribe a segment** as Dutch or Frisian via right-click (or the language
    chip shown on hover/active) — fixes mis-detected language without re-diarizing.
  - **Find & replace** — highlights all matches, navigate with a counter, replace one or
    all.
  - **Show language** toggle — an always-on subtle per-language tint (blue = Dutch,
    green = Frisian).
- **Copy** the transcript to the clipboard (with speaker-name / timestamp toggles) and
  **Export** to `.txt` or `.json`.
- A **Content** tab exists as a placeholder ("coming soon").

> The find-match highlighting uses the CSS Custom Highlight API (modern Chrome / Safari /
> Firefox); where unavailable it falls back to outlining the current match.

## Requirements
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A running **transcription API** (the FastAPI app in `../api`). Start it first — see
  the top-level `README.md`. By default it listens on `http://localhost:8001`.

## Setup
1. **Install dependencies:**

   ```bash
   cd UI_frontend
   uv sync
   ```

2. **Create your `.env` file** by copying the template:

   ```bash
   cp .env_template .env
   ```

   Then set the values (see Configuration below). In particular,
   `TRANSCRIPTION_API_KEY` must match the `API_KEY` in `../api/.env`.

## Run

```bash
cd UI_frontend
uv run uvicorn main:app --port 8090
```

Then open <http://localhost:8090> in your browser.

For development with auto-reload on code changes:

```bash
uv run uvicorn main:app --port 8090 --reload
```

On first start the backend creates `data/app.db`, the `data/audio/` directory, and
seeds a default folder named **"My transcriptions"**.

To make the UI reachable from another machine (e.g. on a VM), bind to all interfaces
and open the port in the firewall:

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8090
```

## Configuration
All configuration lives in `UI_frontend/.env` (gitignored — copy `.env_template`).

| Variable | Required | Description |
|----------|----------|-------------|
| `TRANSCRIPTION_API_URL` | Yes | URL of the transcription API. Default: `http://localhost:8001`. |
| `TRANSCRIPTION_API_KEY` | Yes | API key for the transcription API. Must match `API_KEY` in `../api/.env`. |
| `DATA_DIR` | No | Where the SQLite DB and uploaded audio are stored. Defaults to `./data` next to `main.py`. |

## Data
- **`data/app.db`** — SQLite database (folders and transcriptions, including the
  edited transcript and the original API response).
- **`data/audio/`** — uploaded audio files, so transcription segments stay playable
  after reopening.

Both are gitignored. Deleting the `data/` directory resets the app to an empty state
(the default folder is re-seeded on next start).

## Backend REST API
The frontend talks to this backend (not the transcription API directly):

| Method & path | Purpose |
|---------------|---------|
| `GET /api/folders` | List folders + transcription counts |
| `POST /api/folders` | Create a folder |
| `PATCH /api/folders/{id}` | Rename / update settings |
| `DELETE /api/folders/{id}` | Delete a folder (and its transcriptions + audio) |
| `GET /api/transcriptions?folder_id=&q=&limit=` | List (sidebar / search / filter) |
| `GET /api/transcriptions/{id}` | Full transcription with segments |
| `POST /api/transcriptions` | Upload + transcribe (proxies to the API), store, return |
| `PATCH /api/transcriptions/{id}` | Save edits (name, folder, segments) |
| `DELETE /api/transcriptions/{id}` | Delete a transcription + its audio |
| `GET /api/transcriptions/{id}/audio` | Stream the stored audio |
| `POST /api/transcriptions/{id}/segments/{seg_id}/retranscribe` | Re-transcribe one segment in a forced language |

## Project layout
```
UI_frontend/
  main.py            FastAPI: serves the static app + REST API + proxy to the API
  db.py              SQLite access (folders, transcriptions)
  static/
    index.html
    css/styles.css
    js/
      app.js         bootstrap + hash router
      api.js         fetch wrappers for the backend REST API
      sidebar.js     New Transcript, search, folder filter, recent list
      folders.js     folders overview
      upload.js      new-transcript flow
      transcript.js  reading-view editor (edit, split, retranscribe, find/replace,
                     playback, copy/export)
      state.js       active-folder memory
      util.js        DOM helpers, modals, toasts
```
