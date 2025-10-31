#!/usr/bin/env python3
"""Assess USAspending coverage for SBIR enrichment.

This script evaluates how well USAspending data can enrich SBIR awards by
joining on common identifiers (UEI, DUNS, PIID) and calculating match rates.
"""

import argparse
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd
from loguru import logger


class USAspendingCoverageAssessor:
    """Assesses USAspending coverage for SBIR enrichment."""

    def __init__(
        self, usaspending_dump: Path | None = None, profile_json: Path | None = None
    ):
        """Initialize assessor.

        Args:
            usaspending_dump: Path to USAspending dump (optional)
            profile_json: Path to profiling results JSON (optional)
        """
        self.usaspending_dump = usaspending_dump
        self.profile_json = profile_json
        self.connection: duckdb.DuckDBPyConnection | None = None

    def load_sbir_sample(self, sample_path: Path, limit: int | None = None) -> pd.DataFrame:
        """Load SBIR awards sample data.

        Args:
            sample_path: Path to SBIR sample CSV
            limit: Optional row limit for testing

        Returns:
            DataFrame with SBIR sample data
        """
        logger.info(f"Loading SBIR sample from: {sample_path}")

        if not sample_path.exists():
            raise FileNotFoundError(f"SBIR sample file not found: {sample_path}")

        df = pd.read_csv(sample_path, nrows=limit)
        logger.info(f"Loaded {len(df)} SBIR awards")

        # Log key identifier coverage
        total = len(df)
        uei_count = df["UEI"].notna().sum()
        duns_count = df["Duns"].notna().sum()
        contract_count = df["Contract"].notna().sum()

        logger.info("SBIR identifier coverage:")
        logger.info(f"  UEI: {uei_count}/{total} ({uei_count/total:.1%})")
        logger.info(f"  DUNS: {duns_count}/{total} ({duns_count/total:.1%})")
        logger.info(f"  Contract: {contract_count}/{total} ({contract_count/total:.1%})")

        return df

    def get_usaspending_sample(
        self, table_name: str = "transaction_normalized", limit: int = 10000
    ) -> pd.DataFrame:
        """Get sample USAspending data for assessment.

        Args:
            table_name: USAspending table to sample
            limit: Number of rows to sample

        Returns:
            DataFrame with USAspending sample data
        """
        logger.info(f"Sampling {limit} rows from USAspending table: {table_name}")

        if self.profile_json and self.profile_json.exists():
            # Use profiling results if available
            return self._load_from_profile(table_name, limit)
        elif self.usaspending_dump:
            # Query directly from dump
            return self._query_from_dump(table_name, limit)
        else:
            raise ValueError("Either profile_json or usaspending_dump must be provided")

    def _load_from_profile(self, table_name: str, limit: int) -> pd.DataFrame:
        """Load data from profiling results."""
        logger.info(f"Loading from profile: {self.profile_json}")

        with open(self.profile_json) as f:
            profile = json.load(f)

        # Find table sample in profile
        table_sample = None
        for sample in profile.get("table_samples", []):
            if sample.get("table_name") == table_name:
                table_sample = sample
                break

        if not table_sample:
            raise ValueError(f"Table {table_name} not found in profile")

        # Convert sample data to DataFrame
        sample_data = table_sample.get("sample_data", [])
        if not sample_data:
            logger.warning(f"No sample data for table {table_name}")
            return pd.DataFrame()

        df = pd.DataFrame(sample_data)

        # Debug: Show original columns
        logger.info(f"Original columns in {table_name}: {list(df.columns)}")

        # Map columns based on actual data structure from profiling
        if table_name == "recipient_lookup":
            # Based on profiling: columns are '0'=DUNS, '1'=company_name, '18'=UEI
            column_mapping = {"0": "recipient_duns", "1": "recipient_name", "18": "recipient_uei"}
            df = df.rename(columns=column_mapping)
        elif table_name == "transaction_normalized":
            # Transaction data - may not have recipient info directly
            # This table contains financial transaction data
            logger.warning(f"Table {table_name} contains transaction data, not recipient data")

        # Debug: Show columns after mapping
        logger.info(f"Columns after mapping in {table_name}: {list(df.columns)}")

        logger.info(f"Loaded {len(df)} sample rows from profile for {table_name}")
        return df

    def _query_from_dump(self, table_name: str, limit: int) -> pd.DataFrame:
        """Query data directly from dump."""
        logger.info(f"Querying from dump: {self.usaspending_dump}")

        if not self.connection:
            self.connection = duckdb.connect(":memory:")
            self.connection.execute("INSTALL postgres_scanner;")
            self.connection.execute("LOAD postgres_scanner;")

        try:
            query = f"""
            SELECT
                award_id_piid,
                recipient_uei,
                recipient_unique_id as recipient_duns,
                federal_action_obligation,
                awarding_agency_name,
                funding_agency_name,
                action_date
            FROM postgres_scan('{self.usaspending_dump}', '{table_name}')
            WHERE award_id_piid IS NOT NULL
            LIMIT {limit}
            """

            df = self.connection.execute(query).fetchdf()
            logger.info(f"Queried {len(df)} rows from dump")
            return df

        except Exception as e:
            logger.error(f"Query failed: {e}")
            return pd.DataFrame()

    def assess_coverage(self, sbir_df: pd.DataFrame, usaspending_df: pd.DataFrame) -> dict:
        """Assess coverage by joining SBIR and USAspending data.

        Args:
            sbir_df: SBIR awards DataFrame
            usaspending_df: USAspending recipient DataFrame

        Returns:
            Dictionary with coverage assessment results
        """
        logger.info("Assessing coverage between SBIR and USAspending recipient data")

        results = {
            "total_sbir_awards": len(sbir_df),
            "total_usaspending_recipients": len(usaspending_df),
            "match_rates": {},
            "coverage_details": {},
            "data_quality_notes": [],
        }

        # Clean and prepare data
        sbir_clean = self._prepare_sbir_data(sbir_df)
        usaspending_clean = self._prepare_usaspending_data(usaspending_df)

        # Check if we have the expected columns
        expected_cols = ["recipient_uei", "recipient_duns", "recipient_name"]
        available_cols = [col for col in expected_cols if col in usaspending_clean.columns]
        results["data_quality_notes"].append(f"Available USAspending columns: {available_cols}")

        # Assess matches by identifier - only for available columns
        identifiers = []
        if "recipient_uei" in usaspending_clean.columns:
            identifiers.append(("uei", "UEI", "recipient_uei"))
        if "recipient_duns" in usaspending_clean.columns:
            identifiers.append(("duns", "Duns", "recipient_duns"))

        # Note: Contract matching would require transaction table, not recipient table
        results["data_quality_notes"].append(
            "Contract matching requires transaction_normalized table data"
        )

        for identifier_name, sbir_col, usaspending_col in identifiers:
            match_rate = self._calculate_match_rate(
                sbir_clean, usaspending_clean, sbir_col, usaspending_col
            )
            results["match_rates"][identifier_name] = match_rate

        # Calculate overall coverage (any identifier match)
        if identifiers:
            results["overall_coverage"] = self._calculate_overall_coverage(
                sbir_clean, usaspending_clean
            )
        else:
            results["overall_coverage"] = {
                "match_rate": 0.0,
                "matched_awards": 0,
                "total_awards": len(sbir_clean),
            }
            results["data_quality_notes"].append("No identifier columns available for matching")

        # Check target achievement
        target_rate = 0.70  # 70%
        results["target_achieved"] = results["overall_coverage"]["match_rate"] >= target_rate

        logger.info(f"Overall coverage: {results['overall_coverage']['match_rate']:.1%}")
        logger.info(f"Target achieved: {results['target_achieved']}")

        return results

    def _prepare_sbir_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare SBIR data for matching."""
        # Clean identifiers
        df = df.copy()
        df["UEI"] = df["UEI"].astype(str).str.strip().str.upper()
        df["Duns"] = df["Duns"].astype(str).str.strip()
        df["Contract"] = df["Contract"].astype(str).str.strip()

        # Replace empty strings with NaN
        df = df.replace("", pd.NA)
        return df

    def _prepare_usaspending_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare USAspending data for matching."""
        df = df.copy()

        # Handle columns that may or may not exist
        if "recipient_uei" in df.columns:
            df["recipient_uei"] = df["recipient_uei"].astype(str).str.strip().str.upper()
        if "recipient_duns" in df.columns:
            df["recipient_duns"] = df["recipient_duns"].astype(str).str.strip()
        if "award_id_piid" in df.columns:
            df["award_id_piid"] = df["award_id_piid"].astype(str).str.strip()

        # Replace empty strings with NaN
        df = df.replace("", pd.NA)
        return df

    def _calculate_match_rate(
        self,
        sbir_df: pd.DataFrame,
        usaspending_df: pd.DataFrame,
        sbir_col: str,
        usaspending_col: str,
    ) -> dict:
        """Calculate match rate for a specific identifier."""
        # Get non-null values
        sbir_valid = sbir_df[sbir_df[sbir_col].notna()]
        usaspending_valid = usaspending_df[usaspending_df[usaspending_col].notna()]

        if len(sbir_valid) == 0:
            return {
                "match_rate": 0.0,
                "matched_awards": 0,
                "total_awards_with_id": 0,
                "total_usaspending_with_id": len(usaspending_valid),
            }

        # Find matches
        sbir_ids = set(sbir_valid[sbir_col].dropna())
        usaspending_ids = set(usaspending_valid[usaspending_col].dropna())

        matched_ids = sbir_ids.intersection(usaspending_ids)
        matched_awards = len(matched_ids)

        return {
            "match_rate": matched_awards / len(sbir_valid),
            "matched_awards": matched_awards,
            "total_awards_with_id": len(sbir_valid),
            "total_usaspending_with_id": len(usaspending_valid),
            "matched_ids_sample": list(matched_ids)[:5],  # Sample of matches
        }

    def _calculate_overall_coverage(
        self, sbir_df: pd.DataFrame, usaspending_df: pd.DataFrame
    ) -> dict:
        """Calculate overall coverage using any identifier."""
        # Create match flags for each identifier
        matches = []
        breakdown = {}

        # UEI matches (if available)
        if "recipient_uei" in usaspending_df.columns:
            uei_matches = self._get_matches(sbir_df, usaspending_df, "UEI", "recipient_uei")
            matches.append(uei_matches)
            breakdown["uei_matches"] = len(uei_matches)
        else:
            breakdown["uei_matches"] = 0

        # DUNS matches (if available)
        if "recipient_duns" in usaspending_df.columns:
            duns_matches = self._get_matches(sbir_df, usaspending_df, "Duns", "recipient_duns")
            matches.append(duns_matches)
            breakdown["duns_matches"] = len(duns_matches)
        else:
            breakdown["duns_matches"] = 0

        # Contract matches (if available - would need transaction table)
        if "award_id_piid" in usaspending_df.columns:
            contract_matches = self._get_matches(
                sbir_df, usaspending_df, "Contract", "award_id_piid"
            )
            matches.append(contract_matches)
            breakdown["contract_matches"] = len(contract_matches)
        else:
            breakdown["contract_matches"] = 0

        # Combine all matches (any identifier)
        all_matched_indices = set()
        for match_set in matches:
            all_matched_indices.update(match_set)

        total_sbir = len(sbir_df)
        matched_sbir = len(all_matched_indices)

        return {
            "match_rate": matched_sbir / total_sbir if total_sbir > 0 else 0.0,
            "matched_awards": matched_sbir,
            "total_awards": total_sbir,
            "breakdown": breakdown,
        }

    def _get_matches(
        self,
        sbir_df: pd.DataFrame,
        usaspending_df: pd.DataFrame,
        sbir_col: str,
        usaspending_col: str,
    ) -> set:
        """Get indices of matching SBIR awards."""
        sbir_valid = sbir_df[sbir_df[sbir_col].notna()]
        usaspending_valid = usaspending_df[usaspending_df[usaspending_col].notna()]

        sbir_ids = set(sbir_valid[sbir_col].dropna())
        usaspending_ids = set(usaspending_valid[usaspending_col].dropna())

        matched_ids = sbir_ids.intersection(usaspending_ids)

        # Find indices of matched awards
        matched_indices = set()
        for idx, row in sbir_valid.iterrows():
            if row[sbir_col] in matched_ids:
                matched_indices.add(idx)

        return matched_indices

    def save_report(self, results: dict, output_path: Path):
        """Save assessment report to file.

        Args:
            results: Assessment results dictionary
            output_path: Path to save the report
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"Assessment report saved to: {output_path}")

    def close(self):
        """Clean up resources."""
        if self.connection:
            self.connection.close()
            self.connection = None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Assess USAspending coverage for SBIR enrichment")
    parser.add_argument(
        "--sbir-sample",
        type=Path,
        default=Path("tests/fixtures/sbir_sample.csv"),
        help="Path to SBIR sample CSV",
    )
    parser.add_argument(
        "--usaspending-dump",
        type=Path,
        default=Path("/Volumes/X10 Pro/projects/usaspending-db-subset_20251006.zip"),
        help="Path to USAspending dump",
    )
    parser.add_argument(
        "--profile-json",
        type=Path,
        default=Path("reports/usaspending_subset_profile.json"),
        help="Path to profiling results JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/usaspending_coverage_assessment.json"),
        help="Output path for assessment report",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Limit for SBIR sample size",
    )
    parser.add_argument(
        "--usaspending-limit",
        type=int,
        default=10000,
        help="Limit for USAspending sample size",
    )
    parser.add_argument(
        "--table-name",
        type=str,
        default="recipient_lookup",
        help="USAspending table to analyze (recipient_lookup or transaction_normalized)",
    )

    args = parser.parse_args()

    # Set up logging
    logger.add(sys.stderr, level="INFO")

    assessor = USAspendingCoverageAssessor(args.usaspending_dump, args.profile_json)

    try:
        # Load SBIR sample
        sbir_df = assessor.load_sbir_sample(args.sbir_sample, args.limit)

        # Get USAspending sample
        usaspending_df = assessor.get_usaspending_sample(
            table_name=args.table_name, limit=args.usaspending_limit
        )

        # Assess coverage
        results = assessor.assess_coverage(sbir_df, usaspending_df)

        # Save report
        assessor.save_report(results, args.output)

        # Print summary
        print("\n=== USAspending Coverage Assessment Summary ===")
        print(f"SBIR Awards Analyzed: {results['total_sbir_awards']}")
        print(
            f"USAspending Recipients Sampled: {results.get('total_usaspending_recipients', 'N/A')}"
        )
        if "overall_coverage" in results:
            print(".1%")
            print(f"Target Achieved (≥70%): {results['target_achieved']}")

        print("\nMatch Rates by Identifier:")
        for identifier, stats in results["match_rates"].items():
            print(".1%")

        if results.get("data_quality_notes"):
            print("\nData Quality Notes:")
            for note in results["data_quality_notes"]:
                print(f"- {note}")

        logger.info("Assessment complete")

    except Exception as e:
        logger.error(f"Assessment failed: {e}")
        sys.exit(1)
    finally:
        assessor.close()


if __name__ == "__main__":
    main()
