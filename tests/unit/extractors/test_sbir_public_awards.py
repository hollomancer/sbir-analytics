from pathlib import Path

import pandas as pd

from sbir_etl.extractors.sbir_public_awards import (
    load_sbir_awards_csv,
    normalize_sbir_awards,
)
from sbir_etl.identity.sbir_awards import SBIR_AWARD_KEY_VERSION


def _award(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Agency Tracking Number": "000123",
        "Contract": "CONTRACT-1",
        "Company": "Acme",
        "Agency": "DEFENSE",
        "Branch": "NAVY",
        "Phase": "Phase II",
        "Program": "STTR",
        "Proposal Award Date": "2026-06-12",
        "Award Year": "2026",
        "Award Amount": "$1,000,000",
        "Award Title": "Navigation",
        "Abstract": "Autonomous navigation",
        "UEI": "UEI000000001",
    }
    row.update(overrides)
    return row


def test_normalizer_materializes_versioned_award_grain() -> None:
    normalized = normalize_sbir_awards(pd.DataFrame([_award()]))

    assert normalized.loc[0, "award_key_version"] == SBIR_AWARD_KEY_VERSION
    assert len(normalized.loc[0, "award_key"]) == 24
    assert normalized.loc[0, "program"] == "STTR"
    assert normalized.loc[0, "award_year"] == 2026


def test_source_editions_collapse_without_collapsing_distinct_awards() -> None:
    normalized = normalize_sbir_awards(
        pd.DataFrame(
            [
                _award(**{"Award Amount": "$1,000,000"}),
                _award(**{"Award Amount": "$2,000,000"}),
                _award(Phase="Phase I"),
            ]
        )
    )

    assert len(normalized) == 2
    phase_two = normalized.loc[normalized["phase"].eq("Phase II")].iloc[0]
    assert phase_two["amount"] == 2_000_000
    assert phase_two["source_edition_count"] == 2


def test_csv_loader_preserves_identifier_text_and_source_row(tmp_path: Path) -> None:
    path = tmp_path / "award_data.csv"
    pd.DataFrame([_award()]).to_csv(path, index=False)

    award = load_sbir_awards_csv(path).iloc[0]

    assert award["agency_tracking_number"] == "000123"
    assert award["source_row"] == 2


def test_csv_edition_collapse_is_independent_of_chunk_boundaries(tmp_path: Path) -> None:
    path = tmp_path / "award_data.csv"
    pd.DataFrame(
        [
            _award(**{"Award Amount": "$1,000,000"}),
            _award(**{"Award Amount": "$2,000,000"}),
        ]
    ).to_csv(path, index=False)

    awards = load_sbir_awards_csv(path, chunk_size=1)

    assert len(awards) == 1
    assert awards.loc[0, "amount"] == 2_000_000
    assert awards.loc[0, "source_edition_count"] == 2
    assert awards.loc[0, "source_edition_variants"] == 2
