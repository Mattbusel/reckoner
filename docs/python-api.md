# Python API

```
pip install reckoner-er
```

The distribution is called `reckoner-er` because `reckoner` on PyPI is an unrelated
Helm tool. The import name and the command are both `reckoner`. Do not install both
packages in the same environment: they would fight over the `reckoner` name.

Python 3.9 or newer, no dependencies. The package ships `py.typed` and passes
`mypy --strict`.

## resolve(names, *, agency=False) -> list[Cluster]

Groups names (or records) that refer to the same organization.

```python
from reckoner import resolve

clusters = resolve([
    "GENERAL ELECTRIC CO",
    "General Electric Company",
    {"name": "GE", "cik": "0000040545"},
    {"name": "General Electric", "cik": "40545"},
    "Boeing",
])
for c in clusters:
    print(c.canonical_name, c.members, c.link_confidence)
    for why in c.explanations:
        print("   ", why)
```

Each input item is either a string (a name) or a mapping with any of the keys
`name`, `agency`, `cik`, `uei`, `ein`, `cage`, `ticker`, `domain`, `source`, `state`.
Keys are matched case-insensitively.

A `Cluster` has:

| field | meaning |
|---|---|
| `entity_id` | `"ent-<n>"`, stable within one call |
| `canonical_name` | the longest member name |
| `normalized_name` | `canonical_name` after normalization |
| `members` | input indices, in input order |
| `names` | the member names, aligned with `members` |
| `identifiers` | identifiers carried by any member, e.g. `{"cik": "40545"}` |
| `link_confidence` | strongest evidence that merged the members: CIK/UEI 0.99, EIN 0.98, CAGE 0.97, ticker 0.90, domain 0.85, exact normalized name 0.60; 1.0 for a single record |
| `explanations` | one sentence per merge into the cluster and per refused merge involving a member |

Clusters come back in order of first appearance, and every input index is in
exactly one cluster. A `Cluster` is frozen and hashable, so clusters can go in a
set or be used as dict keys (do not change `identifiers` in place).

## match(a, b, *, agency=False) -> MatchResult

Decides whether two names or records are the same organization. It makes exactly
the decision `resolve` would make for that pair.

```python
from reckoner import match

m = match("THE SHERWIN-WILLIAMS COMPANY", "Sherwin Williams Co")
m.matched   # True
m.score     # 0.6
m.method    # "name_exact_normalized"
m.reasons   # ("names are identical after normalization: 'sherwin williams' (confidence 0.60)",)

match("Meta Platforms", "Meta Financial Group").matched              # False
match({"name": "GE", "cik": "40545"},
      {"name": "General Electric", "cik": "0000040545"}).score      # 0.99
```

`score` is the confidence of the merge, not a similarity: two names either match
or they do not. `method` is `"id:<name>"`, `"name_exact_normalized"`, `"refused"`
(same normalized name but conflicting CIK, UEI, EIN or CAGE) or `"none"`. A
`MatchResult` is truthy when it matched.

## Command line

```
reckoner match "GENERAL ELECTRIC CO" "General Electric Company"
reckoner match --a-cik 40545 --b-cik 0000040545 "GE" "General Electric" --json
reckoner match --agency "DoD" "U.S. Department of Defense"
```

Exit status is 0 on a match, 1 on no match and 2 on a usage error, so it works in
shell `if` statements. `reckoner FILE` resolves a whole CSV, JSON or JSON Lines file
as before; see `reckoner --help`.

## Scoring your own labelled data

```python
from reckoner import resolve, pairwise_scores

names  = ["Acme Inc", "ACME", "Acme Holdings", "Zeta LLC"]
labels = ["acme",     "acme", "acme",          "zeta"]     # the truth
s = pairwise_scores([c.members for c in resolve(names)], labels)
print(s.precision, s.recall, s.f1)
```

`benchmarks/run_benchmark.py` does this on public GLEIF data; see
[benchmark.md](benchmark.md).

## The full result

`EntityResolver().resolve(records)` still returns the original dict with
`entities`, `clusters` and every `matches` receipt, for callers who want to store
the audit trail.
