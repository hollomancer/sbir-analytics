"""Mutation tests for the retired graph-reference guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.check_retired_neo4j_references import scan_paths


pytestmark = [pytest.mark.fast, pytest.mark.unit]


@pytest.mark.parametrize(
    ("relative", "content"),
    [
        ("module.py", "from neo4j import GraphDatabase\n"),
        ("module.py", "from sbir_graph.loaders import Loader\n"),
        ("pyproject.toml", 'dependencies = ["neo4j>=5"]\n'),
        ("requirements.txt", "neo4j>=5\n"),
        ("docker-compose.yml", "services:\n  neo4j:\n    image: database:latest\n"),
        ("docker-compose.yml", 'ports:\n  - "7687:7687"\n'),
        (".github/workflows/ci.yml", "run: docker compose up neo4j\n"),
        ("docs/setup.md", "Run `docker compose up neo4j` before the pipeline.\n"),
        ("docs/setup.md", "Install with `uv add neo4j`.\n"),
        ("docs/setup.md", "from neo4j import GraphDatabase\n"),
        ("docs/testing.md", "Run `pytest -m neo4j` for graph integration.\n"),
        ("settings.env", "NEO4J_PASSWORD=secret\n"),
        ("settings.yaml", "uri: bolt://database:7687\n"),
    ],
)
def test_guard_rejects_active_reference_families(
    tmp_path: Path, relative: str, content: str
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)

    violations = scan_paths([path], root=tmp_path)

    assert violations
    assert violations[0].path == relative


def test_guard_allows_plain_historical_name_in_live_prose(tmp_path: Path) -> None:
    path = tmp_path / "docs" / "architecture.md"
    path.parent.mkdir(parents=True)
    path.write_text("The Neo4j projection was retired.\n")

    assert scan_paths([path], root=tmp_path) == []


def test_guard_allows_exact_retirement_record(tmp_path: Path) -> None:
    path = tmp_path / "archive" / "neo4j" / "README.md"
    path.parent.mkdir(parents=True)
    path.write_text("Historical command: docker compose up neo4j\n")

    assert scan_paths([path], root=tmp_path) == []


def test_guard_does_not_allow_unregistered_archive_path(tmp_path: Path) -> None:
    path = tmp_path / "archive" / "neo4j" / "unregistered.md"
    path.parent.mkdir(parents=True)
    path.write_text("Historical command: docker compose up neo4j\n")

    violations = scan_paths([path], root=tmp_path)

    assert len(violations) == 1
    assert violations[0].path == "archive/neo4j/unregistered.md"


def test_guard_allows_its_exact_ci_invocation(tmp_path: Path) -> None:
    path = tmp_path / "Makefile"
    path.write_text("\tuv run python scripts/ci/check_retired_neo4j_references.py\n")

    assert scan_paths([path], root=tmp_path) == []


def test_guard_does_not_allow_control_path_as_a_comment_escape(tmp_path: Path) -> None:
    path = tmp_path / "Makefile"
    path.write_text("\tdocker compose up neo4j  # scripts/ci/check_retired_neo4j_references.py\n")

    assert scan_paths([path], root=tmp_path)
