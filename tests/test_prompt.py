"""Listening rules: a section without speech is written down explicitly, never as no turns."""

from pathlib import Path

import pytest

from openrouter_transcribe.config import load
from openrouter_transcribe.listen import check_no_speech
from openrouter_transcribe.prompt import NO_SPEECH, system_prompt

EXAMPLE = Path(__file__).parent.parent / "examples" / "transcript.example.toml"


def test_rules_tell_the_listener_how_to_write_a_section_without_speech() -> None:
    # 2026-10-15 workshop, chunk 013 (12:52-13:00): empty room at lunch, -60 dB mean. The
    # listener answered no turns three times and the run failed; it needs a way to say so.
    project = load(EXAMPLE)
    prompt = system_prompt(project)
    assert "Never return an empty list of turns" in prompt
    assert f'speaker "{project.unclear}"' in prompt
    assert f'"{NO_SPEECH}"' in prompt
    assert "{" not in prompt.split("Rules:")[1]


def test_no_speech_is_believed_only_when_the_draft_heard_almost_nothing() -> None:
    silence = [{"start": "00:00", "speaker": "Unclear", "basis": "guess", "text": NO_SPEECH}]
    check_no_speech(silence, 0)  # chunk 013, lunch break: Deepgram heard nothing
    # chunk 001: the second listener said "There is no audio", Deepgram heard 1186 words
    with pytest.raises(ValueError, match="draft heard 1186 words"):
        check_no_speech(silence, 1186)


def test_no_speech_next_to_real_turns_is_refused() -> None:
    turns = [{"start": "00:00", "speaker": "Franz", "basis": "voice", "text": "So."},
             {"start": "01:00", "speaker": "Unclear", "basis": "guess", "text": NO_SPEECH}]
    with pytest.raises(ValueError, match="next to other turns"):
        check_no_speech(turns, 400)
