"""Example: Extending GeographicResolver to resolve congressional districts.

This demonstrates how to add congressional district resolution to the existing
fiscal impact pipeline. Since SBIR awards include full addresses, we can
geocode them to get congressional districts.

This is a proof-of-concept showing the implementation pattern.
"""

from pathlib import Path
import sys

import pandas as pd

# Ensure the src package is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class CongressionalDistrictResolver:
    """Resolve congressional districts from addresses.

    This class demonstrates how to extend the existing GeographicResolver
    to add congressional district capabilities.
    """

    def __init__(self, method: str = "census_api"):
        """Initialize district resolver.

        Args:
            method: Resolution method to use:
                - "census_api": US Census Geocoder API (free, accurate)
                - "zip_crosswalk": ZIP-to-district mapping (fast, approximate)
                - "google_civic": Google Civic Information API (accurate, requires key)
        """
        self.method = method

    def resolve_district_from_address(
        self, address: str, city: str, state: str, zip_code: str
    ) -> dict:
        """Resolve congressional district from address components.

        Args:
            address: Street address
            city: City name
            state: Two-letter state code
            zip_code: ZIP code

        Returns:
            Dictionary with district info:
            {
                "congressional_district": "CA-12",
                "district_number": "12",
                "state": "CA",
                "confidence": 0.95,
                "method": "census_api",
                "representative": "Nancy Pelosi",  # if available
            }
        """
        if self.method == "census_api":
            return self._resolve_via_census_api(address, city, state, zip_code)
        elif self.method == "zip_crosswalk":
            return self._resolve_via_zip_crosswalk(zip_code)
        elif self.method == "google_civic":
            return self._resolve_via_google_civic(address, city, state, zip_code)
        else:
            raise ValueError(f"Unknown method: {self.method}")

    def _resolve_via_census_api(self, address: str, city: str, state: str, zip_code: str) -> dict:
        """Resolve district using US Census Geocoder API.

        Census API: https://geocoding.geo.census.gov/geocoder/
        Free, authoritative, but rate-limited.

        Example API call:
        https://geocoding.geo.census.gov/geocoder/geographies/address?
            street=4600+Silver+Hill+Rd&
            city=Washington&
            state=DC&
            zip=20233&
            benchmark=Public_AR_Current&
            vintage=Current_Current&
            format=json
        """
        import time
        import requests

        # Census Geocoder API endpoint
        base_url = "https://geocoding.geo.census.gov/geocoder/geographies/address"

        params = {
            "street": address,
            "city": city,
            "state": state,
            "zip": zip_code,
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "format": "json",
        }

        try:
            # Add small delay to respect rate limits
            time.sleep(0.1)

            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Parse response
            if data.get("result", {}).get("addressMatches"):
                match = data["result"]["addressMatches"][0]
                geographies = match.get("geographies", {})

                # Extract congressional district info
                cd_info = geographies.get("116th Congress", [{}])[0]  # or use current congress
                district_code = cd_info.get("BASENAME", "")

                if district_code:
                    return {
                        "congressional_district": f"{state}-{district_code}",
                        "district_number": district_code,
                        "state": state,
                        "confidence": 0.95,
                        "method": "census_api",
                        "matched_address": match.get("matchedAddress"),
                    }

        except Exception as e:
            print(f"Census API error: {e}")

        return {
            "congressional_district": None,
            "confidence": 0.0,
            "method": "census_api",
            "error": "Could not resolve district",
        }

    def _resolve_via_zip_crosswalk(self, zip_code: str) -> dict:
        """Resolve district using ZIP-to-district crosswalk.

        Uses HUD's ZIP-to-Congressional District crosswalk file.
        Fast but approximate (some ZIPs span multiple districts).

        Data source: https://www.huduser.gov/portal/datasets/usps_crosswalk.html
        """
        # This would load a crosswalk file
        # For now, demonstrate the concept

        # Example crosswalk data (would be loaded from file)
        # zip_to_district = pd.read_csv("data/reference/zip_to_cd_118.csv")

        # Mock example
        mock_crosswalk = {
            "94102": {"district": "CA-11", "state": "CA", "allocation": 1.0},
            "10001": {"district": "NY-12", "state": "NY", "allocation": 0.8},
            "02101": {"district": "MA-07", "state": "MA", "allocation": 0.9},
        }

        zip5 = zip_code[:5] if len(zip_code) >= 5 else zip_code

        if zip5 in mock_crosswalk:
            info = mock_crosswalk[zip5]
            return {
                "congressional_district": info["district"],
                "district_number": info["district"].split("-")[1],
                "state": info["state"],
                "confidence": info["allocation"],  # Lower if ZIP spans multiple districts
                "method": "zip_crosswalk",
            }

        return {
            "congressional_district": None,
            "confidence": 0.0,
            "method": "zip_crosswalk",
            "error": "ZIP not in crosswalk",
        }

    def _resolve_via_google_civic(self, address: str, city: str, state: str, zip_code: str) -> dict:
        """Resolve district using Google Civic Information API.

        Requires API key. Very accurate and includes current representative info.
        API docs: https://developers.google.com/civic-information
        """
        import os
        import requests

        api_key = os.environ.get("GOOGLE_CIVIC_API_KEY")
        if not api_key:
            return {
                "congressional_district": None,
                "confidence": 0.0,
                "method": "google_civic",
                "error": "GOOGLE_CIVIC_API_KEY not set",
            }

        # Format address
        full_address = f"{address}, {city}, {state} {zip_code}"

        url = "https://www.googleapis.com/civicinfo/v2/representatives"
        params = {
            "key": api_key,
            "address": full_address,
            "levels": "country",
            "roles": "legislatorLowerBody",
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Extract congressional district info
            divisions = data.get("divisions", {})
            for division_id, _division_data in divisions.items():
                if "cd:" in division_id:
                    # Extract state and district from ocd-division ID
                    # Example: ocd-division/country:us/state:ca/cd:12
                    parts = division_id.split("/")
                    state_part = next((p for p in parts if p.startswith("state:")), None)
                    cd_part = next((p for p in parts if p.startswith("cd:")), None)

                    if state_part and cd_part:
                        state_code = state_part.split(":")[1].upper()
                        district_num = cd_part.split(":")[1]

                        # Get representative name if available
                        officials = data.get("officials", [])
                        rep_name = officials[0].get("name") if officials else None

                        return {
                            "congressional_district": f"{state_code}-{district_num}",
                            "district_number": district_num,
                            "state": state_code,
                            "confidence": 0.98,
                            "method": "google_civic",
                            "representative": rep_name,
                        }

        except Exception as e:
            print(f"Google Civic API error: {e}")

        return {
            "congressional_district": None,
            "confidence": 0.0,
            "method": "google_civic",
            "error": "Could not resolve district",
        }

    def enrich_awards_with_districts(self, awards_df: pd.DataFrame) -> pd.DataFrame:
        """Add congressional district info to awards DataFrame.

        Args:
            awards_df: DataFrame with SBIR awards (must have address fields)

        Returns:
            DataFrame with added congressional_district column
        """
        enriched = awards_df.copy()

        # Initialize new columns
        enriched["congressional_district"] = None
        enriched["district_number"] = None
        enriched["district_confidence"] = None
        enriched["district_method"] = None

        print(f"Resolving congressional districts for {len(awards_df)} awards...")
        print(f"Using method: {self.method}")

        resolved_count = 0

        for idx, row in awards_df.iterrows():
            # Get address components
            address = row.get("company_address") or row.get("address1", "")
            city = row.get("company_city", "")
            state = row.get("company_state", "")
            zip_code = row.get("company_zip", "")

            # Skip if missing required fields
            if not all([address, city, state, zip_code]):
                continue

            # Resolve district
            result = self.resolve_district_from_address(address, city, state, zip_code)

            if result.get("congressional_district"):
                enriched.at[idx, "congressional_district"] = result["congressional_district"]
                enriched.at[idx, "district_number"] = result.get("district_number")
                enriched.at[idx, "district_confidence"] = result["confidence"]
                enriched.at[idx, "district_method"] = result["method"]
                resolved_count += 1

        resolution_rate = resolved_count / len(awards_df) if len(awards_df) > 0 else 0
        print(f"Resolved {resolved_count}/{len(awards_df)} districts ({resolution_rate:.1%})")

        return enriched


def demonstrate_district_resolution():
    """Demonstrate congressional district resolution."""

    # Create sample awards with addresses
    awards_df = pd.DataFrame(
        {
            "award_id": ["SBIR-001", "SBIR-002", "SBIR-003"],
            "company_name": ["Tech Corp", "Bio Inc", "Mfg LLC"],
            "company_address": [
                "1600 Amphitheatre Parkway",
                "1 Main Street",
                "100 Innovation Drive",
            ],
            "company_city": ["Mountain View", "Cambridge", "Austin"],
            "company_state": ["CA", "MA", "TX"],
            "company_zip": ["94043", "02142", "78701"],
            "award_amount": [1000000, 500000, 750000],
        }
    )

    print("=" * 80)
    print("CONGRESSIONAL DISTRICT RESOLUTION DEMONSTRATION")
    print("=" * 80)
    print()

    print("Sample awards:")
    print(awards_df[["company_name", "company_city", "company_state"]].to_string(index=False))
    print()

    # Try ZIP crosswalk method (fastest, no API calls needed)
    print("Method 1: ZIP-to-District Crosswalk (fast, approximate)")
    print("-" * 80)
    resolver_zip = CongressionalDistrictResolver(method="zip_crosswalk")
    enriched_zip = resolver_zip.enrich_awards_with_districts(awards_df)
    print(
        enriched_zip[["company_name", "congressional_district", "district_confidence"]].to_string(
            index=False
        )
    )
    print()

    # Census API method would be:
    print("Method 2: Census Geocoder API (accurate, free, rate-limited)")
    print("-" * 80)
    print("To use: resolver_census = CongressionalDistrictResolver(method='census_api')")
    print("Note: Requires internet connection and respects rate limits")
    print()

    # Google Civic method would be:
    print("Method 3: Google Civic Information API (accurate, requires API key)")
    print("-" * 80)
    print("To use: resolver_google = CongressionalDistrictResolver(method='google_civic')")
    print("Note: Requires GOOGLE_CIVIC_API_KEY environment variable")
    print()

    print("=" * 80)
    print("INTEGRATION WITH FISCAL IMPACT PIPELINE")
    print("=" * 80)
    print()
    print("Once districts are resolved, you can aggregate impacts:")
    print()
    print("# Aggregate awards by district")
    print("district_awards = enriched_zip.groupby('congressional_district')['award_amount'].sum()")
    print()
    print("# Calculate state-level impacts (using StateIO)")
    print("state_impacts = calculator.calculate_impacts_from_sbir_awards(awards_df)")
    print()
    print("# Allocate state impacts to districts proportionally")
    print("district_impacts = allocate_state_impacts_to_districts(")
    print("    state_impacts=state_impacts,")
    print("    district_awards=enriched_zip")
    print(")")


if __name__ == "__main__":
    demonstrate_district_resolution()
