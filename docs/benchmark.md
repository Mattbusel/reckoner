# Benchmark: real company names from GLEIF

```
python benchmarks/run_benchmark.py
```

Runs offline in well under a second on a committed snapshot,
`benchmarks/data/gleif_us_sample.csv` (204 KB). To rebuild the snapshot from the
live API (about 30 small requests), run `python benchmarks/fetch_gleif_sample.py`.

## The data

[GLEIF](https://www.gleif.org/) publishes every Legal Entity Identifier record
under CC0. Each record has a legal name and often other names (previous legal
names, trading names). The LEI is the ground truth: two names belong to the same
entity exactly when they belong to the same LEI.

The snapshot (fetched 2026-11-14) is the first page of GLEIF full-text results for
32 well-known US company names (Apple, Goldman Sachs, Blackstone, General
Electric, Oracle and so on), limited to entities with a US legal address, with
duplicate and annulled LEIs left out. Those searches return the parent company and
many separate legal entities with very similar names: funds, trusts, pension plans
and subsidiaries. That is the hard case for any name matcher.

1312 entities, 2922 names:

| variant | rows | what it is |
|---|---:|---|
| legal | 1312 | the GLEIF legal name |
| conformed | 1113 | the legal name rewritten the way SEC EDGAR writes names: upper case, no periods or commas, COMPANY to CO, CORPORATION to CORP, INCORPORATED to INC, LIMITED to LTD. A deterministic rewrite, not a second source. Rows identical to the legal name are dropped. |
| previous | 472 | GLEIF previous legal names |
| trading | 25 | GLEIF trading or operating names |

reckoner sees names only. GLEIF records carry no CIK, EIN or UEI, so the
identifier rules, which are reckoner's strongest evidence, are not exercised here.

## Results (reckoner 0.3.0)

Pairwise metrics: a pair of names is a true positive when reckoner put them in one
cluster and they share an LEI.

| slice | names | precision | recall | F1 |
|---|---:|---:|---:|---:|
| formatting only (legal + conformed) | 2425 | 0.9659 | 0.9686 | 0.9672 |
| all names | 2922 | 0.9628 | 0.4996 | 0.6578 |

Recall by variant (pairs of legal name and variant for the same LEI that ended up
together):

| variant | linked |
|---|---|
| conformed | 1078 / 1113 (96.9%) |
| previous | 18 / 472 (3.8%) |
| trading | 0 / 25 (0.0%) |

## Reading the numbers

**Formatting differences are handled.** Case, punctuation, a leading "The" and
trailing legal suffixes do not stop a match. The 35 conformed pairs still missed
are abbreviations in the middle of a name ("The Boeing Company Employee Retirement
Plans Master Trust" against "THE BOEING CO EMPLOYEE ..."), which reckoner
deliberately does not rewrite, and dotted suffixes that are not at the end
("Fund L.P. II").

**Renames and trade names are not found, by design.** "Boston Edison Company" and
"NSTAR Electric Company" are the same LEI, but nothing in the two names says so.
reckoner never guesses from similarity; link renamed entities with an identifier.

**Every wrong merge is two entities with the same legal name.** All 13 clusters
that hold more than one LEI are separately registered entities whose names are
identical after normalization: two "Oracle Corporation" LEIs, two "Cisco Systems,
Inc." LEIs, two "Goldman Sachs Mid Cap Growth Fund" LEIs, two "Green Apple, LLC".
No name-only method can tell these apart. Give reckoner a CIK, EIN or UEI for each
record and conflicting identifiers block the merge.

## What changed in 0.3.0

The benchmark found that dotted legal suffixes were not stripped: "Oracle Partners,
L.P." normalized to `oracle partners l p` and never met "ORACLE PARTNERS LP".
Fixing that raised formatting-only recall from 0.9102 to 0.9686 with precision
unchanged (0.9638 before, 0.9659 after).

## Using it as a regression gate

```
python benchmarks/run_benchmark.py --min-precision 0.95 --min-recall 0.95
```

exits 1 when all-names precision or formatting-only recall drops below the given
floor. CI runs it on every push. `--json` prints every number, including the
false merges.
