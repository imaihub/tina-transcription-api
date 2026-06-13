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
