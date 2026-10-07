"""Speaker naming rules on small synthetic voice vectors (test data, not mocks)."""

import numpy as np

from openrouter_transcribe.config import Voices
from openrouter_transcribe.speakers import Turn, change_points, decide, enrol, unit

VOICES = Voices(min_similarity=0.5, min_margin=0.1, short_turn_seconds=2.5, change_seconds=4.0)
LABELS = ("Unclear", "Several")
ANNA = unit(np.array([1.0, 0.0, 0.0], dtype=np.float32))
BEN = unit(np.array([0.0, 1.0, 0.0], dtype=np.float32))
CENTROIDS = {"Anna": ANNA, "Ben": BEN}


def turn(heard: str, vector: np.ndarray, seconds: float = 10.0, basis: str = "voice") -> Turn:
    return Turn(key="001:0", heard=heard, basis=basis, seconds=seconds, vector=unit(vector))


def test_voice_and_listener_agree() -> None:
    verdict = decide(turn("Anna", np.array([0.9, 0.1, 0.0])), CENTROIDS, VOICES, LABELS)
    assert (verdict.speaker, verdict.decided_by) == ("Anna", "agree")


def test_clear_voice_overrides_a_listener_guess() -> None:
    verdict = decide(turn("Anna", np.array([0.1, 0.9, 0.0])), CENTROIDS, VOICES, LABELS)
    assert (verdict.speaker, verdict.decided_by) == ("Ben", "voice")
    assert verdict.flags == ("listener heard Anna",)


def test_named_turn_needs_a_strong_voice_to_be_overridden() -> None:
    weak = np.array([0.55, 0.7, 0.45])
    verdict = decide(turn("Anna", weak, basis="named"), CENTROIDS, VOICES, LABELS)
    assert verdict.speaker == "Anna"
    assert verdict.decided_by == "listener"


def test_short_turn_keeps_the_listener_label() -> None:
    verdict = decide(turn("Anna", np.array([0.0, 1.0, 0.0]), seconds=1.0), CENTROIDS, VOICES,
                     LABELS)
    assert verdict.speaker == "Anna"


def test_unknown_voice_without_listener_name_is_unclear() -> None:
    verdict = decide(turn("Unclear", np.array([0.0, 0.0, 1.0])), CENTROIDS, VOICES, LABELS)
    assert verdict.speaker == "Unclear"


def test_several_stays_several() -> None:
    verdict = decide(turn("Several", np.array([1.0, 0.0, 0.0])), CENTROIDS, VOICES, LABELS)
    assert verdict.speaker == "Several"


def test_enrol_adds_a_person_without_samples_from_named_turns() -> None:
    carl = np.array([0.0, 0.0, 1.0])
    turns = [turn("Carl", carl, basis="named"), turn("Anna", np.array([1.0, 0.1, 0.0]))]
    centroids = enrol({"Anna": [ANNA], "Ben": [BEN]}, turns, rounds=2)
    assert set(centroids) == {"Anna", "Ben", "Carl"}
    assert float(centroids["Carl"] @ unit(carl.astype(np.float32))) > 0.99


def test_change_point_inside_a_long_turn() -> None:
    times = [0.0, 1.5, 3.0, 4.5, 6.0, 7.5, 9.0]
    vectors = [ANNA, ANNA, ANNA, BEN, BEN, BEN, BEN]
    assert change_points(times, vectors, "Anna", CENTROIDS, VOICES) == [(4.5, "Ben")]
