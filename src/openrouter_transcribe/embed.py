"""Local voice embeddings with sherpa-onnx (no account, no gated models, nothing leaves the
machine). Several models are averaged: the dot product of two outputs is the mean cosine."""

import math
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import sherpa_onnx
from numpy.typing import NDArray

from openrouter_transcribe.config import Voices
from openrouter_transcribe.speakers import Vector, unit

MODEL_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
             "speaker-recongition-models/{name}")
MODEL_DIR = Path.home() / ".cache" / "openrouter-transcribe" / "models"
RATE = 16000
MIN_SECONDS = 1.0
THREADS_PER_MODEL = 4

Samples = NDArray[np.float32]


def model_path(name: str) -> Path:
    """Download a model once into the user cache."""
    target = MODEL_DIR / name
    if not target.exists():
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".partial")
        urllib.request.urlretrieve(MODEL_URL.format(name=name), partial)
        partial.replace(target)
    return target


def padded(samples: Samples) -> Samples:
    """Very short turns are repeated up to MIN_SECONDS; the extractors need some audio."""
    need = int(MIN_SECONDS * RATE)
    if samples.size == 0:
        raise ValueError("no audio to embed")
    if samples.size >= need:
        return samples
    return np.tile(samples, math.ceil(need / samples.size))[:need]


def loudness_dbfs(samples: Samples) -> float:
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64))))) if samples.size else 0.0
    return 20 * math.log10(rms) if rms > 0 else -120.0


class Embedder:
    """One extractor per model, run side by side; use one Embedder per thread."""

    def __init__(self, voices: Voices) -> None:
        self.extractors = [sherpa_onnx.SpeakerEmbeddingExtractor(
            sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=str(model_path(name)), num_threads=THREADS_PER_MODEL))
            for name in voices.models]
        self.pool = ThreadPoolExecutor(max_workers=len(self.extractors))

    def _one(self, extractor: object, samples: Samples) -> Vector:
        stream = extractor.create_stream()  # type: ignore[attr-defined]
        stream.accept_waveform(RATE, samples)
        stream.input_finished()
        return unit(np.asarray(extractor.compute(stream), dtype=np.float32))  # type: ignore[attr-defined]

    def embed(self, samples: Samples) -> Vector:
        audio = padded(samples)
        parts = list(self.pool.map(lambda extractor: self._one(extractor, audio),
                                   self.extractors))
        return (np.concatenate(parts) / math.sqrt(len(parts))).astype(np.float32)


def windows(samples: Samples, voices: Voices) -> list[tuple[float, Samples]]:
    """(start second, audio) of every voiced analysis window."""
    size, hop = int(voices.window_seconds * RATE), int(voices.hop_seconds * RATE)
    found = []
    for begin in range(0, max(1, samples.size - size + 1), hop):
        piece = samples[begin:begin + size]
        if loudness_dbfs(piece) >= voices.silence_dbfs:
            found.append((begin / RATE, piece))
    return found
