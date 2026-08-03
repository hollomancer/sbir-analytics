"""Phase III candidate asset factory and per-signal-class materializations.

NOTE: do NOT add ``from __future__ import annotations`` — breaks Dagster runtime context validation.
"""

import hashlib
import json
import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from sbir_etl.models.phase_iii_candidate import PhaseIIICandidate, SignalClass
from sbir_etl.models.transition_models import CompetitionType, FederalContract
from sbir_ml.transition.detection.scoring import TransitionScorer
from sbir_ml.transition.detection.ranking_features import id_xref

from .pairing import pair_filter_s1, pair_filter_s2, pair_filter_s3
from .similarity import (
    normalize_code,
    compute_text_similarity_batch,
    compute_topical_similarity,
)

try:
    from dagster import (
        AssetsDefinition,
        MetadataValue,
        OpExecutionContext,
        Output,
        asset,
    )
except Exception:  # pragma: no cover - test-only shim

    def asset(*_args: Any, **_kwargs: Any):  # type: ignore[no-redef]
        def _wrap(fn):
            return fn

        return _wrap

    class Output:  # type: ignore[no-redef]
        def __init__(self, value: Any, metadata: dict | None = None) -> None:
            self.value = value
            self.metadata = metadata or {}

    class MetadataValue:  # type: ignore[no-redef]
        @staticmethod
        def json(v: Any) -> Any:
            return v

    class OpExecutionContext:  # type: ignore[no-redef]
        pass

    AssetsDefinition = Any  # type: ignore[assignment, misc]


CANDIDATES_OUTPUT_PATH = Path("data/processed/phase_iii_candidates.parquet")
EVIDENCE_OUTPUT_PATH = Path("data/processed/phase_iii_evidence.ndjson")


# Per-signal weights; sum to 1.0 (asserted below). UEI is a pair-filter gate, not a scored signal.
WEIGHTS_RETROSPECTIVE: dict[str, float] = {
    "agency_continuity": 0.25,
    "timing_proximity": 0.15,
    "competition_type": 0.20,
    "patent_signal": 0.05,
    "cet_alignment": 0.15,
    "text_similarity": 0.10,
    "lineage_language": 0.10,
    # Terse FPDS descriptions cannot cite identifiers; zero weight keeps the
    # RETROSPECTIVE composite — and its >=0.85 precision gate — bit-identical.
    "id_xref": 0.0,
}

HIGH_THRESHOLD_RETROSPECTIVE: float = 0.85
HIGH_THRESHOLD_DIRECTED: float = 0.75
HIGH_THRESHOLD_FOLLOWON: float = 0.60

WEIGHTS_DIRECTED: dict[str, float] = {
    "agency_continuity": 0.20,
    "timing_proximity": 0.15,
    "competition_type": 0.20,
    "patent_signal": 0.0,
    "cet_alignment": 0.0,
    "text_similarity": 0.15,
    "lineage_language": 0.20,
    # Notice cites the firm's SBIR contract/topic/tracking number —
    # near-dispositive (transition-ranker fusion ladder, 0.779 -> 0.795).
    "id_xref": 0.10,
}
WEIGHTS_FOLLOWON: dict[str, float] = {
    "agency_continuity": 0.20,
    "timing_proximity": 0.15,
    "competition_type": 0.05,
    "patent_signal": 0.0,
    "cet_alignment": 0.15,
    "text_similarity": 0.40,
    "lineage_language": 0.0,
    "id_xref": 0.05,
}


_REQUIRED_WEIGHT_KEYS: frozenset[str] = frozenset(
    {
        "agency_continuity",
        "timing_proximity",
        "competition_type",
        "patent_signal",
        "cet_alignment",
        "text_similarity",
        "lineage_language",
        "id_xref",
    }
)


def _validate_weights(name: str, weights: dict[str, float]) -> None:
    missing = _REQUIRED_WEIGHT_KEYS - weights.keys()
    if missing:
        raise ValueError(f"{name} missing required weight keys: {sorted(missing)}")
    extra = set(weights) - _REQUIRED_WEIGHT_KEYS
    if extra:
        raise ValueError(f"{name} has unexpected weight keys: {sorted(extra)}")
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"{name} weights must sum to 1.0, got {total!r}")


# Module-level guard — fail fast at import if the constants drift.
_validate_weights("WEIGHTS_RETROSPECTIVE", WEIGHTS_RETROSPECTIVE)
_validate_weights("WEIGHTS_DIRECTED", WEIGHTS_DIRECTED)
_validate_weights("WEIGHTS_FOLLOWON", WEIGHTS_FOLLOWON)


def _scorer_config(weights: dict[str, float]) -> dict[str, Any]:
    """Build a TransitionScorer config dict from a flat weight mapping."""

    return {
        "base_score": 0.0,
        "scoring": {
            "agency_continuity": {
                "enabled": True,
                "weight": weights["agency_continuity"],
                "same_agency_bonus": 1.0,
                "cross_service_bonus": 0.5,
                "different_dept_bonus": 0.0,
            },
            "timing_proximity": {
                "enabled": True,
                "weight": weights["timing_proximity"],
                # [0, 730] days = full credit; [731, 1825] = half credit; beyond = none.
                "windows": [
                    {"range": [0, 730], "score": 1.0},
                    {"range": [731, 1825], "score": 0.5},
                ],
                "beyond_window_penalty": 0.0,
            },
            "competition_type": {
                "enabled": True,
                "weight": weights["competition_type"],
                "sole_source_bonus": 1.0,
                "limited_competition_bonus": 0.5,
                "full_and_open_bonus": 0.0,
            },
            "patent_signal": {
                "enabled": True,
                "weight": weights["patent_signal"],
                "has_patent_bonus": 0.5,
                "patent_pre_contract_bonus": 0.3,
                "patent_topic_match_bonus": 0.2,
            },
            "cet_alignment": {
                "enabled": True,
                "weight": weights["cet_alignment"],
                "same_cet_area_bonus": 1.0,
            },
            "text_similarity": {
                "enabled": True,
                "weight": weights["text_similarity"],
            },
            "lineage_language": {
                "enabled": True,
                "weight": weights["lineage_language"],
            },
        },
    }


_COMPETITION_CODE_MAP: dict[str, CompetitionType] = {
    "A": CompetitionType.FULL_AND_OPEN,
    "B": CompetitionType.LIMITED,
    "C": CompetitionType.FULL_AND_OPEN,
    "D": CompetitionType.LIMITED,
    "E": CompetitionType.LIMITED,
    "F": CompetitionType.LIMITED,
    "G": CompetitionType.SOLE_SOURCE,
}


def _coerce_competition_type(value: Any) -> CompetitionType | None:
    if value is None:
        return None
    if isinstance(value, CompetitionType):
        return value
    s = str(value).strip().upper()
    if not s:
        return None
    if s in _COMPETITION_CODE_MAP:
        return _COMPETITION_CODE_MAP[s]
    if s in {"U", "S"}:
        return CompetitionType.SOLE_SOURCE
    if s == "P":
        return CompetitionType.LIMITED
    if s in {"O", "K", "R"}:
        return CompetitionType.FULL_AND_OPEN
    if "SOLE" in s:
        return CompetitionType.SOLE_SOURCE
    if "FULL AND OPEN" in s:
        return CompetitionType.FULL_AND_OPEN
    if "LIMITED" in s or "SET ASIDE" in s or "SET-ASIDE" in s:
        return CompetitionType.LIMITED
    return CompetitionType.OTHER


def _to_date(value: Any):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        ts = pd.to_datetime(value, errors="coerce")
    except Exception:
        return None
    if pd.isna(ts):
        return None
    return ts.date()


def _candidate_id(signal_class: SignalClass, prior_identity: str, target_id: str) -> str:
    # Content hash for a short deterministic id, not a security primitive:
    # usedforsecurity=False states that so the digest choice is not read as one.
    h = hashlib.sha1(  # noqa: S324
        f"{signal_class.value}|{prior_identity}|{target_id}".encode(), usedforsecurity=False
    )
    return f"{signal_class.value}-{h.hexdigest()[:16]}"


def _row_to_federal_contract(row: pd.Series) -> FederalContract:
    return FederalContract(
        contract_id=str(row.get("target_id") or uuid.uuid4().hex),
        agency=row.get("target_agency") if pd.notna(row.get("target_agency")) else None,
        sub_agency=row.get("target_sub_agency") if pd.notna(row.get("target_sub_agency")) else None,
        # target_action_date IS the contract's transaction action_date — carry it in the
        # action_date field (the scorer reads action_date, falling back to start_date).
        action_date=_to_date(row.get("target_action_date")),
        obligation_amount=float(row.get("target_obligated_amount"))  # type: ignore[arg-type]
        if pd.notna(row.get("target_obligated_amount"))
        else None,
        competition_type=_coerce_competition_type(row.get("target_competition_type")),
        description=row.get("target_description")
        if pd.notna(row.get("target_description"))
        else None,
    )


def _row_to_award_data(row: pd.Series) -> dict[str, Any]:
    return {
        "agency": row.get("prior_agency") if pd.notna(row.get("prior_agency")) else None,
        "department": row.get("prior_sub_agency")
        if pd.notna(row.get("prior_sub_agency"))
        else None,
        "completion_date": _to_date(row.get("prior_period_of_performance_end")),
    }


def _row_to_cet_data(row: pd.Series) -> dict[str, Any] | None:
    prior_cet = _str_or_none(row.get("prior_cet"))
    target_cet = _str_or_none(row.get("target_cet"))
    if prior_cet is None and target_cet is None:
        return None
    return {"award_cet": prior_cet, "contract_cet": target_cet}


def _score_pair(
    scorer: TransitionScorer,
    row: pd.Series,
    text_similarity: float | None = None,
    id_xref_weight: float = 0.0,
) -> tuple[float, dict[str, float], float]:
    """Return ``(composite_score, per_signal_subscores, topical_similarity)`` for one candidate row.

    ``text_similarity`` is the corpus-fitted TF-IDF cosine from the batch path;
    when absent it is computed for this pair alone (degenerate two-text idf).
    """

    award_data = _row_to_award_data(row)
    contract = _row_to_federal_contract(row)
    cet_data = _row_to_cet_data(row)

    agency = scorer.score_agency_continuity(award_data, contract)
    timing = scorer.score_timing_proximity(award_data, contract)
    competition = scorer.score_competition_type(contract)
    patent = scorer.score_patent_signal(None)
    cet = scorer.score_cet_alignment(cet_data)

    prior = {
        "naics_code": row.get("prior_naics_code"),
        "psc_code": row.get("prior_psc_code"),
        "title": row.get("prior_title"),
        "abstract": row.get("prior_abstract"),
    }
    target = {
        "naics_code": row.get("target_naics_code"),
        "psc_code": row.get("target_psc_code"),
        "description": row.get("target_description"),
    }
    topical = compute_topical_similarity(prior, target, text_similarity=text_similarity)
    text_score = scorer.score_text_similarity(topical)

    description = row.get("target_description")
    desc_str = (
        str(description)
        if description is not None and not (isinstance(description, float) and pd.isna(description))
        else None
    )
    lineage_score = scorer.score_lineage_language(desc_str)

    subscores = {
        "agency_continuity_score": float(agency.agency_score),
        "timing_proximity_score": float(timing.timing_score),
        "competition_type_score": float(competition.competition_score),
        "patent_signal_score": float(patent.patent_score),
        "cet_alignment_score": float(cet.cet_alignment_score),
        "text_similarity_score": float(text_score),
        "lineage_language_score": float(lineage_score),
        # Notice cites the firm's SBIR identifier — near-dispositive when present.
        "id_xref_score": float(id_xref_weight * id_xref(desc_str, [row.get("prior_award_id")])),
    }
    composite = min(1.0, sum(subscores.values()))
    return composite, subscores, float(topical)


def _matched_keys(row: pd.Series) -> list[str]:
    """Keys the pair actually agrees on — never assumed.

    S2's lineage fallback and every S3 code/text pair are made without a
    recipient-identity match, so ``recipient_uei`` may not be among them.
    """

    keys: list[str] = []
    prior_uei = _str_or_none(row.get("prior_recipient_uei"))
    target_uei = _str_or_none(row.get("target_recipient_uei"))
    if prior_uei and target_uei and prior_uei.upper() == target_uei.upper():
        keys.append("recipient_uei")
    for name, prior_field, target_field in (
        ("naics_code", "prior_naics_code", "target_naics_code"),
        ("psc_code", "prior_psc_code", "target_psc_code"),
    ):
        prior_code = normalize_code(row.get(prior_field))
        target_code = normalize_code(row.get(target_field))
        if prior_code and prior_code == target_code:
            keys.append(name)
    if level := _str_or_none(row.get("agency_match_level")):
        keys.append(level)
    return keys


def _evidence_bundle(
    candidate: PhaseIIICandidate,
    row: pd.Series,
    topical_similarity: float,
) -> dict[str, Any]:
    """Build the per-candidate evidence record matching the ``transitions_evidence.ndjson`` key shape."""

    return {
        "candidate_id": candidate.candidate_id,
        "signal_class": candidate.signal_class.value,
        "award_id": candidate.prior_award_id,
        "award_key": candidate.prior_award_key,
        "contract_id": candidate.target_id,
        "target_type": candidate.target_type,
        "score": candidate.candidate_score,
        "is_high_confidence": candidate.is_high_confidence,
        "method": "phase_iii_candidate_scorer",
        "matched_keys": _matched_keys(row),
        "dates": {
            "prior_period_of_performance_end": _iso_or_none(
                row.get("prior_period_of_performance_end")
            ),
            "target_action_date": _iso_or_none(row.get("target_action_date")),
        },
        "amounts": {
            "target_obligated_amount": _float_or_none(row.get("target_obligated_amount")),
        },
        "agencies": {
            "prior_agency": _str_or_none(row.get("prior_agency")),
            "prior_sub_agency": _str_or_none(row.get("prior_sub_agency")),
            "prior_office": _str_or_none(row.get("prior_office")),
            "target_agency": _str_or_none(row.get("target_agency")),
            "target_sub_agency": _str_or_none(row.get("target_sub_agency")),
            "target_office": _str_or_none(row.get("target_office")),
            "agency_match_level": _str_or_none(row.get("agency_match_level")),
        },
        "subscores": {
            "agency_continuity": candidate.agency_continuity_score,
            "timing_proximity": candidate.timing_proximity_score,
            "competition_type": candidate.competition_type_score,
            "patent_signal": candidate.patent_signal_score,
            "cet_alignment": candidate.cet_alignment_score,
            "text_similarity": candidate.text_similarity_score,
            "lineage_language": candidate.lineage_language_score,
            "id_xref": candidate.id_xref_score,
        },
        "topical_similarity": float(topical_similarity),
        "target_description_excerpt": _excerpt(row.get("target_description")),
        "generated_at": candidate.generated_at.isoformat(),
    }


def _excerpt(value: Any, max_chars: int = 400) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value)
    return s if len(s) <= max_chars else s[:max_chars] + "..."


def _iso_or_none(value: Any) -> str | None:
    d = _to_date(value)
    return d.isoformat() if d else None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    s = str(value).strip()
    return None if not s or s.upper() in {"NAN", "NAT", "NONE", "NULL", "<NA>", r"\N"} else s


def _float_or_none(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _candidate_dataframe(candidates: list[PhaseIIICandidate]) -> pd.DataFrame:
    if not candidates:
        return pd.DataFrame(
            columns=[
                "candidate_id",
                "signal_class",
                "prior_award_id",
                "prior_award_key",
                "target_type",
                "target_id",
                "candidate_score",
                "is_high_confidence",
                "evidence_ref",
                "agency_continuity_score",
                "timing_proximity_score",
                "competition_type_score",
                "patent_signal_score",
                "cet_alignment_score",
                "text_similarity_score",
                "lineage_language_score",
                "id_xref_score",
                "generated_at",
            ]
        )
    rows = [c.model_dump(mode="json") for c in candidates]
    df = pd.DataFrame(rows)
    return df


def score_candidate_pairs(
    pairs: pd.DataFrame,
    *,
    signal_class: SignalClass,
    weights: dict[str, float],
    high_threshold: float,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Score pre-filtered pairs without requiring Dagster."""

    _validate_weights(signal_class.value, weights)
    scorer = TransitionScorer(_scorer_config(weights))
    target_type = "fpds_contract" if signal_class is SignalClass.RETROSPECTIVE else "opportunity"
    candidates: list[PhaseIIICandidate] = []
    evidence_records: list[dict[str, Any]] = []
    # Corpus-fitted TF-IDF over the whole frame — idf reflects this run, not one pair.
    text_similarities = compute_text_similarity_batch(pairs)
    for position, (_, row) in enumerate(pairs.iterrows()):
        composite, subscores, topical = _score_pair(
            scorer,
            row,
            text_similarity=text_similarities[position],
            id_xref_weight=weights["id_xref"],
        )
        prior_id = _str_or_none(row.get("prior_award_id"))
        prior_key = _str_or_none(row.get("prior_award_key"))
        target_id = _str_or_none(row.get("target_id"))
        if not prior_id or not target_id:
            continue
        prior_identity = f"key:{prior_key}" if prior_key else f"id:{prior_id}"
        cid = _candidate_id(signal_class, prior_identity, target_id)
        candidate = PhaseIIICandidate(
            candidate_id=cid,
            signal_class=signal_class,
            prior_award_id=prior_id,
            prior_award_key=prior_key,
            target_type=target_type,  # type: ignore[arg-type]
            target_id=target_id,
            candidate_score=composite,
            is_high_confidence=composite >= high_threshold,
            evidence_ref=cid,
            **subscores,
            generated_at=datetime.now(UTC),
        )
        candidates.append(candidate)
        evidence_records.append(_evidence_bundle(candidate, row, topical))
    return _candidate_dataframe(candidates), evidence_records


def _default_retrospective_loader(_context: Any) -> pd.DataFrame:
    """Read and normalize the extractor's persisted contract schema.

    Older ``FederalContract.model_dump()`` parquets retained the canonical
    USAspending award id only in ``metadata.award_id``. Promote that value
    rather than treating the bare-PIID ``contract_id`` as unique. Element 10Q
    is likewise promoted when a legacy producer retained it in metadata; old
    extracts without it receive an explicit null ``research`` column.
    """

    contracts_path = Path("data/transition/contracts_ingestion.parquet")
    if not contracts_path.exists():
        contracts_path = Path("data/processed/contracts_ingestion.parquet")
    if not contracts_path.exists():
        return pd.DataFrame()
    try:
        contracts = pd.read_parquet(contracts_path)
        metadata = contracts.get("metadata", pd.Series([None] * len(contracts)))

        def _metadata_field(value: object, field: str) -> object:
            return value.get(field) if isinstance(value, dict) else None

        metadata_award_id = metadata.map(lambda value: _metadata_field(value, "award_id"))
        metadata_research = metadata.map(lambda value: _metadata_field(value, "research"))

        if "generated_unique_award_id" not in contracts.columns:
            contracts["generated_unique_award_id"] = metadata_award_id
        else:
            missing_id = contracts["generated_unique_award_id"].isna() | contracts[
                "generated_unique_award_id"
            ].astype(str).str.strip().eq("")
            contracts.loc[missing_id, "generated_unique_award_id"] = metadata_award_id[missing_id]

        if "research" not in contracts.columns:
            contracts["research"] = metadata_research
        else:
            missing_research = contracts["research"].isna() | contracts["research"].astype(
                str
            ).str.strip().eq("")
            contracts.loc[missing_research, "research"] = metadata_research[missing_research]
        return contracts
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to read contracts parquet at {}: {}", contracts_path, exc)
        return pd.DataFrame()


DEFAULT_PRIOR_DETAIL_PATH = Path("data/processed/enriched_sbir_awards.parquet")

# Fields the pair filters and scorer need that ``validated_phase_ii_awards`` does
# not carry: without them S3's topical gate scores zero and S2's missing-code
# fallback pairs generic lineage notices to every same-agency prior.
_PRIOR_DETAIL_FIELDS: dict[str, tuple[str, ...]] = {
    "title": ("award_title", "title"),
    "abstract": ("abstract", "award_abstract"),
    "naics_code": ("naics_code", "naics"),
    "psc_code": ("psc_code", "product_or_service_code"),
    "office": ("office", "awarding_office_name", "branch"),
    "cet": ("cet", "cet_category"),
}


def enrich_prior_awards(priors: pd.DataFrame, detail: pd.DataFrame) -> pd.DataFrame:
    """Join descriptive fields by award grain, with a guarded public-id fallback.

    Left join — priors without a detail row keep their (null) values, and the
    frame's row grain is unchanged. Existing non-null values always win.
    """

    if priors.empty or detail.empty or "award_id" not in priors or "award_id" not in detail:
        return priors

    def _normalized(frame: pd.DataFrame, column: str) -> pd.Series:
        values = (
            frame.get(column, pd.Series(pd.NA, index=frame.index, dtype="string"))
            .astype("string")
            .str.strip()
            .str.upper()
        )
        return values.mask(values.isin(["", "NAN", "NAT", "NONE", "<NA>", r"\N"]))

    prior_ids = _normalized(priors, "award_id")
    detail_ids = _normalized(detail, "award_id")
    prior_keys = _normalized(priors, "award_key")
    detail_keys = _normalized(detail, "award_key")
    shared_keys = set(prior_keys.dropna()) & set(detail_keys.dropna())
    safe_public_ids = set(prior_ids.value_counts().loc[lambda count: count == 1].index) & set(
        detail_ids.value_counts().loc[lambda count: count == 1].index
    )
    prior_safe = prior_ids.isin(safe_public_ids)
    detail_safe = detail_ids.isin(safe_public_ids)
    rollout_keys = pd.DataFrame(
        {
            "prior": pd.Series(
                prior_keys.loc[prior_safe].array,
                index=prior_ids.loc[prior_safe].array,
            ),
            "detail": pd.Series(
                detail_keys.loc[detail_safe].array,
                index=detail_ids.loc[detail_safe].array,
            ),
        }
    )
    conflicts = (
        rollout_keys["prior"].notna()
        & rollout_keys["detail"].notna()
        & rollout_keys["prior"].ne(rollout_keys["detail"])
    )
    conflicting_public_ids = set(rollout_keys.index[conflicts])
    if conflicting_public_ids:
        logger.warning(
            "Skipping descriptive enrichment for {} conflicting award keys",
            len(conflicting_public_ids),
        )
        safe_public_ids -= conflicting_public_ids

    def _identity(keys: pd.Series, public_ids: pd.Series) -> pd.Series:
        identities = pd.Series(pd.NA, index=public_ids.index, dtype="string")
        keyed = keys.isin(shared_keys)
        identities.loc[keyed] = "key:" + keys.loc[keyed]
        public = ~keyed & public_ids.isin(safe_public_ids)
        identities.loc[public] = "id:" + public_ids.loc[public]
        return identities

    projected = pd.DataFrame({"_award_identity": _identity(detail_keys, detail_ids)})
    for canonical, sources in _PRIOR_DETAIL_FIELDS.items():
        for source in sources:
            if source in detail.columns:
                projected[canonical] = detail[source]
                break
    projected = projected.loc[projected["_award_identity"].notna()]
    ambiguous = projected["_award_identity"].duplicated(keep=False)
    if ambiguous.any():
        logger.warning(
            "Skipping descriptive enrichment for {} ambiguous award identities",
            projected.loc[ambiguous, "_award_identity"].nunique(),
        )
        projected = projected.loc[~ambiguous]
    if len(projected.columns) == 1:
        return priors

    out = priors.copy()
    merged = out.assign(_award_identity=_identity(prior_keys, prior_ids)).merge(
        projected,
        on="_award_identity",
        how="left",
        suffixes=("", "_detail"),
    )
    for canonical in projected.columns:
        if canonical == "_award_identity":
            continue
        detail_column = f"{canonical}_detail" if f"{canonical}_detail" in merged else canonical
        if canonical in out.columns and detail_column != canonical:
            merged[canonical] = merged[canonical].combine_first(merged[detail_column])
        elif detail_column != canonical:
            merged[canonical] = merged[detail_column]
    drop = [column for column in merged.columns if column.endswith("_detail")]
    return merged.drop(columns=[*drop, "_award_identity"])


def _default_prior_detail_loader(_context: Any) -> pd.DataFrame:
    if not DEFAULT_PRIOR_DETAIL_PATH.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(DEFAULT_PRIOR_DETAIL_PATH)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Failed to read prior award detail at {}: {}", DEFAULT_PRIOR_DETAIL_PATH, exc
        )
        return pd.DataFrame()


def _default_opportunity_loader(_context: Any) -> pd.DataFrame:
    path = Path("data/raw/sam_gov_opportunities/opportunities.parquet")
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to read SAM.gov opportunities at {}: {}", path, exc)
        return pd.DataFrame()


def build_candidate_asset(
    *,
    signal_class: SignalClass,
    pair_filter: Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame],
    weights: dict[str, float],
    high_threshold: float,
    asset_name: str,
    target_loader: Callable[[Any], pd.DataFrame],
    prior_detail_loader: Callable[[Any], pd.DataFrame] = _default_prior_detail_loader,
):
    """Return a Dagster asset function for one signal-class materialization."""

    _validate_weights(asset_name, weights)

    @asset(
        name=asset_name,
        group_name="phase_iii_candidates",
        compute_kind="pandas",
        description=(
            f"Phase III candidate surfacing — {signal_class.value}. Emits scored "
            "(prior_award, target) candidate rows into "
            "data/processed/phase_iii_candidates.parquet and per-candidate "
            "evidence bundles into data/processed/phase_iii_evidence.ndjson."
        ),
    )
    def _candidate_asset(
        context=None,
        validated_phase_ii_awards: pd.DataFrame | None = None,
    ):
        priors = (
            validated_phase_ii_awards if validated_phase_ii_awards is not None else pd.DataFrame()
        )
        targets = target_loader(context)
        log = getattr(context, "log", logger) if context is not None else logger

        # The upstream Phase II contract carries identity and dates only; the
        # topical signals need the descriptive fields joined in here.
        priors = enrich_prior_awards(priors, prior_detail_loader(context))
        pairs = pair_filter(priors, targets)
        df, evidence_records = score_candidate_pairs(
            pairs,
            signal_class=signal_class,
            weights=weights,
            high_threshold=high_threshold,
        )
        _write_outputs(df, evidence_records, signal_class)

        high_count = int(df["is_high_confidence"].sum()) if not df.empty else 0
        log.info(
            "phase_iii_candidates materialized",
            extra={
                "signal_class": signal_class.value,
                "rows": len(df),
                "high_confidence_rows": high_count,
            },
        )
        metadata: dict[str, Any] = {
            "rows": int(len(df)),
            "high_confidence_rows": high_count,
            "candidates_path": str(candidates_path_for(signal_class)),
            "evidence_path": str(evidence_path_for(signal_class)),
            "signal_class": signal_class.value,
            "high_threshold": float(high_threshold),
        }
        return Output(df, metadata=metadata)

    return _candidate_asset


def candidates_path_for(signal_class: SignalClass) -> Path:
    """Per-signal-class candidate parquet — each asset owns exactly one."""

    return CANDIDATES_OUTPUT_PATH.with_name(
        f"{CANDIDATES_OUTPUT_PATH.stem}_{signal_class.value}{CANDIDATES_OUTPUT_PATH.suffix}"
    )


def evidence_path_for(signal_class: SignalClass) -> Path:
    """Per-signal-class evidence NDJSON — each asset owns exactly one."""

    return EVIDENCE_OUTPUT_PATH.with_name(
        f"{EVIDENCE_OUTPUT_PATH.stem}_{signal_class.value}{EVIDENCE_OUTPUT_PATH.suffix}"
    )


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    frame.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _write_outputs(
    new_rows: pd.DataFrame,
    evidence_records: list[dict[str, Any]],
    signal_class: SignalClass,
) -> None:
    """Replace this signal class's own outputs.

    Each signal-class asset writes only the files it owns, so the three
    materializations — which have no ordering dependency between them — never
    read-modify-write shared state. ``phase_iii_candidates`` combines them.
    An empty result still overwrites, so a class that now yields nothing does
    not leave its previous rows behind.
    """

    candidates_path = candidates_path_for(signal_class)
    evidence_path = evidence_path_for(signal_class)
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)

    _atomic_write_parquet(
        candidates_path, new_rows if not new_rows.empty else _candidate_dataframe([])
    )
    _atomic_write_text(
        evidence_path, "".join(json.dumps(record) + "\n" for record in evidence_records)
    )


def combine_candidate_outputs() -> pd.DataFrame:
    """Concatenate every per-class output into the shared parquet + NDJSON artifacts."""

    frames: list[pd.DataFrame] = []
    lines: list[str] = []
    for signal_class in SignalClass:
        candidates_path = candidates_path_for(signal_class)
        if candidates_path.exists():
            try:
                frames.append(pd.read_parquet(candidates_path))
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to read {}: {}", candidates_path, exc)
        evidence_path = evidence_path_for(signal_class)
        if evidence_path.exists():
            lines += [
                raw for raw in evidence_path.read_text(encoding="utf-8").splitlines() if raw.strip()
            ]

    combined = (
        pd.concat(frames, ignore_index=True, sort=False) if frames else _candidate_dataframe([])
    )
    CANDIDATES_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_parquet(CANDIDATES_OUTPUT_PATH, combined)
    _atomic_write_text(EVIDENCE_OUTPUT_PATH, "".join(line + "\n" for line in lines))
    return combined


phase_iii_retrospective_candidates = build_candidate_asset(
    signal_class=SignalClass.RETROSPECTIVE,
    pair_filter=pair_filter_s1,
    weights=WEIGHTS_RETROSPECTIVE,
    high_threshold=HIGH_THRESHOLD_RETROSPECTIVE,
    asset_name="phase_iii_retrospective_candidates",
    target_loader=_default_retrospective_loader,
)

phase_iii_directed_candidates = build_candidate_asset(
    signal_class=SignalClass.DIRECTED,
    pair_filter=pair_filter_s2,
    weights=WEIGHTS_DIRECTED,
    high_threshold=HIGH_THRESHOLD_DIRECTED,
    asset_name="phase_iii_directed_candidates",
    target_loader=_default_opportunity_loader,
)

phase_iii_followon_candidates = build_candidate_asset(
    signal_class=SignalClass.FOLLOWON,
    pair_filter=pair_filter_s3,
    weights=WEIGHTS_FOLLOWON,
    high_threshold=HIGH_THRESHOLD_FOLLOWON,
    asset_name="phase_iii_followon_candidates",
    target_loader=_default_opportunity_loader,
)


@asset(
    name="phase_iii_candidates",
    group_name="phase_iii_candidates",
    compute_kind="pandas",
    description=(
        "Combined Phase III candidate ledger. Depends on the three signal-class "
        "materializations so the shared data/processed/phase_iii_candidates.parquet "
        "and phase_iii_evidence.ndjson artifacts have exactly one writer."
    ),
)
def phase_iii_candidates(
    context=None,
    phase_iii_retrospective_candidates: pd.DataFrame | None = None,
    phase_iii_directed_candidates: pd.DataFrame | None = None,
    phase_iii_followon_candidates: pd.DataFrame | None = None,
):
    """Concatenate the per-signal-class outputs into the shared artifacts."""

    combined = combine_candidate_outputs()
    log = getattr(context, "log", logger) if context is not None else logger
    log.info("phase_iii_candidates combined", extra={"rows": len(combined)})
    return Output(
        combined,
        metadata={
            "rows": int(len(combined)),
            "candidates_path": str(CANDIDATES_OUTPUT_PATH),
            "evidence_path": str(EVIDENCE_OUTPUT_PATH),
        },
    )


__all__ = [
    "CANDIDATES_OUTPUT_PATH",
    "EVIDENCE_OUTPUT_PATH",
    "HIGH_THRESHOLD_RETROSPECTIVE",
    "HIGH_THRESHOLD_DIRECTED",
    "HIGH_THRESHOLD_FOLLOWON",
    "WEIGHTS_DIRECTED",
    "WEIGHTS_FOLLOWON",
    "WEIGHTS_RETROSPECTIVE",
    "build_candidate_asset",
    "candidates_path_for",
    "combine_candidate_outputs",
    "enrich_prior_awards",
    "evidence_path_for",
    "phase_iii_candidates",
    "phase_iii_retrospective_candidates",
    "phase_iii_directed_candidates",
    "phase_iii_followon_candidates",
    "score_candidate_pairs",
]
