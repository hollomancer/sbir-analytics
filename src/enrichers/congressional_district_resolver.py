"""Congressional District Resolution Service.

This module resolves company addresses to congressional districts using
multiple methods with fallback logic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


@dataclass
class CongressionalDistrictResult:
    """Result of congressional district resolution."""

    congressional_district: str | None
    district_number: str | None
    state: str | None
    confidence: float
    method: str
    timestamp: datetime
    metadata: dict[str, Any]


class CongressionalDistrictResolver:
    """Resolve congressional districts from company addresses.

    Supports multiple resolution methods with automatic fallback:
    1. ZIP code crosswalk (fast, approximate, ~80-90% accurate)
    2. Census Geocoder API (accurate, free, rate-limited)
    3. Google Civic Information API (accurate, requires API key)
    """

    def __init__(
        self,
        method: str = "auto",
        crosswalk_path: str | Path | None = None,
        census_api_delay: float = 0.2,
    ):
        """Initialize congressional district resolver.

        Args:
            method: Resolution method to use:
                - "auto": Try multiple methods with fallback (recommended)
                - "zip_crosswalk": ZIP-to-district mapping only
                - "census_api": US Census Geocoder API only
                - "google_civic": Google Civic Information API only
            crosswalk_path: Path to HUD ZIP-to-district crosswalk file (optional)
            census_api_delay: Delay between Census API calls in seconds (rate limiting)
        """
        self.method = method
        self.census_api_delay = census_api_delay
        self.crosswalk_path = Path(crosswalk_path) if crosswalk_path else None

        # Load ZIP crosswalk data if available
        self.zip_crosswalk: dict[str, dict] | None = None
        if self.crosswalk_path and self.crosswalk_path.exists():
            self._load_zip_crosswalk()
        elif method in ("zip_crosswalk", "auto"):
            logger.warning(
                "ZIP crosswalk file not provided. ZIP-based resolution will be unavailable. "
                "Download from: https://www.huduser.gov/portal/datasets/usps_crosswalk.html"
            )

        logger.info(f"Initialized CongressionalDistrictResolver with method='{method}'")

    def _load_zip_crosswalk(self) -> None:
        """Load HUD ZIP-to-Congressional District crosswalk file."""
        try:
            logger.info(f"Loading ZIP crosswalk from {self.crosswalk_path}")

            # HUD crosswalk format: ZIP, CD (congressional district), allocation ratio
            # Example columns: ZIP, TOT_RATIO, CD118 (for 118th Congress)
            df = pd.read_csv(self.crosswalk_path)

            # Build lookup dictionary: ZIP -> {district, state, allocation}
            self.zip_crosswalk = {}

            for _, row in df.iterrows():
                zip_code = str(row.get("ZIP", "")).zfill(5)
                # Extract CD (e.g., "0612" -> CA-12, first 2 digits are state FIPS)
                cd_code = str(row.get("CD118", row.get("CD", ""))).zfill(4)

                if len(cd_code) == 4:
                    district_num = cd_code[2:]

                    # Convert state FIPS to state code (would need FIPS lookup)
                    # For now, extract from other column if available
                    state = row.get("USPS", row.get("STATE", ""))

                    allocation = float(row.get("TOT_RATIO", row.get("RES_RATIO", 1.0)))

                    district_key = f"{state}-{district_num}" if state else cd_code

                    self.zip_crosswalk[zip_code] = {
                        "district": district_key,
                        "state": state,
                        "district_number": district_num,
                        "allocation": allocation,
                    }

            logger.info(f"Loaded {len(self.zip_crosswalk)} ZIP-to-district mappings")

        except Exception as e:
            logger.error(f"Failed to load ZIP crosswalk: {e}")
            self.zip_crosswalk = None

    def resolve_district_from_zip(self, zip_code: str) -> CongressionalDistrictResult | None:
        """Resolve district using ZIP code crosswalk.

        Args:
            zip_code: 5 or 9 digit ZIP code

        Returns:
            District resolution result or None
        """
        if not self.zip_crosswalk:
            return None

        # Normalize to 5-digit ZIP
        zip5 = zip_code[:5] if len(zip_code) >= 5 else zip_code.zfill(5)

        if zip5 in self.zip_crosswalk:
            info = self.zip_crosswalk[zip5]

            return CongressionalDistrictResult(
                congressional_district=info["district"],
                district_number=info["district_number"],
                state=info.get("state"),
                confidence=info["allocation"],  # Lower if ZIP spans multiple districts
                method="zip_crosswalk",
                timestamp=datetime.now(),
                metadata={"zip_code": zip5, "allocation": info["allocation"]},
            )

        return None

    def resolve_district_from_census_api(
        self, address: str, city: str, state: str, zip_code: str
    ) -> CongressionalDistrictResult | None:
        """Resolve district using US Census Geocoder API.

        Free and authoritative, but rate-limited. Adds delay between requests.

        API: https://geocoding.geo.census.gov/geocoder/

        Args:
            address: Street address
            city: City name
            state: Two-letter state code
            zip_code: ZIP code

        Returns:
            District resolution result or None
        """
        try:
            import requests

            # Add delay to respect rate limits
            time.sleep(self.census_api_delay)

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

            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Parse response
            if data.get("result", {}).get("addressMatches"):
                match = data["result"]["addressMatches"][0]
                geographies = match.get("geographies", {})

                # Extract congressional district (try different Congress versions)
                cd_info = (
                    geographies.get("118th Congress", [{}])[0]
                    or geographies.get("117th Congress", [{}])[0]
                    or geographies.get("116th Congress", [{}])[0]
                )

                district_code = cd_info.get("BASENAME", "")

                if district_code:
                    return CongressionalDistrictResult(
                        congressional_district=f"{state}-{district_code}",
                        district_number=district_code,
                        state=state,
                        confidence=0.95,
                        method="census_api",
                        timestamp=datetime.now(),
                        metadata={
                            "matched_address": match.get("matchedAddress"),
                            "coordinates": match.get("coordinates", {}),
                        },
                    )

        except Exception as e:
            logger.debug(f"Census API error for {address}, {city}, {state}: {e}")

        return None

    def resolve_district_from_google_civic(
        self, address: str, city: str, state: str, zip_code: str, api_key: str
    ) -> CongressionalDistrictResult | None:
        """Resolve district using Google Civic Information API.

        Requires API key. Very accurate and includes current representative info.

        API: https://developers.google.com/civic-information

        Args:
            address: Street address
            city: City name
            state: Two-letter state code
            zip_code: ZIP code
            api_key: Google API key

        Returns:
            District resolution result or None
        """
        try:
            import requests

            full_address = f"{address}, {city}, {state} {zip_code}"

            url = "https://www.googleapis.com/civicinfo/v2/representatives"
            params = {
                "key": api_key,
                "address": full_address,
                "levels": "country",
                "roles": "legislatorLowerBody",
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Extract congressional district from OCD division ID
            divisions = data.get("divisions", {})
            for division_id, _division_data in divisions.items():
                if "cd:" in division_id:
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

                        return CongressionalDistrictResult(
                            congressional_district=f"{state_code}-{district_num}",
                            district_number=district_num,
                            state=state_code,
                            confidence=0.98,
                            method="google_civic",
                            timestamp=datetime.now(),
                            metadata={
                                "representative": rep_name,
                                "division_id": division_id,
                            },
                        )

        except Exception as e:
            logger.debug(f"Google Civic API error for {address}, {city}, {state}: {e}")

        return None

    def resolve_single_address(
        self,
        address: str | None,
        city: str | None,
        state: str | None,
        zip_code: str | None,
        google_api_key: str | None = None,
    ) -> CongressionalDistrictResult | None:
        """Resolve congressional district using best available method.

        Tries multiple methods with automatic fallback if method="auto".

        Args:
            address: Street address
            city: City name
            state: Two-letter state code
            zip_code: ZIP code
            google_api_key: Optional Google API key

        Returns:
            District resolution result or None
        """
        # Validate we have minimum required data
        if not state:
            return None

        result = None

        if self.method == "auto":
            # Try methods in order of preference
            # 1. ZIP crosswalk (fast, no API calls)
            if zip_code:
                result = self.resolve_district_from_zip(zip_code)
                if result:
                    return result

            # 2. Census API (free, accurate)
            if address and city and state and zip_code:
                result = self.resolve_district_from_census_api(address, city, state, zip_code)
                if result:
                    return result

            # 3. Google Civic (if API key provided)
            if google_api_key and address and city and state and zip_code:
                result = self.resolve_district_from_google_civic(
                    address, city, state, zip_code, google_api_key
                )
                if result:
                    return result

        elif self.method == "zip_crosswalk":
            if zip_code:
                result = self.resolve_district_from_zip(zip_code)

        elif self.method == "census_api":
            if address and city and state and zip_code:
                result = self.resolve_district_from_census_api(address, city, state, zip_code)

        elif self.method == "google_civic":
            if google_api_key and address and city and state and zip_code:
                result = self.resolve_district_from_google_civic(
                    address, city, state, zip_code, google_api_key
                )

        return result

    def enrich_awards_with_districts(
        self,
        awards_df: pd.DataFrame,
        google_api_key: str | None = None,
    ) -> pd.DataFrame:
        """Add congressional district information to awards DataFrame.

        Args:
            awards_df: DataFrame with SBIR awards (must have address fields)
            google_api_key: Optional Google API key for Civic Information API

        Returns:
            DataFrame with added congressional district columns
        """
        enriched = awards_df.copy()

        # Initialize new columns
        enriched["congressional_district"] = None
        enriched["district_number"] = None
        enriched["congressional_district_confidence"] = None
        enriched["congressional_district_method"] = None

        logger.info(f"Resolving congressional districts for {len(awards_df)} awards...")
        logger.info(f"Using method: {self.method}")

        resolved_count = 0
        method_counts: dict[str, int] = {}

        for idx, row in awards_df.iterrows():
            # Get address components
            address = row.get("company_address") or row.get("address1", "")
            city = row.get("company_city", "")
            state = row.get("company_state", "")
            zip_code = row.get("company_zip", "")

            # Resolve district
            result = self.resolve_single_address(
                address=address,
                city=city,
                state=state,
                zip_code=zip_code,
                google_api_key=google_api_key,
            )

            if result and result.congressional_district:
                enriched.at[idx, "congressional_district"] = result.congressional_district  # type: ignore[index]
                enriched.at[idx, "district_number"] = result.district_number  # type: ignore[index]
                enriched.at[idx, "congressional_district_confidence"] = result.confidence  # type: ignore[index]
                enriched.at[idx, "congressional_district_method"] = result.method  # type: ignore[index]

                resolved_count += 1
                method_counts[result.method] = method_counts.get(result.method, 0) + 1

        resolution_rate = resolved_count / len(awards_df) if len(awards_df) > 0 else 0

        logger.info(f"Resolved {resolved_count}/{len(awards_df)} districts ({resolution_rate:.1%})")
        logger.info(f"Methods used: {method_counts}")

        return enriched
