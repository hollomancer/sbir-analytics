"""Dagster assets for USPTO patent transformation stage."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    AssetIn,
    MetadataValue,
    asset,
    asset_check,
)

# Optional imports – degrade gracefully if heavy modules are unavailable at import time.
try:  # pragma: no cover - defensive import
    from ..extractors.uspto_extractor import USPTOExtractor
except Exception:  # pragma: no cover - degrade when dependency missing
    USPTOExtractor = None  # type: ignore

try:  # pragma: no cover - defensive import
    from ..transformers.patent_transformer import PatentAssignmentTransformer
except Exception:
    PatentAssignmentTransformer = None  # type: ignore

try:  # pragma: no cover - defensive import
    from ..models.uspto_models import PatentAssignment
except Exception:
    PatentAssignment = None  # type: ignore


DEFAULT_TRANSFORMED_DIR = Path(
    os.environ.get("SBIR_ETL__USPTO__TRANSFORM_DIR", "data/transformed/uspto")
)
TRANSFORM_SUCCESS_THRESHOLD = float(
    os.environ.get("SBIR_ETL__USPTO__TRANSFORM_SUCCESS_THRESHOLD", "0.98")
)
LINKAGE_TARGET = float(os.environ.get("SBIR_ETL__USPTO__LINKAGE_TARGET", "0.60"))


def _now_suffix() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%S")


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_sbir_index(index_path: str | None) -> dict[str, str]:
    if not index_path:
        return {}
    idx_file = Path(index_path)
    if not idx_file.exists():
        return {}
    try:
        with idx_file.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return {str(k).upper(): str(v) for k, v in data.items()}
    except Exception:  # pragma: no cover - best-effort loader
        return {}
    return {}


def _serialize_assignment(model: Any) -> dict[str, Any]:
    if model is None:
        return {}
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")  # type: ignore[attr-defined]
    if isinstance(model, dict):
        return model
    return dict(model.__dict__)


def _iter_small_sample(store: list[Any], new_item: Any, limit: int) -> None:
    if len(store) < limit:
        store.append(new_item)


def _coerce_str(val: Any) -> str | None:
    if val in (None, ""):
        return None
    return str(val)


def _combine_address(*parts: str | None) -> str | None:
    parts_clean = [
        p for p in (part.strip() if isinstance(part, str) else part for part in parts) if p
    ]
    return ", ".join(parts_clean) if parts_clean else None


def _normalize_country(country: str | None) -> str | None:
    if not country:
        return None
    c = str(country).strip().upper()
    if c in {"NOT PROVIDED", "", "UNKNOWN", "N/A"}:
        return None
    return c


@dataclass
class JoinedRow:
    data: dict[str, Any]
    rf_id: str | None


class USPTOAssignmentJoiner:
    """Join USPTO tables on rf_id and emit flattened rows for transformation."""

    def __init__(self, extractor: USPTOExtractor, chunk_size: int = 10000) -> None:
        self.extractor = extractor
        self.chunk_size = chunk_size

    def _lookup(self, files: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
        table: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for file_path in files or []:
            path = Path(file_path)
            if not path.exists():
                continue
            for row in self.extractor.stream_rows(path, chunk_size=self.chunk_size):
                rf = row.get("rf_id")
                if rf in (None, ""):
                    continue
                copied = dict(row)
                copied["_source_file"] = str(path)
                table[str(rf)].append(copied)
        return table

    @staticmethod
    def _merge_rows(
        assignment: dict[str, Any],
        assignee: dict[str, Any] | None,
        assignor: dict[str, Any] | None,
        document: dict[str, Any] | None,
        conveyance: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}

        def set_if(key: str, *values: Any) -> None:
            for value in values:
                if value not in (None, ""):
                    merged[key] = value
                    return

        # Assignment core fields
        set_if("rf_id", assignment.get("rf_id"))
        set_if("file_id", assignment.get("file_id"))
        set_if("recorded_date", assignment.get("record_dt"), assignment.get("recorded_date"))
        set_if("execution_date", assignment.get("exec_dt"), assignment.get("execution_date"))
        set_if("conveyance_text", assignment.get("convey_text"))
        merged["source_assignment"] = {
            "reel_no": assignment.get("reel_no"),
            "frame_no": assignment.get("frame_no"),
            "correspondent": assignment.get("cname"),
        }

        # Document fields
        if document:
            set_if("document_rf_id", document.get("rf_id"))
            set_if("grant_doc_num", document.get("grant_doc_num"), document.get("grant_doc_number"))
            set_if(
                "application_number",
                document.get("appno_doc_num"),
                document.get("appno_doc_number"),
            )
            set_if("publication_number", document.get("pgpub_doc_num"))
            set_if("filing_date", document.get("appno_date"))
            set_if("publication_date", document.get("pgpub_date"))
            set_if("grant_date", document.get("grant_date"))
            set_if("title", document.get("title"))
            set_if("language", document.get("lang"))

        # Assignee fields
        if assignee:
            set_if("assignee_rf_id", assignee.get("rf_id"))
            set_if("assignee_name", assignee.get("ee_name"))
            set_if("assignee_street", assignee.get("ee_address_1"))
            set_if("assignee_city", assignee.get("ee_city"))
            set_if("assignee_state", assignee.get("ee_state"))
            set_if("assignee_postal", assignee.get("ee_postcode"))
            set_if("assignee_country", _normalize_country(assignee.get("ee_country")))
            set_if(
                "assignee_address",
                _combine_address(assignee.get("ee_address_1"), assignee.get("ee_address_2")),
            )

        # Assignor fields
        if assignor:
            set_if("assignor_rf_id", assignor.get("rf_id"))
            set_if("assignor_name", assignor.get("or_name"))
            set_if("execution_date", assignor.get("exec_dt"), assignor.get("execution_date"))
            set_if("acknowledgment_date", assignor.get("ack_dt"))

        # Conveyance fields
        if conveyance:
            set_if("conveyance", conveyance.get("convey_ty"))
            merged["employer_assign"] = conveyance.get("employer_assign")

        return merged

    def iter_joined_records(
        self,
        assignment_files: Iterable[str],
        assignee_files: Iterable[str],
        assignor_files: Iterable[str],
        document_files: Iterable[str],
        conveyance_files: Iterable[str],
    ) -> Iterable[JoinedRow]:
        assignees = self._lookup(assignee_files)
        assignors = self._lookup(assignor_files)
        documents = self._lookup(document_files)
        conveyances = self._lookup(conveyance_files)

        for assignment_file in assignment_files:
            path = Path(assignment_file)
            if not path.exists():
                continue
            for assignment in self.extractor.stream_rows(path, chunk_size=self.chunk_size):
                rf = assignment.get("rf_id")
                rf_key = str(rf) if rf not in (None, "") else None
                assignee_rows = assignees.get(rf_key, [None]) if rf_key else [None]
                assignor_rows = assignors.get(rf_key, [None]) if rf_key else [None]
                document_rows = documents.get(rf_key, [None]) if rf_key else [None]
                convey_rows = conveyances.get(rf_key, [None]) if rf_key else [None]

                for ass_row, asr_row, doc_row, conv_row in product(
                    assignee_rows or [None],
                    assignor_rows or [None],
                    document_rows or [None],
                    convey_rows or [None],
                ):
                    merged = self._merge_rows(assignment, ass_row, asr_row, doc_row, conv_row)
                    merged["_source_assignment_file"] = str(path)
                    yield JoinedRow(merged, rf_key)


def _resolve_output_paths(context: AssetExecutionContext, prefix: str) -> tuple[Path, Path]:
    cfg = context.op_config or {}
    base_dir = Path(cfg.get("output_dir", DEFAULT_TRANSFORMED_DIR))
    _ensure_dir(base_dir)
    timestamp = _now_suffix()
    return base_dir / f"{prefix}_{timestamp}.jsonl", base_dir


def _load_assignments_file(path: str | None) -> Iterable[dict[str, Any]]:
    if not path:
        return []
    src = Path(path)
    if not src.exists():
        return []
    with src.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


@asset(
    description="Transform USPTO assignments into normalized PatentAssignment models",
    group_name="uspto",
    ins={
        "assignment_files": AssetIn("raw_uspto_assignments"),
        "assignee_files": AssetIn("raw_uspto_assignees"),
        "assignor_files": AssetIn("raw_uspto_assignors"),
        "documentid_files": AssetIn("raw_uspto_documentids"),
        "conveyance_files": AssetIn("raw_uspto_conveyances"),
        "validation_report": AssetIn("validated_uspto_assignments"),
    },
)
def transformed_patent_assignments(
    context: AssetExecutionContext,
    assignment_files: list[str],
    assignee_files: list[str],
    assignor_files: list[str],
    documentid_files: list[str],
    conveyance_files: list[str],
    validation_report: dict[str, Any],
) -> dict[str, Any]:
    if USPTOExtractor is None or PatentAssignmentTransformer is None:
        msg = "USPTOExtractor or PatentAssignmentTransformer unavailable"
        context.log.warning(msg)
        return {"error": msg, "total_records": 0, "success_count": 0}

    if not assignment_files:
        context.log.warning("No assignment files discovered; skipping transformation")
        return {"error": "no_assignment_files", "total_records": 0, "success_count": 0}

    chunk_size = int((context.op_config or {}).get("chunk_size", 10000))
    sample_limit = int((context.op_config or {}).get("sample_limit", 5))
    sbir_index = _load_sbir_index((context.op_config or {}).get("sbir_index_path"))

    output_path, base_dir = _resolve_output_paths(context, "patent_assignments")
    failure_path = base_dir / f"patent_assignment_failures_{_now_suffix()}.jsonl"

    stats = {
        "total_records": 0,
        "success_count": 0,
        "error_count": 0,
        "linked_count": 0,
    }
    samples: list[dict[str, Any]] = []

    extractor = USPTOExtractor(Path(assignment_files[0]).parent)
    joiner = USPTOAssignmentJoiner(extractor, chunk_size=chunk_size)
    transformer = PatentAssignmentTransformer(sbir_company_grant_index=sbir_index)

    failure_written = False
    with (
        output_path.open("w", encoding="utf-8") as out_fh,
        failure_path.open("w", encoding="utf-8") as fail_fh,
    ):
        for joined in joiner.iter_joined_records(
            assignment_files, assignee_files, assignor_files, documentid_files, conveyance_files
        ):
            stats["total_records"] += 1
            result = transformer.transform_row(joined.data)

            if PatentAssignment is not None and isinstance(result, PatentAssignment):
                stats["success_count"] += 1
                if result.metadata.get("linked_sbir_company"):
                    stats["linked_count"] += 1
                serialized = _serialize_assignment(result)
                out_fh.write(json.dumps(serialized) + "\n")
                _iter_small_sample(samples, result.summarize(), sample_limit)
            elif isinstance(result, dict) and "_error" not in result:
                stats["success_count"] += 1
                if result.get("metadata", {}).get("linked_sbir_company"):
                    stats["linked_count"] += 1
                out_fh.write(json.dumps(result) + "\n")
                _iter_small_sample(samples, result, sample_limit)
            else:
                stats["error_count"] += 1
                failure_written = True
                failure_payload = result if isinstance(result, dict) else {"_error": str(result)}
                failure_payload.setdefault("rf_id", joined.rf_id)
                fail_fh.write(json.dumps(failure_payload) + "\n")

    if not failure_written and failure_path.exists():
        failure_path.unlink(missing_ok=True)

    success_rate = (
        stats["success_count"] / stats["total_records"] if stats["total_records"] > 0 else 0.0
    )
    linkage_rate = (
        stats["linked_count"] / stats["success_count"] if stats["success_count"] > 0 else 0.0
    )

    metadata = {
        "output_path": str(output_path),
        "failure_path": str(failure_path) if failure_written else None,
        "total_records": stats["total_records"],
        "success_count": stats["success_count"],
        "error_count": stats["error_count"],
        "success_rate": success_rate,
        "linked_assignments": stats["linked_count"],
        "linkage_rate": linkage_rate,
        "sample": MetadataValue.json(samples),
        "validation_passed": bool(validation_report.get("overall_success", False)),
    }
    context.add_output_metadata({k: v for k, v in metadata.items() if v is not None})

    return metadata


@asset(
    description="Aggregate transformed assignments into patent-centric records",
    group_name="uspto",
    ins={"transformed_assignments": AssetIn("transformed_patent_assignments")},
)
def transformed_patents(
    context: AssetExecutionContext, transformed_assignments: dict[str, Any]
) -> dict[str, Any]:
    output_path, base_dir = _resolve_output_paths(context, "patents")
    src_path = transformed_assignments.get("output_path")
    if not src_path or not Path(src_path).exists():
        context.log.warning("No transformed assignments output available for patent aggregation")
        return {"error": "missing_assignments", "patent_count": 0}

    patents: dict[str, dict[str, Any]] = {}
    linked = 0
    for record in _load_assignments_file(src_path):
        document = record.get("document") or {}
        grant = document.get("grant_number") or document.get("publication_number")
        if not grant:
            continue
        grant = str(grant)
        entry = patents.setdefault(
            grant,
            {
                "grant_number": grant,
                "title": document.get("title"),
                "language": document.get("language"),
                "assignee_names": set(),
                "assignor_names": set(),
                "assignment_count": 0,
                "latest_recorded_date": None,
                "linked_companies": set(),
            },
        )
        entry["assignment_count"] += 1
        if record.get("assignee"):
            name = record["assignee"].get("name") if isinstance(record["assignee"], dict) else None
            if name:
                entry["assignee_names"].add(name)
        if record.get("assignor"):
            name = record["assignor"].get("name") if isinstance(record["assignor"], dict) else None
            if name:
                entry["assignor_names"].add(name)
        linked_meta = (record.get("metadata") or {}).get("linked_sbir_company")
        if linked_meta:
            entry["linked_companies"].add(linked_meta.get("company_id"))
        if record.get("recorded_date"):
            current = entry["latest_recorded_date"]
            new_date = record["recorded_date"]
            if current is None or new_date > current:
                entry["latest_recorded_date"] = new_date

    with output_path.open("w", encoding="utf-8") as fh:
        for entry in patents.values():
            entry["assignee_names"] = sorted(entry["assignee_names"])  # type: ignore
            entry["assignor_names"] = sorted(entry["assignor_names"])  # type: ignore
            entry["linked_companies"] = sorted(entry["linked_companies"])  # type: ignore
            if entry["linked_companies"]:
                linked += 1
            fh.write(json.dumps(entry) + "\n")

    metadata = {
        "output_path": str(output_path),
        "patent_count": len(patents),
        "linked_patent_count": linked,
        "linkage_rate": linked / len(patents) if patents else 0.0,
    }
    context.add_output_metadata(metadata)
    return metadata


@asset(
    description="Derive patent entity dimension (assignees + assignors)",
    group_name="uspto",
    ins={"transformed_assignments": AssetIn("transformed_patent_assignments")},
)
def transformed_patent_entities(
    context: AssetExecutionContext, transformed_assignments: dict[str, Any]
) -> dict[str, Any]:
    output_path, _ = _resolve_output_paths(context, "patent_entities")
    src_path = transformed_assignments.get("output_path")
    if not src_path or not Path(src_path).exists():
        context.log.warning("No transformed assignments output available for entity aggregation")
        return {"error": "missing_assignments", "entity_count": 0}

    entities: dict[str, dict[str, Any]] = {}

    def upsert(entity: dict[str, Any], entity_type: str, rf_id: str | None) -> None:
        if not entity:
            return
        name = entity.get("name")
        if not name:
            return
        key = f"{entity_type}:{name.upper()}"
        bucket = entities.setdefault(
            key,
            {
                "name": name,
                "entity_type": entity_type,
                "rf_ids": set(),
                "city": entity.get("city"),
                "state": entity.get("state"),
                "country": entity.get("country"),
                "linked_companies": set(),
            },
        )
        if rf_id:
            bucket["rf_ids"].add(rf_id)
        if entity.get("metadata", {}).get("linked_sbir_company"):
            bucket["linked_companies"].add(
                entity["metadata"]["linked_sbir_company"].get("company_id")
            )

    for record in _load_assignments_file(src_path):
        rf_id = record.get("rf_id")
        if isinstance(record.get("assignee"), dict):
            upsert(record["assignee"], "assignee", rf_id)
        if isinstance(record.get("assignor"), dict):
            upsert(record["assignor"], "assignor", rf_id)

    with output_path.open("w", encoding="utf-8") as fh:
        for entry in entities.values():
            entry["rf_ids"] = sorted(entry["rf_ids"])  # type: ignore
            entry["linked_companies"] = sorted(entry["linked_companies"])  # type: ignore
            fh.write(json.dumps(entry) + "\n")

    metadata = {
        "output_path": str(output_path),
        "entity_count": len(entities),
    }
    context.add_output_metadata(metadata)
    return metadata


@asset_check(
    asset=transformed_patent_assignments,
    description="Verify transformation success rate meets threshold",
)
def uspto_transformation_success_check(
    context: AssetExecutionContext, transformed_patent_assignments: dict[str, Any]
) -> AssetCheckResult:
    success_rate = transformed_patent_assignments.get("success_rate", 0.0)
    passed = success_rate >= TRANSFORM_SUCCESS_THRESHOLD
    metadata = {
        "success_rate": success_rate,
        "threshold": TRANSFORM_SUCCESS_THRESHOLD,
        "total_records": transformed_patent_assignments.get("total_records", 0),
        "success_count": transformed_patent_assignments.get("success_count", 0),
    }
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR
    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=(
            f"Transformation success rate {success_rate:.2%} "
            f"({'meets' if passed else 'below'} threshold {TRANSFORM_SUCCESS_THRESHOLD:.0%})"
        ),
        metadata=metadata,
    )


@asset_check(
    asset=transformed_patent_assignments,
    description="Ensure SBIR company linkage coverage meets target",
)
def uspto_company_linkage_check(
    context: AssetExecutionContext, transformed_patent_assignments: dict[str, Any]
) -> AssetCheckResult:
    linkage_rate = transformed_patent_assignments.get("linkage_rate", 0.0)
    passed = linkage_rate >= LINKAGE_TARGET
    metadata = {
        "linkage_rate": linkage_rate,
        "linked_assignments": transformed_patent_assignments.get("linked_assignments", 0),
        "success_count": transformed_patent_assignments.get("success_count", 0),
        "target": LINKAGE_TARGET,
    }
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR
    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=(
            f"Company linkage rate {linkage_rate:.2%} "
            f"({'meets' if passed else 'below'} target {LINKAGE_TARGET:.0%})"
        ),
        metadata=metadata,
    )


__all__ = [
    "transformed_patent_assignments",
    "transformed_patents",
    "transformed_patent_entities",
    "uspto_transformation_success_check",
    "uspto_company_linkage_check",
]
