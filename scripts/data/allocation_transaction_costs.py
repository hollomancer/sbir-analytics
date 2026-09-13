#!/usr/bin/env python3
"""NIH SBIR/STTR versus R01-equivalent allocation transaction costs.

Exploratory study calculator. Every model number comes from a source field or
from assumptions.yaml. Paperwork Reduction Act hours and F&A rates are refused.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sbir_etl.config.yaml_io import read_yaml_mapping
from sbir_etl.exceptions import ConfigurationError

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCES = REPOSITORY_ROOT / "studies/allocation-transaction-costs/sources.yaml"
DEFAULT_ASSUMPTIONS = REPOSITORY_ROOT / "studies/allocation-transaction-costs/assumptions.yaml"
DEFAULT_COMPLEXITY = (
    REPOSITORY_ROOT / "studies/allocation-transaction-costs/complexity/nih_foa_rules.yaml"
)
FORBIDDEN_HOUR_SOURCES = frozenset({"pra_estimate", "fa_rate"})
ANNUAL_CONVENTION = "annual_award_size"
PROJECT_CONVENTION = "project_total"


@dataclass(frozen=True)
class MechanismYear:
    agency: str
    mechanism: str
    program: str
    phase: str
    fiscal_year: int
    applications: int
    awards: int
    success_rate: float | None
    dollars_awarded: float
    mean_award_size: float | None
    award_size_basis: str
    source_id: str
    evidence_class: str
    duration_convention: str


@dataclass(frozen=True)
class TransactionCost:
    hours_per_award: float
    applicant_hours_per_award: float
    review_hours_per_award: float
    dollars_per_award: float | None
    dollars_per_award_dollar: float | None
    hours_per_million_awarded: float | None
    gc_included: bool
    applicant_hours: float
    review_hours: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def success_rate(applications: int, awards: int) -> float | None:
    if applications <= 0:
        return None
    return awards / applications


def award_dollars_per_application(
    success: float | None, mean_award_size: float | None
) -> float | None:
    if success is None or mean_award_size is None:
        return None
    return success * mean_award_size


def breakeven_sbir_hours(
    h_control: float,
    success_treatment: float,
    dollars_treatment: float,
    success_control: float,
    dollars_control: float,
) -> float:
    """Applicant hours at which treatment cost per awarded dollar equals control."""

    if min(success_treatment, dollars_treatment, success_control, dollars_control) <= 0:
        raise ConfigurationError("break-even requires positive success rates and award sizes")
    return h_control * (success_treatment * dollars_treatment) / (success_control * dollars_control)


def breakeven_reviewer_hours(
    reviewer_hours_control: float,
    reviewers_treatment: float,
    reviewers_control: float,
    success_treatment: float,
    dollars_treatment: float,
    success_control: float,
    dollars_control: float,
) -> float:
    """Reviewer hours per application at which review cost per dollar equals."""

    if min(success_treatment, dollars_treatment, success_control, dollars_control) <= 0:
        raise ConfigurationError("reviewer break-even requires positive success rates and sizes")
    if reviewers_treatment <= 0:
        raise ConfigurationError("reviewer break-even requires a positive treatment reviewer count")
    control_review_hours = reviewer_hours_control * reviewers_control
    return (
        control_review_hours
        * (success_treatment * dollars_treatment)
        / (success_control * dollars_control)
        / reviewers_treatment
    )


def refuse_forbidden_hour_source(evidence_class: str) -> None:
    if evidence_class in FORBIDDEN_HOUR_SOURCES:
        raise ConfigurationError(f"{evidence_class} cannot be used as hours_per_application")


def applicant_hours_from_source(hours: float, evidence_class: str) -> float:
    """Accept a hour value only when its evidence class is not forbidden."""

    refuse_forbidden_hour_source(evidence_class)
    return hours


def transaction_cost(
    *,
    applications: float,
    awards: float,
    mean_award_size: float,
    hours_per_application: float,
    wage: float,
    reviewers_per_application: float,
    reviewer_hours: float,
    reviewer_wage: float,
    agency_cost: float | None,
    per_million_dollars: float,
) -> TransactionCost:
    if applications <= 0 or awards <= 0 or mean_award_size <= 0:
        raise ConfigurationError(
            "transaction cost requires positive applications, awards, and size"
        )
    applicant_hours = applications * hours_per_application
    review_hours = applications * reviewers_per_application * reviewer_hours
    applicant_cost = applicant_hours * wage
    review_cost = review_hours * reviewer_wage
    gc_included = agency_cost is not None
    total_cost = applicant_cost + review_cost + (agency_cost or 0.0)
    dollars_awarded = awards * mean_award_size
    hours_per_award = (applicant_hours + review_hours) / awards
    return TransactionCost(
        hours_per_award=hours_per_award,
        applicant_hours_per_award=applicant_hours / awards,
        review_hours_per_award=review_hours / awards,
        dollars_per_award=total_cost / awards,
        dollars_per_award_dollar=total_cost / dollars_awarded,
        hours_per_million_awarded=(
            (applicant_hours + review_hours) / dollars_awarded * per_million_dollars
        ),
        gc_included=gc_included,
        applicant_hours=applicant_hours,
        review_hours=review_hours,
    )


def _require_mapping(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = raw.get(key)
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"expected mapping for {key}")
    return value


def _require_list(raw: Mapping[str, Any], key: str) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise ConfigurationError(f"expected list for {key}")
    return value


def load_assumptions(path: Path) -> dict[str, Any]:
    raw = read_yaml_mapping(path, description="assumptions")
    forbidden = raw.get("forbidden_hour_sources", [])
    if not isinstance(forbidden, list):
        raise ConfigurationError("forbidden_hour_sources must be a list")
    unknown = set(forbidden) - FORBIDDEN_HOUR_SOURCES
    if unknown:
        raise ConfigurationError(f"unsupported forbidden hour source: {sorted(unknown)}")
    citations = raw.get("applicant_hour_citations", {})
    if isinstance(citations, Mapping):
        for citation in citations.values():
            if isinstance(citation, Mapping):
                refuse_forbidden_hour_source(str(citation.get("evidence_class", "")))
    return dict(raw)


def load_sources(path: Path) -> dict[str, Any]:
    return dict(read_yaml_mapping(path, description="sources"))


def _parse_optional_float(value: str) -> float | None:
    if value == "":
        return None
    return float(value)


def _apply_duration(
    row: MechanismYear,
    convention: str,
    r01_project_years: float,
    control_mechanism: str,
) -> MechanismYear:
    mean_size = row.mean_award_size
    dollars = row.dollars_awarded
    if convention == PROJECT_CONVENTION and row.mechanism == control_mechanism:
        if mean_size is None:
            raise ConfigurationError("project_total requires mean_award_size on the control")
        mean_size = mean_size * r01_project_years
        dollars = row.awards * mean_size
    elif convention not in {ANNUAL_CONVENTION, PROJECT_CONVENTION}:
        raise ConfigurationError(f"unknown duration convention {convention}")
    return MechanismYear(
        agency=row.agency,
        mechanism=row.mechanism,
        program=row.program,
        phase=row.phase,
        fiscal_year=row.fiscal_year,
        applications=row.applications,
        awards=row.awards,
        success_rate=row.success_rate,
        dollars_awarded=dollars,
        mean_award_size=mean_size,
        award_size_basis=row.award_size_basis,
        source_id=row.source_id,
        evidence_class=row.evidence_class,
        duration_convention=convention,
    )


def load_mechanism_years(
    sources: Mapping[str, Any],
    *,
    repository_root: Path,
    duration_convention: str,
    r01_project_years: float,
    control_mechanism: str,
) -> list[MechanismYear]:
    tables = sources.get("tables")
    if not isinstance(tables, list) or not tables:
        raise ConfigurationError("sources.yaml must list tables")
    rows: list[MechanismYear] = []
    for table in tables:
        if not isinstance(table, Mapping):
            raise ConfigurationError("each sources.tables entry must be a mapping")
        relative = str(table["path"])
        path = repository_root / relative
        expected = str(table["sha256"])
        actual = sha256_file(path)
        if actual != expected:
            raise ConfigurationError(
                f"SHA-256 mismatch for {relative}: expected {expected}, found {actual}"
            )
        evidence_class = str(table["evidence_class"])
        with path.open(newline="") as handle:
            for raw in csv.DictReader(handle):
                applications = int(raw["applications"])
                awards = int(raw["awards"])
                mean_size = _parse_optional_float(raw["mean_award_size"])
                rows.append(
                    _apply_duration(
                        MechanismYear(
                            agency=raw["agency"],
                            mechanism=raw["mechanism"],
                            program=raw["program"],
                            phase=raw["phase"],
                            fiscal_year=int(raw["fiscal_year"]),
                            applications=applications,
                            awards=awards,
                            success_rate=success_rate(applications, awards),
                            dollars_awarded=float(raw["dollars_awarded"]),
                            mean_award_size=mean_size,
                            award_size_basis=raw["award_size_basis"],
                            source_id=raw["source_id"],
                            evidence_class=evidence_class,
                            duration_convention=duration_convention,
                        ),
                        duration_convention,
                        r01_project_years,
                        control_mechanism,
                    )
                )
    return rows


def _labor_rate(assumptions: Mapping[str, Any], rate_id: str) -> float:
    for entry in _require_list(assumptions, "labor_rates"):
        if isinstance(entry, Mapping) and entry.get("id") == rate_id:
            return float(entry["usd_per_hour"])
    raise ConfigurationError(f"unknown labor rate {rate_id}")


def _hours_for(assumptions: Mapping[str, Any], mechanism: str) -> list[float]:
    scenarios = _require_mapping(assumptions, "applicant_hour_scenarios")
    values = scenarios.get(mechanism)
    if not isinstance(values, list) or not values:
        raise ConfigurationError(f"no applicant_hour_scenarios for {mechanism}")
    return [float(item) for item in values]


def _reviewers_for(assumptions: Mapping[str, Any], mechanism: str) -> list[float]:
    review = _require_mapping(assumptions, "review")
    mapping = _require_mapping(review, "reviewers_per_application")
    values = mapping.get(mechanism)
    if not isinstance(values, list) or not values:
        raise ConfigurationError(f"no reviewers_per_application for {mechanism}")
    return [float(item) for item in values]


def _agency_cost(
    assumptions: Mapping[str, Any], mechanism: str, dollars_awarded: float
) -> float | None:
    spec = _require_mapping(assumptions, "agency_cost")
    mode = str(spec.get("mode", "missing"))
    if mode == "missing":
        return None
    if mode == "sbir_admin_allowance_ceiling":
        if mechanism.startswith("nih_sbir_") or mechanism.startswith("nih_sttr_"):
            return float(spec["sbir_admin_allowance_ceiling"]) * dollars_awarded
        return None
    raise ConfigurationError(f"unknown agency_cost.mode {mode}")


def index_by_mechanism_year(
    rows: Sequence[MechanismYear],
) -> dict[tuple[str, int, str], MechanismYear]:
    return {(row.mechanism, row.fiscal_year, row.duration_convention): row for row in rows}


def comparison_years(rows: Sequence[MechanismYear], left: str, right: str) -> list[int]:
    left_years = {row.fiscal_year for row in rows if row.mechanism == left and row.awards > 0}
    right_years = {row.fiscal_year for row in rows if row.mechanism == right and row.awards > 0}
    return sorted(left_years & right_years)


def break_even_table(
    rows: Sequence[MechanismYear],
    assumptions: Mapping[str, Any],
) -> list[dict[str, Any]]:
    comparison = _require_mapping(assumptions, "comparison")
    treatment = str(comparison["treatment_mechanism"])
    control = str(comparison["control_mechanism"])
    duration = _require_mapping(assumptions, "duration")
    indexed = index_by_mechanism_year(rows)
    records: list[dict[str, Any]] = []
    for h_control in _hours_for(assumptions, control):
        for year in comparison_years(rows, treatment, control):
            for convention in duration["conventions"]:
                treat = indexed[(treatment, year, str(convention))]
                ctrl = indexed[(control, year, str(convention))]
                if treat.success_rate is None or ctrl.success_rate is None:
                    continue
                if treat.mean_award_size is None or ctrl.mean_award_size is None:
                    continue
                threshold = breakeven_sbir_hours(
                    h_control,
                    treat.success_rate,
                    treat.mean_award_size,
                    ctrl.success_rate,
                    ctrl.mean_award_size,
                )
                records.append(
                    {
                        "fiscal_year": year,
                        "duration_convention": convention,
                        "treatment_mechanism": treatment,
                        "control_mechanism": control,
                        "h_control": h_control,
                        "h_treatment_breakeven": threshold,
                        "treatment_success_rate": treat.success_rate,
                        "control_success_rate": ctrl.success_rate,
                        "treatment_mean_award_size": treat.mean_award_size,
                        "control_mean_award_size": ctrl.mean_award_size,
                        "treatment_award_dollars_per_application": award_dollars_per_application(
                            treat.success_rate, treat.mean_award_size
                        ),
                        "control_award_dollars_per_application": award_dollars_per_application(
                            ctrl.success_rate, ctrl.mean_award_size
                        ),
                    }
                )
    return records


def reviewer_break_even_table(
    rows: Sequence[MechanismYear],
    assumptions: Mapping[str, Any],
) -> list[dict[str, Any]]:
    comparison = _require_mapping(assumptions, "comparison")
    treatment = str(comparison["treatment_mechanism"])
    control = str(comparison["control_mechanism"])
    duration = _require_mapping(assumptions, "duration")
    review = _require_mapping(assumptions, "review")
    indexed = index_by_mechanism_year(rows)
    records: list[dict[str, Any]] = []
    for reviewer_hours_control in review["reviewer_hours"]:
        for reviewers_t in _reviewers_for(assumptions, treatment):
            for reviewers_c in _reviewers_for(assumptions, control):
                for year in comparison_years(rows, treatment, control):
                    for convention in duration["conventions"]:
                        treat = indexed[(treatment, year, str(convention))]
                        ctrl = indexed[(control, year, str(convention))]
                        if treat.success_rate is None or ctrl.success_rate is None:
                            continue
                        if treat.mean_award_size is None or ctrl.mean_award_size is None:
                            continue
                        threshold = breakeven_reviewer_hours(
                            float(reviewer_hours_control),
                            reviewers_t,
                            reviewers_c,
                            treat.success_rate,
                            treat.mean_award_size,
                            ctrl.success_rate,
                            ctrl.mean_award_size,
                        )
                        records.append(
                            {
                                "fiscal_year": year,
                                "duration_convention": convention,
                                "reviewer_hours_control": float(reviewer_hours_control),
                                "reviewers_treatment": reviewers_t,
                                "reviewers_control": reviewers_c,
                                "reviewer_hours_treatment_breakeven": threshold,
                            }
                        )
    return records


def metrics_table(
    rows: Sequence[MechanismYear],
    assumptions: Mapping[str, Any],
    *,
    labor_rate_id: str | None = None,
) -> list[dict[str, Any]]:
    rate_id = labor_rate_id or str(assumptions["default_labor_rate_id"])
    wage = _labor_rate(assumptions, rate_id)
    review = _require_mapping(assumptions, "review")
    reviewer_wage = _labor_rate(assumptions, str(review["reviewer_labor_rate_id"]))
    per_million = float(assumptions["per_million_dollars"])
    records: list[dict[str, Any]] = []
    for row in rows:
        if row.awards <= 0 or row.applications <= 0 or row.mean_award_size is None:
            continue
        try:
            hour_grid = _hours_for(assumptions, row.mechanism)
            reviewer_grid = _reviewers_for(assumptions, row.mechanism)
        except ConfigurationError:
            continue
        for hours in hour_grid:
            for reviewers in reviewer_grid:
                for reviewer_hours in review["reviewer_hours"]:
                    agency_cost = _agency_cost(
                        assumptions, row.mechanism, row.awards * row.mean_award_size
                    )
                    cost = transaction_cost(
                        applications=row.applications,
                        awards=row.awards,
                        mean_award_size=row.mean_award_size,
                        hours_per_application=hours,
                        wage=wage,
                        reviewers_per_application=reviewers,
                        reviewer_hours=float(reviewer_hours),
                        reviewer_wage=reviewer_wage,
                        agency_cost=agency_cost,
                        per_million_dollars=per_million,
                    )
                    record = asdict(row)
                    record.update(asdict(cost))
                    record.update(
                        {
                            "hours_per_application": hours,
                            "reviewers_per_application": reviewers,
                            "reviewer_hours": float(reviewer_hours),
                            "labor_rate_id": rate_id,
                            "wage": wage,
                            "reviewer_wage": reviewer_wage,
                            "applications_per_award": row.applications / row.awards,
                            "award_dollars_per_application": award_dollars_per_application(
                                row.success_rate, row.mean_award_size
                            ),
                        }
                    )
                    records.append(record)
    return records


def sensitivity_grid(
    rows: Sequence[MechanismYear],
    assumptions: Mapping[str, Any],
) -> list[dict[str, Any]]:
    comparison = _require_mapping(assumptions, "comparison")
    treatment = str(comparison["treatment_mechanism"])
    control = str(comparison["control_mechanism"])
    duration = _require_mapping(assumptions, "duration")
    shocks = _require_mapping(assumptions, "sensitivity")
    wage = _labor_rate(assumptions, str(assumptions["default_labor_rate_id"]))
    review = _require_mapping(assumptions, "review")
    reviewer_wage = _labor_rate(assumptions, str(review["reviewer_labor_rate_id"]))
    per_million = float(assumptions["per_million_dollars"])
    indexed = index_by_mechanism_year(rows)
    records: list[dict[str, Any]] = []
    reviewer_hours_t = float(review["reviewer_hours"][len(review["reviewer_hours"]) // 2])
    reviewers_t = _reviewers_for(assumptions, treatment)[0]
    reviewers_c = _reviewers_for(assumptions, control)[0]
    for h_t in _hours_for(assumptions, treatment):
        for h_c in _hours_for(assumptions, control):
            for year in comparison_years(rows, treatment, control):
                for convention in duration["conventions"]:
                    treat = indexed[(treatment, year, str(convention))]
                    ctrl = indexed[(control, year, str(convention))]
                    if treat.mean_award_size is None or ctrl.mean_award_size is None:
                        continue
                    if treat.success_rate is None or ctrl.success_rate is None:
                        continue
                    for s_shock in shocks["success_rate_relative_shocks"]:
                        for d_shock in shocks["award_size_relative_shocks"]:
                            s_t = treat.success_rate * (1.0 + float(s_shock))
                            s_c = ctrl.success_rate * (1.0 + float(s_shock))
                            d_t = treat.mean_award_size * (1.0 + float(d_shock))
                            d_c = ctrl.mean_award_size * (1.0 + float(d_shock))
                            if min(s_t, s_c, d_t, d_c) <= 0:
                                continue
                            apps_t = treat.awards / s_t
                            apps_c = ctrl.awards / s_c
                            cost_t = transaction_cost(
                                applications=apps_t,
                                awards=treat.awards,
                                mean_award_size=d_t,
                                hours_per_application=h_t,
                                wage=wage,
                                reviewers_per_application=reviewers_t,
                                reviewer_hours=reviewer_hours_t,
                                reviewer_wage=reviewer_wage,
                                agency_cost=None,
                                per_million_dollars=per_million,
                            )
                            cost_c = transaction_cost(
                                applications=apps_c,
                                awards=ctrl.awards,
                                mean_award_size=d_c,
                                hours_per_application=h_c,
                                wage=wage,
                                reviewers_per_application=reviewers_c,
                                reviewer_hours=reviewer_hours_t,
                                reviewer_wage=reviewer_wage,
                                agency_cost=None,
                                per_million_dollars=per_million,
                            )
                            t_per = cost_t.dollars_per_award_dollar
                            c_per = cost_c.dollars_per_award_dollar
                            if t_per is None or c_per is None:
                                continue
                            records.append(
                                {
                                    "fiscal_year": year,
                                    "duration_convention": convention,
                                    "h_treatment": h_t,
                                    "h_control": h_c,
                                    "success_rate_shock": float(s_shock),
                                    "award_size_shock": float(d_shock),
                                    "treatment_tc_per_dollar": t_per,
                                    "control_tc_per_dollar": c_per,
                                    "treatment_cheaper_per_dollar": t_per < c_per,
                                }
                            )
    return records


def ranking_flip_summary(sensitivity_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[bool]] = {}
    for row in sensitivity_rows:
        key = (
            row["duration_convention"],
            row["h_treatment"],
            row["h_control"],
            row["success_rate_shock"],
            row["award_size_shock"],
        )
        groups.setdefault(key, []).append(bool(row["treatment_cheaper_per_dollar"]))
    records = []
    for key, flags in sorted(groups.items()):
        cheaper = sum(flags)
        records.append(
            {
                "duration_convention": key[0],
                "h_treatment": key[1],
                "h_control": key[2],
                "success_rate_shock": key[3],
                "award_size_shock": key[4],
                "years_treatment_cheaper": cheaper,
                "years": len(flags),
                "always_treatment_cheaper": cheaper == len(flags),
                "always_control_cheaper": cheaper == 0,
            }
        )
    return records


def complexity_index(path: Path) -> list[dict[str, Any]]:
    raw = read_yaml_mapping(path, description="complexity rules")
    mechanisms = _require_mapping(raw, "mechanisms")
    records = []
    for mechanism, spec in mechanisms.items():
        if not isinstance(spec, Mapping):
            continue
        score = (
            int(spec.get("research_strategy_pages", 0))
            + int(spec.get("specific_aims_pages", 0))
            + int(spec.get("commercialization_plan_pages", 0))
            + (2 if spec.get("research_institution_coordination") else 0)
            + (1 if spec.get("commercialization_plan_required") else 0)
            + len(spec.get("registrations", []))
            + len(spec.get("certifications", []))
        )
        records.append(
            {
                "mechanism": mechanism,
                "label": spec.get("label"),
                "research_strategy_pages": spec.get("research_strategy_pages"),
                "commercialization_plan_pages": spec.get("commercialization_plan_pages"),
                "research_institution_coordination": spec.get("research_institution_coordination"),
                "registrations": spec.get("registrations"),
                "certifications": spec.get("certifications"),
                "complexity_score": score,
                "measures_hours": False,
            }
        )
    return records


def load_all_duration_rows(
    sources: Mapping[str, Any],
    assumptions: Mapping[str, Any],
    *,
    repository_root: Path,
) -> list[MechanismYear]:
    duration = _require_mapping(assumptions, "duration")
    comparison = _require_mapping(assumptions, "comparison")
    control = str(comparison["control_mechanism"])
    rows: list[MechanismYear] = []
    for convention in duration["conventions"]:
        rows.extend(
            load_mechanism_years(
                sources,
                repository_root=repository_root,
                duration_convention=str(convention),
                r01_project_years=float(duration["r01_project_years"]),
                control_mechanism=control,
            )
        )
    return rows


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run(
    *,
    sources_path: Path = DEFAULT_SOURCES,
    assumptions_path: Path = DEFAULT_ASSUMPTIONS,
    complexity_path: Path = DEFAULT_COMPLEXITY,
    out_dir: Path,
    repository_root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    sources = load_sources(sources_path)
    assumptions = load_assumptions(assumptions_path)
    rows = load_all_duration_rows(sources, assumptions, repository_root=repository_root)
    breakeven = break_even_table(rows, assumptions)
    reviewer_breakeven = reviewer_break_even_table(rows, assumptions)
    metrics = metrics_table(rows, assumptions)
    sensitivity = sensitivity_grid(rows, assumptions)
    flips = ranking_flip_summary(sensitivity)
    complexity = complexity_index(complexity_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "mechanism_year.csv", [asdict(row) for row in rows])
    _write_csv(out_dir / "metrics.csv", metrics)
    _write_csv(out_dir / "breakeven.csv", breakeven)
    _write_csv(out_dir / "reviewer_breakeven.csv", reviewer_breakeven)
    _write_csv(out_dir / "sensitivity.csv", sensitivity)
    _write_csv(out_dir / "ranking_flips.csv", flips)
    _write_csv(out_dir / "complexity_index.csv", complexity)
    summary = {
        "mechanism_years": len(rows),
        "breakeven_rows": len(breakeven),
        "metrics_rows": len(metrics),
        "sensitivity_rows": len(sensitivity),
        "gc_mode": assumptions["agency_cost"]["mode"],
        "comparison": assumptions["comparison"],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--assumptions", type=Path, default=DEFAULT_ASSUMPTIONS)
    parser.add_argument("--complexity", type=Path, default=DEFAULT_COMPLEXITY)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPOSITORY_ROOT / "data/reports/allocation-transaction-costs",
    )
    args = parser.parse_args(argv)
    summary = run(
        sources_path=args.sources,
        assumptions_path=args.assumptions,
        complexity_path=args.complexity,
        out_dir=args.out,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
