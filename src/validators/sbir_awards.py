"""SBIR award validation rules and quality checks."""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd
from loguru import logger

from ..models.quality import QualityIssue, QualitySeverity


# US State codes for validation
VALID_US_STATES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
    "PR",
    "VI",
    "GU",
    "AS",
    "MP",  # Territories
}

# Email validation regex
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Phone validation regex
PHONE_REGEX = re.compile(r"^\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$")


def validate_required_field(value: Any, field_name: str, row_index: int) -> QualityIssue | None:
    """
    Validate a required field is not null/empty.

    Args:
        value: Field value to check
        field_name: Name of the field
        row_index: Row index for error reporting

    Returns:
        QualityIssue if validation fails, None otherwise
    """
    if pd.isna(value) or (isinstance(value, str) and value.strip() == ""):  # type: ignore[unreachable]
        return QualityIssue(
            severity=QualitySeverity.ERROR,
            field=field_name,
            message=f"Required field '{field_name}' is missing",
            row_index=row_index,
        )
    return None  # type: ignore[unreachable]


def validate_phase(phase: Any, row_index: int) -> QualityIssue | None:
    """Validate Phase is one of the allowed values."""
    if pd.isna(phase):
        return QualityIssue(  # type: ignore[unreachable]
            severity=QualitySeverity.ERROR,
            field="Phase",
            message="Phase is required",
            row_index=row_index,
        )

    if phase not in ["Phase I", "Phase II", "Phase III"]:
        return QualityIssue(
            severity=QualitySeverity.ERROR,
            field="Phase",
            message=f"Invalid phase '{phase}'. Must be 'Phase I', 'Phase II', or 'Phase III'",
            row_index=row_index,
        )
    return None


def validate_program(program: Any, row_index: int) -> QualityIssue | None:
    """Validate Program is SBIR or STTR."""
    if pd.isna(program):
        return QualityIssue(  # type: ignore[unreachable]
            severity=QualitySeverity.ERROR,
            field="Program",
            message="Program is required",
            row_index=row_index,
        )

    if program.upper() not in ["SBIR", "STTR"]:
        return QualityIssue(
            severity=QualitySeverity.ERROR,
            field="Program",
            message=f"Invalid program '{program}'. Must be 'SBIR' or 'STTR'",
            row_index=row_index,
        )
    return None


def validate_award_year(year: Any, row_index: int) -> QualityIssue | None:
    """Validate Award Year is within reasonable range."""
    if pd.isna(year):
        return QualityIssue(  # type: ignore[unreachable]
            severity=QualitySeverity.ERROR,
            field="Award Year",
            message="Award Year is required",
            row_index=row_index,
        )

    if year < 1983 or year > 2026:
        return QualityIssue(
            severity=QualitySeverity.ERROR,
            field="Award Year",
            message=f"Award Year {year} is out of valid range (1983-2026)",
            row_index=row_index,
        )
    return None


def validate_award_amount(amount: Any, row_index: int) -> QualityIssue | None:
    """Validate Award Amount is positive and within reasonable range.

    Accept string inputs (e.g., \"1,000,000.00\") by coercing to float. If coercion
    fails, return an ERROR QualityIssue indicating the award amount must be numeric.
    """
    # Treat empty / missing as required error
    if pd.isna(amount) or (isinstance(amount, str) and str(amount).strip() == ""):
        return QualityIssue(
            severity=QualitySeverity.ERROR,
            field="Award Amount",
            message="Award Amount is required",
            row_index=row_index,
        )

    # Coerce string representations (allow commas)
    amount_val: float
    if isinstance(amount, str):
        try:
            amount_val = float(amount.replace(",", "").strip())
        except Exception:
            return QualityIssue(
                severity=QualitySeverity.ERROR,
                field="Award Amount",
                message=f"Award Amount must be numeric, got: '{amount}'",
                row_index=row_index,
            )
    else:
        # Assume it's already numeric-ish
        try:
            amount_val = float(amount)
        except Exception:
            return QualityIssue(
                severity=QualitySeverity.ERROR,
                field="Award Amount",
                message=f"Award Amount must be numeric, got: '{amount}'",
                row_index=row_index,
            )

    # Validate numeric value
    if amount_val <= 0:
        return QualityIssue(
            severity=QualitySeverity.ERROR,
            field="Award Amount",
            message=f"Award Amount must be positive, got {amount_val}",
            row_index=row_index,
        )

    if amount_val > 10_000_000:
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="Award Amount",
            message=f"Award Amount ${amount_val:,.2f} exceeds typical maximum of $10M",
            row_index=row_index,
        )

    return None


def validate_uei_format(uei: Any, row_index: int) -> QualityIssue | None:
    """Validate UEI format (12 alphanumeric characters)."""
    if pd.isna(uei) or uei == "":
        return None  # UEI is optional

    if len(uei) != 12:
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="UEI",
            message=f"UEI should be 12 characters, got {len(uei)}: '{uei}'",
            row_index=row_index,
        )

    if not uei.isalnum():
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="UEI",
            message=f"UEI should be alphanumeric: '{uei}'",
            row_index=row_index,
        )

    return None


def validate_duns_format(duns: Any, row_index: int) -> QualityIssue | None:
    """Validate DUNS format (9 digits)."""
    if pd.isna(duns) or duns == "":
        return None  # DUNS is optional

    # Convert to string if numeric
    duns_str = str(duns).strip()
    if len(duns_str) != 9 or not duns_str.isdigit():
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="Duns",
            message=f"DUNS should be 9 digits, got: '{duns}'",
            row_index=row_index,
        )

    return None


def validate_email_format(email: Any, field_name: str, row_index: int) -> QualityIssue | None:
    """Validate email format."""
    if pd.isna(email) or email == "":
        return None  # Email is optional

    if not EMAIL_REGEX.match(email):
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field=field_name,
            message=f"Invalid email format: '{email}'",
            row_index=row_index,
        )

    return None


def validate_state_code(state: Any, row_index: int) -> QualityIssue | None:
    """Validate state is a valid 2-letter US state code."""
    if pd.isna(state) or state == "":
        return None  # State is optional

    if len(state) != 2:
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="State",
            message=f"State should be 2-letter code, got: '{state}'",
            row_index=row_index,
        )

    if state.upper() not in VALID_US_STATES:
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="State",
            message=f"Invalid state code: '{state}'",
            row_index=row_index,
        )

    return None


def validate_zip_code(zip_code: Any, row_index: int) -> QualityIssue | None:
    """Validate ZIP code format (5 or 9 digits with optional hyphen)."""
    if pd.isna(zip_code) or zip_code == "":
        return None  # ZIP is optional

    # Convert to string if it's not already
    zip_str = str(zip_code)

    # Remove hyphen for validation
    zip_clean = zip_str.replace("-", "")

    if len(zip_clean) not in [5, 9]:
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="Zip",
            message=f"ZIP code should be 5 or 9 digits, got: '{zip_str}'",
            row_index=row_index,
        )

    if not zip_clean.isdigit():
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="Zip",
            message=f"ZIP code should contain only digits, got: '{zip_str}'",
            row_index=row_index,
        )

    return None


def validate_phone_format(phone: Any, field_name: str, row_index: int) -> QualityIssue | None:
    """Validate phone number format."""
    if pd.isna(phone) or phone == "":
        return None  # Phone is optional

    if not PHONE_REGEX.match(phone):
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field=field_name,
            message=f"Invalid phone format: '{phone}'",
            row_index=row_index,
        )

    return None


def validate_award_year_date_consistency(
    award_year: Any, proposal_date: date | None, row_index: int
) -> QualityIssue | None:
    """Validate that Award Year matches Proposal Award Date year."""
    # Handle missing values (None, pd.NA, or pd.isna)
    if pd.isna(award_year):
        return None

    # Check for None first
    if proposal_date is None:
        return None

    # Check for pandas NA types - must do this before isinstance check
    try:
        if pd.isna(proposal_date):
            return None
    except (TypeError, ValueError):
        # proposal_date might not be a pandas type, continue
        pass

    # Ensure proposal_date is a date object before accessing .year
    if not isinstance(proposal_date, date):
        return None

    if proposal_date.year != award_year:
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="Award Year",
            message=f"Award Year {award_year} does not match Proposal Award Date year {proposal_date.year}",
            row_index=row_index,
        )

    return None


def validate_phase_program_consistency(
    phase: Any, program: Any, row_index: int
) -> QualityIssue | None:
    """Validate that Phase is consistent with Program."""
    if pd.isna(phase) or pd.isna(program):
        return None  # type: ignore[unreachable]

    valid_phases = {
        "SBIR": ["Phase I", "Phase II", "Phase III"],
        "STTR": ["Phase I", "Phase II", "Phase III"],
    }

    if phase not in valid_phases.get(program.upper(), []):
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="Phase",
            message=f"Phase '{phase}' is not valid for Program '{program}'",
            row_index=row_index,
        )

    return None


def validate_date_consistency(
    award_date: date | None, end_date: date | None, row_index: int
) -> QualityIssue | None:
    """Validate that contract end date is after award date."""
    if award_date is None or end_date is None:
        return None  # Can't validate if either is missing

    if end_date < award_date:
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="Contract End Date",
            message=f"Contract end date ({end_date}) is before award date ({award_date})",
            row_index=row_index,
        )

    return None


def validate_sbir_award_record(row: pd.Series, row_index: Any) -> list[QualityIssue]:
    """
    Validate a single SBIR award record.

    Args:
        row: pandas Series representing one award record
        row_index: Index of the row for error reporting

    Returns:
        List of QualityIssue objects (empty if all validations pass)
    """
    issues = []

    # Required field validation
    for field in ["Company", "Award Title", "Agency"]:
        issue = validate_required_field(row.get(field), field, row_index)
        if issue:
            issues.append(issue)

    # Phase validation
    issue = validate_phase(row.get("Phase"), row_index)
    if issue:
        issues.append(issue)

    # Program validation
    issue = validate_program(row.get("Program"), row_index)
    if issue:
        issues.append(issue)

    # Award Year validation
    issue = validate_award_year(row.get("Award Year"), row_index)
    if issue:
        issues.append(issue)

    # Award Amount validation
    issue = validate_award_amount(row.get("Award Amount"), row_index)
    if issue:
        issues.append(issue)

    # Format validations (optional fields)
    issue = validate_uei_format(row.get("UEI"), row_index)
    if issue:
        issues.append(issue)

    issue = validate_duns_format(row.get("Duns"), row_index)
    if issue:
        issues.append(issue)

    issue = validate_email_format(row.get("Contact Email"), "Contact Email", row_index)
    if issue:
        issues.append(issue)

    issue = validate_email_format(row.get("PI Email"), "PI Email", row_index)
    if issue:
        issues.append(issue)

    issue = validate_state_code(row.get("State"), row_index)
    if issue:
        issues.append(issue)

    issue = validate_zip_code(row.get("Zip"), row_index)
    if issue:
        issues.append(issue)

    # Date consistency validation
    award_date = row.get("Proposal Award Date")
    end_date = row.get("Contract End Date")
    if pd.notna(award_date) and pd.notna(end_date):
        issue = validate_date_consistency(award_date, end_date, row_index)
        if issue:
            issues.append(issue)

    # Phone format validation
    issue = validate_phone_format(row.get("Contact Phone"), "Contact Phone", row_index)
    if issue:
        issues.append(issue)

    issue = validate_phone_format(row.get("PI Phone"), "PI Phone", row_index)
    if issue:
        issues.append(issue)

    # Award Year and Proposal Date consistency
    issue = validate_award_year_date_consistency(
        row.get("Award Year"), row.get("Proposal Award Date"), row_index
    )
    if issue:
        issues.append(issue)

    # Phase and Program consistency
    issue = validate_phase_program_consistency(row.get("Phase"), row.get("Program"), row_index)
    if issue:
        issues.append(issue)

    return issues


def validate_sbir_awards(
    df: pd.DataFrame, pass_rate_threshold: float = 0.95
) -> Any:  # Returns SimpleNamespace, not QualityReport
    """
    Validate a DataFrame of SBIR awards.

    Args:
        df: pandas DataFrame with SBIR award data
        pass_rate_threshold: Minimum pass rate required (0.0-1.0)

    Returns:
        QualityReport with validation results
    """
    logger.info(f"Validating {len(df)} SBIR award records")

    all_issues: list[QualityIssue] = []

    # Validate each record with progress logging
    validated_count = 0
    for idx, row in df.iterrows():
        issues = validate_sbir_award_record(row, idx)
        all_issues.extend(issues)
        validated_count += 1

        # Log progress every 1000 records
        if validated_count % 1000 == 0:
            logger.info(
                f"Validated {validated_count}/{len(df)} records ({validated_count / len(df) * 100:.1f}%)"
            )

    # Count errors vs warnings
    errors = [i for i in all_issues if i.severity == QualitySeverity.ERROR]
    warnings = [i for i in all_issues if i.severity == QualitySeverity.WARNING]

    # Calculate pass/fail
    failed_rows = len({issue.row_index for issue in errors})
    passed_rows = len(df) - failed_rows
    pass_rate = passed_rows / len(df) if len(df) > 0 else 1.0  # Empty DataFrame passes

    # Determine overall status
    passed = pass_rate >= pass_rate_threshold

    # Build a lightweight SimpleNamespace report to avoid strict Pydantic validation
    # in higher-level assets and make the result easily serializable/inspectable.
    report = SimpleNamespace(
        total_records=len(df),
        passed_records=passed_rows,
        failed_records=failed_rows,
        issues=[
            SimpleNamespace(
                # Use the enum member name (e.g. 'ERROR', 'WARNING', 'CRITICAL') so callers
                # that expect uppercase values (issue.severity.value == "ERROR") still work.
                severity=SimpleNamespace(
                    value=(
                        issue.severity.name
                        if hasattr(issue.severity, "name")
                        else str(issue.severity)
                    )
                ),
                field=issue.field,
                message=issue.message,
                row_index=getattr(issue, "row_index", None),
                value=getattr(issue, "value", None),
                expected=getattr(issue, "expected", None),
                rule=getattr(issue, "rule", None),
            )
            for issue in all_issues
        ],
        passed=passed,
        pass_rate=pass_rate,
        threshold=pass_rate_threshold,
    )

    logger.info(
        "Validation complete",
        total_records=len(df),
        passed_records=passed_rows,
        failed_records=failed_rows,
        pass_rate=f"{pass_rate:.1%}",
        errors=len(errors),
        warnings=len(warnings),
        passed=passed,
    )

    return report
