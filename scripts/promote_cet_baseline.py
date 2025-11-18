#!/usr/bin/env python3
"""
promote_cet_baseline.py

Promote a candidate CET baseline distribution file to the canonical baseline file.

This script is intended to be used after running the CET drift detection asset which
writes a candidate baseline to:

    reports/benchmarks/cet_baseline_distributions_current.json

Promotion will atomically copy that candidate to:

    reports/benchmarks/cet_baseline_distributions.json

Optional behavior (via flags):
- --commit: run `git add` and `git commit` for the promoted baseline
- --push: push the commit to the current branch (requires --commit)
- --message: customize the git commit message
- --force: overwrite existing canonical baseline without prompting
- --yes: non-interactive confirmation
- --candidate-path / --baseline-path: override default paths
- --dry-run: validate and show what would be promoted without writing

Usage examples:
    # Simple promotion (atomic file replace)
    python scripts/promote_cet_baseline.py

    # Promote and commit the change, with a custom message
    python scripts/promote_cet_baseline.py --commit --message "Promote CET baseline (auto)"

    # Non-interactive promoted in CI
    python scripts/promote_cet_baseline.py --commit --push --yes

Notes:
- This script uses the local git repository to create a commit when requested.
  It assumes the current working directory is the repository root and that git is available.
- Promotion is atomic: the candidate is written to a temporary file and then moved into place.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


# Default paths (relative to repository root)
DEFAULT_CANDIDATE = Path("reports/benchmarks/cet_baseline_distributions_current.json")
DEFAULT_BASELINE = Path("reports/benchmarks/cet_baseline_distributions.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def load_json_safe(path: Path) -> dict[str, Any] | None:
    """Load JSON from path returning dict or None on failure."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.error("Failed to load JSON from %s: %s", path, exc)
        return None


def validate_baseline_structure(obj: dict[str, Any]) -> bool:
    """
    Basic validation of baseline shape. Expected top-level keys:
      - label_pmf (dict) or label distribution structure
      - score_pmf (dict) or score histogram structure

    This is intentionally permissive — we only want to catch obvious errors.
    """
    if not isinstance(obj, dict):
        logger.error("Baseline object is not a JSON object")
        return False

    # Accept either explicit keys or nested shapes; prefer presence of either pmf key
    if "label_pmf" in obj and not isinstance(obj["label_pmf"], dict):
        logger.error("Baseline 'label_pmf' present but not an object")
        return False
    if "score_pmf" in obj and not isinstance(obj["score_pmf"], dict):
        logger.error("Baseline 'score_pmf' present but not an object")
        return False

    # If neither key exists, but object contains plausible keys, accept len>0
    if "label_pmf" not in obj and "score_pmf" not in obj:
        # allow older shapes: check for any dict-like entries
        plausible = any(isinstance(v, dict) for v in obj.values())
        if not plausible:
            logger.warning(
                "Baseline JSON does not contain explicit 'label_pmf' or 'score_pmf' keys; "
                "promotion will proceed but verify baseline contents."
            )
    return True


# Use centralized atomic write utility
from src.utils.file_io import write_json_atomic

def atomic_write_json(target: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically to target path using a temp file + os.replace."""
    write_json_atomic(target, data, indent=2, sort_keys=True, default=str)


def run_git_commit_and_push(paths: [Path], message: str, push: bool = False) -> int:
    """
    Run git add/commit for provided paths and optionally push.
    Returns the subprocess exit code (0 for success).
    """
    # Ensure git is available
    try:
        subprocess.run(["git", "--version"], check=True, stdout=subprocess.DEVNULL)
    except Exception as exc:
        logger.error("Git is not available or not in PATH: %s", exc)
        return 2

    # Add files
    add_cmd = ["git", "add"] + [str(p) for p in paths]
    try:
        logger.info("Running: %s", " ".join(add_cmd))
        subprocess.run(add_cmd, check=True)
    except subprocess.CalledProcessError as exc:
        logger.error("Git add failed: %s", exc)
        return exc.returncode

    # Commit
    commit_cmd = ["git", "commit", "-m", message]
    try:
        logger.info("Committing baseline with message: %s", message)
        subprocess.run(commit_cmd, check=True)
    except subprocess.CalledProcessError as exc:
        logger.error("Git commit failed (maybe nothing to commit): %s", exc)
        # If commit fails because nothing to commit, treat as success (no-op)
        return exc.returncode

    # Push (optional)
    if push:
        try:
            logger.info("Pushing commit to origin (current branch)")
            subprocess.run(["git", "push"], check=True)
        except subprocess.CalledProcessError as exc:
            logger.error("Git push failed: %s", exc)
            return exc.returncode

    return 0


def promote_candidate(
    candidate_path: Path,
    baseline_path: Path,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    """
    Promote the candidate baseline to the canonical baseline path.
    Returns 0 on success, non-zero on error.
    """
    logger.info("Promote candidate: %s -> %s", candidate_path, baseline_path)

    if not candidate_path.exists():
        logger.error("Candidate baseline not found at: %s", candidate_path)
        return 3

    candidate = load_json_safe(candidate_path)
    if candidate is None:
        logger.error("Failed to load candidate baseline JSON; aborting promotion")
        return 4

    if not validate_baseline_structure(candidate):
        logger.error("Candidate baseline failed structure validation; aborting")
        return 5

    if baseline_path.exists() and not force:
        logger.info("Baseline already exists at %s", baseline_path)
        # If the baseline content is identical, skip
        existing = load_json_safe(baseline_path)
        if existing == candidate:
            logger.info("Existing baseline is identical to candidate. Nothing to do.")
            return 0
        # Otherwise, if not forced, require explicit confirmation by caller
        logger.warning(
            "Baseline at %s differs from candidate. Use --force to overwrite or run in interactive mode.",
            baseline_path,
        )
        return 6

    if dry_run:
        logger.info("Dry-run: validated candidate baseline; no file written.")
        return 0

    # Atomic write
    try:
        atomic_write_json(baseline_path, candidate)
        logger.info("Candidate promoted to baseline at %s", baseline_path)
    except Exception as exc:
        logger.error("Failed to write baseline file: %s", exc)
        return 7

    return 0


def parse_args(argv: list | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote CET baseline candidate to canonical baseline (optional git commit/push)."
    )
    parser.add_argument(
        "--candidate-path",
        type=str,
        default=str(DEFAULT_CANDIDATE),
        help=f"Path to candidate baseline JSON (default: {DEFAULT_CANDIDATE})",
    )
    parser.add_argument(
        "--baseline-path",
        type=str,
        default=str(DEFAULT_BASELINE),
        help=f"Path to canonical baseline JSON (default: {DEFAULT_BASELINE})",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Create a git commit for the promoted baseline (git add + git commit).",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push the commit to the current branch (implies --commit).",
    )
    parser.add_argument(
        "--message",
        type=str,
        default=None,
        help="Git commit message. Defaults to a timestamped promotion message.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing canonical baseline without prompting.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Assume yes for interactive confirmations; useful for CI/non-interactive runs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate candidate baseline and show actions without writing files.",
    )
    return parser.parse_args(argv)


def main(argv: list | None = None) -> int:
    args = parse_args(argv)

    candidate_path = Path(args.candidate_path)
    baseline_path = Path(args.baseline_path)

    # Confirm overwrite if baseline exists and not forced and not non-interactive
    if baseline_path.exists() and not args.force and not args.yes:
        logger.warning("Baseline already exists at %s", baseline_path)
        try:
            resp = input("Overwrite existing baseline? [y/N]: ").strip().lower()
        except Exception:
            resp = "n"
        if resp not in ("y", "yes"):
            logger.info("Promotion aborted by user.")
            return 1

    # Perform promotion
    rc = promote_candidate(candidate_path, baseline_path, dry_run=args.dry_run, force=args.force)
    if rc != 0:
        logger.error("Promotion failed with code %d", rc)
        return rc

    # Optionally commit and push
    if args.commit or args.push:
        commit_msg = args.message or f"Promote CET baseline: {datetime.utcnow().isoformat()}"
        # We will git add the baseline path relative to repo root
        git_rc = run_git_commit_and_push([baseline_path], commit_msg, push=args.push)
        if git_rc != 0:
            logger.error("Git operations failed with code %d", git_rc)
            return git_rc
        logger.info("Git commit (and push if requested) completed successfully.")

    logger.info("Promotion complete.")
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except KeyboardInterrupt:
        logger.error("Promotion cancelled by user (KeyboardInterrupt).")
        rc = 130
    sys.exit(rc)
