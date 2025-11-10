"""USPTO parsing assets.

This module contains:
- parsed_uspto_assignments: Parse assignment files
- validated_uspto_assignees: Parse and validate assignee files
- validated_uspto_assignors: Parse and validate assignor files
- parsed_uspto_documentids: Parse documentids files
- parsed_uspto_conveyances: Parse conveyance files
"""

from __future__ import annotations

from typing import Any

from .utils import AssetIn, _attempt_parse_sample, asset


@asset(
    description="Attempt to parse a small sample of each discovered assignment file",
    group_name="extraction",
    ins={"raw_files": AssetIn("raw_uspto_assignments")},
)
def parsed_uspto_assignments(context, raw_files: list[str]) -> dict[str, dict]:
    """
    For each discovered raw assignment file, parse a small sample and return per-file summaries.
    """
    results: dict[str, dict] = {}
    if not raw_files:
        context.log.info("No assignment files to parse")
        return results

    for fp in raw_files:
        context.log.info("Parsing sample from assignment file", extra={"file": fp})
        summary = _attempt_parse_sample(fp, sample_limit=10)
        results[fp] = summary
        context.log.info(
            "Parsed assignment sample",
            extra={"file": fp, "sampled_rows": summary.get("sampled_rows")},
        )
    return results


@asset(
    description="Attempt to parse a small sample of each discovered assignee file",
    group_name="extraction",
    ins={"raw_files": AssetIn("raw_uspto_assignees")},
)
def validated_uspto_assignees(context, raw_files: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
    if not raw_files:
        context.log.info("No assignee files to parse")
        return results

    for fp in raw_files:
        context.log.info("Parsing sample from assignee file", extra={"file": fp})
        summary = _attempt_parse_sample(fp, sample_limit=8)
        results[fp] = summary
        context.log.info(
            "Parsed assignee sample",
            extra={"file": fp, "sampled_rows": summary.get("sampled_rows")},
        )
    return results


@asset(
    description="Attempt to parse a small sample of each discovered assignor file",
    group_name="extraction",
    ins={"raw_files": AssetIn("raw_uspto_assignors")},
)
def validated_uspto_assignors(context, raw_files: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
    if not raw_files:
        context.log.info("No assignor files to parse")
        return results

    for fp in raw_files:
        context.log.info("Parsing sample from assignor file", extra={"file": fp})
        summary = _attempt_parse_sample(fp, sample_limit=8)
        results[fp] = summary
        context.log.info(
            "Parsed assignor sample",
            extra={"file": fp, "sampled_rows": summary.get("sampled_rows")},
        )
    return results


@asset(
    description="Attempt to parse a small sample of each discovered documentid file",
    group_name="extraction",
    ins={"raw_files": AssetIn("raw_uspto_documentids")},
)
def parsed_uspto_documentids(context, raw_files: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
    if not raw_files:
        context.log.info("No documentid files to parse")
        return results

    for fp in raw_files:
        context.log.info("Parsing sample from documentid file", extra={"file": fp})
        summary = _attempt_parse_sample(fp, sample_limit=12)
        results[fp] = summary
        context.log.info(
            "Parsed documentid sample",
            extra={"file": fp, "sampled_rows": summary.get("sampled_rows")},
        )
    return results


@asset(
    description="Attempt to parse a small sample of each discovered conveyance file",
    group_name="extraction",
    ins={"raw_files": AssetIn("raw_uspto_conveyances")},
)
def parsed_uspto_conveyances(context, raw_files: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
    if not raw_files:
        context.log.info("No conveyance files to parse")
        return results

    for fp in raw_files:
        context.log.info("Parsing sample from conveyance file", extra={"file": fp})
        summary = _attempt_parse_sample(fp, sample_limit=10)
        results[fp] = summary
        context.log.info(
            "Parsed conveyance sample",
            extra={"file": fp, "sampled_rows": summary.get("sampled_rows")},
        )
    return results


# -------------------------
# Asset checks (per-table parsing checks)
