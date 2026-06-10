from pathlib import Path

import librosa


def load_audio(path: Path, target_sr: int = 16000):
    audio, sr = librosa.load(str(path), sr=target_sr, mono=True)
    return audio, sr
