"""Content-addressed Parquet snapshots for candidate assertions (ADR-005 §8).

Parquet is authoritative. A snapshot is immutable once written: the writer
refuses to overwrite an existing snapshot directory, so a rule change produces
a new snapshot rather than mutating one a study has pinned.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from sbir_etl.assertions.identifiers import canonical_payload_digest
from sbir_etl.assertions.models import (
    AssertionRecord,
    AssertionSnapshotManifest,
    InputReference,
)
from sbir_etl.assertions.validation import (
    AssertionValidationError,
    contract_key_method_counts,
    validate_snapshot_cardinality,
    validate_v1_semantics,
)

__all__ = [
    "ASSERTIONS_FILENAME",
    "MANIFEST_FILENAME",
    "SnapshotExistsError",
    "records_to_frame",
    "read_snapshot",
    "snapshot_id_for",
    "write_snapshot",
]

ASSERTIONS_FILENAME = "assertions.parquet"
MANIFEST_FILENAME = "manifest.json"


class SnapshotExistsError(FileExistsError):
    """Raised when a snapshot directory already exists; snapshots are immutable."""


def snapshot_id_for(records: Sequence[AssertionRecord]) -> str:
    """Derive the snapshot identity from its member revisions.

    Order-independent: the same set of revisions always yields the same
    snapshot id, so a producer reordering rows does not fork identity.
    """
    return canonical_payload_digest(
        {"revisions": sorted(record.assertion_revision_id for record in records)}
    )


def records_to_frame(records: Sequence[AssertionRecord]) -> pd.DataFrame:
    """Flatten records to a stable, column-ordered frame.

    Dimensions and actions are serialized as canonical JSON rather than
    exploded, so one row is one assertion revision and no dimension is dropped
    on the way to storage.
    """
    rows = []
    for record in records:
        payload = record.revision_payload()
        rows.append(
            {
                "assertion_id": record.assertion_id,
                "assertion_revision_id": record.assertion_revision_id,
                "claim_family": record.claim_family,
                "source_row_key": record.source_row_key,
                "contract_key": record.contract_key,
                "contract_key_method": record.contract_key_method.value,
                "detector_method": record.detector_method,
                "method_run_id": record.method_run_id,
                "claim_status": record.claim_status.value,
                "support_class": record.support_class.value,
                "permitted_use": record.permitted_use.value,
                "dimensions_json": json.dumps(
                    payload["dimensions"],
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ),
                "actions_json": json.dumps(
                    payload["actions"],
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ),
                "detector_selected_action_key": record.detector_selected_action_key,
                "earliest_award_action_key": record.earliest_award_action_key,
                "earliest_award_action_date": record.earliest_award_action_date,
                "earliest_positive_obligation_action_key": record.earliest_positive_obligation_action_key,
                "earliest_positive_obligation_action_date": record.earliest_positive_obligation_action_date,
                "award_anchor_latency_days": record.award_anchor_latency_days,
                "cet_area": record.cet_area,
                "created_at": record.created_at,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise AssertionValidationError("refusing to write an empty assertion snapshot")
    return frame.sort_values("assertion_revision_id", ignore_index=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_snapshot(
    records: Sequence[AssertionRecord],
    *,
    root: Path,
    rule_versions: dict[str, str],
    inputs: Sequence[InputReference],
    as_of_utc: datetime | None = None,
) -> tuple[Path, AssertionSnapshotManifest]:
    """Write one immutable snapshot and its manifest; return both."""
    for record in records:
        validate_v1_semantics(record)
    validate_snapshot_cardinality(records)

    snapshot_id = snapshot_id_for(records)
    directory = Path(root) / snapshot_id
    if directory.exists():
        raise SnapshotExistsError(
            f"snapshot {snapshot_id} already exists at {directory}; snapshots are "
            "immutable, so publish a new snapshot instead of overwriting one a "
            "study may have pinned"
        )
    directory.mkdir(parents=True)

    frame = records_to_frame(records)
    assertions_path = directory / ASSERTIONS_FILENAME
    frame.to_parquet(assertions_path, index=False)

    manifest = AssertionSnapshotManifest(
        snapshot_id=snapshot_id,
        as_of_utc=as_of_utc or datetime.now(UTC),
        rule_versions=dict(rule_versions),
        inputs=tuple(inputs),
        outputs=(
            InputReference(
                name="assertions",
                path=str(Path(snapshot_id) / ASSERTIONS_FILENAME),
                sha256=_sha256_file(assertions_path),
                n=len(frame),
                gitignored=True,
            ),
        ),
        assertion_count=len(records),
        logical_assertion_count=len({record.assertion_id for record in records}),
        contract_key_method_counts=contract_key_method_counts(records),
    )
    (directory / MANIFEST_FILENAME).write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return directory, manifest


def read_snapshot(directory: Path) -> tuple[pd.DataFrame, AssertionSnapshotManifest]:
    """Read a snapshot, verifying the Parquet digest against its manifest."""
    directory = Path(directory)
    manifest = AssertionSnapshotManifest.model_validate_json(
        (directory / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    assertions_path = directory / ASSERTIONS_FILENAME
    actual = _sha256_file(assertions_path)
    expected = next(output.sha256 for output in manifest.outputs if output.name == "assertions")
    if actual != expected:
        raise AssertionValidationError(
            f"snapshot {manifest.snapshot_id} failed digest verification: "
            f"expected {expected}, found {actual}"
        )
    return pd.read_parquet(assertions_path), manifest
