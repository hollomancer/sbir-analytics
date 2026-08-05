"""Opt-in recurring NSF SBIR to DoD funding-lineage research release."""

from dagster import AssetSelection, define_asset_job


nsf_defense_lineage_refresh_job = define_asset_job(
    name="nsf_defense_lineage_refresh_job",
    selection=AssetSelection.assets(
        "nsf_direct_award_release",
        "nsf_defense_funding_release",
        "nsf_defense_lineage_validation",
        "nsf_defense_lineage_graph",
    ),
    description=(
        "Refresh direct NSF awards, signed DoD funding, validation gates, and the analyst graph"
    ),
)


__all__ = ["nsf_defense_lineage_refresh_job"]
