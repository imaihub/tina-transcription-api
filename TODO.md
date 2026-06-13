# TODO

## Next: Expose diarization speaker controls on `/v1/audio/transcriptions`

Let callers hint the expected speaker count via the OpenAI-format endpoint. Expose
**all three** pyannote controls as optional multipart form fields:

- `num_speakers` — exact expected number of speakers
- `min_speakers` — lower bound
- `max_speakers` — upper bound

All optional; when none are given, behaviour is unchanged (pyannote estimates the
count). OpenAI SDK clients pass them via `extra_body={"num_speakers": 2}`; curl uses
`-F "num_speakers=2"`.

### Implementation outline

Thread the values from the endpoint down to the pyannote pipeline call:

```
openai_transcriptions  (new Form fields)
  → _process(..., num_speakers, min_speakers, max_speakers)
    → diarize(audio_path, min_segment_dur, num_speakers=..., min_speakers=..., max_speakers=...)
      → _pipeline({"waveform": ..., "sample_rate": SR}, num_speakers=..., min_speakers=..., max_speakers=...)
```

Touch points:

- `api/app/main.py` — add `num_speakers`, `min_speakers`, `max_speakers` as
  `int | None = Form(None)` on `openai_transcriptions`; pass through `_process`.
- `api/app/diarize.py` — accept the three kwargs on `diarize()` and forward only the
  non-`None` ones to the `_pipeline(...)` call.

### Validation

- Reject `num_speakers` combined with `min_speakers`/`max_speakers` → `400`
  (pyannote errors on that combination).
- Reject non-positive values and `min_speakers > max_speakers` → `400`.

### Tests (`api/tests/test_api.py`)

- `num_speakers` is forwarded to `diarize` (patch `app.main.diarize`, assert kwarg).
- `num_speakers` + `min_speakers` together → `400`.
- Omitting all three leaves current behaviour unchanged.

### Docs

- Add the three fields to the `/v1/audio/transcriptions` request table in `README.md`,
  noting the `extra_body` pattern for OpenAI SDK clients.

### Notes / open questions

- Decide whether to namespace future TINA-only request fields (e.g. `tina_*`) to avoid
  colliding with OpenAI params added later. `num_speakers`/`min_speakers`/`max_speakers`
  are intuitive enough to leave bare.
- Other settings that could later move from `.env` to per-request overrides:
  `MIN_SEGMENT_DUR`, `PAD_S`, `BEAM_WIDTH`.
