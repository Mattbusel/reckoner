"""The two-function public API: ``resolve`` and ``match``.

Both are thin, typed wrappers over :class:`reckoner.EntityResolver`. They make the
same decisions (identifiers first, exact normalized names second, conflicting
strong identifiers block a merge, nothing fuzzy) and turn the resolver's receipts
into plain sentences you can show a person.

    >>> from reckoner import resolve, match
    >>> [c.names for c in resolve(["GENERAL ELECTRIC CO", "General Electric Company", "Boeing"])]
    [('GENERAL ELECTRIC CO', 'General Electric Company'), ('Boeing',)]
    >>> m = match("THE SHERWIN-WILLIAMS COMPANY", "Sherwin Williams Co")
    >>> m.matched, m.score
    (True, 0.6)
    >>> match("Meta Platforms, Inc.", "Meta Financial Group, Inc.").score
    0.0
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple, Union

from .resolver import STRONG_IDS, EntityResolver

#: A record is either a bare organization name or a mapping with any of the keys
#: ``name``, ``agency``, ``cik``, ``uei``, ``ein``, ``cage``, ``ticker``, ``domain``,
#: ``source`` and ``state``.
Record = Union[str, Mapping[str, Any]]

__all__ = ["Record", "Cluster", "MatchResult", "resolve", "match"]


@dataclass(frozen=True)
class Cluster:
    """One resolved organization and why its members are together.

    Attributes:
        entity_id: Stable within one call, e.g. ``"ent-0"``.
        canonical_name: The longest member name (the most specific spelling).
        normalized_name: ``canonical_name`` after normalization.
        members: Indices into the input, in input order.
        names: The member names, aligned with ``members``.
        identifiers: Identifiers carried by any member, e.g. ``{"cik": "40545"}``.
        link_confidence: The strongest evidence that merged the members: an
            identifier's confidence (CIK 0.99 ... domain 0.85), 0.60 for an exact
            normalized name, 1.0 for a single record.
        explanations: One sentence per merge into this cluster and per refused
            merge involving one of its members.
    """

    entity_id: str
    canonical_name: str
    normalized_name: str
    members: Tuple[int, ...]
    names: Tuple[str, ...]
    identifiers: Dict[str, str]
    link_confidence: float
    explanations: Tuple[str, ...]

    def __len__(self) -> int:
        return len(self.members)

    def __hash__(self) -> int:
        # ``identifiers`` is a dict, which cannot be hashed, so it is hashed as a
        # sorted tuple of pairs. Equal clusters still hash equal, so clusters can
        # go in a set or be dict keys. Do not change ``identifiers`` in place.
        return hash((self.entity_id, self.canonical_name, self.normalized_name,
                     self.members, self.names, tuple(sorted(self.identifiers.items())),
                     self.link_confidence, self.explanations))


@dataclass(frozen=True)
class MatchResult:
    """Whether two records name the same organization, with the reasons.

    Attributes:
        matched: True when reckoner would merge the two records.
        score: The confidence of the merge (0.85 to 0.99 for a shared identifier,
            0.60 for an exact normalized name), or 0.0 when they do not match.
            It is not a similarity score: there are no partial matches.
        method: ``"id:<name>"`` (for example ``"id:cik"``), ``"name_exact_normalized"``,
            ``"refused"`` (same normalized name, conflicting strong identifier)
            or ``"none"``.
        reasons: Plain sentences explaining the decision.
        normalized: The two normalized names that were compared.
    """

    matched: bool
    score: float
    method: str
    reasons: Tuple[str, ...]
    normalized: Tuple[str, str]

    def __bool__(self) -> bool:
        return self.matched


def _as_record(item: Record) -> Dict[str, Any]:
    if isinstance(item, str):
        return {"name": item}
    if isinstance(item, Mapping):
        return {str(k).strip().lower(): v for k, v in item.items()}
    raise TypeError(f"expected a name (str) or a mapping, got {type(item).__name__}")


def _describe(m: Dict[str, Any]) -> str:
    left = f"#{m['left_index']} {m['left_original']!r}"
    right = f"#{m['right_index']} {m['right_original']!r}"
    if not m["merged"]:
        return f"kept {right} apart from {left}: {m['refusal_reason']}"
    if m["method"].startswith("id:"):
        why = f"shared {m['method'][3:].upper()} {m['normalized']}"
    else:
        why = f"same name after normalization ({m['normalized']!r})"
        extra = [e for e in m["evidence"] if not e.startswith("exact normalized name")]
        if extra:
            why += ", " + ", ".join(extra)
    return f"{right} joined {left}: {why} (confidence {m['confidence']:.2f})"


def resolve(names: Iterable[Record], *, agency: bool = False) -> List[Cluster]:
    """Group names (or records) that refer to the same organization.

    Args:
        names: Organization names, or mappings that may also carry identifiers
            (``{"name": "GENERAL ELECTRIC CO", "cik": "40545"}``). Strings and
            mappings can be mixed.
        agency: Normalize as government agency names (strip "U.S.", expand DoD,
            EPA and similar aliases).

    Returns:
        One :class:`Cluster` per organization, in order of first appearance. Every
        input index appears in exactly one cluster.
    """
    records = [_as_record(n) for n in names]
    result = EntityResolver(agency_mode=agency).resolve(records)
    matches = result["matches"]
    original = [str(r.get("name") or r.get("agency") or "") for r in records]
    clusters: List[Cluster] = []
    for e in sorted(result["entities"], key=lambda e: e["member_indices"][0]):
        members = tuple(e["member_indices"])
        member_set = set(members)
        joins = sorted((m for m in matches if m["merged"] and m["right_index"] in member_set),
                       key=lambda m: (m["right_index"], -m["confidence"]))
        refusals = [m for m in matches if not m["merged"]
                    and (m["left_index"] in member_set or m["right_index"] in member_set)]
        explanations = [_describe(m) for m in joins + refusals]
        if len(members) == 1 and not explanations:
            norm = e["normalized_name"]
            explanations.append(
                f"no other record shares an identifier or the normalized name {norm!r}"
                if norm else "no name and no identifier shared with another record")
        clusters.append(Cluster(
            entity_id=e["entity_id"],
            canonical_name=e["canonical_name"],
            normalized_name=e["normalized_name"],
            members=members,
            names=tuple(original[i] for i in members),
            identifiers=dict(e["identifiers"]),
            link_confidence=float(e["link_confidence"]),
            explanations=tuple(explanations),
        ))
    return clusters


def match(a: Record, b: Record, *, agency: bool = False) -> MatchResult:
    """Decide whether two names (or records) are the same organization.

    The decision is exactly the one :func:`resolve` makes for a pair: a shared
    identifier matches outright; otherwise the names must be identical after
    normalization and must not carry conflicting CIK, UEI, EIN or CAGE values.

    Args:
        a: A name or a record mapping.
        b: A name or a record mapping.
        agency: Normalize as government agency names.

    Returns:
        A :class:`MatchResult`. It is truthy when the two match.
    """
    ra, rb = _as_record(a), _as_record(b)
    resolver = EntityResolver(agency_mode=agency)
    result = resolver.resolve([ra, rb])
    fa, fb = resolver._features(ra), resolver._features(rb)
    normalized = (fa["norm_name"], fb["norm_name"])
    merged = [m for m in result["matches"] if m["merged"]]
    refused = [m for m in result["matches"] if not m["merged"]]

    reasons: List[str] = []
    if merged:
        best = max(merged, key=lambda m: m["confidence"])
        for m in sorted(merged, key=lambda m: -m["confidence"]):
            if m["method"].startswith("id:"):
                reasons.append(f"both carry {m['method'][3:].upper()} {m['normalized']} "
                               f"(confidence {m['confidence']:.2f})")
            else:
                reasons.append(f"names are identical after normalization: {m['normalized']!r} "
                               f"(confidence {m['confidence']:.2f})")
                reasons.extend(e for e in m["evidence"]
                               if not e.startswith("exact normalized name"))
        if best["method"].startswith("id:"):
            if normalized[0] and normalized[0] == normalized[1]:
                reasons.append(f"names also agree after normalization ({normalized[0]!r})")
            elif normalized[0] and normalized[1]:
                reasons.append(f"names differ ({normalized[0]!r} vs {normalized[1]!r}); "
                               "the shared identifier decides")
        return MatchResult(True, round(float(best["confidence"]), 2), best["method"],
                           tuple(reasons), normalized)

    if refused:
        return MatchResult(False, 0.0, "refused", (refused[0]["refusal_reason"],), normalized)

    if not normalized[0] or not normalized[1]:
        reasons.append("at least one record has no name to compare and no identifier is shared")
    else:
        reasons.append(f"normalized names differ: {normalized[0]!r} vs {normalized[1]!r} "
                       "(reckoner never matches on similarity)")
    for key in STRONG_IDS:
        va, vb = fa["ids"].get(key), fb["ids"].get(key)
        if va and vb and va != vb:
            reasons.append(f"different {key.upper()}: {va} vs {vb}")
    return MatchResult(False, 0.0, "none", tuple(reasons), normalized)
