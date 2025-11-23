#!/usr/bin/env python3
"""Secret scanning script for CI/CD.

This script performs comprehensive secret scanning using detect-secrets
and fallback pattern matching. It's designed to be run in GitHub Actions
but can also be used locally.

Usage:
    python scripts/ci/scan_secrets.py [--baseline .secrets.baseline]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


# Patterns to scan for (common secret patterns)
SECRET_PATTERNS = [
    "NEO4J_PASSWORD",
    "NEO4J_AUTH",
    "NEO4J_ADMIN_PASSWORD",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    r"AKIA[0-9A-Z]{16}",  # AWS Access Key ID pattern
    "PRIVATE_KEY",
]

# Directories to exclude from scanning
EXCLUDE_DIRS = [
    ".git",
    ".venv",
    "docs",
    "archive",
    ".kiro",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "scripts",
    "config",
]

# File patterns to exclude
EXCLUDE_FILES = [
    "*.png",
    "*.jpg",
    "*.md",
    ".env.example*",
    "*.py",  # Python files may reference env var names legitimately
    "*.sh",
    "*.yml",
    "*.yaml",
    "Makefile",
    "*.conf",
    "*.json",
]


def run_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result


def scan_with_detect_secrets(baseline_path: Path | None = None) -> tuple[int, str]:
    """Run detect-secrets scan.

    Args:
        baseline_path: Path to baseline file. If None, checks for .secrets.baseline.

    Returns:
        Tuple of (exit_code, message)
    """
    baseline = baseline_path or Path(".secrets.baseline")

    if not baseline.exists():
        # No baseline - run direct scan
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp_file:
                output_path = Path(tmp_file.name)
            result = run_command(
                ["detect-secrets", "scan", "--all-files", "--quiet", "--json", str(output_path)],
                check=False,
            )
            if output_path.exists() and output_path.stat().st_size > 0:
                with open(output_path) as f:
                    data = json.load(f)
                    if data.get("results"):
                        return (
                            2,
                            "detect-secrets found findings (no baseline configured).",
                        )
                # Clean up temp file
                output_path.unlink(missing_ok=True)
        except FileNotFoundError:
            return (1, "detect-secrets not installed")
        return (0, "No secrets found (no baseline)")

    # Run with baseline
    try:
        result = run_command(
            [
                "detect-secrets",
                "scan",
                "--baseline",
                str(baseline),
                "--all-files",
            ],
            check=False,
        )
        if result.returncode == 0:
            return (0, "No new secrets detected")
        elif result.returncode == 1:
            # New secrets detected - print verbose output
            print("New secrets detected! Running verbose scan to show details:", file=sys.stderr)
            verbose_result = run_command(
                [
                    "detect-secrets",
                    "scan",
                    "--baseline",
                    str(baseline),
                    "--all-files",
                    "--verbose",
                ],
                check=False,
            )
            if verbose_result.stdout:
                print(verbose_result.stdout, file=sys.stderr)
            if verbose_result.stderr:
                print(verbose_result.stderr, file=sys.stderr)
            return (1, "New secrets detected in baseline scan (see verbose output above)")
        else:
            return (result.returncode, f"detect-secrets exited with code {result.returncode}")
    except FileNotFoundError:
        return (1, "detect-secrets not installed")


def run_precommit_hooks() -> tuple[int, str]:
    """Run pre-commit hooks (which includes detect-secrets).

    Returns:
        Tuple of (exit_code, message)
    """
    precommit_config = Path(".pre-commit-config.yaml")
    if not precommit_config.exists():
        return (0, ".pre-commit-config.yaml not found, skipping pre-commit")

    try:
        result = run_command(["pre-commit", "run", "--all-files"], check=False)
        exit_code = result.returncode

        if exit_code == 0:
            return (0, "Pre-commit checks passed")
        elif exit_code == 3:
            # Exit code 3 means baseline was updated (line number changes)
            baseline_path = Path(".secrets.baseline")
            if not baseline_path.exists():
                return (3, "Baseline should exist but doesn't")

            # Check if baseline was modified
            git_result = run_command(["git", "diff", "--quiet", str(baseline_path)], check=False)
            if git_result.returncode != 0:
                # Baseline was modified - verify no new secrets
                scan_exit, scan_msg = scan_with_detect_secrets(baseline_path)
                if scan_exit == 1:
                    return (
                        1,
                        f"Baseline updated but new secrets detected: {scan_msg}",
                    )
                else:
                    return (
                        0,
                        "Baseline updated successfully - no new secrets (only line number updates)",
                    )
            else:
                return (3, "Baseline was not modified, this is unexpected")
        else:
            # Print full output for debugging
            print("Pre-commit checks failed. Full output:", file=sys.stderr)
            if result.stdout:
                print("STDOUT:", file=sys.stderr)
                print(result.stdout, file=sys.stderr)
            if result.stderr:
                print("STDERR:", file=sys.stderr)
                print(result.stderr, file=sys.stderr)
            return (
                exit_code,
                "Pre-commit checks failed (possible secrets detected). See output above for details.",
            )
    except FileNotFoundError:
        return (1, "pre-commit not installed")


def scan_patterns() -> tuple[int, str]:
    """Scan for common secret patterns using grep.

    Returns:
        Tuple of (exit_code, message)
    """
    import re

    # Build exclude arguments for grep
    exclude_args = []
    for dir_pattern in EXCLUDE_DIRS:
        exclude_args.extend(["--exclude-dir", dir_pattern])
    for file_pattern in EXCLUDE_FILES:
        exclude_args.extend(["--exclude", file_pattern])

    found_secrets = False
    patterns_found = []

    for pattern in SECRET_PATTERNS:
        # Check if pattern is a regex
        is_regex = bool(re.search(r"[\[\]\{\}\(\)\*\?\+\|]", pattern))

        try:
            if is_regex:
                # Use -P for Perl regex
                cmd = ["grep", "-RInP", pattern] + exclude_args + ["."]
                result = run_command(cmd, check=False)
            else:
                # Regular string match
                cmd = ["grep", "-RIn", pattern] + exclude_args + ["."]
                result = run_command(cmd, check=False)

            if result.returncode == 0 and result.stdout:
                # Filter out lines with pragma allowlist secret
                lines = [
                    line
                    for line in result.stdout.split("\n")
                    if line
                    and "pragma: allowlist secret" not in line
                    and "pragma: allowlist secret" not in line.lower()
                ]
                if lines:
                    found_secrets = True
                    patterns_found.append(pattern)
                    print(f"Pattern '{pattern}' found in:")
                    for line in lines[:5]:  # Show first 5 matches
                        print(f"  {line}")

        except FileNotFoundError:
            return (1, "grep not found")

    if found_secrets:
        return (
            3,
            f"High-risk secret patterns detected: {', '.join(patterns_found)}",
        )
    else:
        return (0, "No hardcoded secrets detected")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Scan for secrets in codebase")
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Path to secrets baseline file (defaults to .secrets.baseline)",
    )
    parser.add_argument(
        "--skip-patterns",
        action="store_true",
        help="Skip pattern-based scanning (only use detect-secrets)",
    )
    parser.add_argument(
        "--skip-precommit",
        action="store_true",
        help="Skip pre-commit hooks (run detect-secrets directly)",
    )
    args = parser.parse_args()

    exit_code = 0
    messages = []

    # Determine baseline path
    baseline_path = args.baseline or Path(".secrets.baseline")

    # Step 1: Run pre-commit hooks (includes detect-secrets)
    if not args.skip_precommit:
        precommit_exit, precommit_msg = run_precommit_hooks()
        messages.append(precommit_msg)
        if precommit_exit != 0:
            exit_code = precommit_exit
            if precommit_exit == 1:
                # Hard failure - new secrets found
                print(f"ERROR: {precommit_msg}", file=sys.stderr)
                # Also print stdout/stderr for debugging
                return exit_code
    else:
        # Run detect-secrets directly
        detect_exit, detect_msg = scan_with_detect_secrets(baseline_path)
        messages.append(detect_msg)
        if detect_exit != 0:
            exit_code = detect_exit
            if detect_exit == 1:
                print(f"ERROR: {detect_msg}", file=sys.stderr)
                # Run detect-secrets with verbose output to show what was found
                print("\nRunning detect-secrets scan to show detected secrets:", file=sys.stderr)
                try:
                    verbose_result = run_command(
                        [
                            "detect-secrets",
                            "scan",
                            "--baseline",
                            str(baseline_path),
                            "--all-files",
                            "--verbose",
                        ],
                        check=False,
                    )
                    if verbose_result.stdout:
                        print(verbose_result.stdout, file=sys.stderr)
                    if verbose_result.stderr:
                        print(verbose_result.stderr, file=sys.stderr)
                except FileNotFoundError:
                    pass
                return exit_code

    # Step 2: Fallback pattern scanning
    if not args.skip_patterns:
        pattern_exit, pattern_msg = scan_patterns()
        messages.append(pattern_msg)
        if pattern_exit != 0 and exit_code == 0:
            exit_code = pattern_exit

    # Print summary
    for msg in messages:
        print(msg)

    if exit_code == 0:
        print("✓ Secret scan completed successfully")
    else:
        print(f"✗ Secret scan failed with exit code {exit_code}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
