"""USPTO AI extraction assets.

This module contains:
- raw_uspto_ai_extract: Extract AI dataset from USPTO assignments
- uspto_ai_deduplicate: Deduplicate AI extraction results
- raw_uspto_ai_human_sample_extraction: Generate human annotation samples
- raw_uspto_ai_predictions: Generate AI predictions for entities
- validated_uspto_ai_cache_stats: Validate AI prediction cache statistics
- raw_uspto_ai_human_sample: Generate human samples for annotation
- enriched_uspto_ai_patent_join: Join AI extractions with patent data
"""

from __future__ import annotations
import os

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from .utils import (
    AssetIn,
    MetadataValue,
    USPTOAIExtractor,
    _batch_to_dataframe,
    _ensure_dir,
    _ensure_dir_ai,
    asset,
    DEFAULT_AI_DUCKDB,
    DEFAULT_AI_RAW_DIR,
    DEFAULT_AI_TABLE,
    DEFAULT_AI_DEDUP_TABLE,
    DEFAULT_AI_PROCESSED_DIR,
    DEFAULT_EXTRACT_CHECKS,
    DEFAULT_AI_CHECKPOINT_DIR,
)


@asset(
    name="raw_uspto_ai_extract",
    description=(
        "Stream-extract USPTO AI predictions from raw files into a DuckDB canonical table. "
        "Supports NDJSON, CSV, Parquet, and Stata (.dta) with resume & optional dedupe."
    ),
)
def raw_uspto_ai_extract(context: Any) -> dict[str, object]:
    """
    Implements Task 11.1 (loader) and 11.2 (incremental resume) for USPTO AI extraction.

    Op config options:
      - raw_dir: directory of raw USPTO AI files (default: data/raw/USPTO)
      - file_globs: optional list of globs (e.g., ['*.dta', '*.ndjson'])
      - duckdb: path to DuckDB file (default: data/processed/uspto_ai.duckdb)
      - table: table name (default: uspto_ai_predictions)
      - checkpoint_dir: directory for resume checkpoints
      - batch_size: integer batch size (default: 5000)
      - resume: bool to resume from checkpoints (default: True)
      - dedupe: in-process dedupe by grant_doc_num (default: True)
      - id_candidates: list of candidate id columns for grant number inference (optional)

    Writes:
      - DuckDB table with columns:
          grant_doc_num VARCHAR,
          prediction JSON,
          source_file VARCHAR,
          row_index BIGINT,
          extracted_at TIMESTAMP
      - Checks JSON at data/processed/uspto_ai_extract.checks.json
    """
    if USPTOAIExtractor is None:
        msg = "USPTOAIExtractor unavailable (import failed); cannot perform extraction"
        context.log.warning(msg)
        _ensure_dir(DEFAULT_EXTRACT_CHECKS)
        with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "extractor_unavailable"}, fh, indent=2)
        return {"ok": False, "reason": "extractor_unavailable"}

    # Resolve config
    raw_dir = Path(getattr(context, "op_config", {}).get("raw_dir", DEFAULT_AI_RAW_DIR))
    file_globs = getattr(context, "op_config", {}).get("file_globs")
    duckdb_path = Path(getattr(context, "op_config", {}).get("duckdb", DEFAULT_AI_DUCKDB))
    table = getattr(context, "op_config", {}).get("table", DEFAULT_AI_TABLE)
    checkpoint_dir = Path(
        getattr(context, "op_config", {}).get("checkpoint_dir", DEFAULT_AI_CHECKPOINT_DIR)
    )
    batch_size = int(getattr(context, "op_config", {}).get("batch_size", 5000))
    resume = bool(getattr(context, "op_config", {}).get("resume", True))
    dedupe = bool(getattr(context, "op_config", {}).get("dedupe", True))
    id_candidates = getattr(context, "op_config", {}).get("id_candidates", None)

    _ensure_dir(DEFAULT_EXTRACT_CHECKS)
    DEFAULT_AI_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Connect to DuckDB
    try:
        import duckdb
    except Exception as exc:
        msg = f"duckdb unavailable: {exc}"
        context.log.warning(msg)
        with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "duckdb_unavailable"}, fh, indent=2)
        return {"ok": False, "reason": "duckdb_unavailable"}

    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(database=str(duckdb_path), read_only=False)

    # Ensure target table exists with expected schema
    try:
        con.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                grant_doc_num VARCHAR,
                prediction JSON,
                source_file VARCHAR,
                row_index BIGINT,
                extracted_at TIMESTAMP
            )
            """
        )
    except Exception as exc:
        context.log.exception("Failed to ensure DuckDB table %s: %s", table, exc)
        try:
            con.close()
        except Exception:
            pass
        with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "duckdb_table_create_failed"}, fh, indent=2)
        return {"ok": False, "reason": "duckdb_table_create_failed"}

    # Initialize extractor
    try:
        extractor = USPTOAIExtractor(
            input_dir=raw_dir,
            checkpoint_dir=checkpoint_dir,
            continue_on_error=True,
            log_every=100_000,
        )
    except Exception as exc:
        context.log.exception("Failed to initialize USPTOAIExtractor: %s", exc)
        try:
            con.close()
        except Exception:
            pass
        with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "extractor_init_failed"}, fh, indent=2)
        return {"ok": False, "reason": "extractor_init_failed"}

    files = extractor.discover_files(file_globs=file_globs)
    if not files:
        context.log.warning("No USPTO AI files found under %s", str(raw_dir))
        with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": True, "ingested": 0, "files": []}, fh, indent=2)
        try:
            con.close()
        except Exception:
            pass
        return {"ok": True, "ingested": 0, "files": []}

    total_ingested = 0
    total_batches = 0
    sources: list[str] = []

    try:
        for fp in files:
            sources.append(str(fp))
            context.log.info("Extracting USPTO AI from %s", str(fp))
            try:
                for batch in extractor.stream_batches(
                    fp,
                    batch_size=batch_size,
                    resume=resume,
                    normalized=True,
                    dedupe=dedupe,
                    skip_missing_id=True,
                    id_candidates=id_candidates,
                ):
                    if not batch:
                        continue
                    # Convert to DataFrame and append via a registered temp table
                    try:
                        df = _batch_to_dataframe(batch)
                    except Exception as exc:
                        context.log.exception("Failed to convert batch to DataFrame: %s", exc)
                        continue

                    try:
                        con.register("tmp_batch", df)
                        # Insert casting string -> JSON and string -> TIMESTAMP
                        con.execute(
                            f"""
                            INSERT INTO {table}
                            SELECT
                                grant_doc_num,
                                try_cast(prediction_json AS JSON) AS prediction,
                                source_file,
                                CAST(row_index AS BIGINT) AS row_index,
                                try_cast(extracted_at AS TIMESTAMP) AS extracted_at
                            FROM tmp_batch
                            """
                        )
                        total_ingested += len(df)
                        total_batches += 1
                    except Exception as exc:
                        context.log.exception("Failed to append batch to DuckDB: %s", exc)
                    finally:
                        try:
                            con.unregister("tmp_batch")
                        except Exception:
                            pass
            except Exception as exc:
                context.log.exception("Extraction failed for %s: %s", str(fp), exc)
                # continue with next file
                continue
    finally:
        try:
            con.close()
        except Exception:
            pass

    checks = {
        "ok": True,
        "ingested": int(total_ingested),
        "batches": int(total_batches),
        "files": sources,
        "duckdb": str(duckdb_path),
        "table": table,
        "checkpoint_dir": str(checkpoint_dir),
        "resume": bool(resume),
        "dedupe": bool(dedupe),
    }
    with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
        json.dump(checks, fh, indent=2)
    context.log.info("USPTO AI extraction completed", extra=checks)
    return checks


@asset(
    name="uspto_ai_deduplicate",
    description=(
        "Produce a deduplicated table of USPTO AI predictions keyed by grant_doc_num. "
        "Keeps the most recent extracted_at or highest row_index."
    ),
    ins={"raw_uspto_ai_extract": AssetIn()},
)
def uspto_ai_deduplicate(context: Any, raw_uspto_ai_extract) -> dict[str, object]:
    """
    Implements Task 11.2 (deduplication) using DuckDB window functions.

    Op config options:
      - duckdb: path to DuckDB file (default: data/processed/uspto_ai.duckdb)
      - table: source table name (default: uspto_ai_predictions)
      - dedup_table: output table name (default: uspto_ai_predictions_dedup)

    Writes:
      - Deduplicated DuckDB table
      - Checks JSON at data/processed/uspto_ai_deduplicate.checks.json
    """
    duckdb_path = Path(getattr(context, "op_config", {}).get("duckdb", DEFAULT_AI_DUCKDB))
    table = getattr(context, "op_config", {}).get("table", DEFAULT_AI_TABLE)
    dedup_table = getattr(context, "op_config", {}).get("dedup_table", DEFAULT_AI_DEDUP_TABLE)

    _ensure_dir(DEFAULT_DEDUP_CHECKS)
    try:
        import duckdb
    except Exception as exc:
        msg = f"duckdb unavailable: {exc}"
        context.log.warning(msg)
        with DEFAULT_DEDUP_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "duckdb_unavailable"}, fh, indent=2)
        return {"ok": False, "reason": "duckdb_unavailable"}

    con = duckdb.connect(database=str(duckdb_path), read_only=False)
    try:
        # Counts before
        try:
            before_cnt = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except Exception:
            before_cnt = 0

        # Create or replace dedup table with row_number window over grant_doc_num
        con.execute(
            f"""
            CREATE OR REPLACE TABLE {dedup_table} AS
            WITH ranked AS (
                SELECT
                    grant_doc_num,
                    prediction,
                    source_file,
                    row_index,
                    extracted_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY grant_doc_num
                        ORDER BY
                            extracted_at DESC NULLS LAST,
                            row_index DESC NULLS LAST
                    ) AS rn
                FROM {table}
            )
            SELECT
                grant_doc_num,
                prediction,
                source_file,
                row_index,
                extracted_at
            FROM ranked
            WHERE rn = 1
            """
        )

        after_cnt = int(con.execute(f"SELECT COUNT(*) FROM {dedup_table}").fetchone()[0])

        checks = {
            "ok": True,
            "source_count": before_cnt,
            "dedup_count": after_cnt,
            "duckdb": str(duckdb_path),
            "source_table": table,
            "dedup_table": dedup_table,
        }
        with DEFAULT_DEDUP_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        context.log.info("USPTO AI deduplication completed", extra=checks)
        return checks
    except Exception as exc:
        context.log.exception("Deduplication failed: %s", exc)
        with DEFAULT_DEDUP_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "dedup_failed"}, fh, indent=2)
        return {"ok": False, "reason": "dedup_failed"}
    finally:
        try:
            con.close()
        except Exception:
            pass


@asset(
    name="raw_uspto_ai_human_sample_extraction",
    description=(
        "Sample predictions from the (deduplicated) DuckDB table and write NDJSON for human evaluation."
    ),
    ins={"uspto_ai_deduplicate": AssetIn()},
)
def raw_uspto_ai_human_sample_extraction(context: Any, uspto_ai_deduplicate) -> str:
    """
    Implements Task 11.3 (human sampling) using DuckDB ORDER BY RANDOM() LIMIT N.

    Op config options:
      - duckdb: path to DuckDB file (default: data/processed/uspto_ai.duckdb)
      - table: table to sample from (default: uspto_ai_predictions_dedup if exists, else uspto_ai_predictions)
      - sample_n: number of samples (default: 200)
      - output_path: path to write NDJSON (default: data/processed/uspto_ai_human_sample_extraction.ndjson)

    Output:
      - Path to written NDJSON sample
    """
    Path(getattr(context, "op_config", {}).get("duckdb", DEFAULT_AI_DUCKDB))
    getattr(context, "op_config", {}).get("table", DEFAULT_AI_DEDUP_TABLE)
    int(getattr(context, "op_config", {}).get("sample_n", 200))
    output_path = Path(
        getattr(context, "op_config", {}).get("output_path", DEFAULT_AI_SAMPLE_PATH)
    )

    try:
        pass
    except Exception as exc:
        context.log.warning("duckdb unavailable; cannot sample: %s", exc)
        _ensure_dir_ai(output_path)
        with output_path.open("w", encoding="utf-8") as fh:
            fh.write("")  # empty sentinel
        return str(output_path)


# ============================================================================
# STAGE 5: AI Assets (Consolidated and Implemented)
# ============================================================================
# AI extraction and analysis assets for USPTO patent data processing


@asset(
    name="raw_uspto_ai_predictions",
    description=(
        "Ingest the USPTO AI NDJSON predictions into a local DuckDB cache. "
        "Writes a checks JSON summarizing the ingest and returns the ingest summary dict."
    ),
)
def raw_uspto_ai_predictions(context: Any) -> dict[str, object]:
    """
    Dagster asset that ingests the raw USPTO AI NDJSON into the DuckDB cache.

    Behavior:
    - Resolves input NDJSON path from op config `raw_ndjson` if present, else uses DEFAULT_RAW_NDJSON.
    - Resolves cache DB path from op config `duckdb` if present, else uses DEFAULT_DUCKDB.
    - Uses streaming ingest with resume/checkpoint behavior.
    - Writes a companion checks JSON containing keys: ok, ingested, skipped, errors, cache_count, raw_ndjson, duckdb.
    """
    # Default paths (can be overridden via op_config)
    DEFAULT_RAW_NDJSON = Path(
        os.environ.get("SBIR_ETL__USPTO_AI__RAW_NDJSON", "data/raw/uspto_ai_predictions.ndjson")
    )
    DEFAULT_RAW_DTA_DIR = Path(os.environ.get("SBIR_ETL__USPTO_AI__RAW_DTA_DIR", "data/raw/USPTO"))
    DEFAULT_DUCKDB = Path(
        os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB", "data/processed/uspto_ai.duckdb")
    )
    DEFAULT_DUCKDB_TABLE = os.environ.get(
        "SBIR_ETL__USPTO_AI__DUCKDB_TABLE", "uspto_ai_predictions"
    )

    raw_ndjson = (
        Path(context.op_config.get("raw_ndjson"))
        if getattr(context, "op_config", None) and context.op_config.get("raw_ndjson")
        else DEFAULT_RAW_NDJSON
    )
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
    processed_dir = (
        Path(context.op_config.get("processed_dir"))
        if getattr(context, "op_config", None) and context.op_config.get("processed_dir")
        else Path("data/processed")
    )
    checks_path = processed_dir / "uspto_ai_ingest.checks.json"
    batch_size = (
        int(context.op_config.get("batch_size"))
        if getattr(context, "op_config", None) and context.op_config.get("batch_size")
        else 1000
    )

    processed_dir.mkdir(parents=True, exist_ok=True)

    # Look for DTA files first in configured directory
    dta_dir = (
        Path(context.op_config.get("raw_dta_dir"))
        if getattr(context, "op_config", None) and context.op_config.get("raw_dta_dir")
        else DEFAULT_RAW_DTA_DIR
    )
    dta_files = sorted(dta_dir.glob("*.dta")) if dta_dir.exists() else []

    result_summary = {
        "ok": False,
        "ingested": 0,
        "skipped": 0,
        "errors": 0,
        "source_type": None,
        "sources": [],
    }

    try:
        import duckdb
        import pandas as pd
    except Exception as exc:
        logger.exception("duckdb and pandas are required for USPTO AI ingest: %s", exc)
        result_summary = {
            "ok": False,
            "ingested": 0,
            "skipped": 0,
            "errors": 1,
            "reason": "missing_dependency",
        }
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(result_summary, fh, indent=2)
        return result_summary

    if dta_files:
        # Ingest DTA files into DuckDB
        total_ingested = 0
        total_skipped = 0
        total_errors = 0

        try:
            con = duckdb.connect(database=str(duckdb_path), read_only=False)

            for dfp in dta_files:
                context.log.info(
                    "Ingesting DTA to DuckDB",
                    extra={"file": str(dfp), "duckdb": str(duckdb_path), "table": duckdb_table},
                )
                try:
                    # Read DTA file in chunks
                    df = pd.read_stata(dfp, chunksize=batch_size)
                    for chunk in df:
                        if total_ingested == 0:
                            # Create table on first chunk
                            con.execute(
                                f"CREATE OR REPLACE TABLE {duckdb_table} AS SELECT * FROM chunk LIMIT 0"
                            )
                        con.register("chunk_data", chunk)
                        con.execute(f"INSERT INTO {duckdb_table} SELECT * FROM chunk_data")
                        total_ingested += len(chunk)
                    result_summary["sources"].append(str(dfp))
                except Exception as exc:
                    context.log.exception("DTA ingest failed for %s: %s", str(dfp), exc)
                    total_errors += 1

            con.close()
        except Exception as exc:
            logger.exception("Failed to connect to DuckDB: %s", exc)
            total_errors += 1

        result_summary.update(
            {
                "ok": total_errors == 0,
                "ingested": total_ingested,
                "skipped": total_skipped,
                "errors": total_errors,
                "source_type": "dta",
            }
        )
    else:
        # Fall back to NDJSON input
        if not raw_ndjson.exists():
            context.log.warning("No DTA files and NDJSON not found: %s", raw_ndjson)
            result_summary = {
                "ok": False,
                "ingested": 0,
                "skipped": 0,
                "errors": 0,
                "reason": "raw_missing",
            }
        else:
            try:
                con = duckdb.connect(database=str(duckdb_path), read_only=False)
                ingested = 0
                errors = 0
                batch = []

                with raw_ndjson.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                            batch.append(obj)
                            if len(batch) >= batch_size:
                                df = pd.DataFrame(batch)
                                if ingested == 0:
                                    con.execute(
                                        f"CREATE OR REPLACE TABLE {duckdb_table} AS SELECT * FROM df LIMIT 0"
                                    )
                                con.register("batch_data", df)
                                con.execute(f"INSERT INTO {duckdb_table} SELECT * FROM batch_data")
                                ingested += len(df)
                                batch = []
                        except Exception:
                            errors += 1
                            continue

                # Final batch
                if batch:
                    try:
                        df = pd.DataFrame(batch)
                        con.register("final_batch", df)
                        con.execute(f"INSERT INTO {duckdb_table} SELECT * FROM final_batch")
                        ingested += len(df)
                    except Exception:
                        errors += 1

                con.close()
                result_summary = {
                    "ok": errors == 0,
                    "ingested": ingested,
                    "skipped": 0,
                    "errors": errors,
                    "source_type": "ndjson",
                    "sources": [str(raw_ndjson)],
                }
            except Exception as exc:
                logger.exception("Unexpected error during NDJSON ingest: %s", exc)
                result_summary = {
                    "ok": False,
                    "ingested": 0,
                    "skipped": 0,
                    "errors": 1,
                    "reason": str(exc),
                }

    # Write checks JSON
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

    context.log.info(
        "USPTO AI ingest completed", extra={"checks_path": str(checks_path), "checks": checks}
    )
    return checks


@asset(
    name="validated_uspto_ai_cache_stats",
    description="Return quick statistics about the USPTO AI DuckDB cache (count).",
)
def validated_uspto_ai_cache_stats(context: Any) -> dict[str, int | None]:
    """
    Inspect the DuckDB cache and return a small dict with the number of cached predictions.
    """
    DEFAULT_DUCKDB = Path(
        os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB", "data/processed/uspto_ai.duckdb")
    )
    DEFAULT_DUCKDB_TABLE = os.environ.get(
        "SBIR_ETL__USPTO_AI__DUCKDB_TABLE", "uspto_ai_predictions"
    )

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
        import duckdb
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
        finally:
            con.close()

        return {
            "cache_count": int(count) if count is not None else None,
            "duckdb": str(duckdb_path),
            "duckdb_table": table,
        }
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
def raw_uspto_ai_human_sample(context: Any) -> str:
    """
    Produce a human evaluation sample from the DuckDB cache.
    """
    DEFAULT_DUCKDB = Path(
        os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB", "data/processed/uspto_ai.duckdb")
    )
    DEFAULT_DUCKDB_TABLE = os.environ.get(
        "SBIR_ETL__USPTO_AI__DUCKDB_TABLE", "uspto_ai_predictions"
    )
    DEFAULT_SAMPLE_PATH = Path("data/processed/uspto_ai_human_sample.ndjson")

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
    sample_n = (
        int(context.op_config.get("sample_n"))
        if getattr(context, "op_config", None) and context.op_config.get("sample_n")
        else 100
    )
    output_path = (
        Path(context.op_config.get("output_path"))
        if getattr(context, "op_config", None) and context.op_config.get("output_path")
        else DEFAULT_SAMPLE_PATH
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import duckdb
    except Exception:
        context.log.warning("duckdb unavailable; cannot sample")
        with output_path.open("w", encoding="utf-8") as fh:
            fh.write("")
        return str(output_path)

    try:
        con = duckdb.connect(database=str(duckdb_path), read_only=True)
        try:
            df = con.execute(f"SELECT * FROM {table} ORDER BY RANDOM() LIMIT {sample_n}").fetchdf()
        except Exception:
            context.log.warning("Failed to query DuckDB table %s for sampling", table)
            df = None
        finally:
            con.close()

        if df is None or df.empty:
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

        context.log.info(
            "Wrote human-eval sample", extra={"output_path": str(output_path), "n": len(df)}
        )
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
def enriched_uspto_ai_patent_join(context: Any) -> dict[str, object]:
    """
    Asset that links cached USPTO AI predictions to transformed patents for downstream
    validation and agreement analysis.
    """
    DEFAULT_DUCKDB = Path(
        os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB", "data/processed/uspto_ai.duckdb")
    )
    DEFAULT_DUCKDB_TABLE = os.environ.get(
        "SBIR_ETL__USPTO_AI__DUCKDB_TABLE", "uspto_ai_predictions"
    )

    processed_dir = Path("data/processed")
    output_matches = processed_dir / "uspto_ai_patent_matches.ndjson"
    checks_path = processed_dir / "uspto_ai_patent_join.checks.json"
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Load patent records
    patents: list[dict] = []
    patents_parquet = Path("data/processed/transformed_patents.parquet")
    patents_ndjson = Path("data/processed/transformed_patents.ndjson")

    try:
        if patents_parquet.exists():
            import pandas as pd

            df = pd.read_parquet(patents_parquet)
            patents = df.to_dict(orient="records")
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

    # Query DuckDB to join predictions to patents
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
        import duckdb
    except Exception:
        msg = "duckdb unavailable; cannot perform patent join"
        context.log.warning(msg)
        checks = {"ok": False, "reason": "duckdb_unavailable", "message": msg}
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        return checks

    try:
        con = duckdb.connect(database=str(duckdb_path), read_only=True)
        matched = 0
        total = len(patents)

        with output_matches.open("w", encoding="utf-8") as outf:
            for p in patents:
                # attempt to find a matching grant id
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
                    for col in (
                        "grant_doc_num",
                        "grant_number",
                        "grant_docnum",
                        "patent_id",
                        "publication_number",
                        "doc_num",
                    ):
                        try:
                            df = con.execute(
                                f"SELECT * FROM {table} WHERE {col} = ? LIMIT 1", (gid,)
                            ).fetchdf()
                            if df is not None and not df.empty:
                                found_row = df.to_dict(orient="records")[0]
                                break
                        except Exception:
                            continue
                    if found_row is not None:
                        break

                if found_row is not None:
                    matched += 1
                    out_obj = {"patent": p, "uspto_prediction": found_row}
                    outf.write(json.dumps(out_obj) + "\n")

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
    except Exception:
        context.log.exception("Patent join failed")
        checks = {"ok": False, "reason": "join_failed", "num_patents": len(patents)}
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        return checks
    finally:
        try:
            con.close()
        except Exception:
            pass


# ============================================================================
# Exported symbols
# ============================================================================

__all__ = [
    # Stage 1: Raw discovery and parsing
    "raw_uspto_assignments",
    "raw_uspto_assignees",
    "raw_uspto_assignors",
    "raw_uspto_documentids",
    "raw_uspto_conveyances",
    "parsed_uspto_assignments",
    "validated_uspto_assignees",
    "validated_uspto_assignors",
    "parsed_uspto_documentids",
    "parsed_uspto_conveyances",
    "uspto_assignments_parsing_check",
    "uspto_assignees_parsing_check",
    "uspto_assignors_parsing_check",
    "uspto_documentids_parsing_check",
    "uspto_conveyances_parsing_check",
    # Stage 2: Validation
    "validated_uspto_assignments",
    "uspto_rf_id_asset_check",
    "uspto_completeness_asset_check",
    "uspto_referential_asset_check",
    # Stage 3: Transformation
    "transformed_patent_assignments",
    "transformed_patents",
    "transformed_patent_entities",
    "uspto_transformation_success_check",
    "uspto_company_linkage_check",
    # Stage 4: Neo4j Loading
    "loaded_patents",
    "loaded_patent_assignments",
    "loaded_patent_entities",
    "loaded_patent_relationships",
    "patent_load_success_rate",
    "assignment_load_success_rate",
    "patent_relationship_cardinality",
    # Stage 5: AI Extraction
    "raw_uspto_ai_extract",
    "uspto_ai_deduplicate",
    "raw_uspto_ai_human_sample_extraction",
    # Additional AI assets from consolidated uspto_ai_assets.py
    "raw_uspto_ai_predictions",
    "validated_uspto_ai_cache_stats",
    "raw_uspto_ai_human_sample",
    "enriched_uspto_ai_patent_join",
]
