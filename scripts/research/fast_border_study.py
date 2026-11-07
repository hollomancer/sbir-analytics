"""FAST border study: cross-border county-pair comparison of SBIR Phase I activity.

Exploratory tier (docs/steering/epistemic-tiers.md). Non-citable. This module
implements design A of docs/research/fast-border-discontinuity.md: a
Lanahan & Feldman (2018) style comparison of SBIR outcomes in counties that
straddle a state border, where one side's state has an active SBA FAST
cooperative agreement in that fiscal year and the other's does not.

Estimator
---------
Conditional (fixed-effects) Poisson with pair x year fixed effects. With two
units per pair-year the conditional likelihood reduces to a binomial on the
split of awards between the two sides, with pair dummies absorbing the
time-invariant county-quality difference. The coefficient on
`dF = fast_A - fast_B` is the log ratio of expected awards attributable to
FAST availability.

Inference
---------
Model-based standard errors are NOT valid here: treatment is assigned at the
state x year level while observations are county pairs, so the model SE
understates uncertainty by an order of magnitude. Inference is randomization
based -- the observed FAST year-profiles are permuted across states and the
estimator refit, giving both a p-value and a minimum detectable effect.

Geography
---------
County and coordinates come from the PatentsView disambiguated location table
already in the repo (data/raw/uspto/patentsview/g_location_disambiguated.tsv.zip),
joined to award records on upper-cased city + state. No external crosswalk is
required.

Usage:
    python scripts/research/fast_border_study.py \
        --awards data/raw/sbir/award_data.csv \
        --locations data/raw/uspto/patentsview/g_location_disambiguated.tsv.zip \
        --fast data/reference/fast/fast_awards_fy2010_2024.csv \
        --bands 40 60 --draws 300 --out reports/fast-border/
"""

from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.spatial import cKDTree

EARTH_KM = 6371.0088
FY_MIN, FY_MAX = 2010, 2024

STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}
CONTIGUOUS = {v for v in STATE_ABBR.values() if v not in {"AK", "HI"}}


def _unit_sphere(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    la, lo = np.radians(lat), np.radians(lon)
    return np.column_stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def _chord_to_km(chord: np.ndarray) -> np.ndarray:
    return 2 * EARTH_KM * np.arcsin(np.clip(chord / 2, 0, 1))


def load_locations(path: Path) -> pd.DataFrame:
    """city+state -> county FIPS and mean coordinates, from PatentsView."""
    with zipfile.ZipFile(path) as zf:
        with zf.open(zf.namelist()[0]) as fh:
            loc = pd.read_csv(
                io.TextIOWrapper(fh, "utf-8"), sep="\t", quotechar='"',
                usecols=["disambig_city", "disambig_state", "disambig_country",
                         "latitude", "longitude", "state_fips", "county_fips"],
                low_memory=False,
            )
    loc = loc[(loc.disambig_country == "US") & loc.latitude.notna()
              & loc.state_fips.notna() & loc.county_fips.notna()].copy()
    loc["city_k"] = loc.disambig_city.astype(str).str.upper().str.strip()
    loc["st"] = loc.disambig_state.astype(str).str.upper().str.strip()
    loc["fips"] = (loc.state_fips.astype(int).astype(str).str.zfill(2)
                   + loc.county_fips.astype(int).astype(str).str.zfill(3))
    return (loc.groupby(["city_k", "st"])
               .agg(lat=("latitude", "mean"), lon=("longitude", "mean"),
                    fips=("fips", lambda s: s.mode().iat[0]))
               .reset_index())


def load_awards(path: Path) -> pd.DataFrame:
    """Phase I awards in the study window, with a firm key and first-time flag."""
    cols = ["Company", "Phase", "Award Year", "UEI", "Duns", "City", "State"]
    raw = pd.read_csv(path, usecols=cols, low_memory=False)
    raw["yr"] = pd.to_numeric(raw["Award Year"], errors="coerce")
    phase1 = raw[raw.Phase == "Phase I"].copy()
    firm = phase1["UEI"].fillna("").astype(str).str.strip()
    for alt in ("Duns", "Company"):
        blank = firm.isin(["", "nan"])
        firm = firm.where(~blank, phase1[alt].fillna("").astype(str).str.upper().str.strip())
    phase1["firm"] = firm
    first_year = phase1.groupby("firm").yr.min()
    window = phase1[(phase1.yr >= FY_MIN) & (phase1.yr <= FY_MAX)].copy()
    window["st"] = window.State.map(STATE_ABBR)
    window["city_k"] = window.City.astype(str).str.upper().str.strip()
    window = window[window.st.notna()].copy()
    window["is_ftw"] = (window.yr == window.firm.map(first_year)).astype(int)
    return window


def build_counties(xwalk: pd.DataFrame) -> pd.DataFrame:
    """County centroids plus nearest out-of-state county and distance."""
    counties = (xwalk.groupby(["fips", "st"])
                     .agg(lat=("lat", "mean"), lon=("lon", "mean"))
                     .reset_index())
    counties = counties[counties.st.isin(CONTIGUOUS)].reset_index(drop=True)
    pts = _unit_sphere(counties.lat.values, counties.lon.values)
    nbr_idx = np.full(len(counties), -1)
    nbr_km = np.full(len(counties), np.nan)
    for state in sorted(counties.st.unique()):
        other = counties.st.values != state
        tree = cKDTree(pts[other])
        src = np.where(other)[0]
        here = np.where(counties.st.values == state)[0]
        dist, j = tree.query(pts[here], k=1)
        nbr_idx[here] = src[j]
        nbr_km[here] = _chord_to_km(dist)
    counties["nbr_fips"] = counties.fips.values[nbr_idx]
    counties["nbr_st"] = counties.st.values[nbr_idx]
    counties["pair_km"] = nbr_km
    return counties


def fast_lookup(fast_csv: Path) -> tuple[set[tuple[str, int]], dict[str, set[int]]]:
    panel = pd.read_csv(fast_csv)
    funded = {(r.state, int(r.fiscal_year)) for r in panel.itertuples()}
    profiles = {s: set(panel[panel.state == s].fiscal_year.astype(int)) for s in panel.state.unique()}
    return funded, profiles


def build_pairs(awards: pd.DataFrame, xwalk: pd.DataFrame, counties: pd.DataFrame,
                funded: set[tuple[str, int]]) -> pd.DataFrame:
    """One row per (cross-border county pair, year) with counts on both sides."""
    geo = awards.merge(xwalk, on=["city_k", "st"], how="left")
    geo = geo[geo.fips.notna()]
    counts = geo.groupby(["fips", "yr"]).agg(p1=("firm", "size"), ftw=("is_ftw", "sum"))
    p1 = counts.p1.to_dict()
    ftw = counts.ftw.to_dict()
    active = set(geo.fips.unique())
    state_of = counties.set_index("fips").st.to_dict()
    rows = []
    for c in counties.itertuples():
        if c.fips not in active and c.nbr_fips not in active:
            continue
        pair = "_".join(sorted([c.fips, c.nbr_fips]))
        for year in range(FY_MIN, FY_MAX + 1):
            rows.append((pair, c.fips, c.nbr_fips, c.st, state_of.get(c.nbr_fips), year,
                         p1.get((c.fips, year), 0), p1.get((c.nbr_fips, year), 0),
                         ftw.get((c.fips, year), 0), ftw.get((c.nbr_fips, year), 0),
                         c.pair_km))
    pairs = pd.DataFrame(rows, columns=["pair", "fipsA", "fipsB", "stA", "stB", "yr",
                                        "yA", "yB", "ftwA", "ftwB", "pair_km"])
    pairs["fA"] = [1 if (s, y) in funded else 0 for s, y in zip(pairs.stA, pairs.yr)]
    pairs["fB"] = [1 if (s, y) in funded else 0 for s, y in zip(pairs.stB, pairs.yr)]
    pairs["dF"] = pairs.fA - pairs.fB
    return canonicalize(pairs)


def canonicalize(pairs: pd.DataFrame) -> pd.DataFrame:
    """One row per unordered pair-year, oriented by the lower FIPS.

    Every county nominates its nearest out-of-state county, so a reciprocal
    nomination emits the same unordered pair twice with the sides swapped. Both
    rows carry the same pair id, so leaving them in would force a single pair
    fixed effect to serve two mirrored orientations -- an internally
    inconsistent model. Reorient (do not drop: filtering on fipsA < fipsB would
    silently delete every non-reciprocal pair nominated by the higher FIPS) and
    then de-duplicate.
    """
    out = pairs.copy()
    flip = (out.fipsA > out.fipsB).values
    for a, b in [("fipsA", "fipsB"), ("stA", "stB"), ("yA", "yB"), ("ftwA", "ftwB"), ("fA", "fB")]:
        left = out[a].values.copy()
        right = out[b].values.copy()
        out.loc[flip, a] = right[flip]
        out.loc[flip, b] = left[flip]
    out.loc[flip, "dF"] = -out.loc[flip, "dF"].values
    out = out.drop_duplicates(["pair", "yr"]).reset_index(drop=True)
    assert (out.fipsA < out.fipsB).all()
    return out


def estimation_sample(pairs: pd.DataFrame, band_km: float,
                      outcome: str = "p1") -> pd.DataFrame:
    """Pair-years that carry information about the treatment coefficient."""
    a, b = ("yA", "yB") if outcome == "p1" else ("ftwA", "ftwB")
    s = pairs[pairs.pair_km <= band_km].copy()
    s["y"] = s[a].values
    s["n"] = s[a].values + s[b].values
    s = s[s.n > 0]
    # the pair fixed effect absorbs any pair whose dF never changes
    varies = s.groupby("pair").dF.nunique()
    s = s[s.pair.isin(varies[varies > 1].index)]
    # a pair with all-or-nothing outcomes is separated; its FE diverges
    totals = s.groupby("pair").agg(sy=("y", "sum"), sn=("n", "sum"))
    usable = totals[(totals.sy > 0) & (totals.sy < totals.sn)].index
    s = s[s.pair.isin(usable)].reset_index(drop=True)
    s["g"] = pd.factorize(s.pair)[0]
    return s


def _fit(sample: pd.DataFrame, regressors: np.ndarray) -> np.ndarray:
    """Conditional Poisson as a grouped binomial, pair fixed effects profiled out.

    logit(p_it) = alpha_pair + x_it . beta, with y_it successes of n_it. The
    pair fixed effects are concentrated out by inner Newton steps, so no dummy
    matrix is ever formed -- a dense design over a few hundred pairs costs
    double-digit gigabytes and constrains the reference pair incorrectly unless
    an intercept is added alongside the dropped column.
    """
    x = np.atleast_2d(regressors.T).T
    g = sample.g.values
    y = sample.y.values.astype(float)
    n = sample.n.values.astype(float)
    n_groups = int(g.max()) + 1

    def nll(beta: np.ndarray) -> float:
        beta = np.atleast_1d(np.asarray(beta, dtype=float))
        alpha = np.zeros(n_groups)
        eta = alpha[g] + x @ beta
        for _ in range(60):
            p = 1.0 / (1.0 + np.exp(-eta))
            score = np.bincount(g, y - n * p, minlength=n_groups)
            hess = np.bincount(g, n * p * (1 - p), minlength=n_groups)
            step = np.clip(score / np.maximum(hess, 1e-9), -5, 5)
            alpha = alpha + step
            eta = alpha[g] + x @ beta
            if np.max(np.abs(step)) < 1e-9:
                break
        return float(-np.sum(y * eta - n * np.logaddexp(0.0, eta)))

    if x.shape[1] == 1:
        best = minimize_scalar(nll, bounds=(-5, 5), method="bounded",
                               options={"xatol": 1e-7})
        return np.array([best.x])
    best = minimize(nll, np.zeros(x.shape[1]), method="Nelder-Mead",
                    options={"xatol": 1e-6, "fatol": 1e-6, "maxiter": 4000})
    return best.x


def randomization_inference(pairs: pd.DataFrame, profiles: dict[str, set[int]],
                            band_km: float, outcome: str, observed: float,
                            draws: int, seed: int = 5) -> dict:
    """Permute observed FAST year-profiles across states and refit.

    Treatment is assigned at state x fiscal year while observations are county
    pairs, so model-based standard errors are invalid. The sample filters are
    part of the estimator and are therefore re-applied inside every draw.
    """
    rng = np.random.default_rng(seed)
    states = sorted(set(pairs.stA) | set(pairs.stB))
    profile_list = [profiles.get(s, set()) for s in states]
    out = []
    for _ in range(draws):
        perm = rng.permutation(len(states))
        mapped = {states[i]: profile_list[perm[i]] for i in range(len(states))}
        draw = pairs.copy()
        draw["dF"] = [(1 if y in mapped.get(sa, set()) else 0)
                      - (1 if y in mapped.get(sb, set()) else 0)
                      for sa, sb, y in zip(draw.stA, draw.stB, draw.yr)]
        sample = estimation_sample(draw, band_km, outcome)
        if sample.empty or sample.dF.nunique() < 2:
            continue
        try:
            out.append(float(_fit(sample, sample.dF.values)[0]))
        except Exception:  # pragma: no cover - singular permutation
            continue
    arr = np.array(out)
    return {
        "ri_draws": len(arr),
        "ri_p": float((np.abs(arr) >= abs(observed)).mean()) if len(arr) else float("nan"),
        "mde_pct": float(100 * 2.8 * arr.std(ddof=1)) if len(arr) > 1 else float("nan"),
    }


def pretrend_test(pairs: pd.DataFrame, band_km: float, outcome: str,
                  lead: int) -> dict:
    """Placebo: can FAST status `lead` years in the future move today's awards?

    Future treatment cannot cause past outcomes. A large negative coefficient
    here means treated states were already diverging downward from their
    cross-border neighbours before FAST arrived, which falsifies the parallel
    trends assumption the design rests on.
    """
    future = pairs.set_index(["pair", "yr"]).dF
    framed = pairs.copy()
    framed["lead"] = [future.get((p, y + lead), np.nan)
                      for p, y in zip(framed.pair, framed.yr)]
    framed = framed[framed["lead"].notna()]
    sample = estimation_sample(framed, band_km, outcome)
    if sample.empty or sample["lead"].nunique() < 2:
        return {}
    now = float(_fit(sample, sample.dF.values)[0])
    fut = float(_fit(sample, sample["lead"].values)[0])
    return {
        "lead_years": lead,
        "pair_years": int(len(sample)),
        "current_pct": round(100 * (np.exp(now) - 1), 2),
        "future_pct": round(100 * (np.exp(fut) - 1), 2),
    }


def run_band(pairs: pd.DataFrame, profiles: dict[str, set[int]], band_km: float,
             outcome: str, draws: int) -> dict:
    sample = estimation_sample(pairs, band_km, outcome)
    beta = float(_fit(sample, sample.dF.values)[0])
    row = {
        "outcome": outcome,
        "band_km": band_km,
        "pairs": int(sample.pair.nunique()),
        "pair_years": int(len(sample)),
        "awards": int(sample.n.sum()),
        "beta": round(beta, 4),
        "pct_effect": round(100 * (np.exp(beta) - 1), 2),
    }
    row.update(randomization_inference(pairs, profiles, band_km, outcome, beta, draws))
    volume = sample.groupby("pair").n.sum().sort_values(ascending=False)
    trimmed = sample[~sample.pair.isin(volume.head(5).index)]
    if trimmed.pair.nunique() > 2:
        trimmed = trimmed.assign(g=pd.factorize(trimmed.pair)[0])
        beta_trim = float(_fit(trimmed, trimmed.dF.values)[0])
        row["pct_effect_drop_top5"] = round(100 * (np.exp(beta_trim) - 1), 2)
        row["top5_award_share"] = round(float(volume.head(5).sum() / volume.sum()), 3)
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--awards", type=Path, required=True)
    ap.add_argument("--locations", type=Path, required=True)
    ap.add_argument("--fast", type=Path, required=True)
    ap.add_argument("--bands", type=float, nargs="+", default=[40, 60])
    ap.add_argument("--outcomes", nargs="+", default=["p1"], choices=["p1", "ftw"])
    ap.add_argument("--draws", type=int, default=300)
    ap.add_argument("--leads", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    xwalk = load_locations(args.locations)
    awards = load_awards(args.awards)
    counties = build_counties(xwalk)
    funded, profiles = fast_lookup(args.fast)
    pairs = build_pairs(awards, xwalk, counties, funded)

    results = [run_band(pairs, profiles, band, outcome, args.draws)
               for outcome in args.outcomes for band in args.bands]
    table = pd.DataFrame(results)
    pre_rows = []
    for outcome in args.outcomes:
        for band in args.bands:
            for k in args.leads:
                row = pretrend_test(pairs, band, outcome, k)
                if row:
                    pre_rows.append(dict(band_km=band, outcome=outcome, **row))
    pre = pd.DataFrame(pre_rows)
    args.out.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out / "fast_border_results.csv", index=False)
    pairs.to_parquet(args.out / "fast_border_pairs.parquet")
    print(table.to_string(index=False))
    if not pre.empty:
        pre.to_csv(args.out / "fast_border_pretrend.csv", index=False)
        print("\npre-trend placebo (future treatment on today's awards):")
        print(pre.to_string(index=False))


if __name__ == "__main__":
    main()
