"""Hermetic end-to-end tests for the ``core_refresh_job`` Dagster job.

``core_refresh_job`` (``packages/sbir-analytics/sbir_analytics/definitions.py``) selects
nearly the entire non-heavy asset graph: at time of writing it resolves to 72 of the 113
assets loaded by the repository (everything except the ML/fiscal/NLP-heavy modules listed
in ``assets_pkg.HEAVY_ASSET_PREFIXES``), spanning independent external systems -- SBIR.gov,
USAspending, SAM.gov, USPTO, patents, transition analytics, NIH RePORTER, NSF/defense
lineage, and reporting. Hermetically faking every one of those boundaries in a single
``execute_in_process()`` call, the way ``test_enrichment_job.py`` and
``test_nsf_defense_lineage.py`` do for their much narrower jobs, is not a sane single test:
it would require an unmaintainable pile of independent adapter/IO mocks with no shared
fixture story.

This module instead provides two complementary, honestly-scoped guarantees:

1. ``test_core_refresh_job_selection_excludes_heavy_assets_and_resolves`` is a *structural*
   test. It pins the advertised all-minus-heavy complement: the job resolves against the
   production ``Definitions`` object and its executable keys equal
   ``all_assets - _heavy_keys``. That catches a silent rewrite to ``AssetSelection.all()``
   or a hardcoded subset. It does **not** independently inventory
   ``HEAVY_ASSET_PREFIXES``, and missing-dep / cycle failures for an ``all() - heavy``
   job are already covered by ``Definitions.validate_loadable``.

2. ``test_core_refresh_job_executes_sbir_ingestion_subgraph`` executes a real, connected
   slice of the actual ``core_refresh_job`` object (not a reconstructed copy) end to end via
   ``execute_in_process(asset_selection=...)``: the SBIR ingestion chain
   ``raw_sbir_awards -> validated_sbir_awards -> sbir_validation_report`` plus its
   ``sbir_data_quality_check`` asset check. This chain was chosen because it is a genuine
   source-to-report slice of the job (file/DuckDB-based extraction with no network calls) and
   needs only a config monkeypatch to run hermetically, so it exercises Dagster's real
   execution engine -- not just direct function calls -- against one authentic path through
   the graph. It does **not** prove the other ~69 assets in the job execute correctly; those
   would need their own hermetic adapters, asset by asset, tracked as separate follow-up work.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from dagster import AssetKey


pytestmark = [pytest.mark.e2e, pytest.mark.smoke]


def test_core_refresh_job_selection_excludes_heavy_assets_and_resolves():
    """core_refresh_job must select exactly the non-heavy asset graph, nothing more or less."""
    defs_module = pytest.importorskip("sbir_analytics.definitions")

    job = defs_module.defs.resolve_job_def("core_refresh_job")
    selected_keys = job.asset_layer.executable_asset_keys

    all_loaded_keys = {asset.key for asset in defs_module.all_assets if hasattr(asset, "key")}
    expected_keys = all_loaded_keys - defs_module._heavy_keys

    assert selected_keys, "core_refresh_job selected no assets"
    assert selected_keys == expected_keys


def test_core_refresh_job_executes_sbir_ingestion_subgraph(
    tmp_path: Path, monkeypatch, sbir_sample_csv_path: Path
):
    """Materialize the SBIR ingestion slice of the real core_refresh_job graph.

    Uses the small ``sbir_sample_csv_path`` fixture directly (rather than the
    ``sbir_csv_path`` real/sample switch) so this hermetic test never depends on the large,
    optionally-present ``data/raw/sbir/award_data.csv`` real-data fixture.
    """
    import sbir_analytics.assets.sbir_ingestion as sbir_ingestion_assets

    defs_module = pytest.importorskip("sbir_analytics.definitions")

    data_root = tmp_path / "data"
    db_path = tmp_path / "sbir_core_refresh.duckdb"

    def fake_get_config():
        sbir = SimpleNamespace(
            csv_path=str(sbir_sample_csv_path),
            database_path=str(db_path),
            table_name="sbir_core_refresh_test",
            csv_path_s3=None,
            use_s3_first=False,
        )
        extraction = SimpleNamespace(sbir=sbir)
        data_quality = SimpleNamespace(sbir_awards=SimpleNamespace(pass_rate_threshold=0.0))
        return SimpleNamespace(extraction=extraction, data_quality=data_quality)

    monkeypatch.setenv("SBIR_ETL__PATHS__DATA_ROOT", str(data_root))
    monkeypatch.setattr(sbir_ingestion_assets, "get_config", fake_get_config)
    monkeypatch.chdir(tmp_path)

    job = defs_module.defs.resolve_job_def("core_refresh_job")
    ingestion_keys = [
        AssetKey("raw_sbir_awards"),
        AssetKey("validated_sbir_awards"),
        AssetKey("sbir_validation_report"),
    ]
    assert job.asset_layer.executable_asset_keys.issuperset(ingestion_keys)

    result = job.execute_in_process(asset_selection=ingestion_keys)

    assert result.success
    raw_df = result.output_for_node("raw_sbir_awards")
    validated_df = result.output_for_node("validated_sbir_awards")
    report = result.output_for_node("sbir_validation_report")

    assert len(raw_df) > 0
    assert len(validated_df) == len(raw_df)  # pass_rate_threshold=0.0 keeps every row
    assert report["total_records"] == len(raw_df)

    evaluations = result.get_asset_check_evaluations()
    assert len(evaluations) == 1
    assert evaluations[0].check_name == "sbir_data_quality_check"
    assert evaluations[0].passed

    validated_parquet = data_root / "processed" / "validated" / "sbir_awards.parquet"
    report_json = tmp_path / "data" / "validated" / "sbir_validation_report.json"
    assert validated_parquet.is_file()
    assert report_json.is_file()
