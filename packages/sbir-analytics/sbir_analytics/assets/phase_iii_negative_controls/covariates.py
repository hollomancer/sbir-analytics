"""Arm-blind administrative covariates for Phase III control matching."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from sbir_etl.utils.identifiers import normalize_uei

from .identity import IdentityRecoveryError
from .sam_eligibility import EligibilityStatus, require_reliable_sam_eligibility


MATCH_COVARIATES = (
    "primary_naics",
    "first_contract_business_size",
    "state",
    "first_contract_year",
    "psc_family",
)
USABLE_SIZE_CLASSES = frozenset({"small_business", "other_than_small_business"})

FIRM_FRAME_COLUMNS = ("firm_id", "firm_ueis")
SAM_COLUMNS = ("unique_entity_id", "primary_naics", "physical_address_state")
CONTRACT_COLUMNS = ("vendor_uei", "action_date", "product_or_service_code", "metadata")

_NULL_TEXT = frozenset({"", "<NA>", "NAN", "NAT", "NONE", "NULL", r"\N"})
_NAICS_PATTERN = re.compile(r"^\d{6}$")
_STATE_PATTERN = re.compile(r"^[A-Z]{2}$")
_PSC_PATTERN = re.compile(r"^[A-Z0-9]{4}$")
_BUSINESS_CATEGORY_PATTERN = re.compile(r"^[a-z0-9_]+$")


class CovariateInputError(IdentityRecoveryError):
    """Raised when a matching-covariate source cannot be interpreted exactly."""


def _text(value: Any) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    value_text = str(value).strip()
    return "" if value_text.upper() in _NULL_TEXT else value_text


def _values(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple | list | set):
        return tuple(value)
    tolist = getattr(value, "tolist", None)
    converted = tolist() if callable(tolist) else None
    if isinstance(converted, list):
        return tuple(converted)
    return () if not _text(value) else (value,)


def _require_columns(frame: pd.DataFrame, required: Iterable[str], *, label: str) -> None:
    if missing := sorted(set(required) - set(frame.columns)):
        raise CovariateInputError(f"{label} is missing required columns: {missing}")


def _normalize_naics(value: Any) -> str:
    normalized = _text(value)
    return normalized if _NAICS_PATTERN.fullmatch(normalized) else ""


def _normalize_state(value: Any) -> str:
    normalized = _text(value).upper()
    return normalized if _STATE_PATTERN.fullmatch(normalized) else ""


def _normalize_psc_family(value: Any) -> str:
    normalized = _text(value).upper()
    if not _PSC_PATTERN.fullmatch(normalized):
        return ""
    # The repository's existing PSC-family convention is the leading PSC character.
    return normalized[0]


def _parse_business_categories(value: Any) -> frozenset[str] | None:
    """Parse the PostgreSQL text-array representation preserved by the extractor."""

    raw = _text(value)
    if not raw:
        return None
    if not (raw.startswith("{") and raw.endswith("}")):
        return None
    payload = raw[1:-1].strip()
    if not payload:
        return frozenset()
    tokens = tuple(token.strip().strip('"').lower() for token in payload.split(","))
    if any(not token or not _BUSINESS_CATEGORY_PATTERN.fullmatch(token) for token in tokens):
        return None
    return frozenset(tokens)


def _metadata_value(metadata: Any, key: str) -> Any:
    if isinstance(metadata, Mapping):
        return metadata.get(key)
    asdict = getattr(metadata, "as_py", None)
    converted = asdict() if callable(asdict) else None
    return converted.get(key) if isinstance(converted, Mapping) else None


def _normalize_firm_frame(firms: pd.DataFrame) -> pd.DataFrame:
    _require_columns(firms, FIRM_FRAME_COLUMNS, label="firm frame")
    records: list[dict[str, Any]] = []
    seen_firm_ids: set[str] = set()
    owned_ueis: dict[str, str] = {}
    for row in firms.loc[:, list(FIRM_FRAME_COLUMNS)].itertuples(index=False):
        firm_id = _text(row.firm_id)
        ueis = tuple(
            sorted({uei for value in _values(row.firm_ueis) if (uei := normalize_uei(value))})
        )
        if not firm_id or not ueis:
            raise CovariateInputError(
                "every firm must have a nonblank id and at least one valid UEI"
            )
        if firm_id in seen_firm_ids:
            raise CovariateInputError(f"firm frame contains duplicate firm_id: {firm_id}")
        for uei in ueis:
            previous = owned_ueis.setdefault(uei, firm_id)
            if previous != firm_id:
                raise CovariateInputError(
                    f"UEI {uei} belongs to multiple firm envelopes: {previous}, {firm_id}"
                )
        seen_firm_ids.add(firm_id)
        records.append({"firm_id": firm_id, "firm_ueis": ueis})
    return pd.DataFrame.from_records(records, columns=FIRM_FRAME_COLUMNS)


def build_treated_firm_frame(phase_ii_awards: pd.DataFrame) -> pd.DataFrame:
    """Return one treated firm per exact, nonblank Phase II recipient UEI."""

    _require_columns(phase_ii_awards, ("recipient_uei",), label="Phase II award frame")
    ueis = sorted(
        {uei for value in phase_ii_awards["recipient_uei"] if (uei := normalize_uei(value))}
    )
    return pd.DataFrame(
        {"firm_id": ueis, "firm_ueis": [(uei,) for uei in ueis]},
        columns=FIRM_FRAME_COLUMNS,
    )


def build_control_firm_frame(eligibility: pd.DataFrame) -> pd.DataFrame:
    """Return screened-negative SAM identity envelopes and all their exact UEIs."""

    require_reliable_sam_eligibility(eligibility)
    _require_columns(
        eligibility,
        ("candidate_envelope_id", "candidate_ueis", "eligibility_status"),
        label="SAM eligibility table",
    )
    eligible = eligibility.loc[
        eligibility["eligibility_status"].eq(EligibilityStatus.ELIGIBLE_SCREENED_NEGATIVE.value),
        ["candidate_envelope_id", "candidate_ueis"],
    ].rename(columns={"candidate_envelope_id": "firm_id", "candidate_ueis": "firm_ueis"})
    return _normalize_firm_frame(eligible.reset_index(drop=True))


def _sam_indexes(sam_entities: pd.DataFrame) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    _require_columns(sam_entities, SAM_COLUMNS, label="SAM entity frame")
    naics_by_uei: dict[str, set[str]] = defaultdict(set)
    state_by_uei: dict[str, set[str]] = defaultdict(set)
    for row in sam_entities.loc[:, list(SAM_COLUMNS)].itertuples(index=False):
        uei = normalize_uei(row.unique_entity_id)
        if not uei:
            continue
        if naics := _normalize_naics(row.primary_naics):
            naics_by_uei[uei].add(naics)
        if state := _normalize_state(row.physical_address_state):
            state_by_uei[uei].add(state)
    return naics_by_uei, state_by_uei


def _contract_index(contracts: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    _require_columns(contracts, CONTRACT_COLUMNS, label="February contract frame")
    rows_by_uei: dict[str, list[dict[str, Any]]] = defaultdict(list)
    action_dates = pd.to_datetime(contracts["action_date"], errors="coerce")
    for row, action_date in zip(
        contracts.loc[:, list(CONTRACT_COLUMNS)].itertuples(index=False),
        action_dates,
        strict=True,
    ):
        uei = normalize_uei(row.vendor_uei)
        if not uei or pd.isna(action_date):
            continue
        rows_by_uei[uei].append(
            {
                "action_date": action_date.date(),
                "psc_family": _normalize_psc_family(row.product_or_service_code),
                "business_categories": _parse_business_categories(
                    _metadata_value(row.metadata, "business_categories")
                ),
            }
        )
    return rows_by_uei


def _unanimous(values: set[str]) -> tuple[str, str]:
    if not values:
        return "", "missing"
    if len(values) > 1:
        return "", "conflict"
    return next(iter(values)), "observed"


def build_firm_covariates(
    firms: pd.DataFrame,
    sam_entities: pd.DataFrame,
    contracts: pd.DataFrame,
) -> pd.DataFrame:
    """Build the same five matching covariates for either study arm.

    Only earliest-contract rows are consulted. Later contract dates, coding,
    competition, obligations, descriptions, and census criteria are inaccessible here.
    """

    normalized_firms = _normalize_firm_frame(firms)
    naics_by_uei, state_by_uei = _sam_indexes(sam_entities)
    contracts_by_uei = _contract_index(contracts)
    records: list[dict[str, Any]] = []
    for firm in normalized_firms.to_dict(orient="records"):
        firm_id = str(firm["firm_id"])
        firm_ueis = tuple(str(value) for value in _values(firm["firm_ueis"]))
        naics, naics_status = _unanimous(
            {value for uei in firm_ueis for value in naics_by_uei.get(uei, set())}
        )
        state, state_status = _unanimous(
            {value for uei in firm_ueis for value in state_by_uei.get(uei, set())}
        )
        contract_rows = [row for uei in firm_ueis for row in contracts_by_uei.get(uei, [])]
        first_date = min((row["action_date"] for row in contract_rows), default=None)
        first_rows = [row for row in contract_rows if row["action_date"] == first_date]
        psc_family, psc_status = _unanimous(
            {row["psc_family"] for row in first_rows if row["psc_family"]}
        )
        parsed_size_sets = [
            row["business_categories"]
            for row in first_rows
            if row["business_categories"] is not None
        ]
        size_values = {
            "small_business" if "small_business" in categories else "other_than_small_business"
            for categories in parsed_size_sets
        }
        size_class, size_status = _unanimous(size_values)
        reasons = tuple(
            f"{covariate}_{status}"
            for covariate, status in (
                ("primary_naics", naics_status),
                ("state", state_status),
                ("first_contract", "missing" if first_date is None else "observed"),
                ("first_contract_business_size", size_status),
                ("psc_family", psc_status),
            )
            if status != "observed"
        )
        records.append(
            {
                "firm_id": firm_id,
                "firm_ueis": firm_ueis,
                "primary_naics": naics or None,
                "first_contract_business_size": size_class or None,
                "state": state or None,
                "first_contract_year": first_date.year if first_date else None,
                "psc_family": psc_family or None,
                "first_contract_date": first_date,
                "first_contract_rows": len(first_rows),
                "match_eligible": not reasons,
                "covariate_exclusion_reasons": reasons,
            }
        )
    return pd.DataFrame.from_records(records)


def summarize_covariate_coverage(covariates: pd.DataFrame, *, arm: str) -> pd.DataFrame:
    """Report observed/missing/conflict coverage without selecting an acceptable rate."""

    _require_columns(
        covariates,
        (*MATCH_COVARIATES, "covariate_exclusion_reasons"),
        label="firm covariates",
    )
    reasons = [set(_values(value)) for value in covariates["covariate_exclusion_reasons"]]
    rows: list[dict[str, Any]] = []
    for covariate in MATCH_COVARIATES:
        missing_reason = f"{covariate}_missing"
        conflict_reason = f"{covariate}_conflict"
        if covariate == "first_contract_year":
            missing_reason = "first_contract_missing"
            conflict_reason = "first_contract_conflict"
        missing = sum(missing_reason in value for value in reasons)
        conflict = sum(conflict_reason in value for value in reasons)
        rows.append(
            {
                "arm": arm,
                "covariate": covariate,
                "observed_firms": int(len(covariates) - missing - conflict),
                "missing_firms": int(missing),
                "conflict_firms": int(conflict),
                "total_firms": int(len(covariates)),
            }
        )
    return pd.DataFrame.from_records(rows)


__all__ = [
    "CONTRACT_COLUMNS",
    "MATCH_COVARIATES",
    "CovariateInputError",
    "build_control_firm_frame",
    "build_firm_covariates",
    "build_treated_firm_frame",
    "summarize_covariate_coverage",
]
