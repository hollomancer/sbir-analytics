"""Custom assertion helpers for test suite.

This module provides domain-specific assertion functions to reduce boilerplate
and improve test readability. These helpers encapsulate common assertion patterns
used throughout the test suite.
"""

from datetime import date
from typing import Any

from src.models.award import Award


def assert_valid_extraction_metadata(
    metadata: dict,
    expected_row_count: int | None = None,
    expected_column_count: int | None = None,
) -> None:
    """Assert that extraction metadata has required structure and valid values.

    Args:
        metadata: Metadata dictionary from extractor
        expected_row_count: Expected row count (optional)
        expected_column_count: Expected column count (optional)

    Raises:
        AssertionError: If metadata structure is invalid
    """
    assert isinstance(metadata, dict), "Metadata should be a dict"

    required_keys = [
        "columns",
        "column_count",
        "extraction_start_utc",
        "extraction_end_utc",
        "row_count",
    ]
    for key in required_keys:
        assert key in metadata, f"Missing metadata key: {key}"

    # Validate types
    assert isinstance(metadata["columns"], list), "Columns should be a list"
    assert isinstance(metadata["column_count"], int), "Column count should be int"
    assert isinstance(metadata["row_count"], int | str), "Row count should be int/str"

    # Validate consistency
    assert len(metadata["columns"]) == metadata["column_count"], (
        f"Column count mismatch: expected {metadata['column_count']}, "
        f"got {len(metadata['columns'])}"
    )

    # Validate all columns are strings
    assert all(isinstance(c, str) for c in metadata["columns"]), "All columns should be strings"

    # Validate timestamps are non-empty
    assert (
        isinstance(metadata["extraction_start_utc"], str)
        and len(metadata["extraction_start_utc"]) > 0
    ), "extraction_start_utc should be non-empty string"

    assert (
        isinstance(metadata["extraction_end_utc"], str) and len(metadata["extraction_end_utc"]) > 0
    ), "extraction_end_utc should be non-empty string"

    # Optional validations
    if expected_row_count is not None:
        actual_count = int(metadata["row_count"])
        assert actual_count == expected_row_count, (
            f"Row count mismatch: expected {expected_row_count}, got {actual_count}"
        )

    if expected_column_count is not None:
        assert metadata["column_count"] == expected_column_count, (
            f"Column count mismatch: expected {expected_column_count}, "
            f"got {metadata['column_count']}"
        )


def assert_valid_award(
    award: Award,
    require_uei: bool = False,
    require_duns: bool = False,
    min_amount: float | None = None,
) -> None:
    """Assert that an Award instance has valid required fields.

    Args:
        award: Award instance to validate
        require_uei: If True, assert UEI is not None
        require_duns: If True, assert DUNS is not None
        min_amount: Minimum expected award amount

    Raises:
        AssertionError: If award is invalid
    """
    # Required fields
    assert isinstance(award.award_id, str) and len(award.award_id) > 0, (
        "award_id must be non-empty string"
    )
    assert isinstance(award.company_name, str) and len(award.company_name) > 0, (
        "company_name must be non-empty string"
    )
    assert isinstance(award.award_amount, float), "award_amount must be float"
    assert award.award_amount > 0, f"award_amount must be positive, got {award.award_amount}"
    assert isinstance(award.award_date, date), "award_date must be date object"
    assert award.program in ["SBIR", "STTR", None], (
        f"program must be SBIR or STTR, got {award.program}"
    )

    # Optional validations
    if require_uei:
        assert award.company_uei is not None, "company_uei is required"
        assert len(award.company_uei) == 12, (
            f"UEI should be 12 characters, got {len(award.company_uei)}"
        )

    if require_duns:
        assert award.company_duns is not None, "company_duns is required"
        assert len(award.company_duns) == 9, (
            f"DUNS should be 9 digits, got {len(award.company_duns)}"
        )

    if min_amount is not None:
        assert award.award_amount >= min_amount, (
            f"award_amount {award.award_amount} is less than minimum {min_amount}"
        )


def assert_award_fields_equal(
    award: Award,
    expected: dict[str, Any],
    fields: list[str] | None = None,
) -> None:
    """Assert that specific Award fields match expected values.

    Args:
        award: Award instance to check
        expected: Dictionary of expected field values
        fields: List of field names to check (defaults to all keys in expected)

    Raises:
        AssertionError: If any field doesn't match
    """
    if fields is None:
        fields = list(expected.keys())

    for field in fields:
        if field not in expected:
            continue

        actual = getattr(award, field, None)
        expected_val = expected[field]

        assert actual == expected_val, (
            f"Field '{field}' mismatch: expected {expected_val!r}, got {actual!r}"
        )


def assert_valid_neo4j_load_metrics(metrics: Any, min_nodes: int = 0) -> None:
    """Assert Neo4j LoadMetrics has valid structure.

    Args:
        metrics: LoadMetrics instance
        min_nodes: Minimum expected nodes created/updated

    Raises:
        AssertionError: If metrics are invalid
    """
    # Check required attributes exist
    assert hasattr(metrics, "nodes_created"), "Missing nodes_created attribute"
    assert hasattr(metrics, "nodes_updated"), "Missing nodes_updated attribute"
    assert hasattr(metrics, "relationships_created"), "Missing relationships_created"
    assert hasattr(metrics, "errors"), "Missing errors attribute"

    # Validate types
    assert isinstance(metrics.nodes_created, dict), "nodes_created should be dict"
    assert isinstance(metrics.nodes_updated, dict), "nodes_updated should be dict"
    assert isinstance(metrics.relationships_created, dict), "relationships_created should be dict"
    assert isinstance(metrics.errors, int), "errors should be int"

    # Validate counts are non-negative
    assert metrics.errors >= 0, f"errors should be non-negative, got {metrics.errors}"

    for label, count in metrics.nodes_created.items():
        assert count >= 0, f"nodes_created[{label}] should be non-negative, got {count}"

    for label, count in metrics.nodes_updated.items():
        assert count >= 0, f"nodes_updated[{label}] should be non-negative, got {count}"

    # Optional validation
    if min_nodes > 0:
        total_nodes = sum(metrics.nodes_created.values()) + sum(metrics.nodes_updated.values())
        assert total_nodes >= min_nodes, (
            f"Total nodes {total_nodes} is less than minimum {min_nodes}"
        )


def assert_valid_cet_classification(
    classification: Any,
    min_score: float | None = None,
    max_evidence: int = 3,
) -> None:
    """Assert CET classification has valid structure.

    Args:
        classification: CETClassification instance
        min_score: Minimum expected score
        max_evidence: Maximum evidence statements allowed

    Raises:
        AssertionError: If classification is invalid
    """
    from src.models.cet_models import ClassificationLevel

    # Required fields
    assert hasattr(classification, "cet_id"), "Missing cet_id"
    assert hasattr(classification, "score"), "Missing score"
    assert hasattr(classification, "classification"), "Missing classification"

    # Validate score range
    assert 0 <= classification.score <= 100, f"Score must be 0-100, got {classification.score}"

    # Validate classification level matches score
    score = classification.score
    level = classification.classification

    if score >= 70:
        assert level == ClassificationLevel.HIGH, f"Score {score} should be HIGH, got {level}"
    elif score >= 40:
        assert level == ClassificationLevel.MEDIUM, f"Score {score} should be MEDIUM, got {level}"
    else:
        assert level == ClassificationLevel.LOW, f"Score {score} should be LOW, got {level}"

    # Validate evidence
    if hasattr(classification, "evidence"):
        assert len(classification.evidence) <= max_evidence, (
            f"Too many evidence statements: {len(classification.evidence)} > {max_evidence}"
        )

    # Optional validation
    if min_score is not None:
        assert classification.score >= min_score, (
            f"Score {classification.score} is less than minimum {min_score}"
        )


def assert_dict_subset(actual: dict, expected_subset: dict) -> None:
    """Assert that actual dict contains all key-value pairs from expected subset.

    Args:
        actual: Dictionary to check
        expected_subset: Dictionary with expected key-value pairs

    Raises:
        AssertionError: If any expected key-value pair is missing or different
    """
    for key, expected_val in expected_subset.items():
        assert key in actual, f"Missing key: {key}"
        actual_val = actual[key]
        assert actual_val == expected_val, (
            f"Key '{key}' mismatch: expected {expected_val!r}, got {actual_val!r}"
        )


# =============================================================================
# DataFrame Assertions
# =============================================================================


def assert_dataframe_has_columns(df: Any, required_columns: list[str]) -> None:
    """Assert DataFrame has all required columns.

    Args:
        df: pandas DataFrame
        required_columns: List of column names that must exist

    Raises:
        AssertionError: If any required column is missing
    """
    import pandas as pd

    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
    missing = set(required_columns) - set(df.columns)
    assert not missing, f"Missing columns: {missing}"


def assert_no_null_values(df: Any, columns: list[str] | None = None) -> None:
    """Assert DataFrame has no null values in specified columns.

    Args:
        df: pandas DataFrame
        columns: Columns to check (all if None)

    Raises:
        AssertionError: If null values found
    """
    import pandas as pd

    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
    cols_to_check = columns or df.columns.tolist()

    for col in cols_to_check:
        if col in df.columns:
            null_count = df[col].isna().sum()
            assert null_count == 0, f"Column '{col}' has {null_count} null values"


def assert_dataframe_not_empty(df: Any, min_rows: int = 1) -> None:
    """Assert DataFrame has at least min_rows rows.

    Args:
        df: pandas DataFrame
        min_rows: Minimum number of rows required

    Raises:
        AssertionError: If DataFrame has fewer rows than required
    """
    import pandas as pd

    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
    assert len(df) >= min_rows, f"Expected at least {min_rows} rows, got {len(df)}"


def assert_column_values_in_set(df: Any, column: str, valid_values: set) -> None:
    """Assert all values in a column are from a valid set.

    Args:
        df: pandas DataFrame
        column: Column name to check
        valid_values: Set of allowed values

    Raises:
        AssertionError: If invalid values found
    """
    import pandas as pd

    assert isinstance(df, pd.DataFrame), f"Expected DataFrame, got {type(df)}"
    assert column in df.columns, f"Column '{column}' not found"

    actual_values = set(df[column].dropna().unique())
    invalid = actual_values - valid_values
    assert not invalid, f"Invalid values in '{column}': {invalid}"


# =============================================================================
# Transition Assertions
# =============================================================================


def assert_valid_transition(transition: Any) -> None:
    """Assert transition object has valid structure.

    Args:
        transition: Transition instance

    Raises:
        AssertionError: If transition is invalid
    """
    assert hasattr(transition, "transition_id"), "Missing transition_id"
    assert hasattr(transition, "award_id"), "Missing award_id"
    assert hasattr(transition, "likelihood_score"), "Missing likelihood_score"
    assert hasattr(transition, "confidence"), "Missing confidence"

    # Validate score range
    score = transition.likelihood_score
    assert 0 <= score <= 1, f"Likelihood score must be 0-1, got {score}"


def assert_valid_enrichment_result(result: Any, expected_source: str | None = None) -> None:
    """Assert enrichment result has valid structure.

    Args:
        result: Enrichment result object
        expected_source: Expected source name (optional)

    Raises:
        AssertionError: If result is invalid
    """
    assert hasattr(result, "confidence"), "Missing confidence"
    assert hasattr(result, "source"), "Missing source"

    # Validate confidence range
    conf = result.confidence
    assert 0 <= conf <= 1, f"Confidence must be 0-1, got {conf}"

    if expected_source:
        assert result.source == expected_source, (
            f"Expected source '{expected_source}', got '{result.source}'"
        )


# =============================================================================
# Quality Check Assertions
# =============================================================================


def assert_quality_issues_count(
    issues: list, expected_count: int, severity: str | None = None
) -> None:
    """Assert quality issues list has expected count.

    Args:
        issues: List of quality issues
        expected_count: Expected number of issues
        severity: Filter by severity (optional)

    Raises:
        AssertionError: If count doesn't match
    """
    if severity:
        filtered = [i for i in issues if str(i.severity).upper() == severity.upper()]
        actual = len(filtered)
        assert actual == expected_count, (
            f"Expected {expected_count} {severity} issues, got {actual}"
        )
    else:
        assert len(issues) == expected_count, f"Expected {expected_count} issues, got {len(issues)}"


def assert_no_quality_issues(issues: list) -> None:
    """Assert no quality issues found."""
    assert len(issues) == 0, f"Expected no issues, got {len(issues)}: {issues}"


def assert_quality_issue_field(issues: list, field: str) -> None:
    """Assert at least one issue exists for the given field."""
    fields = [i.field for i in issues]
    assert field in fields, f"Expected issue for field '{field}', found: {fields}"


# =============================================================================
# Evidence Assertions
# =============================================================================


def assert_valid_evidence_item(evidence: Any, expected_signal: str | None = None) -> None:
    """Assert evidence item has valid structure.

    Args:
        evidence: Evidence item
        expected_signal: Expected signal type (optional)

    Raises:
        AssertionError: If evidence is invalid
    """
    assert hasattr(evidence, "source"), "Missing source"
    assert hasattr(evidence, "signal"), "Missing signal"
    assert hasattr(evidence, "score"), "Missing score"
    assert hasattr(evidence, "snippet"), "Missing snippet"

    assert 0 <= evidence.score <= 1, f"Score must be 0-1, got {evidence.score}"
    assert len(evidence.snippet) > 0, "Snippet should not be empty"

    if expected_signal:
        assert evidence.signal == expected_signal, (
            f"Expected signal '{expected_signal}', got '{evidence.signal}'"
        )


def assert_evidence_contains_text(evidence: Any, text: str) -> None:
    """Assert evidence snippet contains expected text."""
    assert text.lower() in evidence.snippet.lower(), (
        f"Expected '{text}' in snippet: {evidence.snippet}"
    )


# =============================================================================
# Validator Result Assertions
# =============================================================================


def assert_validator_success(result: Any) -> None:
    """Assert validator result indicates success."""
    assert result.success is True, f"Expected success, got failure: {result.summary}"


def assert_validator_failure(result: Any) -> None:
    """Assert validator result indicates failure."""
    assert result.success is False, f"Expected failure, got success: {result.summary}"


def assert_validator_summary_key(result: Any, key: str, expected_value: Any = None) -> None:
    """Assert validator summary contains expected key/value."""
    assert key in result.summary, f"Missing summary key: {key}"
    if expected_value is not None:
        assert result.summary[key] == expected_value, (
            f"Summary[{key}] expected {expected_value}, got {result.summary[key]}"
        )
