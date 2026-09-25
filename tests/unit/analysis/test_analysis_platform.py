"""Contracts, registry, runner, and snapshot gates for #441."""

from __future__ import annotations

from pathlib import Path

import pytest

from sbir_etl.analysis.contracts import (
    AnalysisKind,
    AnalysisSpec,
    AwardCorpus,
    EvidenceChannelStage,
    ReportingWindow,
    unavailable_channel_label,
)
from sbir_etl.analysis.registry import load_registry
from sbir_etl.analysis.runner import materialize_analysis
from sbir_etl.analysis.snapshots import compare_snapshots, write_snapshot


pytestmark = pytest.mark.fast


def test_registry_lists_current_profiles() -> None:
    registry = load_registry()
    ids = {entry.profile_id for entry in registry.profiles}
    assert ids >= {
        "drone_manufacturing",
        "uas_relevance",
        "unmanned_systems_manufacturing",
        "nanotechnology",
        "quantum_information_science",
        "hypersonics",
    }
    assert registry.ids_for(AnalysisKind.TRANSITION_COHORT, dagster_asset=True) == (
        "nanotechnology",
        "quantum_information_science",
        "hypersonics",
    )


def test_unavailable_channel_keeps_not_computed_wording() -> None:
    assert unavailable_channel_label(EvidenceChannelStage.UNAVAILABLE) == (
        "Not computed — not zero"
    )


def test_runner_pins_hashes_and_writes_snapshot(tmp_path: Path) -> None:
    config = tmp_path / "profile.yaml"
    config.write_text("area_id: dummy\n", encoding="utf-8")
    source = tmp_path / "awards.csv"
    source.write_text("award_id\n1\n", encoding="utf-8")
    spec = AnalysisSpec(
        profile_id="dummy",
        analysis_kind=AnalysisKind.TECH_CENSUS,
        config_path=config,
        taxonomy_version="t1",
        methodology_version="m1",
        corpus=AwardCorpus.from_sbir_csv(source),
        window=ReportingWindow(label="unbounded"),
    )

    def strategy(_spec: AnalysisSpec) -> dict:
        out = tmp_path / "out"
        out.mkdir()
        return {"output_dir": str(out), "grand_total_n": 1}

    run = materialize_analysis(spec, strategy=strategy, snapshot_root=tmp_path / "snaps")
    assert run.metrics["grand_total_n"] == 1
    assert run.config_sha256
    assert run.source_sha256
    assert run.snapshot_path is not None
    assert run.snapshot_path.is_file()


def test_refuses_silent_methodology_drift(tmp_path: Path) -> None:
    config = tmp_path / "profile.yaml"
    config.write_text("area_id: dummy\n", encoding="utf-8")
    source = tmp_path / "awards.csv"
    source.write_text("award_id\n1\n", encoding="utf-8")
    spec = AnalysisSpec(
        profile_id="dummy",
        analysis_kind=AnalysisKind.TECH_CENSUS,
        config_path=config,
        taxonomy_version="t1",
        methodology_version="m2",
        corpus=AwardCorpus.from_sbir_csv(source, sha256="abc"),
    )
    frozen = tmp_path / "frozen.json"
    write_snapshot(
        materialize_analysis(
            AnalysisSpec(
                profile_id="dummy",
                analysis_kind=AnalysisKind.TECH_CENSUS,
                config_path=config,
                taxonomy_version="t1",
                methodology_version="m1",
                corpus=AwardCorpus.from_sbir_csv(source, sha256="abc"),
            ),
            strategy=lambda _s: {"grand_total_n": 0},
        ),
        frozen,
    )
    with pytest.raises(ValueError, match="methodology_version"):
        materialize_analysis(
            spec,
            strategy=lambda _s: {"grand_total_n": 0},
            frozen_snapshot=frozen,
        )


def test_compare_snapshots_allows_explicit_methodology_change() -> None:
    left = {
        "methodology_version": "m1",
        "taxonomy_version": "t1",
        "reporting_window": "unbounded",
        "source_sha256": "abc",
    }
    right = {**left, "methodology_version": "m2"}
    assert compare_snapshots(left, right) != []
    assert compare_snapshots(left, right, allow_methodology_change=True) == []


def test_yaml_only_profile_needs_no_new_python_module(tmp_path: Path) -> None:
    """A dummy registry row is enough; no new Python module is required."""

    config = tmp_path / "dummy.yaml"
    config.write_text("area_id: dummy_profile\n", encoding="utf-8")
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        "\n".join(
            [
                "profiles:",
                "  - profile_id: dummy_profile",
                "    analysis_kind: transition_cohort",
                f"    config_path: {config}",
                "    taxonomy_version: t1",
                "    methodology_version: m1",
                "    dagster_asset: true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = load_registry(registry)
    assert loaded.ids_for(AnalysisKind.TRANSITION_COHORT, dagster_asset=True) == ("dummy_profile",)
    spec = AnalysisSpec(
        profile_id="dummy_profile",
        analysis_kind=AnalysisKind.TRANSITION_COHORT,
        config_path=config,
        taxonomy_version="t1",
        methodology_version="m1",
        corpus=AwardCorpus.from_sbir_csv(tmp_path / "missing.csv"),
    )
    run = materialize_analysis(
        spec,
        strategy=lambda _s: {"output_dir": str(tmp_path), "method_a_awards": 0},
        snapshot_root=tmp_path / "snaps",
    )
    assert run.metrics["method_a_awards"] == 0


def test_run_analysis_help() -> None:
    import importlib.util

    path = Path(__file__).resolve().parents[3] / "scripts" / "data" / "run_analysis.py"
    spec = importlib.util.spec_from_file_location("run_analysis_cli", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    help_text = module.build_parser().format_help()
    assert "--profile" in help_text
