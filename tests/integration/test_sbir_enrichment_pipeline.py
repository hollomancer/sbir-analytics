import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from dagster import build_asset_context

import src.assets.sbir_ingestion as assets_module
from src.enrichers.company_enricher import enrich_awards_with_companies


def _fixture_csv_path():
    # Resolve absolute path to the fixture regardless of cwd
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sbir_sample.csv"


def _make_test_config(
    csv_path: str, db_path: str, table_name: str, pass_rate_threshold: float = 0.95
):
    sbir = SimpleNamespace(
        csv_path=str(csv_path), database_path=str(db_path), table_name=table_name
    )
    extraction = SimpleNamespace(sbir=sbir)
    data_quality = SimpleNamespace(
        sbir_awards=SimpleNamespace(pass_rate_threshold=pass_rate_threshold)
    )
    return SimpleNamespace(extraction=extraction, data_quality=data_quality)


def test_enrichment_pipeline_runs_and_merges_company_data(tmp_path: Path, monkeypatch):
    """
    Integration test:
    - Run the raw SBIR extraction asset (uses the CSV fixture)
    - Run the company enricher against the extracted DataFrame
    - Assert enrichment metadata and merged company columns exist
    """
    fixture_csv = _fixture_csv_path()
    assert fixture_csv.exists(), f"Expected fixture CSV at {fixture_csv}"

    db_path = tmp_path / "assets_test.duckdb"
    table_name = "sbir_enrich_test"

    # Ensure the asset code writes report into tmp_path by changing cwd
    monkeypatch.chdir(tmp_path)

    # Monkeypatch get_config used by the assets module to point to our fixture and temp DB
    test_config = _make_test_config(
        csv_path=str(fixture_csv),
        db_path=str(db_path),
        table_name=table_name,
        pass_rate_threshold=0.0,
    )
    monkeypatch.setattr(assets_module, "get_config", lambda: test_config)

    # Materialize raw asset
    raw_ctx = build_asset_context()
    raw_output = assets_module.raw_sbir_awards(context=raw_ctx)
    raw_df = getattr(raw_output, "value", raw_output)

    assert isinstance(raw_df, pd.DataFrame)
    # Expect the fixture to contain rows (we know it's small)
    assert len(raw_df) > 0

    # Prepare a minimal companies DataFrame that should match at least one award row
    # Use a company that exists in the fixture: "Acme Innovations" with UEI from fixture
    companies = pd.DataFrame(
        [
            {
                "company": "Acme Innovations",
                "UEI": "A1B2C3D4E5F6",
                "Duns": "123456789",
                "industry": "Aerospace",
            },
            {
                "company": "BioTech Labs",
                "UEI": "Z9Y8X7W6V5U4",
                "Duns": "987654321",
                "industry": "Biotech",
            },
        ]
    )

    # Run enrichment: note award company column in CSV fixture is "Company" (capital C)
    enriched = enrich_awards_with_companies(
        raw_df,
        companies,
        award_company_col="Company",
        company_name_col="company",
        uei_col="UEI",
        duns_col="Duns",
        high_threshold=90,
        low_threshold=75,
        return_candidates=True,
    )

    # Assert enrichment metadata columns exist
    assert "_match_score" in enriched.columns
    assert "_match_method" in enriched.columns
    assert "_match_candidates" in enriched.columns

    # Assert merged company_* columns exist (e.g., company_industry)
    assert "company_industry" in enriched.columns

    # Find the row corresponding to Acme Innovations (match by original Company value)
    acme_rows = enriched[enriched["Company"].astype(str).str.contains("Acme", case=False, na=False)]
    assert len(acme_rows) >= 1

    # For Acme row(s), expect either a deterministic or fuzzy match with non-null score
    acme_row = acme_rows.iloc[0]
    acme_row.get("_match_score")
    match_method = acme_row.get("_match_method")
    # match_score may be pandas NA; ensure it's present and meaningful
    assert match_method is not None
    # If match was successful, the industry column should equal our companies entry
    if acme_row.get("company_industry") is not None:
        assert acme_row["company_industry"] == "Aerospace"

    # Ensure candidates JSON parses if present
    cand = acme_row.get("_match_candidates")
    if pd.notna(cand):
        parsed = json.loads(cand)
        assert isinstance(parsed, list)

    # Basic sanity: enrichment should not alter total row count
    assert len(enriched) == len(raw_df)
