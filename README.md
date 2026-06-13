# TINA Transcription API
Standalone FastAPI service that diarizes an audio file and transcribes each 
speaker turn using a Frisian or Dutch MMS beam-search model, using a common Frisian/Dutch
kenlm model. In dual language mode, the choice between Frisian and Dutch is made with a 
trained language-ID classifier.

The service is exposed through an OpenAI-compatible transcription route
(`POST /v1/audio/transcriptions`), so existing OpenAI clients can use it with only a
`base_url` change, while the Frisian/Dutch language and speaker information is preserved
in an extra response block. See the [API](#api) section for details.

The project consists of the API (in `/api`), a minimal developer test frontend
(`/api_frontend`), and a more polished, user-facing frontend (`/UI_frontend`).

# IMPORTANT! Notes on usage
This is research code developed for the TINA project, in collaboration with Municipality 
of Leeuwarden, which has the goal to develop reliable and open-source dutch/frisian audio 
transcription. Within the context of this project, adapter files, kenlm models and a 
language identifier model were trained. 

Those files are not included in this repository. If you would like to experiment with these 
models, please contact us at mark.westra (at) nhlstenden (dot) com, and we can discuss opportunities for 
collaboration. 

In a later stage in the project, we plan to open source the trained models as well.


## Requirements
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Finetuned MMS adapter files (`adapter.fry.safetensors`, `adapter.nld.safetensors`)
- Shared KenLM ARPA language model (trained on both Frisian and Dutch)
- Trained language-ID classifier (`.pkl`)
- A HuggingFace account with access granted to `pyannote/speaker-diarization-3.1`

## Setup of api
1. **Clone the repository**

2. **Create your `.env` file** in the `api/` directory by copying the template:

   ```bash
   cp api/.env_template api/.env
   ```

   Then fill in the required values (see Configuration below).

3. **Install dependencies:**

   ```bash
   cd api
   uv sync
   ```

   On Ubuntu, `kenlm` requires the Python development headers before `uv sync` will succeed:

   ```bash
   sudo apt install python3.12-dev
   ```

4. **Run the server (development):**

   ```bash
   cd api
   uv run uvicorn app.main:app --port 8001
   ```

All models are loaded at startup. The first startup will download the MMS and pyannote model weights from HuggingFace (~4 GB), which may take several minutes. Subsequent startups load from the local cache. Set `MODEL_CACHE_DIR` to a permanent location to avoid re-downloading.

## Setup of Test frontend
A minimal browser UI for manual testing is included in `api_frontend/`. It connects directly to the API via HTTP and supports two source modes:

- **Server file** — select a file from `AUDIO_BASE_DIR` via a dropdown
- **Upload file** — pick a local audio file from your computer

Both modes transcribe via the OpenAI-compatible `POST /v1/audio/transcriptions` endpoint (server-file mode fetches the file from `/audio/{path}` and uploads it). The page shows an audio player for playback, per-segment play buttons, a transcript view, and the raw OpenAI-format request/response JSON.

To run it locally:

```bash
cd api_frontend
uv sync
uv run uvicorn main:app --port 8080
```

Then open http://localhost:8080 in your browser.

On a remote VM, use `--host 0.0.0.0` so the frontend is reachable from outside, and set `API_URL` in `api_frontend/.env` to the VM's external IP (see [VM deployment](#vm-deployment)).


## User-facing frontend (`UI_frontend`)
A more polished, user-facing web app for organizing and editing transcriptions. Unlike
`api_frontend` (which calls the API directly), the browser talks only to the
`UI_frontend` backend, which persists data in SQLite and calls the transcription API
server-to-server — so the API key stays on the server.

Key features:
- **Folders** of named transcriptions, with search and a recent-files sidebar.
- **Upload + transcribe** with language and folder settings.
- **Reading-view editor**: edit text inline, rename speakers, split a turn on Enter,
  per-segment play and right-click "re-transcribe as Dutch/Frisian", find & replace,
  and a per-language highlight toggle.
- **Copy** to clipboard and **export** to `.txt` / `.json`.

Data is stored under `UI_frontend/data/` (SQLite DB + uploaded audio).

To run it locally (the transcription API in `/api` must be running first):

```bash
cd UI_frontend
uv sync
cp .env_template .env        # set TRANSCRIPTION_API_KEY to match api/.env
uv run uvicorn main:app --port 8090
```

Then open http://localhost:8090 in your browser. See
[`UI_frontend/README.md`](UI_frontend/README.md) for full setup, configuration, and
[`UI_frontend/ARCHITECTURE.md`](UI_frontend/ARCHITECTURE.md) for the design.


## VM deployment
When running on a remote VM and accessing the services from another machine, both services must listen on all interfaces and the relevant ports must be open in the firewall.

**Open ports:**

```bash
sudo ufw allow 8001   # API
sudo ufw allow 8080   # frontend
```

**Start both services** using the provided scripts, which also stops any already-running instances and keeps the processes alive after the terminal is closed:

```bash
chmod +x api_restart.sh   # first time only
chmod +x api_frontend_restart.sh   # first time only
./restart.sh
```

Logs are written to `logs/api.log` and `logs/frontend.log`. PIDs are stored in `api.pid` and `frontend.pid`.

Services are started as background services.

**To close the ports again** when done:

```bash
sudo ufw delete allow 8001
sudo ufw delete allow 8080
```

### Frontend `.env` on the VM
The frontend's `api_frontend/.env` must point to the VM's external IP so the browser can reach the API:

```
API_URL=http://<VM_IP>:8001
API_KEY=<your-api-key>
```
The API_KEY is a random key that is common to the api and the frontend.

### HuggingFace model cache
On a VM with a network-mounted data drive, set `MODEL_CACHE_DIR` to a path on local storage to avoid slow model loading over the network. For example:

```
MODEL_CACHE_DIR=/media/local_data/hf_cache
```

## Configuration
All configuration lives in `api/.env`. The file is gitignored — use `api/.env_template` as the starting point.

| Variable | Required | Description |
|----------|----------|-------------|
| `AUDIO_BASE_DIR` | Yes | Directory from which audio filenames are resolved when a file is chosen from the example list. |
| `API_KEY` | Yes | Static bearer token required on all API requests. |
| `HF_TOKEN` | Yes | HuggingFace token. Accept the model licence at https://huggingface.co/pyannote/speaker-diarization-3.1 |
| `ADAPTER_DIR` | Yes | Directory containing the finetuned adapter files (`adapter.fry.safetensors`, `adapter.nld.safetensors`). |
| `KENLM_MODEL_PATH` | Yes | Path to the shared KenLM ARPA file (trained on both Frisian and Dutch). |
| `LANG_ID_MODEL_PATH` | Yes | Path to the language-ID classifier `.pkl` produced by `LANG_ID_VM/train_lid.py`. |
| `MODEL_CACHE_DIR` | No | Directory for caching HuggingFace model weights. Defaults to `~/.cache/huggingface`. |
| `MIN_SEGMENT_DUR` | No | Minimum speaker segment duration in seconds. Default: `0.3`. |
| `PAD_S` | No | Padding added around each segment before transcription. Default: `0.1`. |
| `BEAM_WIDTH` | No | KenLM beam search width. Higher = better quality, slower decoding. Default: `100`. |

## API
The service exposes two families of transcription endpoints:

- **OpenAI-compatible** — `POST /v1/audio/transcriptions`, which mirrors OpenAI's
  audio transcription API (`response_format=diarized_json`). This is the recommended
  entry point: existing OpenAI clients/SDKs can point at this service with only a
  `base_url` change. TINA-specific data (per-segment Frisian/Dutch language + note,
  and the speaker summary) is returned in a separate top-level `tina` block that
  spec-compliant OpenAI clients ignore. See [`POST /v1/audio/transcriptions`](#post-v1audiotranscriptions).
- **Native TINA** — `POST /transcribe` (server-side filename) and
  `POST /upload-transcribe` (direct upload), which return TINA's own flat response
  shape. These predate the OpenAI route and are kept for backward compatibility.

Both families run the same diarization + transcription pipeline and require the same
authentication. The native endpoints authenticate with the `X-API-Key` header; the
OpenAI-compatible endpoint additionally accepts `Authorization: Bearer <API_KEY>`
(as the OpenAI SDK sends it). The bundled test frontend in `api_frontend/` drives the
OpenAI-compatible endpoint for both of its source modes.

To use the api, it is the easiest to look at the api_frontend code, as this uses all the api functionality.

### `GET /files`
Returns audio filenames available in `AUDIO_BASE_DIR`. Returns all files by default; pass `?limit=N` to cap the count.

### `POST /transcribe`
Diarizes an audio file and transcribes each speaker turn.

**Request body (JSON):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `filename` | string | required | Audio filename, relative to `AUDIO_BASE_DIR` |
| `recording_context` | string | `"GENERAL"` | Recording context — reserved for future use (`"GENERAL"` or `"COUNCIL_MEETING"`) |
| `language` | string | `"nld+fry"` | Language mode: `"nld+fry"`, `"fry"`, or `"nld"` |

**Example request:**

```bash
curl -X POST http://localhost:8001/transcribe \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <API_KEY>" \
  -d '{"filename": "interview.wav"}'
```

### `POST /upload-transcribe`
Same as `/transcribe` but accepts a direct audio file upload instead of a filename. The uploaded file is written to a temporary location, transcribed, and then deleted.

**Request body (`multipart/form-data`):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file` | file | required | Audio file to transcribe (`.wav`, `.mp3`, `.flac`, `.ogg`, `.m4a`, `.aac`) |
| `recording_context` | string | `"GENERAL"` | Recording context — reserved for future use |
| `language` | string | `"nld+fry"` | Language mode: `"nld+fry"`, `"fry"`, or `"nld"` |

**Example request:**

```bash
curl -X POST http://localhost:8001/upload-transcribe \
  -H "X-API-Key: <API_KEY>" \
  -F "file=@interview.wav" \
  -F "language=nld+fry"
```

Both endpoints return the same response format:

**Response body (JSON):**

```json
{
  "segments": [
    {
      "speaker": "SPEAKER_00",
      "start": 0.512,
      "end": 4.231,
      "text": "goeie moarn allegear",
      "lang": "fry",
      "note": "ok"
    },
    {
      "speaker": "SPEAKER_01",
      "start": 4.850,
      "end": 7.100,
      "text": "inaudible",
      "lang": null,
      "note": "overlapping_speech"
    }
  ],
  "speakers": {
    "SPEAKER_00": {
      "n_segments": 5,
      "total_dur_s": 18.4,
      "dominant_lang": "fry",
      "fry_pct": 0.8
    },
    "SPEAKER_01": {
      "n_segments": 3,
      "total_dur_s": 9.1,
      "dominant_lang": "nld",
      "fry_pct": 0.333
    }
  },
  "total_duration_s": 42.1,
  "n_speakers": 2
}
```

**Segment `note` values:**

| Value | Meaning |
|-------|---------|
| `ok` | Segment was transcribed normally |
| `overlapping_speech` | Multiple speakers active simultaneously; text is `"inaudible"` |

**Error responses (`/transcribe`):**

| Status | Cause |
|--------|-------|
| `400` | Filename escapes `AUDIO_BASE_DIR` |
| `404` | Audio file not found |
| `500` | `AUDIO_BASE_DIR` not configured, diarization failed, or transcription failed |

**Error responses (`/upload-transcribe`):**

| Status | Cause |
|--------|-------|
| `400` | Unsupported file type |
| `500` | Diarization failed or transcription failed |

### `POST /v1/audio/transcriptions`
OpenAI-compatible transcription endpoint. Mirrors OpenAI's `POST /v1/audio/transcriptions` with `response_format=diarized_json`, so an existing OpenAI client can point at this service. The standard OpenAI segment objects are kept pure; TINA-specific data (per-segment language/note and the speaker summary) is returned in a separate top-level `tina` block, which spec-compliant clients ignore.

Authentication accepts either the `X-API-Key` header (as the other endpoints) or `Authorization: Bearer <API_KEY>` (as the OpenAI SDK sends it).

**Request body (`multipart/form-data`):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file` | file | required | Audio file to transcribe (`.wav`, `.mp3`, `.flac`, `.ogg`, `.m4a`, `.aac`) |
| `model` | string | `"tina-mms"` | Accepted for compatibility; ignored (the model is fixed by deployment) |
| `language` | string | — | ISO/OpenAI language hint, mapped to internal modes: `nl`/`nld`/`dutch` → `nld`, `fy`/`fry`/`frisian` → `fry`, empty or `nld+fry` → dual mode. Unknown values fall back to dual mode |
| `response_format` | string | `"diarized_json"` | Only `diarized_json` is supported |
| `prompt`, `temperature` | — | — | Accepted for compatibility; ignored |

**Example request (curl):**

```bash
curl -X POST http://localhost:8001/v1/audio/transcriptions \
  -H "Authorization: Bearer <API_KEY>" \
  -F "file=@interview.wav" \
  -F "response_format=diarized_json" \
  -F "language=nl"
```

**Example request (OpenAI Python SDK):**

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8001/v1", api_key="<API_KEY>")
result = client.audio.transcriptions.create(
    model="tina-mms",
    file=open("interview.wav", "rb"),
    response_format="diarized_json",
)
```

**Response body (JSON):**

```json
{
  "task": "transcribe",
  "duration": 42.1,
  "text": "goeie moarn allegear ...",
  "segments": [
    {
      "id": "0",
      "start": 0.512,
      "end": 4.231,
      "text": "goeie moarn allegear",
      "speaker": "SPEAKER_00",
      "type": "transcript.text.segment"
    }
  ],
  "usage": { "type": "duration", "seconds": 42.1 },
  "tina": {
    "segments_meta": [
      { "id": "0", "lang": "fry", "note": "ok" }
    ],
    "speakers": {
      "SPEAKER_00": {
        "n_segments": 5,
        "total_dur_s": 18.4,
        "dominant_lang": "fry",
        "fry_pct": 0.8
      }
    }
  }
}
```

Overlapping-speech segments have segment `text` set to `"inaudible"`, `tina.segments_meta[].lang` of `null`, and `note` of `"overlapping_speech"` (matching the `/transcribe` semantics). Each `tina.segments_meta[]` entry shares its `id` with the corresponding `segments[]` entry.

**Error responses (`/v1/audio/transcriptions`):**

| Status | Cause |
|--------|-------|
| `400` | Unsupported file type, or `response_format` other than `diarized_json` |
| `401` | Invalid or missing API key |
| `500` | Diarization failed or transcription failed |



## Unit tests
Install dev dependencies and run the test suite:

```bash
cd api
uv sync --group dev
uv run pytest tests/ -v
```

Tests use mocked model loading — no GPU or downloaded weights are required.

| File | What is tested |
|------|----------------|
| `tests/test_api.py` | Endpoint behaviour: 404 missing file, 400 path traversal, successful transcription, overlapping speech → `"inaudible"`, speaker summary, error propagation; OpenAI `/v1/audio/transcriptions` diarized_json shape, bearer auth, language mapping, response_format validation |
| `tests/test_diarize.py` | `_is_overlapping`: non-overlapping, overlapping, contained, single-segment, touching boundaries |
| `tests/test_hybrid.py` | `classify_from_embeddings`: fry wins above threshold, nld wins below, exact threshold → fry |
| `tests/test_utils.py` | `load_audio`: dtype/shape, resampling, missing file |

