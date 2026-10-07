"""Turn-start alignment and the reviewer findings."""

from openrouter_transcribe.align import draft_words, refine_start, refined_starts
from openrouter_transcribe.findings import compare, conflicts, gaps, normalize_number

WORDS = draft_words({"words": [
    {"word": "Okay.", "start": 10.2}, {"word": "My", "start": 30.1},
    {"word": "name", "start": 30.4}, {"word": "is", "start": 30.6},
    {"word": "Ben.", "start": 30.8},
]})


def test_start_moves_to_the_first_words() -> None:
    assert refine_start("My name is Ben.", 27.0, WORDS) == 30.1


def test_start_stays_when_the_words_are_too_far_away() -> None:
    assert refine_start("My name is Ben.", 80.0, WORDS) == 80.0


def test_refined_starts_never_go_backwards() -> None:
    starts = refined_starts(["My name is", "Okay."], [29.0, 31.0], WORDS)
    assert starts == [30.1, 31.0]


def test_numbers_compare_across_separators() -> None:
    assert normalize_number("6.544") == normalize_number("6,544") == "6544"
    assert normalize_number("14,3") == "14.3"


def test_compare_flags_unsupported_and_missing_numbers() -> None:
    result = compare("we had 1200 clicks", {"a": "we had 1300 clicks and 42",
                                            "b": "1300 clicks, 42"})
    assert result.unsupported == ["1200"]
    assert result.missing == ["1300", "42"]


def test_gap_where_the_draft_heard_speech() -> None:
    final = [(0.0, 60.0, "word " * 100)]
    reference = [(0.0, 60.0, "word " * 100), (60.0, 120.0, "word " * 80)]
    assert gaps(final, reference, 120.0) == [
        "possible gap 01:00-02:00: 0 words here, 80 in the draft"]


def test_conflict_when_the_second_listener_names_someone_else() -> None:
    text = "this is a long enough turn with more than fifteen words in it for the check ok"
    found = conflicts([(0.0, 20.0, "Anna", text)], [(0.0, "Ben")], {"Anna", "Ben"})
    assert found[0]["second"] == "Ben"
