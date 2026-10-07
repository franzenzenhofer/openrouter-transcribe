"""ffmpeg helpers. Originals are only ever opened as ffmpeg inputs, never written."""

import hashlib
import subprocess
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

HASH_BLOCK_BYTES = 1 << 20
CHUNK_SAMPLE_RATE = 16000
CHUNK_BITRATE = "48k"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(HASH_BLOCK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def run_ffmpeg(arguments: list[str]) -> bytes:
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", *arguments]
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(command)}\n{result.stderr.decode()}")
    return result.stdout


def probe_seconds(path: Path) -> float:
    command = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)]
    result = subprocess.run(command, capture_output=True, check=True, text=True)
    return float(result.stdout.strip())


def read_pcm(path: Path, start: float, seconds: float, rate: int) -> NDArray[np.float32]:
    """Decode a mono slice to float samples in [-1, 1]."""
    raw = run_ffmpeg(["-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", str(path),
                      "-ar", str(rate), "-ac", "1", "-f", "f32le", "-"])
    return np.frombuffer(raw, dtype=np.float32)


def cut_mp3(source: Path, start: float, end: float, target: Path) -> None:
    """Write a 16 kHz mono MP3 slice; atomic, so a crash never leaves half a file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".partial.mp3")
    run_ffmpeg(["-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(source),
                "-ar", str(CHUNK_SAMPLE_RATE), "-ac", "1", "-b:a", CHUNK_BITRATE, str(partial)])
    partial.replace(target)
