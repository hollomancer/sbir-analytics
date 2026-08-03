"""Tests for the CI secret scanner's log redaction."""

import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ci"))

from scan_secrets import _match_locations  # noqa: E402


pytestmark = pytest.mark.fast


class TestMatchLocations:
    """`grep -RInZ` output must be reduced to locations before it reaches a log.

    Input is NUL-delimited: ``path\\0lineno:content``.
    """

    def test_strips_matched_content(self):
        """The matched line's content — the secret itself — is never returned."""
        locations = _match_locations(["./deploy/prod.env\x0012:NEO4J_PASSWORD=hunter2"])
        assert locations == ["./deploy/prod.env:12"]

    def test_strips_content_containing_colons(self):
        """Content with embedded colons does not bleed past the line number.

        A right-split would return "./a.env:7:AWS_SECRET_ACCESS_KEY=a:b" here,
        publishing most of the secret — the exact leak this guards against.
        """
        locations = _match_locations(["./a.env\x007:AWS_SECRET_ACCESS_KEY=a:b:c"])
        assert locations == ["./a.env:7"]

    def test_path_containing_colons_keeps_its_line_number(self):
        """POSIX allows ':' in a path; the NUL delimiter keeps parsing exact."""
        locations = _match_locations(["./wei:rd/x.env\x001:NEO4J_PASSWORD=a:b:c"])
        assert locations == ["./wei:rd/x.env:1"]

    def test_preserves_all_matches(self):
        locations = _match_locations(["./a\x001:x", "./b\x002:y"])
        assert locations == ["./a:1", "./b:2"]

    def test_input_without_nul_never_leaks_content(self):
        """If grep ever stops emitting -Z, degrade closed rather than leaking."""
        assert _match_locations(["./a.env:7:NEO4J_PASSWORD=hunter2"]) == ["./a.env"]

    def test_handles_line_without_location_prefix(self):
        """Malformed input degrades safely rather than raising."""
        assert _match_locations(["./nolineno"]) == ["./nolineno"]
        assert _match_locations([""]) == [""]
