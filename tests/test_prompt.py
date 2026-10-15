"""Listening rules: a section without speech is written down explicitly, never as no turns."""

from pathlib import Path

from openrouter_transcribe.config import load
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
