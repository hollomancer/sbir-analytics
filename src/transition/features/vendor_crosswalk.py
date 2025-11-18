# sbir-etl/src/transition/features/vendor_crosswalk.py
"""
Vendor cross-walk and alias management.

Provides:
- CrosswalkRecord dataclass representing a canonical vendor and aliases/history
- VendorCrosswalk manager for in-memory cross-walk with persistence (Parquet/JSON/CSV/duckdb)
- Alias handling and acquisition/merger helpers

Design goals:
- Safe defaults: only require stdlib to operate. If pandas/duckdb/rapidfuzz are available,
  the module will use them to provide efficient persistence and fuzzy matching.
- Clear, auditable operations: acquisition/merge operations record provenance in metadata.
- Pluggable storage: easy to persist to Parquet/CSV or a DuckDB table.

Usage (examples):
    cw = VendorCrosswalk()
    rec = CrosswalkRecord(canonical_id="co-123", canonical_name="Acme Corporation", uei="ABC123")
    cw.add_or_merge(rec)
    cw.save_parquet("data/vendor_crosswalk.parquet")
    match = cw.find_by_any_identifier(uei="ABC123")  # returns CrosswalkRecord
    cw.handle_acquisition(acquirer_id="co-123", acquired_id="co-456", date="2024-06-01")
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from uuid import uuid4

from loguru import logger


# Optional dependencies
try:
    import pandas as pd
except Exception:
    pd = None  # type: ignore

try:
    import duckdb
except Exception:
    duckdb = None  # type: ignore

try:
    from rapidfuzz import fuzz

    _RAPIDFUZZ_AVAILABLE = True
except Exception:
    fuzz = None  # type: ignore
    _RAPIDFUZZ_AVAILABLE = False

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _normalize_identifier(val: str | None) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if s == "":
        return None
    # remove whitespace and most punctuation, preserve letters/numbers/dash/underscore
    s = re.sub(r"[^\w\-]", "", s)
    return s.upper()


def _normalize_name(name: str | None) -> str | None:
    if name is None:
        return None
    s = " ".join(str(name).strip().split())
    s = s.replace(",", " ").replace(".", " ").replace("/", " ").replace("&", " AND ")
    return s.strip()


def _fuzzy_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if _RAPIDFUZZ_AVAILABLE:
        try:
            return float(fuzz.token_sort_ratio(a, b) / 100.0)
        except Exception:
            pass
    try:
        return float(SequenceMatcher(None, a, b).ratio())
    except Exception:
        return 0.0


def _iso_date(val: str | date | datetime | None) -> str | None:
    """Format date as ISO string using centralized utility."""
    from src.utils.date_utils import format_date_iso, parse_date
    
    # Try to format directly first
    result = format_date_iso(val)
    if result is not None:
        return result
    
    # If formatting failed, try parsing first
    parsed = parse_date(val, strict=False)
    return format_date_iso(parsed) if parsed else str(val) if val else None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AliasRecord:
    name: str
    start_date: str | None = None  # ISO date
    end_date: str | None = None  # ISO date
    note: str | None = None


@dataclass
class CrosswalkRecord:
    """Canonical vendor record stored in the cross-walk."""

    canonical_id: str
    canonical_name: str
    uei: str | None = None
    cage: str | None = None
    duns: str | None = None
    aliases: list[AliasRecord] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = asdict(self)
        return d

    def normalize(self) -> None:
        self.canonical_name = _normalize_name(self.canonical_name) or self.canonical_name
        self.uei = _normalize_identifier(self.uei)
        self.cage = _normalize_identifier(self.cage)
        self.duns = _normalize_identifier(self.duns)
        for a in self.aliases:
            a.name = _normalize_name(a.name) or a.name


# ---------------------------------------------------------------------------
# Crosswalk manager
# ---------------------------------------------------------------------------


class VendorCrosswalk:
    """
    Manage an in-memory cross-walk of vendors with persistence and alias handling.

    Persistence formats supported (best-effort):
      - Parquet/CSV via pandas (if available)
      - JSON Lines (fallback)
      - DuckDB table if duckdb available (reads/writes Parquet/CSV efficiently)

    The crosswalk stores CrosswalkRecord objects keyed by `canonical_id`. It also
    maintains inverted indices on UEI/CAGE/DUNS and normalized names for fast lookup.
    """

    def __init__(self, records: Iterable[CrosswalkRecord] | None = None):
        self.records: dict[str, CrosswalkRecord] = {}
        # indices
        self._uei_index: dict[str, str] = {}
        self._cage_index: dict[str, str] = {}
        self._duns_index: dict[str, str] = {}
        self._name_index: dict[str, list[str]] = {}  # normalized name -> list of canonical_id
        if records:
            for r in records:
                self.add_or_merge(r)

    # ---------------------------
    # CRUD / index maintenance
    # ---------------------------
    def add_or_merge(self, rec: CrosswalkRecord) -> CrosswalkRecord:
        """Add a new canonical record or merge into existing by identifiers.

        Merge strategy:
         - If a record with same UEI/CAGE/DUNS exists, merge fields and aliases.
         - Else if canonical_id exists, update/replace.
         - Otherwise insert as new record.
        """
        rec.normalize()
        # Try identifier-based merge
        for ident, idx in (
            (rec.uei, self._uei_index),
            (rec.cage, self._cage_index),
            (rec.duns, self._duns_index),
        ):
            if ident and ident in idx:
                existing_id = idx[ident]
                logger.debug(
                    "Merging record %s into existing %s (by ident %s)",
                    rec.canonical_id,
                    existing_id,
                    ident,
                )
                return self._merge_into(existing_id, rec)

        # If canonical_id exists - treat as update
        if rec.canonical_id in self.records:
            logger.debug("Updating existing record by canonical_id: %s", rec.canonical_id)
            return self._merge_into(rec.canonical_id, rec)

        # Insert new
        self.records[rec.canonical_id] = rec
        if rec.uei:
            self._uei_index[rec.uei] = rec.canonical_id
        if rec.cage:
            self._cage_index[rec.cage] = rec.canonical_id
        if rec.duns:
            self._duns_index[rec.duns] = rec.canonical_id
        nm = _normalize_name(rec.canonical_name)
        if nm:
            self._name_index.setdefault(nm, []).append(rec.canonical_id)
        logger.info("Added new crosswalk record: %s (%s)", rec.canonical_id, rec.canonical_name)
        return rec

    def _merge_into(self, canonical_id: str, rec: CrosswalkRecord) -> CrosswalkRecord:
        """Merge fields of rec into existing record with canonical_id."""
        if canonical_id not in self.records:
            return self.add_or_merge(rec)
        base = self.records[canonical_id]
        # Merge identifiers if missing
        if not base.uei and rec.uei:
            base.uei = rec.uei
            self._uei_index[rec.uei] = canonical_id
        if not base.cage and rec.cage:
            base.cage = rec.cage
            self._cage_index[rec.cage] = canonical_id
        if not base.duns and rec.duns:
            base.duns = rec.duns
            self._duns_index[rec.duns] = canonical_id
        # Merge aliases (avoid duplicates)
        existing_alias_names = {a.name for a in base.aliases}
        for a in rec.aliases:
            if a.name not in existing_alias_names:
                base.aliases.append(a)
                existing_alias_names.add(a.name)
        # Merge metadata shallowly
        base.metadata.update(rec.metadata or {})
        # If canonical name differs, keep existing canonical_name but add alias
        if _normalize_name(base.canonical_name) != _normalize_name(rec.canonical_name):
            # add rec canonical name as alias if not present
            alias_name = _normalize_name(rec.canonical_name) or rec.canonical_name
            if alias_name and alias_name not in existing_alias_names:
                base.aliases.append(AliasRecord(name=alias_name, note="merged-canonical"))
        logger.info("Merged record %s into %s", rec.canonical_id, canonical_id)
        return base

    def remove(self, canonical_id: str) -> bool:
        """Remove a record by canonical_id and clean indices."""
        if canonical_id not in self.records:
            return False
        rec = self.records.pop(canonical_id)
        if rec.uei:
            self._uei_index.pop(rec.uei, None)
        if rec.cage:
            self._cage_index.pop(rec.cage, None)
        if rec.duns:
            self._duns_index.pop(rec.duns, None)
        nm = _normalize_name(rec.canonical_name)
        if nm and nm in self._name_index:
            self._name_index[nm] = [cid for cid in self._name_index[nm] if cid != canonical_id]
            if not self._name_index[nm]:
                self._name_index.pop(nm, None)
        logger.info("Removed crosswalk record %s", canonical_id)
        return True

    # ---------------------------
    # Lookup methods
    # ---------------------------
    def find_by_uei(self, uei: str) -> CrosswalkRecord | None:
        key = _normalize_identifier(uei)
        if not key:
            return None
        cid = self._uei_index.get(key)
        return self.records.get(cid) if cid else None

    def find_by_cage(self, cage: str) -> CrosswalkRecord | None:
        key = _normalize_identifier(cage)
        if not key:
            return None
        cid = self._cage_index.get(key)
        return self.records.get(cid) if cid else None

    def find_by_duns(self, duns: str) -> CrosswalkRecord | None:
        key = _normalize_identifier(duns)
        if not key:
            return None
        cid = self._duns_index.get(key)
        return self.records.get(cid) if cid else None

    def find_by_name(
        self, name: str, fuzzy_threshold: float = 0.9
    ) -> tuple[CrosswalkRecord, float] | None:
        """
        Find best matching canonical record by name. Returns (record, score) or None.
        """
        if not name:
            return None
        norm = _normalize_name(name)
        # exact match
        cids = self._name_index.get(norm)
        if cids:
            return self.records[cids[0]], 1.0
        # fuzzy choose best across canonical names
        best_score = 0.0
        best_cid = None
        for canon_name, cid_list in self._name_index.items():
            score = _fuzzy_score(norm, canon_name)
            if score > best_score:
                best_score = score
                best_cid = cid_list[0]
        if best_score >= fuzzy_threshold and best_cid:
            return self.records[best_cid], best_score
        return None

    def find_by_any(
        self,
        uei: str | None = None,
        cage: str | None = None,
        duns: str | None = None,
        name: str | None = None,
        fuzzy_threshold: float = 0.9,
    ) -> tuple[CrosswalkRecord, str, float] | None:
        """
        Attempt to find a record using available identifiers, returning (record, method, score).
        """
        if uei:
            r = self.find_by_uei(uei)
            if r:
                return r, "uei", 1.0
        if cage:
            r = self.find_by_cage(cage)
            if r:
                return r, "cage", 1.0
        if duns:
            r = self.find_by_duns(duns)
            if r:
                return r, "duns", 1.0
        if name:
            r = self.find_by_name(name, fuzzy_threshold=fuzzy_threshold)
            if r:
                rec, score = r
                return rec, "name", score
        return None

    # ---------------------------
    # Alias & acquisition handling
    # ---------------------------
    def add_alias(
        self,
        canonical_id: str,
        alias_name: str,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        note: str | None = None,
    ) -> bool:
        """Add an alias to the canonical record and update name index."""
        if canonical_id not in self.records:
            return False
        rec = self.records[canonical_id]
        alias_name_norm = _normalize_name(alias_name) or alias_name
        # avoid duplicates
        if any(a.name == alias_name_norm for a in rec.aliases):
            return True
        ad = AliasRecord(
            name=alias_name_norm,
            start_date=_iso_date(start_date),
            end_date=_iso_date(end_date),
            note=note,
        )
        rec.aliases.append(ad)
        # update name index
        self._name_index.setdefault(alias_name_norm, []).append(canonical_id)
        logger.info("Added alias '%s' to %s", alias_name, canonical_id)
        return True

    def handle_acquisition(
        self,
        acquirer_id: str,
        acquired_id: str,
        date_of_acquisition: date | str | None = None,
        merge: bool = True,
        note: str | None = None,
    ) -> bool:
        """
        Handle company acquisition/name-change events.

        If merge=True, merge acquired record into acquirer record:
         - Combine identifiers (UEI/CAGE/DUNS) where missing
         - Move canonical name of acquired into aliases
         - Record provenance metadata on acquirer record
        If merge=False, add acquisition alias on acquirer and mark acquired record with metadata about being acquired.
        """
        if acquirer_id not in self.records or acquired_id not in self.records:
            logger.warning("Acquirer or acquired id not found: %s, %s", acquirer_id, acquired_id)
            return False
        acq = self.records[acquirer_id]
        target = self.records[acquired_id]
        acq.metadata.setdefault("acquisitions", []).append(
            {"acquired_id": acquired_id, "date": _iso_date(date_of_acquisition), "note": note}
        )
        target.metadata.setdefault("acquired_by", []).append(
            {"acquirer_id": acquirer_id, "date": _iso_date(date_of_acquisition), "note": note}
        )
        # add acquired canonical name as alias on acquirer
        try:
            self.add_alias(
                acquirer_id,
                target.canonical_name,
                start_date=_iso_date(date_of_acquisition),
                note=f"acquired: {acquired_id}",
            )
        except Exception:
            pass
        if merge:
            # merge identifiers and aliases
            logger.info("Merging acquired %s into acquirer %s", acquired_id, acquirer_id)
            self._merge_into(acquirer_id, target)
            # remove acquired record after merge and keep provenance in metadata
            self.remove(acquired_id)
        return True

    # ---------------------------
    # Persistence helpers
    # ---------------------------
    def to_list_of_dicts(self) -> list[dict]:
        out = []
        for _cid, rec in self.records.items():
            d = rec.as_dict()
            out.append(d)
        return out

    def save_parquet(self, path: str | Path) -> None:
        """
        Save crosswalk to Parquet (one row per canonical record). Requires pandas.
        """
        if pd is None:
            raise RuntimeError("pandas is required to save to Parquet/CSV")
        rows = self.to_list_of_dicts()
        df = pd.json_normalize(rows)
        path = Path(path)
        from src.utils.file_io import save_dataframe_parquet
        
        save_dataframe_parquet(df, path, index=False)
        logger.info("VendorCrosswalk saved to parquet: %s", path)

    def save_jsonl(self, path: str | Path) -> None:
        path = Path(path)
        from src.utils.path_utils import ensure_parent_dir
        
        ensure_parent_dir(path)
        with open(path, "w", encoding="utf-8") as fh:
            for rec in self.to_list_of_dicts():
                fh.write(json.dumps(rec, default=str) + "\n")
        logger.info("VendorCrosswalk saved to jsonl: %s", path)

    def load_jsonl(self, path: str | Path) -> None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(str(path))
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                j = json.loads(line)
                # convert alias dicts to AliasRecord
                aliases = []
                for a in j.get("aliases", []) or []:
                    aliases.append(
                        AliasRecord(
                            name=a.get("name"),
                            start_date=a.get("start_date"),
                            end_date=a.get("end_date"),
                            note=a.get("note"),
                        )
                    )
                rec = CrosswalkRecord(
                    canonical_id=j.get("canonical_id") or str(uuid4()),
                    canonical_name=j.get("canonical_name") or j.get("name") or "",
                    uei=j.get("uei"),
                    cage=j.get("cage"),
                    duns=j.get("duns"),
                    aliases=aliases,
                    created_at=j.get("created_at") or _iso_date(datetime.utcnow()),
                    metadata=j.get("metadata", {}),
                )
                self.add_or_merge(rec)
        logger.info("VendorCrosswalk loaded from jsonl: %s", path)

    def save_duckdb_table(self, db_path: str, table_name: str = "vendor_crosswalk") -> None:
        if duckdb is None or pd is None:
            raise RuntimeError("duckdb and pandas required for duckdb persistence")
        conn = duckdb.connect(db_path)
        rows = self.to_list_of_dicts()
        df = pd.json_normalize(rows)
        conn.register("tmp_crosswalk", df)
        conn.execute(f"create or replace table {table_name} as select * from tmp_crosswalk")
        conn.close()
        logger.info("VendorCrosswalk saved to duckdb table %s in %s", table_name, db_path)

    def load_duckdb_table(self, db_path: str, table_name: str = "vendor_crosswalk") -> None:
        if duckdb is None or pd is None:
            raise RuntimeError("duckdb and pandas required for duckdb persistence")
        conn = duckdb.connect(db_path)
        try:
            df = conn.execute(f"select * from {table_name}").fetchdf()
        except Exception:
            conn.close()
            raise
        conn.close()
        # Convert dataframe rows into CrosswalkRecord objects
        for _, r in df.iterrows():
            aliases = []
            for a in r.get("aliases", []) or []:
                aliases.append(
                    AliasRecord(
                        name=a.get("name"),
                        start_date=a.get("start_date"),
                        end_date=a.get("end_date"),
                        note=a.get("note"),
                    )
                )
            rec = CrosswalkRecord(
                canonical_id=r.get("canonical_id") or str(uuid4()),
                canonical_name=r.get("canonical_name") or r.get("name") or "",
                uei=r.get("uei"),
                cage=r.get("cage"),
                duns=r.get("duns"),
                aliases=aliases,
                created_at=r.get("created_at") or _iso_date(datetime.utcnow()),
                metadata=r.get("metadata", {}) or {},
            )
            self.add_or_merge(rec)
        logger.info("VendorCrosswalk loaded from duckdb table %s in %s", table_name, db_path)

    # ---------------------------
    # Utilities
    # ---------------------------
    def list_records(self) -> list[CrosswalkRecord]:
        return list(self.records.values())

    def stats(self) -> dict[str, int]:
        return {
            "count": len(self.records),
            "uei_index": len(self._uei_index),
            "cage_index": len(self._cage_index),
            "duns_index": len(self._duns_index),
            "name_index": len(self._name_index),
        }
