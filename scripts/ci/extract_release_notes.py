#!/usr/bin/env python3
"""Extract one version's CHANGELOG section for use as GitHub release notes.

The release workflow calls this with the tag being published. A missing or
empty section is an error, not an empty release body: v0.12.0 shipped without
a CHANGELOG entry because nothing checked, and the gap was only noticed while
writing the release by hand afterwards.
"""

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = ROOT / "CHANGELOG.md"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def normalize_version(reference: str) -> str:
    """Accept either `1.2.3` or the `v1.2.3` tag form."""
    version = reference[1:] if reference.startswith("v") else reference
    if not SEMVER.match(version):
        raise ValueError(f"{reference!r} is not a vMAJOR.MINOR.PATCH release reference")
    return version


def iter_section_bounds(lines: list[str], version: str) -> tuple[int, int]:
    """Return the [start, end) line span of a version's section body.

    Headings look like `## [0.12.0] - 2026-08-31`. The section runs to the next
    `## ` heading or end of file.
    """
    heading = re.compile(rf"^## \[{re.escape(version)}\](\s|$)")
    start = None
    for index, line in enumerate(lines):
        if start is None:
            if heading.match(line):
                start = index + 1
            continue
        if line.startswith("## "):
            return start, index
    if start is None:
        raise LookupError(
            f"CHANGELOG.md has no '## [{version}]' section. "
            "Add the release's entry before tagging it."
        )
    return start, len(lines)


def extract(version: str, changelog: Path = CHANGELOG) -> str:
    lines = changelog.read_text(encoding="utf-8").splitlines()
    start, end = iter_section_bounds(lines, version)
    body = "\n".join(lines[start:end]).strip()
    if not body:
        raise LookupError(
            f"CHANGELOG.md's '## [{version}]' section is empty. "
            "Describe the release before tagging it."
        )
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Release tag or version (v1.2.3 or 1.2.3)")
    parser.add_argument(
        "--previous-tag",
        help="Prior release tag; appends a compare link when supplied",
    )
    args = parser.parse_args(argv)

    try:
        version = normalize_version(args.tag)
        body = extract(version)
    except (ValueError, LookupError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.previous_tag:
        repo = "hollomancer/sbir-analytics"
        compare = f"https://github.com/{repo}/compare/{args.previous_tag}...v{version}"
        body = f"{body}\n\n## Full changelog\n\n{compare}"

    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
