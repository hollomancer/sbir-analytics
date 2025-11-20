# sbir-analytics/src/transition/features/vendor_resolver.py
"""
Vendor resolution utilities for transition detection.

This module provides a `VendorResolver` class that encapsulates logic to resolve
vendor/company identities across multiple identifier spaces (UEI, CAGE, DUNS)
and by fuzzy name matching. It is intended to be used by the transition
detection pipeline to map contract award vendor references to canonical
company entities used elsewhere in the system (SBIR awards, Neo4j nodes, etc).

Features:
- Exact identifier matching (UEI, CAGE, DUNS)
- Fuzzy name matching with configurable thresholds
- Cross-walk table support (load and query)
- Simple in-memory caching of match results
- Pluggable fuzzy-match backend: rapidfuzz (preferred) with difflib fallback

Usage example
-------------
from sbir_etl.src.transition.features.vendor_resolver import VendorResolver, VendorRecord

# Prepare a list of known vendors (from DB, DuckDB, or CSV)
vendors = [
    VendorRecord(uei="ABC123", cage="1A2B3", duns="123456789", name="Acme Corporation"),
    VendorRecord(uei="DEF456", cage="4C5D6", duns="987654321", name="Ophir Corporation"),
]

resolver = VendorResolver.from_records(vendors)
match = resolver.resolve_by_name("Acme Corp", prefer_identifiers=True)
print(match)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from loguru import logger


# Try to use rapidfuzz if installed for higher-quality fuzzy matching.
try:
    from rapidfuzz import fuzz

    _RAPIDFUZZ_AVAILABLE = True
except Exception:
    _RAPIDFUZZ_AVAILABLE = False


@dataclass
class VendorRecord:
    """
    Canonical vendor/entity record used for matching.

    Fields:
    - uei: Unique Entity Identifier (string) - may be None
    - cage: CAGE code (string) - may be None
    - duns: DUNS number (string) - may be None
    - name: Normalized company name (string)
    - metadata: Arbitrary metadata dictionary (optional)
    """

    uei: str | None
    cage: str | None
    duns: str | None
    name: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class VendorMatch:
    """
    Result of a vendor match operation.

    - record: matched canonical VendorRecord or None if no match
    - method: how the match was found ('uei', 'cage', 'duns', 'name_exact', 'name_fuzzy', etc.)
    - score: confidence score in [0.0, 1.0] (1.0 = exact)
    - note: optional human-readable note
    """

    record: VendorRecord | None
    method: str
    score: float
    note: str | None = None


class VendorResolver:
    """
    Resolve vendor references to canonical vendor records.

    Construction:
      - VendorResolver.from_records(records, config=...) to build an in-memory resolver.

    Matching priorities (default):
      1. UEI exact match
      2. CAGE exact match
      3. DUNS exact match
      4. Exact normalized name match
      5. Fuzzy name match (threshold configurable)

    The resolver maintains small indices on UEI/CAGE/DUNS and a name index for
    fast lookups. For fuzzy matching, it will use rapidfuzz.fuzz.ratio if available;
    otherwise it falls back to difflib.SequenceMatcher ratio.
    """

    def __init__(
        self,
        records: Iterable[VendorRecord],
        fuzzy_threshold: float = 0.9,
        fuzzy_secondary_threshold: float = 0.8,
    ) -> None:
        self.fuzzy_threshold = float(fuzzy_threshold)
        self.fuzzy_secondary_threshold = float(fuzzy_secondary_threshold)

        # Indices
        self._uei_index: dict[str, VendorRecord] = {}
        self._cage_index: dict[str, VendorRecord] = {}
        self._duns_index: dict[str, VendorRecord] = {}
        # Name index: normalized lowercase name -> list of records (to support duplicates)
        self._name_index: dict[str, list[VendorRecord]] = {}

        # Cache resolved queries for speed (simple in-memory)
        self._cache: dict[tuple[str, str], VendorMatch] = {}

        # Load records into indices
        self._load_records(records)

    @classmethod
    def from_records(cls: Any, records: Iterable[VendorRecord], **kwargs) -> VendorResolver:
        """Convenience constructor."""
        return cls(records, **kwargs)

    def _normalize_name(self, name: str) -> str:
        """Normalize company names for indexing and exact comparisons."""
        if name is None:
            return ""  # type: ignore[unreachable]
        # Basic normalization: uppercase, trim, collapse whitespace, strip punctuation-ish chars
        n = " ".join(name.strip().split())
        n = n.replace(",", " ").replace(".", " ").replace("/", " ").replace("&", " AND ")
        n = n.lower()
        # Normalize common business suffix variants so "corp" vs "corporation" etc. compare closely.
        replacements = {
            "incorporated": "inc",
            "inc": "inc",
            "corporation": "corp",
            "corp": "corp",
            "company": "co",
            "co": "co",
            "limited": "ltd",
            "ltd": "ltd",
            "llc": "llc",
            "llp": "llp",
        }
        tokens = n.split()
        normalized_tokens = [replacements.get(tok, tok) for tok in tokens]
        return " ".join(normalized_tokens)

    def _load_records(self, records: Iterable[VendorRecord]) -> None:
        """Populate indices from the provided VendorRecord iterable."""
        count = 0
        for r in records:
            count += 1
            if r.uei:
                key = str(r.uei).strip().upper()
                if key:
                    self._uei_index[key] = r
            if r.cage:
                key = str(r.cage).strip().upper()
                if key:
                    self._cage_index[key] = r
            if r.duns:
                key = str(r.duns).strip()
                if key:
                    self._duns_index[key] = r
            nm = self._normalize_name(r.name)
            self._name_index.setdefault(nm, []).append(r)
        logger.info("VendorResolver loaded %d vendor records", count)

    # -----------------------------
    # Exact identifier match methods
    # -----------------------------
    def resolve_by_uei(self, uei: str) -> VendorMatch:
        """Resolve by UEI (exact)."""
        if not uei:
            return VendorMatch(record=None, method="uei", score=0.0, note="no uei provided")
        key = str(uei).strip().upper()
        rec = self._uei_index.get(key)
        if rec:
            return VendorMatch(record=rec, method="uei", score=1.0)
        return VendorMatch(record=None, method="uei", score=0.0, note="no match")

    def resolve_by_cage(self, cage: str) -> VendorMatch:
        """Resolve by CAGE (exact)."""
        if not cage:
            return VendorMatch(record=None, method="cage", score=0.0, note="no cage provided")
        key = str(cage).strip().upper()
        rec = self._cage_index.get(key)
        if rec:
            return VendorMatch(record=rec, method="cage", score=1.0)
        return VendorMatch(record=None, method="cage", score=0.0, note="no match")

    def resolve_by_duns(self, duns: str) -> VendorMatch:
        """Resolve by DUNS (exact)."""
        if not duns:
            return VendorMatch(record=None, method="duns", score=0.0, note="no duns provided")
        key = str(duns).strip()
        rec = self._duns_index.get(key)
        if rec:
            return VendorMatch(record=rec, method="duns", score=1.0)
        return VendorMatch(record=None, method="duns", score=0.0, note="no match")

    # -----------------------------
    # Name matching helpers
    # -----------------------------
    def _fuzzy_score(self, s1: str, s2: str) -> float:
        """Compute a similarity score between 0 and 1 between two strings.

        Uses rapidfuzz if available for better performance and options; falls back
        to difflib.SequenceMatcher ratio otherwise.
        """
        if not s1 or not s2:
            return 0.0
        if _RAPIDFUZZ_AVAILABLE:
            try:
                # rapidfuzz.fuzz.token_sort_ratio returns 0-100
                score = fuzz.token_sort_ratio(s1, s2) / 100.0
                return float(score)
            except Exception:
                # fallback to difflib if something unexpected happens
                pass
        # difflib fallback
        try:
            sm = SequenceMatcher(None, s1, s2)
            return float(sm.ratio())
        except Exception:
            return 0.0

    def resolve_by_name(self, name: str, prefer_identifiers: bool = True) -> VendorMatch:
        """
        Resolve vendor by name.

        Steps:
        1. Normalize name and check exact matches in name index.
        2. If exact not found, perform fuzzy search across the canonical names
           and return best match above fuzzy_threshold.
        3. If prefer_identifiers is True and match candidate has identifiers,
           prefer returning that candidate (higher confidence).
        """
        cache_key = ("name", name or "")
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not name:
            result = VendorMatch(record=None, method="name", score=0.0, note="no name provided")
            self._cache[cache_key] = result
            return result

        norm = self._normalize_name(name)
        # Exact name match
        exact = self._name_index.get(norm)
        if exact:
            # If multiple records exist for the same normalized name, prefer one with identifiers
            rec = self._choose_preferred_record(exact)
            result = VendorMatch(record=rec, method="name_exact", score=1.0)
            self._cache[cache_key] = result
            return result

        # Fuzzy search: compute best candidate across known names
        best_score = 0.0
        best_record: VendorRecord | None = None
        # Iterate through indexed names and compute fuzzy score
        for indexed_name, recs in self._name_index.items():
            s = self._fuzzy_score(norm, indexed_name)
            if s > best_score:
                best_score = s
                best_record = self._choose_preferred_record(recs)

        # Decide if best_score is acceptable
        if best_score >= self.fuzzy_threshold:
            result = VendorMatch(record=best_record, method="name_fuzzy", score=best_score)
            self._cache[cache_key] = result
            return result

        # If secondary threshold met, return as lower-confidence match
        if best_score >= self.fuzzy_secondary_threshold:
            result = VendorMatch(
                record=best_record,
                method="name_fuzzy_secondary",
                score=best_score,
                note="secondary threshold met",
            )
            self._cache[cache_key] = result
            return result

        result = VendorMatch(record=None, method="name", score=0.0, note="no reliable match")
        self._cache[cache_key] = result
        return result

    def _choose_preferred_record(self, recs: list[VendorRecord]) -> VendorRecord:
        """
        Choose a preferred record from a list. Heuristic:
        - Prefer records with UEI
        - Then CAGE
        - Then DUNS
        - Otherwise return the first
        """
        for r in recs:
            if r.uei:
                return r
        for r in recs:
            if r.cage:
                return r
        for r in recs:
            if r.duns:
                return r
        return recs[0]

    # -----------------------------
    # High-level resolve entrypoint
    # -----------------------------
    def resolve(
        self,
        *,
        uei: str | None = None,
        cage: str | None = None,
        duns: str | None = None,
        name: str | None = None,
        prefer_identifiers: bool = True,
    ) -> VendorMatch:
        """
        High-level resolution method combining identifier and name strategies.

        Priority order:
        - UEI exact
        - CAGE exact
        - DUNS exact
        - Name exact
        - Name fuzzy
        """
        # Try UEI
        if uei:
            m = self.resolve_by_uei(uei)
            if m.record:
                return m

        # Try cage
        if cage:
            m = self.resolve_by_cage(cage)
            if m.record:
                return m

        # Try duns
        if duns:
            m = self.resolve_by_duns(duns)
            if m.record:
                return m

        # Name-based fallback
        if name:
            m = self.resolve_by_name(name, prefer_identifiers=prefer_identifiers)
            if m.record:
                return m

        return VendorMatch(record=None, method="none", score=0.0, note="no match found")

    # -----------------------------
    # Cross-walk / CRUD helpers
    # -----------------------------
    def add_record(self, rec: VendorRecord) -> None:
        """Add a new vendor record to indices at runtime (useful for interactive flows)."""
        if rec.uei:
            self._uei_index[str(rec.uei).strip().upper()] = rec
        if rec.cage:
            self._cage_index[str(rec.cage).strip().upper()] = rec
        if rec.duns:
            self._duns_index[str(rec.duns).strip()] = rec
        nm = self._normalize_name(rec.name)
        self._name_index.setdefault(nm, []).append(rec)
        # Clear caches (conservative)
        self._cache.clear()

    def remove_record_by_uei(self, uei: str) -> bool:
        """Remove a record by UEI from indices (best-effort)."""
        key = str(uei).strip().upper()
        rec = self._uei_index.pop(key, None)
        if not rec:
            return False
        # remove from other indices if present (best-effort)
        try:
            if rec.cage:
                self._cage_index.pop(str(rec.cage).strip().upper(), None)
            if rec.duns:
                self._duns_index.pop(str(rec.duns).strip(), None)
            nm = self._normalize_name(rec.name)
            lst = self._name_index.get(nm, [])
            self._name_index[nm] = [r for r in lst if r is not rec]
        except Exception:
            logger.exception("Error removing record from indices for uei=%s", uei)
        self._cache.clear()
        return True

    # -----------------------------
    # Utilities
    # -----------------------------
    def clear_cache(self) -> None:
        """Clear the match result cache."""
        self._cache.clear()

    def stats(self) -> dict[str, int]:
        """Return basic stats about the resolver indices."""
        return {
            "records_by_uei": len(self._uei_index),
            "records_by_cage": len(self._cage_index),
            "records_by_duns": len(self._duns_index),
            "unique_names": len(self._name_index),
            "cache_entries": len(self._cache),
        }


# Module-level convenience factory
def build_resolver_from_iterable(
    iterable: Iterable[dict[str, object]], fuzzy_threshold: float = 0.9
) -> VendorResolver:
    """
    Build a VendorResolver from an iterable of mapping-like records.

    Each input dict may contain keys: 'uei', 'cage', 'duns', 'name', and optional 'metadata'.
    """
    records = []
    for item in iterable:
        uei = item.get("uei") or item.get("UEI") or item.get("uei_string")
        cage = item.get("cage") or item.get("CAGE")
        duns = item.get("duns") or item.get("DUNS")
        name = item.get("name") or item.get("company") or item.get("org")
        if not name:
            # skip rows without a name; they are not resolvable
            continue
        rec = VendorRecord(
            uei=uei, cage=cage, duns=duns, name=str(name), metadata=item.get("metadata", {})
        )
        records.append(rec)
    return VendorResolver(records, fuzzy_threshold=fuzzy_threshold)
