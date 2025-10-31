# sbir-etl/src/assets/uspto_ai_assets.py
"""
Dagster assets for ingesting the USPTO AI predictions NDJSON into a local SQLite cache
and producing a sampled output for human evaluation.

This module is import-safe in lightweight CI/dev runners: it will degrade gracefully
if the high-level loader (`USPTOAILoader`) is unavailable at import time.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from loguru import logger

try:
    # Local import: prefer DuckDB ingest helper; fall back to the SQLite loader if available.
    # We import the DuckDB DTA ingest helper so assets can write directly to DuckDB.
    from src.ml.data.uspto_ai_loader import ingest_dta_to_duckdb, USPTOAILoader  # type: ignore
except Exception:  # pragma: no cover - defensive import
    ingest_dta_to_duckdb = None  # type: ignore
    USPTOAILoader = None  # type: ignore

# Dagster imports (kept at top-level so this module will raise if dagster is truly missing;
# if you want to be more defensive, wrap the import in try/except as done elsewhere in the repo)
try:
    from dagster import AssetExecutionContext, asset, asset_sensor, Output, AssetIn
except Exception:  # pragma: no cover - defensive import
    # Provide minimal stand-ins so static analysis tools and import-time introspection
    # in constrained environments won't fail hard when dagster is not installed.
    AssetExecutionContext = object  # type: ignore
    asset = lambda *a, **k: (lambda f: f)  # type: ignore
    Output = lambda v, **m: v  # type: ignore
    AssetIn = lambda s: None  # type: ignore

# Default locations (overridable via environment variables or op/config)
DEFAULT_RAW_NDJSON = Path(
    os.environ.get("SBIR_ETL__USPTO_AI__RAW_NDJSON", "data/raw/uspto_ai_predictions.ndjson")
)
# Prefer DTA files in data/raw/USPTO; asset will look here first
DEFAULT_RAW_DTA_DIR = Path(os.environ.get("SBIR_ETL__USPTO_AI__RAW_DTA_DIR", "data/raw/USPTO"))
# DuckDB will be the canonical store for USPTO AI predictions
DEFAULT_DUCKDB = Path(os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB", "data/processed/uspto_ai.duckdb"))
DEFAULT_PROCESSED_DIR = Path(os.environ.get("SBIR_ETL__USPTO_AI__PROCESSED_DIR", "data/processed"))
DEFAULT_SAMPLE_PATH = DEFAULT_PROCESSED_DIR / "uspto_ai_human_sample.ndjson"
DEFAULT_CHECKS_PATH = DEFAULT_PROCESSED_DIR / "uspto_ai_ingest.checks.json"
DEFAULT_DUCKDB_TABLE = os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB_TABLE", "uspto_ai_predictions")


@asset(
    name="raw_uspto_ai_predictions",
    description=(
        "Ingest the USPTO AI NDJSON predictions into a local SQLite cache. "
        "Writes a checks JSON summarizing the ingest and returns the ingest summary dict."
    ),
)
def raw_uspto_ai_predictions(context: AssetExecutionContext) -> Dict[str, object]:
    """
    Dagster asset that ingests the raw USPTO AI NDJSON into the SQLite cache.

    Behavior:
    - Resolves input NDJSON path from op config `raw_ndjson` if present, else uses DEFAULT_RAW_NDJSON.
    - Resolves cache DB path from op config `cache_db` if present, else uses DEFAULT_CACHE_DB.
    - Uses `USPTOAILoader` to perform streaming ingest with resume/checkpoint behavior.
    - Writes a companion checks JSON at `data/processed/uspto_ai_ingest.checks.json` containing
      keys: ok, ingested, skipped, errors, cache_count, raw_ndjson, cache_db.
    - If the loader implementation is unavailable, returns an explanatory checks record and writes it.
    """
    raw_ndjson = (
        Path(context.op_config.get("raw_ndjson"))
        if getattr(context, "op_config", None) and context.op_config.get("raw_ndjson")
        else DEFAULT_RAW_NDJSON
    )
    cache_db = (
        Path(context.op_config.get("cache_db"))
        if getattr(context, "op_config", None) and context.op_config.get("cache_db")
        else DEFAULT_CACHE_DB
    )
    processed_dir = (
        Path(context.op_config.get("processed_dir"))
        if getattr(context, "op_config", None) and context.op_config.get("processed_dir")
        else DEFAULT_PROCESSED_DIR
    )
    checks_path = processed_dir / (
        context.op_config.get("checks_filename")
        if getattr(context, "op_config", None) and context.op_config.get("checks_filename")
        else DEFAULT_CHECKS_PATH.name
    )

    processed_dir.mkdir(parents=True, exist_ok=True)

    if USPTOAILoader is None:
        reason = "USPTOAILoader unavailable (missing implementation or import failure)"
        logger.warning(reason)
        checks = {
            "ok": False,
            "reason": reason,
            "ingested": 0,
            "skipped": 0,
            "errors": 0,
            "cache_count": None,
            "raw_ndjson": str(raw_ndjson),
            "cache_db": str(cache_db),
        }
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        context.log.info(
            "Wrote checks JSON (loader missing)", extra={"checks_path": str(checks_path)}
        )
        return checks

    # Prefer DTA files in the configured raw DTA directory; fall back to NDJSON if no DTA present.
    processed_dir = processed_dir  # keep local name for checks path use
    batch_size = (
        int(context.op_config.get("batch_size"))
        if getattr(context, "op_config", None) and context.op_config.get("batch_size")
        else 1000
    )

    # Resolve DuckDB path & table
    duckdb_path = (
        Path(context.op_config.get("duckdb"))
        if getattr(context, "op_config", None) and context.op_config.get("duckdb")
        else DEFAULT_DUCKDB
    )
    duckdb_table = (
        context.op_config.get("duckdb_table")
        if getattr(context, "op_config", None) and context.op_config.get("duckdb_table")
        else DEFAULT_DUCKDB_TABLE
    )

    # Look for DTA files first in configured directory (op_config override allowed)
    dta_dir = (
        Path(context.op_config.get("raw_dta_dir"))
        if getattr(context, "op_config", None) and context.op_config.get("raw_dta_dir")
        else DEFAULT_RAW_DTA_DIR
    )
    dta_files = sorted([p for p in dta_dir.glob("*.dta")]) if dta_dir.exists() else []

    result_summary = {"ok": False, "ingested": 0, "skipped": 0, "errors": 0, "source_type": None, "sources": []}

    if dta_files and ingest_dta_to_duckdb is not None:
        # Ingest each DTA file into DuckDB canonical table
        total_ingested = 0
        total_skipped = 0
        total_errors = 0
        for dfp in dta_files:
            context.log.info("Ingesting DTA to DuckDB", extra={"file": str(dfp), "duckdb": str(duckdb_path), "table": duckdb_table})
            try:
                res = ingest_dta_to_duckdb(
                    dta_path=dfp,
                    duckdb_path=duckdb_path,
                    table_name=duckdb_table,
                    grant_id_candidates=None,
                    batch_size=batch_size,
                )
                total_ingested += int(res.get("ingested", 0))
                total_skipped += int(res.get("skipped", 0))
                total_errors += int(res.get("errors", 0))
                result_summary["sources"].append(str(dfp))
            except Exception as exc:
                context.log.exception("DTA ingest failed for %s: %s", str(dfp), exc)
                total_errors += 1

        result_summary.update(
            {"ok": True if total_errors == 0 else False, "ingested": total_ingested, "skipped": total_skipped, "errors": total_errors, "source_type": "dta"}
        )
    else:
        # Fall back to NDJSON input but write into DuckDB as canonical store
        ndjson_path = raw_ndjson
        try:
            if not ndjson_path.exists():
                context.log.warning("No DTA files and NDJSON not found: %s", ndjson_path)
                result_summary = {"ok": False, "ingested": 0, "skipped": 0, "errors": 0, "reason": "raw_missing"}
            else:
                # Stream NDJSON into DuckDB in batches
                try:
                    import duckdb  # type: ignore
                    import pandas as pd  # type: ignore
                except Exception as exc:
                    logger.exception("duckdb and pandas are required to ingest NDJSON into DuckDB: %s", exc)
                    result_summary = {"ok": False, "ingested": 0, "skipped": 0, "errors": 1, "reason": "missing_dependency"}
                else:
                    con = duckdb.connect(database=str(duckdb_path), read_only=False)
                    ingested = 0
                    skipped = 0
                    errors = 0
                    # Read NDJSON in streaming fashion by reading lines and batching into DataFrame
                    batch = []
                    with ndjson_path.open("r", encoding="utf-8") as fh:
                        for line in fh:
                            if not line.strip():
                                continue
                            try:
                                obj = json.loads(line)
                            except Exception:
                                errors += 1
                                continue
                            batch.append(obj)
                            if len(batch) >= batch_size:
                                df = pd.DataFrame(batch)
                                try:
                                    # Append to DuckDB table
                                    # First batch will create table if not exists
                                    if ingested == 0:
                                        con.execute(f"CREATE OR REPLACE TABLE {duckdb_table} AS SELECT * FROM df LIMIT 0", {"df": df})
                                        con.append(duckdb_table, df)  # type: ignore[attr-defined]
                                    else:
                                        con.append(duckdb_table, df)  # type: ignore[attr-defined]
                                    ingested += len(df)
                                except Exception:
                                    try:
                                        # Try insert via SQL fallback
                                        con.register("tmp_batch", df)
                                        if ingested == 0:
                                            con.execute(f"CREATE OR REPLACE TABLE {duckdb_table} AS SELECT * FROM tmp_batch LIMIT 0")
                                            con.execute(f"INSERT INTO {duckdb_table} SELECT * FROM tmp_batch")
                                        else:
                                            con.execute(f"INSERT INTO {duckdb_table} SELECT * FROM tmp_batch")
                                        ingested += len(df)
                                    except Exception:
                                        logger.exception("Failed to append NDJSON batch to DuckDB")
                                        errors += 1
                                batch = []
                    # Final batch
                    if batch:
                        try:
                            df = pd.DataFrame(batch)
                            con.append(duckdb_table, df)  # type: ignore[attr-defined]
                            ingested += len(df)
                        except Exception:
                            logger.exception("Failed to append final NDJSON batch to DuckDB")
                            errors += 1
                    try:
                        con.close()
                    except Exception:
                        pass
                    result_summary = {"ok": True if errors == 0 else False, "ingested": ingested, "skipped": skipped, "errors": errors, "source_type": "ndjson", "sources": [str(ndjson_path)]}
        except Exception as exc:
            logger.exception("Unexpected error during ingest: %s", exc)
            result_summary = {"ok": False, "ingested": 0, "skipped": 0, "errors": 1, "reason": str(exc)}

    # Write checks JSON for CI and auditing
    checks = {
        "ok": bool(result_summary.get("ok", False)),
        "ingested": int(result_summary.get("ingested", 0)),
        "skipped": int(result_summary.get("skipped", 0)),
        "errors": int(result_summary.get("errors", 0)),
        "source_type": result_summary.get("source_type"),
        "sources": result_summary.get("sources", []),
        "duckdb": str(duckdb_path),
        "duckdb_table": str(duckdb_table),
    }
    with open(checks_path, "w", encoding="utf-8") as fh:
        json.dump(checks, fh, indent=2)

    context.log.info("USPTO AI ingest completed", extra={"checks_path": str(checks_path), "checks": checks})
    return checks


@asset(
    name="validated_uspto_ai_cache_stats",
    description="Return quick statistics about the USPTO AI local cache (count).",
)
def validated_uspto_ai_cache_stats(context: AssetExecutionContext) -> Dict[str, Optional[int]]:
    """
    Inspect the SQLite cache and return a small dict with the number of cached predictions.

    - If the loader/cache is unavailable, returns {"cache_count": None}.
    """
    # Return count from DuckDB canonical store
    duckdb_path = (
        Path(context.op_config.get("duckdb"))
        if getattr(context, "op_config", None) and context.op_config.get("duckdb")
        else DEFAULT_DUCKDB
    )
    table = (
        context.op_config.get("duckdb_table")
        if getattr(context, "op_config", None) and context.op_config.get("duckdb_table")
        else DEFAULT_DUCKDB_TABLE
    )

    try:
        import duckdb  # type: ignore
    except Exception:
        context.log.warning("duckdb is unavailable; cannot compute cache stats")
        return {"cache_count": None, "duckdb": str(duckdb_path)}

    try:
        con = duckdb.connect(database=str(duckdb_path), read_only=True)
        try:
            df = con.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchdf()
            count = int(df["cnt"].iloc[0]) if not df.empty else 0
        except Exception:
            context.log.exception("Error while counting DuckDB table %s", table)
            count = None
        try:
            con.close()
        except Exception:
            pass
        return {"cache_count": int(count) if count is not None else None, "duckdb": str(duckdb_path), "duckdb_table": table}
    except Exception:
        context.log.exception("Failed to open DuckDB at %s", duckdb_path)
        return {"cache_count": None, "duckdb": str(duckdb_path)}


@asset(
    name="raw_uspto_ai_human_sample",
    description=(
        "Produce a sampled NDJSON of USPTO AI predictions intended for human evaluation. "
        "Writes the sample to `data/processed/uspto_ai_human_sample.ndjson` (or path configured via op_config)."
    ),
)
def raw_uspto_ai_human_sample(context: AssetExecutionContext) -> str:
    """
    Produce a human evaluation sample.

    Configurable via op config:
      - cache_db: path to SQLite cache (default DEFAULT_CACHE_DB)
      - sample_n: total number of examples to sample (default 100)
      - score_field: optional dotted path within prediction JSON to treat as numeric score (e.g. 'predict93_score')
      - score_bins: optional list of (low,high) tuples to stratify by score; provided as a list of strings like '0:0.5','0.5:1.0'
      - output_path: path to write NDJSON sample (default DEFAULT_SAMPLE_PATH)

    Returns:
      Path to the written NDJSON sample file.
    """
    cache_db = (
        Path(context.op_config.get("cache_db"))
        if getattr(context, "op_config", None) and context.op_config.get("cache_db")
        else DEFAULT_CACHE_DB
    )
    sample_n = (
        int(context.op_config.get("sample_n"))
        if getattr(context, "op_config", None) and context.op_config.get("sample_n")
        else 100
    )
    score_field = (
        context.op_config.get("score_field")
        if getattr(context, "op_config", None) and context.op_config.get("score_field")
        else None
    )
    output_path = (
        Path(context.op_config.get("output_path"))
        if getattr(context, "op_config", None) and context.op_config.get("output_path")
        else DEFAULT_SAMPLE_PATH
    )

    # Parse optional score_bins from op_config (list of strings like "0:0.33")
    score_bins_raw = (
        context.op_config.get("score_bins")
        if getattr(context, "op_config", None) and context.op_config.get("score_bins")
        else None
    )
    score_bins = None
    if score_bins_raw and isinstance(score_bins_raw, Iterable):
        try:
            bins = []
            for b in score_bins_raw:
                # accept "low:high" strings
                if isinstance(b, str) and ":" in b:
                    lo, hi = b.split(":", 1)
                    bins.append((float(lo), float(hi)))
            if bins:
                score_bins = bins
        except Exception:
            score_bins = None

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if USPTOAILoader is None:
        reason = "USPTOAILoader unavailable; cannot sample"
        context.log.warning(reason)
        # write an empty NDJSON file with a header comment
        with output_path.open("w", encoding="utf-8") as fh:
            fh.write("")  # empty file for consumers to detect
        context.log.info(
            "Wrote empty sample due to missing loader", extra={"output_path": str(output_path)}
        )
        return str(output_path)

    # Sample directly from DuckDB canonical store using SQL ORDER BY RANDOM()
    duckdb_path = (
        Path(context.op_config.get("duckdb"))
        if getattr(context, "op_config", None) and context.op_config.get("duckdb")
        else DEFAULT_DUCKDB
    )
    table = (
        context.op_config.get("duckdb_table")
        if getattr(context, "op_config", None) and context.op_config.get("duckdb_table")
        else DEFAULT_DUCKDB_TABLE
    )

    try:
        import duckdb  # type: ignore
    except Exception:
        msg = "duckdb unavailable; cannot sample"
        context.log.warning(msg)
        with output_path.open("w", encoding="utf-8") as fh:
            fh.write("")
        return str(output_path)

    try:
        con = duckdb.connect(database=str(duckdb_path), read_only=True)
        # Use a simple randomized sample via DuckDB SQL. If table missing, return empty sample.
        try:
            df = con.execute(f"SELECT * FROM {table} ORDER BY RANDOM() LIMIT {sample_n}").fetchdf()
        except Exception:
            context.log.warning("Failed to query DuckDB table %s for sampling", table)
            df = None
        try:
            con.close()
        except Exception:
            pass

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if df is None or df.empty:
            # Write empty file for consumers
            with output_path.open("w", encoding="utf-8") as fh:
                fh.write("")
            context.log.warning("No sample returned from DuckDB; wrote empty sample")
            return str(output_path)

        # Serialize rows to NDJSON
        with output_path.open("w", encoding="utf-8") as fh:
            for rec in df.to_dict(orient="records"):
                grant = rec.get("grant_doc_num") or rec.get("grant_number") or rec.get("patent_id")
                out = {"grant_doc_num": grant, "prediction": rec}
                fh.write(json.dumps(out) + "\n")

        context.log.info("Wrote human-eval sample", extra={"output_path": str(output_path), "n": len(df)})
        return str(output_path)
    except Exception:
        context.log.exception("Sampling from DuckDB failed")
        with output_path.open("w", encoding="utf-8") as fh:
            fh.write("")
        return str(output_path)


@asset(
    name="enriched_uspto_ai_patent_join",
    description=(
        "Join USPTO AI predictions (cached) to transformed patent records for validation "
        "and produce a summary checks JSON and an NDJSON of matches."
    ),
)
def enriched_uspto_ai_patent_join(context: AssetExecutionContext) -> Dict[str, object]:
    """
    Asset that links cached USPTO AI predictions to transformed patents for downstream
    validation and agreement analysis.

    Behavior:
    - Loads transformed patent records from `data/processed/transformed_patents.parquet`
      or `data/processed/transformed_patents.ndjson`. If neither exists, operates on a
      small sample so CI can run lightweight checks.
    - Looks up USPTO AI predictions by attempting common id fields on each patent record.
    - Writes a matched NDJSON at `data/processed/uspto_ai_patent_matches.ndjson` (one object per matched patent)
      and a companion checks JSON at `data/processed/uspto_ai_patent_join.checks.json` summarizing
      matching coverage and basic agreement statistics.
    - If the USPTO loader is unavailable, writes a checks JSON explaining the missing loader.
    """
    processed_dir = Path(os.environ.get("SBIR_ETL__USPTO_AI__PROCESSED_DIR", "data/processed"))
    output_matches = processed_dir / "uspto_ai_patent_matches.ndjson"
    checks_path = processed_dir / "uspto_ai_patent_join.checks.json"
    processed_dir.mkdir(parents=True, exist_ok=True)

    if USPTOAILoader is None:
        msg = "USPTOAILoader unavailable; cannot join predictions to patents"
        context.log.warning(msg)
        checks = {"ok": False, "reason": "loader_unavailable", "message": msg}
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        return checks

    # Load patent records
    patents: List[Dict] = []
    patents_parquet = Path("data/processed/transformed_patents.parquet")
    patents_ndjson = Path("data/processed/transformed_patents.ndjson")
    try:
        if patents_parquet.exists():
            import pandas as pd

            df = pd.read_parquet(patents_parquet)
            for _, row in df.iterrows():
                patents.append(dict(row.dropna().to_dict()))
        elif patents_ndjson.exists():
            with patents_ndjson.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        try:
                            patents.append(json.loads(line))
                        except Exception:
                            continue
        else:
            # minimal sample for CI
            patents = [
                {
                    "patent_id": "sample_p1",
                    "grant_doc_num": "US1234567B2",
                    "title": "ML for imaging",
                },
                {
                    "patent_id": "sample_p2",
                    "grant_doc_num": "US7654321B2",
                    "title": "Quantum error correction",
                },
            ]
            context.log.warning("No transformed patents found; running on a small sample")
    except Exception:
        context.log.exception("Failed to load transformed patents; aborting join")
        checks = {"ok": False, "reason": "load_error", "num_patents": 0}
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        return checks

    # Query DuckDB canonical store to join predictions to patents
    duckdb_path = Path(os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB", str(DEFAULT_DUCKDB)))
    table = os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB_TABLE", DEFAULT_DUCKDB_TABLE)

    try:
        import duckdb  # type: ignore
    except Exception:
        msg = "duckdb unavailable; cannot perform patent join"
        context.log.warning(msg)
        checks = {"ok": False, "reason": "duckdb_unavailable", "message": msg}
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        return checks

    try:
        con = duckdb.connect(database=str(duckdb_path), read_only=True)
    except Exception:
        context.log.exception("Failed to open DuckDB at %s", duckdb_path)
        checks = {"ok": False, "reason": "duckdb_open_failed", "duckdb": str(duckdb_path)}
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        return checks

    try:
        matched = 0
        total = len(patents)
        matches_written = 0
        with output_matches.open("w", encoding="utf-8") as outf:
            for p in patents:
                # attempt to find a matching grant id in common fields
                candidate_ids = [
                    p.get("grant_doc_num"),
                    p.get("grant_number"),
                    p.get("grant_docnum"),
                    p.get("patent_id"),
                    p.get("publication_number"),
                    p.get("doc_num"),
                ]
                candidate_ids = [str(x).strip() for x in candidate_ids if x]
                found_row = None
                for gid in candidate_ids:
                    # Try multiple column matches; be defensive about missing columns
                    for col in ("grant_doc_num", "grant_number", "grant_docnum", "patent_id", "publication_number", "doc_num"):
                        try:
                            df = con.execute(f"SELECT * FROM {table} WHERE {col} = ? LIMIT 1", (gid,)).fetchdf()
                            if df is not None and not df.empty:
                                found_row = df.to_dict(orient="records")[0]
                                break
                        except Exception:
                            # Column might not exist; ignore and try next
                            continue
                    if found_row is not None:
                        break
                if found_row is not None:
                    matched += 1
                    out_obj = {
                        "patent": p,
                        "uspto_prediction": found_row,
                    }
                    outf.write(json.dumps(out_obj) + "\n")
                    matches_written += 1

        checks = {
            "ok": True,
            "num_patents": total,
            "num_matched": matched,
            "match_rate": round(matched / total, 4) if total > 0 else 0.0,
            "matches_path": str(output_matches),
        }
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        context.log.info("USPTO AI patent join complete", extra=checks)
        return checks
    finally:
        try:
            con.close()
        except Exception:
            pass

        checks = {
            "ok": True,
            "num_patents": total,
            "num_matched": matched,
            "match_rate": round(matched / total, 4) if total > 0 else 0.0,
            "matches_path": str(output_matches),
        }
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        context.log.info("USPTO AI patent join complete", extra=checks)
        return checks
    finally:
        try:
            loader.close()
        except Exception:
            pass
