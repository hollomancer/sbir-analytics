"""
StateIO economic multipliers tool.

Wraps the existing RStateIOAdapter to provide state-by-sector economic
multipliers for Track A fiscal estimation.

Data source: EPA Data Commons (StateIO pre-computed I-O tables)
Access method: R package output / CSV
Refresh cadence: Static (2012-2020 vintage data)

Known limitation: StateIO temporal coverage ends 2020. Post-2020 estimates
require extrapolation. Sectors with rapid structural change (AI, biotech)
have higher extrapolation uncertainty.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


class StateIOMultipliersTool(BaseTool):
    """Retrieve StateIO economic multipliers by state and BEA sector.

    Wraps the R StateIO adapter with the standard tool interface.
    Falls back to CSV-based lookup if R/rpy2 is not available.
    """

    name = "stateio_multipliers"
    version = "1.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        states: list[str] | None = None,
        bea_sectors: list[str] | None = None,
        awards_df: pd.DataFrame | None = None,
        csv_fallback_path: str | None = None,
    ) -> ToolResult:
        """Retrieve economic multipliers for state-sector combinations.

        Args:
            metadata: Pre-initialized metadata to populate
            states: List of state abbreviations (e.g., ["CA", "MA"])
            bea_sectors: List of BEA sector codes
            awards_df: Awards with state and bea_sector columns (alternative input)
            csv_fallback_path: Path to pre-computed multiplier CSV

        Returns:
            ToolResult with multipliers DataFrame
        """
        metadata.upstream_tools.append("naics_to_bea_crosswalk")

        # Determine state-sector pairs needed
        pairs: list[tuple[str, str]] = []
        if awards_df is not None and not awards_df.empty:
            state_col = next(
                (c for c in ["state", "company_state"] if c in awards_df.columns),
                None,
            )
            sector_col = next(
                (c for c in ["bea_sector", "sector"] if c in awards_df.columns),
                None,
            )
            if state_col and sector_col:
                unique_pairs = awards_df[[state_col, sector_col]].dropna().drop_duplicates()
                pairs = list(unique_pairs.itertuples(index=False, name=None))
        elif states and bea_sectors:
            pairs = [(s, b) for s in states for b in bea_sectors]

        if not pairs:
            metadata.warnings.append("No state-sector pairs to look up multipliers for")
            return ToolResult(data=pd.DataFrame(), metadata=metadata)

        logger.info(f"Looking up multipliers for {len(pairs)} state-sector combinations")

        # Try R adapter first, fall back to CSV
        multipliers: list[dict[str, Any]] = []
        access_method = "csv_fallback"

        try:
            from src.transformers.r_stateio_adapter import RStateIOAdapter, RPY2_AVAILABLE

            if RPY2_AVAILABLE:
                adapter = RStateIOAdapter()
                for state, sector in pairs:
                    try:
                        result = adapter.get_multiplier(state=state, sector=sector)
                        if result is not None:
                            multipliers.append({
                                "state": state,
                                "bea_sector": sector,
                                "output_multiplier": result.get("output_multiplier", 1.0),
                                "employment_multiplier": result.get("employment_multiplier", 1.0),
                                "value_added_multiplier": result.get("value_added_multiplier", 1.0),
                                "source": "stateio_r",
                            })
                    except Exception as e:
                        logger.debug(f"R adapter failed for {state}/{sector}: {e}")
                if multipliers:
                    access_method = "stateio_r_package"
        except ImportError:
            pass

        # CSV fallback
        if not multipliers and csv_fallback_path:
            try:
                csv_df = pd.read_csv(csv_fallback_path)
                for state, sector in pairs:
                    match = csv_df[
                        (csv_df["state"] == state) & (csv_df["bea_sector"] == sector)
                    ]
                    if not match.empty:
                        row = match.iloc[0]
                        multipliers.append({
                            "state": state,
                            "bea_sector": sector,
                            "output_multiplier": float(row.get("output_multiplier", 1.0)),
                            "employment_multiplier": float(row.get("employment_multiplier", 1.0)),
                            "value_added_multiplier": float(row.get("value_added_multiplier", 1.0)),
                            "source": "csv_precomputed",
                        })
                access_method = "csv_precomputed"
            except Exception as e:
                logger.warning(f"CSV fallback failed: {e}")
                metadata.warnings.append(f"CSV multiplier fallback failed: {e}")

        # If still no multipliers, use default (1.0)
        if not multipliers:
            metadata.warnings.append(
                "No multiplier source available (R or CSV). Using default multiplier of 1.0"
            )
            for state, sector in pairs:
                multipliers.append({
                    "state": state,
                    "bea_sector": sector,
                    "output_multiplier": 1.0,
                    "employment_multiplier": 1.0,
                    "value_added_multiplier": 1.0,
                    "source": "default",
                })
            access_method = "default_fallback"

        multipliers_df = pd.DataFrame(multipliers)

        metadata.record_count = len(multipliers_df)
        metadata.data_sources.append(
            DataSourceRef(
                name="EPA Data Commons (StateIO)",
                url="https://github.com/USEPA/stateior",
                version="2012-2020",
                record_count=len(multipliers_df),
                access_method=access_method,
            )
        )

        if access_method in ("csv_precomputed", "default_fallback"):
            metadata.warnings.append(
                "StateIO temporal coverage ends 2020. Post-2020 estimates "
                "require extrapolation from most recent I-O tables."
            )

        return ToolResult(data=multipliers_df, metadata=metadata)
