"""Per-firm wide-format aggregator over the long-format events table."""

import pandas as pd


def summarize_per_firm(events: pd.DataFrame, cohort: list[dict]) -> pd.DataFrame:
    """Aggregate events to one row per cohort firm.

    Inputs:
      events: long-format events DataFrame with columns matching the
              CapitalEvent schema.
      cohort: list of cohort row dicts; every cohort firm is represented
              in the output even when it has zero events.

    Returns DataFrame with one row per firm, columns documented in the
    spec's "Wide-format per-firm summary" section.
    """
    cohort_df = pd.DataFrame(cohort)

    if events.empty:
        agg = pd.DataFrame(columns=["company_name"])
    else:
        by_firm_type = events.groupby(
            ["company_name", "event_type"], dropna=False
        ).agg(
            count=("source_id", "size"),
            total_amount=("amount_usd", "sum"),
            first_date=("event_date", "min"),
        ).reset_index()
        counts = by_firm_type.pivot(
            index="company_name", columns="event_type", values="count"
        ).fillna(0).astype(int)
        sums = by_firm_type.pivot(
            index="company_name", columns="event_type", values="total_amount"
        ).fillna(0.0)
        firsts = by_firm_type.pivot(
            index="company_name", columns="event_type", values="first_date"
        )
        firms = counts.index.union(sums.index).union(firsts.index)

        def _counts_col(name: str) -> pd.Series:
            return counts[name] if name in counts.columns else pd.Series(0, index=firms, dtype=int)

        def _sums_col(name: str) -> pd.Series:
            return sums[name] if name in sums.columns else pd.Series(0.0, index=firms, dtype=float)

        def _firsts_col(name: str) -> pd.Series:
            return firsts[name] if name in firsts.columns else pd.Series(None, index=firms, dtype=object)

        def _year_from(name: str) -> pd.Series:
            col = _firsts_col(name)
            return col.map(lambda s: int(s[:4]) if isinstance(s, str) and len(s) >= 4 else None)

        agg = pd.DataFrame(
            {
                "sbir_award_count": _counts_col("sbir_award"),
                "total_sbir_amount": _sums_col("sbir_award"),
                "form_d_filing_count": _counts_col("form_d_filing"),
                "total_form_d_raised": _sums_col("form_d_filing"),
                "ma_event_count": _counts_col("ma_event"),
                "first_ma_event_date": _firsts_col("ma_event"),
                "usaspending_contract_count": _counts_col("usaspending_contract"),
                "total_usaspending_obligated": _sums_col("usaspending_contract"),
                "first_usaspending_year": _year_from("usaspending_contract"),
                "patent_count": _counts_col("patent_grant"),
                "first_patent_year": _year_from("patent_grant"),
                "ucc_filing_count": _counts_col("ucc_filing"),
            },
            index=firms,
        )
        agg.index.name = "company_name"
        agg = agg.reset_index()

        first_overall = events.groupby("company_name")["event_date"].min()
        last_overall = events.groupby("company_name")["event_date"].max()
        type_count = events.groupby("company_name")["event_type"].nunique()
        agg["first_event_date"] = agg["company_name"].map(first_overall)
        agg["last_event_date"] = agg["company_name"].map(last_overall)
        agg["event_type_count"] = agg["company_name"].map(type_count).fillna(0).astype(int)

        ma_only = events[events["event_type"] == "ma_event"]
        if not ma_only.empty:
            ma_max_tier = (
                ma_only.groupby("company_name")["event_subtype"]
                .apply(lambda s: "high" if (s == "high").any() else "medium")
            )
            agg["ma_confidence_max_tier"] = agg["company_name"].map(ma_max_tier)
        else:
            agg["ma_confidence_max_tier"] = None

    # Drop any cohort columns that would clash with computed aggregate columns
    # (e.g. form_d_filing_count / form_d_total_raised that some cohort schemas carry)
    agg_cols = set(agg.columns) - {"company_name"}
    cohort_df = cohort_df.drop(columns=[c for c in cohort_df.columns if c in agg_cols])
    result = cohort_df.merge(agg, on="company_name", how="left")
    fill_zero_int_cols = [
        "sbir_award_count", "form_d_filing_count", "ma_event_count",
        "usaspending_contract_count", "patent_count", "ucc_filing_count",
        "event_type_count",
    ]
    fill_zero_float_cols = [
        "total_sbir_amount", "total_form_d_raised", "total_usaspending_obligated",
    ]
    for col in fill_zero_int_cols:
        if col in result.columns:
            result[col] = result[col].fillna(0).astype(int)
        else:
            result[col] = 0
    for col in fill_zero_float_cols:
        if col in result.columns:
            result[col] = result[col].fillna(0.0)
        else:
            result[col] = 0.0
    for col in ("first_event_date", "last_event_date", "first_ma_event_date",
                "ma_confidence_max_tier"):
        if col not in result.columns:
            result[col] = None
    result["has_ma_event"] = result["ma_event_count"] > 0
    result["has_ucc_match"] = result["ucc_filing_count"] > 0
    return result
