"""Precision and recall of reckoner on real company names from GLEIF.

Runs offline on the committed snapshot benchmarks/data/gleif_us_sample.csv (built
by fetch_gleif_sample.py; GLEIF data is CC0). Every row is a name attached to an
LEI, and the LEI is the ground truth. reckoner sees names only, no identifiers.

Reported:
  * pairwise precision, recall and F1 on every row ("all names");
  * the same on legal names plus their EDGAR-style rewrites only ("formatting
    only"), which isolates what normalization is for;
  * recall per variant kind: of the pairs (legal name, variant) for one LEI, how
    many reckoner put together;
  * the false merges: clusters holding more than one LEI, with their names.

Usage:
    python benchmarks/run_benchmark.py
    python benchmarks/run_benchmark.py --json
    python benchmarks/run_benchmark.py --min-precision 0.9   # exit 1 below this
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))   # run from a checkout without installing

from reckoner import pairwise_scores, resolve  # noqa: E402

DEFAULT_DATA = HERE / "data" / "gleif_us_sample.csv"
VARIANTS = ("conformed", "trading", "previous", "other")


def load(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def evaluate(rows: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    names = [r["name"] for r in rows]
    labels = [r["lei"] for r in rows]
    start = time.perf_counter()
    clusters = resolve(names)
    seconds = time.perf_counter() - start
    scores = pairwise_scores([c.members for c in clusters], labels)

    cluster_of: Dict[int, int] = {}
    for ci, c in enumerate(clusters):
        for i in c.members:
            cluster_of[i] = ci
    legal_row: Dict[str, int] = {}
    for i, r in enumerate(rows):
        if r["variant"] == "legal":
            legal_row[r["lei"]] = i
    per_variant: Dict[str, Dict[str, int]] = defaultdict(lambda: {"pairs": 0, "found": 0})
    for i, r in enumerate(rows):
        if r["variant"] == "legal" or r["lei"] not in legal_row:
            continue
        stat = per_variant[r["variant"]]
        stat["pairs"] += 1
        stat["found"] += cluster_of[i] == cluster_of[legal_row[r["lei"]]]

    false_merges = []
    for c in clusters:
        leis = sorted({labels[i] for i in c.members})
        if len(leis) > 1:
            false_merges.append({"names": list(c.names), "leis": leis})

    return {
        "records": len(rows),
        "entities": len(set(labels)),
        "clusters": len(clusters),
        "seconds": round(seconds, 4),
        "precision": round(scores.precision, 4),
        "recall": round(scores.recall, 4),
        "f1": round(scores.f1, 4),
        "true_positives": scores.true_positives,
        "false_positives": scores.false_positives,
        "false_negatives": scores.false_negatives,
        "recall_by_variant": {k: dict(v) for k, v in sorted(per_variant.items())},
        "false_merges": false_merges,
    }


def report(name: str, res: Dict[str, Any]) -> str:
    out = [
        f"{name}: {res['records']} names, {res['entities']} entities -> "
        f"{res['clusters']} clusters in {res['seconds'] * 1000:.0f} ms",
        f"  precision {res['precision']:.4f}   recall {res['recall']:.4f}   "
        f"F1 {res['f1']:.4f}   (pairs: {res['true_positives']} right, "
        f"{res['false_positives']} wrong, {res['false_negatives']} missed)",
    ]
    for variant, s in res["recall_by_variant"].items():
        rate = s["found"] / s["pairs"] if s["pairs"] else 1.0
        out.append(f"  legal name + {variant:<9} {s['found']:4}/{s['pairs']:<4} linked ({rate:.1%})")
    return "\n".join(out)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="reckoner precision/recall on GLEIF names")
    ap.add_argument("--data", default=str(DEFAULT_DATA), help="CSV with lei,name,variant")
    ap.add_argument("--json", action="store_true", help="print results as JSON")
    ap.add_argument("--show", type=int, default=10, help="false merges to list (default 10)")
    ap.add_argument("--min-precision", type=float, help="exit 1 if all-names precision is lower")
    ap.add_argument("--min-recall", type=float, help="exit 1 if formatting-only recall is lower")
    args = ap.parse_args(argv)

    rows = load(Path(args.data))
    results = {
        "all_names": evaluate(rows),
        "formatting_only": evaluate([r for r in rows if r["variant"] in ("legal", "conformed")]),
    }
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(report("all names", results["all_names"]))
        print()
        print(report("formatting only (legal + EDGAR-style rewrite)", results["formatting_only"]))
        fm = results["all_names"]["false_merges"]
        if fm:
            print(f"\nfalse merges ({len(fm)} clusters hold more than one LEI):")
            for m in fm[:args.show]:
                print(f"  {m['names']}  LEIs {', '.join(m['leis'])}")

    failed = False
    if args.min_precision is not None and results["all_names"]["precision"] < args.min_precision:
        print(f"precision {results['all_names']['precision']} < {args.min_precision}", file=sys.stderr)
        failed = True
    if args.min_recall is not None and results["formatting_only"]["recall"] < args.min_recall:
        print(f"recall {results['formatting_only']['recall']} < {args.min_recall}", file=sys.stderr)
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
