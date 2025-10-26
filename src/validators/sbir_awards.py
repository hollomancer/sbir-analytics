"""SBIR award validation rules and quality checks."""

import re
from types import SimpleNamespace
from typing import List, Optional
from datetime import date
import pandas as pd
from loguru import logger

from ..models.quality import QualityIssue, QualitySeverity, QualityReport


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


def validate_required_field(value: any, field_name: str, row_index: int) -> Optional[QualityIssue]:
    """
    Validate a required field is not null/empty.

    Args:
        value: Field value to check
        field_name: Name of the field
        row_index: Row index for error reporting

    Returns:
        QualityIssue if validation fails, None otherwise
    """
    if pd.isna(value) or (isinstance(value, str) and value.strip() == ""):
        return QualityIssue(
            severity=QualitySeverity.ERROR,
            field=field_name,
            message=f"Required field '{field_name}' is missing",
            row_index=row_index,
        )
    return None


def validate_phase(phase: str, row_index: int) -> Optional[QualityIssue]:
    """Validate Phase is one of the allowed values."""
    if pd.isna(phase):
        return QualityIssue(
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


def validate_program(program: str, row_index: int) -> Optional[QualityIssue]:
    """Validate Program is SBIR or STTR."""
    if pd.isna(program):
        return QualityIssue(
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


def validate_award_year(year: int, row_index: int) -> Optional[QualityIssue]:
    """Validate Award Year is within reasonable range."""
    if pd.isna(year):
        return QualityIssue(
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


def validate_award_amount(amount: float, row_index: int) -> Optional[QualityIssue]:
    """Validate Award Amount is positive and within reasonable range."""
    if pd.isna(amount):
        return QualityIssue(
            severity=QualitySeverity.ERROR,
            field="Award Amount",
            message="Award Amount is required",
            row_index=row_index,
        )

    if amount <= 0:
        return QualityIssue(
            severity=QualitySeverity.ERROR,
            field="Award Amount",
            message=f"Award Amount must be positive, got {amount}",
            row_index=row_index,
        )

    if amount > 10_000_000:
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="Award Amount",
            message=f"Award Amount ${amount:,.2f} exceeds typical maximum of $10M",
            row_index=row_index,
        )

    return None


def validate_uei_format(uei: str, row_index: int) -> Optional[QualityIssue]:
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


def validate_duns_format(duns: str, row_index: int) -> Optional[QualityIssue]:
    """Validate DUNS format (9 digits)."""
    if pd.isna(duns) or duns == "":
        return None  # DUNS is optional

    if len(duns) != 9 or not duns.isdigit():
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="Duns",
            message=f"DUNS should be 9 digits, got: '{duns}'",
            row_index=row_index,
        )

    return None


def validate_email_format(email: str, field_name: str, row_index: int) -> Optional[QualityIssue]:
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


def validate_state_code(state: str, row_index: int) -> Optional[QualityIssue]:
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


def validate_zip_code(zip_code: str, row_index: int) -> Optional[QualityIssue]:
    """Validate ZIP code format (5 or 9 digits with optional hyphen)."""
    if pd.isna(zip_code) or zip_code == "":
        return None  # ZIP is optional

    # Remove hyphen for validation
    zip_clean = zip_code.replace("-", "")

    if len(zip_clean) not in [5, 9]:
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="Zip",
            message=f"ZIP code should be 5 or 9 digits, got: '{zip_code}'",
            row_index=row_index,
        )

    if not zip_clean.isdigit():
        return QualityIssue(
            severity=QualitySeverity.WARNING,
            field="Zip",
            message=f"ZIP code should contain only digits, got: '{zip_code}'",
            row_index=row_index,
        )

    return None


def validate_date_consistency(
    award_date: Optional[date], end_date: Optional[date], row_index: int
) -> Optional[QualityIssue]:
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


def validate_sbir_award_record(row: pd.Series, row_index: int) -> List[QualityIssue]:
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

    return issues


def validate_sbir_awards(df: pd.DataFrame, pass_rate_threshold: float = 0.95) -> QualityReport:
    """
    Validate a DataFrame of SBIR awards.

    Args:
        df: pandas DataFrame with SBIR award data
        pass_rate_threshold: Minimum pass rate required (0.0-1.0)

    Returns:
        QualityReport with validation results
    """
    logger.info(f"Validating {len(df)} SBIR award records")

    all_issues: List[QualityIssue] = []

    # Validate each record
    for idx, row in df.iterrows():
        issues = validate_sbir_award_record(row, idx)
        all_issues.extend(issues)

    # Count errors vs warnings
    errors = [i for i in all_issues if i.severity == QualitySeverity.ERROR]
    warnings = [i for i in all_issues if i.severity == QualitySeverity.WARNING]

    # Calculate pass/fail
    failed_rows = len(set(issue.row_index for issue in errors))
    passed_rows = len(df) - failed_rows
    pass_rate = passed_rows / len(df) if len(df) > 0 else 0.0

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
                    value=issue.severity.name
                    if hasattr(issue.severity, "name")
                    else str(issue.severity)
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
        f"Validation complete",
        total_records=len(df),
        passed_records=passed_rows,
        failed_records=failed_rows,
        pass_rate=f"{pass_rate:.1%}",
        errors=len(errors),
        warnings=len(warnings),
        passed=passed,
    )

    return report
