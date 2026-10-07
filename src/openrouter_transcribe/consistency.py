"""An independent check of the voice naming: cluster the long turns without any names and see
whether the clusters coincide with the names given. High agreement means the names follow real
voice differences; low agreement means two people are being mixed up."""

from collections import Counter
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

SEEDS = 20
ITERATIONS = 50


@dataclass(frozen=True)
class Consistency:
    agreement: float
    clusters: list[dict[str, int]]


def spherical_kmeans(vectors: NDArray[np.float32], k: int, seed: int) -> tuple[NDArray[np.int64],
                                                                              float]:
    """Labels and mean cosine to the own centroid (higher = tighter clusters)."""
    rng = np.random.default_rng(seed)
    centres = vectors[rng.choice(len(vectors), k, replace=False)]
    labels = np.zeros(len(vectors), dtype=np.int64)
    for _ in range(ITERATIONS):
        labels = np.argmax(vectors @ centres.T, axis=1)
        centres = np.stack([vectors[labels == j].mean(axis=0) if (labels == j).any()
                            else centres[j] for j in range(k)])
        centres /= np.linalg.norm(centres, axis=1, keepdims=True)
    return labels, float(np.mean(np.max(vectors @ centres.T, axis=1)))


def check(vectors: list[NDArray[np.float32]], names: list[str]) -> Consistency:
    """k = number of distinct names; best of SEEDS runs; agreement via each cluster's majority."""
    k = len(set(names))
    if k < 2 or len(vectors) < 2 * k:
        return Consistency(agreement=1.0, clusters=[dict(Counter(names))])
    stacked = np.stack(vectors)
    labels, _ = max((spherical_kmeans(stacked, k, seed) for seed in range(SEEDS)),
                    key=lambda result: result[1])
    clusters = [dict(Counter(name for name, label in zip(names, labels, strict=True)
                             if label == j)) for j in range(k)]
    majority = sum(max(cluster.values(), default=0) for cluster in clusters)
    return Consistency(agreement=majority / len(names), clusters=clusters)
