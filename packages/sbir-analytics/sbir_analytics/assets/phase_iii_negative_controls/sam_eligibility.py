"""Exact SAM identity envelopes and fail-closed SBIR eligibility screening."""

import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from enum import StrEnum
from typing import Any

import pandas as pd

from sbir_etl.utils.identifiers import normalize_cage, normalize_duns, normalize_uei

from .identity import IdentityRecoveryError, RecoveryStatus
from .quarantine import (
    normalize_quarantine_component,
    normalize_zip5,
    require_complete_unresolved_quarantine_keys,
)


class EligibilityStatus(StrEnum):
    """Exhaustive preregistered control-candidate eligibility outcomes."""

    CONFIRMED_SBIR = "confirmed_sbir"
    INDETERMINATE_POSSIBLE_SBIR = "indeterminate_possible_sbir"
    ELIGIBLE_SCREENED_NEGATIVE = "eligible_screened_negative"


SAM_ELIGIBILITY_COLUMNS = (
    "unique_entity_id",
    "duns_number",
    "cage_code",
    "legal_business_name",
    "dba_name",
    "physical_address_line_1",
    "physical_address_line_2",
    "physical_address_state",
    "physical_address_zip_postal_code",
)
IDENTITY_LINK_COLUMNS = (
    "uei",
    "duns",
    "cage",
    "official_record_id",
    "source_digest",
    "snapshot_date",
)

_SBIR_SOURCE_REQUIRED = frozenset({"source_row_sha256", "uei", "duns"})
_RECOVERY_REQUIRED = frozenset(
    {"source_row_sha256", "recovery_status", "resolved_ueis", "resolved_duns"}
)
_QUARANTINE_REQUIRED = frozenset(
    {
        "source_row_sha256",
        "name_state_key",
        "address_zip_key",
        # Also required by require_complete_unresolved_quarantine_keys, which this
        # module calls; declaring them here fails closed at the boundary instead
        # of surfacing schema drift as a less direct error deeper in the gate.
        "coverage_category",
        "has_name_state_key",
        "has_address_zip_key",
    }
)
_NULL_TEXT = frozenset({"", "<NA>", "NAN", "NAT", "NONE", "NULL", r"\N"})
# Same strict form the quarantine audit enforces, so a malformed fingerprint
# cannot pass this screen and silently fail to intersect there.
_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_STATUS_ORDER = tuple(status.value for status in EligibilityStatus)
_REASON_ORDER = (
    "resolved_uei_intersection",
    "resolved_duns_intersection",
    "unresolved_name_state_collision",
    "unresolved_address_zip_collision",
    "missing_comparable_name_state_key",
    "phase_ii_uei_intersection",
    "fpds_sbir_sttr_code_intersection",
)
_FEDERAL_SBIR_STTR_CODES = frozenset({"SR1", "SR2", "SR3", "ST1", "ST2", "ST3"})


def _text(value: Any) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    normalized = str(value).strip()
    return "" if normalized.upper() in _NULL_TEXT else normalized


def _require_columns(frame: pd.DataFrame, required: Iterable[str], *, label: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise IdentityRecoveryError(f"{label} is missing required columns: {missing}")


def _require_unique_fingerprints(frame: pd.DataFrame, *, label: str) -> pd.Series:
    fingerprints = frame["source_row_sha256"].map(_text).str.lower()
    if not fingerprints.map(lambda value: bool(_FINGERPRINT_PATTERN.fullmatch(value))).all():
        raise IdentityRecoveryError(
            f"{label}.source_row_sha256 must contain complete lowercase SHA-256 values"
        )
    if fingerprints.duplicated().any():
        raise IdentityRecoveryError(f"{label}.source_row_sha256 values must be unique")
    return fingerprints


def _values(value: Any) -> tuple[Any, ...]:
    if isinstance(value, (tuple, list, set)):
        return tuple(value)
    tolist = getattr(value, "tolist", None)
    converted = tolist() if callable(tolist) else None
    if isinstance(converted, list):
        return tuple(converted)
    return () if not _text(value) else (value,)


class _DisjointSet:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, token: str) -> None:
        self.parent.setdefault(token, token)

    def find(self, token: str) -> str:
        root = token
        while self.parent[root] != root:
            root = self.parent[root]

        while self.parent[token] != token:
            parent = self.parent[token]
            self.parent[token] = root
            token = parent
        return root

    def union_all(self, tokens: Iterable[str]) -> None:
        values = tuple(tokens)
        for token in values:
            self.add(token)
        if not values:
            return
        first = values[0]
        for token in values[1:]:
            left = self.find(first)
            right = self.find(token)
            if left != right:
                keep, replace = sorted((left, right))
                self.parent[replace] = keep


def _identifier_tokens(uei: Any, duns: Any, cage: Any) -> tuple[str, ...]:
    normalized = (
        ("UEI", normalize_uei(uei)),
        ("DUNS", normalize_duns(duns)),
        ("CAGE", normalize_cage(cage)),
    )
    return tuple(f"{kind}:{value}" for kind, value in normalized if value is not None)


def _resolved_sbir_identifiers(
    sbir_awards: pd.DataFrame,
    recovery_audit: pd.DataFrame,
    quarantine_audit: pd.DataFrame,
) -> tuple[set[str], set[str]]:
    _require_columns(sbir_awards, _SBIR_SOURCE_REQUIRED, label="SBIR source frame")
    _require_columns(recovery_audit, _RECOVERY_REQUIRED, label="recovery audit")
    _require_columns(quarantine_audit, _QUARANTINE_REQUIRED, label="quarantine audit")

    source_fingerprints = _require_unique_fingerprints(sbir_awards, label="SBIR source frame")
    recovery_fingerprints = _require_unique_fingerprints(recovery_audit, label="recovery audit")
    quarantine_fingerprints = _require_unique_fingerprints(
        quarantine_audit,
        label="quarantine audit",
    )

    direct_ueis = sbir_awards["uei"].map(normalize_uei)
    direct_duns = sbir_awards["duns"].map(normalize_duns)
    identifier_poor = set(source_fingerprints[direct_ueis.isna() & direct_duns.isna()])
    if set(recovery_fingerprints) != identifier_poor:
        raise IdentityRecoveryError(
            "recovery audit must cover exactly the SBIR source rows without a valid UEI or DUNS"
        )

    valid_statuses = {status.value for status in RecoveryStatus}
    statuses = recovery_audit["recovery_status"].map(_text)
    if invalid := sorted(set(statuses) - valid_statuses):
        raise IdentityRecoveryError(f"recovery audit contains invalid statuses: {invalid}")
    unresolved = set(
        recovery_fingerprints[statuses.ne(RecoveryStatus.RESOLVED_AUTHORITATIVE.value)]
    )
    if set(quarantine_fingerprints) != unresolved:
        raise IdentityRecoveryError(
            "quarantine audit must cover exactly the unresolved recovery rows"
        )
    require_complete_unresolved_quarantine_keys(quarantine_audit)

    resolved_ueis = {value for value in direct_ueis if value is not None}
    resolved_duns = {value for value in direct_duns if value is not None}
    for row in recovery_audit.loc[
        statuses.eq(RecoveryStatus.RESOLVED_AUTHORITATIVE.value)
    ].itertuples(index=False):
        recovered_ueis = {
            value for item in _values(row.resolved_ueis) if (value := normalize_uei(item))
        }
        recovered_duns = {
            value for item in _values(row.resolved_duns) if (value := normalize_duns(item))
        }
        if not recovered_ueis and not recovered_duns:
            raise IdentityRecoveryError("resolved recovery row has no valid UEI or DUNS")
        resolved_ueis.update(recovered_ueis)
        resolved_duns.update(recovered_duns)
    return resolved_ueis, resolved_duns


def build_sam_eligibility_table(
    sam_entities: pd.DataFrame,
    sbir_awards: pd.DataFrame,
    recovery_audit: pd.DataFrame,
    quarantine_audit: pd.DataFrame,
    *,
    identity_links: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build one exact identity envelope and eligibility status per SAM firm.

    Identifier components are joined only by exact UEI/DUNS/CAGE co-occurrence
    on the supplied official records. Names and addresses are attached as
    aliases after component construction and can only quarantine a candidate.
    """

    _require_columns(sam_entities, SAM_ELIGIBILITY_COLUMNS, label="SAM entity frame")
    if sam_entities.empty:
        raise IdentityRecoveryError("SAM entity frame is empty")
    if identity_links is not None:
        _require_columns(identity_links, IDENTITY_LINK_COLUMNS, label="identity-link frame")
        for column in ("official_record_id", "source_digest", "snapshot_date"):
            if identity_links[column].map(_text).eq("").any():
                raise IdentityRecoveryError(f"identity-link frame.{column} contains a blank value")

    graph = _DisjointSet()
    entity_tokens: list[tuple[str, ...]] = []
    for row in sam_entities.loc[:, SAM_ELIGIBILITY_COLUMNS].itertuples(index=False):
        tokens = _identifier_tokens(row.unique_entity_id, row.duns_number, row.cage_code)
        if normalize_uei(row.unique_entity_id) is None:
            raise IdentityRecoveryError("every SAM candidate row must have a valid UEI")
        graph.union_all(tokens)
        entity_tokens.append(tokens)

    if identity_links is not None:
        for row in identity_links.loc[:, IDENTITY_LINK_COLUMNS].itertuples(index=False):
            tokens = _identifier_tokens(row.uei, row.duns, row.cage)
            if len(tokens) < 2:
                raise IdentityRecoveryError(
                    "every identity-link row must contain at least two valid co-occurring identifiers"
                )
            graph.union_all(tokens)

    component_tokens: dict[str, set[str]] = {}
    for token in graph.parent:
        component_tokens.setdefault(graph.find(token), set()).add(token)

    entity_components = [graph.find(tokens[0]) for tokens in entity_tokens]
    component_row_counts = Counter(entity_components)
    aliases: dict[str, dict[str, set[str]]] = {}
    for component, row in zip(
        entity_components,
        sam_entities.loc[:, SAM_ELIGIBILITY_COLUMNS].itertuples(index=False),
        strict=True,
    ):
        values = aliases.setdefault(component, {"name_state": set(), "address_zip": set()})
        state = normalize_quarantine_component(row.physical_address_state)
        if state:
            for name in (row.legal_business_name, row.dba_name):
                normalized_name = normalize_quarantine_component(name)
                if normalized_name:
                    values["name_state"].add(f"{normalized_name}|{state}")
        address = " ".join(
            value
            for raw in (row.physical_address_line_1, row.physical_address_line_2)
            if (value := normalize_quarantine_component(raw))
        )
        zip5 = normalize_zip5(row.physical_address_zip_postal_code)
        if address and zip5:
            values["address_zip"].add(f"{address}|{zip5}")

    resolved_ueis, resolved_duns = _resolved_sbir_identifiers(
        sbir_awards,
        recovery_audit,
        quarantine_audit,
    )
    unresolved_name_state = {
        value for raw in quarantine_audit["name_state_key"] if (value := _text(raw))
    }
    unresolved_address_zip = {
        value for raw in quarantine_audit["address_zip_key"] if (value := _text(raw))
    }

    records: list[dict[str, Any]] = []
    for component in sorted({graph.find(value) for value in entity_components}):
        tokens = component_tokens[component]
        ueis = tuple(
            sorted(token.removeprefix("UEI:") for token in tokens if token.startswith("UEI:"))
        )
        duns_values = tuple(
            sorted(token.removeprefix("DUNS:") for token in tokens if token.startswith("DUNS:"))
        )
        cages = tuple(
            sorted(token.removeprefix("CAGE:") for token in tokens if token.startswith("CAGE:"))
        )
        name_keys = tuple(sorted(aliases[component]["name_state"]))
        address_keys = tuple(sorted(aliases[component]["address_zip"]))
        matched_ueis = tuple(sorted(set(ueis) & resolved_ueis))
        matched_duns = tuple(sorted(set(duns_values) & resolved_duns))
        matched_names = tuple(sorted(set(name_keys) & unresolved_name_state))
        matched_addresses = tuple(sorted(set(address_keys) & unresolved_address_zip))
        confirmed_sbir = bool(matched_ueis or matched_duns)
        missing_comparable_key = not confirmed_sbir and not name_keys
        reasons = tuple(
            reason
            for reason, matched in (
                (_REASON_ORDER[0], matched_ueis),
                (_REASON_ORDER[1], matched_duns),
                (_REASON_ORDER[2], matched_names),
                (_REASON_ORDER[3], matched_addresses),
                (_REASON_ORDER[4], missing_comparable_key),
            )
            if matched
        )
        if confirmed_sbir:
            status = EligibilityStatus.CONFIRMED_SBIR
        elif missing_comparable_key or matched_names or matched_addresses:
            status = EligibilityStatus.INDETERMINATE_POSSIBLE_SBIR
        else:
            status = EligibilityStatus.ELIGIBLE_SCREENED_NEGATIVE

        envelope_id = hashlib.sha256("\n".join(sorted(tokens)).encode()).hexdigest()
        records.append(
            {
                "candidate_envelope_id": envelope_id,
                "eligibility_status": status.value,
                "exclusion_reasons": reasons,
                "candidate_ueis": ueis,
                "candidate_duns": duns_values,
                "candidate_cages": cages,
                "name_state_keys": name_keys,
                "address_zip_keys": address_keys,
                "matched_sbir_ueis": matched_ueis,
                "matched_sbir_duns": matched_duns,
                "matched_unresolved_name_state_keys": matched_names,
                "matched_unresolved_address_zip_keys": matched_addresses,
                "sam_source_rows": component_row_counts[component],
                "multiple_ueis": len(ueis) > 1,
                "multiple_duns": len(duns_values) > 1,
                "multiple_cages": len(cages) > 1,
            }
        )
    return pd.DataFrame.from_records(records)


def exclude_fpds_coded_awardees(
    eligibility: pd.DataFrame,
    contracts: pd.DataFrame,
) -> pd.DataFrame:
    """Conservatively confirm exact-UEI firms carrying any FPDS SBIR/STTR code.

    This is an eligibility screen across the complete extracted contract history,
    not a Phase III census outcome. It runs before covariates or matching and treats
    all six Phase I–III SBIR/STTR research codes identically.
    """

    _require_columns(
        eligibility,
        ("eligibility_status", "exclusion_reasons", "candidate_ueis"),
        label="eligibility table",
    )
    _require_columns(contracts, ("vendor_uei", "research"), label="FPDS contract frame")
    coded_ueis = {
        uei
        for row in contracts.loc[:, ["vendor_uei", "research"]].itertuples(index=False)
        if _text(row.research).upper() in _FEDERAL_SBIR_STTR_CODES
        and (uei := normalize_uei(row.vendor_uei))
    }
    result = eligibility.copy()
    matched_values: list[tuple[str, ...]] = []
    statuses: list[str] = []
    reasons: list[tuple[str, ...]] = []
    for row in result.itertuples(index=False):
        matched = tuple(
            sorted(
                {
                    uei
                    for value in _values(row.candidate_ueis)
                    if (uei := normalize_uei(value)) and uei in coded_ueis
                }
            )
        )
        current_reasons = tuple(_text(value) for value in _values(row.exclusion_reasons))
        if matched and "fpds_sbir_sttr_code_intersection" not in current_reasons:
            current_reasons = (*current_reasons, "fpds_sbir_sttr_code_intersection")
        statuses.append(
            EligibilityStatus.CONFIRMED_SBIR.value if matched else _text(row.eligibility_status)
        )
        reasons.append(current_reasons)
        matched_values.append(matched)
    result["eligibility_status"] = statuses
    result["exclusion_reasons"] = reasons
    result["matched_fpds_sbir_sttr_ueis"] = matched_values
    return result


def exclude_phase_ii_awardees(
    eligibility: pd.DataFrame,
    phase_ii_awards: pd.DataFrame,
) -> pd.DataFrame:
    """Confirm any candidate intersecting the provenance-verified Phase II UEI frame."""

    _require_columns(
        eligibility,
        ("eligibility_status", "exclusion_reasons", "candidate_ueis"),
        label="eligibility table",
    )
    _require_columns(phase_ii_awards, ("recipient_uei",), label="Phase II award frame")
    phase_ii_ueis = {
        uei for value in phase_ii_awards["recipient_uei"] if (uei := normalize_uei(value))
    }
    result = eligibility.copy()
    matched_values: list[tuple[str, ...]] = []
    statuses: list[str] = []
    reasons: list[tuple[str, ...]] = []
    for row in result.itertuples(index=False):
        matched = tuple(
            sorted(
                {
                    uei
                    for value in _values(row.candidate_ueis)
                    if (uei := normalize_uei(value)) and uei in phase_ii_ueis
                }
            )
        )
        current_reasons = tuple(_text(value) for value in _values(row.exclusion_reasons))
        if matched and "phase_ii_uei_intersection" not in current_reasons:
            current_reasons = (*current_reasons, "phase_ii_uei_intersection")
        statuses.append(
            EligibilityStatus.CONFIRMED_SBIR.value if matched else _text(row.eligibility_status)
        )
        reasons.append(current_reasons)
        matched_values.append(matched)
    result["eligibility_status"] = statuses
    result["exclusion_reasons"] = reasons
    result["matched_phase_ii_ueis"] = matched_values
    return result


def summarize_sam_eligibility(eligibility: pd.DataFrame) -> pd.DataFrame:
    """Return all three frozen statuses, including zero-count categories."""

    _require_columns(eligibility, ("eligibility_status",), label="eligibility table")
    counts = eligibility["eligibility_status"].value_counts()
    if invalid := sorted(set(counts.index) - set(_STATUS_ORDER)):
        raise IdentityRecoveryError(f"eligibility table contains invalid statuses: {invalid}")
    return pd.DataFrame(
        {
            "eligibility_status": _STATUS_ORDER,
            "candidate_firms": tuple(int(counts.get(status, 0)) for status in _STATUS_ORDER),
        }
    )


def summarize_sam_exclusion_reasons(eligibility: pd.DataFrame) -> pd.DataFrame:
    """Count every exact exclusion reason without selecting one per firm."""

    _require_columns(eligibility, ("exclusion_reasons",), label="eligibility table")
    counts = dict.fromkeys(_REASON_ORDER, 0)
    for raw_reasons in eligibility["exclusion_reasons"]:
        reasons = _values(raw_reasons)
        if invalid := sorted(set(reasons) - set(_REASON_ORDER)):
            raise IdentityRecoveryError(f"eligibility table contains invalid reasons: {invalid}")
        for reason in reasons:
            counts[reason] += 1
    return pd.DataFrame(
        {
            "exclusion_reason": _REASON_ORDER,
            "candidate_firms": tuple(counts[reason] for reason in _REASON_ORDER),
        }
    )


def sam_eligibility_gate(eligibility: pd.DataFrame) -> dict[str, int | bool]:
    """Require every screened-negative candidate to have the comparable key."""

    required = (
        "eligibility_status",
        "name_state_keys",
        "address_zip_keys",
        "sam_source_rows",
        "multiple_ueis",
        "multiple_duns",
        "multiple_cages",
    )
    _require_columns(eligibility, required, label="eligibility table")
    summarize_sam_eligibility(eligibility)
    missing_quarantine_keys = sum(
        not _values(row.name_state_keys) and not _values(row.address_zip_keys)
        for row in eligibility.itertuples(index=False)
    )
    missing_name_state_keys = eligibility["name_state_keys"].map(_values).map(len).eq(0)
    screened_negative = eligibility["eligibility_status"].eq(
        EligibilityStatus.ELIGIBLE_SCREENED_NEGATIVE.value
    )
    screened_negative_without_comparable_key = int(
        (screened_negative & missing_name_state_keys).sum()
    )
    return {
        "passed": screened_negative_without_comparable_key == 0,
        "candidate_source_rows": int(eligibility["sam_source_rows"].sum()),
        "candidate_firms": int(len(eligibility)),
        "candidate_firms_without_quarantine_key": int(missing_quarantine_keys),
        "candidate_firms_without_comparable_name_state_key": int(missing_name_state_keys.sum()),
        "screened_negative_firms_without_comparable_name_state_key": (
            screened_negative_without_comparable_key
        ),
        "candidate_firms_with_multiple_ueis": int(eligibility["multiple_ueis"].sum()),
        "candidate_firms_with_multiple_duns": int(eligibility["multiple_duns"].sum()),
        "candidate_firms_with_multiple_cages": int(eligibility["multiple_cages"].sum()),
    }


def require_reliable_sam_eligibility(eligibility: pd.DataFrame) -> None:
    """Stop before matching if a screened negative lacks the universal exact key."""

    gate = sam_eligibility_gate(eligibility)
    if not gate["passed"]:
        raise IdentityRecoveryError(
            "SAM eligibility is unreliable: "
            f"{gate['screened_negative_firms_without_comparable_name_state_key']} "
            "screened-negative candidate identity envelopes lack the exact "
            "name-plus-state key required to compare against every unresolved SBIR source row"
        )
