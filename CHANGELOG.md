# Changelog

## [0.2.1] - 2026-09-25

- The CLI now stops with a clear message when a CSV row has more fields than the header (usually an unquoted comma in a company name) instead of writing a garbled extra column.

## [0.2.0] - 2026-09-25

- New `reckoner` command line tool: resolve a CSV, JSON or JSON Lines file (or stdin) and get a readable summary, the full JSON result with every receipt, or a CSV of your rows with `entity_id`, `canonical_name` and `link_confidence` appended. `--agency` for agency names, `--demo` for a built-in example.
- Prebuilt single-file executables for Windows, macOS (Apple Silicon and Intel) and Linux on every GitHub Release. No Python needed.
- `python -m reckoner` works too.
- CI runs the tests and the CLI on Linux and Windows.

## [0.1.0]

- Initial release: `EntityResolver`, identifier-first merges, exact-normalized name links, refusal receipts, agency mode.
