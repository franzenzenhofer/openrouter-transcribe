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


def test_speaker_stats_count_words_turns_and_minutes() -> None:
    from openrouter_transcribe.assemble import speaker_stats
    rows = [{"speaker": "Ana", "words": 3, "start": "2026-01-01T09:00:00+01:00",
             "end": "2026-01-01T09:01:00+01:00"},
            {"speaker": "Ana", "words": 2, "start": "2026-01-01T09:01:00+01:00",
             "end": "2026-01-01T09:01:30+01:00"}]
    assert speaker_stats(rows) == {"Ana": {"words": 5, "turns": 2, "minutes": 1.5}}


def test_enrolment_note_says_who_had_a_voice_sample() -> None:
    from openrouter_transcribe.assemble import enrolment_note
    from openrouter_transcribe.config import Person, Sample

    franz = Person(name="Franz", description="trainer", samples=(Sample("am", 130.0, 155.0),))
    guest = Person(name="Ben", description="participant")
    assert enrolment_note([franz]) == "enrolled from each person's own voice samples"
    # 2026-10-14: recording started after the intro round, only the trainer had a sample
    note = enrolment_note([franz, guest])
    assert note.startswith("enrolled from voice samples of Franz; the other 1 people")
