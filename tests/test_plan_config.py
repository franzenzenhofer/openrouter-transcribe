"""Cut planning, coverage and the project file."""

import dataclasses
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from openrouter_transcribe.config import Source, load, parse_clock
from openrouter_transcribe.plan import (
    assert_full_coverage,
    build_chunks,
    quietest_offset,
    target_cuts,
)

VIENNA = ZoneInfo("Europe/Vienna")
SOURCE = Source(key="a", title="A", path=Path("a.flac"), sha256="0",
                wall_start=datetime(2026, 1, 1, 9, 0, tzinfo=VIENNA),
                wall_end=datetime(2026, 1, 1, 10, 0, tzinfo=VIENNA))
EXAMPLE = Path(__file__).parent.parent / "examples" / "transcript.example.toml"


def test_cuts_keep_chunks_at_or_below_target() -> None:
    assert target_cuts(1000.0, 480.0) == pytest.approx([1000 / 3, 2000 / 3])
    assert target_cuts(400.0, 480.0) == []


def test_quietest_offset_finds_the_silent_gap() -> None:
    rate = 8000
    samples = np.full(rate * 3, 0.5, dtype=np.float32)
    samples[rate:rate + rate // 2] = 0.0
    assert quietest_offset(samples, rate, 0.4) == pytest.approx(1.25, abs=0.06)


def test_chunks_cover_the_source_and_map_to_clock_time() -> None:
    chunks = build_chunks(SOURCE, [1800.0], 3600.0, first=1)
    assert_full_coverage(chunks, {"a": 3600.0})
    assert chunks[1].wall_start == "2026-01-01T09:30:00+01:00"


def test_a_gap_between_chunks_is_refused() -> None:
    chunks = build_chunks(SOURCE, [1800.0], 3600.0, first=1)
    broken = [chunks[0], dataclasses.replace(chunks[1], start=1801.0)]
    with pytest.raises(ValueError, match="gap or overlap"):
        assert_full_coverage(broken, {"a": 3600.0})


def test_parse_clock() -> None:
    assert parse_clock("1:02:03") == 3723
    assert parse_clock("07:25") == 445


def test_example_project_file_loads() -> None:
    project = load(EXAMPLE)
    assert project.names[0] == "Ana"
    assert project.people[0].samples[0].start == 65.0
    assert project.voices.min_margin > 0
