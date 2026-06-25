"""Consortium Management Firm (CMF) registry.

The registry is the rollup-detection key: when a CMF is the recorded FPDS vendor,
its obligation total aggregates all member awards, so the award and amount cannot
be attributed to any single member (tier T2). Matching prefers UEI (stable, no
false positives) and falls back to a normalized-name match until UEIs are
verified against the authoritative USAspending ``recipient_lookup`` table.

Follows the ``NAICSToBEAMapper`` reference-data pattern: optional explicit path →
config fallback → ``pd.read_csv`` → graceful degradation to an empty registry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

DEFAULT_REGISTRY_PATH = "data/reference/cmf_registry.csv"

# Business-suffix noise stripped before comparing names. Kept deliberately small;
# the registry match is a coarse rollup-vendor screen, not entity resolution.
_SUFFIX_TOKENS = {"inc", "incorporated", "llc", "corp", "corporation", "co", "company", "ltd"}


def normalize_cmf_name(name: str | None) -> str:
    """Normalize a vendor name for registry comparison.

    Uppercase-insensitive, punctuation stripped, whitespace collapsed, and common
    business suffixes dropped so "SOSSEC, Inc." and "SOSSEC Inc" compare equal.
    """
    if not name:
        return ""
    n = re.sub(r"[^a-z0-9 ]+", " ", str(name).lower())
    tokens = [t for t in n.split() if t and t not in _SUFFIX_TOKENS]
    return " ".join(tokens)


def _split_list(value: Any) -> list[str]:
    """Split a pipe-delimited CSV cell into a clean list."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    parts = [p.strip() for p in str(value).split("|")]
    return [p for p in parts if p]


@dataclass
class CMFRecord:
    """One Consortium Management Firm."""

    cmf_id: str
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    uei: str | None = None
    cage: str | None = None
    consortia_managed: list[str] = field(default_factory=list)
    agencies: list[str] = field(default_factory=list)
    notes: str = ""
    source: str = ""

    def all_names(self) -> list[str]:
        """Canonical name plus aliases."""
        return [self.canonical_name, *self.aliases]


@dataclass
class CMFMatch:
    """Result of matching a recorded vendor against the registry."""

    record: CMFRecord
    method: str  # "uei" | "name"
    note: str = ""


class CMFRegistry:
    """In-memory registry of CMFs with UEI- and name-based rollup detection."""

    def __init__(self, records: list[CMFRecord]):
        self.records = records
        self._uei_index: dict[str, CMFRecord] = {}
        self._name_index: dict[str, CMFRecord] = {}
        for rec in records:
            if rec.uei:
                self._uei_index[rec.uei.strip().upper()] = rec
            for nm in rec.all_names():
                norm = normalize_cmf_name(nm)
                if norm:
                    self._name_index[norm] = rec

    # -- construction ---------------------------------------------------------
    @classmethod
    def from_csv(cls, path: str | Path | None = None, config: Any | None = None) -> CMFRegistry:
        """Load the registry from CSV, falling back to config then the default path."""
        if path is None:
            ot_config = getattr(config, "ot_consortium", None) if config is not None else None
            path = getattr(ot_config, "cmf_registry_path", DEFAULT_REGISTRY_PATH)
        csv_path = Path(path)
        if not csv_path.exists():
            logger.warning("CMF registry not found at {}; using empty registry", csv_path)
            return cls([])
        try:
            df = pd.read_csv(csv_path, dtype=str).fillna("")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load CMF registry {}: {}", csv_path, exc)
            return cls([])
        records = [
            CMFRecord(
                cmf_id=str(row.get("cmf_id", "")).strip(),
                canonical_name=str(row.get("canonical_name", "")).strip(),
                aliases=_split_list(row.get("aliases")),
                uei=(str(row.get("uei", "")).strip() or None),
                cage=(str(row.get("cage", "")).strip() or None),
                consortia_managed=_split_list(row.get("consortia_managed")),
                agencies=_split_list(row.get("agencies")),
                notes=str(row.get("notes", "")).strip(),
                source=str(row.get("source", "")).strip(),
            )
            for _, row in df.iterrows()
            if str(row.get("canonical_name", "")).strip()
        ]
        logger.info("Loaded {} CMF records from {}", len(records), csv_path)
        return cls(records)

    # -- matching -------------------------------------------------------------
    def match(self, *, name: str | None = None, uei: str | None = None) -> CMFMatch | None:
        """Return the CMF this recorded vendor belongs to, or None.

        UEI match is preferred (no false positives); name match is the fallback
        used until the registry's UEIs are verified.
        """
        if uei:
            rec = self._uei_index.get(uei.strip().upper())
            if rec:
                return CMFMatch(record=rec, method="uei")
        if name:
            rec = self._name_index.get(normalize_cmf_name(name))
            if rec:
                return CMFMatch(
                    record=rec,
                    method="name",
                    note="matched by normalized name; UEI not yet verified",
                )
        return None

    def has_verified_ueis(self) -> bool:
        """True if at least one CMF has a populated UEI."""
        return bool(self._uei_index)

    # -- enrichment -----------------------------------------------------------
    def enrich_ueis_from_recipient_lookup(
        self,
        recipient_lookup: pd.DataFrame,
        *,
        name_col: str = "legal_business_name",
        uei_col: str = "uei",
    ) -> int:
        """Resolve blank CMF UEIs against the authoritative recipient_lookup table.

        Matches each CMF's canonical name / aliases (normalized) to recipient
        legal names and writes the verified UEI back onto the record with
        ``source`` stamped ``recipient_lookup``. Returns the number of UEIs filled.
        Names that resolve to more than one distinct UEI are left blank and logged
        for human review — we do not guess.
        """
        if recipient_lookup is None or recipient_lookup.empty:
            return 0
        if name_col not in recipient_lookup.columns or uei_col not in recipient_lookup.columns:
            logger.warning(
                "recipient_lookup missing {!r}/{!r}; skipping CMF UEI enrichment", name_col, uei_col
            )
            return 0

        lut = recipient_lookup[[name_col, uei_col]].dropna().copy()
        lut["_norm"] = lut[name_col].map(normalize_cmf_name)

        filled = 0
        for rec in self.records:
            if rec.uei:
                continue
            norms = {normalize_cmf_name(n) for n in rec.all_names() if normalize_cmf_name(n)}
            candidates = lut[lut["_norm"].isin(norms)]
            ueis = {str(u).strip().upper() for u in candidates[uei_col] if str(u).strip()}
            if len(ueis) == 1:
                rec.uei = ueis.pop()
                rec.source = "recipient_lookup"
                self._uei_index[rec.uei] = rec
                filled += 1
            elif len(ueis) > 1:
                logger.warning(
                    "CMF {} ambiguous in recipient_lookup ({} UEIs); left blank for review",
                    rec.cmf_id,
                    len(ueis),
                )
        logger.info("Enriched {} CMF UEIs from recipient_lookup", filled)
        return filled

    def unknown_rollup_vendor_diagnostic(
        self,
        vendor_obligations: pd.DataFrame,
        *,
        name_col: str = "recipient_name",
        amount_col: str = "obligation_amount",
        top_n: int = 25,
        min_obligation: float = 1_000_000.0,
    ) -> pd.DataFrame:
        """Surface high-obligation vendors that look consortium-like but aren't registered.

        This is how the registry grows from evidence rather than guesswork: it does
        NOT mutate the registry, it returns candidates for human review. A vendor is
        flagged when its name contains a consortium-like keyword, it is not already
        a registered CMF, and its total obligation exceeds ``min_obligation``.
        """
        if vendor_obligations is None or vendor_obligations.empty:
            return pd.DataFrame(columns=["recipient_name", "total_obligation", "reason"])
        if name_col not in vendor_obligations.columns:
            return pd.DataFrame(columns=["recipient_name", "total_obligation", "reason"])

        keywords = ("consortium", "consortia", "enterprise", "technologies consortium")
        df = vendor_obligations.copy()
        amounts = (
            pd.to_numeric(df[amount_col], errors="coerce").fillna(0.0)
            if amount_col in df.columns
            else pd.Series(0.0, index=df.index)
        )
        df = df.assign(_amount=amounts)
        grouped = df.groupby(name_col, dropna=True)["_amount"].sum().reset_index()
        grouped = grouped.rename(
            columns={name_col: "recipient_name", "_amount": "total_obligation"}
        )

        rows: list[dict[str, Any]] = []
        for _, row in grouped.iterrows():
            name = str(row["recipient_name"])
            total = float(row["total_obligation"])
            norm = normalize_cmf_name(name)
            if not norm or norm in self._name_index:
                continue
            looks_consortium = any(k in name.lower() for k in keywords)
            if looks_consortium and total >= min_obligation:
                rows.append(
                    {
                        "recipient_name": name,
                        "total_obligation": total,
                        "reason": "consortium-like name not in CMF registry",
                    }
                )
        out = pd.DataFrame(rows, columns=["recipient_name", "total_obligation", "reason"])
        return (
            out.sort_values("total_obligation", ascending=False).head(top_n).reset_index(drop=True)
        )
