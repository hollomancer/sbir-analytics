"""Date-aware firm presence for the Form D business-combination filing proxy.

This exploratory-tier module deliberately knows nothing about study assignment beyond
validating the arm label.  Both arms pass through the same event, coverage, follow-up,
and right-censoring rules.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any

from .outcomes import wilson_interval


EVENT_TYPE = "form_d_business_combination_filing_proxy"
DEFAULT_HORIZON_YEARS = 5
DEFAULT_SNAPSHOT_DATE = date(2024, 12, 31)
VALID_ARMS = ("treated", "control")


class OutcomeContractError(ValueError):
    """Raised when records cannot be interpreted without changing the estimand."""


def _parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _firm_key(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    prefix = "form_d_cik:"
    if not value.startswith(prefix):
        return None
    cik = value[len(prefix) :]
    if not cik.isdigit() or cik.startswith("0") or len(cik) > 10:
        return None
    return value


def _horizon_end(index_date: date, years: int) -> date:
    try:
        return index_date.replace(year=index_date.year + years)
    except ValueError:
        # Calendar-year horizons map leap day to the final day of February.
        return index_date.replace(year=index_date.year + years, day=28)


def _event_in_window(record: Mapping[str, Any], start: date, end: date) -> bool:
    event_date = _parse_date(record.get("event_date"))
    return event_date is not None and start <= event_date <= end


def _nonblank_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _event_is_complete(record: Mapping[str, Any]) -> bool:
    accession = record.get("accession_number")
    source_quarter = record.get("source_quarter")
    event_date = _parse_date(record.get("event_date"))
    filing_date = _parse_date(record.get("filing_date"))
    return (
        _nonblank_text(record.get("event_id"))
        and _nonblank_text(accession)
        and event_date is not None
        and event_date == filing_date
        and record.get("date_basis") == "filing_date"
        and record.get("evidence_kind") == "proxy"
        and _nonblank_text(record.get("source"))
        and _nonblank_text(record.get("source_snapshot_id"))
        and _nonblank_text(source_quarter)
        and isinstance(record.get("is_amendment"), bool)
        and "previous_accession_number" in record
    )


def _index_events(
    event_records: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], set[str], set[tuple[str, str]]]:
    events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incomplete_firms: set[str] = set()
    source_contracts: set[tuple[str, str]] = set()
    event_ids: set[str] = set()
    for record in event_records:
        if record.get("event_type") != EVENT_TYPE:
            raise OutcomeContractError(f"event_type must be {EVENT_TYPE!r}")
        firm_key = _firm_key(record.get("firm_key"))
        if firm_key is None:
            raise OutcomeContractError("event record contains an invalid Form D CIK firm_key")
        if not _event_is_complete(record):
            incomplete_firms.add(firm_key)
            continue
        event_id = str(record["event_id"])
        if event_id in event_ids:
            raise OutcomeContractError(f"event records contain duplicate event_id: {event_id}")
        event_ids.add(event_id)
        source_contracts.add((str(record["source"]), str(record["source_snapshot_id"])))
        events[firm_key].append(dict(record))
    for rows in events.values():
        rows.sort(key=lambda row: (str(row["event_date"]), str(row["event_id"])))
    return dict(events), incomplete_firms, source_contracts


def _index_coverage(
    coverage_records: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], bool, set[tuple[str, str]], bool]:
    coverage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_complete = True
    source_contracts: set[tuple[str, str]] = set()
    source_snapshots: set[date] = set()
    source_present = False
    for record in coverage_records:
        source_present = True
        if record.get("metric") != EVENT_TYPE:
            raise OutcomeContractError(f"coverage metric must be {EVENT_TYPE!r}")
        firm_key = _firm_key(record.get("firm_key"))
        if firm_key is None:
            raise OutcomeContractError("coverage record contains an invalid Form D CIK firm_key")
        start = _parse_date(record.get("coverage_start_date"))
        end = _parse_date(record.get("coverage_end_date"))
        snapshot = _parse_date(record.get("source_snapshot_date"))
        source = record.get("source")
        source_snapshot_id = record.get("source_snapshot_id")
        valid_interval = start is not None and end is not None and start <= end
        if (
            record.get("source_complete") is not True
            or not valid_interval
            or snapshot is None
            or not _nonblank_text(source)
            or not _nonblank_text(source_snapshot_id)
        ):
            source_complete = False
        if _nonblank_text(source) and _nonblank_text(source_snapshot_id):
            source_contracts.add((str(source), str(source_snapshot_id)))
        if snapshot is not None:
            source_snapshots.add(snapshot)
        coverage[firm_key].append(dict(record))
    if len(source_snapshots) > 1 or len(source_contracts) > 1:
        source_complete = False
    return dict(coverage), source_complete, source_contracts, source_present


def _unavailable(
    *,
    arm: str,
    firm_key: str | None,
    index_date: date | None,
    horizon_end_date: date | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "arm": arm,
        "firm_key": firm_key,
        "index_date": index_date.isoformat() if index_date else None,
        "horizon_end_date": horizon_end_date.isoformat() if horizon_end_date else None,
        "metric": EVENT_TYPE,
        "available": False,
        "value": None,
        "event_count": 0,
        "evidence": [],
        "unavailability_reason": reason,
    }


def evaluate_event_presence(
    risk_set: Iterable[Mapping[str, Any]],
    event_records: Iterable[Mapping[str, Any]],
    coverage_records: Iterable[Mapping[str, Any]],
    *,
    horizon_years: int = DEFAULT_HORIZON_YEARS,
    snapshot_date: date = DEFAULT_SNAPSHOT_DATE,
) -> list[dict[str, Any]]:
    """Evaluate inclusive in-window firm presence for one unlabeled risk-set stream.

    Risk-set records require ``arm``, exact ``form_d_cik:<CIK>`` ``firm_key``, and
    ``index_date``. Invalid firm identities and unavailable observation windows remain
    explicit rows but do not enter aggregate denominators.
    """

    if isinstance(horizon_years, bool) or not isinstance(horizon_years, int) or horizon_years <= 0:
        raise OutcomeContractError("horizon_years must be a positive integer")
    parsed_snapshot = _parse_date(snapshot_date)
    if parsed_snapshot is None:
        raise OutcomeContractError("snapshot_date must be a valid date")

    events_by_firm, incomplete_event_firms, event_sources = _index_events(event_records)
    coverage_by_firm, source_complete, coverage_sources, source_present = _index_coverage(
        coverage_records
    )
    if event_sources and event_sources != coverage_sources:
        source_complete = False
    evaluated: list[dict[str, Any]] = []
    seen_firms: dict[str, str] = {}

    for record in risk_set:
        arm = str(record.get("arm") or "").strip().lower()
        if arm not in VALID_ARMS:
            raise OutcomeContractError(f"arm must be one of {list(VALID_ARMS)}")
        firm_key = _firm_key(record.get("firm_key"))
        index_date = _parse_date(record.get("index_date"))
        horizon_end_date = _horizon_end(index_date, horizon_years) if index_date else None

        if firm_key is None:
            evaluated.append(
                _unavailable(
                    arm=arm,
                    firm_key=None,
                    index_date=index_date,
                    horizon_end_date=horizon_end_date,
                    reason="invalid_firm_key",
                )
            )
            continue
        prior_arm = seen_firms.get(firm_key)
        if prior_arm is not None:
            if prior_arm != arm:
                raise OutcomeContractError(f"firm {firm_key} appears in both arms")
            raise OutcomeContractError(
                f"risk set contains duplicate firm identity: {(arm, firm_key)}"
            )
        seen_firms[firm_key] = arm
        if index_date is None:
            evaluated.append(
                _unavailable(
                    arm=arm,
                    firm_key=firm_key,
                    index_date=None,
                    horizon_end_date=None,
                    reason="invalid_index_date",
                )
            )
            continue
        if not source_present:
            evaluated.append(
                _unavailable(
                    arm=arm,
                    firm_key=firm_key,
                    index_date=index_date,
                    horizon_end_date=horizon_end_date,
                    reason="missing_source",
                )
            )
            continue
        if not source_complete:
            evaluated.append(
                _unavailable(
                    arm=arm,
                    firm_key=firm_key,
                    index_date=index_date,
                    horizon_end_date=horizon_end_date,
                    reason="incomplete_source",
                )
            )
            continue
        if firm_key in incomplete_event_firms:
            evaluated.append(
                _unavailable(
                    arm=arm,
                    firm_key=firm_key,
                    index_date=index_date,
                    horizon_end_date=horizon_end_date,
                    reason="incomplete_source",
                )
            )
            continue

        firm_coverage = coverage_by_firm.get(firm_key, [])
        if len(firm_coverage) != 1:
            reason = "missing_coverage" if not firm_coverage else "ambiguous_coverage"
            evaluated.append(
                _unavailable(
                    arm=arm,
                    firm_key=firm_key,
                    index_date=index_date,
                    horizon_end_date=horizon_end_date,
                    reason=reason,
                )
            )
            continue
        coverage = firm_coverage[0]
        coverage_start = _parse_date(coverage.get("coverage_start_date"))
        coverage_end = _parse_date(coverage.get("coverage_end_date"))
        source_snapshot = _parse_date(coverage.get("source_snapshot_date"))
        if coverage_start is None or coverage_end is None or source_snapshot is None:
            raise AssertionError("complete coverage was not parseable")
        if coverage_start > index_date:
            evaluated.append(
                _unavailable(
                    arm=arm,
                    firm_key=firm_key,
                    index_date=index_date,
                    horizon_end_date=horizon_end_date,
                    reason="outside_coverage",
                )
            )
            continue
        assert horizon_end_date is not None
        follow_up_end = min(coverage_end, source_snapshot, parsed_snapshot)
        if horizon_end_date > follow_up_end:
            evaluated.append(
                _unavailable(
                    arm=arm,
                    firm_key=firm_key,
                    index_date=index_date,
                    horizon_end_date=horizon_end_date,
                    reason="right_censored",
                )
            )
            continue

        evidence = [
            event
            for event in events_by_firm.get(firm_key, [])
            if _event_in_window(event, index_date, horizon_end_date)
        ]
        evaluated.append(
            {
                "arm": arm,
                "firm_key": firm_key,
                "index_date": index_date.isoformat(),
                "horizon_end_date": horizon_end_date.isoformat(),
                "metric": EVENT_TYPE,
                "available": True,
                "value": int(bool(evidence)),
                "event_count": len(evidence),
                "evidence": evidence,
                "unavailability_reason": None,
            }
        )
    return evaluated


def aggregate_event_presence(evaluated: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate available firm-presence rows by arm with Wilson intervals."""

    rows = list(evaluated)
    aggregates: list[dict[str, Any]] = []
    for arm in VALID_ARMS:
        arm_rows = [row for row in rows if row.get("arm") == arm]
        if not arm_rows:
            continue
        if any(row.get("metric") != EVENT_TYPE for row in arm_rows):
            raise OutcomeContractError(f"aggregate rows must use metric {EVENT_TYPE!r}")
        available = [row for row in arm_rows if row.get("available") is True]
        if any(row.get("value") not in {0, 1} for row in available):
            raise OutcomeContractError("available aggregate rows must have binary values")
        numerator = sum(int(row["value"]) for row in available)
        interval = wilson_interval(numerator, len(available))
        exclusion_reasons = Counter(
            str(row.get("unavailability_reason") or "unspecified")
            for row in arm_rows
            if row.get("available") is not True
        )
        aggregates.append(
            {
                "arm": arm,
                "metric": EVENT_TYPE,
                "numerator": interval["numerator"],
                "denominator": interval["denominator"],
                "rate": interval["rate"],
                "ci_low": interval["ci_low"],
                "ci_high": interval["ci_high"],
                "excluded": len(arm_rows) - len(available),
                "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
            }
        )
    return aggregates
