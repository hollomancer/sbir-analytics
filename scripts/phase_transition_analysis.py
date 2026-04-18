"""Ad-hoc Phase II -> Phase III transition latency analysis.

Reads the four materialized phase-transition parquet files into DuckDB and
emits distribution, agency, and cohort breakdowns as JSON to
``reports/phase_transition/``.

Run after the Dagster assets have been materialized::

    python scripts/phase_transition_analysis.py \\
        --phase-ii data/processed/phase_ii_awards.parquet \\
        --phase-iii data/processed/phase_iii_contracts.parquet \\
        --pairs data/processed/phase_ii_iii_pairs.parquet \\
        --survival data/processed/phase_transition_survival.parquet \\
        --out reports/phase_transition

Deliverables mirrored in the task brief:

- Latency distribution: histogram (month bins) + percentiles.
- Agency breakdowns: match rate and median latency per agency.
- Match rate: matched Phase IIs / all Phase IIs, by agency and end-year cohort.
- Transition rate as a function of Phase II end-year cohort.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _run(
    phase_ii: Path,
    phase_iii: Path,
    pairs: Path,
    survival: Path,
    out_dir: Path,
) -> None:
    import duckdb

    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    # DuckDB does not support prepared parameters for table-valued functions
    # like ``read_parquet``. Instead we escape embedded single quotes in the
    # path before interpolating so paths with quotes can't break the SQL.
    def _lit(path: Path) -> str:
        return "'" + str(path).replace("'", "''") + "'"

    con.execute(f"CREATE VIEW phase_ii AS SELECT * FROM read_parquet({_lit(phase_ii)})")
    con.execute(f"CREATE VIEW phase_iii AS SELECT * FROM read_parquet({_lit(phase_iii)})")
    con.execute(f"CREATE VIEW pairs AS SELECT * FROM read_parquet({_lit(pairs)})")
    con.execute(f"CREATE VIEW survival AS SELECT * FROM read_parquet({_lit(survival)})")

    # 1. Latency distribution — percentiles and month-binned histogram.
    percentiles = con.execute(
        """
        SELECT
            count(*)::BIGINT                          AS n,
            sum(CASE WHEN latency_days < 0 THEN 1 ELSE 0 END)::BIGINT AS negative,
            approx_quantile(latency_days, 0.10)       AS p10,
            approx_quantile(latency_days, 0.25)       AS p25,
            approx_quantile(latency_days, 0.50)       AS p50,
            approx_quantile(latency_days, 0.75)       AS p75,
            approx_quantile(latency_days, 0.90)       AS p90,
            avg(latency_days)                          AS mean
        FROM pairs
        """
    ).fetchone()

    histogram = con.execute(
        """
        WITH binned AS (
            SELECT CAST(floor(latency_days / 30.0) AS INTEGER) AS month_bin
            FROM pairs
        )
        SELECT month_bin, count(*) AS n
        FROM binned
        GROUP BY month_bin
        ORDER BY month_bin
        """
    ).fetchall()

    # 2. Agency breakdown — match rate + median latency per Phase II agency.
    agency_breakdown = con.execute(
        """
        WITH per_agency AS (
            SELECT
                coalesce(s.phase_ii_agency, 'UNKNOWN') AS agency,
                count(*)                                AS phase_ii_total,
                sum(CASE WHEN s.event_observed THEN 1 ELSE 0 END) AS matched
            FROM survival s
            GROUP BY 1
        )
        SELECT
            p.agency,
            p.phase_ii_total,
            p.matched,
            round(p.matched::DOUBLE / nullif(p.phase_ii_total, 0), 4) AS match_rate,
            approx_quantile(pa.latency_days, 0.5)                      AS median_latency_days
        FROM per_agency p
        LEFT JOIN pairs pa
               ON coalesce(pa.phase_ii_agency, 'UNKNOWN') = p.agency
        GROUP BY p.agency, p.phase_ii_total, p.matched
        ORDER BY p.phase_ii_total DESC
        """
    ).fetchall()

    # 3. Transition rate by Phase II end-year cohort.
    cohort = con.execute(
        """
        SELECT
            extract(year FROM phase_ii_end_date)::INTEGER AS end_year,
            count(*)                                       AS phase_ii_total,
            sum(CASE WHEN event_observed THEN 1 ELSE 0 END) AS transitioned,
            round(
                sum(CASE WHEN event_observed THEN 1 ELSE 0 END)::DOUBLE
                / nullif(count(*), 0),
                4
            ) AS transition_rate
        FROM survival
        WHERE phase_ii_end_date IS NOT NULL
        GROUP BY end_year
        ORDER BY end_year
        """
    ).fetchall()

    # 4. Match rate by agency-x-year cohort.
    agency_year = con.execute(
        """
        SELECT
            coalesce(phase_ii_agency, 'UNKNOWN') AS agency,
            extract(year FROM phase_ii_end_date)::INTEGER AS end_year,
            count(*) AS phase_ii_total,
            sum(CASE WHEN event_observed THEN 1 ELSE 0 END) AS matched,
            round(
                sum(CASE WHEN event_observed THEN 1 ELSE 0 END)::DOUBLE
                / nullif(count(*), 0),
                4
            ) AS match_rate
        FROM survival
        WHERE phase_ii_end_date IS NOT NULL
        GROUP BY agency, end_year
        ORDER BY agency, end_year
        """
    ).fetchall()

    report = {
        "latency_distribution": {
            "n": int(percentiles[0]) if percentiles else 0,
            "negative": int(percentiles[1]) if percentiles else 0,
            "percentiles_days": {
                "p10": _to_num(percentiles[2]) if percentiles else None,
                "p25": _to_num(percentiles[3]) if percentiles else None,
                "p50": _to_num(percentiles[4]) if percentiles else None,
                "p75": _to_num(percentiles[5]) if percentiles else None,
                "p90": _to_num(percentiles[6]) if percentiles else None,
            },
            "mean_days": _to_num(percentiles[7]) if percentiles else None,
            "histogram_month_bins": [
                {"month_bin": int(b), "n": int(n)} for b, n in histogram
            ],
        },
        "agency_breakdown": [
            {
                "agency": a,
                "phase_ii_total": int(t),
                "matched": int(m),
                "match_rate": _to_num(r),
                "median_latency_days": _to_num(med),
            }
            for a, t, m, r, med in agency_breakdown
        ],
        "cohort_transition_rate": [
            {
                "end_year": int(y) if y is not None else None,
                "phase_ii_total": int(t),
                "transitioned": int(m),
                "transition_rate": _to_num(r),
            }
            for y, t, m, r in cohort
        ],
        "agency_year_match_rate": [
            {
                "agency": a,
                "end_year": int(y) if y is not None else None,
                "phase_ii_total": int(t),
                "matched": int(m),
                "match_rate": _to_num(r),
            }
            for a, y, t, m, r in agency_year
        ],
    }

    out_path = out_dir / "phase_transition_report.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"Wrote {out_path} ({out_path.stat().st_size} bytes)")


def _to_num(v: object) -> float | int | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else round(f, 4)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase-ii", type=Path, default=Path("data/processed/phase_ii_awards.parquet"))
    p.add_argument(
        "--phase-iii", type=Path, default=Path("data/processed/phase_iii_contracts.parquet")
    )
    p.add_argument("--pairs", type=Path, default=Path("data/processed/phase_ii_iii_pairs.parquet"))
    p.add_argument(
        "--survival", type=Path, default=Path("data/processed/phase_transition_survival.parquet")
    )
    p.add_argument("--out", type=Path, default=Path("reports/phase_transition"))
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    missing = [
        p for p in (args.phase_ii, args.phase_iii, args.pairs, args.survival) if not p.exists()
    ]
    if missing:
        raise SystemExit(
            "Missing upstream parquet files:\n  - "
            + "\n  - ".join(str(m) for m in missing)
            + "\nMaterialize the phase_transition Dagster assets first."
        )
    _run(args.phase_ii, args.phase_iii, args.pairs, args.survival, args.out)
