"""Deterministic, explainable entity resolution for organization names.

Links organization/agency records across sources (procurement recipients, SEC
filers, regulatory records, CRM exports, vendor lists...) with rules a human can
audit, and no fuzzy matching anywhere:

  * IDENTIFIERS FIRST. CIK, UEI, EIN, CAGE, ticker, domain - a shared stable official
    identifier is the only thing that merges two records outright.
  * NAMES NEVER MERGE ON SIMILARITY. An exact match AFTER conservative normalization
    (case, punctuation, legal suffixes) may link records - recorded as a lower-
    confidence method - but "similar-looking" names never do: there is no fuzzy
    scoring anywhere in this module, by design.
  * CONFLICTING IDENTIFIERS BLOCK. If two records agree on a normalized name but
    carry DIFFERENT values for the same strong identifier (two distinct CIKs), the
    merge is refused and the refusal is recorded. Meta Financial ≠ Meta Platforms.
  * EVERYTHING IS EXPLAINABLE. Every link (and every refusal) becomes a MatchRecord:
    original values preserved, normalized values shown, method named, confidence
    stated, evidence listed.

Output: clusters of record indices + canonical entity dicts + the full match trail.
Pure stdlib, no I/O - callers feed lists of dicts and persist results themselves.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# normalization
# ---------------------------------------------------------------------------
# legal-form tokens stripped from the END of names, repeatedly ("X Corp LLC" -> "X")
LEGAL_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "llc", "llp",
    "lp", "ltd", "limited", "plc", "pllc", "pc", "pa", "gmbh", "sa", "ag", "bv",
    "nv", "srl", "spa", "ab", "as", "oy", "kk", "pty", "ulc", "lc",
}
# leading tokens that carry no identity ("The Boeing Company")
_LEAD_NOISE = ("the ",)

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s&]")   # keep & for the AND expansion below


def normalize_org(name: str) -> str:
    """Conservative canonical form of an organization name. Deliberately does NOT
    stem, abbreviate, or drop distinguishing words - only case, punctuation, '&',
    leading 'the', and trailing legal suffixes."""
    s = (name or "").strip().lower()
    if not s:
        return ""
    for lead in _LEAD_NOISE:
        if s.startswith(lead):
            s = s[len(lead):]
    s = s.replace("&", " and ")
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    tokens = s.split(" ")
    while len(tokens) > 1 and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


# common federal agency long/short forms; extend as the lake meets more variants.
# Alias map is exact-match on the normalized string - no similarity anywhere.
AGENCY_ALIASES = {
    "dod": "department of defense",
    "dept of defense": "department of defense",
    "us department of defense": "department of defense",
    "gsa": "general services administration",
    "hhs": "department of health and human services",
    "dhs": "department of homeland security",
    "va": "department of veterans affairs",
    "usda": "department of agriculture",
    "doj": "department of justice",
    "dot": "department of transportation",
    "doe": "department of energy",
    "ed": "department of education",
    "epa": "environmental protection agency",
    "nasa": "national aeronautics and space administration",
    "sba": "small business administration",
    "ssa": "social security administration",
}
_US_PREFIX = re.compile(r"^(u\s?s|us|u\.s\.|united states)( of america)?\s+", re.I)


def normalize_agency(name: str) -> str:
    """Canonical agency name: normalize_org + strip US-prefixes + alias table."""
    s = normalize_org(name)
    s = _US_PREFIX.sub("", s).strip()
    return AGENCY_ALIASES.get(s, s)


# ---- identifier normalizers (each returns "" when the value is unusable) ----
def norm_cik(v) -> str:
    s = re.sub(r"\D", "", str(v or ""))
    return s.lstrip("0") or "" if s else ""


def norm_uei(v) -> str:
    """UEI is exactly 12 alphanumerics; formatting separators (dashes/spaces) are
    stripped before validating, anything else is rejected as unusable."""
    s = re.sub(r"[^A-Za-z0-9]", "", str(v or "")).upper()
    return s if len(s) == 12 else ""


def norm_ein(v) -> str:
    s = re.sub(r"\D", "", str(v or ""))
    return s if len(s) == 9 else ""


def norm_cage(v) -> str:
    s = re.sub(r"[^A-Za-z0-9]", "", str(v or "")).upper()
    return s if len(s) == 5 else ""


def norm_ticker(v) -> str:
    s = str(v or "").strip().upper()
    return s if re.fullmatch(r"[A-Z]{1,6}(\.[A-Z])?", s) else ""


def norm_domain(v) -> str:
    s = str(v or "").strip().lower()
    s = re.sub(r"^https?://", "", s).split("/")[0]
    s = s.removeprefix("www.")
    return s if "." in s else ""


# identifier name -> (normalizer, confidence when it makes the match). CIK/UEI/EIN
# are registry-grade; ticker/domain are strong but reassignable, hence lower.
IDENTIFIERS: dict[str, tuple] = {
    "cik": (norm_cik, .99),
    "uei": (norm_uei, .99),
    "ein": (norm_ein, .98),
    "cage": (norm_cage, .97),
    "ticker": (norm_ticker, .90),
    "domain": (norm_domain, .85),
}
# identifiers so authoritative that a CONFLICT between them forbids a name merge
STRONG_IDS = ("cik", "uei", "ein", "cage")

NAME_EXACT_CONFIDENCE = .60               # exact-normalized-name link, no id support


@dataclass
class MatchRecord:
    """One explainable link (or refusal) between two input records."""
    left_index: int
    right_index: int
    method: str                            # e.g. "id:cik", "name_exact_normalized"
    confidence: float
    merged: bool
    left_original: str
    right_original: str
    normalized: str                        # the shared normalized value
    evidence: list = field(default_factory=list)
    refusal_reason: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


class EntityResolver:
    """resolve(records) -> {clusters, entities, matches}.

    Each input record is a dict; recognized keys (all optional):
      name, agency (treated as agency-style name), cik, uei, ein, cage, ticker,
      domain, source (provenance label), state (used only as merge evidence, never
      as a merge key).
    """

    def __init__(self, agency_mode: bool = False):
        self.agency_mode = agency_mode
        self._norm_name = normalize_agency if agency_mode else normalize_org

    # -- per-record feature extraction --------------------------------------
    def _features(self, rec: dict) -> dict:
        name = str(rec.get("name") or rec.get("agency") or "")
        feats = {"original_name": name, "norm_name": self._norm_name(name), "ids": {}}
        for key, (fn, _conf) in IDENTIFIERS.items():
            val = fn(rec.get(key))
            if val:
                feats["ids"][key] = val
        return feats

    @staticmethod
    def _id_conflict(fa: dict, fb: dict) -> str:
        """Name-merge blocker: same strong identifier PRESENT ON BOTH with different
        values. Returns the conflicting id name, or ''."""
        for key in STRONG_IDS:
            va, vb = fa["ids"].get(key), fb["ids"].get(key)
            if va and vb and va != vb:
                return key
        return ""

    def resolve(self, records: list[dict]) -> dict:
        feats = [self._features(r) for r in records]
        uf = _UnionFind(len(records))
        matches: list[MatchRecord] = []

        # pass 1: identifier buckets - the only outright merges
        for key, (fn, conf) in IDENTIFIERS.items():
            buckets: dict[str, list[int]] = {}
            for i, f in enumerate(feats):
                v = f["ids"].get(key)
                if v:
                    buckets.setdefault(v, []).append(i)
            for value, idxs in buckets.items():
                anchor = idxs[0]
                for j in idxs[1:]:
                    uf.union(anchor, j)
                    matches.append(MatchRecord(
                        anchor, j, f"id:{key}", conf, True,
                        feats[anchor]["original_name"], feats[j]["original_name"],
                        value, evidence=[f"shared {key.upper()} {value}"]))

        # pass 2: exact-normalized-name links - allowed ONLY without id conflict
        name_buckets: dict[str, list[int]] = {}
        for i, f in enumerate(feats):
            if f["norm_name"]:
                name_buckets.setdefault(f["norm_name"], []).append(i)
        for norm, idxs in name_buckets.items():
            if len(idxs) < 2:
                continue
            anchor = idxs[0]
            for j in idxs[1:]:
                if uf.find(anchor) == uf.find(j):
                    continue                      # already merged via an identifier
                conflict = self._id_conflict(feats[anchor], feats[j])
                if conflict:
                    matches.append(MatchRecord(
                        anchor, j, "name_exact_normalized", 0.0, False,
                        feats[anchor]["original_name"], feats[j]["original_name"],
                        norm, evidence=[],
                        refusal_reason=f"identical normalized names but conflicting "
                                       f"{conflict.upper()} - refusing to merge"))
                    continue
                evidence = [f"exact normalized name '{norm}'"]
                sa = str(records[anchor].get("state") or "").upper()
                sb = str(records[j].get("state") or "").upper()
                if sa and sb and sa == sb:
                    evidence.append(f"same state {sa}")
                uf.union(anchor, j)
                matches.append(MatchRecord(
                    anchor, j, "name_exact_normalized", NAME_EXACT_CONFIDENCE, True,
                    feats[anchor]["original_name"], feats[j]["original_name"],
                    norm, evidence=evidence))

        # collect clusters + canonical entities
        clusters: dict[int, list[int]] = {}
        for i in range(len(records)):
            clusters.setdefault(uf.find(i), []).append(i)
        entities = []
        for root, members in sorted(clusters.items()):
            ids: dict[str, str] = {}
            aliases, sources = [], []
            for i in members:
                for k, v in feats[i]["ids"].items():
                    ids.setdefault(k, v)
                nm = feats[i]["original_name"]
                if nm and nm not in aliases:
                    aliases.append(nm)
                src = records[i].get("source")
                if src and src not in sources:
                    sources.append(str(src))
            # canonical name: longest alias (most specific), stable tiebreak
            canonical = max(aliases, key=lambda a: (len(a), a)) if aliases else ""
            # link confidence = the strongest evidence that formed this cluster:
            # a shared identifier's confidence if any merged the members, otherwise
            # the exact-normalized-name confidence. A singleton is trivially 1.0.
            if len(members) > 1:
                confidence = max((IDENTIFIERS[k][1] for k in ids),
                                 default=NAME_EXACT_CONFIDENCE)
            else:
                confidence = 1.0
            entities.append({
                "entity_id": f"ent-{root}",
                "canonical_name": canonical,
                "normalized_name": self._norm_name(canonical),
                "identifiers": ids,
                "aliases": aliases,
                "member_indices": members,
                "sources": sources,
                "link_confidence": round(confidence, 2),
            })
        return {
            "entities": entities,
            "clusters": [e["member_indices"] for e in entities],
            "matches": [m.to_dict() for m in matches],
            "records_in": len(records),
            "entities_out": len(entities),
        }
