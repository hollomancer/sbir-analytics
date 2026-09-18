#!/usr/bin/env python3
"""Recompute the SBA SBIR/STTR annual-report state tables from the award export.

Roadmap Order 1, study ``sba-annual-report-tables``. Recomputes the published
"SBIR/STTR Awards by U.S. State and Territory" tables for FY2020-FY2022 from a
pinned SBIR.gov award export and compares the result to the captured published
tables under the study's reproduction contract.

The comparison is deliberately tolerance-based rather than exact. SBA states the
published tables are "a summation of the individual awards uploaded to SBA"
(FY2016 annual report, p39), and that post-publication corrections are pushed to
SBIR.gov while the published report is not revised. The export is therefore a
corrected database compared against an uncorrected table, and no report-era
export survives. See studies/sba-annual-report-tables/assembly-methodology.md.

Two effects are superimposed in the cell deltas and are reported separately:
a net count surplus (the export holds records the published count did not) and
gross cell displacement (firms that relocated since publication sit in the wrong
jurisdiction). Cell displacement must never be attributed to counting.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.exceptions import ValidationError
from sbir_etl.identity.geography import USJurisdictionProfile, normalize_us_jurisdiction

EPISTEMIC_TIER = "exploratory"

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STUDY_ROOT = REPOSITORY_ROOT / "studies/sba-annual-report-tables"
DEFAULT_EXPORT = REPOSITORY_ROOT / "data/raw/sbir/history/2026-09-17/award_data.csv"
DEFAULT_PUBLISHED_DIR = STUDY_ROOT / "data"
DEFAULT_OUTPUT_DIR = STUDY_ROOT / "results"

#: Report-years captured under the frozen protocol. FY2022 is the selected
#: report-year; FY2020 and FY2021 extend the panel.
REPORT_YEARS: tuple[int, ...] = (2020, 2021, 2022)

#: Jurisdiction normalization profile. STRICT_V1 rejects non-canonical values
#: rather than passing them through, which is what we want: an unmapped
#: jurisdiction is a reconciliation failure, not a row to drop silently.
JURISDICTION_PROFILE = USJurisdictionProfile.STRICT_V1

#: Published tables report only these two programs and two phases.
PROGRAMS: tuple[str, ...] = ("SBIR", "STTR")
PHASES: tuple[str, ...] = ("Phase I", "Phase II")

#: Structural-check bands from studies/sba-annual-report-tables/sources.yaml
#: (``published_table_tolerances``). One-sided on the total because
#: post-publication correction only adds records; hybrid on cells because small
#: cells move little absolutely but up to 200% relatively, and large cells the
#: reverse. Derived over all 632 published cells across FY2020-FY2022, of which
#: 569 have a non-zero published count.
TOTAL_COUNT_BAND_FRACTION = 0.03
CELL_FLOOR_ROWS = 6
CELL_RELATIVE_FRACTION = 0.20

#: The published tables print whole dollars summed from sub-dollar amounts, so a
#: total column can miss the sum of its parts by a dollar. design.md classifies
#: that as ``rounding``.
DOLLAR_ROUNDING_ALLOWANCE = 1

#: Difference classes frozen in design.md. Every non-matching cell is assigned
#: exactly one. ``definition_mismatch`` is never assigned automatically: it
#: requires a maintainer to identify which rule diverged, and design.md
#: resolves it by fixing our rule rather than by recording a delta.
CELL_CLASSES: tuple[str, ...] = (
    "exact",
    "rounding",
    "revised_upstream",
    "definition_mismatch",
    "pipeline_defect",
)

#: Provenance record for the pinned export, committed under the study because
#: data/ is gitignored. Its sha256 is the contract: a run against any other
#: export is not this study.
DEFAULT_RETRIEVAL_MANIFEST = STUDY_ROOT / "award-export-2026-09-17.meta.json"


@dataclass(frozen=True)
class CellComparison:
    """One published cell against its recomputed counterpart."""

    report_year: int
    jurisdiction: str
    program: str
    phase: str
    published_count: int
    recomputed_count: int
    delta: int
    tolerance: int
    within_tolerance: bool
    published_dollars: int
    recomputed_dollars: int
    dollar_delta: int
    classification: str


@dataclass(frozen=True)
class YearComparison:
    """Totals, tolerance verdict, and displacement decomposition for one year."""

    report_year: int
    published_total: int
    recomputed_total: int
    total_delta: int
    total_delta_fraction: float
    total_band: int
    total_within_tolerance: bool
    cells: int
    cells_exact: int
    cells_over: int
    cells_under: int
    cells_outside_tolerance: int
    surplus_rows: int
    deficit_rows: int
    displacement_floor: int
    published_dollars: int
    recomputed_dollars: int
    dollar_delta: int
    dollar_delta_fraction: float
    classification_counts: dict[str, int]


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of ``path``, for pinning inputs in the run manifest."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repository_relative(path: Path) -> str:
    """Render ``path`` relative to the repository when it sits inside it.

    An export supplied from outside the repository is recorded absolutely rather
    than raising, so a run against a scratch copy still produces a manifest.
    """
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPOSITORY_ROOT))
    except ValueError:
        return str(resolved)


def normalize_jurisdiction(value: Any) -> str:
    """Map an export ``State`` value to a USPS code, refusing unmapped values.

    The published tables key on two-letter codes while the export carries full
    names, so the mapping is load-bearing. An unmapped non-blank value is raised
    rather than dropped: silently discarding it would understate a jurisdiction
    without any signal. Known gap: STRICT_V1 does not carry Marshall Islands,
    which appears on two award records across the whole export (FY2014, FY2019)
    and none in FY2020-FY2022.
    """
    code = normalize_us_jurisdiction(value, profile=JURISDICTION_PROFILE)
    if code is None:
        raise ValidationError(
            f"jurisdiction {value!r} is not mapped by {JURISDICTION_PROFILE.value}; "
            "resolve the mapping rather than dropping the record"
        )
    return code


def verify_export_pinned(export_path: Path, retrieval_manifest: Path) -> str:
    """Check the export against the committed retrieval manifest before use.

    Recording a hash after the fact does not pin anything: ``--export`` is
    overridable and the export is gitignored, so a wrong endpoint would
    otherwise produce a successful run carrying an authoritative-looking hash.
    This study has already been burned once by a near-identical SBIR.gov
    endpoint serving a different product, so the check runs before aggregation
    and refuses rather than warns.
    """
    expected = json.loads(retrieval_manifest.read_text(encoding="utf-8"))["sha256"]
    actual = sha256_file(export_path)
    if actual != expected:
        raise ValidationError(
            f"export at {export_path} has sha256 {actual}, but {retrieval_manifest.name} "
            f"pins {expected}. This is a different export, so the comparison would not be "
            "this study. Re-download the pinned vintage, or pass --allow-unpinned to run "
            "against another export and have the result labelled unpinned."
        )
    return actual


def classify_cell(delta: int, dollar_delta: int, tolerance: int) -> str:
    """Assign one frozen difference class to a cell.

    design.md admits exactly four classes for a non-match and states that
    unexplained differences are not a category. Mapping, in order:

    - counts and dollars both agree exactly: ``exact``;
    - counts agree and dollars differ within the whole-dollar allowance:
      ``rounding``;
    - counts agree and dollars differ by more, or counts differ inside the
      declared band: ``revised_upstream``, the class design.md assigns to a
      source record that changed after the report was printed;
    - counts differ outside the band: ``pipeline_defect``, which keeps the study
      out of ``reproduced``.

    ``definition_mismatch`` is deliberately unreachable here; see CELL_CLASSES.
    """
    if delta == 0 and dollar_delta == 0:
        return "exact"
    if delta == 0 and abs(dollar_delta) <= DOLLAR_ROUNDING_ALLOWANCE:
        return "rounding"
    if abs(delta) <= tolerance:
        return "revised_upstream"
    return "pipeline_defect"


def load_award_export(path: Path, report_years: tuple[int, ...] = REPORT_YEARS) -> pd.DataFrame:
    """Load award rows for ``report_years`` from a pinned SBIR.gov export.

    No de-duplication is applied. Distinct ``(Contract, Phase)`` pairs already
    exceed the published counts, so no merging rule can close the gap; the
    difference is records the published count did not contain, which the
    tolerance absorbs. Rows with a blank jurisdiction are dropped and counted,
    because the published tables have no cell to hold them.
    """
    frame = pd.read_csv(
        path,
        usecols=["Award Year", "Program", "Phase", "State", "Award Amount"],
        dtype=str,
        low_memory=False,
    )
    frame["report_year"] = pd.to_numeric(frame["Award Year"], errors="coerce")
    frame["amount"] = pd.to_numeric(frame["Award Amount"], errors="coerce")
    frame = frame[frame["report_year"].isin(report_years)].copy()
    frame["report_year"] = frame["report_year"].astype(int)

    blank = frame["State"].isna() | frame["State"].astype(str).str.strip().eq("")
    if int(blank.sum()):
        frame = frame[~blank].copy()
    frame.attrs["dropped_blank_jurisdiction"] = int(blank.sum())

    frame["jurisdiction"] = frame["State"].map(normalize_jurisdiction)
    unknown_programs = sorted(set(frame["Program"].dropna()) - set(PROGRAMS))
    unknown_phases = sorted(set(frame["Phase"].dropna()) - set(PHASES))
    if unknown_programs or unknown_phases:
        raise ValidationError(
            "export carries values the published tables cannot hold: "
            f"programs={unknown_programs} phases={unknown_phases}"
        )
    return frame


def recompute_cells(awards: pd.DataFrame, report_year: int) -> pd.DataFrame:
    """Aggregate export rows into published-table cells for one report-year."""
    subset = awards[awards["report_year"] == report_year]
    grouped = (
        subset.groupby(["jurisdiction", "Program", "Phase"], dropna=False)
        .agg(recomputed_count=("amount", "size"), recomputed_dollars=("amount", "sum"))
        .reset_index()
        .rename(columns={"Program": "program", "Phase": "phase"})
    )
    grouped["recomputed_dollars"] = grouped["recomputed_dollars"].round().astype("int64")
    return grouped


def published_cells(table: pd.DataFrame, report_year: int) -> pd.DataFrame:
    """Reshape a captured wide published table into one row per cell."""
    columns = {
        ("SBIR", "Phase I"): ("sbir_p1_n", "sbir_p1_usd"),
        ("STTR", "Phase I"): ("sttr_p1_n", "sttr_p1_usd"),
        ("SBIR", "Phase II"): ("sbir_p2_n", "sbir_p2_usd"),
        ("STTR", "Phase II"): ("sttr_p2_n", "sttr_p2_usd"),
    }
    rows: list[dict[str, Any]] = []
    for _, record in table.iterrows():
        for (program, phase), (count_column, dollar_column) in columns.items():
            rows.append(
                {
                    "report_year": report_year,
                    "jurisdiction": str(record["state"]),
                    "program": program,
                    "phase": phase,
                    "published_count": int(record[count_column]),
                    "published_dollars": int(record[dollar_column]),
                }
            )
    return pd.DataFrame(rows)


def verify_published_identities(table: pd.DataFrame, report_year: int) -> list[dict[str, Any]]:
    """Check each published row against its own totals, before any comparison.

    design.md makes denominator integrity a blocking check: every published
    total must equal the sum of its published parts. The captured tables satisfy
    that exactly on award counts but miss by a dollar on some total-dollar
    columns, because the source sums sub-dollar amounts and prints whole
    dollars. Differences up to DOLLAR_ROUNDING_ALLOWANCE are returned as
    ``rounding`` violations and do not fail the study, per the amendment
    recorded in amendments.md; anything larger is a capture defect.
    """
    identities = (
        ("sbir_count", "sbir_tot_n", ("sbir_p1_n", "sbir_p2_n"), 0),
        ("sttr_count", "sttr_tot_n", ("sttr_p1_n", "sttr_p2_n"), 0),
        ("all_count", "all_tot_n", ("sbir_tot_n", "sttr_tot_n"), 0),
        ("sbir_dollars", "sbir_tot_usd", ("sbir_p1_usd", "sbir_p2_usd"), DOLLAR_ROUNDING_ALLOWANCE),
        ("sttr_dollars", "sttr_tot_usd", ("sttr_p1_usd", "sttr_p2_usd"), DOLLAR_ROUNDING_ALLOWANCE),
        ("all_dollars", "all_tot_usd", ("sbir_tot_usd", "sttr_tot_usd"), DOLLAR_ROUNDING_ALLOWANCE),
    )
    violations: list[dict[str, Any]] = []
    for name, total_column, part_columns, allowance in identities:
        residual = table[total_column] - sum(table[column] for column in part_columns)
        for index in residual[residual != 0].index:
            amount = int(residual.loc[index])
            violations.append(
                {
                    "report_year": report_year,
                    "jurisdiction": str(table.loc[index, "state"]),
                    "identity": name,
                    "residual": amount,
                    "classification": "rounding" if abs(amount) <= allowance else "capture_defect",
                }
            )
    return violations


def cell_tolerance(published_count: int) -> int:
    """Return the per-cell award-count band for a cell of the given size.

    ``max(CELL_FLOOR_ROWS, CELL_RELATIVE_FRACTION x published)``. The hybrid is
    required because the two failure modes invert with cell size; the band was
    derived as the tightest on a tested grid covering all 632 published cells
    across FY2020-FY2022.
    """
    return max(CELL_FLOOR_ROWS, int(round(published_count * CELL_RELATIVE_FRACTION)))


def compare_year(
    awards: pd.DataFrame, published: pd.DataFrame, report_year: int
) -> tuple[YearComparison, list[CellComparison]]:
    """Compare one report-year and decompose surplus from displacement."""
    left = published_cells(published, report_year)
    right = recompute_cells(awards, report_year)
    merged = left.merge(right, on=["jurisdiction", "program", "phase"], how="outer")
    merged["report_year"] = report_year
    for column in ("published_count", "recomputed_count", "published_dollars", "recomputed_dollars"):
        merged[column] = merged[column].fillna(0).astype("int64")

    merged["delta"] = merged["recomputed_count"] - merged["published_count"]
    merged["dollar_delta"] = merged["recomputed_dollars"] - merged["published_dollars"]
    merged["tolerance"] = merged["published_count"].map(cell_tolerance)
    merged["within_tolerance"] = merged["delta"].abs() <= merged["tolerance"]
    merged["classification"] = [
        classify_cell(int(row.delta), int(row.dollar_delta), int(row.tolerance))
        for row in merged.itertuples()
    ]

    published_total = int(merged["published_count"].sum())
    recomputed_total = int(merged["recomputed_count"].sum())
    total_delta = recomputed_total - published_total
    total_band = int(round(published_total * TOTAL_COUNT_BAND_FRACTION))
    surplus_rows = int(merged.loc[merged["delta"] > 0, "delta"].sum())
    deficit_rows = int(-merged.loc[merged["delta"] < 0, "delta"].sum())
    published_dollars = int(merged["published_dollars"].sum())
    recomputed_dollars = int(merged["recomputed_dollars"].sum())

    summary = YearComparison(
        report_year=report_year,
        published_total=published_total,
        recomputed_total=recomputed_total,
        total_delta=total_delta,
        total_delta_fraction=total_delta / published_total if published_total else 0.0,
        total_band=total_band,
        # One-sided: the export may exceed the published count but should never
        # fall below it, because correction only adds records.
        total_within_tolerance=0 <= total_delta <= total_band,
        cells=int(len(merged)),
        cells_exact=int((merged["delta"] == 0).sum()),
        cells_over=int((merged["delta"] > 0).sum()),
        cells_under=int((merged["delta"] < 0).sum()),
        cells_outside_tolerance=int((~merged["within_tolerance"]).sum()),
        surplus_rows=surplus_rows,
        deficit_rows=deficit_rows,
        # Rows that must be in the wrong cell rather than merely extra: the
        # smaller side of the two-sided movement. This is the state-attribution
        # tolerance, not the count surplus.
        displacement_floor=min(surplus_rows, deficit_rows),
        published_dollars=published_dollars,
        recomputed_dollars=recomputed_dollars,
        dollar_delta=recomputed_dollars - published_dollars,
        dollar_delta_fraction=(
            (recomputed_dollars - published_dollars) / published_dollars if published_dollars else 0.0
        ),
        classification_counts={
            name: int((merged["classification"] == name).sum()) for name in CELL_CLASSES
        },
    )
    cells = [
        CellComparison(
            report_year=report_year,
            jurisdiction=str(record.jurisdiction),
            program=str(record.program),
            phase=str(record.phase),
            published_count=int(record.published_count),
            recomputed_count=int(record.recomputed_count),
            delta=int(record.delta),
            tolerance=int(record.tolerance),
            within_tolerance=bool(record.within_tolerance),
            published_dollars=int(record.published_dollars),
            recomputed_dollars=int(record.recomputed_dollars),
            dollar_delta=int(record.dollar_delta),
            classification=str(record.classification),
        )
        for record in merged.itertuples()
    ]
    return summary, cells


def run(
    export_path: Path = DEFAULT_EXPORT,
    published_dir: Path = DEFAULT_PUBLISHED_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    report_years: tuple[int, ...] = REPORT_YEARS,
    retrieval_manifest: Path = DEFAULT_RETRIEVAL_MANIFEST,
    allow_unpinned: bool = False,
) -> dict[str, Any]:
    """Recompute, compare, and write the cell table plus a run manifest."""
    if allow_unpinned:
        export_sha256 = sha256_file(export_path)
    else:
        export_sha256 = verify_export_pinned(export_path, retrieval_manifest)
    awards = load_award_export(export_path, report_years)
    summaries: list[YearComparison] = []
    cells: list[CellComparison] = []
    published_inputs: dict[str, str] = {}
    identity_violations: list[dict[str, Any]] = []

    for report_year in report_years:
        # No table number in the filename: the same table is numbered 20 in FY22 and
        # 18 in FY20/FY21, verified against each report's caption.
        published_path = published_dir / f"awards_by_state_fy{str(report_year)[2:]}.csv"
        if not published_path.exists():
            raise ValidationError(f"captured published table missing: {published_path}")
        published_inputs[published_path.name] = sha256_file(published_path)
        published = pd.read_csv(published_path)
        identity_violations.extend(verify_published_identities(published, report_year))
        summary, year_cells = compare_year(awards, published, report_year)
        summaries.append(summary)
        cells.extend(year_cells)

    capture_defects = [v for v in identity_violations if v["classification"] == "capture_defect"]
    if capture_defects:
        raise ValidationError(
            f"{len(capture_defects)} published row(s) fail denominator integrity by more than "
            f"${DOLLAR_ROUNDING_ALLOWANCE}, which design.md treats as blocking: "
            f"{capture_defects[:3]}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    cell_frame = pd.DataFrame([asdict(cell) for cell in cells])
    cell_frame = cell_frame.sort_values(["report_year", "jurisdiction", "program", "phase"])
    cell_path = output_dir / "comparison_cells.csv"
    cell_frame.to_csv(cell_path, index=False)

    result: dict[str, Any] = {
        "study_id": "sba-annual-report-tables",
        "inputs": {
            "award_export": {
                "path": _repository_relative(export_path),
                "sha256": export_sha256,
                "pinned": not allow_unpinned,
                "retrieval_manifest": _repository_relative(retrieval_manifest),
            },
            "published_tables": published_inputs,
        },
        "decisions": {
            "window": "Award Year field",
            "jurisdiction_profile": JURISDICTION_PROFILE.value,
            "deduplication": "none",
            "dropped_blank_jurisdiction": int(awards.attrs.get("dropped_blank_jurisdiction", 0)),
        },
        "tolerances": {
            "total_count_band_fraction": TOTAL_COUNT_BAND_FRACTION,
            "total_count_one_sided": True,
            "cell_floor_rows": CELL_FLOOR_ROWS,
            "cell_relative_fraction": CELL_RELATIVE_FRACTION,
        },
        "published_identity_check": {
            "allowance_usd": DOLLAR_ROUNDING_ALLOWANCE,
            "violations": len(identity_violations),
            "classified_rounding": len(identity_violations) - len(capture_defects),
            "capture_defects": len(capture_defects),
            "by_identity": {
                name: sum(1 for v in identity_violations if v["identity"] == name)
                for name in sorted({v["identity"] for v in identity_violations})
            },
        },
        "years": [asdict(summary) for summary in summaries],
        "verdict": {
            "totals_within_tolerance": all(summary.total_within_tolerance for summary in summaries),
            "cells_outside_tolerance": sum(summary.cells_outside_tolerance for summary in summaries),
            "pipeline_defect_cells": sum(
                summary.classification_counts["pipeline_defect"] for summary in summaries
            ),
            "structural_check_passed": (
                all(summary.total_within_tolerance for summary in summaries)
                and not sum(summary.cells_outside_tolerance for summary in summaries)
            ),
            # design.md: with no report-era vintage the published-sample outcome
            # is `blocked`, and a comparison against the current snapshot is
            # admissible only as a labelled structural check. Passing the bands
            # does not promote this to `reproduced`.
            "published_sample_outcome": "blocked",
        },
        "dollar_band_status": (
            "No published-dollar tolerance is committed. Dollar deltas are reported as measured "
            "and carry no verdict. The whole-dollar allowance is used only to classify a cell "
            "whose counts agree as `rounding`."
        ),
    }
    manifest_path = output_dir / "comparison_manifest.json"
    manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--published-dir", type=Path, default=DEFAULT_PUBLISHED_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--retrieval-manifest", type=Path, default=DEFAULT_RETRIEVAL_MANIFEST)
    parser.add_argument(
        "--allow-unpinned",
        action="store_true",
        help="run against an export whose hash does not match the pinned vintage; "
        "the run manifest records the result as unpinned",
    )
    arguments = parser.parse_args()

    result = run(
        arguments.export,
        arguments.published_dir,
        arguments.output_dir,
        retrieval_manifest=arguments.retrieval_manifest,
        allow_unpinned=arguments.allow_unpinned,
    )
    for year in result["years"]:
        classes = ", ".join(
            f"{name}={count}" for name, count in year["classification_counts"].items() if count
        )
        print(
            f"FY{year['report_year']}: published {year['published_total']:,} "
            f"recomputed {year['recomputed_total']:,} "
            f"delta {year['total_delta']:+,} ({year['total_delta_fraction']:+.2%}) "
            f"band +{year['total_band']:,} "
            f"{'WITHIN' if year['total_within_tolerance'] else 'OUTSIDE'} | "
            f"cells {year['cells']}, {year['cells_outside_tolerance']} outside band, "
            f"displacement floor {year['displacement_floor']} | {classes}"
        )
    verdict = result["verdict"]
    print(
        f"structural check: {'PASS' if verdict['structural_check_passed'] else 'FAIL'} | "
        f"published-sample outcome: {verdict['published_sample_outcome']} "
        "(no report-era vintage exists; design.md admits this run only as a structural check)"
    )
    # Both declared bands gate the exit status. Checking totals alone would let a
    # cell outside its band pass whenever the totals happened to stay inside +3%.
    return 0 if verdict["structural_check_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
