"""Dagster assets for SBIR ETL pipeline."""

from .example_assets import raw_sbir_data, validated_sbir_data
from .uspto_assets import (
    raw_uspto_assignments,
    raw_uspto_assignees,
    raw_uspto_assignors,
    raw_uspto_documentids,
    raw_uspto_conveyances,
    parsed_uspto_assignments,
    parsed_uspto_assignees,
    parsed_uspto_assignors,
    parsed_uspto_documentids,
    parsed_uspto_conveyances,
    uspto_assignments_parsing_check,
    uspto_assignees_parsing_check,
    uspto_assignors_parsing_check,
    uspto_documentids_parsing_check,
    uspto_conveyances_parsing_check,
)

__all__ = [
    "raw_sbir_data",
    "validated_sbir_data",
    "raw_uspto_assignments",
    "raw_uspto_assignees",
    "raw_uspto_assignors",
    "raw_uspto_documentids",
    "raw_uspto_conveyances",
    "parsed_uspto_assignments",
    "parsed_uspto_assignees",
    "parsed_uspto_assignors",
    "parsed_uspto_documentids",
    "parsed_uspto_conveyances",
    "uspto_assignments_parsing_check",
    "uspto_assignees_parsing_check",
    "uspto_assignors_parsing_check",
    "uspto_documentids_parsing_check",
    "uspto_conveyances_parsing_check",
]
