"""Reading layout of the Markdown transcript."""

from openrouter_transcribe.assemble import merged


def test_consecutive_turns_of_one_speaker_become_one_paragraph() -> None:
    rows = [{"speaker": "Ana", "text": "One.", "start": "a"},
            {"speaker": "Ana", "text": "Two.", "start": "b"},
            {"speaker": "Ben", "text": "Three.", "start": "c"}]
    result = merged(rows)
    assert [(row["speaker"], row["text"], row["start"]) for row in result] == [
        ("Ana", "One. Two.", "a"), ("Ben", "Three.", "c")]
    assert rows[0]["text"] == "One."
