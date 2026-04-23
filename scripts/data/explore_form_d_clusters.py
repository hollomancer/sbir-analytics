#!/usr/bin/env python3
"""Exploratory clustering on Form D confidence signals.

Runs GMM and k-means on the raw signal vector (person_score, state_score,
temporal_score, year_of_inc_score) to discover natural groupings. Outputs
cluster profiles and cross-tabs to inform rule-based tier definitions.

Usage:
    python scripts/data/explore_form_d_clusters.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

SIGNALS = ["person_score", "state_score", "temporal_score", "year_of_inc_score"]
# Default for missing signals — neutral (matches the scoring system's convention)
MISSING_DEFAULT = 0.5


def load_data(path: str) -> tuple[list[dict], np.ndarray]:
    """Load records and extract signal matrix."""
    records = []
    with open(path) as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    X = np.zeros((len(records), len(SIGNALS)))
    for i, r in enumerate(records):
        c = r["match_confidence"]
        for j, sig in enumerate(SIGNALS):
            val = c.get(sig)
            X[i, j] = val if val is not None else MISSING_DEFAULT

    return records, X


def describe_cluster(
    records: list[dict],
    X: np.ndarray,
    labels: np.ndarray,
    cluster_id: int,
) -> dict:
    """Compute descriptive stats for one cluster."""
    mask = labels == cluster_id
    subset = X[mask]
    cluster_records = [r for r, m in zip(records, mask) if m]

    # Signal means
    means = {SIGNALS[j]: float(subset[:, j].mean()) for j in range(len(SIGNALS))}

    # Tier distribution within this cluster
    tiers = Counter(r["match_confidence"]["tier"] for r in cluster_records)

    # Fundraising stats
    raised_values = [
        r.get("total_raised", 0) or 0 for r in cluster_records
    ]
    has_raised = sum(1 for v in raised_values if v > 0)

    # Person+state quadrant
    quadrant = Counter()
    for r in cluster_records:
        c = r["match_confidence"]
        ps = c.get("person_score")
        ss = c.get("state_score")
        if ps is None or ss is None:
            quadrant["missing"] += 1
        elif ps >= 0.7 and ss >= 0.5:
            quadrant["person+state"] += 1
        elif ps >= 0.7:
            quadrant["person_only"] += 1
        elif ss >= 0.5:
            quadrant["state_only"] += 1
        else:
            quadrant["neither"] += 1

    return {
        "cluster_id": cluster_id,
        "size": int(mask.sum()),
        "signal_means": means,
        "tiers": dict(tiers),
        "quadrant": dict(quadrant),
        "pct_with_funding": has_raised / max(len(cluster_records), 1) * 100,
        "median_raised": float(np.median([v for v in raised_values if v > 0]))
        if has_raised > 0
        else 0,
    }


def print_cluster_profile(profile: dict) -> None:
    size = profile["size"]
    means = profile["signal_means"]
    tiers = profile["tiers"]
    quad = profile["quadrant"]

    # Characterize the cluster by its dominant signals
    tags = []
    if means["person_score"] >= 0.65:
        tags.append("PI-MATCH")
    elif means["person_score"] < 0.35:
        tags.append("no-PI")
    if means["state_score"] >= 0.7:
        tags.append("STATE-MATCH")
    elif means["state_score"] < 0.3:
        tags.append("no-state")
    if means["temporal_score"] >= 0.7:
        tags.append("TEMPORAL-OK")
    elif means["temporal_score"] < 0.3:
        tags.append("temporal-miss")
    label = " + ".join(tags) if tags else "mixed"

    print(f"\n  Cluster {profile['cluster_id']}  ({size:,} companies)  [{label}]")
    print(f"    Signals:  person={means['person_score']:.2f}  "
          f"state={means['state_score']:.2f}  "
          f"temporal={means['temporal_score']:.2f}  "
          f"yoi={means['year_of_inc_score']:.2f}")
    print(f"    Tiers:    high={tiers.get('high', 0):,}  "
          f"med={tiers.get('medium', 0):,}  "
          f"low={tiers.get('low', 0):,}")
    print(f"    Quadrant: person+state={quad.get('person+state', 0):,}  "
          f"person_only={quad.get('person_only', 0):,}  "
          f"state_only={quad.get('state_only', 0):,}  "
          f"neither={quad.get('neither', 0):,}")
    print(f"    Funding:  {profile['pct_with_funding']:.0f}% have raised  "
          f"median=${profile['median_raised']/1e6:.1f}M")


def run_clustering(records, X, method, n_clusters):
    """Run one clustering method and print profiles."""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    if method == "gmm":
        model = GaussianMixture(n_components=n_clusters, random_state=42, n_init=5)
        labels = model.fit_predict(X_scaled)
        bic = model.bic(X_scaled)
        aic = model.aic(X_scaled)
        print(f"\n  BIC={bic:.0f}  AIC={aic:.0f}")
    else:
        model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = model.fit_predict(X_scaled)
        print(f"\n  Inertia={model.inertia_:.0f}")

    # Sort clusters by mean person_score descending for consistent ordering
    cluster_means = []
    for k in range(n_clusters):
        mask = labels == k
        mean_person = X[mask, 0].mean() if mask.any() else 0
        cluster_means.append((k, mean_person))
    cluster_means.sort(key=lambda x: -x[1])

    # Remap labels so cluster 0 = highest person score
    remap = {old: new for new, (old, _) in enumerate(cluster_means)}
    labels = np.array([remap[l] for l in labels])

    profiles = []
    for k in range(n_clusters):
        p = describe_cluster(records, X, labels, k)
        profiles.append(p)

    for p in profiles:
        print_cluster_profile(p)

    return labels, profiles


def main():
    input_path = "data/form_d_details.jsonl"
    records, X = load_data(input_path)
    print(f"Loaded {len(records):,} records, {len(SIGNALS)} signals")
    print(f"Missing values per signal:")
    for j, sig in enumerate(SIGNALS):
        missing = sum(
            1 for r in records if r["match_confidence"].get(sig) is None
        )
        print(f"  {sig}: {missing:,} ({missing/len(records)*100:.1f}%)")

    # --- GMM: try k=3,4,5,6 to find natural number of clusters ---
    print(f"\n{'='*70}")
    print("GMM MODEL SELECTION (BIC/AIC)")
    print(f"{'='*70}")

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    for k in range(3, 8):
        gmm = GaussianMixture(n_components=k, random_state=42, n_init=5)
        gmm.fit(X_scaled)
        print(f"  k={k}  BIC={gmm.bic(X_scaled):>10.0f}  AIC={gmm.aic(X_scaled):>10.0f}")

    # --- Detailed profiles at k=4,5 ---
    for k in [4, 5]:
        print(f"\n{'='*70}")
        print(f"GMM k={k} — CLUSTER PROFILES")
        print(f"{'='*70}")
        run_clustering(records, X, "gmm", k)

    # --- K-Means for comparison at k=4,5 ---
    for k in [4, 5]:
        print(f"\n{'='*70}")
        print(f"K-MEANS k={k} — CLUSTER PROFILES")
        print(f"{'='*70}")
        run_clustering(records, X, "kmeans", k)

    # --- Cross-tab: person_score bins × state_score bins ---
    print(f"\n{'='*70}")
    print("SIGNAL CROSS-TAB: person_score × state_score × temporal_score")
    print(f"{'='*70}")

    for temporal_label, t_lo, t_hi in [
        ("temporal OK (≥0.5)", 0.5, 1.01),
        ("temporal miss (<0.5)", -0.01, 0.5),
    ]:
        print(f"\n  {temporal_label}:")
        print(f"  {'':>20s} | {'state MATCH':>12s} | {'state MISS':>12s} |")
        print(f"  {'':>20s} | {'':>12s} | {'':>12s} |")

        for p_label, p_lo, p_hi in [
            ("person HIGH (≥0.7)", 0.7, 1.01),
            ("person MID (0.4-0.7)", 0.4, 0.7),
            ("person LOW (<0.4)", -0.01, 0.4),
        ]:
            counts = [0, 0]  # [state_match, state_miss]
            for r in records:
                c = r["match_confidence"]
                ps = c.get("person_score") or 0.5
                ss = c.get("state_score") or 0.5
                ts = c.get("temporal_score") or 0.5
                if p_lo <= ps < p_hi and t_lo <= ts < t_hi:
                    if ss >= 0.5:
                        counts[0] += 1
                    else:
                        counts[1] += 1
            print(f"  {p_label:>20s} | {counts[0]:>12,} | {counts[1]:>12,} |")


if __name__ == "__main__":
    main()
