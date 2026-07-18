"""Time from first observed DoD Phase II to first later observed coded Phase III.

This is a bounded descriptive estimand. It is not verified award lineage and it
does not observe uncoded Phase III events. A median that is not reached during
follow-up is reported as not estimable, never as proof that firms do not transition.
"""

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

OBS_END = 2025


def _year(value: object) -> int | None:
    match = re.search(r"(19[89]\d|20[0-2]\d)", str(value))
    return int(match.group()) if match else None


def kaplan_meier(lag: np.ndarray, is_event: np.ndarray) -> dict[int, float]:
    """Kaplan-Meier survival S(t) from integer lags and event indicators. Pure."""
    survival, step = {0: 1.0}, 1.0
    for t in sorted({int(x) for x in lag}):
        at_risk = int((lag >= t).sum())
        deaths = int(((lag == t) & is_event).sum())
        if at_risk:
            step *= 1 - deaths / at_risk
        survival[t] = step
    return survival


def survival_at(curve: dict[int, float], t: int) -> float:
    return curve[max(k for k in curve if k <= t)]


def build_cohort_frames(awards: pd.DataFrame, coded: pd.DataFrame) -> pd.DataFrame:
    """Build one firm-level row using the earliest valid post-entry coded action."""
    awards = awards[(awards["UEI"].str.len() > 5) &
                    (awards["Agency"] == "Department of Defense")].copy()
    phase = awards["Phase"].astype(str).str.upper()
    awards = awards[phase.str.contains("II", na=False)
                    & ~phase.str.contains("III", na=False)].copy()
    year = awards["Proposal Award Date"].map(_year)
    awards["ay"] = year.fillna(pd.to_numeric(awards["Solicitation Year"], errors="coerce"))
    awards = awards[(awards["ay"] >= 1983) & (awards["ay"] <= OBS_END)]
    entry = awards.groupby("UEI")["ay"].min().astype(int)

    date_columns = [name for name in ("signed", "signedDate", "action_date", "effectiveDate")
                    if name in coded]
    if not date_columns:
        raise ValueError("coded frame requires an action-date column; FY-only modification rows are invalid")
    parsed = pd.concat(
        [pd.to_datetime(coded[name], errors="coerce", utc=True) for name in date_columns],
        axis=1,
    ).bfill(axis=1).iloc[:, 0]
    events = coded.assign(_event_year=parsed.dt.year).dropna(subset=["_event_year"])
    events_by_firm: dict[object, list[int]] = {
        uei: sorted(int(year) for year in group["_event_year"])
        for uei, group in events.groupby("uei", sort=False)
    }

    cohort = pd.DataFrame({"entry": entry})
    cohort["event_yr"] = [
        next((year for year in events_by_firm.get(uei, []) if year >= int(entry_year)), np.nan)
        for uei, entry_year in cohort["entry"].items()
    ]
    cohort["is_event"] = cohort["event_yr"].notna()
    cohort["lag"] = np.where(cohort["is_event"], cohort["event_yr"] - cohort["entry"],
                             OBS_END - cohort["entry"])
    return cohort[cohort["lag"] >= 0]


def build_cohort(award_csv: Path, coded_parquet: Path) -> pd.DataFrame:
    return build_cohort_frames(
        pd.read_csv(award_csv, dtype=str, keep_default_na=False),
        pd.read_parquet(coded_parquet),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--coded", type=Path, default=Path("data/derived/m0a_coded_dod.parquet"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    missing = [str(path) for path in (args.awards, args.coded) if not path.exists()]
    if missing:
        result = {"status": "blocked_missing_inputs", "missing": missing}
        payload = json.dumps(result, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload)
        print(payload, end="")
        return 0
    cohort = build_cohort(args.awards, args.coded)

    n, events = len(cohort), int(cohort["is_event"].sum())
    print(f"DoD Phase II cohort: {n} firms | observed coded Phase III: {events} ({100 * events / n:.0f}%) | "
          f"censored: {n - events}\n")
    conditional = cohort.loc[cohort["is_event"], "lag"]
    print("(a) Descriptive event-only lag (not a population bound):")
    print(f"    n={len(conditional)}  median {conditional.median():.0f}y  mean {conditional.mean():.1f}y "
          "— conditional on an observed coded event\n")

    clean = cohort[cohort["entry"] >= 2016]
    curve = kaplan_meier(clean["lag"].to_numpy(), clean["is_event"].to_numpy())
    print(f"(b) Kaplan-Meier, first observed DoD Phase II 2016+, n={len(clean)}, "
          f"events={int(clean['is_event'].sum())}):")
    for t in (2, 3, 5, 7):
        if any(k >= t for k in curve):
            print(f"    transitioned by year {t}: {100 * (1 - survival_at(curve, t)):.1f}%")
    reached = [t for t in sorted(curve) if curve[t] <= 0.5]
    verdict = f"{reached[0]}y" if reached else "NOT REACHED during observed follow-up"
    print(f"    KM median time-to-first-observed-coded-Phase-III: {verdict}")
    print("\n  This curve does not identify true Phase III latency or a never-transition fraction.")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({
            "status": "provisional",
            "estimand": "first observed DoD Phase II to first later observed coded Phase III action",
            "firms": n,
            "events": events,
            "median": verdict,
            "warnings": ["coded events only", "same-firm proxy; lineage unverified"],
        }, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
