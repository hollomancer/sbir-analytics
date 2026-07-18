"""Right-censored survival of time-to-Phase-III — why the '~Ny median lag' is not a median.

External review (see eval-validity.md) flagged that any median time-to-event computed over firms that
*experienced* the event is right-censored: firms that will transition later, or never, are excluded, so the
observed median underestimates the truth. This is Kaplan-Meier territory.

Cohort: DoD SBIR firms, origin = earliest DoD SBIR award year. Event = first coded DoD Phase III
(m0a_coded_dod `fy`). Firms with no observed Phase III are CENSORED at the observation end (2025).

Two readings:
  (a) naive conditional median lag over event-only firms (the figure the review warns about);
  (b) Kaplan-Meier survival on a left-truncation-free sub-cohort (firms first entering DoD SBIR within the
      Phase III observation window, 2016+), so transitions are observable across the whole follow-up.

Left-truncation caveat: coded Phase III is only observed ~2016-2025, so a pre-2016 entrant's early Phase III
is unobservable — hence (b) restricts the origin to >=2016. This shrinks follow-up (can't see long lags) but
removes the truncation bias; (a) and (b) bound the truth from opposite sides.
"""

import argparse
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
    for t in sorted(set(int(x) for x in lag)):
        at_risk = int((lag >= t).sum())
        deaths = int(((lag == t) & is_event).sum())
        if at_risk:
            step *= 1 - deaths / at_risk
        survival[t] = step
    return survival


def survival_at(curve: dict[int, float], t: int) -> float:
    return curve[max(k for k in curve if k <= t)]


def build_cohort(award_csv: Path, coded_parquet: Path) -> pd.DataFrame:
    awards = pd.read_csv(award_csv, dtype=str, keep_default_na=False)
    awards = awards[(awards["UEI"].str.len() > 5) &
                    (awards["Agency"] == "Department of Defense")].copy()
    year = awards["Proposal Award Date"].map(_year)
    awards["ay"] = year.fillna(pd.to_numeric(awards["Solicitation Year"], errors="coerce"))
    awards = awards[(awards["ay"] >= 1983) & (awards["ay"] <= OBS_END)]
    entry = awards.groupby("UEI")["ay"].min().astype(int)

    coded = pd.read_parquet(coded_parquet)
    coded["ey"] = pd.to_numeric(coded["fy"], errors="coerce")
    event_year = coded.dropna(subset=["ey"]).groupby("uei")["ey"].min().astype(int)

    cohort = pd.DataFrame({"entry": entry})
    cohort["event_yr"] = cohort.index.map(event_year)
    cohort["is_event"] = cohort["event_yr"].notna() & (cohort["event_yr"] >= cohort["entry"])
    cohort["lag"] = np.where(cohort["is_event"], cohort["event_yr"] - cohort["entry"],
                             OBS_END - cohort["entry"])
    return cohort[cohort["lag"] >= 0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--coded", type=Path, default=Path("data/derived/m0a_coded_dod.parquet"))
    args = parser.parse_args(argv)
    cohort = build_cohort(args.awards, args.coded)

    n, events = len(cohort), int(cohort["is_event"].sum())
    print(f"DoD SBIR cohort: {n} firms | observed Phase III: {events} ({100 * events / n:.0f}%) | "
          f"censored: {n - events}\n")
    conditional = cohort.loc[cohort["is_event"], "lag"]
    print("(a) NAIVE conditional median lag (event-only — the figure the review warns about):")
    print(f"    n={len(conditional)}  median {conditional.median():.0f}y  mean {conditional.mean():.1f}y "
          f"— conditional on transitioning in-window AND right-censored (true >= this)\n")

    clean = cohort[cohort["entry"] >= 2016]
    curve = kaplan_meier(clean["lag"].to_numpy(), clean["is_event"].to_numpy())
    print(f"(b) Kaplan-Meier, left-truncation-free (first DoD SBIR 2016+, n={len(clean)}, "
          f"events={int(clean['is_event'].sum())}):")
    for t in (2, 3, 5, 7):
        if any(k >= t for k in curve):
            print(f"    transitioned by year {t}: {100 * (1 - survival_at(curve, t)):.1f}%")
    reached = [t for t in sorted(curve) if curve[t] <= 0.5]
    verdict = f"{reached[0]}y" if reached else f">{int(clean['lag'].max())}y — NOT REACHED (<50% ever transition)"
    print(f"    KM median time-to-Phase-III: {verdict}")
    print("\n  Unconditional median is UNDEFINED; the naive conditional figure is a right-censored lower bound.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
