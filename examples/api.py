"""The two-function API: resolve() groups names, match() compares two.

Run from the repo root:  python examples/api.py
(or after `pip install reckoner-er`, from anywhere)
"""
from reckoner import match, resolve

names = [
    "GENERAL ELECTRIC CO",
    "General Electric Company",
    "ORACLE PARTNERS, L.P.",
    "Oracle Partners LP",
    {"name": "Meta Platforms, Inc.", "cik": "1326801"},
    {"name": "META PLATFORMS INC", "cik": "907471"},   # a different CIK: kept apart
    "Meta Financial Group",
]

for cluster in resolve(names):
    print(f"{cluster.canonical_name}  (confidence {cluster.link_confidence:.2f})")
    for name in cluster.names:
        print(f"    {name}")
    for why in cluster.explanations:
        print(f"    - {why}")
    print()

for a, b in [("THE SHERWIN-WILLIAMS COMPANY", "Sherwin Williams Co"),
             ("Meta Platforms", "Meta Financial Group")]:
    m = match(a, b)
    print(f"match({a!r}, {b!r}) -> {m.matched}, score {m.score}")
    for reason in m.reasons:
        print(f"    - {reason}")
