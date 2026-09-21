#!/usr/bin/env python3
"""Acquire and verify the SBA structural-comparison source bundle.

Epistemic tier: pipelines. This command only retrieves declared bytes. It does
not compute or interpret study results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx

from sbir_etl.utils.data.file_io import file_sha256


EPISTEMIC_TIER = "pipelines"
DEFAULT_MANIFEST = Path("studies/sba-annual-report-structural-comparison/source-manifest.json")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36"
)


class SourceAcquisitionError(RuntimeError):
    """Raised when a declared source cannot be retrieved or verified."""


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceAcquisitionError(f"source manifest is unreadable: {path}: {exc}") from exc
    gate = value.get("capture_gate")
    if not isinstance(gate, dict) or gate.get("allowed") is not True:
        blockers = gate.get("blockers", []) if isinstance(gate, dict) else []
        raise SourceAcquisitionError(f"source acquisition gate is closed: {blockers}")
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources:
        raise SourceAcquisitionError("source manifest must declare at least one source")
    return value


def _verify_file(path: Path, source: dict[str, Any]) -> dict[str, Any]:
    expected_bytes = int(source["size_bytes"])
    observed_bytes = path.stat().st_size
    if observed_bytes != expected_bytes:
        raise SourceAcquisitionError(
            f"{source['source_id']} byte count mismatch: "
            f"expected {expected_bytes}, observed {observed_bytes}"
        )
    expected_sha256 = str(source["sha256"])
    observed_sha256 = file_sha256(path)
    if observed_sha256 != expected_sha256:
        raise SourceAcquisitionError(
            f"{source['source_id']} SHA-256 mismatch: "
            f"expected {expected_sha256}, observed {observed_sha256}"
        )
    return {
        "source_id": source["source_id"],
        "path": path.as_posix(),
        "sha256": observed_sha256,
        "size_bytes": observed_bytes,
        "verified": True,
    }


def _download_source(
    source: dict[str, Any],
    destination: Path,
    *,
    transport: httpx.BaseTransport | None = None,
) -> None:
    uri = source.get("durable_uri")
    if not isinstance(uri, str) or not uri:
        raise SourceAcquisitionError(f"{source['source_id']} has no durable URI")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".part",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            size_bytes = 0
            with httpx.Client(
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*;q=0.8"},
                timeout=httpx.Timeout(60.0, read=300.0),
                transport=transport,
            ) as client:
                with client.stream("GET", uri) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        temporary.write(chunk)
                        digest.update(chunk)
                        size_bytes += len(chunk)

        if size_bytes != int(source["size_bytes"]):
            raise SourceAcquisitionError(
                f"{source['source_id']} downloaded byte count mismatch: "
                f"expected {source['size_bytes']}, observed {size_bytes}"
            )
        observed_sha256 = digest.hexdigest()
        if observed_sha256 != source["sha256"]:
            raise SourceAcquisitionError(
                f"{source['source_id']} downloaded SHA-256 mismatch: "
                f"expected {source['sha256']}, observed {observed_sha256}"
            )
        os.replace(temporary_path, destination)
        temporary_path = None
    except (httpx.HTTPError, OSError) as exc:
        raise SourceAcquisitionError(
            f"failed to acquire {source.get('source_id', '<unknown>')}: {exc}"
        ) from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def acquire_sources(
    manifest_path: Path,
    destination_root: Path,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Acquire missing source files and verify the complete declared bundle."""

    manifest = _load_manifest(manifest_path)
    verified_sources: list[dict[str, Any]] = []
    for source in manifest["sources"]:
        destination = destination_root / source["local_path"]
        if not destination.is_file():
            _download_source(source, destination, transport=transport)
        verified_sources.append(_verify_file(destination, source))

    verified_tables: list[dict[str, Any]] = []
    for table in manifest.get("captured_tables", []):
        path = destination_root / table["path"]
        if not path.is_file():
            raise SourceAcquisitionError(f"captured table is missing: {path}")
        verified_tables.append(_verify_file(path, table))

    return {
        "schema_version": 1,
        "source_manifest": manifest_path.as_posix(),
        "source_manifest_sha256": file_sha256(manifest_path),
        "sources": verified_sources,
        "captured_tables": verified_tables,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--destination-root", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    """Run source acquisition and optionally write a deterministic report."""

    args = _parse_args()
    report = acquire_sources(args.manifest, args.destination_root)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report is None:
        print(rendered, end="")
    else:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
