"""Phase III candidate asset factory and per-signal-class materializations.

A single ``build_candidate_asset`` factory produces one Dagster asset per
signal class (``RETROSPECTIVE`` / ``DIRECTED`` / ``FOLLOWON``). Each
materialization writes into the same parquet
(``data/processed/phase_iii_candidates.parquet``, distinguished by the
``signal_class`` column) and the same evidence NDJSON
(``data/processed/phase_iii_evidence.ndjson``).

v1 ships only the RETROSPECTIVE materialization. The DIRECTED and FOLLOWON
classes will be wired in subsequent phases of the spec but reuse the same
factory and weight-dict pattern declared here.

NOTE: this module is a Dagster asset module — do NOT add
``from __future__ import annotations`` (it breaks Dagster's runtime context
type validation).
"""

import hashlib
import json
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

from .pairing import pair_filter_s1
from .similarity import compute_topical_similarity

try:
    from dagster import (
        AssetsDefinition,
        MetadataValue,
        OpExecutionContext,
        Output,
        asset,
    )
except Exception:  # pragma: no cover - test-only shim

    def asset(*_args: Any, **_kwargs: Any):  # type: ignore[override]
        def _wrap(fn):
            return fn

        return _wrap

    class Output:  # type: ignore[override]
        def __init__(self, value: Any, metadata: dict | None = None) -> None:
            self.value = value
            self.metadata = metadata or {}

    class MetadataValue:  # type: ignore[override]
        @staticmethod
        def json(v: Any) -> Any:
            return v

    class OpExecutionContext:  # type: ignore[override]
        pass

    AssetsDefinition = Any  # type: ignore[assignment, misc]


CANDIDATES_OUTPUT_PATH = Path("data/processed/phase_iii_candidates.parquet")
EVIDENCE_OUTPUT_PATH = Path("data/processed/phase_iii_evidence.ndjson")


# Per-signal-class scoring weights. Sum to 1.0 (asserted at module load below).
# Weights are NOT YAML — by design (see design.md §"Signal-class weight
# constants"). Vendor match is intentionally absent: UEI overlap is a
# pair-filter gate, not a scored signal.
WEIGHTS_RETROSPECTIVE: dict[str, float] = {
    "agency_continuity": 0.25,
    "timing_proximity": 0.15,
    "competition_type": 0.20,
    "patent_signal": 0.05,
    "cet_alignment": 0.15,
    "text_similarity": 0.10,
    "lineage_language": 0.10,
}

HIGH_THRESHOLD_RETROSPECTIVE: float = 0.85


_REQUIRED_WEIGHT_KEYS: frozenset[str] = frozenset(
    {
        "agency_continuity",
        "timing_proximity",
        "competition_type",
        "patent_signal",
        "cet_alignment",
        "text_similarity",
        "lineage_language",
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
                # Two windows: within 24 months (full credit), within 60 months
                # (half credit). Beyond that, no credit. v1 defaults; tune via
                # the precision backtest.
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
    # Common FPDS extent_competed codes mapped to our internal taxonomy.
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


def _candidate_id(signal_class: SignalClass, prior_award_id: str, target_id: str) -> str:
    h = hashlib.sha1(
        f"{signal_class.value}|{prior_award_id}|{target_id}".encode()
    )
    return f"{signal_class.value}-{h.hexdigest()[:16]}"


def _row_to_federal_contract(row: pd.Series) -> FederalContract:
    return FederalContract(
        contract_id=str(row.get("target_id") or uuid.uuid4().hex),
        agency=row.get("target_agency") if pd.notna(row.get("target_agency")) else None,
        sub_agency=row.get("target_sub_agency")
        if pd.notna(row.get("target_sub_agency"))
        else None,
        start_date=_to_date(row.get("target_action_date")),
        obligation_amount=float(row.get("target_obligated_amount"))
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
    scorer: TransitionScorer, row: pd.Series
) -> tuple[float, dict[str, float], float]:
    """Score one pre-filtered candidate row.

    Returns ``(composite_score, per_signal_subscores, topical_similarity)``.
    The composite score is the sum of all per-signal contributions, capped at
    1.0. Subscores are returned per-signal for evidence/parquet.
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
    topical = compute_topical_similarity(prior, target)
    text_score = scorer.score_text_similarity(topical)

    description = row.get("target_description")
    desc_str = str(description) if description is not None and not (
        isinstance(description, float) and pd.isna(description)
    ) else None
    lineage_score = scorer.score_lineage_language(desc_str)

    subscores = {
        "agency_continuity_score": float(agency.agency_score),
        "timing_proximity_score": float(timing.timing_score),
        "competition_type_score": float(competition.competition_score),
        "patent_signal_score": float(patent.patent_score),
        "cet_alignment_score": float(cet.cet_alignment_score),
        "text_similarity_score": float(text_score),
        "lineage_language_score": float(lineage_score),
    }
    composite = min(1.0, sum(subscores.values()))
    return composite, subscores, float(topical)


def _evidence_bundle(
    candidate: PhaseIIICandidate,
    row: pd.Series,
    topical_similarity: float,
) -> dict[str, Any]:
    """Build the per-candidate evidence record.

    Mirrors the key shape of ``transitions_evidence.ndjson`` (``award_id``,
    ``contract_id``, ``score``, ``method``, ``matched_keys``, ``dates``,
    ``amounts``, ``agencies``) so downstream tooling can reuse the same
    parsing helpers.
    """

    return {
        "candidate_id": candidate.candidate_id,
        "signal_class": candidate.signal_class.value,
        "award_id": candidate.prior_award_id,
        "contract_id": candidate.target_id,
        "target_type": candidate.target_type,
        "score": candidate.candidate_score,
        "is_high_confidence": candidate.is_high_confidence,
        "method": "phase_iii_candidate_scorer",
        "matched_keys": ["recipient_uei", str(row.get("agency_match_level") or "")],
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
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s or None


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
                "generated_at",
            ]
        )
    rows = [c.model_dump(mode="json") for c in candidates]
    df = pd.DataFrame(rows)
    return df


def _default_retrospective_loader(_context: Any) -> pd.DataFrame:
    """Default S1 target loader: read FPDS contracts parquet from disk.

    Production wires this through ``validated_phase_ii_awards`` upstream and
    a contracts parquet path. Returning an empty frame when the file is
    missing keeps the asset materializable in dev environments without raw
    contract data.
    """

    from .pairing import _is_phase_iii_already_coded  # noqa: F401  # ensure module loads

    contracts_path = Path("data/transition/contracts_ingestion.parquet")
    if not contracts_path.exists():
        contracts_path = Path("data/processed/contracts_ingestion.parquet")
    if not contracts_path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(contracts_path)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to read contracts parquet at {}: {}", contracts_path, exc)
        return pd.DataFrame()


def build_candidate_asset(
    *,
    signal_class: SignalClass,
    pair_filter: Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame],
    weights: dict[str, float],
    high_threshold: float,
    asset_name: str,
    target_loader: Callable[[Any], pd.DataFrame],
):
    """Factory that produces one Dagster asset per signal class.

    Args:
        signal_class: Which surfacing pipeline this materialization belongs to.
        pair_filter: Module-level pair-filter callable
            ``(prior_awards, targets) -> DataFrame``.
        weights: Per-signal scoring weights (sum to 1.0).
        high_threshold: Score cutoff for ``is_high_confidence``.
        asset_name: Dagster asset name (e.g. ``phase_iii_retrospective_candidates``).
        target_loader: Callable that returns the target DataFrame given the
            asset execution context. The factory keeps target loading out of
            the asset body so each signal class can source its own corpus.

    Returns:
        A Dagster ``AssetsDefinition`` (or the underlying function when
        Dagster isn't installed; tests use the shim to call directly).
    """

    _validate_weights(asset_name, weights)
    target_type = "fpds_contract" if signal_class is SignalClass.RETROSPECTIVE else "opportunity"

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
            validated_phase_ii_awards
            if validated_phase_ii_awards is not None
            else pd.DataFrame()
        )
        targets = target_loader(context)
        log = getattr(context, "log", logger) if context is not None else logger

        pairs = pair_filter(priors, targets)
        config = _scorer_config(weights)
        scorer = TransitionScorer(config)

        candidates: list[PhaseIIICandidate] = []
        evidence_records: list[dict[str, Any]] = []
        for _, row in pairs.iterrows():
            composite, subscores, topical = _score_pair(scorer, row)
            prior_id = str(row.get("prior_award_id") or "")
            target_id = str(row.get("target_id") or "")
            if not prior_id or not target_id:
                continue
            cid = _candidate_id(signal_class, prior_id, target_id)
            candidate = PhaseIIICandidate(
                candidate_id=cid,
                signal_class=signal_class,
                prior_award_id=prior_id,
                target_type=target_type,  # type: ignore[arg-type]
                target_id=target_id,
                candidate_score=composite,
                is_high_confidence=composite >= high_threshold,
                evidence_ref=cid,
                agency_continuity_score=subscores["agency_continuity_score"],
                timing_proximity_score=subscores["timing_proximity_score"],
                competition_type_score=subscores["competition_type_score"],
                patent_signal_score=subscores["patent_signal_score"],
                cet_alignment_score=subscores["cet_alignment_score"],
                text_similarity_score=subscores["text_similarity_score"],
                lineage_language_score=subscores["lineage_language_score"],
                generated_at=datetime.now(UTC),
            )
            candidates.append(candidate)
            evidence_records.append(_evidence_bundle(candidate, row, topical))

        df = _candidate_dataframe(candidates)
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
        metadata = {
            "rows": int(len(df)),
            "high_confidence_rows": high_count,
            "candidates_path": str(CANDIDATES_OUTPUT_PATH),
            "evidence_path": str(EVIDENCE_OUTPUT_PATH),
            "signal_class": signal_class.value,
            "high_threshold": float(high_threshold),
        }
        return Output(df, metadata=metadata)

    return _candidate_asset


def _write_outputs(
    new_rows: pd.DataFrame,
    evidence_records: list[dict[str, Any]],
    signal_class: SignalClass,
) -> None:
    """Append-and-replace this signal class's rows in the shared outputs.

    The parquet and NDJSON are shared across all three signal-class
    materializations. To make the per-class run idempotent we read the
    existing file (if any), drop rows for this class, and concat the new
    rows. Same idea for the NDJSON.
    """

    CANDIDATES_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Parquet
    if CANDIDATES_OUTPUT_PATH.exists():
        try:
            existing = pd.read_parquet(CANDIDATES_OUTPUT_PATH)
            existing = existing.loc[existing["signal_class"] != signal_class.value]
        except Exception:
            existing = pd.DataFrame()
    else:
        existing = pd.DataFrame()
    combined = pd.concat([existing, new_rows], ignore_index=True, sort=False)
    if not combined.empty:
        combined.to_parquet(CANDIDATES_OUTPUT_PATH, index=False)

    # NDJSON: rewrite, preserving lines for the other signal classes.
    preserved: list[str] = []
    if EVIDENCE_OUTPUT_PATH.exists():
        for raw in EVIDENCE_OUTPUT_PATH.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if obj.get("signal_class") != signal_class.value:
                preserved.append(raw)

    with EVIDENCE_OUTPUT_PATH.open("w", encoding="utf-8") as fh:
        for line in preserved:
            fh.write(line + "\n")
        for record in evidence_records:
            fh.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Concrete materializations — one per signal class.
# ---------------------------------------------------------------------------

phase_iii_retrospective_candidates = build_candidate_asset(
    signal_class=SignalClass.RETROSPECTIVE,
    pair_filter=pair_filter_s1,
    weights=WEIGHTS_RETROSPECTIVE,
    high_threshold=HIGH_THRESHOLD_RETROSPECTIVE,
    asset_name="phase_iii_retrospective_candidates",
    target_loader=_default_retrospective_loader,
)


__all__ = [
    "CANDIDATES_OUTPUT_PATH",
    "EVIDENCE_OUTPUT_PATH",
    "HIGH_THRESHOLD_RETROSPECTIVE",
    "WEIGHTS_RETROSPECTIVE",
    "build_candidate_asset",
    "phase_iii_retrospective_candidates",
]
