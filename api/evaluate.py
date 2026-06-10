#!/usr/bin/env python3
"""
Evaluation script for the TINA transcription pipeline.

Evaluates four aspects of the pipeline without running diarization:

  1. lang-id   — Language classification accuracy (fry vs nld)
  2. fry       — Frisian-only transcription WER / CER
  3. nld       — Dutch-only transcription WER / CER
  4. mixed     — Mixed-language transcription: lang accuracy + WER
                 (combines Radboud or Gemeente fry+nld samples)

Usage (from the api/ directory):
    uv run python evaluate.py
    uv run python evaluate.py --tasks lang-id fry nld
    uv run python evaluate.py --max-samples 200 --seed 0
    uv run python evaluate.py --out results.json
"""

import argparse
import csv
import json
import random
import re
import sys
import time
import unicodedata
from pathlib import Path

import librosa
import numpy as np

# ── Model / config imports ─────────────────────────────────────────────────────

from app.config import (
    CV_FRY_CLEAN_DIR, CV_FRY_AUDIO_DIR,
    CV_NL_CLEAN_DIR,  CV_NL_AUDIO_DIR,
    RADBOUD_FRY_CLEAN_DIR, RADBOUD_FRY_AUDIO_DIR,
    RADBOUD_NL_CLEAN_DIR,  RADBOUD_NL_AUDIO_DIR,
    GEMEENTE_FRY_CLEAN_DIR, GEMEENTE_FRY_AUDIO_DIR,
    GEMEENTE_NL_CLEAN_DIR,  GEMEENTE_NL_AUDIO_DIR,
    KENLM_MODEL_PATH,
)
from app.hybrid import run_hybrid
from app.kenlm import decoder_ready, rebuild_decoder
from app.lang_id import classify_language, load_lang_id
from app.models import MODELS, load_model


# ── Dataset registry ───────────────────────────────────────────────────────────

DATASETS: dict[str, dict] = {
    "cv-fry": {
        "name":      "CommonVoice fy-NL",
        "lang":      "fry",
        "clean_dir": CV_FRY_CLEAN_DIR,
        "audio_dir": CV_FRY_AUDIO_DIR,
    },
    "cv-nl": {
        "name":      "CommonVoice nl",
        "lang":      "nld",
        "clean_dir": CV_NL_CLEAN_DIR,
        "audio_dir": CV_NL_AUDIO_DIR,
    },
    "radboud-fry": {
        "name":      "Radboud FAME fry",
        "lang":      "fry",
        "clean_dir": RADBOUD_FRY_CLEAN_DIR,
        "audio_dir": RADBOUD_FRY_AUDIO_DIR,
    },
    "radboud-nl": {
        "name":      "Radboud FAME nl",
        "lang":      "nld",
        "clean_dir": RADBOUD_NL_CLEAN_DIR,
        "audio_dir": RADBOUD_NL_AUDIO_DIR,
    },
    "gemeente-fry": {
        "name":      "Gemeente fry",
        "lang":      "fry",
        "clean_dir": GEMEENTE_FRY_CLEAN_DIR,
        "audio_dir": GEMEENTE_FRY_AUDIO_DIR,
    },
    "gemeente-nl": {
        "name":      "Gemeente nl",
        "lang":      "nld",
        "clean_dir": GEMEENTE_NL_CLEAN_DIR,
        "audio_dir": GEMEENTE_NL_AUDIO_DIR,
    },
}

# Which datasets to use per task
TASK_DATASETS = {
    "lang-id": ["cv-fry", "cv-nl", "radboud-fry", "radboud-nl", "gemeente-fry", "gemeente-nl"],
    "fry":     ["cv-fry", "radboud-fry", "gemeente-fry"],
    "nld":     ["cv-nl", "radboud-nl", "gemeente-nl"],
    "mixed":   ["radboud-fry", "radboud-nl", "gemeente-fry", "gemeente-nl"],
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _strip_diacritics(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    text = _strip_diacritics(text)
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_audio(path: Path) -> np.ndarray:
    audio, _ = librosa.load(str(path), sr=16_000, mono=True)
    return audio


def resolve_audio(ds_id: str, path_str: str) -> Path | None:
    cfg = DATASETS[ds_id]
    p = Path(path_str)
    if p.is_absolute():
        return p if p.exists() else None
    audio_dir = cfg.get("audio_dir", "")
    if not audio_dir:
        return None
    return Path(audio_dir) / path_str


def load_rows(ds_id: str, max_samples: int, seed: int) -> list[dict]:
    cfg = DATASETS[ds_id]
    clean_tsv = Path(cfg["clean_dir"]) / "clean.tsv"
    if not clean_tsv.exists():
        print(f"  [skip] {ds_id}: clean.tsv not found at {clean_tsv}")
        return []

    rows = []
    with open(clean_tsv, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            audio_path = resolve_audio(ds_id, row.get("path", ""))
            if audio_path is None or not audio_path.exists():
                continue
            rows.append({
                "audio_path": audio_path,
                "sentence":   row.get("sentence", ""),
                "lang":       cfg["lang"],
                "dataset":    ds_id,
            })

    if max_samples > 0 and len(rows) > max_samples:
        rows = random.Random(seed).sample(rows, max_samples)
    return rows


def _wer_cer(refs: list[str], hyps: list[str]) -> tuple[float | None, float | None]:
    from jiwer import cer as compute_cer, wer as compute_wer
    if not refs:
        return None, None
    return compute_wer(refs, hyps), compute_cer(refs, hyps)


def _print_header(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def _fmt(v, pct: bool = True) -> str:
    if v is None:
        return "  —   "
    return f"{v*100:5.1f}%" if pct else f"{v:.4f}"


# ── Startup ────────────────────────────────────────────────────────────────────

def startup(beam_width: int) -> None:
    print("Loading models…")
    for lang in ("fry", "nld"):
        t0 = time.time()
        load_model(f"mms-1b-all-{lang}")
        print(f"  mms-1b-all-{lang}  [{time.time()-t0:.0f}s]")

    print("Building KenLM decoders…")
    for lang in ("fry", "nld"):
        rebuild_decoder(lang)
        if not decoder_ready(lang):
            print(f"  WARNING: KenLM decoder for '{lang}' not ready — falling back to greedy decoding")

    print("Loading language-ID classifier…")
    load_lang_id()
    print("Ready.\n")


# ── Task 1: Language ID accuracy ───────────────────────────────────────────────

def task_lang_id(ds_ids: list[str], max_per_dataset: int, seed: int) -> dict:
    _print_header("Task 1 — Language ID accuracy")

    total_correct = total_n = 0
    per_dataset: list[dict] = []

    for ds_id in ds_ids:
        rows = load_rows(ds_id, max_per_dataset, seed)
        if not rows:
            continue
        true_lang = DATASETS[ds_id]["lang"]
        correct = n = 0
        t0 = time.time()
        for i, row in enumerate(rows):
            try:
                audio = load_audio(row["audio_path"])
                pred_lang, _ = classify_language(audio)
                if pred_lang == true_lang:
                    correct += 1
                n += 1
            except Exception as e:
                print(f"    [warn] {row['audio_path'].name}: {e}")
            if (i + 1) % 50 == 0:
                print(f"    {ds_id}: {i+1}/{len(rows)}  ({time.time()-t0:.0f}s)", flush=True)
        acc = correct / n if n else None
        per_dataset.append({"dataset": ds_id, "n": n, "correct": correct, "accuracy": acc})
        total_correct += correct
        total_n += n
        print(f"  {DATASETS[ds_id]['name']:30s}  n={n:4d}  acc={_fmt(acc)}")

    overall = total_correct / total_n if total_n else None
    print(f"\n  {'OVERALL':30s}  n={total_n:4d}  acc={_fmt(overall)}")
    return {"per_dataset": per_dataset, "overall_accuracy": overall, "n": total_n}


# ── Task 2 & 3: Single-language transcription WER ─────────────────────────────

def task_transcription(label: str, ds_ids: list[str], max_per_dataset: int, seed: int,
                       beam_width: int) -> dict:
    _print_header(f"Task — {label} transcription WER")

    all_refs: list[str] = []
    all_hyps: list[str] = []
    per_dataset: list[dict] = []
    lang_correct = lang_total = 0

    for ds_id in ds_ids:
        rows = load_rows(ds_id, max_per_dataset, seed)
        if not rows:
            continue
        true_lang = DATASETS[ds_id]["lang"]
        ds_refs, ds_hyps = [], []
        ds_lang_correct = 0
        t0 = time.time()
        for i, row in enumerate(rows):
            ref_norm = normalize_text(row["sentence"])
            if not ref_norm:
                continue
            try:
                audio = load_audio(row["audio_path"])
                pred_lang, text, _ = run_hybrid(audio, beam_width=beam_width)
                hyp_norm = normalize_text(text or "")
                ds_refs.append(ref_norm)
                ds_hyps.append(hyp_norm)
                if pred_lang == true_lang:
                    ds_lang_correct += 1
            except Exception as e:
                print(f"    [warn] {row['audio_path'].name}: {e}")
            if (i + 1) % 50 == 0:
                print(f"    {ds_id}: {i+1}/{len(rows)}  ({time.time()-t0:.0f}s)", flush=True)

        wer, cer = _wer_cer(ds_refs, ds_hyps)
        n = len(ds_refs)
        lang_acc = ds_lang_correct / n if n else None
        per_dataset.append({
            "dataset": ds_id, "n": n,
            "wer": wer, "cer": cer,
            "lang_accuracy": lang_acc,
        })
        all_refs.extend(ds_refs)
        all_hyps.extend(ds_hyps)
        lang_correct += ds_lang_correct
        lang_total   += n
        print(f"  {DATASETS[ds_id]['name']:30s}  n={n:4d}  "
              f"WER={_fmt(wer)}  CER={_fmt(cer)}  lang_acc={_fmt(lang_acc)}")

    agg_wer, agg_cer = _wer_cer(all_refs, all_hyps)
    overall_lang_acc = lang_correct / lang_total if lang_total else None
    print(f"\n  {'OVERALL':30s}  n={lang_total:4d}  "
          f"WER={_fmt(agg_wer)}  CER={_fmt(agg_cer)}  lang_acc={_fmt(overall_lang_acc)}")

    return {
        "per_dataset":     per_dataset,
        "aggregate_wer":   agg_wer,
        "aggregate_cer":   agg_cer,
        "lang_accuracy":   overall_lang_acc,
        "n":               lang_total,
    }


# ── Task 4: Mixed-language transcription ──────────────────────────────────────

def task_mixed(fry_ds_ids: list[str], nld_ds_ids: list[str],
               max_per_lang: int, seed: int, beam_width: int) -> dict:
    _print_header("Task 4 — Mixed-language transcription")

    rng = random.Random(seed)
    rows: list[dict] = []
    for ds_id in fry_ds_ids:
        rows.extend(load_rows(ds_id, max_per_lang, seed))
    for ds_id in nld_ds_ids:
        rows.extend(load_rows(ds_id, max_per_lang, seed))
    rng.shuffle(rows)

    if not rows:
        print("  No rows available.")
        return {}

    all_refs: list[str] = []
    all_hyps: list[str] = []
    fry_refs, fry_hyps = [], []
    nld_refs, nld_hyps = [], []
    lang_correct = 0
    t0 = time.time()

    for i, row in enumerate(rows):
        ref_norm = normalize_text(row["sentence"])
        if not ref_norm:
            continue
        try:
            audio = load_audio(row["audio_path"])
            pred_lang, text, _ = run_hybrid(audio, beam_width=beam_width)
            hyp_norm = normalize_text(text or "")
            all_refs.append(ref_norm)
            all_hyps.append(hyp_norm)
            if pred_lang == row["lang"]:
                lang_correct += 1
            if row["lang"] == "fry":
                fry_refs.append(ref_norm)
                fry_hyps.append(hyp_norm)
            else:
                nld_refs.append(ref_norm)
                nld_hyps.append(hyp_norm)
        except Exception as e:
            print(f"    [warn] {row['audio_path'].name}: {e}")
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(rows)}  ({time.time()-t0:.0f}s)", flush=True)

    n = len(all_refs)
    lang_acc = lang_correct / n if n else None
    agg_wer, agg_cer       = _wer_cer(all_refs, all_hyps)
    fry_wer, fry_cer       = _wer_cer(fry_refs, fry_hyps)
    nld_wer, nld_cer       = _wer_cer(nld_refs, nld_hyps)

    print(f"  n={n}  lang_accuracy={_fmt(lang_acc)}")
    print(f"  Overall WER={_fmt(agg_wer)}  CER={_fmt(agg_cer)}")
    print(f"  Frisian WER={_fmt(fry_wer)}  CER={_fmt(fry_cer)}  (n={len(fry_refs)})")
    print(f"  Dutch   WER={_fmt(nld_wer)}  CER={_fmt(nld_cer)}  (n={len(nld_refs)})")

    return {
        "n":             n,
        "lang_accuracy": lang_acc,
        "aggregate_wer": agg_wer,
        "aggregate_cer": agg_cer,
        "fry_wer":       fry_wer,
        "fry_cer":       fry_cer,
        "nld_wer":       nld_wer,
        "nld_cer":       nld_cer,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the TINA transcription pipeline.")
    parser.add_argument(
        "--tasks", nargs="+",
        choices=["lang-id", "fry", "nld", "mixed"],
        default=["lang-id", "fry", "nld", "mixed"],
        help="Which tasks to run (default: all)",
    )
    parser.add_argument(
        "--max-samples", type=int, default=200,
        help="Max samples per dataset per task (0 = all, default: 200)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--beam-width", type=int, default=10)
    parser.add_argument("--out", type=str, default="", help="Save results as JSON to this path")
    args = parser.parse_args()

    t_start = time.time()
    startup(args.beam_width)

    results: dict = {}

    if "lang-id" in args.tasks:
        results["lang_id"] = task_lang_id(
            TASK_DATASETS["lang-id"], args.max_samples, args.seed
        )

    if "fry" in args.tasks:
        results["fry"] = task_transcription(
            "Frisian", TASK_DATASETS["fry"], args.max_samples, args.seed, args.beam_width
        )

    if "nld" in args.tasks:
        results["nld"] = task_transcription(
            "Dutch", TASK_DATASETS["nld"], args.max_samples, args.seed, args.beam_width
        )

    if "mixed" in args.tasks:
        mixed_fry = [d for d in TASK_DATASETS["mixed"] if DATASETS[d]["lang"] == "fry"]
        mixed_nld = [d for d in TASK_DATASETS["mixed"] if DATASETS[d]["lang"] == "nld"]
        results["mixed"] = task_mixed(
            mixed_fry, mixed_nld, args.max_samples, args.seed, args.beam_width
        )

    elapsed = time.time() - t_start
    h, m = divmod(int(elapsed), 3600)
    m, s = divmod(m, 60)
    print(f"\n{'─' * 60}")
    print(f"  Done in {h:02d}:{m:02d}:{s:02d}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"  Results saved to {args.out}")


if __name__ == "__main__":
    main()
