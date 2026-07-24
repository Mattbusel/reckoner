"""Resolve a messy list of organization records into canonical entities.

Run from the repo root:  python examples/quickstart.py
"""
from reckoner import EntityResolver

# The same company shows up spelled differently in every system. Two of these
# records also carry an official identifier (SEC CIK); the rest are name-only.
records = [
    {"name": "GENERAL ELECTRIC CO", "cik": "0000040545", "source": "sec"},
    {"name": "General Electric Company", "source": "usaspending"},
    {"name": "THE SHERWIN-WILLIAMS COMPANY", "source": "usaspending"},
    {"name": "Sherwin Williams Co", "source": "sec"},
    {"name": "Meta Platforms, Inc.", "cik": "1326801", "source": "sec"},
    {"name": "Meta Financial Group, Inc.", "cik": "907471", "source": "sec"},
]

result = EntityResolver().resolve(records)

print(f"{result['records_in']} records -> {result['entities_out']} entities\n")
for e in result["entities"]:
    ids = ", ".join(f"{k}={v}" for k, v in e["identifiers"].items()) or "no identifiers"
    print(f"  {e['canonical_name']}")
    print(f"     aliases : {e['aliases']}")
    print(f"     ids     : {ids}")
    print(f"     conf    : {e['link_confidence']}\n")

# The two "Meta" companies share a normalized-ish look but carry different CIKs,
# so the merge is refused and the refusal is on the record.
refusals = [m for m in result["matches"] if not m["merged"]]
if refusals:
    print("Refused merges (kept separate on purpose):")
    for m in refusals:
        print(f"  {m['left_original']!r} vs {m['right_original']!r}: {m['refusal_reason']}")
