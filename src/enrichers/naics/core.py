"""NAICS enrichment utilities.

This module provides a pragmatic, incremental NAICS index builder that streams the
USAspending pg_dump `.dat.gz` files inside the provided zip and heuristically
extracts NAICS candidates mapped to award IDs and recipient identifiers.

The implementation intentionally uses conservative heuristics and supports a
`sample_only` mode (limits files/lines processed) to allow quick validation in
development environments. The resulting compact index is persisted as Parquet
for fast joins in downstream enrichment.
"""

from __future__ import annotations

import gzip
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


NAICS_RE = re.compile(r"\b(0*\d{2,6})\b")
RECIPIENT_UEI_RE = re.compile(r"\b[A-Z0-9]{8,20}\b")


@dataclass
class NAICSEnricherConfig:
    zip_path: str
    cache_path: str = "data/processed/usaspending/naics_index.parquet"
    sample_only: bool = True
    max_files: int = 6
    max_lines_per_file: int = 1000


class NAICSEnricher:
    def __init__(self, config: NAICSEnricherConfig):
        self.config = config
        self.award_map: dict[str, set[str]] = {}
        self.recipient_map: dict[str, set[str]] = {}
        # optional canonical NAICS set (loaded from data/reference/naics_codes.txt if present)
        self.valid_naics_set: set[str] = set()
        ref = Path("data/reference/naics_codes.txt")
        if ref.exists():
            try:
                for line in ref.read_text().splitlines():
                    s = line.strip()
                    if s:
                        self.valid_naics_set.add(s)
            except Exception:
                # ignore failures reading the optional reference list
                self.valid_naics_set = set()

    def load_usaspending_index(self, force: bool = False) -> None:
        cache = Path(self.config.cache_path)
        from src.utils.common.path_utils import ensure_parent_dir

        ensure_parent_dir(cache)
        if cache.exists() and not force:
            logger.info("Loading persisted NAICS index from %s", cache)
            df = pd.read_parquet(cache)
            # reconstruct maps
            for _, row in df.iterrows():
                key_type = row["key_type"]
                key = row["key"]
                raw = row["naics_candidates"]
                naics: set[Any] = set()
                if raw is None:
                    naics = set()
                else:
                    # handle lists, tuples, numpy arrays, and JSON strings
                    try:
                        if isinstance(raw, list | tuple | set):
                            naics = set(raw)
                        else:
                            # numpy arrays have .tolist()
                            if hasattr(raw, "tolist"):
                                naics = set(raw.tolist())
                            else:
                                # fallback: try to parse as JSON string
                                try:
                                    parsed = json.loads(raw)
                                    if isinstance(parsed, list | tuple):
                                        naics = set(parsed)
                                except Exception:
                                    naics = set()
                    except Exception:
                        naics = set()
                if key_type == "award":
                    self.award_map[key] = naics
                else:
                    self.recipient_map[key] = naics
            return

        zip_path = Path(self.config.zip_path)
        if not zip_path.exists():
            raise FileNotFoundError(f"USAspending zip not found: {zip_path}")

        file_count = 0
        with zipfile.ZipFile(zip_path, "r") as z:
            members = [
                n
                for n in z.namelist()
                if n.startswith("pruned_data_store_api_dump/") and n.endswith(".dat.gz")
            ]
            logger.info(
                "Found %d pruned dump members; processing up to %d files (sample_only=%s)",
                len(members),
                self.config.max_files,
                self.config.sample_only,
            )
            for member in members:
                if self.config.sample_only and file_count >= self.config.max_files:
                    break
                file_count += 1
                logger.debug("Processing %s", member)
                try:
                    with z.open(member) as comp_fh:
                        # wrap compressed stream with gzip.GzipFile so we stream decompressed lines
                        with gzip.GzipFile(fileobj=comp_fh) as gz:
                            line_no = 0
                            for raw in gz:
                                if (
                                    self.config.sample_only
                                    and line_no >= self.config.max_lines_per_file
                                ):
                                    break
                                try:
                                    line = raw.decode("utf-8", errors="ignore")
                                except Exception:
                                    line = str(raw)
                                line_no += 1
                                self._process_line(line)
                except Exception:
                    logger.exception("Failed to process %s", member)

        # persist compact index as parquet
        def _valid_naics(code: str) -> bool:
            try:
                ci = int(code)
            except Exception:
                return False
            # must be 2-6 digits
            if ci < 0:
                return False
            code_length = len(str(ci))
            if code_length < 2 or code_length > 6:
                return False
            # conservative filters
            if code_length == 2 and ci < 11:
                return False
            if code_length >= 3 and ci < 100:
                return False
            return True

        rows = []
        for k, s in self.award_map.items():
            filtered = sorted([c for c in s if _valid_naics(str(c))])
            if not filtered:
                continue
            rows.append({"key_type": "award", "key": str(k), "naics_candidates": filtered})
        for k, s in self.recipient_map.items():
            filtered = sorted([c for c in s if _valid_naics(str(c))])
            if not filtered:
                continue
            rows.append({"key_type": "recipient", "key": str(k), "naics_candidates": filtered})

        df = pd.DataFrame(rows)
        # ensure deterministic ordering
        df = df.sort_values(["key_type", "key"]).reset_index(drop=True)
        from src.utils.data.file_io import save_dataframe_parquet

        save_dataframe_parquet(df, cache, index=False)
        logger.info("Persisted NAICS index to %s (rows=%d)", cache, len(df))

    def _process_line(self, line: str) -> None:
        """Heuristic extraction from a single decompressed line.

        Strategy:
        - Attempt to find an award_id as the first long integer token on the line.
        - Extract NAICS-like 2-6 digit tokens (exclude probable years 1900-2099).
        - Extract possible recipient UEI tokens (alphanumeric 8-20 chars).
        - Associate found NAICS candidates with award_id and recipient candidates.
        """
        if not line or line.strip() == "":
            return

        toks = re.split(r"\s+", line)
        # award id heuristic: first token that's all digits and length >=6
        award_id = None
        for t in toks[:3]:
            if t.isdigit() and len(t) >= 6:
                award_id = t
                break

        # find naics candidates and normalize/filter
        naics = set()
        for m in NAICS_RE.finditer(line):
            code_raw = m.group(1)
            # skip tokens that parse oddly
            try:
                code_int = int(code_raw)
            except ValueError:
                continue

            # filter out probable years
            if 1900 <= code_int <= 2099:
                continue

            # normalize: drop leading zeros (store as string)
            code = str(code_int)

            # NAICS codes are hierarchical 2-6 digits. Apply conservative filters:
            # - 1-digit codes are invalid
            # - 2-digit codes should be >= 11 (valid sector codes start at 11)
            # - 3-6 digit codes should be >= 100 (avoid tiny numeric artifacts)
            if len(code) < 2:
                continue
            if len(code) == 2 and code_int < 11:
                continue
            if len(code) >= 3 and code_int < 100:
                continue

            # upper bound sanity (avoid extremely large tokens)
            if code_int > 999999:
                continue

            naics.add(code)

        if not naics:
            return

        # map to award
        if award_id:
            self.award_map.setdefault(award_id, set()).update(naics)

        # find recipient-like tokens and map
        # look for UEI-like token (alphanumeric long)
        recipient_candidates = set()
        for m in RECIPIENT_UEI_RE.finditer(line):
            tok = m.group(0)
            # skip purely numeric tokens (caught as award ids/others)
            if tok.isdigit():
                continue
            # crude filter: prefer tokens containing letters OR length between 8-20
            if any(c.isalpha() for c in tok) and len(tok) >= 6:
                recipient_candidates.add(tok)

        # also try to capture recipient names (simple heuristic: sequences of capitalized words)
        # (skipped here; recipient UEI capture usually sufficient)

        for r in recipient_candidates:
            self.recipient_map.setdefault(r, set()).update(naics)

    def enrich_awards(
        self,
        df: pd.DataFrame,
        award_id_col: str = "award_id",
        recipient_uei_col: str = "recipient_uei",
    ) -> pd.DataFrame:
        """Enrich the provided awards DataFrame with NAICS fields using the built index.

        Adds columns: `naics_assigned`, `naics_origin`, `naics_confidence`, `naics_quality_flags`, `naics_trace`.
        """
        df = df.copy()
        assigned = []
        for _, row in df.iterrows():
            naics_assigned = None
            origin = "unknown"
            conf = 0.0
            flags: list[str] = []
            trace = []

            # try award-level
            aid = str(row.get(award_id_col, "")) if award_id_col in row else ""
            if aid and aid in self.award_map and self.award_map[aid]:
                candidates = sorted(self.award_map[aid])
                naics_assigned = candidates[0]
                origin = "usaspending_award"
                conf = 0.85
                trace = [{"source": "usaspending_award", "candidates": candidates}]
            else:
                # try recipient-level
                r = str(row.get(recipient_uei_col, "")) if recipient_uei_col in row else ""
                if r and r in self.recipient_map and self.recipient_map[r]:
                    candidates = sorted(self.recipient_map[r])
                    naics_assigned = candidates[0]
                    origin = "usaspending_recipient"
                    conf = 0.7
                    trace = [{"source": "usaspending_recipient", "candidates": candidates}]
                else:
                    # leave None and add missing flag
                    flags.append("missing")

            df_val = {
                "naics_assigned": naics_assigned,
                "naics_origin": origin,
                "naics_confidence": conf,
                "naics_quality_flags": flags,
                "naics_trace": json.dumps(trace) if trace else None,
            }
            assigned.append(df_val)

        assigned_df = pd.DataFrame(assigned)
        out = pd.concat([df.reset_index(drop=True), assigned_df], axis=1)
        return out


__all__ = ["NAICSEnricher", "NAICSEnricherConfig"]
