"""Shared UEI pair construction and Phase III candidate filters.

Epistemic tier: pipelines. Pair construction and coded-status filters are
deterministic data movement with no scoring — the evidence-tier census
imports this boundary, so it must never gain inference.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from sbir_etl.utils.award_identity import award_key_series


EPISTEMIC_TIER = "pipelines"

# FPDS Element 10Q codes that mark a contract as already-coded Phase III.
# Duplicated intentionally — avoids cross-package import for a five-element set.
_PHASE_III_RESEARCH_CODES = frozenset({"SR3", "ST3"})

# Tokens we accept as evidence that ``sbir_phase`` already says "Phase III".
_PHASE_III_LABELS = frozenset({"PHASE III", "III", "3", "PHASE 3"})

# If neither column exists, the already-coded exclusion cannot run safely.
_CODED_STATUS_COLUMNS: tuple[str, ...] = ("research", "sbir_phase")


PAIR_S1_COLUMNS: list[str] = [
    "prior_award_id",
    "prior_award_key",
    "prior_recipient_uei",
    "prior_agency",
    "prior_sub_agency",
    "prior_office",
    "prior_naics_code",
    "prior_psc_code",
    "prior_title",
    "prior_abstract",
    "prior_award_date",
    "prior_period_of_performance_end",
    "prior_cet",
    "target_id",
    "target_recipient_uei",
    "target_agency",
    "target_sub_agency",
    "target_office",
    "target_naics_code",
    "target_psc_code",
    "target_description",
    "target_action_date",
    "target_competition_type",
    "target_obligated_amount",
    "agency_match_level",
]

# Transaction-grain schema shared by the weighted retrospective path and the
# label-free census. ``pair_filter_s1`` projects back to the declared
# ``PAIR_S1_COLUMNS`` contract after its internal grain checks.
PAIR_COLUMNS: list[str] = [
    *PAIR_S1_COLUMNS[:-1],
    "target_research",
    "target_sbir_phase",
    "target_transaction_id",
    "target_contract_key",
    "agency_match_level",
]

# ``str()`` of a pandas null renders as text — treat those spellings as missing.
_MISSING_TOKENS = frozenset({"", "NAN", "NAT", "NONE", "NULL", "<NA>"})


def _normalize(value: object) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    s = str(value).strip().upper()
    return "" if s in _MISSING_TOKENS or s == r"\N" else s


def _prior_identity(df: pd.DataFrame) -> pd.Series:
    """Internal grain key without promoting a legacy public id to ``award_key``."""

    public_ids = df.get("prior_award_id", pd.Series(None, index=df.index)).map(_normalize)
    award_keys = df.get("prior_award_key", pd.Series(None, index=df.index)).map(_normalize)
    return ("key:" + award_keys).where(award_keys.ne(""), "id:" + public_ids)


def _is_phase_iii_already_coded(row: pd.Series) -> bool:
    """True iff a contract row already carries explicit Phase III coding."""

    research = row.get("target_research") if "target_research" in row else row.get("research")
    if isinstance(research, str) and research.strip().upper() in _PHASE_III_RESEARCH_CODES:
        return True

    sbir_phase = (
        row.get("target_sbir_phase") if "target_sbir_phase" in row else row.get("sbir_phase")
    )
    if sbir_phase is not None:
        label = _normalize(sbir_phase)
        if label in _PHASE_III_LABELS:
            return True
    return False


def _prepare_priors(prior_awards: pd.DataFrame) -> pd.DataFrame:
    """Project & rename the prior-award frame to canonical ``prior_*`` columns."""

    if prior_awards.empty:
        return pd.DataFrame(columns=[c for c in PAIR_S1_COLUMNS if c.startswith("prior_")])

    df = prior_awards.copy()

    def _col(name: str, default: object = None) -> pd.Series:
        if name in df.columns:
            return df[name]
        return pd.Series([default] * len(df), index=df.index)

    award_ids = _col("award_id")
    award_keys = _col("award_key")
    award_keys = award_keys.where(award_keys.map(_normalize).ne(""), None)
    out = pd.DataFrame(
        {
            "prior_award_id": award_ids,
            # Preserve absence on legacy inputs. Internal pairing can use the
            # public id, but downstream reports must not mistake it for a true key.
            "prior_award_key": award_keys,
            "prior_recipient_uei": _col("recipient_uei"),
            "prior_agency": _col("agency"),
            "prior_sub_agency": _col("sub_agency"),
            "prior_office": _col("office"),
            "prior_naics_code": _col("naics_code"),
            "prior_psc_code": _col("psc_code"),
            "prior_title": _col("title"),
            "prior_abstract": _col("abstract"),
            "prior_award_date": _col("award_date"),
            "prior_period_of_performance_end": _col("period_of_performance_end"),
            "prior_cet": _col("cet"),
        }
    )
    # UEI is the join gate for S1 and the S2 exact path only — those apply it on
    # their own join keys. Do not drop UEI-null priors here: S3 pairs on
    # NAICS/PSC/text, so a rich prior without a UEI is still a valid follow-on prior.
    return out.reset_index(drop=True)


def _metadata_field(df: pd.DataFrame, *names: str) -> pd.Series:
    """Return the first nonblank metadata value per row for ``names``."""

    if "metadata" not in df.columns:
        return pd.Series([None] * len(df), index=df.index, dtype="object")

    def _get(value: object) -> object:
        if not isinstance(value, Mapping):
            return None
        for name in names:
            candidate = value.get(name)
            if _normalize(candidate):
                return candidate
        return None

    return df["metadata"].map(_get)


def _coalesce_fields(
    df: pd.DataFrame,
    *fields: str,
    fallback: pd.Series | None = None,
) -> pd.Series:
    """Coalesce fields per row, treating blank/null-like strings as absent."""

    result = pd.Series([None] * len(df), index=df.index, dtype="object")
    for field in fields:
        if field not in df.columns:
            continue
        source = df[field]
        take = result.map(_normalize).eq("") & source.map(_normalize).ne("")
        result.loc[take] = source.loc[take]
    if fallback is not None:
        take = result.map(_normalize).eq("") & fallback.map(_normalize).ne("")
        result.loc[take] = fallback.loc[take]
    return result


def _prepare_contract_transactions(contracts: pd.DataFrame) -> pd.DataFrame:
    """Project source transactions without applying a census or scoring gate."""

    if contracts.empty:
        return pd.DataFrame(columns=[c for c in PAIR_COLUMNS if c.startswith("target_")])

    df = contracts.copy()
    if not any(column in df.columns for column in _CODED_STATUS_COLUMNS):
        raise ValueError(
            "contracts frame carries no Phase III coding column "
            f"(need one of {_CODED_STATUS_COLUMNS}); the already-coded exclusion cannot run"
        )

    # The USAspending-generated award key is preferred; the shared identity
    # helper fails closed on partial or ambiguous identifiers and otherwise
    # derives the same agency + parent-IDV + PIID key used by legacy S1.
    contract_keys = award_key_series(df)

    def _pick(*names: str) -> pd.Series:
        for name in names:
            if name in df.columns:
                return df[name]
        return pd.Series([None] * len(df), index=df.index)

    metadata_transaction_id = _metadata_field(df, "transaction_unique_id", "transaction_id")
    out = pd.DataFrame(
        {
            # Preserve the historical transaction-facing identifier here. S1
            # restores its award-grain target_id after its legacy collapse.
            "target_id": _pick("contract_id", "piid", "generated_unique_award_id"),
            "target_recipient_uei": _pick("vendor_uei", "recipient_uei", "uei"),
            "target_agency": _pick(
                "awarding_toptier_agency_name",
                "awarding_agency_name",
                "agency",
                "awarding_agency",
            ),
            "target_sub_agency": _pick(
                "awarding_subtier_agency_name",
                "awarding_sub_tier_agency_name",
                "sub_agency",
            ),
            "target_office": _pick("awarding_office_name", "office"),
            "target_naics_code": _pick("naics_code", "naics"),
            "target_psc_code": _pick("psc_code", "product_or_service_code"),
            "target_description": _pick(
                "transaction_description", "description", "award_description"
            ),
            "target_action_date": _pick("action_date", "award_date"),
            "target_competition_type": _pick(
                "extent_competed", "competition_type", "type_of_set_aside"
            ),
            "target_obligated_amount": _pick(
                "federal_action_obligation", "obligated_amount", "obligation_amount"
            ),
            # ``research`` is the authoritative FPDS Element 10Q field. The
            # optional phase label remains supplemental rather than replacing it.
            "target_research": _pick("research"),
            "target_sbir_phase": _pick("sbir_phase"),
            "target_transaction_id": _coalesce_fields(
                df,
                "transaction_unique_id",
                "transaction_id",
                fallback=metadata_transaction_id,
            ),
            "target_contract_key": contract_keys,
        }
    )
    return out.reset_index(drop=True)


def _legacy_s1_target_transactions(transactions: pd.DataFrame) -> pd.DataFrame:
    """Apply current S1's award-level coded exclusion and latest-row policy."""

    if transactions.empty:
        return transactions.copy()

    coded = transactions.apply(_is_phase_iii_already_coded, axis=1)
    award_coded = coded.groupby(transactions["target_contract_key"], sort=False).transform("any")
    eligible = transactions.loc[~award_coded].copy()
    if eligible.empty:
        return eligible

    # Keep the latest transaction exactly as the legacy source-grain helper
    # does. This is row selection, not financial aggregation.
    sort_date = pd.to_datetime(eligible["target_action_date"], errors="coerce", utc=True)
    eligible = (
        eligible.assign(_award_sort_date=sort_date)
        .sort_values("_award_sort_date", kind="mergesort", na_position="first")
        .drop_duplicates("target_contract_key", keep="last")
        .drop(columns="_award_sort_date")
    )
    eligible["target_id"] = eligible["target_contract_key"]
    valid_uei = eligible["target_recipient_uei"].map(_normalize).ne("")
    return eligible.loc[valid_uei].reset_index(drop=True)


def _legacy_s1_targets(transactions: pd.DataFrame) -> pd.DataFrame:
    target_columns = [c for c in PAIR_S1_COLUMNS if c.startswith("target_")]
    eligible = _legacy_s1_target_transactions(transactions)
    return eligible.loc[:, target_columns].reset_index(drop=True)


def _target_transaction_signatures(frame: pd.DataFrame) -> pd.Series:
    """Build internal row signatures for matching the legacy-selected transaction."""

    columns = [
        column for column in PAIR_COLUMNS if column.startswith("target_") and column != "target_id"
    ]
    return frame.loc[:, columns].apply(
        lambda row: tuple(_normalize(value) for value in row),
        axis=1,
    )


def _prepare_contracts(contracts: pd.DataFrame) -> pd.DataFrame:
    """Prepare the legacy S1 award-grain target frame.

    Kept as a compatibility seam for callers and tests; the neutral census
    boundary is :func:`build_uei_pairs` below.
    """

    return _legacy_s1_targets(_prepare_contract_transactions(contracts))


def build_uei_pairs(
    prior_awards: pd.DataFrame,
    contracts: pd.DataFrame,
    *,
    columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Build normalized, nonblank exact-UEI pairs at target-transaction grain.

    This shared boundary applies no coded-status or agency gate. It carries the
    source transaction and award identifiers plus every field needed by either
    the label-free criteria or legacy S1. Callers may project the shared schema
    before the merge; omitting columns never changes the pair universe.
    """

    output_columns = list(PAIR_COLUMNS if columns is None else columns)
    unknown_columns = sorted(set(output_columns) - set(PAIR_COLUMNS))
    if unknown_columns or len(output_columns) != len(set(output_columns)):
        raise ValueError(
            "Requested pair columns must be unique members of PAIR_COLUMNS; "
            f"unknown={unknown_columns}"
        )

    priors = _prepare_priors(prior_awards)
    targets = _prepare_contract_transactions(contracts)
    if priors.empty or targets.empty:
        return pd.DataFrame(columns=output_columns)

    priors = priors.assign(_uei=priors["prior_recipient_uei"].map(_normalize))
    targets = targets.assign(_uei=targets["target_recipient_uei"].map(_normalize))
    priors = priors.loc[priors["_uei"] != ""].copy()
    targets = targets.loc[targets["_uei"] != ""].copy()
    if priors.empty or targets.empty:
        return pd.DataFrame(columns=output_columns)

    merge_columns = set(output_columns)
    if "agency_match_level" in merge_columns:
        merge_columns.update(
            {
                "prior_agency",
                "prior_sub_agency",
                "prior_office",
                "target_agency",
                "target_sub_agency",
                "target_office",
            }
        )
    prior_columns = [
        column for column in priors.columns if column == "_uei" or column in merge_columns
    ]
    target_columns = [
        column for column in targets.columns if column == "_uei" or column in merge_columns
    ]

    merged = priors.loc[:, prior_columns].merge(
        targets.loc[:, target_columns], on="_uei", how="inner", suffixes=("", "_t")
    )
    if merged.empty:
        return pd.DataFrame(columns=output_columns)

    if "agency_match_level" in output_columns:
        levels = pd.Series(None, index=merged.index, dtype="object")
        for level, prior_column, target_column in (
            ("agency", "prior_agency", "target_agency"),
            ("sub_tier", "prior_sub_agency", "target_sub_agency"),
            ("office", "prior_office", "target_office"),
        ):
            prior_values = merged[prior_column].map(_normalize)
            target_values = merged[target_column].map(_normalize)
            matches = prior_values.ne("") & target_values.ne("") & prior_values.eq(target_values)
            levels.loc[matches] = level
        merged["agency_match_level"] = levels
    return merged.loc[:, output_columns].reset_index(drop=True)


def pair_filter_s1(
    prior_awards: pd.DataFrame,
    contracts: pd.DataFrame,
) -> pd.DataFrame:
    """S1 retrospective filter with its unchanged award-grain gates and schema."""

    pairs = build_uei_pairs(prior_awards, contracts)
    if pairs.empty:
        return pd.DataFrame(columns=PAIR_S1_COLUMNS)

    # Compute coded status and latest-transaction selection on the complete
    # contract frame, as current S1 did before dropping blank UEIs or joining.
    # The signature then selects that exact transaction from the delegated pair
    # universe without changing the census's transaction-grain representation.
    selected_targets = _legacy_s1_target_transactions(_prepare_contract_transactions(contracts))
    if selected_targets.empty:
        return pd.DataFrame(columns=PAIR_S1_COLUMNS)

    allowed = set(
        zip(
            selected_targets["target_contract_key"].map(_normalize),
            _target_transaction_signatures(selected_targets),
            strict=True,
        )
    )
    pair_keys = list(
        zip(
            pairs["target_contract_key"].map(_normalize),
            _target_transaction_signatures(pairs),
            strict=True,
        )
    )
    eligible = pairs.loc[[key in allowed for key in pair_keys]].copy()
    if eligible.empty:
        return pd.DataFrame(columns=PAIR_S1_COLUMNS)

    # The transaction-grain universe intentionally retains duplicate source
    # rows so census validation can fail on them. Legacy S1, however, emitted
    # exactly one selected row per prior × award after its grain collapse.
    eligible = eligible.assign(_prior_identity=_prior_identity(eligible)).drop_duplicates(
        ["_prior_identity", "target_contract_key"], keep="last"
    )

    target_order = {
        _normalize(key): order for order, key in enumerate(selected_targets["target_contract_key"])
    }
    eligible["target_id"] = eligible["target_contract_key"]
    eligible = eligible.loc[eligible["agency_match_level"].notna()].copy()
    if eligible.empty:
        return pd.DataFrame(columns=PAIR_S1_COLUMNS)

    eligible = eligible.assign(
        _prior_order=pd.factorize(eligible["_prior_identity"], sort=False)[0],
        _target_order=eligible["target_contract_key"].map(_normalize).map(target_order),
    ).sort_values(["_prior_order", "_target_order"], kind="mergesort")
    return eligible.loc[:, PAIR_S1_COLUMNS].reset_index(drop=True)


__all__ = [
    "PAIR_COLUMNS",
    "PAIR_S1_COLUMNS",
    "build_uei_pairs",
    "pair_filter_s1",
]
