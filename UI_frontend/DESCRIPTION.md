This document describes the intended user interface of the transcription tool

Example screenshots are in the folder /screenshots. Screenshot file names contain a hint of what they show. Don't take these literally, just as a suggestion. We can and will do things differently.

# Tech Stack
* HTML/CSS frontend
* FastAPI backend
* modular frontend files
* for how the frontend calls the api, consult the folder /api_frontend

# Data structure:
* Projects: have a name and settings
* Projects contain transcriptions. transcriptions have a name

# High level overview
* Layout with left sidebar
* left sidebar shows latest transcriptions + search bar for projects and files + filter on projects
* clicking on transcription opens the transcription on the right detail view
* There is a way to go to the project overview, which shows the projects as folders. When the folder is opened, I see the transcriptions.
* When a transcription is opened, I see a transcript tab and a content tab.
* The transcript tab shows the transcribed text. If it has been translated, it shows multiple sub-tabs, one per language
* The transcript tab shows options: undo, redo, copy, translate, and export.

# TODO items. Implement one by one!
1. ✅ decide on structure of UI — see ARCHITECTURE.md
* 'projects' → **Folders**; seeded default folder "My transcriptions"
* sidebar: New Transcript · search · filter-by-folder · recent list · Folders link
* no need to create a folder first (default folder); new transcriptions save to the active/last-used folder, pickable in upload settings
* persistence: SQLite via FastAPI backend (browser → backend → transcription API)
* detail tabs: Transcript + Content (placeholder)
* Example screenshots: 1, 1a, 1b

2. ✅ implement main UI items
* sidebar (New Transcript · search · folder filter · recent list · Folders link) + folders overview detail view with create/rename/delete, expandable to transcriptions
* backend scaffold: FastAPI + SQLite (db.py) + REST API + server-to-server proxy to the transcription API
* run: `cd UI_frontend && uv sync && cp .env_template .env && uv run uvicorn main:app --port 8090`

3. ✅ implement file upload + transcript
* upload (select + drag & drop), shows selected file with duration
* settings: name, save-to-folder (active), language (Dutch / Frisian / Dutch+Frisian)
* Transcribe Now → POST /api/transcriptions (progress spinner) → opens the result
* transcript detail view: Transcript + Content(placeholder) tabs, speaker blocks with
  per-segment playback + language badges, sticky audio player
* deferred (needs API support): exact number of speakers (see ../TODO.md), custom spelling
* editing (search/replace, split) is item 4; copy/export is item 5
* example screenshots: 2, 3, 4, 5

4. transcript editing (see ARCHITECTURE.md "Transcript editing model")
* ✅ 4a: Detail / Reading view toggle; reading view = flowing editable paragraph per
  turn, edits preserve per-segment language/timestamps
* ✅ 4b: split-on-Enter (snap to real boundary, else interpolate; break_before flag;
  caret lands in the new block; same-speaker halves stay separate)
* ✅ 4c: find & replace (highlights all matches via CSS Custom Highlight API,
  match counter + prev/next, replace current / replace all, persisted)
* example screenshots 5, 6, 6a, 7

5. options after transcription edit
* implement copy to clipboard
* implement 
* example screenshots: 7, 8, 9, 10, 11, 12, 13

6. Implement content hub
* example screenshot: 14