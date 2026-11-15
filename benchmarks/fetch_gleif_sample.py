"""Rebuild benchmarks/data/gleif_us_sample.csv from the public GLEIF API.

GLEIF (the Global Legal Entity Identifier Foundation) publishes every LEI record
under CC0. Each record has one legal name and, often, other names: trading names
and previous legal names. The LEI is the ground truth: two names belong to the same
entity exactly when they hang off the same LEI.

The sample is built from full-text searches for well-known US company names. Those
searches return the parent company AND dozens of similarly named but separate legal
entities (funds, trusts, pension plans, subsidiaries), which is exactly the case a
name matcher gets wrong.

Rows written per LEI:
  legal       the GLEIF legal name, as registered
  conformed   the same legal name rewritten the way SEC EDGAR "conforms" names
              (upper case, no periods or commas, COMPANY -> CO and so on). This is
              a deterministic rewrite, not a second source; it measures whether
              formatting differences alone break a match.
  trading     a GLEIF TRADING_OR_OPERATING_NAME
  previous    a GLEIF PREVIOUS_LEGAL_NAME
  other       any other GLEIF other-name type (for example alternative language)

Usage (needs network, about 30 small requests):
    python benchmarks/fetch_gleif_sample.py
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

API = "https://api.gleif.org/api/v1/lei-records"
HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "data" / "gleif_us_sample.csv"

# Well-known US public companies. Each query returns up to PAGE_SIZE records whose
# names share words with the query, related or not.
QUERIES = [
    "apple", "microsoft", "alphabet", "amazon", "meta platforms", "berkshire hathaway",
    "jpmorgan chase", "goldman sachs", "morgan stanley", "wells fargo", "citigroup",
    "bank of america", "general electric", "general motors", "ford motor", "boeing",
    "exxon mobil", "chevron", "pfizer", "johnson & johnson", "procter & gamble",
    "walmart", "home depot", "coca-cola", "pepsico", "intel", "cisco systems",
    "oracle", "caterpillar", "lockheed martin", "blackstone", "sherwin-williams",
]
PAGE_SIZE = 100
SKIP_REGISTRATION = {"DUPLICATE", "ANNULLED"}   # the LEI itself is unreliable
OTHER_NAME_KIND = {
    "TRADING_OR_OPERATING_NAME": "trading",
    "PREVIOUS_LEGAL_NAME": "previous",
}

_EDGAR_WORDS = {
    "COMPANY": "CO", "CORPORATION": "CORP", "INCORPORATED": "INC",
    "LIMITED": "LTD", "L L C": "LLC", "L P": "LP",
}


def edgar_conform(name: str) -> str:
    """Rewrite a name roughly the way EDGAR conformed names look: GENERAL ELECTRIC CO."""
    s = name.upper().replace(".", " ").replace(",", " ")
    s = re.sub(r"\s+", " ", s).strip()
    for long, short in _EDGAR_WORDS.items():
        s = re.sub(rf"\b{long}\b", short, s)
    return s


def fetch(query: str) -> List[Dict[str, Any]]:
    params = {
        "filter[fulltext]": query,
        "filter[entity.legalAddress.country]": "US",
        "page[size]": str(PAGE_SIZE),
        "page[number]": "1",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.api+json",
        "User-Agent": "reckoner-benchmark",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    return list(payload.get("data") or [])


def build_rows(records: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for rec in records:
        attrs = rec["attributes"]
        lei = attrs["lei"]
        entity = attrs["entity"]
        legal = (entity.get("legalName") or {}).get("name") or ""
        if not legal.strip():
            continue
        seen = set()

        def add(name: str, variant: str) -> None:
            name = re.sub(r"\s+", " ", name).strip()
            if name and name not in seen:
                seen.add(name)
                rows.append({"lei": lei, "name": name, "variant": variant})

        add(legal, "legal")
        add(edgar_conform(legal), "conformed")
        for other in entity.get("otherNames") or []:
            add(other.get("name") or "", OTHER_NAME_KIND.get(other.get("type") or "", "other"))
    return rows


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-o", "--output", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)

    by_lei: Dict[str, Dict[str, Any]] = {}
    for q in QUERIES:
        got = fetch(q)
        kept = 0
        for rec in got:
            if rec["attributes"]["registration"]["status"] in SKIP_REGISTRATION:
                continue
            if rec["id"] not in by_lei:
                by_lei[rec["id"]] = rec
                kept += 1
        print(f"{q!r:24} {len(got):4} records, {kept:4} new", file=sys.stderr)
        time.sleep(0.5)   # be polite to a free public API

    # Stable order: by LEI, so reruns on the same golden copy give the same file.
    records = [by_lei[k] for k in sorted(by_lei)]
    rows = build_rows(records)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["lei", "name", "variant"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    meta = {
        "source": "GLEIF LEI records API, https://api.gleif.org/api/v1/lei-records",
        "license": "CC0 1.0 (GLEIF data)",
        "fetched": dt.date.today().isoformat(),
        "filter": "entity.legalAddress.country = US, fulltext per query, first page",
        "page_size": PAGE_SIZE,
        "queries": QUERIES,
        "entities": len(records),
        "rows": len(rows),
        "variants": {v: sum(1 for r in rows if r["variant"] == v)
                     for v in ("legal", "conformed", "trading", "previous", "other")},
    }
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(records)} entities, {len(rows)} rows)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
