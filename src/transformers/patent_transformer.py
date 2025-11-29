# sbir-analytics/src/transformers/patent_transformer.py
"""
PatentAssignmentTransformer

Transform raw USPTO rows (as yielded by USPTOExtractor) into normalized
PatentAssignment models ready for downstream validation and loading.

Responsibilities
- Normalize fields (identifiers, dates, names)
- Join assignment + conveyance + assignee + assignor + documentid semantics if provided on the raw row
- Heuristically parse conveyance text for conveyance type and employer-assign flags
- Link patents to SBIR companies via exact or fuzzy grant number matching (optional index provided)
- Provide batch and streaming helpers

Usage
-----
from src.transformers.patent_transformer import PatentAssignmentTransformer
transformer = PatentAssignmentTransformer(...
for assignment in transformer.transform_chunk(rows):
    # assignment is a PatentAssignment model (or dict with _error)
    ...
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from typing import Any

from loguru import logger


# Try to use rapidfuzz for fuzzy matching; fallback to difflib
try:
    from rapidfuzz import fuzz

    _RAPIDFUZZ_AVAILABLE = True
except Exception:
    _RAPIDFUZZ_AVAILABLE = False

# Import Pydantic models from uspto_models
try:
    from src.models.uspto_models import (
        ConveyanceType,
        PatentAssignee,
        PatentAssignment,
        PatentAssignor,
        PatentConveyance,
        PatentDocument,
    )
except Exception:
    # If models are not importable, define simple placeholders to avoid hard failure.
    PatentAssignment = None  # type: ignore
    PatentDocument = None  # type: ignore
    PatentAssignee = None  # type: ignore
    PatentAssignor = None  # type: ignore
    PatentConveyance = None  # type: ignore
    ConveyanceType = None  # type: ignore

# Keywords heuristics for conveyance type detection
_CONVEYANCE_KEYWORDS = {
    "assignment": ["assign", "assignment", "convey", "transferr", "transfer", "deed"],
    "license": ["license", "licence", "licensing", "licensed"],
    "security_interest": ["security interest", "security-interest", "security"],
    "merger": ["merger", "acquir", "acquisition", "merge", "purchase"],
}


@dataclass
class PatentTransformOptions:
    fuzzy_grant_threshold: float = 0.9
    fuzzy_secondary_threshold: float = 0.8
    normalize_names: bool = True
    normalize_identifiers: bool = True


class PatentAssignmentTransformer:
    """
    Transformer for patent assignment records.

    Constructor:
        PatentAssignmentTransformer(sbire_company_grant_index=None, options=None)

    Parameters:
    - sbir_company_grant_index: Optional mapping from normalized grant_doc_num -> company_id
      to help link transformed patent assignments to SBIR awardee companies. If not provided,
      linking is disabled unless a grant_doc_num appears exact in the mapping.
    - options: PatentTransformOptions instance for thresholds and normalization toggles.
    """

    def __init__(
        self,
        sbir_company_grant_index: dict[str, str] | None = None,
        options: PatentTransformOptions | None = None,
    ) -> None:
        self.sbir_index = sbir_company_grant_index or {}
        self.options = options or PatentTransformOptions()
        logger.debug(
            "PatentAssignmentTransformer initialized: sbir_index_keys=%d, options=%s",
            len(self.sbir_index),
            self.options,
        )

    # ------------------------
    # Normalization helpers
    # ------------------------
    @staticmethod
    def _normalize_identifier(val: Any | None) -> str | None:
        if val is None:
            return None
        s = str(val).strip()
        if not s:
            return None
        # remove non-alphanumeric (retain dashes/underscores)
        s = re.sub(r"[^\w\-]", "", s)
        return s.upper()

    @staticmethod
    def _normalize_name(name: Any | None) -> str | None:
        if name is None:
            return None
        s = " ".join(str(name).strip().split())
        s = s.replace(",", " ").replace(".", " ").replace("/", " ").replace("&", " AND ")
        # Collapse multiple spaces to single space
        s = " ".join(s.split())
        return s.strip()

    @staticmethod
    def _parse_address(
        text: Any | None,
    ) -> tuple[str | None, str | None, str | None, str | None, str | None]:
        """
        Heuristic address parser for assignee/assignor free-text address fields.

        Returns a tuple: (street, city, state, postal_code, country).
        This is intentionally lightweight: uses simple splits and patterns to extract common US-style addresses.
        For robust parsing consider integrating libpostal or a dedicated address parsing library.
        """
        if text is None:
            return None, None, None, None, None
        s = str(text).strip()
        if not s:
            return None, None, None, None, None

        # Attempt quick heuristics:
        # - Split on commas and assign segments: street, city, state + zip, country
        parts = [p.strip() for p in s.split(",") if p.strip()]
        street = city = state = postal = country = None

        if len(parts) == 1:
            # Single-line address; try to extract ZIP-like token (5 digits) and state (2 letters)
            tokens = parts[0].split()
            # Look for 5-digit zip
            zip_token = next(
                (t for t in reversed(tokens) if re.fullmatch(r"\d{5}(-\d{4})?", t)), None
            )
            if zip_token:
                postal = zip_token
                # remove zip token from tokens
                tokens = [t for t in tokens if t != zip_token]
            # try last token as state abbreviation (2 letters)
            if tokens:
                last = tokens[-1]
                if re.fullmatch(r"[A-Za-z]{2}", last):
                    state = last.upper()
                    tokens = tokens[:-1]
            street = " ".join(tokens) if tokens else parts[0]
        else:
            # Common case: "123 Main St, Springfield, IL 62704, USA"
            street = parts[0] if len(parts) >= 1 else None
            if len(parts) >= 2:
                city = parts[1]
            if len(parts) >= 3:
                third = parts[2]
                # third often contains state + postal
                m = re.search(r"([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)", third)
                if m:
                    state = m.group(1).upper()
                    postal = m.group(2)
                else:
                    # try to split numeric zip from trailing token
                    tok = third.split()
                    if tok and re.fullmatch(r"\d{5}(-\d{4})?", tok[-1]):
                        postal = tok[-1]
                        if len(tok) >= 2 and re.fullmatch(r"[A-Za-z]{2}", tok[-2]):
                            state = tok[-2].upper()
            if len(parts) >= 4:
                country = parts[3]

        # Normalize empty strings to None
        def _clean(x):
            if x is None:
                return None
            xx = str(x).strip()
            return xx if xx else None

        return _clean(street), _clean(city), _clean(state), _clean(postal), _clean(country)

    @staticmethod
    def _parse_date(value: Any | None) -> date | None:
        """Parse date using centralized utility."""
        from src.utils.common.date_utils import parse_date

        return parse_date(value, strict=False)

    # ------------------------
    # Conveyance parsing
    # ------------------------
    def _infer_conveyance_type(self, text: str | None) -> tuple[ConveyanceType | None, bool | None]:
        """
        Heuristically infer the conveyance type and whether it's an employer-assignment.
        Returns (ConveyanceType, employer_assign_flag)
        """
        if text is None:
            return ConveyanceType.ASSIGNMENT if ConveyanceType is not None else None, None
        txt = str(text).lower()
        # employer assignment heuristics: phrases like "by employee", "work for hire", "assigned to employer"
        employer_keywords = [
            "work for hire",
            "employee",
            "employer",
            "by employee",
            "assigned to employer",
        ]
        employer_flag = any(k in txt for k in employer_keywords)

        # type detection: check for each group of keywords
        for tname, keywords in _CONVEYANCE_KEYWORDS.items():
            for kw in keywords:
                if kw in txt:
                    try:
                        return ConveyanceType(
                            tname if isinstance(tname, str) else tname
                        ), employer_flag
                    except Exception:
                        # ConveyanceType may be enum of different names; fall back to generic
                        return (
                            ConveyanceType.ASSIGNMENT if ConveyanceType is not None else None,
                            employer_flag,
                        )

        # fallback: assignment default
        return ConveyanceType.ASSIGNMENT if ConveyanceType is not None else None, employer_flag

    # ------------------------
    # Fuzzy matching helpers
    # ------------------------
    def _fuzzy_similarity(self, s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0.0
        if _RAPIDFUZZ_AVAILABLE:
            try:
                return float(fuzz.token_sort_ratio(s1, s2) / 100.0)
            except Exception:
                pass
        try:
            return float(SequenceMatcher(None, s1, s2).ratio())
        except Exception:
            return 0.0

    def _match_grant_to_sbir(self, grant: str | None) -> tuple[str, float] | None:
        """
        Try to match a normalized grant_doc_num to the SBIR company index.
        Returns (company_id, score) or None.
        """
        if grant is None:
            return None
        ngrant = self._normalize_identifier(grant)
        if not ngrant:
            return None

        # Exact match first
        if ngrant in self.sbir_index:
            return self.sbir_index[ngrant], 1.0

        # Fuzzy fallback across keys (if index not too large)
        # Avoid fuzz across extremely large index (caller should build efficient index).
        best_score = 0.0
        best_company = None
        # Iterate through keys (may be expensive); future: build inverted index or trie
        for key, company_id in self.sbir_index.items():
            score = self._fuzzy_similarity(ngrant, key)
            if score > best_score:
                best_score = score
                best_company = company_id

        if best_score >= self.options.fuzzy_grant_threshold:
            if best_company is not None:
                return best_company, best_score
        if best_score >= self.options.fuzzy_secondary_threshold:
            if best_company is not None:
                return best_company, best_score
        return None

    # ------------------------
    # Row -> Model mapping
    # ------------------------
    def transform_row(self, row: dict[str, Any]) -> PatentAssignment | dict[str, Any]:
        """
        Transform a single raw row dict into a PatentAssignment Pydantic model.
        On validation or mapping error, returns a dict with `_error` key describing the issue.
        """

        # Normalize common keys (in case upstream extractor left many variants)
        # We accept the extractor already normalized, but be defensive.
        def _get(*keys, default=None):
            for k in keys:
                if k in row and row[k] is not None:
                    return row[k]
            return default

        try:
            # Build subcomponents
            doc = PatentDocument(
                rf_id=_get("document_rf_id", "rf_id"),
                application_number=self._normalize_identifier(
                    _get("application_number", "app_num")
                ),
                publication_number=self._normalize_identifier(
                    _get("publication_number", "pub_num")
                ),
                grant_number=self._normalize_identifier(
                    _get("grant_doc_num", "grant_number", "patent_number")
                ),
                filing_date=self._parse_date(_get("filing_date")),
                publication_date=self._parse_date(_get("publication_date")),
                grant_date=self._parse_date(_get("grant_date")),
                title=_get("title"),
                abstract=_get("abstract"),
                language=_get("language"),
                raw=row,
            )
        except Exception as e:
            logger.debug("Document construction failed: %s", e)
            # proceed but keep raw doc dict
            doc = {"_error": f"document_build_failed: {e}"}  # type: ignore[assignment, no-redef]

        try:
            # Try to parse a combined address if explicit street/city/state not provided
            street = _get("assignee_street")
            city = _get("assignee_city")
            state = _get("assignee_state")
            postal = _get("assignee_postal")
            country = _get("assignee_country")
            # If any of the main address pieces are missing, attempt to parse from `assignee_address` or `assignee_full_address`
            if not any([street, city, state, postal, country]):
                addr_text = (
                    _get("assignee_address")
                    or _get("assignee_full_address")
                    or _get("assignee_addr")
                )
                if addr_text:
                    parsed = self._parse_address(addr_text)
                    if parsed:
                        street, city, state, postal, country = parsed
                        # Task 7.4: Standardize address components
                        standardized = self._standardize_address(
                            street, city, state, postal, country
                        )
                        street = standardized.get("street")
                        city = standardized.get("city")
                        state = standardized.get("state")
                        postal = standardized.get("postal_code")
                        country = standardized.get("country")

            assignee = PatentAssignee(
                rf_id=_get("assignee_rf_id"),
                name=self._normalize_name(_get("assignee_name")),
                street=street,
                city=city,
                state=state,
                postal_code=postal,
                country=country,
                uei=self._normalize_identifier(_get("assignee_uei")),
                cage=self._normalize_identifier(_get("assignee_cage")),
                duns=self._normalize_identifier(_get("assignee_duns")),
                metadata={},
            )
        except Exception as e:
            logger.debug("Assignee construction failed: %s", e)
            assignee = {"_error": f"assignee_build_failed: {e}"}  # type: ignore[assignment, no-redef]

        try:
            assignor = PatentAssignor(
                rf_id=_get("assignor_rf_id"),
                name=self._normalize_name(_get("assignor_name")),
                execution_date=self._parse_date(_get("execution_date")),
                acknowledgment_date=self._parse_date(_get("acknowledgment_date")),
                metadata={},
            )
        except Exception as e:
            logger.debug("Assignor construction failed: %s", e)
            assignor = {"_error": f"assignor_build_failed: {e}"}  # type: ignore[assignment, no-redef]

        # Conveyance inference
        conv_text = _get("conveyance_text", "conveyance")
        conveyance_type, employer_flag = self._infer_conveyance_type(conv_text)
        try:
            conveyance = PatentConveyance(
                rf_id=_get("conveyance_rf_id"),
                conveyance_type=conveyance_type
                or (ConveyanceType.ASSIGNMENT if ConveyanceType is not None else None),
                description=conv_text,
                employer_assign=employer_flag,
                recorded_date=self._parse_date(_get("recorded_date")),
                metadata={},
            )
        except Exception as e:
            logger.debug("Conveyance build failed: %s", e)
            conveyance = {"_error": f"conveyance_build_failed: {e}"}  # type: ignore[assignment, no-redef]

        # Build main assignment
        try:
            pa = PatentAssignment(
                rf_id=_get("rf_id", "record_id"),
                file_id=_get("file_id"),
                document=doc if isinstance(doc, PatentDocument) else None,
                conveyance=conveyance if isinstance(conveyance, PatentConveyance) else None,
                assignee=assignee if isinstance(assignee, PatentAssignee) else None,
                assignor=assignor if isinstance(assignor, PatentAssignor) else None,
                execution_date=self._parse_date(_get("execution_date")),
                recorded_date=self._parse_date(_get("recorded_date")),
                normalized_assignee_name=self._normalize_name(_get("assignee_name")),
                normalized_assignor_name=self._normalize_name(_get("assignor_name")),
                metadata={"_raw": row},
            )
        except Exception as e:
            logger.exception("PatentAssignment model build failed: %s", e)
            row_with_err = dict(row)
            row_with_err["_error"] = f"model_build_failed: {e}"
            return row_with_err

        # Optional: link to SBIR company via grant_doc_num heuristic
        grantnum = None
        if isinstance(pa.document, PatentDocument):
            grantnum = pa.document.grant_number or pa.document.publication_number
        match = self._match_grant_to_sbir(grantnum) if grantnum else None
        if match:
            company_id, score = match
            # attach linking metadata
            pa.metadata["linked_sbir_company"] = {"company_id": company_id, "match_score": score}

        # Task 7.8: Calculate assignment chain metadata
        self._calculate_chain_metadata(pa, row)

        return pa

    # Task 7.8: Assignment chain metadata calculation
    # -----------------------------------------------
    def _calculate_chain_metadata(self, assignment: PatentAssignment, row: dict[str, Any]) -> None:
        """
        Calculate and attach assignment chain metadata to track timeline and transitions.

        This method adds the following metadata:
        - chain_sequence_indicator: ordinal position if part of multi-part assignment
        - temporal_span_days: days between execution and recording
        - transition_type: nature of assignment (new_assignee, consolidation, etc.)
        - chain_flags: special indicators (urgent, disputed, etc.)

        Args:
            assignment: PatentAssignment model to annotate
            row: Raw input row with potential chain indicators
        """
        if not assignment.metadata:
            assignment.metadata = {}

        # Extract dates for temporal analysis
        exec_date = assignment.execution_date
        rec_date = assignment.recorded_date

        # Calculate temporal span
        temporal_span_days = None
        if exec_date and rec_date:
            temporal_span_days = (rec_date - exec_date).days
            assignment.metadata["temporal_span_days"] = temporal_span_days

            # Flag unusual delays (>90 days between execution and recording)
            if temporal_span_days > 90:
                chain_flags = assignment.metadata.get("chain_flags")
                if not isinstance(chain_flags, list):
                    chain_flags = []
                    assignment.metadata["chain_flags"] = chain_flags
                chain_flags.append("delayed_recording")

        # Detect sequence indicators (e.g., "Part 1 of 3")
        raw_conveyance = row.get("conveyance_description", "")
        if isinstance(raw_conveyance, str):
            # Look for part indicators like "Part 1 of 3" or "A of B"
            part_match = re.search(
                r"(?:part|section)\s+(\d+)\s+of\s+(\d+)", raw_conveyance, re.IGNORECASE
            )
            if part_match:
                current_part = int(part_match.group(1))
                total_parts = int(part_match.group(2))
                assignment.metadata["chain_sequence_indicator"] = {
                    "current_part": current_part,
                    "total_parts": total_parts,
                }

        # Detect transition type based on assignee change
        if (
            PatentAssignee is not None
            and PatentAssignor is not None
            and isinstance(assignment.assignee, PatentAssignee)
            and isinstance(assignment.assignor, PatentAssignor)
        ):
            assignee_name = assignment.normalized_assignee_name or assignment.assignee.name or ""
            assignor_name = assignment.normalized_assignor_name or assignment.assignor.name or ""

            if assignee_name.lower() == assignor_name.lower():
                assignment.metadata["transition_type"] = "consolidation"
            elif "merge" in (
                assignment.conveyance.conveyance_type.value if assignment.conveyance else ""
            ):
                assignment.metadata["transition_type"] = "merger_acquisition"
            elif "license" in (
                assignment.conveyance.conveyance_type.value if assignment.conveyance else ""
            ):
                assignment.metadata["transition_type"] = "license_grant"
            elif assignment.conveyance and assignment.conveyance.employer_assign:
                assignment.metadata["transition_type"] = "employer_assignment"
            else:
                assignment.metadata["transition_type"] = "standard_assignment"

        # Mark employment-related assignments for special handling
        if assignment.conveyance and assignment.conveyance.employer_assign:
            if "chain_flags" not in assignment.metadata:
                chain_flags = []
                assignment.metadata["chain_flags"] = chain_flags
            else:
                chain_flags = assignment.metadata.get("chain_flags")
                if not isinstance(chain_flags, list):
                    chain_flags = []
                    assignment.metadata["chain_flags"] = chain_flags
            if "employer_assigned" not in chain_flags:
                chain_flags.append("employer_assigned")

    # Task 7.4: Enhanced address standardization (building on _parse_address)
    # -----------------------------------------------------------------------
    @staticmethod
    def _standardize_state_code(state: str | None) -> str | None:
        """
        Standardize state abbreviations and full names to 2-letter codes.

        Args:
            state: State name, abbreviation, or code

        Returns:
            2-letter state code (uppercase) or None if not recognized
        """
        if not state:
            return None

        state_str = str(state).strip().upper()

        # US state mapping
        state_map = {
            "ALABAMA": "AL",
            "ALASKA": "AK",
            "ARIZONA": "AZ",
            "ARKANSAS": "AR",
            "CALIFORNIA": "CA",
            "COLORADO": "CO",
            "CONNECTICUT": "CT",
            "DELAWARE": "DE",
            "FLORIDA": "FL",
            "GEORGIA": "GA",
            "HAWAII": "HI",
            "IDAHO": "ID",
            "ILLINOIS": "IL",
            "INDIANA": "IN",
            "IOWA": "IA",
            "KANSAS": "KS",
            "KENTUCKY": "KY",
            "LOUISIANA": "LA",
            "MAINE": "ME",
            "MARYLAND": "MD",
            "MASSACHUSETTS": "MA",
            "MICHIGAN": "MI",
            "MINNESOTA": "MN",
            "MISSISSIPPI": "MS",
            "MISSOURI": "MO",
            "MONTANA": "MT",
            "NEBRASKA": "NE",
            "NEVADA": "NV",
            "NEW HAMPSHIRE": "NH",
            "NEW JERSEY": "NJ",
            "NEW MEXICO": "NM",
            "NEW YORK": "NY",
            "NORTH CAROLINA": "NC",
            "NORTH DAKOTA": "ND",
            "OHIO": "OH",
            "OKLAHOMA": "OK",
            "OREGON": "OR",
            "PENNSYLVANIA": "PA",
            "RHODE ISLAND": "RI",
            "SOUTH CAROLINA": "SC",
            "SOUTH DAKOTA": "SD",
            "TENNESSEE": "TN",
            "TEXAS": "TX",
            "UTAH": "UT",
            "VERMONT": "VT",
            "VIRGINIA": "VA",
            "WASHINGTON": "WA",
            "WEST VIRGINIA": "WV",
            "WISCONSIN": "WI",
            "WYOMING": "WY",
            "DISTRICT OF COLUMBIA": "DC",
        }

        # Check if already a 2-letter code
        if len(state_str) == 2 and state_str.isalpha():
            return state_str

        # Try to map full name to abbreviation
        if state_str in state_map:
            return state_map[state_str]

        # Try partial matches
        for full_name, abbrev in state_map.items():
            if full_name.startswith(state_str):
                return abbrev

        return None

    @staticmethod
    def _standardize_country_code(country: str | None) -> str | None:
        """
        Standardize country names to ISO 3166-1 alpha-2 codes.

        Args:
            country: Country name or code

        Returns:
            2-letter ISO country code (uppercase) or None if not recognized
        """
        if not country:
            return None

        country_str = str(country).strip().upper()

        # Common country mappings (US-centric, since most USPTO data is US)
        country_map = {
            "UNITED STATES": "US",
            "USA": "US",
            "US": "US",
            "UNITED STATES OF AMERICA": "US",
            "CANADA": "CA",
            "MEXICO": "MX",
            "UNITED KINGDOM": "GB",
            "UK": "GB",
            "GERMANY": "DE",
            "FRANCE": "FR",
            "JAPAN": "JP",
            "CHINA": "CN",
            "INDIA": "IN",
            "AUSTRALIA": "AU",
            "SOUTH KOREA": "KR",
            "BRAZIL": "BR",
            "ISRAEL": "IL",
            "SWITZERLAND": "CH",
            "NETHERLANDS": "NL",
            "SWEDEN": "SE",
            "SINGAPORE": "SG",
            "HONG KONG": "HK",
            "TAIWAN": "TW",
            "IRELAND": "IE",
        }

        # Check if already a 2-letter code
        if len(country_str) == 2 and country_str.isalpha():
            return country_str

        # Try to map full name to code
        if country_str in country_map:
            return country_map[country_str]

        return None

    @staticmethod
    def _standardize_address(
        street: str | None,
        city: str | None,
        state: str | None,
        postal_code: str | None,
        country: str | None,
    ) -> dict[str, str | None]:
        """
        Standardize and normalize address components for consistency.

        Task 7.4 implementation: Provides address standardization with:
        - State code normalization (full names → 2-letter codes)
        - Country code standardization (ISO 3166-1 alpha-2)
        - Postal code formatting (cleanup of whitespace)
        - City/street normalization (trim, capitalize properly)

        Args:
            street: Street address
            city: City name
            state: State name or code
            postal_code: ZIP/postal code
            country: Country name or code

        Returns:
            Dictionary with standardized address components
        """
        result: dict[str, str | None] = {}

        # Standardize street
        if street:
            result["street"] = " ".join(str(street).strip().split())
        else:
            result["street"] = None

        # Standardize city
        if city:
            result["city"] = " ".join(str(city).strip().split())
        else:
            result["city"] = None

        # Standardize state to 2-letter code
        if state:
            result["state"] = PatentAssignmentTransformer._standardize_state_code(state)
        else:
            result["state"] = None

        # Standardize postal code
        if postal_code:
            # Remove internal spaces but preserve hyphens (for ZIP+4)
            pc_str = str(postal_code).strip()
            pc_str = re.sub(r"\s+", "", pc_str)
            result["postal_code"] = pc_str if pc_str else None
        else:
            result["postal_code"] = None

        # Standardize country to ISO code
        if country:
            result["country"] = PatentAssignmentTransformer._standardize_country_code(country)
        else:
            result["country"] = None

        return result

    # ------------------------
    # Batch helpers
    # ------------------------
    def transform_chunk(
        self, rows: Iterable[dict[str, Any]]
    ) -> Iterator[PatentAssignment | dict[str, Any]]:
        """
        Transform an iterable of raw rows into PatentAssignment models in a streaming fashion.
        """
        for row in rows:
            yield self.transform_row(row)
