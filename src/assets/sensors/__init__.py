"""Dagster sensors package for SBIR ETL pipeline."""

from .usaspending_refresh_sensor import usaspending_refresh_sensor

__all__ = ["usaspending_refresh_sensor"]
