"""Tests for the strict YAML mapping reader."""

from pathlib import Path

import pytest

from sbir_etl.config.yaml_io import read_yaml_mapping
from sbir_etl.exceptions import ConfigurationError


def test_reads_a_mapping(tmp_path: Path) -> None:
    path = tmp_path / "ok.yaml"
    path.write_text("version: NSTC-2025Q1\ncount: 3\n", encoding="utf-8")

    assert read_yaml_mapping(path) == {"version": "NSTC-2025Q1", "count": 3}


def test_missing_file_names_the_path(tmp_path: Path) -> None:
    path = tmp_path / "absent.yaml"

    with pytest.raises(ConfigurationError, match="cannot read") as excinfo:
        read_yaml_mapping(path, description="CET taxonomy")

    assert "CET taxonomy" in str(excinfo.value)
    assert str(path) in str(excinfo.value)


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    """An empty file parses to None, which callers would hit as AttributeError."""
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="is empty"):
        read_yaml_mapping(path)


def test_comment_only_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "comments.yaml"
    path.write_text("# nothing but a comment\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="is empty"):
        read_yaml_mapping(path)


@pytest.mark.parametrize("content", ["", "# intentionally empty\n"])
def test_empty_file_can_explicitly_mean_empty_mapping(tmp_path: Path, content: str) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text(content, encoding="utf-8")

    assert read_yaml_mapping(path, allow_empty=True) == {}


@pytest.mark.parametrize(
    ("content", "type_name"),
    [("- one\n- two\n", "list"), ("just a string\n", "str"), ("42\n", "int")],
)
def test_non_mapping_top_level_is_rejected(tmp_path: Path, content: str, type_name: str) -> None:
    path = tmp_path / "wrong.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ConfigurationError, match="must hold a mapping") as excinfo:
        read_yaml_mapping(path)

    assert type_name in str(excinfo.value)


def test_malformed_yaml_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("key: [unclosed\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="not valid YAML"):
        read_yaml_mapping(path)


def test_description_appears_in_every_failure(tmp_path: Path) -> None:
    """The description is what tells an operator which file to go fix."""
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    listed = tmp_path / "list.yaml"
    listed.write_text("- a\n", encoding="utf-8")
    bad = tmp_path / "bad.yaml"
    bad.write_text("key: [unclosed\n", encoding="utf-8")

    for path in (empty, listed, bad, tmp_path / "absent.yaml"):
        with pytest.raises(ConfigurationError) as excinfo:
            read_yaml_mapping(path, description="study manifest")
        assert "study manifest" in str(excinfo.value)
