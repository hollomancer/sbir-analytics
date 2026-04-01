"""SBIR/STTR benchmark eligibility evaluator.

Evaluates which companies are subject to the statutory performance benchmarks
and whether they pass or fail, given a target evaluation fiscal year.

Implements the two benchmark types:

1. **Phase I→II Transition Rate Benchmark**
   - Standard: company has ≥21 Phase I awards in the 5-FY window (excl. most recent FY)
     → must achieve ≥0.25 transition ratio (Phase II / Phase I)
   - Increased (experienced firms): ≥51 Phase I awards → ≥0.50 ratio

2. **Commercialization Rate Benchmark**
   - Standard: company has ≥16 Phase II awards in the 10-FY window (excl. 2 most recent FYs)
     → must avg ≥$100K sales/investment per Phase II, OR ≥15% patents per Phase II
   - Increased Tier 1: ≥51 Phase II awards → avg $250K+ (no patent path)
   - Increased Tier 2: ≥101 Phase II awards → avg $450K+ (no patent path)

Also provides sensitivity analysis identifying companies near the margins of
these thresholds—both those approaching eligibility and those at risk of failing.

Typical usage::

    evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
    summary = evaluator.evaluate(awards_df)
    for r in summary.transition_results:
        print(r.company_id, r.tier, r.status)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from sbir_etl.models.benchmark_models import (
    BenchmarkEvaluationSummary,
    BenchmarkStatus,
    BenchmarkTier,
    CommercializationRateResult,
    CommercializationRateThresholds,
    CompanyAwardCounts,
    ConsequenceType,
    FiscalYearWindow,
    SensitivityResult,
    TransitionRateResult,
    TransitionRateThresholds,
)


def _first_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first column name from candidates that exists in df."""
    for c in candidates:
        if c in df.columns:
            return c
    lower_map = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def _company_id_series(df: pd.DataFrame) -> pd.Series:
    """Build a canonical company ID with priority: UEI > DUNS > name."""
    uei_col = _first_col(df, ["UEI", "uei", "company_uei"])
    duns_col = _first_col(df, ["Duns", "duns", "company_duns"])
    name_col = _first_col(df, ["Company", "company", "company_name", "vendor_name"])

    result = pd.Series([""] * len(df), index=df.index, dtype="object")

    if uei_col:
        uei = df[uei_col].astype(str).str.strip()
        valid = (uei != "") & (~uei.isin(["None", "nan", "NaN"]))
        result = result.mask(valid, "uei:" + uei)
    if duns_col:
        duns = df[duns_col].astype(str).str.strip()
        valid = (duns != "") & (~duns.isin(["None", "nan", "NaN"]))
        result = result.mask((~result.astype(bool)) & valid, "duns:" + duns)
    if name_col:
        names = df[name_col].astype(str).str.strip().str.lower()
        valid = (names != "") & (~names.isin(["none", "nan"]))
        result = result.mask((~result.astype(bool)) & valid, "name:" + names)

    result = result.where(result.astype(bool), "row:" + df.index.astype(str))
    return result


class BenchmarkEligibilityEvaluator:
    """Evaluates SBIR/STTR benchmark eligibility for a given fiscal year.

    Parameters
    ----------
    evaluation_fy :
        The fiscal year for the benchmark evaluation (e.g., 2025 means the
        June 1, 2025 determination date).
    transition_thresholds :
        Override default transition rate thresholds.
    commercialization_thresholds :
        Override default commercialization rate thresholds.
    sensitivity_margin_awards :
        Number of awards within which a company is considered "near" a
        threshold trigger (for sensitivity analysis). Default 5.
    sensitivity_margin_ratio :
        Ratio margin within which a company is considered "at risk" of
        failing a benchmark. Default 0.05 (5 percentage points).
    """

    def __init__(
        self,
        evaluation_fy: int,
        transition_thresholds: TransitionRateThresholds | None = None,
        commercialization_thresholds: CommercializationRateThresholds | None = None,
        sensitivity_margin_awards: int = 5,
        sensitivity_margin_ratio: float = 0.05,
    ) -> None:
        self.evaluation_fy = evaluation_fy
        self.transition_thresholds = transition_thresholds or TransitionRateThresholds()
        self.commercialization_thresholds = (
            commercialization_thresholds or CommercializationRateThresholds()
        )
        self.sensitivity_margin_awards = sensitivity_margin_awards
        self.sensitivity_margin_ratio = sensitivity_margin_ratio

        self.transition_window = self._build_transition_windows()
        self.commercialization_window = self._build_commercialization_window()

    # ─── Window construction ──────────────────────────────────────────

    def _build_transition_windows(self) -> dict[str, FiscalYearWindow]:
        """Build FY windows for Phase I count and Phase II count.

        Phase I window: past 5 FYs excluding the most recently completed FY.
        Phase II window: past 5 FYs including the most recently completed FY.
        """
        t = self.transition_thresholds
        most_recent_completed = self.evaluation_fy - 1

        phase1_end = most_recent_completed - t.phase1_exclude_recent_years
        phase1_start = phase1_end - t.lookback_years + 1

        phase2_end = most_recent_completed - t.phase2_exclude_recent_years
        phase2_start = phase2_end - t.lookback_years + 1

        return {
            "phase1": FiscalYearWindow(
                evaluation_fy=self.evaluation_fy,
                start_fy=phase1_start,
                end_fy=phase1_end,
                exclude_recent_years=t.phase1_exclude_recent_years,
            ),
            "phase2": FiscalYearWindow(
                evaluation_fy=self.evaluation_fy,
                start_fy=phase2_start,
                end_fy=phase2_end,
                exclude_recent_years=t.phase2_exclude_recent_years,
            ),
        }

    def _build_commercialization_window(self) -> FiscalYearWindow:
        """Build FY window for commercialization benchmark.

        Past 10 FYs excluding the 2 most recently completed FYs.
        """
        c = self.commercialization_thresholds
        most_recent_completed = self.evaluation_fy - 1
        end_fy = most_recent_completed - c.exclude_recent_years
        start_fy = end_fy - c.lookback_years + 1
        return FiscalYearWindow(
            evaluation_fy=self.evaluation_fy,
            start_fy=start_fy,
            end_fy=end_fy,
            exclude_recent_years=c.exclude_recent_years,
        )

    # ─── Award counting ──────────────────────────────────────────────

    def _count_awards_by_company(
        self,
        awards_df: pd.DataFrame,
        commercialization_df: pd.DataFrame | None = None,
    ) -> dict[str, CompanyAwardCounts]:
        """Aggregate per-company award counts within the evaluation windows.

        Parameters
        ----------
        awards_df :
            DataFrame of SBIR/STTR awards. Must contain columns for award_id,
            company identifier, phase, and fiscal_year/award_year.
        commercialization_df :
            Optional DataFrame with per-Phase-II commercialization data
            (sales, investment, patents). Columns: company_id,
            total_sales_and_investment, patent_count.
        """
        if awards_df.empty:
            return {}

        df = awards_df.copy()

        # Resolve columns
        phase_col = _first_col(df, ["Phase", "phase"])
        fy_col = _first_col(df, ["fiscal_year", "award_year", "Award Year"])
        name_col = _first_col(df, ["Company", "company", "company_name"])

        if not phase_col or not fy_col:
            return {}

        df["_company_id"] = _company_id_series(df)
        df["_phase"] = df[phase_col].astype(str).str.strip().str.upper().str.replace("PHASE ", "")
        df["_fy"] = pd.to_numeric(df[fy_col], errors="coerce")

        # Drop rows with no FY
        df = df.dropna(subset=["_fy"])
        df["_fy"] = df["_fy"].astype(int)

        p1_window = self.transition_window["phase1"]
        p2_window = self.transition_window["phase2"]
        comm_window = self.commercialization_window

        # Phase I awards in the transition Phase I window
        p1_mask = (
            df["_phase"].isin(["I", "1"])
            & (df["_fy"] >= p1_window.start_fy)
            & (df["_fy"] <= p1_window.end_fy)
        )
        # Phase II awards in the transition Phase II window
        p2_mask = (
            df["_phase"].isin(["II", "2"])
            & (df["_fy"] >= p2_window.start_fy)
            & (df["_fy"] <= p2_window.end_fy)
        )
        # Phase II awards in the commercialization window
        comm_p2_mask = (
            df["_phase"].isin(["II", "2"])
            & (df["_fy"] >= comm_window.start_fy)
            & (df["_fy"] <= comm_window.end_fy)
        )

        p1_counts = df[p1_mask].groupby("_company_id").size().to_dict()
        p2_counts = df[p2_mask].groupby("_company_id").size().to_dict()
        comm_p2_counts = df[comm_p2_mask].groupby("_company_id").size().to_dict()

        # Phase I FYs per company (for detail)
        p1_fys = (
            df[p1_mask].groupby("_company_id")["_fy"].apply(sorted).apply(list).to_dict()
        )
        p2_fys = (
            df[p2_mask].groupby("_company_id")["_fy"].apply(sorted).apply(list).to_dict()
        )

        # Company names
        if name_col:
            company_names = df.groupby("_company_id")[name_col].first().to_dict()
        else:
            company_names = {}

        # All unique companies
        all_companies = set(df["_company_id"].unique())

        # Merge commercialization data
        comm_data: dict[str, dict[str, float]] = {}
        if commercialization_df is not None and not commercialization_df.empty:
            cid_col = _first_col(commercialization_df, ["company_id", "_company_id"])
            sales_col = _first_col(
                commercialization_df,
                ["total_sales_and_investment", "sales", "revenue"],
            )
            pat_col = _first_col(commercialization_df, ["patent_count", "patents"])
            if cid_col:
                for _, row in commercialization_df.iterrows():
                    cid = str(row[cid_col])
                    comm_data[cid] = {
                        "sales": float(row[sales_col]) if sales_col else 0.0,
                        "patents": int(row[pat_col]) if pat_col else 0,
                    }

        results: dict[str, CompanyAwardCounts] = {}
        for cid in all_companies:
            cd = comm_data.get(cid, {})
            results[cid] = CompanyAwardCounts(
                company_id=cid,
                company_name=company_names.get(cid),
                phase1_count=p1_counts.get(cid, 0),
                phase2_count=p2_counts.get(cid, 0),
                phase2_count_commercialization=comm_p2_counts.get(cid, 0),
                total_sales_and_investment=cd.get("sales", 0.0),
                patent_count=int(cd.get("patents", 0)),
                phase1_fiscal_years=p1_fys.get(cid, []),
                phase2_fiscal_years=p2_fys.get(cid, []),
            )

        return results

    # ─── Transition rate evaluation ──────────────────────────────────

    def _evaluate_transition_rate(
        self, counts: CompanyAwardCounts
    ) -> TransitionRateResult:
        """Evaluate the Phase I→II transition rate benchmark for one company."""
        t = self.transition_thresholds
        p1 = counts.phase1_count
        p2 = counts.phase2_count

        # Determine tier
        if p1 >= t.increased_min_phase1:
            tier = BenchmarkTier.INCREASED_TIER1
            required_ratio = t.increased_min_ratio
        elif p1 >= t.standard_min_phase1:
            tier = BenchmarkTier.STANDARD
            required_ratio = t.standard_min_ratio
        else:
            tier = BenchmarkTier.NOT_SUBJECT
            required_ratio = None

        # Compute ratio
        ratio = p2 / p1 if p1 > 0 else None

        # Determine status and consequence
        if tier == BenchmarkTier.NOT_SUBJECT:
            status = BenchmarkStatus.NOT_APPLICABLE
            consequence = ConsequenceType.NONE
        elif ratio is not None and required_ratio is not None and ratio >= required_ratio:
            status = BenchmarkStatus.PASS
            consequence = ConsequenceType.NONE
        else:
            status = BenchmarkStatus.FAIL
            if tier == BenchmarkTier.STANDARD:
                consequence = ConsequenceType.PHASE1_INELIGIBLE_1YR
            else:
                consequence = ConsequenceType.CAPPED_20_AWARDS_PER_AGENCY

        # Sensitivity: awards to next tier
        if p1 < t.standard_min_phase1:
            awards_to_next = t.standard_min_phase1 - p1
        elif p1 < t.increased_min_phase1:
            awards_to_next = t.increased_min_phase1 - p1
        else:
            awards_to_next = None

        # Margin from threshold
        margin = None
        if required_ratio is not None and ratio is not None:
            margin = round(ratio - required_ratio, 6)

        return TransitionRateResult(
            company_id=counts.company_id,
            company_name=counts.company_name,
            tier=tier,
            status=status,
            consequence=consequence,
            phase1_count=p1,
            phase2_count=p2,
            transition_ratio=round(ratio, 6) if ratio is not None else None,
            required_ratio=required_ratio,
            phase1_awards_to_next_tier=awards_to_next,
            margin_from_threshold=margin,
        )

    # ─── Commercialization rate evaluation ───────────────────────────

    def _evaluate_commercialization_rate(
        self, counts: CompanyAwardCounts
    ) -> CommercializationRateResult:
        """Evaluate the commercialization rate benchmark for one company."""
        c = self.commercialization_thresholds
        p2 = counts.phase2_count_commercialization

        # Determine tier
        if p2 >= c.increased_tier2_min_phase2:
            tier = BenchmarkTier.INCREASED_TIER2
        elif p2 >= c.increased_tier1_min_phase2:
            tier = BenchmarkTier.INCREASED_TIER1
        elif p2 >= c.standard_min_phase2:
            tier = BenchmarkTier.STANDARD
        else:
            tier = BenchmarkTier.NOT_SUBJECT

        # Required thresholds (tier-specific sales, patents only for standard)
        patents_path = tier == BenchmarkTier.STANDARD
        if tier == BenchmarkTier.INCREASED_TIER2:
            required_avg_sales = c.increased_tier2_min_avg_sales
        elif tier == BenchmarkTier.INCREASED_TIER1:
            required_avg_sales = c.increased_tier1_min_avg_sales
        elif tier == BenchmarkTier.STANDARD:
            required_avg_sales = c.standard_min_avg_sales
        else:
            required_avg_sales = None
        required_patent_rate = c.standard_min_patent_rate if patents_path else None

        # Compute metrics
        avg_sales = (
            counts.total_sales_and_investment / p2 if p2 > 0 else None
        )
        patent_rate = counts.patent_count / p2 if p2 > 0 else None

        # Determine status
        if tier == BenchmarkTier.NOT_SUBJECT:
            status = BenchmarkStatus.NOT_APPLICABLE
            consequence = ConsequenceType.NONE
        else:
            passes_sales = (
                avg_sales is not None
                and required_avg_sales is not None
                and avg_sales >= required_avg_sales
            )
            passes_patents = (
                patents_path
                and patent_rate is not None
                and patent_rate >= c.standard_min_patent_rate
            )

            if passes_sales or passes_patents:
                status = BenchmarkStatus.PASS
                consequence = ConsequenceType.NONE
            else:
                status = BenchmarkStatus.FAIL
                if tier == BenchmarkTier.STANDARD:
                    consequence = ConsequenceType.PHASE1_INELIGIBLE_1YR
                else:
                    consequence = ConsequenceType.CAPPED_20_AWARDS_PER_AGENCY

        # Sensitivity: awards to next tier
        if p2 < c.standard_min_phase2:
            awards_to_next = c.standard_min_phase2 - p2
        elif p2 < c.increased_tier1_min_phase2:
            awards_to_next = c.increased_tier1_min_phase2 - p2
        elif p2 < c.increased_tier2_min_phase2:
            awards_to_next = c.increased_tier2_min_phase2 - p2
        else:
            awards_to_next = None

        # Margins
        sales_margin = None
        patent_margin = None
        if required_avg_sales is not None and avg_sales is not None:
            sales_margin = round(avg_sales - required_avg_sales, 2)
        if required_patent_rate is not None and patent_rate is not None:
            patent_margin = round(patent_rate - required_patent_rate, 6)

        return CommercializationRateResult(
            company_id=counts.company_id,
            company_name=counts.company_name,
            tier=tier,
            status=status,
            consequence=consequence,
            phase2_count=p2,
            avg_sales_per_phase2=round(avg_sales, 2) if avg_sales is not None else None,
            patent_rate=round(patent_rate, 6) if patent_rate is not None else None,
            required_avg_sales=required_avg_sales,
            required_patent_rate=required_patent_rate,
            patents_path_available=patents_path,
            phase2_awards_to_next_tier=awards_to_next,
            margin_from_sales_threshold=sales_margin,
            margin_from_patent_threshold=patent_margin,
        )

    # ─── Sensitivity analysis ────────────────────────────────────────

    def _compute_sensitivity(
        self,
        counts: CompanyAwardCounts,
        transition_result: TransitionRateResult,
        commercialization_result: CommercializationRateResult,
    ) -> SensitivityResult:
        """Compute sensitivity analysis for a company.

        A company is considered "at risk" if:
        - It is within `sensitivity_margin_awards` of a tier threshold, OR
        - It is subject to a benchmark and its ratio/metric is within
          `sensitivity_margin_ratio` of the required threshold.
        """
        t = self.transition_thresholds
        c = self.commercialization_thresholds
        p1 = counts.phase1_count
        p2_comm = counts.phase2_count_commercialization

        p1_to_standard = max(0, t.standard_min_phase1 - p1)
        p1_to_increased = max(0, t.increased_min_phase1 - p1)
        p2_to_standard_comm = max(0, c.standard_min_phase2 - p2_comm)
        p2_to_tier1 = max(0, c.increased_tier1_min_phase2 - p2_comm)
        p2_to_tier2 = max(0, c.increased_tier2_min_phase2 - p2_comm)

        # Approaching transition threshold
        at_risk_transition = (
            0 < p1_to_standard <= self.sensitivity_margin_awards
            or 0 < p1_to_increased <= self.sensitivity_margin_awards
        )
        # Already subject and close to failing
        if transition_result.margin_from_threshold is not None:
            margin = transition_result.margin_from_threshold
            if 0 <= margin <= self.sensitivity_margin_ratio:
                at_risk_transition = True

        # Approaching commercialization threshold
        at_risk_commercialization = (
            0 < p2_to_standard_comm <= self.sensitivity_margin_awards
            or 0 < p2_to_tier1 <= self.sensitivity_margin_awards
            or 0 < p2_to_tier2 <= self.sensitivity_margin_awards
        )
        # Already subject and close to failing
        if commercialization_result.margin_from_sales_threshold is not None:
            margin = commercialization_result.margin_from_sales_threshold
            if commercialization_result.required_avg_sales is not None and 0 <= margin <= self.sensitivity_margin_ratio * commercialization_result.required_avg_sales:
                at_risk_commercialization = True

        return SensitivityResult(
            company_id=counts.company_id,
            company_name=counts.company_name,
            phase1_count=p1,
            phase1_to_standard_transition=p1_to_standard,
            phase1_to_increased_transition=p1_to_increased,
            phase2_count_for_commercialization=p2_comm,
            phase2_to_standard_commercialization=p2_to_standard_comm,
            phase2_to_increased_tier1=p2_to_tier1,
            phase2_to_increased_tier2=p2_to_tier2,
            transition_rate_margin=transition_result.margin_from_threshold,
            commercialization_sales_margin=commercialization_result.margin_from_sales_threshold,
            commercialization_patent_margin=commercialization_result.margin_from_patent_threshold,
            at_risk_transition=at_risk_transition,
            at_risk_commercialization=at_risk_commercialization,
        )

    # ─── Public API ──────────────────────────────────────────────────

    def get_commercialization_candidates(
        self,
        awards_df: pd.DataFrame,
    ) -> list[CompanyAwardCounts]:
        """Identify companies subject to the commercialization benchmark.

        Runs award counting without commercialization data to find companies
        with enough Phase II awards (≥16 standard, ≥51 tier 1, ≥101 tier 2)
        to be subject to the commercialization benchmark.  Use this to
        pre-filter USAspending queries before running the full evaluation.

        Returns
        -------
        list[CompanyAwardCounts]
            Companies whose Phase II count in the commercialization window
            meets or exceeds the standard threshold.
        """
        company_counts = self._count_awards_by_company(awards_df)
        min_p2 = self.commercialization_thresholds.standard_min_phase2
        return [
            counts
            for counts in company_counts.values()
            if counts.phase2_count_commercialization >= min_p2
        ]

    def evaluate(
        self,
        awards_df: pd.DataFrame,
        commercialization_df: pd.DataFrame | None = None,
    ) -> BenchmarkEvaluationSummary:
        """Run the full benchmark evaluation for all companies in the dataset.

        Parameters
        ----------
        awards_df :
            DataFrame of SBIR/STTR awards. Required columns:
            - award_id (or equivalent)
            - company identifier (UEI, DUNS, or company name)
            - phase (I, II, III or Phase I, Phase II, Phase III)
            - fiscal_year or award_year
        commercialization_df :
            Optional DataFrame with per-company commercialization data for the
            commercialization rate benchmark. Columns: company_id,
            total_sales_and_investment, patent_count.

        Returns
        -------
        BenchmarkEvaluationSummary
            Complete evaluation results including per-company transition rate
            results, commercialization rate results, and sensitivity analysis.
        """
        company_counts = self._count_awards_by_company(awards_df, commercialization_df)

        transition_results: list[TransitionRateResult] = []
        commercialization_results: list[CommercializationRateResult] = []
        sensitivity_results: list[SensitivityResult] = []

        for _cid, counts in company_counts.items():
            tr = self._evaluate_transition_rate(counts)
            cr = self._evaluate_commercialization_rate(counts)
            sr = self._compute_sensitivity(counts, tr, cr)

            transition_results.append(tr)
            commercialization_results.append(cr)
            # Include in sensitivity results only if at risk or subject
            if (
                sr.at_risk_transition
                or sr.at_risk_commercialization
                or tr.tier != BenchmarkTier.NOT_SUBJECT
                or cr.tier != BenchmarkTier.NOT_SUBJECT
            ):
                sensitivity_results.append(sr)

        # Sort: companies subject to benchmarks first, then by company_id
        transition_results.sort(
            key=lambda r: (r.tier == BenchmarkTier.NOT_SUBJECT, r.company_id)
        )
        commercialization_results.sort(
            key=lambda r: (r.tier == BenchmarkTier.NOT_SUBJECT, r.company_id)
        )
        sensitivity_results.sort(
            key=lambda r: (
                not r.at_risk_transition and not r.at_risk_commercialization,
                r.company_id,
            )
        )

        p1_window = self.transition_window["phase1"]
        p2_window = self.transition_window["phase2"]

        return BenchmarkEvaluationSummary(
            evaluation_fy=self.evaluation_fy,
            determination_date=f"{self.evaluation_fy}-06-01",
            transition_window=p1_window,
            transition_phase2_window=p2_window,
            commercialization_window=self.commercialization_window,
            total_companies_evaluated=len(company_counts),
            companies_subject_to_transition=sum(
                1 for r in transition_results if r.tier != BenchmarkTier.NOT_SUBJECT
            ),
            companies_subject_to_commercialization=sum(
                1 for r in commercialization_results if r.tier != BenchmarkTier.NOT_SUBJECT
            ),
            companies_failing_transition=sum(
                1 for r in transition_results if r.status == BenchmarkStatus.FAIL
            ),
            companies_failing_commercialization=sum(
                1 for r in commercialization_results if r.status == BenchmarkStatus.FAIL
            ),
            transition_results=transition_results,
            commercialization_results=commercialization_results,
            sensitivity_results=sensitivity_results,
        )

    def evaluate_single_company(
        self,
        awards_df: pd.DataFrame,
        company_id: str,
        commercialization_df: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        """Evaluate benchmarks for a single company.

        Filters the awards_df to the specified company and returns a dict
        with transition_rate, commercialization_rate, and sensitivity results.
        """
        # Try to filter by various company ID columns
        df = awards_df.copy()
        df["_company_id"] = _company_id_series(df)

        company_df = df[df["_company_id"] == company_id]
        if company_df.empty:
            # Try matching by name substring
            name_col = _first_col(df, ["Company", "company", "company_name"])
            if name_col:
                company_df = df[
                    df[name_col].astype(str).str.lower().str.contains(
                        company_id.lower(), na=False
                    )
                ]

        if company_df.empty:
            return {
                "error": f"No awards found for company: {company_id}",
                "company_id": company_id,
            }

        summary = self.evaluate(company_df, commercialization_df)

        if summary.transition_results:
            tr = summary.transition_results[0]
            cr = summary.commercialization_results[0] if summary.commercialization_results else None
            sr = summary.sensitivity_results[0] if summary.sensitivity_results else None
            return {
                "transition_rate": tr.to_dict(),
                "commercialization_rate": cr.to_dict() if cr else None,
                "sensitivity": sr.to_dict() if sr else None,
            }

        return {"error": "Evaluation produced no results", "company_id": company_id}

    def get_companies_at_risk(
        self,
        awards_df: pd.DataFrame,
        commercialization_df: pd.DataFrame | None = None,
    ) -> list[SensitivityResult]:
        """Return only companies flagged as at-risk in sensitivity analysis."""
        summary = self.evaluate(awards_df, commercialization_df)
        return [
            sr
            for sr in summary.sensitivity_results
            if sr.at_risk_transition or sr.at_risk_commercialization
        ]

    def generate_report(
        self,
        summary: BenchmarkEvaluationSummary,
    ) -> str:
        """Generate a human-readable markdown report from evaluation results."""
        lines = [
            "# SBIR/STTR Benchmark Eligibility Report",
            "",
            f"**Evaluation Fiscal Year:** {summary.evaluation_fy}",
            f"**Determination Date:** {summary.determination_date}",
            "",
            "## Evaluation Windows",
            "",
            f"- **Transition Rate Window (Phase I):** "
            f"FY {summary.transition_window.start_fy}–{summary.transition_window.end_fy}",
            f"- **Transition Rate Window (Phase II):** "
            f"FY {summary.transition_phase2_window.start_fy}–{summary.transition_phase2_window.end_fy}",
            f"- **Commercialization Rate Window:** "
            f"FY {summary.commercialization_window.start_fy}–{summary.commercialization_window.end_fy}",
            "",
            "## Summary Statistics",
            "",
            f"- Total companies evaluated: **{summary.total_companies_evaluated}**",
            f"- Subject to transition benchmark: **{summary.companies_subject_to_transition}**",
            f"- Subject to commercialization benchmark: **{summary.companies_subject_to_commercialization}**",
            f"- Failing transition benchmark: **{summary.companies_failing_transition}**",
            f"- Failing commercialization benchmark: **{summary.companies_failing_commercialization}**",
            "",
        ]

        # Transition rate details — failures first
        def _tr_row(r: TransitionRateResult) -> str:
            ratio_str = f"{r.transition_ratio:.2%}" if r.transition_ratio is not None else "N/A"
            req_str = f"{r.required_ratio:.0%}" if r.required_ratio is not None else "N/A"
            name = r.company_name or r.company_id
            return (
                f"| {name} | {r.phase1_count} | {r.phase2_count} | "
                f"{ratio_str} | {req_str} | {r.tier.value} | {r.consequence.value} |"
            )

        tr_header = [
            "| Company | Phase I | Phase II | Ratio | Required | Tier | Consequence |",
            "|---------|---------|----------|-------|----------|------|-------------|",
        ]
        for label, status in [("Failing", BenchmarkStatus.FAIL), ("Passing", BenchmarkStatus.PASS)]:
            rows = [
                r for r in summary.transition_results
                if r.status == status and r.tier != BenchmarkTier.NOT_SUBJECT
            ]
            if rows:
                lines.extend([f"## {label} Transition Rate Benchmark", ""] + tr_header)
                lines.extend(_tr_row(r) for r in rows)
                lines.append("")

        # Commercialization rate details — failures first
        def _cr_row(r: CommercializationRateResult) -> str:
            sales_str = f"${r.avg_sales_per_phase2:,.0f}" if r.avg_sales_per_phase2 is not None else "N/A"
            pat_str = f"{r.patent_rate:.1%}" if r.patent_rate is not None else "N/A"
            name = r.company_name or r.company_id
            return (
                f"| {name} | {r.phase2_count} | "
                f"{sales_str} | {pat_str} | {r.tier.value} | {r.consequence.value} |"
            )

        cr_header = [
            "| Company | Phase II | Avg Sales | Patent Rate | Tier | Consequence |",
            "|---------|----------|-----------|-------------|------|-------------|",
        ]
        for label, status in [("Failing", BenchmarkStatus.FAIL), ("Passing", BenchmarkStatus.PASS)]:
            rows = [
                r for r in summary.commercialization_results
                if r.status == status and r.tier != BenchmarkTier.NOT_SUBJECT
            ]
            if rows:
                lines.extend([f"## {label} Commercialization Rate Benchmark", ""] + cr_header)
                lines.extend(_cr_row(r) for r in rows)
                lines.append("")

        # Sensitivity analysis
        at_risk = [
            sr for sr in summary.sensitivity_results
            if sr.at_risk_transition or sr.at_risk_commercialization
        ]
        if at_risk:
            lines.extend([
                "## Sensitivity Analysis: Companies Near Thresholds",
                "",
                "| Company | Phase I | To Std Trans | To Inc Trans | Phase II (Comm) | To Std Comm | Risk |",
                "|---------|---------|-------------|-------------|-----------------|-------------|------|",
            ])
            for sr in at_risk:
                name = sr.company_name or sr.company_id
                risks = []
                if sr.at_risk_transition:
                    risks.append("Transition")
                if sr.at_risk_commercialization:
                    risks.append("Commercialization")
                risk_str = ", ".join(risks)
                lines.append(
                    f"| {name} | {sr.phase1_count} | "
                    f"{sr.phase1_to_standard_transition} | "
                    f"{sr.phase1_to_increased_transition} | "
                    f"{sr.phase2_count_for_commercialization} | "
                    f"{sr.phase2_to_standard_commercialization} | "
                    f"{risk_str} |"
                )
            lines.append("")

        lines.extend([
            "## Benchmark Rules Reference",
            "",
            "### Phase I to Phase II Transition Rate",
            "- **Standard:** >=21 Phase I awards -> ratio must be >= 0.25",
            "- **Increased (experienced):** >=51 Phase I awards -> ratio must be >= 0.50",
            "- **Consequence (standard fail):** Ineligible for Phase I awards for 1 year",
            "- **Consequence (increased fail):** Capped at 20 Phase I awards per agency",
            "",
            "### Commercialization Rate",
            "- **Standard:** >=16 Phase II awards -> avg $100K+ sales/investment per Phase II, "
            "OR >= 15% patents per Phase II",
            "- **Increased Tier 1:** >=51 Phase II awards -> avg $250K+ (no patent path)",
            "- **Increased Tier 2:** >=101 Phase II awards -> avg $450K+ (no patent path)",
            "",
        ])

        return "\n".join(lines)


__all__ = ["BenchmarkEligibilityEvaluator"]
