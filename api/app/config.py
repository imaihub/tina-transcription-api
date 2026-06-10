import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Required: base directory from which audio filenames are resolved.
# The API only accepts filenames relative to this directory.
AUDIO_BASE_DIR = Path(os.getenv("AUDIO_BASE_DIR", ""))

API_KEY     = os.getenv("API_KEY", "")
HF_TOKEN    = os.getenv("HF_TOKEN", "")
MODEL_CACHE = os.getenv("MODEL_CACHE_DIR", None)

# Required: directory containing the finetuned adapter files.
# Expected files: adapter.fry.safetensors and adapter.nld.safetensors.
ADAPTER_DIR = os.getenv("ADAPTER_DIR", "")

# Required: shared KenLM ARPA file (trained on both Frisian and Dutch).
KENLM_MODEL_PATH = Path(os.getenv("KENLM_MODEL_PATH", ""))

# Required: trained language-ID classifier (.pkl produced by LANG_ID_VM).
LANG_ID_MODEL_PATH = os.getenv("LANG_ID_MODEL_PATH", "")

# Dataset paths (used by the evaluation script)
CV_FRY_CLEAN_DIR      = os.getenv("CV_FRY_CLEAN_DIR",      "")
CV_FRY_AUDIO_DIR      = os.getenv("CV_FRY_AUDIO_DIR",      "")
CV_NL_CLEAN_DIR       = os.getenv("CV_NL_CLEAN_DIR",       "")
CV_NL_AUDIO_DIR       = os.getenv("CV_NL_AUDIO_DIR",       "")
RADBOUD_FRY_CLEAN_DIR = os.getenv("RADBOUD_FRY_CLEAN_DIR", "")
RADBOUD_FRY_AUDIO_DIR = os.getenv("RADBOUD_FRY_AUDIO_DIR", "")
RADBOUD_NL_CLEAN_DIR  = os.getenv("RADBOUD_NL_CLEAN_DIR",  "")
RADBOUD_NL_AUDIO_DIR  = os.getenv("RADBOUD_NL_AUDIO_DIR",  "")
GEMEENTE_FRY_CLEAN_DIR = os.getenv("GEMEENTE_FRY_CLEAN_DIR", "")
GEMEENTE_FRY_AUDIO_DIR = os.getenv("GEMEENTE_FRY_AUDIO_DIR", "")
GEMEENTE_NL_CLEAN_DIR  = os.getenv("GEMEENTE_NL_CLEAN_DIR",  "")
GEMEENTE_NL_AUDIO_DIR  = os.getenv("GEMEENTE_NL_AUDIO_DIR",  "")

# Transcription settings (fixed per deployment)
MIN_SEGMENT_DUR = float(os.getenv("MIN_SEGMENT_DUR", "0.3"))
PAD_S           = float(os.getenv("PAD_S",           "0.1"))
BEAM_WIDTH      = int(os.getenv("BEAM_WIDTH",        "100"))
