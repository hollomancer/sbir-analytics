"""USPTO raw extraction assets.

This module contains:
- raw_uspto_assignments: Discover assignment table files
- raw_uspto_assignees: Discover assignee table files
- raw_uspto_assignors: Discover assignor table files
- raw_uspto_documentids: Discover documentids table files
- raw_uspto_conveyances: Discover conveyance table files
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from .utils import (
    _discover_table_files,
    _get_input_dir,
    asset,
)


@asset(
    description="Discover raw USPTO assignment files",
    group_name="extraction",
)
def raw_uspto_assignments(context) -> list[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering assignment files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "assignment")
    context.log.info("Found assignment files", extra={"count": len(files), "files": files})
    return files


@asset(
    description="Discover raw USPTO assignee files",
    group_name="extraction",
)
def raw_uspto_assignees(context) -> list[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering assignee files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "assignee")
    context.log.info("Found assignee files", extra={"count": len(files), "files": files})
    return files


@asset(
    description="Discover raw USPTO assignor files",
    group_name="extraction",
)
def raw_uspto_assignors(context) -> list[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering assignor files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "assignor")
    context.log.info("Found assignor files", extra={"count": len(files), "files": files})
    return files


@asset(
    description="Discover raw USPTO documentid files",
    group_name="extraction",
)
def raw_uspto_documentids(context) -> list[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering documentid files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "documentid")
    context.log.info("Found documentid files", extra={"count": len(files), "files": files})
    return files


@asset(
    description="Discover raw USPTO conveyance files",
    group_name="extraction",
)
def raw_uspto_conveyances(context) -> list[str]:
    input_dir = _get_input_dir(context)
    context.log.info("Discovering conveyance files", extra={"input_dir": str(input_dir)})
    files = _discover_table_files(input_dir, "conveyance")
    context.log.info("Found conveyance files", extra={"count": len(files), "files": files})
    return files


# -------------------------
# Parsing assets (per-table)
# -------------------------
