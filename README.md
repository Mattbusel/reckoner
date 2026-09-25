# reckoner

**Deterministic, explainable entity resolution for organization names. No fuzzy matching. Every merge comes with a receipt.**

Pure Python standard library. Zero dependencies. One file of logic you can read in ten minutes.

---

## The problem

The same company is spelled a different way in every system it appears in.

| One source says | Another says |
| --- | --- |
| `GENERAL ELECTRIC CO` | `GENERAL ELECTRIC COMPANY` |
| `BECTON DICKINSON & CO` | `BECTON, DICKINSON AND COMPANY` |
| `THE SHERWIN-WILLIAMS COMPANY` | `Sherwin Williams Co` |
| `Medtronic plc` | `MEDTRONIC INC` |

Join two public datasets on the raw name and you silently drop a large share of the true matches. So teams reach for a fuzzy matcher, turn a similarity threshold up until the demo looks right, and quietly start merging companies that are not the same one. Now you have a different problem, and no way to explain any single decision.

`reckoner` takes the opposite stance.

## What it does

- **Identifiers merge first.** A shared CIK, UEI, EIN, CAGE, ticker, or domain is the only thing that merges two records outright. Registry-grade IDs (CIK/UEI/EIN/CAGE) link at `0.97`+, reassignable ones (ticker/domain) lower.
- **Names link only after conservative normalization, and only on an exact match.** Case, punctuation, `&`, a leading `The`, and trailing legal suffixes (`Inc`, `Corp`, `Company`, `LLC`, `GmbH`, `plc`, ...) are stripped. `GENERAL ELECTRIC CO` and `General Electric Company` both become `general electric` and link at `0.60`. Distinguishing words are never dropped.
- **There is no fuzzy scoring anywhere.** A typo does not match. `Micrsoft` never links to `Microsoft`. This is a feature: no similarity knob to tune, no silent false merge.
- **Conflicting strong identifiers block a merge.** Two records with the same normalized name but different CIKs are refused, and the refusal is recorded with its reason.
- **Everything is a receipt.** Every link and every refusal is a `MatchRecord`: the original values, the normalized value, the method, the confidence, the evidence. You can audit any decision the resolver made.

## What it does not do

- No fuzzy / edit-distance / embedding similarity. By design.
- No machine learning, no training data, no model to drift.
- No network calls, no I/O. You feed it a list of dicts; it returns clusters, canonical entities, and the full match trail. You persist the results.

If you need probabilistic record linkage across millions of noisy consumer records, use a heavier library. `reckoner` is for the case where a wrong merge is worse than a missed one, and where you have to be able to explain every decision to an analyst, an auditor, or a regulator.

## Install

```bash
pip install git+https://github.com/Mattbusel/reckoner
```

It is not on PyPI: the `reckoner` name there belongs to an unrelated Helm tool, so do not `pip install reckoner`. Or just copy `reckoner/resolver.py` into your project. It is standard library only.

## Quickstart

```python
from reckoner import EntityResolver

records = [
    {"name": "GENERAL ELECTRIC CO", "cik": "0000040545", "source": "sec"},
    {"name": "General Electric Company", "source": "usaspending"},
    {"name": "THE SHERWIN-WILLIAMS COMPANY", "source": "usaspending"},
    {"name": "Sherwin Williams Co", "source": "sec"},
    {"name": "Meta Platforms, Inc.", "cik": "1326801", "source": "sec"},
    {"name": "Meta Financial Group, Inc.", "cik": "907471", "source": "sec"},
]

result = EntityResolver().resolve(records)

for e in result["entities"]:
    print(e["canonical_name"], "<-", e["aliases"], f"(conf {e['link_confidence']})")
```

```
General Electric Company <- ['GENERAL ELECTRIC CO', 'General Electric Company'] (conf 0.99)
THE SHERWIN-WILLIAMS COMPANY <- ['THE SHERWIN-WILLIAMS COMPANY', 'Sherwin Williams Co'] (conf 0.6)
Meta Platforms, Inc. <- ['Meta Platforms, Inc.'] (conf 1.0)
Meta Financial Group, Inc. <- ['Meta Financial Group, Inc.'] (conf 1.0)
```

GE merged on its CIK. Sherwin-Williams merged on the normalized name at lower confidence. The two Metas normalize to different names and carry different CIKs, so they never link.

When two records do normalize to the same name but carry conflicting identifiers, the merge is refused and the refusal is kept:

```python
result = EntityResolver().resolve([
    {"name": "Meta Platforms, Inc.", "cik": "1326801"},
    {"name": "META PLATFORMS INC", "cik": "907471"},
])
result["entities_out"]  # 2, with a refusal receipt in result["matches"]
```

Run the full example with `PYTHONPATH=. python examples/quickstart.py` from the repo root (or after installing the package).

## The output shape

`resolve(records)` returns a dict:

```python
{
  "entities": [ ... ],   # one canonical entity per cluster
  "clusters": [[0, 1], [2, 3], ...],   # input indices grouped
  "matches":  [ ... ],   # every MatchRecord, merged and refused
  "records_in": 6,
  "entities_out": 4,
}
```

Each entity:

```python
{
  "entity_id": "ent-0",
  "canonical_name": "General Electric Company",
  "normalized_name": "general electric",
  "identifiers": {"cik": "40545"},
  "aliases": ["GENERAL ELECTRIC CO", "General Electric Company"],
  "member_indices": [0, 1],
  "sources": ["sec", "usaspending"],
  "link_confidence": 0.99,
}
```

Each match / refusal receipt:

```python
{
  "left_index": 0, "right_index": 1,
  "method": "name_exact_normalized",
  "confidence": 0.0, "merged": False,
  "left_original": "Meta Platforms, Inc.",
  "right_original": "META PLATFORMS INC",
  "normalized": "meta platforms",
  "evidence": [],
  "refusal_reason": "identical normalized names but conflicting CIK - refusing to merge",
}
```

## Agencies too

Pass `agency_mode=True` to resolve government agency names: it adds US-prefix stripping and a small alias table (`DoD` -> `department of defense`, `EPA` -> `environmental protection agency`, ...).

```python
EntityResolver(agency_mode=True).resolve([
    {"agency": "DoD"},
    {"agency": "U.S. Department of Defense"},
])  # -> 1 entity
```

## Extending it

The normalization is deliberately small and readable. Add legal suffixes to `LEGAL_SUFFIXES`, agency aliases to `AGENCY_ALIASES`, or new identifier types to `IDENTIFIERS` with a normalizer and a confidence. Everything is exact-match on the normalized value; there is nothing fuzzy to tune.

## Tests

```bash
python -m unittest discover -s tests
```

## License

MIT, see [LICENSE](LICENSE).

---

Built by the team behind [Tensorust](https://tensorust-site.vercel.app/), where reconciling public records across systems that each spell reality slightly differently is the whole job.
