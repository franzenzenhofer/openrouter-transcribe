"""Draft results: an empty draft on quiet audio is stored, a malformed answer fails loud."""

import pytest

from openrouter_transcribe.draft import draft_summary


def test_draft_with_words_reports_the_word_count() -> None:
    assert draft_summary("012", "openai/whisper-large-v3", {"text": "hallo und willkommen"}) == \
        "012 openai/whisper-large-v3: 3 words"


def test_empty_draft_on_quiet_audio_is_a_result_not_a_failure() -> None:
    # 2026-10-14 workshop, chunk 036: participants working, trainer away from the microphone;
    # deepgram/nova-3 returned "" while whisper heard 818 words. That must not stop the run.
    assert draft_summary("036", "deepgram/nova-3", {"text": "  "}) == \
        "036 deepgram/nova-3: 0 words (empty draft, quiet audio)"


def test_answer_without_text_field_fails_loud() -> None:
    with pytest.raises(RuntimeError, match="without a text field"):
        draft_summary("036", "deepgram/nova-3", {"error": "bad request"})
