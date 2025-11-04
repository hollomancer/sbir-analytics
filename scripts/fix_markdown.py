#!/usr/bin/env python3
"""
Auto-fix common markdownlint issues in markdown files.

This script fixes:
- MD032: Lists should be surrounded by blank lines
- MD031: Fenced code blocks should be surrounded by blank lines
- MD040: Fenced code blocks should have a language specified (adds 'text' if missing)
- MD022: Headings should be surrounded by blank lines
- MD025: Multiple top-level headings (converts extra H1 to H2)
- MD001: Heading levels should only increment by one level at a time
- MD036: Emphasis used instead of a heading (converts **text** to ### text)

Usage:
    python scripts/fix_markdown.py [directory]
"""

import argparse
import re
import sys
from pathlib import Path


def should_process_file(file_path: Path) -> bool:
    """Check if file should be processed (exclude archives and generated files)."""
    path_str = str(file_path)
    exclude_patterns = [
        "/archive/",
        "/.kiro/specs/archive/",
        "/reports/",
        "/node_modules/",
        "/.git/",
        "/htmlcov/",
        "/.venv/",
        "/venv/",
        "/__pycache__/",
        "/.pytest_cache/",
        "/.mypy_cache/",
        "/site-packages/",
    ]
    return not any(pattern in path_str for pattern in exclude_patterns)


def fix_list_blank_lines(content: str) -> str:
    """Fix MD032: Lists should be surrounded by blank lines."""
    lines = content.split("\n")
    result = []
    prev_was_list = False

    for i, line in enumerate(lines):
        # Check if current line is a list item
        is_list = bool(re.match(r"^\s*[-*+]|\s*\d+\.", line))
        # Check if previous line exists and is not blank
        prev_line = lines[i - 1] if i > 0 else ""
        next_line = lines[i + 1] if i < len(lines) - 1 else ""

        # Add blank line before list if needed
        if is_list and not prev_was_list and prev_line and not prev_line.strip() == "":
            # Check if previous line is a heading or code fence
            if not re.match(r"^#+|\s*```", prev_line.rstrip()):
                result.append("")

        result.append(line)

        # Add blank line after list if needed
        if is_list and next_line and not re.match(r"^\s*[-*+]|\s*\d+\.|^\s*$|^#+|\s*```", next_line):
            if i < len(lines) - 1:  # Not the last line
                result.append("")

        prev_was_list = is_list

    return "\n".join(result)


def fix_code_fence_blank_lines(content: str) -> str:
    """Fix MD031: Fenced code blocks should be surrounded by blank lines."""
    lines = content.split("\n")
    result = []
    in_code_block = False

    for i, line in enumerate(lines):
        is_code_fence = line.strip().startswith("```")
        prev_line = lines[i - 1] if i > 0 else ""
        next_line = lines[i + 1] if i < len(lines) - 1 else ""

        # Add blank line before code fence if needed
        if is_code_fence and not in_code_block:
            if prev_line and not prev_line.strip() == "":
                result.append("")

        result.append(line)

        # Add blank line after code fence if needed
        if is_code_fence and in_code_block:
            if next_line and not next_line.strip() == "":
                result.append("")

        if is_code_fence:
            in_code_block = not in_code_block

    return "\n".join(result)


def fix_code_fence_language(content: str) -> str:
    """Fix MD040: Fenced code blocks should have a language specified."""
    # Pattern to match code fences without language
    lines = content.split("\n")
    result = []
    in_code_block = False

    for _i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```") and not in_code_block:
            # Check if it has a language tag
            if stripped == "```" or stripped == "``` ":
                # Add 'text' as default language
                indent = len(line) - len(line.lstrip())
                result.append(" " * indent + "```text")
            else:
                result.append(line)
            in_code_block = True
        elif stripped.startswith("```") and in_code_block:
            result.append(line)
            in_code_block = False
        else:
            result.append(line)

    return "\n".join(result)


def fix_heading_blank_lines(content: str) -> str:
    """Fix MD022: Headings should be surrounded by blank lines."""
    lines = content.split("\n")
    result = []

    for i, line in enumerate(lines):
        is_heading = re.match(r"^(#+)\s", line)
        prev_line = lines[i - 1] if i > 0 else ""
        next_line = lines[i + 1] if i < len(lines) - 1 else ""

        # Add blank line before heading if needed
        if is_heading and prev_line and not prev_line.strip() == "":
            result.append("")

        result.append(line)

        # Add blank line after heading if needed (unless it's the last line)
        if is_heading and next_line and not next_line.strip() == "":
            result.append("")

    return "\n".join(result)


def fix_multiple_h1(content: str) -> str:
    """Fix MD025: Multiple top-level headings (convert extra H1 to H2)."""
    lines = content.split("\n")
    result = []
    h1_count = 0

    for line in lines:
        if re.match(r"^#\s", line):
            h1_count += 1
            if h1_count > 1:
                # Convert to H2
                result.append(re.sub(r"^#\s", "## ", line))
            else:
                result.append(line)
        else:
            result.append(line)

    return "\n".join(result)


def fix_heading_increment(content: str) -> str:
    """Fix MD001: Heading levels should only increment by one level at a time."""
    lines = content.split("\n")
    result = []
    prev_level = 0

    for line in lines:
        match = re.match(r"^(#+)\s", line)
        if match:
            current_level = len(match.group(1))
            # If jump is more than 1, adjust it
            if current_level > prev_level + 1:
                new_level = prev_level + 1
                line = "#" * new_level + line[match.end():]
            prev_level = len(re.match(r"^(#+)", line).group(1))
        result.append(line)

    return "\n".join(result)


def fix_emphasis_as_heading(content: str) -> str:
    """Fix MD036: Emphasis used instead of a heading."""
    lines = content.split("\n")
    result = []

    for line in lines:
        # Check if line is just bold text (likely a heading)
        # Pattern: line starts with **text** or **text**: (with optional colon)
        match = re.match(r"^(\s*)\*\*([^*]+)\*\*:?\s*$", line)
        if match:
            indent = match.group(1)
            text = match.group(2)
            # Convert to H3 heading (indented based on context)
            if len(indent) > 0:
                # Keep indentation, use H3
                result.append(f"{indent}### {text}")
            else:
                result.append(f"### {text}")
        else:
            result.append(line)

    return "\n".join(result)


def fix_markdown_file(file_path: Path) -> tuple[int, bool]:
    """Fix all markdown issues in a file."""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content

        # Apply fixes in order
        content = fix_heading_blank_lines(content)
        content = fix_code_fence_blank_lines(content)
        content = fix_code_fence_language(content)
        content = fix_list_blank_lines(content)
        content = fix_multiple_h1(content)
        content = fix_heading_increment(content)
        content = fix_emphasis_as_heading(content)

        # Normalize line endings
        content = content.replace("\r\n", "\n").replace("\r", "\n")

        if content != original:
            file_path.write_text(content, encoding="utf-8")
            return (len(content.split("\n")), True)
        return (len(content.split("\n")), False)
    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        return (0, False)


def main():
    parser = argparse.ArgumentParser(description="Fix common markdownlint issues")
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to process (default: current directory)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without making changes",
    )
    args = parser.parse_args()

    root = Path(args.directory)
    if not root.exists():
        print(f"Error: Directory {root} does not exist", file=sys.stderr)
        sys.exit(1)

    # Find all markdown files
    md_files = list(root.rglob("*.md"))
    processed = 0
    modified = 0

    for md_file in md_files:
        if not should_process_file(md_file):
            continue

        processed += 1
        lines, was_modified = fix_markdown_file(md_file)
        if was_modified:
            modified += 1
            if not args.dry_run:
                print(f"Fixed: {md_file} ({lines} lines)")

    if args.dry_run:
        print(f"Would process {processed} files")
    else:
        print(f"Processed {processed} files, modified {modified} files")


if __name__ == "__main__":
    main()

