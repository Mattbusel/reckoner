# Changelog

## [0.3.0] - 2026-11-14

- On PyPI as `reckoner-er` (`pip install reckoner-er`). The name `reckoner` there belongs to an unrelated Helm tool; the import name and the command stay `reckoner`.
- New two-function API: `resolve(names)` returns typed `Cluster` objects (members, names, canonical name, identifiers, confidence, and an `explanations` sentence for every merge and refusal); `match(a, b)` returns a `MatchResult` with `matched`, `score`, `method` and `reasons`. Both take plain strings or records with identifiers. `Cluster` and `MatchResult` are frozen and hashable. See `docs/python-api.md`.
- New `reckoner match "A" "B"` command, with `--a-cik`/`--b-cik` (and UEI, EIN, CAGE, ticker, domain), `--agency`, `--color` and `--json`. Exits 0 on a match and 1 otherwise. `match` is recognised as the first argument that is not an option, so `reckoner --color never match A B` works too. Because of this, a file literally named `match` is now read with `reckoner ./match` or `reckoner -- match`.
- `pairwise_scores(clusters, labels)` scores a resolution against labelled data (pairwise precision, recall, F1).
- Benchmark on real GLEIF names (1312 entities, 2922 names, CC0 snapshot committed): precision 0.966 and recall 0.969 on formatting variants; renames and trade names are not linked, by design. `python benchmarks/run_benchmark.py`; details in `docs/benchmark.md`. CI fails if precision or recall drops below 0.95.
- Fix: dotted legal suffixes at the end of a name are now stripped like the plain ones. "Oracle Partners, L.P." and "ORACLE PARTNERS LP" both normalize to `oracle partners` (they did not match before), as do "L.L.C.", "P.A." and similar. Each dotted abbreviation is read on its own from the right, so "Acme U.S. L.P." matches "Acme U.S. LP" and "Foo L.P. L.L.C." matches "Foo LP LLC". Only letters that spell a legal suffix are joined, so initials such as "A.G. Edwards" and "U.S." normalize exactly as before. On the benchmark this raised formatting recall from 0.910 to 0.969 with precision unchanged.
- Type hints throughout; ships `py.typed` and passes `mypy --strict`.
- `publish.yml` builds, checks and smoke-tests the sdist and wheel, then uploads them to PyPI with trusted publishing when a `v*` tag is pushed.
- The PyPI page comes from `docs/pypi.md` (absolute image URLs, `pip install reckoner-er`). The sdist includes `benchmarks/`, `docs/` and `examples/`, so the full test suite runs from an unpacked sdist; the benchmark test skips itself when `benchmarks/` is absent.

## [0.2.2] - 2026-09-25

- Fix: `link_confidence` no longer claims an identifier's confidence when only one record in the cluster carries that identifier. Such clusters were joined by name, so they now report 0.60 (for example GE with a CIK on one record only: was 0.99, now 0.60).
- The summary now shows every record in each group and why it joined (`= CIK 907471`, `= name 'general electric'`), aligned, with a count of merges and refusals.
- Color in the terminal (off when piped, with `NO_COLOR`, or `--color never`).
- Running `reckoner` with no file prints what to try next; a file with none of the recognised columns stops with a message naming the columns found and what to rename; a missing file suggests `--demo`.
- `--help` ends with copy-paste examples.
- `install.sh` and `install.ps1` one-line installers; `examples/vendors.csv`.

## [0.2.1] - 2026-09-25

- The CLI now stops with a clear message when a CSV row has more fields than the header (usually an unquoted comma in a company name) instead of writing a garbled extra column.

## [0.2.0] - 2026-09-25

- New `reckoner` command line tool: resolve a CSV, JSON or JSON Lines file (or stdin) and get a readable summary, the full JSON result with every receipt, or a CSV of your rows with `entity_id`, `canonical_name` and `link_confidence` appended. `--agency` for agency names, `--demo` for a built-in example.
- Prebuilt single-file executables for Windows, macOS (Apple Silicon and Intel) and Linux on every GitHub Release. No Python needed.
- `python -m reckoner` works too.
- CI runs the tests and the CLI on Linux and Windows.

## [0.1.0]

- Initial release: `EntityResolver`, identifier-first merges, exact-normalized name links, refusal receipts, agency mode.
