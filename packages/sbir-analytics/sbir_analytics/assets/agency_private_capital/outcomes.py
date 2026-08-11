"""Outcome-metric calculator for the SBIR cohort (agency-parameterized).

Computes per-stratum (vintage x phase) commercialization rates with Wilson-
score confidence intervals. Inputs are optional; when an upstream artifact
is missing the corresponding metric is reported as ``available=False`` and
all numeric fields are ``None`` so the downstream report can still render.

Metrics:
    - phase_i_to_ii_graduation: any canonically resolved company with a Phase I
      award in stratum that has a Phase II award in the cohort no earlier than
      that Phase I and within the configured graduation horizon (default:
      5 years). Every UEI, DUNS, and normalized-name alias present on a row is
      connected before this firm-level calculation.
    - phase_ii_to_federal_contract_transition: Phase II awards with at least
      one upstream transition score >= the configured threshold (consumes
      ``transformed_transition_scores`` produced by the existing detector;
      the >=85% precision benchmark is enforced upstream and not relaxed
      here).
    - five_year_survival_proxy: Phase II company appears as a recipient or
      vendor in any federal dataset >=5 years after Phase II award year.
      Denominator is unique companies (not award rows) per stratum.
    - ma_exit_rate: SBIR awardee appears in the M&A events JSONL (post-#286).
      The join checks every alias attached to the resolved company component.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from sbir_etl.identity import CompanyNameProfile, normalize_company_name


WILSON_Z_95 = 1.959963984540054


def wilson_interval(
    numerator: int, denominator: int, *, z: float = WILSON_Z_95
) -> dict[str, float]:
    """Wilson score confidence interval for a binomial proportion.

    Returns a dict with ``rate`` (point estimate), ``ci_low``, ``ci_high``,
    ``numerator`` and ``denominator``. When ``denominator`` is zero, the
    rate and bounds are returned as ``float('nan')`` so the caller can
    decide how to render an undefined cell.
    """

    n = int(denominator)
    k = int(numerator)
    if n <= 0:
        return {
            "rate": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "numerator": k,
            "denominator": n,
        }
    if k < 0 or k > n:
        raise ValueError(f"numerator {k} out of range for denominator {n}")
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return {
        "rate": p,
        "ci_low": max(0.0, centre - half),
        "ci_high": min(1.0, centre + half),
        "numerator": k,
        "denominator": n,
    }


_IDENTITY_PREFIX_ORDER = {"uei": 0, "duns": 1, "name": 2}


def _nonempty_value(row: pd.Series, *keys: str) -> object | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        try:
            if bool(pd.isna(value)):
                continue
        except (TypeError, ValueError):  # pragma: no cover - non-scalar cell
            continue
        if str(value).strip():
            return value
    return None


def _normalized_duns(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    digits = "".join(character for character in text if character.isdigit())
    return digits or text.upper()


def _identity_aliases(row: pd.Series) -> frozenset[str]:
    """Return every exact identity alias present on an award row.

    Names use the repository's versioned organization-key policy. This is an
    exact alias graph, not a fuzzy match: rows are joined only when they share
    a normalized UEI, DUNS, or organization name, including through a
    transitive chain of co-occurring identifiers.
    """

    aliases: set[str] = set()
    uei = _nonempty_value(row, "uei", "UEI")
    if uei is not None:
        aliases.add(f"uei:{str(uei).strip().upper()}")
    duns = _nonempty_value(row, "duns", "Duns")
    if duns is not None:
        aliases.add(f"duns:{_normalized_duns(duns)}")
    name = _nonempty_value(row, "company_name", "Company")
    if name is not None:
        normalized_name = normalize_company_name(
            name,
            profile=CompanyNameProfile.ORGANIZATION_KEY_V1,
        )
        if normalized_name:
            aliases.add(f"name:{normalized_name.lower()}")
    return frozenset(aliases)


def _alias_sort_key(alias: str) -> tuple[int, str]:
    prefix = alias.partition(":")[0]
    return (_IDENTITY_PREFIX_ORDER.get(prefix, 99), alias)


def _resolve_company_identities(
    cohort: pd.DataFrame,
) -> tuple[list[str | None], list[frozenset[str]]]:
    """Resolve rows to deterministic connected components of exact aliases."""

    row_aliases = [_identity_aliases(row) for _, row in cohort.iterrows()]
    parent: dict[str, str] = {}

    def find(alias: str) -> str:
        parent.setdefault(alias, alias)
        root = alias
        while parent[root] != root:
            root = parent[root]
        while parent[alias] != alias:
            next_alias = parent[alias]
            parent[alias] = root
            alias = next_alias
        return root

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if _alias_sort_key(left_root) <= _alias_sort_key(right_root):
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    for aliases in row_aliases:
        ordered = sorted(aliases, key=_alias_sort_key)
        if not ordered:
            continue
        find(ordered[0])
        for alias in ordered[1:]:
            union(ordered[0], alias)

    component_aliases: dict[str, set[str]] = {}
    for alias in parent:
        component_aliases.setdefault(find(alias), set()).add(alias)
    canonical_by_root = {
        root: min(aliases, key=_alias_sort_key) for root, aliases in component_aliases.items()
    }
    company_keys = [
        canonical_by_root[find(min(aliases, key=_alias_sort_key))] if aliases else None
        for aliases in row_aliases
    ]
    return company_keys, row_aliases


def _resolved_award_year(row: pd.Series) -> int | None:
    value = row.get("award_year_resolved")
    if value is None or pd.isna(value):
        return None
    return int(value)


@dataclass
class OutcomeMetricsCalculator:
    """Compute per-stratum SBIR cohort outcome rates with Wilson CIs.

    Args:
        graduation_horizon_years: maximum inclusive number of calendar years
            from a Phase I award to a qualifying Phase II award. ``None``
            means unbounded follow-up. Default 5 is the current Phase 1 review
            estimand and is configurable rather than implicit.
        transition_score_threshold: minimum upstream transition-score for a
            Phase II award to count as transitioned. Default 0.65 matches
            the ``likely`` confidence threshold in
            ``sbir_ml.transition.DEFAULTS``.
        survival_horizon_years: years after award_year to look for
            recipient/vendor activity. Default 5.
    """

    graduation_horizon_years: int | None = 5
    transition_score_threshold: float = 0.65
    survival_horizon_years: int = 5
    z: float = WILSON_Z_95

    transition_scores: pd.DataFrame | None = field(default=None)
    federal_activity_companies: set[str] | None = field(default=None)
    ma_event_companies: set[str] | None = field(default=None)

    def __post_init__(self) -> None:
        if self.graduation_horizon_years is not None and self.graduation_horizon_years < 0:
            raise ValueError("graduation_horizon_years must be non-negative or None")

    @staticmethod
    def identity_coverage(
        cohort: pd.DataFrame,
        *,
        vintage_bucket: str | None = None,
        phase_label: str | None = None,
    ) -> dict[str, object]:
        """Summarize coverage after resolving aliases across the full cohort.

        Optional vintage and phase filters select the rows whose firms form the
        reported denominator, while retaining aliases learned from every row.
        """

        if cohort.empty:
            return {
                "row_count": 0,
                "resolved_row_count": 0,
                "resolved_row_rate": None,
                "company_count": 0,
                "company_basis_counts": {"uei": 0, "duns": 0, "name": 0},
                "uei_duns_bridge_company_count": 0,
            }
        company_keys, row_aliases = _resolve_company_identities(cohort)
        selected = pd.Series(True, index=cohort.index)
        if vintage_bucket is not None:
            selected &= cohort["vintage_bucket"] == vintage_bucket
        if phase_label is not None:
            selected &= cohort["phase_label"] == phase_label
        selected_positions = [
            position for position, keep in enumerate(selected.tolist()) if bool(keep)
        ]
        selected_company_keys: set[str] = set()
        for position in selected_positions:
            company_key = company_keys[position]
            if company_key is not None:
                selected_company_keys.add(company_key)
        aliases_by_company: dict[str, set[str]] = {}
        for company_key, aliases in zip(company_keys, row_aliases, strict=True):
            if company_key is not None and company_key in selected_company_keys:
                aliases_by_company.setdefault(company_key, set()).update(aliases)
        basis_counts = {"uei": 0, "duns": 0, "name": 0}
        bridge_count = 0
        for component_aliases in aliases_by_company.values():
            prefixes = {alias.partition(":")[0] for alias in component_aliases}
            if "uei" in prefixes:
                basis_counts["uei"] += 1
            elif "duns" in prefixes:
                basis_counts["duns"] += 1
            else:
                basis_counts["name"] += 1
            if {"uei", "duns"}.issubset(prefixes):
                bridge_count += 1
        resolved_rows = sum(company_keys[position] is not None for position in selected_positions)
        row_count = len(selected_positions)
        return {
            "row_count": row_count,
            "resolved_row_count": resolved_rows,
            "resolved_row_rate": resolved_rows / row_count if row_count else None,
            "company_count": len(aliases_by_company),
            "company_basis_counts": basis_counts,
            "uei_duns_bridge_company_count": bridge_count,
        }

    def compute(self, cohort: pd.DataFrame) -> pd.DataFrame:
        """Emit one row per (vintage_bucket, phase_label, metric) stratum."""

        if cohort.empty:
            return pd.DataFrame(
                columns=[
                    "vintage_bucket",
                    "phase_label",
                    "metric",
                    "numerator",
                    "denominator",
                    "rate",
                    "ci_low",
                    "ci_high",
                    "available",
                ]
            )

        records: list[dict[str, Any]] = []
        cohort = cohort.copy()
        company_keys, row_aliases = _resolve_company_identities(cohort)
        cohort["_company_key"] = company_keys
        cohort["_identity_aliases"] = row_aliases

        # Phase I->II graduation: per-vintage. A Phase II that predates its
        # company's Phase I is not a graduation, nor is one outside the
        # configured cohort window.
        phase_i = cohort[cohort["phase_label"] == "I"]
        phase_ii = cohort[cohort["phase_label"] == "II"].copy()
        phase_ii_years: dict[str, set[int]] = {}
        for _, row in phase_ii.iterrows():
            company_key = row["_company_key"]
            year = _resolved_award_year(row)
            if company_key and year is not None:
                phase_ii_years.setdefault(company_key, set()).add(year)

        for vintage, group in phase_i.groupby("vintage_bucket", dropna=False):
            keys = [k for k in group["_company_key"].tolist() if k]
            unique_keys = set(keys)
            graduated: set[str] = set()
            for _, row in group.iterrows():
                company_key = row["_company_key"]
                phase_i_year = _resolved_award_year(row)
                if not company_key or phase_i_year is None:
                    continue
                if any(
                    phase_i_year <= phase_ii_year
                    and (
                        self.graduation_horizon_years is None
                        or phase_ii_year <= phase_i_year + self.graduation_horizon_years
                    )
                    for phase_ii_year in phase_ii_years.get(company_key, set())
                ):
                    graduated.add(company_key)
            records.append(
                self._make_row(
                    vintage,
                    "I",
                    "phase_i_to_ii_graduation",
                    numerator=len(graduated),
                    denominator=len(unique_keys),
                    available=True,
                )
            )

        # Phase II -> federal-contract transition
        transition_award_ids = self._transitioned_award_ids()
        for vintage, group in phase_ii.groupby("vintage_bucket", dropna=False):
            denom = len(group)
            if self.transition_scores is None:
                records.append(
                    self._make_row(
                        vintage,
                        "II",
                        "phase_ii_to_federal_contract_transition",
                        numerator=None,
                        denominator=denom,
                        available=False,
                    )
                )
                continue
            award_ids = set(group.get("award_id", pd.Series(dtype=object)).dropna().astype(str))
            transitioned = award_ids & transition_award_ids
            records.append(
                self._make_row(
                    vintage,
                    "II",
                    "phase_ii_to_federal_contract_transition",
                    numerator=len(transitioned),
                    denominator=denom,
                    available=True,
                )
            )

        # 5-year survival proxy (Phase II only).
        # Bug fix: denominator is unique companies, not award rows.
        for vintage, group in phase_ii.groupby("vintage_bucket", dropna=False):
            unique_companies = group["_company_key"].dropna().nunique()
            denom = unique_companies
            if self.federal_activity_companies is None:
                records.append(
                    self._make_row(
                        vintage,
                        "II",
                        "five_year_survival_proxy",
                        numerator=None,
                        denominator=denom,
                        available=False,
                    )
                )
                continue
            active_company_keys = {k for k in group["_company_key"].tolist() if k}
            survived = active_company_keys & self.federal_activity_companies
            records.append(
                self._make_row(
                    vintage,
                    "II",
                    "five_year_survival_proxy",
                    numerator=len(survived),
                    denominator=denom,
                    available=True,
                )
            )

        # M&A exit rate (per stratum, all phases).
        # Match every alias on a resolved company component. The current M&A
        # artifact is name-keyed, while future inputs may carry UEI or DUNS.
        for (vintage, phase), group in cohort.groupby(
            ["vintage_bucket", "phase_label"], dropna=False
        ):
            denom_keys = {k for k in group["_company_key"].tolist() if k}
            denom = len(denom_keys)
            if self.ma_event_companies is None:
                records.append(
                    self._make_row(
                        vintage,
                        phase,
                        "ma_exit_rate",
                        numerator=None,
                        denominator=denom,
                        available=False,
                    )
                )
                continue
            exited: set[str] = set()
            for _, row in group.iterrows():
                company_k = row.get("_company_key")
                aliases = row.get("_identity_aliases") or frozenset()
                if company_k and any(alias in self.ma_event_companies for alias in aliases):
                    exited.add(company_k)
            records.append(
                self._make_row(
                    vintage,
                    phase,
                    "ma_exit_rate",
                    numerator=len(exited),
                    denominator=denom,
                    available=True,
                )
            )

        return pd.DataFrame.from_records(records)

    def _transitioned_award_ids(self) -> set[str]:
        if self.transition_scores is None or self.transition_scores.empty:
            return set()
        df = self.transition_scores
        score_col = "score" if "score" in df.columns else "likelihood_score"
        if score_col not in df.columns or "award_id" not in df.columns:
            return set()
        passed = df[df[score_col].astype(float) >= self.transition_score_threshold]
        return set(passed["award_id"].dropna().astype(str))

    def _make_row(
        self,
        vintage: object,
        phase: object,
        metric: str,
        *,
        numerator: int | None,
        denominator: int,
        available: bool,
    ) -> dict[str, Any]:
        wi: dict[str, Any]
        if available and numerator is not None and denominator > 0:
            wi = wilson_interval(numerator, denominator, z=self.z)
        else:
            wi = {
                "rate": float("nan"),
                "ci_low": float("nan"),
                "ci_high": float("nan"),
                "numerator": numerator,
                "denominator": denominator,
            }
        return {
            "vintage_bucket": vintage,
            "phase_label": phase,
            "metric": metric,
            "numerator": int(wi["numerator"]) if wi["numerator"] is not None else None,
            "denominator": int(wi["denominator"]),
            "rate": wi["rate"],
            "ci_low": wi["ci_low"],
            "ci_high": wi["ci_high"],
            "available": bool(available),
        }
