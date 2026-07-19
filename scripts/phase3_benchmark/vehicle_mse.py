"""Structure-stratified multi-list capture model for dark Phase III (code x order-text x vehicle-declaration).

Review-driven design (PR #458 methodology review):
- **Structural zero respected**: list C ("child of a self-declared Phase III vehicle") is only reachable for
  task orders — standalone contracts have no parent, so they are fit as a separate 2-list (A x B) stratum and
  the two dark cells are summed. Pooling them in one homogeneous ABC model is unidentified for the stated
  population.
- **Cluster-correct uncertainty**: C is assigned at vehicle level and expanded to correlated child orders, so
  CIs come from a block bootstrap — task-order units resampled by parent vehicle, standalone units iid.
- No "lower bound" semantics: every figure is a model-scenario estimate; dependence terms are reported per
  model with AIC, and the independence scenario is just one row. List precision (esp. C) is unadjudicated.

Inputs: the m0a coded/described parquets plus two frozen JSON caches committed under
`specs/phase3-match-benchmark/inputs/` (self-declared vehicle listing and their enumerated children). The CLI
emits a JSON result with input SHA-256s so the run is reproducible byte-for-byte against those caches.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

CELL_ORDER = [(1, 1, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
MODELS = [[], ["AB"], ["AC"], ["BC"], ["AB", "AC"], ["AB", "BC"], ["AC", "BC"], ["AB", "AC", "BC"]]


def _nk(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def coded_key(order_piid: object, idv_piid: object) -> tuple[str, str]:
    parent = _nk(idv_piid) if str(idv_piid).strip() not in ("", "None") else "NONE"
    return (_nk(order_piid), parent)


def described_key(gen_id: object) -> tuple[str, str] | None:
    match = re.match(r"CONT_AWD_([^_]+)_[^_]+_(.+)_[^_]+$", str(gen_id))
    if not match:
        return None
    parent = match.group(2)
    return (_nk(match.group(1)), "NONE" if parent == "-NONE-" else _nk(parent))


def build_units(a_keys: set, b_keys: set, c_keys: set) -> pd.DataFrame:
    """One row per captured unit with list membership, parent, and standalone flag."""
    rows = [{"parent": key[1], "a": key in a_keys, "b": key in b_keys, "c": key in c_keys,
             "standalone": key[1] == "NONE"} for key in (a_keys | b_keys | c_keys)]
    return pd.DataFrame(rows)


def chapman(n1: int, n2: int, m: int) -> float:
    """Chapman two-list estimator (an independence-scenario figure, not a bound)."""
    return (n1 + 1) * (n2 + 1) / (m + 1) - 1


def cell_counts(task_orders: pd.DataFrame) -> np.ndarray:
    pattern = task_orders.groupby(["a", "b", "c"]).size()
    return np.array([pattern.get((bool(p[0]), bool(p[1]), bool(p[2])), 0) for p in CELL_ORDER], float)


def _design(terms: list[str]) -> np.ndarray:
    base = {"1": np.ones(7),
            "A": np.array([p[0] for p in CELL_ORDER], float),
            "B": np.array([p[1] for p in CELL_ORDER], float),
            "C": np.array([p[2] for p in CELL_ORDER], float)}
    base["AB"], base["AC"], base["BC"] = base["A"] * base["B"], base["A"] * base["C"], base["B"] * base["C"]
    return np.column_stack([base[c] for c in ["1", "A", "B", "C"] + terms])


def loglinear_dark(cells: np.ndarray, terms: list[str]) -> dict | None:
    """Poisson log-linear on the 7 observed cells; returns AIC and the predicted 000 cell.

    IRLS initialized from least squares on log(n+0.5) — a zero init diverges on large counts.
    """
    design = _design(terms)
    beta, _, _, _ = np.linalg.lstsq(design, np.log(cells + 0.5), rcond=None)
    for _ in range(300):
        mu = np.exp(design @ beta)
        working = design @ beta + (cells - mu) / np.maximum(mu, 1e-9)
        weighted = design.T * mu
        try:
            beta_new = np.linalg.solve(weighted @ design, weighted @ working)
        except np.linalg.LinAlgError:
            return None
        if np.max(np.abs(beta_new - beta)) < 1e-10:
            beta = beta_new
            break
        beta = beta_new
    mu = np.exp(design @ beta)
    loglik = float(np.sum(cells * np.log(np.maximum(mu, 1e-12)) - mu))
    return {"aic": -2 * loglik + 2 * design.shape[1], "n000": float(np.exp(beta[0]))}


def stratified_dark(units: pd.DataFrame, terms: list[str]) -> dict | None:
    """Standalone AB-Chapman dark + task-order ABC log-linear dark. The structural-zero-correct estimate."""
    stand = units[units["standalone"]]
    n1, n2, m = int(stand["a"].sum()), int(stand["b"].sum()), int((stand["a"] & stand["b"]).sum())
    dark_stand = chapman(n1, n2, m) - (n1 + n2 - m)
    fitted = loglinear_dark(cell_counts(units[~units["standalone"]]), terms)
    if fitted is None:
        return None
    return {"dark_standalone": dark_stand, "dark_task_order": fitted["n000"],
            "dark_total": dark_stand + fitted["n000"], "aic_task_order": fitted["aic"]}


def block_bootstrap_ci(units: pd.DataFrame, terms: list[str], n_boot: int = 600,
                       seed: int = 0) -> tuple[float, float]:
    """95% CI for total dark: standalone units iid, task orders resampled by parent vehicle (cluster)."""
    rng = np.random.RandomState(seed)
    stand = units[units["standalone"]][["a", "b"]].values
    clusters = [g[["a", "b", "c"]].values for _, g in units[~units["standalone"]].groupby("parent")]
    estimates = []
    for _ in range(n_boot):
        s = stand[rng.randint(0, len(stand), len(stand))]
        n1, n2, m = int(s[:, 0].sum()), int(s[:, 1].sum()), int((s[:, 0] & s[:, 1]).sum())
        dark_stand = chapman(n1, n2, m) - (n1 + n2 - m)
        picked = np.vstack([clusters[i] for i in rng.randint(0, len(clusters), len(clusters))])
        counts: dict = {}
        for row in picked:
            counts[tuple(row)] = counts.get(tuple(row), 0) + 1
        cells = np.array([counts.get((bool(p[0]), bool(p[1]), bool(p[2])), 0) for p in CELL_ORDER], float)
        fitted = loglinear_dark(cells, terms)
        if fitted is not None:
            estimates.append(dark_stand + fitted["n000"])
    lo, hi = np.percentile(estimates, [2.5, 97.5])
    return float(lo), float(hi)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coded", type=Path, default=Path("data/derived/m0a_coded_dod.parquet"))
    parser.add_argument("--described", type=Path, default=Path("data/derived/m0a_desc_phase3_dod.parquet"))
    parser.add_argument("--children", type=Path,
                        default=Path("specs/phase3-match-benchmark/inputs/vehicle149_children.json"))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    coded = pd.read_parquet(args.coded)
    described = pd.read_parquet(args.described)
    children = json.loads(args.children.read_text())
    a_keys = {coded_key(o, i) for o, i in zip(coded["order_piid"], coded["idv_piid"])}
    gen_col = "gen_id" if "gen_id" in described.columns else "generated_internal_id"
    b_keys = {k for k in (described_key(g) for g in described[gen_col]) if k}
    c_keys = {(_nk(k["order"]), _nk(k["idv"])) for k in children if k.get("order")}
    units = build_units(a_keys, b_keys, c_keys)

    result = {"inputs": {str(p): _sha(p) for p in (args.coded, args.described, args.children)},
              "n_units_observed": int(len(units)),
              "standalone_cells": {"n1": int(units[units["standalone"]]["a"].sum()),
                                   "n2": int(units[units["standalone"]]["b"].sum()),
                                   "m": int((units[units["standalone"]]["a"] & units[units["standalone"]]["b"]).sum())},
              "task_order_cells": dict(zip(["ABC", "AB", "AC", "BC", "A", "B", "C"],
                                           cell_counts(units[~units["standalone"]]).astype(int).tolist())),
              "models": {}}
    for terms in MODELS:
        fitted = stratified_dark(units, terms)
        if fitted is None:
            continue
        name = "+".join(terms) if terms else "independence"
        total_n = len(units) + fitted["dark_total"]
        result["models"][name] = {**{k: round(v, 1) for k, v in fitted.items()},
                                  "total_N": round(total_n, 0),
                                  "code_miss_rate": round(100 * (total_n - len(a_keys)) / total_n, 1)}
    lo, hi = block_bootstrap_ci(units, ["AB", "BC"])
    result["ab_bc_block_bootstrap_ci"] = [round(lo, 0), round(hi, 0)]
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
