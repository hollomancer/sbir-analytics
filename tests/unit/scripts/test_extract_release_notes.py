"""Tests for the release-notes extractor.

The gap these guard against is concrete: v0.12.0 was tagged and published with
no CHANGELOG entry, and nothing caught it until the release was written by
hand afterwards. A missing or empty section must fail the release job rather
than produce an empty release body.
"""

from pathlib import Path

import pytest

from scripts.ci import extract_release_notes as notes


CHANGELOG = """# Changelog

## [Unreleased]

## [0.12.0] - 2026-08-31

### Fixed

- Something real (#692).

## [0.11.0] - 2026-08-26

### Added

- An earlier thing (#668).
"""


def _changelog(tmp_path: Path, text: str = CHANGELOG) -> Path:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("reference", ["v0.12.0", "0.12.0"])
def test_normalize_accepts_tag_and_bare_version(reference: str) -> None:
    assert notes.normalize_version(reference) == "0.12.0"


@pytest.mark.parametrize("reference", ["release-1", "v1.2", "v1.2.3.4", "latest", "v01.2.3"])
def test_normalize_rejects_non_release_references(reference: str) -> None:
    with pytest.raises(ValueError):
        notes.normalize_version(reference)


def test_extract_returns_only_the_requested_section(tmp_path: Path) -> None:
    body = notes.extract("0.12.0", _changelog(tmp_path))

    assert "Something real (#692)." in body
    # Must stop at the next heading rather than running into older releases.
    assert "An earlier thing" not in body
    # The version heading itself is dropped; GitHub renders the title separately.
    assert "## [0.12.0]" not in body
    assert body.startswith("### Fixed")


def test_extract_reads_the_final_section_to_end_of_file(tmp_path: Path) -> None:
    body = notes.extract("0.11.0", _changelog(tmp_path))

    assert "An earlier thing (#668)." in body


def test_missing_section_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(LookupError, match=r"no '## \[9.9.9\]' section"):
        notes.extract("9.9.9", _changelog(tmp_path))


def test_empty_section_is_an_error(tmp_path: Path) -> None:
    """A heading with no body must not become an empty release."""
    path = _changelog(
        tmp_path,
        "# Changelog\n\n## [1.0.0] - 2026-01-01\n\n## [0.9.0] - 2025-12-01\n\n- prior\n",
    )

    with pytest.raises(LookupError, match=r"'## \[1.0.0\]' section is empty"):
        notes.extract("1.0.0", path)


def test_version_prefix_does_not_match_a_longer_version(tmp_path: Path) -> None:
    """`0.1.1` must not match the `0.1.1` prefix inside a `## [0.1.10]` heading."""
    path = _changelog(
        tmp_path,
        "# Changelog\n\n## [0.1.10] - 2026-01-01\n\n- ten\n",
    )

    with pytest.raises(LookupError):
        notes.extract("0.1.1", path)


def test_compare_link_uses_the_actions_repository(tmp_path, monkeypatch, capsys) -> None:
    """A fork or renamed repo must not get a compare link to the original."""
    monkeypatch.setattr(notes, "CHANGELOG", _changelog(tmp_path))
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone-else/a-fork")

    assert notes.main(["--tag", "v0.12.0", "--previous-tag", "v0.11.0"]) == 0

    out = capsys.readouterr().out
    assert "https://github.com/someone-else/a-fork/compare/v0.11.0...v0.12.0" in out


def test_compare_link_falls_back_when_unset(tmp_path, monkeypatch, capsys) -> None:
    """Local runs have no GITHUB_REPOSITORY and should still produce a link."""
    monkeypatch.setattr(notes, "CHANGELOG", _changelog(tmp_path))
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    assert notes.main(["--tag", "v0.12.0", "--previous-tag", "v0.11.0"]) == 0

    out = capsys.readouterr().out
    assert f"https://github.com/{notes.DEFAULT_REPOSITORY}/compare/v0.11.0...v0.12.0" in out
