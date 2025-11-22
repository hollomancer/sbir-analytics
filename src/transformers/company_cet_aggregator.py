"""
CompanyCETAggregator

Transforms award-level CET classifications (output of `cet_award_classifications`)
into company-level aggregated CET profiles suitable for downstream assets and loaders.

Key behaviors:
- Accepts award classification records as a pandas.DataFrame or an iterable of dicts.
- Aggregates per-company CET mean scores, computes dominant CET, and a specialization
  score (Herfindahl-Hirschman Index over CET score shares).
- Computes coverage metrics (fraction of a company's awards that received a CET).
- Produces optional CET time-evolution (by `phase` if present, otherwise by award year).
- Exposes `to_dataframe()` which returns a flattened dataframe ready to persist.

The implementation is defensive about optional dependencies: if `pandas` is not available,
the class will raise an informative ImportError when used.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


try:
    import numpy as np  # used for numeric safety
    import pandas as pd
except Exception:  # pragma: no cover - defensive import
    pd = None
    np = None  # type: ignore

__all__ = ["CompanyCETAggregator"]


class CompanyCETAggregator:
    """
    Aggregates award-level CET classifications to company-level CET profiles.

    Expected award-level input columns (preferred):
    - `award_id` (str)
    - `company_id` (str or int)
    - `company_name` (optional)
    - `primary_cet` (str) -- CET id
    - `primary_score` (float) -- primary CET score (numeric, typically 0-100)
    - `supporting_cets` (optional list[dict]) -- each dict with keys `cet_id` and `score`
    - `classified_at` (optional datetime-like)
    - `taxonomy_version` (optional)
    - `award_date` (optional date/datetime string)
    - `phase` (optional str; e.g., "I", "II", "III")

    The aggregator will treat `primary_cet` and any `supporting_cets` as CET evidence and
    include both in per-CET aggregations.
    """

    def __init__(self, awards: pd.DataFrame | Iterable[Mapping[str, Any]]) -> None:
        if pd is None:
            raise ImportError(
                "pandas is required for CompanyCETAggregator. Please install pandas to use this class."
            )

        # Normalize input into a DataFrame
        if isinstance(awards, pd.DataFrame):
            self.df = awards.copy()
        else:
            # Iterable[Mapping] -> DataFrame
            self.df = pd.DataFrame(list(awards))

        # Ensure columns exist
        default_cols = [
            "award_id",
            "company_id",
            "company_name",
            "primary_cet",
            "primary_score",
            "supporting_cets",
            "classified_at",
            "taxonomy_version",
            "award_date",
            "phase",
        ]
        for c in default_cols:
            if c not in self.df.columns:
                self.df[c] = None

        # Normalize types for some columns
        # supporting_cets should be list-like or None
        self.df["supporting_cets"] = self.df["supporting_cets"].apply(
            lambda v: v if isinstance(v, list | tuple) else []
        )

        # award_date -> datetime if possible
        try:
            self.df["award_date_parsed"] = pd.to_datetime(self.df["award_date"], errors="coerce")
        except Exception:
            # Best-effort fallback: leave as None/NaT if parsing fails
            self.df["award_date_parsed"] = pd.NaT

    @staticmethod
    def _extract_cet_rows_from_award(row: Mapping[str, Any]) -> list[tuple[str, float, str]]:
        """
        Given an award record (mapping), return list of (cet_id, score, award_id).
        Includes primary and supporting CETs. Scores are normalized to floats; missing scores
        are treated as 0.0.
        """
        rows: list[tuple[str, float, str]] = []
        award_id = str(row.get("award_id") or "")
        primary = row.get("primary_cet")
        primary_score = row.get("primary_score") or 0.0
        if primary:
            try:
                score = float(primary_score)
            except Exception:
                score = 0.0
            rows.append((str(primary), score, award_id))

        supporting = row.get("supporting_cets") or []
        if isinstance(supporting, list | tuple):
            for s in supporting:
                if not s:
                    continue
                # supporting may be dict-like or simple tuple/list
                if isinstance(s, Mapping):
                    cet_id = s.get("cet_id") or s.get("cet") or None
                    score_raw = s.get("score", 0.0)
                elif isinstance(s, list | tuple) and len(s) >= 2:
                    cet_id, score_raw = s[0], s[1]
                else:
                    # unsupported format; skip
                    cet_id = None
                    score_raw = 0.0
                if cet_id:
                    try:
                        sc = float(score_raw)
                    except Exception:
                        sc = 0.0
                    rows.append((str(cet_id), sc, award_id))
        return rows

    def _build_company_cet_matrix(self) -> pd.DataFrame:
        """
        Return a flattened DataFrame with columns:
        - company_id
        - company_name
        - award_id
        - cet_id
        - score
        - award_date_parsed
        - phase
        """
        records = []
        for _, row in self.df.iterrows():
            company_id = row.get("company_id")
            company_name = row.get("company_name")
            award_date = row.get("award_date_parsed", pd.NaT)
            phase = row.get("phase")
            cet_rows = self._extract_cet_rows_from_award(row)
            if not cet_rows:
                # keep a placeholder row to count awards_with_cet correctly later (no CETs)
                records.append(
                    {
                        "company_id": company_id,
                        "company_name": company_name,
                        "award_id": row.get("award_id"),
                        "cet_id": None,
                        "score": None,
                        "award_date_parsed": award_date,
                        "phase": phase,
                        "has_cet": False,
                    }
                )
                continue
            for cet_id, score, award_id in cet_rows:
                records.append(
                    {
                        "company_id": company_id,
                        "company_name": company_name,
                        "award_id": award_id,
                        "cet_id": cet_id,
                        "score": score,
                        "award_date_parsed": award_date,
                        "phase": phase,
                        "has_cet": True,
                    }
                )

        flat = pd.DataFrame(records)
        return flat

    @staticmethod
    def _hhi_from_scores(score_map: Mapping[str, float]) -> float:
        """
        Compute HHI (Herfindahl-Hirschman Index) from a dict of cet_id -> score.
        We convert scores to non-negative shares that sum to 1, then compute sum(share^2).
        Returns a float in range [0, 1]. If there is no signal, returns 0.0.
        """
        if not score_map:
            return 0.0
        total = sum(max(0.0, float(v)) for v in score_map.values())
        if total <= 0.0:
            return 0.0
        hhi = 0.0
        for v in score_map.values():
            share = max(0.0, float(v)) / total
            hhi += share * share
        # HHI is already in 0..1 (if shares sum to 1). Return as-is.
        return float(hhi)

    def aggregate_by_company(
        self, use_scores: str = "mean", include_supporting: bool = True, top_n_cets: int = 10
    ) -> pd.DataFrame:
        """
        Performs aggregation and returns a company-level DataFrame.

        Parameters:
        - use_scores: aggregation method for per-company per-CET scores. Options: 'mean' (default), 'median'.
        - include_supporting: whether to include supporting CETs in aggregations (default True).
        - top_n_cets: keep up to top N CETs in the `cet_scores` map (sorted by mean score).

        Returns:
        DataFrame with columns:
        - company_id
        - company_name
        - total_awards
        - awards_with_cet
        - coverage
        - dominant_cet
        - dominant_score
        - specialization_score
        - cet_scores (dict mapping cet_id -> mean_score)
        - first_award_date
        - last_award_date
        - cet_trend (dict mapping period -> {cet_id: share})
        """
        flat = self._build_company_cet_matrix()

        # Compute counts per company
        # total_awards: count distinct award_id per company
        company_award_counts = (
            flat.groupby("company_id")["award_id"].nunique().rename("total_awards").to_frame()
        )
        # awards_with_cet: count distinct award_id per company where has_cet is True
        awards_with_cet = (
            flat.loc[flat["has_cet"]]
            .groupby("company_id")["award_id"]
            .nunique()
            .rename("awards_with_cet")
            .to_frame()
        )
        stats = company_award_counts.join(awards_with_cet, how="left").fillna(0)
        stats["total_awards"] = stats["total_awards"].astype(int)
        stats["awards_with_cet"] = stats["awards_with_cet"].astype(int)
        stats["coverage"] = stats["awards_with_cet"] / stats["total_awards"].replace({0: 1})

        # Filter CET rows (if including supporting is False, keep only primary rows)
        if not include_supporting:
            # Heuristic: primary rows are those where score equals primary_score and cet matches primary_cet.
            # Since we don't have an explicit flag, attempt to keep only the highest score per award (best-effort).
            flat_primary = (
                flat.loc[flat["cet_id"].notnull()]
                .sort_values(["award_id", "score"], ascending=[True, False])
                .drop_duplicates(subset=["award_id"], keep="first")
            )
            cet_rows = flat_primary
        else:
            cet_rows = flat.loc[flat["cet_id"].notnull()]

        # Aggregate per company and cet
        if use_scores == "median":
            np.median if np is not None else lambda x: x.median()
        else:
            np.mean if np is not None else lambda x: x.mean()

        cet_group = cet_rows.groupby(["company_id", "cet_id"])["score"].agg(list).to_frame("scores")

        # compute aggregate (mean by default)
        def _agg_list(scores: list[float]) -> float:
            if not scores:
                return 0.0
            try:
                if use_scores == "median":
                    return (
                        float(np.median(scores))
                        if np is not None
                        else float(pd.Series(scores).median())
                    )
                return float(np.mean(scores)) if np is not None else float(pd.Series(scores).mean())
            except Exception:
                # last resort
                return float(sum(scores) / max(1, len(scores)))

        cet_group["agg_score"] = cet_group["scores"].apply(_agg_list)
        cet_group = cet_group.reset_index()  # columns: company_id, cet_id, scores, agg_score

        # Build per-company cet_scores mapping
        cet_scores_map: dict[Any, dict[str, float]] = defaultdict(dict)
        for _, r in cet_group.iterrows():
            cmp = r["company_id"]
            cid = r["cet_id"]
            sc = r["agg_score"]
            cet_scores_map[cmp][cid] = float(sc)

        # Build dominant CET and specialization
        rows: list[dict[str, Any]] = []
        company_ids = sorted(stats.index.tolist(), key=lambda x: (str(x) if x is not None else ""))
        for cid in company_ids:
            company_row = stats.loc[cid]
            c_name = self.df.loc[self.df["company_id"] == cid, "company_name"]
            company_name = c_name.dropna().unique().tolist()
            company_name = company_name[0] if company_name else None

            scores_map = cet_scores_map.get(cid, {})
            # Keep only top_n_cets
            if scores_map:
                sorted_items = sorted(scores_map.items(), key=lambda x: x[1], reverse=True)[
                    :top_n_cets
                ]
                trimmed_map = {k: float(v) for k, v in sorted_items}
            else:
                trimmed_map = {}

            dominant_cet = None
            dominant_score = None
            if trimmed_map:
                dominant_cet, dominant_score = max(trimmed_map.items(), key=lambda x: x[1])

            specialization = self._hhi_from_scores(trimmed_map)

            # date range
            company_awards = self.df.loc[self.df["company_id"] == cid]
            try:
                first_dt = pd.to_datetime(company_awards["award_date_parsed"].dropna()).min()
                last_dt = pd.to_datetime(company_awards["award_date_parsed"].dropna()).max()
            except Exception:
                first_dt = pd.NaT
                last_dt = pd.NaT

            # Build CET trend by period: prefer `phase`, else use year
            trend: dict[str, dict[str, float]] = {}
            # choose period column
            if company_awards["phase"].notnull().any():
                periods = company_awards[["award_id", "phase"]].drop_duplicates()
                # compute shares per phase by counting award-level primary CETs per phase, weighted by score
                for p in periods["phase"].dropna().unique():
                    part = company_awards.loc[company_awards["phase"] == p]
                    # build local cet score sums for this period
                    local_cet_totals: dict[str, float] = {}
                    for _, ar in part.iterrows():
                        for cet_id, sc, _ in self._extract_cet_rows_from_award(ar):
                            local_cet_totals[cet_id] = local_cet_totals.get(cet_id, 0.0) + float(sc)
                    total = sum(local_cet_totals.values()) or 0.0
                    if total > 0:
                        trend[p] = {k: v / total for k, v in local_cet_totals.items()}
                    else:
                        trend[p] = {}
            else:
                # use year
                try:
                    years = (
                        company_awards["award_date_parsed"]
                        .dropna()
                        .dt.year.astype(int)
                        .drop_duplicates()
                        .tolist()
                    )
                except Exception:
                    years = []
                for y in years:
                    part = company_awards.loc[company_awards["award_date_parsed"].dt.year == int(y)]
                    year_cet_totals: dict[str, float] = {}
                    for _, ar in part.iterrows():
                        for cet_id, sc, _ in self._extract_cet_rows_from_award(ar):
                            year_cet_totals[cet_id] = year_cet_totals.get(cet_id, 0.0) + float(sc)
                    total = sum(year_cet_totals.values()) or 0.0
                    if total > 0:
                        trend[str(int(y))] = {k: v / total for k, v in year_cet_totals.items()}
                    else:
                        trend[str(int(y))] = {}

            rows.append(
                {
                    "company_id": cid,
                    "company_name": company_name,
                    "total_awards": int(company_row["total_awards"]),
                    "awards_with_cet": int(company_row["awards_with_cet"]),
                    "coverage": float(company_row["coverage"]),
                    "dominant_cet": dominant_cet,
                    "dominant_score": float(dominant_score) if dominant_score is not None else None,
                    "specialization_score": float(specialization),
                    "cet_scores": trimmed_map,
                    "first_award_date": pd.Timestamp(first_dt) if not pd.isna(first_dt) else None,
                    "last_award_date": pd.Timestamp(last_dt) if not pd.isna(last_dt) else None,
                    "cet_trend": trend,
                }
            )

        result_df = pd.DataFrame(rows)
        # sort for deterministic order
        if not result_df.empty:
            result_df = result_df.sort_values(["company_id"]).reset_index(drop=True)
        return result_df

    def to_dataframe(self, **kwargs) -> pd.DataFrame:
        """
        Convenience wrapper for `aggregate_by_company`.
        Accepts same kwargs as `aggregate_by_company` and returns the DataFrame result.
        """
        return self.aggregate_by_company(**kwargs)

    # Small convenience utilities
    @staticmethod
    def specialization_from_cet_scores(cet_scores: Mapping[str, float]) -> float:
        """
        Public wrapper to compute specialization (HHI) from a cet_scores mapping.
        """
        return CompanyCETAggregator._hhi_from_scores(cet_scores)

    @staticmethod
    def serialize_row_for_storage(row: Mapping[str, Any]) -> dict[str, Any]:
        """
        Prepare a single company profile row for JSON/NDJSON storage. Ensures
        serializable types (datetimes -> ISO strings).
        """
        out = dict(row)
        # Convert pandas Timestamp to ISO string if present
        for k in ("first_award_date", "last_award_date"):
            v = out.get(k)
            if v is None:
                continue
            try:
                # pandas.Timestamp or datetime -> isoformat
                out[k] = v.isoformat()
            except Exception:
                out[k] = str(v)
        # Ensure cet_scores and cet_trend are JSON-serializable
        if "cet_scores" in out:
            out["cet_scores"] = out["cet_scores"] or {}
        if "cet_trend" in out:
            out["cet_trend"] = out["cet_trend"] or {}
        return out
