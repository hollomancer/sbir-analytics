"""CLI wiring for scripts/data/run_analysis.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.fast

REPO = Path(__file__).resolve().parents[3]


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "run_analysis_cli", REPO / "scripts" / "data" / "run_analysis.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_analysis_cli"] = module
    spec.loader.exec_module(module)
    return module


def test_census_strategy_writes_artifacts(tmp_path, monkeypatch) -> None:
    """The strategy must emit the artifacts build_tech_census.py emits (regression)."""

    cli = _load_cli()
    from sbir_etl.analysis.contracts import AnalysisKind, AnalysisSpec, AwardCorpus

    awards = tmp_path / "awards.csv"
    awards.write_text("award_id\n1\n", encoding="utf-8")
    out_root = tmp_path / "repo"
    monkeypatch.setattr(cli, "REPO", out_root)

    captured: dict = {}

    def _fake_run_census(awards_arg, compiled, **kwargs):
        captured["called"] = True
        return {
            "_epistemic": {"tier": "exploratory", "notice": "non-citable"},
            "area_id": "dummy",
            "display_name": "Dummy",
            "config_version": "v1",
            "override_version": "v0",
            "programs": ["SBIR"],
            "classified_awards": [{"company": "ACME", "year": 2024, "amount": 100.0}],
            "excluded_awards": [],
            "by_fy_subset": {(2024, "core"): {"n": 1, "usd": 100.0}},
            "subset_totals": {"core": {"n": 1, "usd": 100.0}},
            "scope_totals": {"in_scope": {"n": 1, "usd": 100.0}},
            "fy_totals": {2024: {"n": 1, "usd": 100.0}},
            "grand_total": {"n": 1, "usd": 100.0},
            "exclusion_counts": {},
            "adjacent_counts": {},
            "program_exclusion_counts": {},
            "rejection_counts": {},
        }

    import sbir_etl.utils.tech_census as tech_census

    monkeypatch.setattr(tech_census, "run_census", _fake_run_census)
    monkeypatch.setattr(tech_census, "load_census_config", lambda profile_id: {"area_id": "dummy"})
    monkeypatch.setattr(tech_census, "CompiledCensus", lambda cfg: object())
    monkeypatch.setattr(tech_census, "load_award_data_csv", lambda path: [{"award_key": "1"}])

    spec = AnalysisSpec(
        profile_id="dummy",
        analysis_kind=AnalysisKind.TECH_CENSUS,
        config_path=tmp_path / "profile.yaml",
        taxonomy_version="t1",
        methodology_version="m1",
        corpus=AwardCorpus.from_sbir_csv(awards),
    )

    payload = cli._census_strategy(spec)

    out_dir = Path(payload["output_dir"])
    assert (out_dir / "classified_awards.csv").is_file()
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["grand_total"] == {"n": 1, "usd": 100.0}
    assert summary["provenance"]["sha256"]


def test_frozen_snapshot_flag_resolves_previous(tmp_path) -> None:
    cli = _load_cli()
    args = cli.build_parser().parse_args(
        ["--profile", "dummy", "--frozen-snapshot", "previous", "--period", "fy2024"]
    )

    resolved = cli._frozen_snapshot(args, "dummy")

    assert resolved == cli.SNAPSHOT_ROOT / "dummy" / "fy2024.json"


def test_frozen_snapshot_defaults_to_no_baseline() -> None:
    cli = _load_cli()
    args = cli.build_parser().parse_args(["--profile", "dummy"])

    assert cli._frozen_snapshot(args, "dummy") is None


def test_frozen_snapshot_accepts_an_explicit_path(tmp_path) -> None:
    cli = _load_cli()
    baseline = tmp_path / "frozen.json"
    args = cli.build_parser().parse_args(["--profile", "dummy", "--frozen-snapshot", str(baseline)])

    assert cli._frozen_snapshot(args, "dummy") == baseline
