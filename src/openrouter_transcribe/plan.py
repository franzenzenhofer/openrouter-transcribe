"""Pure planning logic: where to cut, and how audio time maps to clock time."""

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from itertools import pairwise

import numpy as np
from numpy.typing import NDArray

from openrouter_transcribe.config import Source


@dataclass(frozen=True)
class Chunk:
    """One slice of a source recording, in seconds of that source's audio."""

    index: int
    source: str
    start: float
    end: float
    wall_start: str
    wall_end: str

    @property
    def name(self) -> str:
        return f"{self.index:03d}"

    @property
    def seconds(self) -> float:
        return self.end - self.start

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def target_cuts(duration: float, target: float) -> list[float]:
    """Evenly spaced cut points that keep every chunk at or below the target."""
    count = max(1, math.ceil(duration / target))
    return [duration * step / count for step in range(1, count)]


def quietest_offset(samples: NDArray[np.float32], rate: int, window_seconds: float) -> float:
    """Centre (seconds) of the lowest-energy window, so cuts fall between words."""
    window = int(rate * window_seconds)
    if samples.size < window:
        raise ValueError(f"need at least {window} samples, got {samples.size}")
    energy = samples.astype(np.float64) ** 2
    cumulative = np.concatenate(([0.0], np.cumsum(energy)))
    window_sums = cumulative[window:] - cumulative[:-window]
    return (int(np.argmin(window_sums)) + window / 2) / rate


def wall_clock(source: Source, audio_seconds: float, audio_total: float) -> datetime:
    """Clock time of a position, interpolated across the source's wall-clock span."""
    return source.wall_start + timedelta(seconds=audio_seconds * source.wall_seconds / audio_total)


def build_chunks(source: Source, cuts: list[float], total: float, first: int) -> list[Chunk]:
    """Chunks covering the whole source with no gap and no overlap."""
    bounds = [0.0, *cuts, total]
    if bounds != sorted(bounds) or len(set(bounds)) != len(bounds):
        raise ValueError(f"cut points for {source.key} are not strictly ascending: {cuts}")
    return [
        Chunk(index=first + offset, source=source.key, start=round(start, 3), end=round(end, 3),
              wall_start=wall_clock(source, start, total).isoformat(timespec="seconds"),
              wall_end=wall_clock(source, end, total).isoformat(timespec="seconds"))
        for offset, (start, end) in enumerate(pairwise(bounds))
    ]


def assert_full_coverage(chunks: list[Chunk], totals: dict[str, float]) -> None:
    """Every second of every source belongs to exactly one chunk."""
    for key, total in totals.items():
        mine = [chunk for chunk in chunks if chunk.source == key]
        if not mine or mine[0].start != 0.0 or abs(mine[-1].end - total) > 0.01:
            raise ValueError(f"source {key}: chunks do not span 0..{total}")
        for before, after in pairwise(mine):
            if before.end != after.start:
                raise ValueError(f"source {key}: gap or overlap at {before.end}/{after.start}")


def format_clock(seconds: float) -> str:
    """"MM:SS" (minutes may exceed 59) for a number of seconds."""
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def turn_ends(starts: list[float], chunk_seconds: float) -> list[float]:
    """A turn lasts until the next turn starts; the last one until the chunk ends."""
    return [*starts[1:], chunk_seconds]

