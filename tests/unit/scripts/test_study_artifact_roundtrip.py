"""Tests for the study-deliverable round-trip guard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.ci import check_study_artifact_roundtrip as guard


RENDERER = (
    "def render_markdown(summary):\n    return f\"# Readout\\n\\nPairs: {summary['pairs']}\\n\"\n"
)


def _build_study(root: Path, markdown: str, *, renderer: str = RENDERER) -> guard.RoundTripPair:
    (root / "scripts/data").mkdir(parents=True, exist_ok=True)
    (root / "docs/readouts").mkdir(parents=True, exist_ok=True)
    (root / "scripts/data/build_readout.py").write_text(renderer, encoding="utf-8")
    (root / "docs/readouts/example.summary.json").write_text(
        json.dumps({"pairs": 500}), encoding="utf-8"
    )
    (root / "docs/readouts/example.md").write_text(markdown, encoding="utf-8")
    return guard.RoundTripPair(
        markdown="docs/readouts/example.md",
        sidecar="docs/readouts/example.summary.json",
        renderer="scripts/data/build_readout.py:render_markdown",
    )


def test_matching_pair_passes(tmp_path: Path) -> None:
    pair = _build_study(tmp_path, "# Readout\n\nPairs: 500\n")

    assert guard.validate_pair(pair, root=tmp_path) == []


def test_drifted_markdown_reports_the_difference(tmp_path: Path) -> None:
    pair = _build_study(tmp_path, "# Readout\n\nPairs: 512\n")

    violations = guard.validate_pair(pair, root=tmp_path)

    assert len(violations) == 1
    assert "does not reproduce from" in violations[0].message
    assert "Pairs: 512" in violations[0].message
    assert "Pairs: 500" in violations[0].message


def test_renderer_that_raises_on_its_own_sidecar_is_reported(tmp_path: Path) -> None:
    renderer = (
        "def render_markdown(summary):\n"
        "    return f\"# Readout\\n\\nPairs: {summary['post_cap_over_cap_n']}\\n\"\n"
    )
    pair = _build_study(tmp_path, "# Readout\n\nPairs: 500\n", renderer=renderer)

    violations = guard.validate_pair(pair, root=tmp_path)

    assert len(violations) == 1
    assert "raised KeyError" in violations[0].message


def test_non_string_renderer_output_is_reported(tmp_path: Path) -> None:
    pair = _build_study(
        tmp_path,
        "# Readout\n\nPairs: 500\n",
        renderer="def render_markdown(summary):\n    return summary\n",
    )

    violations = guard.validate_pair(pair, root=tmp_path)

    assert len(violations) == 1
    assert "returned dict, expected str" in violations[0].message


def test_missing_sidecar_is_reported(tmp_path: Path) -> None:
    pair = _build_study(tmp_path, "# Readout\n\nPairs: 500\n")
    (tmp_path / pair.sidecar).unlink()

    violations = guard.validate_pair(pair, root=tmp_path)

    assert len(violations) == 1
    assert "registered sidecar is missing" in violations[0].message


def test_unregistered_renderer_is_reported(tmp_path: Path) -> None:
    _build_study(tmp_path, "# Readout\n\nPairs: 500\n")

    violations = guard.validate_coverage(
        root=tmp_path, pairs=(), waived={}, scan_roots=("scripts",)
    )

    assert len(violations) == 1
    assert violations[0].path == "scripts/data/build_readout.py"
    assert "not in REGISTERED_PAIRS" in violations[0].message


def test_waived_renderer_is_accepted_and_stale_waiver_is_reported(tmp_path: Path) -> None:
    _build_study(tmp_path, "# Readout\n\nPairs: 500\n")

    waived = {"scripts/data/build_readout.py": "renders a template, not a study artifact"}
    assert (
        guard.validate_coverage(root=tmp_path, pairs=(), waived=waived, scan_roots=("scripts",))
        == []
    )

    stale = {"scripts/data/gone.py": "removed last release"}
    violations = guard.validate_coverage(
        root=tmp_path, pairs=(), waived=stale, scan_roots=("scripts",)
    )
    assert len(violations) == 2
    assert any("stale waiver" in violation.message for violation in violations)


def test_blank_waiver_reason_waives_nothing(tmp_path: Path) -> None:
    """A waiver with no reason is reported, and does not exempt the renderer."""
    _build_study(tmp_path, "# Readout\n\nPairs: 500\n")

    violations = guard.validate_coverage(
        root=tmp_path,
        pairs=(),
        waived={"scripts/data/build_readout.py": "   "},
        scan_roots=("scripts",),
    )

    messages = sorted(violation.message for violation in violations)
    assert messages == [
        "exposes render_markdown but is not in REGISTERED_PAIRS; register the "
        "sidecar it renders from, or waive it with a reason",
        "waiver has no reason; state why this renderer has no committed pair",
    ]


def test_repository_registry_is_consistent() -> None:
    violations = guard.validate_repository()

    assert violations == [], "\n".join(violation.format() for violation in violations)


def test_validate_pair_loads_a_renderer_that_defines_a_dataclass(tmp_path: Path) -> None:
    """The loader must register the module before exec_module, or Python 3.12's
    postponed-annotation handling for dataclasses crashes with AttributeError
    on `sys.modules[cls.__module__].__dict__` when the module was never registered.
    """
    renderer = (
        "from __future__ import annotations\n"
        "\n"
        "from dataclasses import dataclass\n"
        "\n"
        "\n"
        "@dataclass(frozen=True)\n"
        "class Profile:\n"
        "    label: str\n"
        "\n"
        "\n"
        "def render_markdown(payload):\n"
        '    return "# Readout\\n\\nFixed.\\n"\n'
    )
    pair = _build_study(tmp_path, "# Readout\n\nFixed.\n", renderer=renderer)

    assert guard.validate_pair(pair, root=tmp_path) == []


def test_load_renderer_unregisters_a_module_that_fails_to_execute(tmp_path: Path) -> None:
    """A renderer that raises while loading must not leave a partial module
    registered in sys.modules, or a later import of the same path could see
    the half-initialized module instead of failing cleanly.
    """
    pair = _build_study(
        tmp_path,
        "# Readout\n\nPairs: 500\n",
        renderer='raise RuntimeError("boom")\n',
    )
    derived_name = "_roundtrip_" + pair.renderer_path.replace("/", "_").removesuffix(".py")
    derived_suffix = derived_name.removeprefix("_roundtrip_")

    with pytest.raises(RuntimeError):
        guard._load_renderer(tmp_path, pair)

    assert not any(
        key.startswith("_roundtrip_") and key.endswith(derived_suffix) for key in sys.modules
    )
