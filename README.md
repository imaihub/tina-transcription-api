# TINA Transcription API
Standalone FastAPI service that diarizes an audio file and transcribes each 
speaker turn using a Frisian or Dutch MMS beam-search model, using a common Frisian/Dutch
kenlm model. In dual language mode, the choice between Frisian and Dutch is made with a 
trained language-ID classifier.

The project consists of the api (in the folder /api), and a minimal example frontend in /api_frontend

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

- **Server file** — select a file from `AUDIO_BASE_DIR` via a dropdown (uses `POST /transcribe`)
- **Upload file** — pick a local audio file from your computer and upload it directly (uses `POST /upload-transcribe`; the file is deleted from the server after transcription)

Both modes show an audio player for playback, per-segment play buttons, a transcript view, and the raw request/response JSON.

To run it locally:

```bash
cd api_frontend
uv sync
uv run uvicorn main:app --port 8080
```

Then open http://localhost:8080 in your browser.

On a remote VM, use `--host 0.0.0.0` so the frontend is reachable from outside, and set `API_URL` in `api_frontend/.env` to the VM's external IP (see [VM deployment](#vm-deployment)).


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
| `tests/test_api.py` | Endpoint behaviour: 404 missing file, 400 path traversal, successful transcription, overlapping speech → `"inaudible"`, speaker summary, error propagation |
| `tests/test_diarize.py` | `_is_overlapping`: non-overlapping, overlapping, contained, single-segment, touching boundaries |
| `tests/test_hybrid.py` | `classify_from_embeddings`: fry wins above threshold, nld wins below, exact threshold → fry |
| `tests/test_utils.py` | `load_audio`: dtype/shape, resampling, missing file |

