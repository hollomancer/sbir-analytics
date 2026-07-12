"""Dagster asset for Phase 2 agency-vs-Form-D matched cohort analysis."""

import json
from pathlib import Path
from typing import Any

import pandas as pd
from dagster import AssetExecutionContext, Config, MetadataValue, Output, asset

from .control_cohort import (
    AgencyAwardeeFilter,
    PrivateCapitalControlCohortBuilder,
    agency_leverage_cross_check,
)
from .form_d_inputs import (
    DEFAULT_FORM_D_CONTROL_UNIVERSE_PATH,
    DEFAULT_FORM_D_MATCHES_PATH,
    load_form_d_control_universe,
    load_form_d_matches,
)
from .matching import CohortMatcher, _pairs_frame
from .phase2_outcomes import MatchedCohortOutcomes, _outcome_frame, keys_from_ma_events
from .threats import ThreatsToValidity


DEFAULT_OUTPUT_ROOT = Path("data/processed/agency_private_capital")
DEFAULT_MA_EVENTS_PATH = Path("data/sbir_ma_events.jsonl")


class AgencyPrivateCapitalPhase2Config(Config):
    """Run config for the Phase 2 matched Form D comparison."""

    agency_code: str = "NSF"
    form_d_matches_path: str = str(DEFAULT_FORM_D_MATCHES_PATH)
    form_d_control_universe_path: str = str(DEFAULT_FORM_D_CONTROL_UNIVERSE_PATH)
    ma_events_path: str = str(DEFAULT_MA_EVENTS_PATH)
    controls_per_treated: int = 3
    year_min: int = 2009
    year_max: int = 2024
    output_dir: str | None = None


@asset(
    name="agency_private_capital_form_d_matched_comparison",
    group_name="agency_private_capital",
    compute_kind="pandas",
    description=(
        "Phase 2 Form D matched-control comparison for a configured SBIR agency. "
        "Builds agency Form D awardee cohort, non-SBIR Form D controls, coarsened-"
        "exact matches, outcome rows, balance metadata, and threats-to-validity gate."
    ),
)
def agency_private_capital_form_d_matched_comparison(
    context: AssetExecutionContext,
    config: AgencyPrivateCapitalPhase2Config,
    enriched_sbir_awards: pd.DataFrame,
) -> Output[str]:
    output_dir = (
        Path(config.output_dir)
        if config.output_dir
        else DEFAULT_OUTPUT_ROOT / config.agency_code.lower()
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison_path = output_dir / "agency_vs_form_d_comparison.parquet"
    pairs_path = output_dir / "agency_vs_form_d_matched_pairs.parquet"
    md_path = output_dir / "agency_vs_form_d_comparison.md"
    threats_path = output_dir / "threats_to_validity.json"
    balance_path = output_dir / "match_balance.json"

    form_d_matches_path = Path(config.form_d_matches_path)
    control_path = Path(config.form_d_control_universe_path)
    missing_inputs = [
        str(path) for path in (form_d_matches_path, control_path) if not path.exists()
    ]
    if missing_inputs:
        threats_payload = ThreatsToValidity().write(threats_path)
        md_path.write_text(
            _missing_inputs_markdown(config.agency_code, missing_inputs), encoding="utf-8"
        )
        _outcome_frame([]).to_parquet(comparison_path, index=False)
        _pairs_frame([]).to_parquet(pairs_path, index=False)
        balance_path.write_text(
            json.dumps({"status": "missing_inputs", "missing_inputs": missing_inputs}, indent=2),
            encoding="utf-8",
        )
        return Output(
            str(md_path),
            metadata={
                "status": "missing_inputs",
                "missing_inputs": MetadataValue.json(missing_inputs),
                "threats_passed": bool(threats_payload["passed"]),
            },
        )

    form_d_matches = load_form_d_matches(
        form_d_matches_path,
        tier_filter={"high"},
        year_min=config.year_min,
        year_max=config.year_max,
    )
    sbir_ciks = set(form_d_matches["form_d_cik"].dropna().astype(str))
    controls_universe = load_form_d_control_universe(
        control_path,
        sbir_ciks=sbir_ciks,
        year_min=config.year_min,
        year_max=config.year_max,
    )
    treated = AgencyAwardeeFilter(agency_code=config.agency_code).build(
        enriched_sbir_awards, form_d_matches
    )
    controls = PrivateCapitalControlCohortBuilder().build(controls_universe)
    pairs, balance = CohortMatcher(controls_per_treated=config.controls_per_treated).match(
        treated, controls
    )
    balance["agency_leverage_cross_check"] = agency_leverage_cross_check(
        config.agency_code,
        enriched_sbir_awards,
        treated,
    )
    ma_keys = keys_from_ma_events(config.ma_events_path)
    outcomes = MatchedCohortOutcomes(ma_event_keys=ma_keys).compute(pairs)
    threats_payload = ThreatsToValidity().write(threats_path)

    pairs.to_parquet(pairs_path, index=False)
    outcomes.to_parquet(comparison_path, index=False)
    balance_path.write_text(json.dumps(balance, indent=2, default=str), encoding="utf-8")
    md_path.write_text(
        _comparison_markdown(
            agency_code=config.agency_code,
            outcomes=outcomes,
            balance=balance,
            threats_passed=bool(threats_payload["passed"]),
        ),
        encoding="utf-8",
    )

    context.log.info(
        "Phase 2 agency private-capital matched comparison complete",
        extra={"agency_code": config.agency_code, "balance": balance},
    )
    return Output(
        str(md_path),
        metadata={
            "status": "complete",
            "agency_code": config.agency_code,
            "treated_count": int(balance["treated_count"]),
            "control_count": int(balance["control_count"]),
            "matched_treated_count": int(balance["matched_treated_count"]),
            "match_rate": MetadataValue.float(float(balance["match_rate"])),
            "comparison_path": str(comparison_path),
            "pairs_path": str(pairs_path),
            "threats_path": str(threats_path),
            "threats_passed": bool(threats_payload["passed"]),
        },
    )


def _missing_inputs_markdown(agency_code: str, missing_inputs: list[str]) -> str:
    lines = [
        f"# {agency_code} SBIR vs. Form D Matched Controls",
        "",
        "Phase 2 did not run because required input artifacts are missing.",
        "",
        "| Missing input |",
        "| --- |",
    ]
    lines.extend(f"| `{path}` |" for path in missing_inputs)
    lines.append("")
    return "\n".join(lines)


def _comparison_markdown(
    *,
    agency_code: str,
    outcomes: pd.DataFrame,
    balance: dict[str, Any],
    threats_passed: bool,
) -> str:
    leverage = balance.get("agency_leverage_cross_check", {})
    lines = [
        f"# {agency_code} SBIR vs. Form D Matched Controls",
        "",
        "Descriptive comparison only. Coarsened-exact matching uses filing/award vintage, "
        "Form D industry group, and state.",
        "",
        "## Match Balance",
        "",
        f"- Treated firms: {balance['treated_count']}",
        f"- Control issuers: {balance['control_count']}",
        f"- Matched treated firms: {balance['matched_treated_count']}",
        f"- Unmatched treated firms: {balance['unmatched_treated_count']}",
        f"- Match rate: {balance['match_rate']:.1%}",
        "",
        "## Agency Leverage Cross-Check",
        "",
        f"- Agency SBIR denominator: {_money(leverage.get('agency_program_sbir_amount'))}",
        f"- Matched agency SBIR amount: {_money(leverage.get('matched_agency_sbir_amount'))}",
        f"- Matched Form D raised: {_money(leverage.get('matched_form_d_raised'))}",
        "- Form D / agency SBIR denominator: "
        f"{_multiple(leverage.get('form_d_to_agency_program_ratio'))}",
        "- Form D / matched SBIR amount: "
        f"{_multiple(leverage.get('form_d_to_matched_sbir_ratio'))}",
        "",
        "## Outcome Rows",
        "",
        "| Cohort | Metric | Rate | n | Available |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    if outcomes.empty:
        lines.append("| n/a | n/a | n/a | 0 | false |")
    else:
        for _, row in outcomes.iterrows():
            rate = row.get("rate")
            rate_text = "n/a" if pd.isna(rate) else f"{float(rate):.1%}"
            lines.append(
                f"| {row['cohort']} | {row['metric']} | {rate_text} | "
                f"{int(row['denominator'])} | {bool(row['available'])} |"
            )
    lines.extend(
        [
            "",
            "## Threats Gate",
            "",
            "Passed." if threats_passed else "Failed. Headline interpretation is suppressed.",
            "",
        ]
    )
    return "\n".join(lines)


def _money(value: object) -> str:
    parsed = _float_or_none(value)
    if parsed is None:
        return "n/a"
    return f"${parsed:,.0f}"


def _multiple(value: object) -> str:
    parsed = _float_or_none(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.2f}x"


def _float_or_none(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(str(value))
    except ValueError:
        return None
