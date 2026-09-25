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
import os
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
    rows = []
    for row in reader:
        if None in row:
            # More cells than headers: almost always an unquoted comma in a name.
            raise InputError(
                f"CSV line {reader.line_num} has more fields than the header. "
                'Put values that contain commas in double quotes, e.g. "Becton, Dickinson and Co"')
        rows.append(dict(row))
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
        hint = (" (check the path; run reckoner --demo to see the expected input)"
                if isinstance(exc, FileNotFoundError) else "")
        raise InputError(f"cannot read {path}: {exc.strerror or exc}{hint}") from exc


RECOGNISED_COLUMNS = ("name", "agency", "cik", "uei", "ein", "cage", "ticker", "domain")


class _Style:
    """ANSI styling that collapses to plain text when color is off."""

    CODES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33",
             "blue": "34", "cyan": "36", "grey": "90"}

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def __call__(self, text: str, *styles: str) -> str:
        if not self.enabled or not styles or not text:
            return text
        codes = ";".join(self.CODES[s] for s in styles)
        return f"\x1b[{codes}m{text}\x1b[0m"


def use_color(stream, mode: str = "auto") -> bool:
    """auto: color on a terminal unless NO_COLOR is set; FORCE_COLOR forces it on."""
    if mode == "never":
        return False
    if mode == "always":
        return True
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(stream, "isatty") and stream.isatty()


def _enable_windows_ansi() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:  # pragma: no cover - best effort only
        pass


def _record_name(rec: dict) -> str:
    return str(rec.get("name") or rec.get("agency") or "")


def _conf_color(c: float) -> str:
    return "green" if c >= 0.95 else ("yellow" if c >= 0.6 else "red")


def format_summary(result: dict, records: list[dict] | None = None, color: bool = False) -> str:
    """Readable report: every entity, the records it holds, and why each one joined.

    `records` are the (key-normalized) input records; without them the member lines
    fall back to the entity's aliases.
    """
    st = _Style(color)
    merged = [m for m in result["matches"] if m["merged"]]
    refusals = [m for m in result["matches"] if not m["merged"]]
    # why each record joined its cluster: the merge that brought it in
    joined_by = {m["right_index"]: m for m in merged}

    head = f"{result['records_in']} records -> {result['entities_out']} entities"
    tail = (f"   {len(merged)} merge{'s' if len(merged) != 1 else ''}, "
            f"{len(refusals)} refused")
    out = [st(head, "bold") + st(tail, "grey"), ""]

    id_w = max((len(e["entity_id"]) for e in result["entities"]), default=5)
    idx_w = len(str(max(result["records_in"] - 1, 0))) + 1
    names = [_record_name(r) for r in records] if records is not None else None
    name_w = min(40, max((len(n) for n in names), default=10)) if names else 0
    src_w = min(16, max((len(str(r.get("source") or "")) for r in records), default=0)) if records else 0

    canon_w = min(44, max((len(e["canonical_name"] or "(no name)") for e in result["entities"]),
                          default=10))
    for e in result["entities"]:
        ids = "  ".join(f"{k.upper()} {v}" for k, v in e["identifiers"].items())
        conf = f"{e['link_confidence']:.2f}"
        canon = e["canonical_name"] or "(no name)"
        out.append(st(e["entity_id"].ljust(id_w), "grey") + "  "
                   + st(canon, "bold") + " " * max(0, canon_w - len(canon))
                   + "  " + st(conf, _conf_color(e["link_confidence"]))
                   + (("  " + st(ids, "cyan")) if ids else ""))
        pad = " " * (id_w + 2)
        if names is None:
            if len(e["aliases"]) > 1:
                for alias in e["aliases"]:
                    out.append(f"{pad}alias: {alias}")
            out.append(f"{pad}records: {', '.join(str(i) for i in e['member_indices'])}")
            continue
        if len(e["member_indices"]) == 1:
            continue
        for i in e["member_indices"]:
            nm = names[i] or "(no name)"
            if len(nm) > name_w:
                nm = nm[:name_w - 3] + "..."
            src = str(records[i].get("source") or "")[:src_w]
            m = joined_by.get(i)
            if m is None:
                why = ""
            elif m["method"].startswith("id:"):
                why = st("= " + m["method"][3:].upper() + " " + m["normalized"], "green")
            else:
                why = st(f"= name '{m['normalized']}'", "yellow")
            row = (pad + st(f"#{i}".ljust(idx_w), "grey") + "  " + nm.ljust(name_w)
                   + ("  " + st(src.ljust(src_w), "dim") if src_w else "")
                   + ("  " + why if why else ""))
            out.append(row.rstrip())

    if refusals:
        out.append("")
        out.append(st(f"Refused merges ({len(refusals)}):", "red", "bold"))
        for m in refusals:
            lead = f"  #{m['left_index']} + #{m['right_index']}  "
            out.append(lead + f"{m['left_original']!r} vs {m['right_original']!r}")
            out.append(" " * len(lead) + st(m["refusal_reason"], "red"))
    if names is not None and result["entities_out"] < result["records_in"]:
        out.append("")
        out.append(st("#n is the input record.  '= CIK 123', '= TICKER X': joined on a shared ID.", "grey"))
        out.append(st("'= name ...' joined on the exact normalized name (0.60, never fuzzy).", "grey"))
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


EXAMPLES = """\
examples:
  reckoner --demo                                see it work on a built-in example
  reckoner companies.csv                         readable report, refusals listed
  reckoner companies.csv -f csv -o resolved.csv  your rows + entity_id, canonical_name,
                                                 link_confidence
  reckoner records.jsonl -f json                 full result with every match receipt
  reckoner agencies.csv --agency                 agency names: DoD, EPA, U.S. prefixes
  cat companies.csv | reckoner -                 read stdin

Recognised columns (case-insensitive): name, agency, cik, uei, ein, cage, ticker,
domain, source, state. Other columns are kept in CSV output.
Color is on in a terminal; NO_COLOR=1 or --color never turns it off.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reckoner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Group records that name the same organization. Merges on shared IDs\n"
                    "(CIK, EIN, UEI, CAGE, ticker, domain) or exact normalized names, never\n"
                    "fuzzy guesses, and keeps a receipt for every merge and refusal.",
        epilog=EXAMPLES,
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
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                        help="color the summary (default auto: on in a terminal, off when "
                             "piped or when NO_COLOR is set)")
    parser.add_argument("--version", action="version", version=f"reckoner {__version__}")
    return parser


FIRST_RUN = """\
reckoner: no input file given.

  reckoner --demo              see it work on a built-in example
  reckoner companies.csv       resolve your own CSV, JSON or JSON Lines file
  reckoner --help              every option, with examples
"""


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
        sys.stderr.write(FIRST_RUN)
        return 2

    # The resolver sees lower-cased keys; CSV output keeps the original headers.
    records = [_normalize_keys(r) for r in raw]
    if records and not any(k in r for r in records for k in RECOGNISED_COLUMNS):
        found = ", ".join(sorted({str(k) for r in raw for k in r})[:8]) or "none"
        print(f"reckoner: none of the columns are ones reckoner reads (found: {found}).\n"
              "  Rename the organization-name column to 'name' (or 'agency'), and/or add an "
              "ID column: cik, ein, uei, cage, ticker, domain.", file=sys.stderr)
        return 2
    result = EntityResolver(agency_mode=args.agency).resolve(records)

    if args.format == "json":
        rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    elif args.format == "csv":
        rendered = format_csv(raw, result)
    else:
        color = not args.output and use_color(sys.stdout, args.color)
        if color:
            _enable_windows_ansi()
        rendered = format_summary(result, records, color=color)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8", newline="") as fh:
                fh.write(rendered)
        except OSError as exc:
            print(f"reckoner: cannot write {args.output}: {exc.strerror or exc}", file=sys.stderr)
            return 2
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
