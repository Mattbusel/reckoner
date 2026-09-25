"""Command-line interface: resolve a CSV / JSON / JSON Lines file of records.

    reckoner companies.csv                     human-readable summary
    reckoner companies.csv --format csv -o out.csv   every input row + its entity
    reckoner records.json --format json        the full result, receipts included
    reckoner --demo                            run on a built-in example

Column names are matched case-insensitively against the keys the resolver
understands: name, agency, cik, uei, ein, cage, ticker, domain, source, state.
Any other columns are carried through untouched in CSV output.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

from . import __version__
from .resolver import EntityResolver

DEMO_RECORDS = [
    {"name": "GENERAL ELECTRIC CO", "cik": "0000040545", "source": "sec"},
    {"name": "General Electric Company", "source": "usaspending"},
    {"name": "THE SHERWIN-WILLIAMS COMPANY", "source": "usaspending"},
    {"name": "Sherwin Williams Co", "source": "sec"},
    {"name": "Meta Platforms, Inc.", "cik": "1326801", "source": "sec"},
    {"name": "Meta Financial Group, Inc.", "cik": "907471", "source": "sec"},
    {"name": "META PLATFORMS INC", "cik": "907471", "source": "typo-feed"},
]


class InputError(Exception):
    """The input file could not be read as records."""


def _normalize_keys(record: dict) -> dict:
    """Lower-case and trim column names so `Name`, ` CIK ` etc. are recognised."""
    return {str(k).strip().lower(): v for k, v in record.items() if k is not None}


def parse_records(text: str, hint: str = "") -> list[dict]:
    """Parse CSV, a JSON array of objects, or JSON Lines into a list of dicts."""
    stripped = text.lstrip("﻿").strip()
    if not stripped:
        raise InputError("the input is empty")
    hint = hint.lower()
    if hint in (".json", ".jsonl", ".ndjson") or stripped[0] in "[{":
        if stripped[0] == "[":
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise InputError(f"invalid JSON: {exc}") from exc
        else:
            data = []
            for n, line in enumerate(stripped.splitlines(), 1):
                if line.strip():
                    try:
                        data.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise InputError(f"invalid JSON on line {n}: {exc}") from exc
        if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
            raise InputError("JSON input must be an array of objects (or one object per line)")
        return [dict(r) for r in data]
    reader = csv.DictReader(io.StringIO(stripped))
    rows = [dict(r) for r in reader]
    if not reader.fieldnames:
        raise InputError("the CSV has no header row")
    return rows


def _read_input(path: str) -> tuple[str, str]:
    if path == "-":
        data = sys.stdin.buffer.read()
        return data.decode("utf-8-sig", errors="replace"), ""
    p = Path(path)
    try:
        return p.read_text(encoding="utf-8-sig", errors="replace"), p.suffix
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc.strerror or exc}") from exc


def format_summary(result: dict) -> str:
    out = [f"{result['records_in']} records -> {result['entities_out']} entities", ""]
    for e in result["entities"]:
        ids = ", ".join(f"{k.upper()} {v}" for k, v in e["identifiers"].items())
        out.append(f"{e['entity_id']}  {e['canonical_name'] or '(no name)'}"
                   f"  [confidence {e['link_confidence']}]" + (f"  {ids}" if ids else ""))
        if len(e["aliases"]) > 1:
            for alias in e["aliases"]:
                out.append(f"    alias: {alias}")
        out.append(f"    records: {', '.join(str(i) for i in e['member_indices'])}")
    refusals = [m for m in result["matches"] if not m["merged"]]
    if refusals:
        out.append("")
        out.append(f"Refused merges ({len(refusals)}):")
        for m in refusals:
            out.append(f"    records {m['left_index']} and {m['right_index']}: "
                       f"{m['left_original']!r} vs {m['right_original']!r}: {m['refusal_reason']}")
    return "\n".join(out) + "\n"


def format_csv(records: list[dict], result: dict) -> str:
    """One row per input record, in input order, with its entity appended."""
    by_index = {}
    for e in result["entities"]:
        for i in e["member_indices"]:
            by_index[i] = e
    columns: list[str] = []
    for r in records:
        for k in r:
            if k not in columns:
                columns.append(k)
    extra = ["entity_id", "canonical_name", "link_confidence"]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns + extra)
    for i, r in enumerate(records):
        e = by_index[i]
        writer.writerow([r.get(c, "") for c in columns]
                        + [e["entity_id"], e["canonical_name"], e["link_confidence"]])
    return buf.getvalue()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reckoner",
        description="Deterministic, explainable entity resolution for organization names. "
                    "Reads records from a CSV, JSON or JSON Lines file (or - for stdin) and "
                    "groups the ones that are the same organization. No fuzzy matching.",
        epilog="Recognised columns (case-insensitive): name, agency, cik, uei, ein, cage, "
               "ticker, domain, source, state. Example: reckoner companies.csv --format csv "
               "-o resolved.csv",
    )
    parser.add_argument("input", nargs="?",
                        help="CSV, JSON or JSON Lines file of records, or - to read stdin")
    parser.add_argument("-f", "--format", choices=("summary", "json", "csv"), default="summary",
                        help="summary (default): readable report; json: full result with every "
                             "match receipt; csv: each input row plus its entity_id, "
                             "canonical_name and link_confidence")
    parser.add_argument("-o", "--output", help="write to this file instead of the terminal")
    parser.add_argument("--agency", action="store_true",
                        help="agency mode: strip US prefixes and expand aliases like DoD, EPA")
    parser.add_argument("--demo", action="store_true",
                        help="resolve a small built-in example instead of reading a file")
    parser.add_argument("--version", action="version", version=f"reckoner {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo:
        raw = [dict(r) for r in DEMO_RECORDS]
    elif args.input:
        try:
            text, suffix = _read_input(args.input)
            raw = parse_records(text, suffix)
        except InputError as exc:
            print(f"reckoner: {exc}", file=sys.stderr)
            return 2
    else:
        parser.print_help()
        return 2

    # The resolver sees lower-cased keys; CSV output keeps the original headers.
    records = [_normalize_keys(r) for r in raw]
    result = EntityResolver(agency_mode=args.agency).resolve(records)

    if args.format == "json":
        rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    elif args.format == "csv":
        rendered = format_csv(raw, result)
    else:
        rendered = format_summary(result)

    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8", newline="")
        print(f"wrote {args.output} ({result['records_in']} records -> "
              f"{result['entities_out']} entities)", file=sys.stderr)
    else:
        # Windows consoles and pipes may not be UTF-8; never crash on a company name.
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
