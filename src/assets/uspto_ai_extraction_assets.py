# sbir-etl/src/assets/uspto_ai_extraction_assets.py
"""
Dagster assets for USPTO AI dataset extraction (Task 11)

Alignment to tasks.md:
- 11.1 Add loader for USPTO AI dataset (streaming + chunking)
  -> uspto_ai_extract_to_duckdb: Streams from NDJSON/CSV/DTA/Parquet with batching
- 11.2 Add deduplication & incremental checkpointing
  -> Incremental resume via extractor checkpoints; uspto_ai_deduplicate table asset
- 11.3 Add sampling pipeline for human evaluation
  -> uspto_ai_human_sample_extraction: Writes NDJSON sample for manual QA
- 11.4 Add patent-specific extractor logic
  -> Normalizes common patent identifiers into canonical grant_doc_num

Notes:
- Import-safe: gracefully degrades when optional deps (dagster, duckdb, pandas) are missing
- Uses DuckDB for canonical store of normalized predictions
- Checkpoints written under data/cache/uspto_ai_checkpoints
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# Optional logger (Dagster context.log is primary; fallback to std logging)
import logging

logger = logging.getLogger(__name__)

# Optional imports guarded for import-safety
try:  # Dagster scaffolding
    from dagster import AssetExecutionContext, asset, AssetIn
except Exception:  # pragma: no cover - keep import-safe
    AssetExecutionContext = object  # type: ignore

    def asset(*args, **kwargs):  # type: ignore
        def _wrap(fn):
            return fn

        return _wrap

    AssetIn = lambda *args, **kwargs: None  # type: ignore


# Internal extractor (created in src/extractors/uspto_ai_extractor.py)
try:
    from src.extractors.uspto_ai_extractor import USPTOAIExtractor  # type: ignore
except Exception:  # pragma: no cover
    USPTOAIExtractor = None  # type: ignore

# Defaults and env-configurable paths
DEFAULT_RAW_DIR = Path(os.environ.get("SBIR_ETL__USPTO_AI__RAW_DIR", "data/raw/USPTO"))
DEFAULT_CHECKPOINT_DIR = Path(
    os.environ.get("SBIR_ETL__USPTO_AI__CHECKPOINT_DIR", "data/cache/uspto_ai_checkpoints")
)
DEFAULT_DUCKDB = Path(
    os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB", "data/processed/uspto_ai.duckdb")
)
DEFAULT_TABLE = os.environ.get("SBIR_ETL__USPTO_AI__DUCKDB_TABLE", "uspto_ai_predictions")
DEFAULT_DEDUP_TABLE = os.environ.get(
    "SBIR_ETL__USPTO_AI__DUCKDB_TABLE_DEDUP", f"{DEFAULT_TABLE}_dedup"
)
DEFAULT_PROCESSED_DIR = Path(os.environ.get("SBIR_ETL__USPTO_AI__PROCESSED_DIR", "data/processed"))
DEFAULT_SAMPLE_PATH = DEFAULT_PROCESSED_DIR / "uspto_ai_human_sample_extraction.ndjson"
DEFAULT_EXTRACT_CHECKS = DEFAULT_PROCESSED_DIR / "uspto_ai_extract.checks.json"
DEFAULT_DEDUP_CHECKS = DEFAULT_PROCESSED_DIR / "uspto_ai_deduplicate.checks.json"


def _ensure_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def _batch_to_dataframe(batch: List[Dict]):
    """
    Convert a normalized batch into a pandas DataFrame using only lightweight fields:
      - grant_doc_num
      - prediction_json (stringified JSON)
      - source_file
      - row_index
      - extracted_at
    """
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("pandas is required to convert batches to DataFrame") from exc

    rows = []
    for rec in batch:
        rows.append(
            {
                "grant_doc_num": rec.get("grant_doc_num"),
                "prediction_json": json.dumps(rec.get("prediction", {}), ensure_ascii=False),
                "source_file": (rec.get("_meta") or {}).get("source_file"),
                "row_index": (rec.get("_meta") or {}).get("row_index"),
                "extracted_at": (rec.get("_meta") or {}).get("extracted_at"),
            }
        )
    return pd.DataFrame(rows)


@asset(
    name="uspto_ai_extract_to_duckdb",
    description=(
        "Stream-extract USPTO AI predictions from raw files into a DuckDB canonical table. "
        "Supports NDJSON, CSV, Parquet, and Stata (.dta) with resume & optional dedupe."
    ),
)
def uspto_ai_extract_to_duckdb(context) -> Dict[str, object]:
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
        context.log.warning(msg)  # type: ignore[attr-defined]
        _ensure_dir(DEFAULT_EXTRACT_CHECKS)
        with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "extractor_unavailable"}, fh, indent=2)
        return {"ok": False, "reason": "extractor_unavailable"}

    # Resolve config
    raw_dir = Path(getattr(context, "op_config", {}).get("raw_dir", DEFAULT_RAW_DIR))  # type: ignore[attr-defined]
    file_globs = getattr(context, "op_config", {}).get("file_globs")  # type: ignore[attr-defined]
    duckdb_path = Path(getattr(context, "op_config", {}).get("duckdb", DEFAULT_DUCKDB))  # type: ignore[attr-defined]
    table = getattr(context, "op_config", {}).get("table", DEFAULT_TABLE)  # type: ignore[attr-defined]
    checkpoint_dir = Path(
        getattr(context, "op_config", {}).get("checkpoint_dir", DEFAULT_CHECKPOINT_DIR)  # type: ignore[attr-defined]
    )
    batch_size = int(getattr(context, "op_config", {}).get("batch_size", 5000))  # type: ignore[attr-defined]
    resume = bool(getattr(context, "op_config", {}).get("resume", True))  # type: ignore[attr-defined]
    dedupe = bool(getattr(context, "op_config", {}).get("dedupe", True))  # type: ignore[attr-defined]
    id_candidates = getattr(context, "op_config", {}).get("id_candidates", None)  # type: ignore[attr-defined]

    _ensure_dir(DEFAULT_EXTRACT_CHECKS)
    DEFAULT_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Connect to DuckDB
    try:
        import duckdb  # type: ignore
    except Exception as exc:
        msg = f"duckdb unavailable: {exc}"
        context.log.warning(msg)  # type: ignore[attr-defined]
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
        context.log.exception("Failed to ensure DuckDB table %s: %s", table, exc)  # type: ignore[attr-defined]
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
        context.log.exception("Failed to initialize USPTOAIExtractor: %s", exc)  # type: ignore[attr-defined]
        try:
            con.close()
        except Exception:
            pass
        with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "extractor_init_failed"}, fh, indent=2)
        return {"ok": False, "reason": "extractor_init_failed"}

    files = extractor.discover_files(file_globs=file_globs)
    if not files:
        context.log.warning("No USPTO AI files found under %s", str(raw_dir))  # type: ignore[attr-defined]
        with DEFAULT_EXTRACT_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": True, "ingested": 0, "files": []}, fh, indent=2)
        try:
            con.close()
        except Exception:
            pass
        return {"ok": True, "ingested": 0, "files": []}

    total_ingested = 0
    total_batches = 0
    sources: List[str] = []

    try:
        for fp in files:
            sources.append(str(fp))
            context.log.info("Extracting USPTO AI from %s", str(fp))  # type: ignore[attr-defined]
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
                        context.log.exception("Failed to convert batch to DataFrame: %s", exc)  # type: ignore[attr-defined]
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
                        context.log.exception("Failed to append batch to DuckDB: %s", exc)  # type: ignore[attr-defined]
                    finally:
                        try:
                            con.unregister("tmp_batch")
                        except Exception:
                            pass
            except Exception as exc:
                context.log.exception("Extraction failed for %s: %s", str(fp), exc)  # type: ignore[attr-defined]
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
    context.log.info("USPTO AI extraction completed", extra=checks)  # type: ignore[attr-defined]
    return checks


@asset(
    name="uspto_ai_deduplicate",
    description=(
        "Produce a deduplicated table of USPTO AI predictions keyed by grant_doc_num. "
        "Keeps the most recent extracted_at or highest row_index."
    ),
    ins={"uspto_ai_extract_to_duckdb": AssetIn()},
)
def uspto_ai_deduplicate(
    context, uspto_ai_extract_to_duckdb
) -> Dict[str, object]:
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
    duckdb_path = Path(getattr(context, "op_config", {}).get("duckdb", DEFAULT_DUCKDB))  # type: ignore[attr-defined]
    table = getattr(context, "op_config", {}).get("table", DEFAULT_TABLE)  # type: ignore[attr-defined]
    dedup_table = getattr(context, "op_config", {}).get("dedup_table", DEFAULT_DEDUP_TABLE)  # type: ignore[attr-defined]

    _ensure_dir(DEFAULT_DEDUP_CHECKS)
    try:
        import duckdb  # type: ignore
    except Exception as exc:
        msg = f"duckdb unavailable: {exc}"
        context.log.warning(msg)  # type: ignore[attr-defined]
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
        context.log.info("USPTO AI deduplication completed", extra=checks)  # type: ignore[attr-defined]
        return checks
    except Exception as exc:
        context.log.exception("Deduplication failed: %s", exc)  # type: ignore[attr-defined]
        with DEFAULT_DEDUP_CHECKS.open("w", encoding="utf-8") as fh:
            json.dump({"ok": False, "reason": "dedup_failed"}, fh, indent=2)
        return {"ok": False, "reason": "dedup_failed"}
    finally:
        try:
            con.close()
        except Exception:
            pass


@asset(
    name="uspto_ai_human_sample_extraction",
    description=(
        "Sample predictions from the (deduplicated) DuckDB table and write NDJSON for human evaluation."
    ),
    ins={"uspto_ai_deduplicate": AssetIn()},
)
def uspto_ai_human_sample_extraction(context, uspto_ai_deduplicate) -> str:
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
    duckdb_path = Path(getattr(context, "op_config", {}).get("duckdb", DEFAULT_DUCKDB))  # type: ignore[attr-defined]
    table = getattr(context, "op_config", {}).get("table", DEFAULT_DEDUP_TABLE)  # type: ignore[attr-defined]
    sample_n = int(getattr(context, "op_config", {}).get("sample_n", 200))  # type: ignore[attr-defined]
    output_path = Path(
        getattr(context, "op_config", {}).get("output_path", DEFAULT_SAMPLE_PATH)  # type: ignore[attr-defined]
    )

    try:
        import duckdb  # type: ignore
    except Exception as exc:
        context.log.warning("duckdb unavailable; cannot sample: %s", exc)  # type: ignore[attr-defined]
        _ensure_dir(output_path)
        with output_path.open("w", encoding="utf-8") as fh:
            fh.write("")  # empty sentinel
        return str(output_path)

    _ensure_dir(output_path)

    con = duckdb.connect(database=str(duckdb_path), read_only=True)
    try:
        # If configured table doesn't exist, fall back to primary table
        try:
            _ = con.execute(
                f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table}'"
            ).fetchone()[0]
            table_exists = bool(_)
        except Exception:
            table_exists = False

        if not table_exists:
            # fallback to DEFAULT_TABLE
            table = DEFAULT_TABLE

        df = con.execute(
            f"""
            SELECT grant_doc_num, prediction
            FROM {table}
            USING SAMPLE {max(sample_n, 1)} ROWS -- faster sampling for large tables
            """
        ).fetchdf()

        with output_path.open("w", encoding="utf-8") as fh:
            if df is not None and not df.empty:
                for rec in df.to_dict(orient="records"):
                    # prediction column is DuckDB JSON type -> Python dict
                    obj = {
                        "grant_doc_num": rec.get("grant_doc_num"),
                        "prediction": rec.get("prediction"),
                    }
                    fh.write(json.dumps(obj) + "\n")
            else:
                # Write empty sentinel
                fh.write("")
        context.log.info(  # type: ignore[attr-defined]
            "Wrote human-eval sample",
            extra={"path": str(output_path), "n": 0 if df is None else len(df)},
        )
        return str(output_path)
    except Exception as exc:
        context.log.exception("Sampling failed: %s", exc)  # type: ignore[attr-defined]
        with output_path.open("w", encoding="utf-8") as fh:
            fh.write("")
        return str(output_path)
    finally:
        try:
            con.close()
        except Exception:
            pass
