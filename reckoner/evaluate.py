"""Score a resolution against labelled data (pairwise precision and recall).

Pairwise metrics are the standard yardstick for entity resolution: every pair of
records is either in the same predicted cluster or not, and either truly the same
entity or not.

    precision = correct same-entity pairs / pairs reckoner put together
    recall    = correct same-entity pairs / pairs that truly belong together

    >>> from reckoner.evaluate import pairwise_scores
    >>> s = pairwise_scores([[0, 1], [2], [3]], ["ge", "ge", "ge", "boeing"])
    >>> round(s.precision, 2), round(s.recall, 2)
    (1.0, 0.33)
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Hashable, Iterable, Sequence

__all__ = ["PairwiseScores", "pairwise_scores"]


def _pairs(n: int) -> int:
    return n * (n - 1) // 2


@dataclass(frozen=True)
class PairwiseScores:
    """Pair counts and the derived precision, recall and F1."""

    true_positives: int
    predicted_pairs: int
    gold_pairs: int

    @property
    def false_positives(self) -> int:
        return self.predicted_pairs - self.true_positives

    @property
    def false_negatives(self) -> int:
        return self.gold_pairs - self.true_positives

    @property
    def precision(self) -> float:
        """1.0 when nothing was merged (no merge can be wrong)."""
        return self.true_positives / self.predicted_pairs if self.predicted_pairs else 1.0

    @property
    def recall(self) -> float:
        """1.0 when the gold data has no pairs to find."""
        return self.true_positives / self.gold_pairs if self.gold_pairs else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def pairwise_scores(clusters: Iterable[Sequence[int]],
                    labels: Sequence[Hashable]) -> PairwiseScores:
    """Compare predicted clusters with gold labels.

    Args:
        clusters: Predicted clusters as lists of record indices, for example
            ``[c.members for c in resolve(names)]``. Every index from 0 to
            ``len(labels) - 1`` must appear exactly once.
        labels: The true entity of each record (any hashable value, e.g. an LEI).

    Raises:
        ValueError: if the clusters do not partition the label indices.
    """
    cluster_of = [-1] * len(labels)
    for ci, members in enumerate(clusters):
        for i in members:
            if not 0 <= i < len(labels):
                raise ValueError(f"cluster index {i} is outside 0..{len(labels) - 1}")
            if cluster_of[i] != -1:
                raise ValueError(f"record {i} appears in more than one cluster")
            cluster_of[i] = ci
    if -1 in cluster_of:
        raise ValueError(f"record {cluster_of.index(-1)} is in no cluster")

    by_cell = Counter(zip(cluster_of, labels))
    return PairwiseScores(
        true_positives=sum(_pairs(n) for n in by_cell.values()),
        predicted_pairs=sum(_pairs(n) for n in Counter(cluster_of).values()),
        gold_pairs=sum(_pairs(n) for n in Counter(labels).values()),
    )
