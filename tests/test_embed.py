"""Audio helpers of the embedder that need no model."""

import numpy as np

from openrouter_transcribe.config import Voices
from openrouter_transcribe.embed import MIN_SECONDS, RATE, loudness_dbfs, padded, windows


def test_short_audio_is_repeated_to_the_minimum_length() -> None:
    samples = np.arange(100, dtype=np.float32)
    result = padded(samples)
    assert result.size == int(MIN_SECONDS * RATE)
    assert result[100] == samples[0]


def test_loudness_of_silence_and_full_scale() -> None:
    assert loudness_dbfs(np.zeros(RATE, dtype=np.float32)) == -120.0
    assert abs(loudness_dbfs(np.ones(RATE, dtype=np.float32))) < 1e-6


def test_silent_windows_are_skipped() -> None:
    voices = Voices(window_seconds=1.0, hop_seconds=1.0, silence_dbfs=-40.0)
    audio = np.concatenate([np.zeros(RATE), np.full(RATE, 0.1), np.zeros(RATE)])
    found = windows(audio.astype(np.float32), voices)
    assert [start for start, _ in found] == [1.0]
