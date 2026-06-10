# Performance TODO

Deferred backend performance work. These are higher-effort changes that need
benchmarking and validation before adoption. The low-risk wins (decode only the
winning language, cached device detection, `torch.inference_mode`) are already
applied in `app/hybrid.py` and `app/models.py`.

Benchmark first, then decide whether the added complexity is justified.

---

## 1. Batch the encoder forward passes across segments

**Impact:** High · **Effort:** High · **Risk:** Medium

Currently `app/main.py` processes diarization segments strictly sequentially
(one `run_hybrid` call per segment via the thread executor). The GPU sits idle
between segments while Python prepares the next slice, and per-call dispatch
overhead is paid once per segment.

**Idea:** collect all non-overlapping segment slices up front, pad them into
batches, and run the encoder once per language per batch instead of once per
segment. This keeps the GPU saturated and amortizes dispatch overhead.

**Watch out for:**
- Padding must be masked correctly. The `std/max/min` temporal pooling in
  `app/lang_id.py::pool_hidden` reduces over the time axis — padded frames would
  corrupt the pooled embedding and shift language-ID results. Pass an attention
  mask and pool only over real frames.
- The KenLM beam search needs per-sequence logit lengths; slice each sequence
  back to its true length before decoding.
- Larger batches raise peak GPU memory — two ~1B-param models are already
  resident, so tune batch size per device.

**Validation:** confirm identical transcripts and lang-ID decisions vs. the
sequential path on a fixed sample set before/after.

---

## 2. fp16 autocast on CUDA

**Impact:** Medium-High (GPU only) · **Effort:** Low · **Risk:** Medium

Models load in fp32 (`app/models.py`). Wrapping the encoder pass in
`torch.autocast("cuda", dtype=torch.float16)` roughly halves encoder time and
memory on CUDA.

**Watch out for:**
- The language-ID classifier was trained on fp32 pooled embeddings. Keep the
  pooling and `classify_from_embeddings` math in fp32 (cast the hidden states
  back up before pooling) and verify classification accuracy does not drift.
- MPS fp16 support is less reliable than CUDA — gate autocast on
  `get_device() == "cuda"` only.

**Validation:** compare WER/CER and lang-ID accuracy with `evaluate.py` in fp32
vs. fp16; adopt only if quality is unchanged within tolerance.
