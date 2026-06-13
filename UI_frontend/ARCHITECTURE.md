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

## Transcript editing model (item 4)
A single **reading view** over the segment list (segments stay the source of truth):
consecutive same-speaker segments are merged into one flowing, editable paragraph per
turn. (An earlier per-segment "Detail" view was removed as overkill — language errors
are rare; all per-segment actions now live in a context menu.)

- **Edits preserve segments.** Each segment is a distinct editable run within the
  paragraph; an edit updates only that segment's `text`, so per-segment language +
  timestamps (and retranscribe) survive editing.
- **Per-segment actions via context menu.** Right-click a segment — or click the
  language chip shown on hover/active — to open a menu: play segment, re-transcribe as
  Dutch/Frisian (current marked). Hover tints by language (blue=Dutch, green=Frisian);
  the focused segment shows a pronounced boundary. A "Show language" toolbar toggle
  turns on an always-on subtle per-language tint.
- **Turn grouping** = consecutive segments with the same speaker *and* no explicit
  break. A `break_before` flag on a segment forces a new turn even for the same
  speaker — needed so a split into two same-named blocks doesn't re-merge.
- **Split-on-Enter timing**: if the cursor is at/near a real segment boundary, snap to
  that true timestamp; only when splitting *inside* a segment, interpolate by character
  offset: `mid = start + (end−start) × charsBefore/charsTotal`. We have no word-level
  timestamps, so interpolation is approximate — but fine segments mean we fall back to
  it rarely. A split divides the cursor's segment, marks the second half `break_before`,
  and moves any later segments of the turn into the new block.
- **Search & replace** operates on the segment text model directly, so it is
  view-independent.

Build sub-steps: (4a) view-mode toggle + reading view with per-segment editing;
(4b) split-on-Enter; (4c) find & replace.

## Build order (from DESCRIPTION.md TODO)
1. ✅ Decide structure (this document)
2. Sidebar + folders detail view, with New Transcript button
3. File upload + settings + transcribe
4. Transcript editing: search & replace, split on Enter
5. Post-edit options: copy to clipboard, export
6. Content hub (placeholder for now)
