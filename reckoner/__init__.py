"""reckoner - deterministic, explainable entity resolution for organization names.

No fuzzy matching. Identifiers merge outright; exact-normalized names link at low
confidence; conflicting strong identifiers block a merge. Every link and every
refusal is an auditable receipt.

Install with ``pip install reckoner-er`` (the import name is ``reckoner``).

The short API:

    from reckoner import resolve, match

    for cluster in resolve(["GENERAL ELECTRIC CO", "General Electric Company", "Boeing"]):
        print(cluster.canonical_name, cluster.names, cluster.explanations)

    m = match("THE SHERWIN-WILLIAMS COMPANY", "Sherwin Williams Co")
    print(m.matched, m.score, m.reasons)

The full result, with every receipt as a dict:

    from reckoner import EntityResolver

    records = [
        {"name": "GENERAL ELECTRIC CO", "cik": "40545", "source": "sec"},
        {"name": "General Electric Company", "source": "usaspending"},
        {"name": "Meta Platforms, Inc.", "cik": "1326801", "source": "sec"},
        {"name": "Meta Financial Group", "cik": "907471", "source": "sec"},
    ]
    result = EntityResolver().resolve(records)
    for e in result["entities"]:
        print(e["canonical_name"], e["member_indices"])
"""
from .api import Cluster, MatchResult, Record, match, resolve
from .evaluate import PairwiseScores, pairwise_scores
from .resolver import (
    EntityResolver,
    MatchRecord,
    normalize_org,
    normalize_agency,
    norm_cik,
    norm_uei,
    norm_ein,
    norm_cage,
    norm_ticker,
    norm_domain,
    IDENTIFIERS,
    STRONG_IDS,
    LEGAL_SUFFIXES,
    AGENCY_ALIASES,
    NAME_EXACT_CONFIDENCE,
)

__version__ = "0.3.0"
__all__ = [
    "resolve",
    "match",
    "Cluster",
    "MatchResult",
    "Record",
    "pairwise_scores",
    "PairwiseScores",
    "EntityResolver",
    "MatchRecord",
    "normalize_org",
    "normalize_agency",
    "norm_cik",
    "norm_uei",
    "norm_ein",
    "norm_cage",
    "norm_ticker",
    "norm_domain",
    "IDENTIFIERS",
    "STRONG_IDS",
    "LEGAL_SUFFIXES",
    "AGENCY_ALIASES",
    "NAME_EXACT_CONFIDENCE",
]
