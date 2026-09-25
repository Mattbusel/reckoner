"""reckoner - deterministic, explainable entity resolution for organization names.

No fuzzy matching. Identifiers merge outright; exact-normalized names link at low
confidence; conflicting strong identifiers block a merge. Every link and every
refusal is an auditable receipt.

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

__version__ = "0.2.1"
__all__ = [
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
