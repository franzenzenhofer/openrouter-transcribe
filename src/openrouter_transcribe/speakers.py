"""Pure speaker-naming logic on voice embeddings (unit vectors, cosine = dot product).

A turn is named by the person whose voice centroid it is closest to, if that is clear enough;
otherwise the listening model's label stands, or the turn is marked unclear. Centroids start
from the enrolment samples and are re-estimated from turns where voice and listener agree.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from openrouter_transcribe.config import Voices

Vector = NDArray[np.float32]
TRAINING_MIN_SECONDS = 3.0
TRAINING_CAP_SECONDS = 30.0
CONFIDENT_SIMILARITY = 0.6


@dataclass(frozen=True)
class Turn:
    """What the voices stage knows about one turn."""

    key: str
    heard: str
    basis: str
    seconds: float
    vector: Vector


@dataclass(frozen=True)
class Verdict:
    speaker: str
    decided_by: str
    best: str
    similarity: float
    margin: float
    flags: tuple[str, ...]


def unit(vector: Vector) -> Vector:
    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        raise ValueError("zero vector has no direction")
    return (vector / norm).astype(np.float32)


def centroid(vectors: list[Vector], weights: list[float]) -> Vector:
    stacked = np.stack(vectors)
    return unit((stacked * np.asarray(weights, dtype=np.float32)[:, None]).sum(axis=0))


def ranking(vector: Vector, centroids: dict[str, Vector]) -> list[tuple[str, float]]:
    """People by similarity, best first."""
    scores = [(name, float(vector @ centre)) for name, centre in centroids.items()]
    return sorted(scores, key=lambda item: item[1], reverse=True)


def best_and_margin(vector: Vector, centroids: dict[str, Vector]) -> tuple[str, float, float]:
    ranked = ranking(vector, centroids)
    runner_up = ranked[1][1] if len(ranked) > 1 else -1.0
    return ranked[0][0], ranked[0][1], ranked[0][1] - runner_up


def decide(turn: Turn, centroids: dict[str, Vector], voices: Voices,
           labels: tuple[str, str]) -> Verdict:
    """`labels` = (unclear, several). The rules are documented in the README."""
    unclear, several = labels
    best, similarity, margin = best_and_margin(turn.vector, centroids)
    known = turn.heard in centroids
    clear = similarity >= voices.min_similarity and margin >= voices.min_margin
    strong = similarity >= voices.min_similarity and margin >= 2 * voices.min_margin

    def verdict(speaker: str, decided_by: str, *flags: str) -> Verdict:
        return Verdict(speaker, decided_by, best, round(similarity, 3), round(margin, 3), flags)

    if turn.heard == several:
        return verdict(several, "listener")
    if turn.seconds < voices.short_turn_seconds:
        if known:
            return verdict(turn.heard, "listener")
        return verdict(best, "voice") if strong else verdict(unclear, "none")
    if known and best == turn.heard:
        return verdict(best, "agree")
    if known and turn.basis == "named" and not strong:
        return verdict(turn.heard, "listener", f"voice suggests {best}")
    if clear:
        flags = (f"listener heard {turn.heard}",) if known else ()
        return verdict(best, "voice", *flags)
    if known:
        return verdict(turn.heard, "listener", "voice unclear")
    return verdict(unclear, "none", "voice unclear")


def retrain(turns: list[Turn], centroids: dict[str, Vector],
            anchors: dict[str, list[Vector]]) -> dict[str, Vector]:
    """New centroids from enrolment samples plus turns where voice and listener agree."""
    vectors: dict[str, list[Vector]] = {name: list(found) for name, found in anchors.items()}
    weights: dict[str, list[float]] = {name: [TRAINING_CAP_SECONDS] * len(found)
                                       for name, found in anchors.items()}
    for turn in turns:
        if turn.seconds < TRAINING_MIN_SECONDS or turn.heard not in centroids:
            continue
        best, similarity, _ = best_and_margin(turn.vector, centroids)
        trusted = turn.basis != "guess" or similarity >= CONFIDENT_SIMILARITY
        if best == turn.heard and trusted:
            vectors.setdefault(best, []).append(turn.vector)
            weights.setdefault(best, []).append(min(turn.seconds, TRAINING_CAP_SECONDS))
    return {name: centroid(vectors[name], weights[name]) if vectors.get(name) else centre
            for name, centre in centroids.items()}


def enrol(anchors: dict[str, list[Vector]], turns: list[Turn], rounds: int) -> dict[str, Vector]:
    """Centroids for everyone with samples; people without samples join from named turns."""
    centroids = {name: centroid(found, [1.0] * len(found))
                 for name, found in anchors.items() if found}
    named: dict[str, list[Vector]] = {}
    for turn in turns:
        if turn.basis == "named" and turn.heard not in centroids \
                and turn.seconds >= TRAINING_MIN_SECONDS:
            named.setdefault(turn.heard, []).append(turn.vector)
    centroids |= {name: centroid(found, [1.0] * len(found)) for name, found in named.items()}
    for _ in range(rounds):
        centroids = retrain(turns, centroids, anchors)
    return centroids


def change_points(times: list[float], vectors: list[Vector], speaker: str,
                  centroids: dict[str, Vector], voices: Voices) -> list[tuple[float, str]]:
    """Runs of windows inside one turn that clearly belong to someone else."""
    found: list[tuple[float, str]] = []
    run_start, run_name = 0.0, ""
    for time, vector in zip([*times, float("inf")], [*vectors, None], strict=True):
        name = ""
        if vector is not None:
            best, similarity, margin = best_and_margin(vector, centroids)
            if best != speaker and similarity >= voices.min_similarity \
                    and margin >= voices.min_margin:
                name = best
        if name != run_name:
            if run_name and time - run_start >= voices.change_seconds:
                found.append((run_start, run_name))
            run_start, run_name = time, name
    return found
