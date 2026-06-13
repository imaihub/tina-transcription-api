# UI_frontend — architecture & structure

Decisions for the new user-facing frontend. The existing `api_frontend/` (developer
test UI) is kept as-is; this is a separate, more polished app under `UI_frontend/`.

See `DESCRIPTION.md` for the spec and `screenshots/` for reference mockups
(WhisperTranscribe — used as inspiration, not copied literally).

## Terminology
- **Folder** — a named container with settings; holds transcriptions. A seeded
  default folder, **"My transcriptions"**, always exists so the New Transcript flow
  works without creating a folder first.
- **Transcription** — named, belongs to exactly one folder.
- Detail-view breadcrumb: `Folders / <folder> / <transcription>`.

## Capability constraint
The transcription API supports diarization (speakers), `nld` / `fry` / `nld+fry`, and
(soon) `num_speakers`. It is **stateless**. Translation, Content Hub, Visual Hub,
brand voice, record/URL/podcast input — all WhisperTranscribe features we do **not**
have — are out of scope or placeholders. The core flow (upload → settings →
transcribe → edit → export) maps directly onto our API.

## Architecture
Browser talks **only to the UI_frontend backend**, which persists data and calls the
transcription API server-to-server. The transcription API key stays server-side.

```
browser ──REST──> UI_frontend FastAPI ──/v1/audio/transcriptions──> transcription API
                        │
                        └── SQLite (metadata + edited transcript) + disk (audio)
```

## Persistence (SQLite + disk)
- DB: `UI_frontend/data/app.db`
- Audio: `UI_frontend/data/audio/<transcription_id>.<ext>` (so segments stay playable
  after reopening a transcription).

```
folders(id, name, created_at, settings_json)
transcriptions(id, folder_id, name, created_at, language,
               status, source_filename, audio_filename,
               duration_s, segments_json, raw_response_json)
```
- `segments_json` — current (edited) transcript state, rendered/edited by the UI.
- `raw_response_json` — original `/v1/audio/transcriptions` response, kept for
  reference and re-export.

## Backend REST API (UI_frontend)
- `GET    /api/folders`                  — list folders + transcription counts
- `POST   /api/folders`                  — create
- `PATCH  /api/folders/{id}`             — rename / update settings
- `DELETE /api/folders/{id}`
- `GET    /api/transcriptions?folder_id=&q=` — list (sidebar recent / search / filter)
- `GET    /api/transcriptions/{id}`      — full detail (segments)
- `POST   /api/transcriptions`           — multipart upload + settings; proxies to the
                                           transcription API, stores result, returns it
- `PATCH  /api/transcriptions/{id}`      — save edits (name, segments_json)
- `DELETE /api/transcriptions/{id}`
- `GET    /api/transcriptions/{id}/audio`— stream stored audio

Config via `.env`: `TRANSCRIPTION_API_URL`, `TRANSCRIPTION_API_KEY`.

## Layout & views
**Left sidebar:** New Transcript button · search (folders + files) · filter-by-folder ·
recent transcriptions list · Folders link · footer (about/version).

**Detail pane** has three states:
1. **New Transcript** — upload drop zone + settings (name, Save-to-folder [default =
   active folder], primary language Dutch/Frisian/both, speaker recognition on/off,
   number of speakers auto/exact, custom spelling) → Transcribe Now.
2. **Folders overview** — table of folders (name, count, created, actions), expandable
   to their transcriptions; + New Folder.
3. **Transcription detail** — breadcrumb + editable title; tabs **Transcript** |
   **Content** (placeholder "coming soon"). Transcript tab: toolbar (Find & Replace,
   undo/redo, Copy, Export; Translate deferred) over speaker blocks with per-segment
   play + editable text, plus an audio player.

## Frontend module layout (vanilla HTML/CSS/ES modules, no build step)
```
UI_frontend/
  main.py            FastAPI: serve static + REST + proxy to transcription API
  db.py              SQLite access
  .env_template
  pyproject.toml
  static/
    index.html
    css/styles.css
    js/
      app.js         bootstrap, view routing, shared state
      api.js         fetch wrappers for the backend REST API
      sidebar.js
      folders.js     folders overview
      upload.js      new-transcript flow
      transcript.js  transcription detail + editing
```

## Build order (from DESCRIPTION.md TODO)
1. ✅ Decide structure (this document)
2. Sidebar + folders detail view, with New Transcript button
3. File upload + settings + transcribe
4. Transcript editing: search & replace, split on Enter
5. Post-edit options: copy to clipboard, export
6. Content hub (placeholder for now)
