#!/usr/bin/env python3
"""Add @pytest.mark.fast to unit tests that don't have markers."""

from pathlib import Path


def add_fast_marker(file_path: Path) -> bool:
    """Add fast marker to test file if needed."""
    content = file_path.read_text()

    # Skip if already has markers or is not a test file
    if "@pytest.mark." in content or not content.strip():
        return False

    # Skip if no test functions
    if "def test_" not in content:
        return False

    # Check if pytest is imported
    has_pytest_import = "import pytest" in content

    # Find first test function
    lines = content.split("\n")
    modified = False
    new_lines = []

    for i, line in enumerate(lines):
        # Add pytest import if missing
        if not has_pytest_import and i == 0 and line.startswith('"""'):
            # Find end of docstring
            for j in range(i + 1, len(lines)):
                if '"""' in lines[j]:
                    new_lines.extend(lines[: j + 1])
                    new_lines.append("")
                    new_lines.append("import pytest")
                    new_lines.extend(lines[j + 1 :])
                    modified = True
                    has_pytest_import = True
                    break
            if modified:
                break
        elif not has_pytest_import and line.startswith("import ") and "pytest" not in line:
            new_lines.append(line)
            if i + 1 < len(lines) and not lines[i + 1].startswith("import"):
                new_lines.append("import pytest")
                new_lines.extend(lines[i + 1 :])
                modified = True
                has_pytest_import = True
                break

    if not modified:
        new_lines = lines

    # Add @pytest.mark.fast to test functions
    final_lines = []
    for i, line in enumerate(new_lines):
        if line.strip().startswith("def test_") and i > 0:
            # Check if previous line is already a decorator
            prev_line = new_lines[i - 1].strip()
            if not prev_line.startswith("@"):
                final_lines.append("    @pytest.mark.fast")
        final_lines.append(line)

    if final_lines != lines:
        file_path.write_text("\n".join(final_lines))
        return True

    return False


def main():
    """Add fast markers to all unit tests."""
    tests_dir = Path("tests/unit")
    modified_count = 0

    for test_file in tests_dir.rglob("test_*.py"):
        if add_fast_marker(test_file):
            print(f"✓ {test_file.relative_to('tests')}")
            modified_count += 1

    print(f"\nModified {modified_count} files")


if __name__ == "__main__":
    main()
