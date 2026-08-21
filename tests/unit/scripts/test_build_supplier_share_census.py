"""Focused tests for the exploratory supplier-share census producer."""

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest


SCRIPT = Path(__file__).parents[3] / "scripts/data/build_supplier_share_census.py"
SPEC = importlib.util.spec_from_file_location("build_supplier_share_census", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _firm(
    firm_id: str,
    *,
    first_year: int,
    last_year: int,
    award_count: int,
    dollars: float,
    form_d_signal: bool = False,
    ma_signal: bool = False,
    contract_signal: bool = False,
    searchable: bool = True,
) -> dict[str, object]:
    observation_years = 2026 - first_year
    return {
        "firm_key": f"NAME:{firm_id}",
        "firm_id": firm_id,
        "private_firm_name": f"Private {firm_id}",
        "source_name_count": 1,
        "award_count": award_count,
        "award_count_stratum": MODULE._award_count_stratum(award_count),
        "first_award_year": first_year,
        "last_award_year": last_year,
        "award_tenure_years": last_year - first_year,
        "observation_years": observation_years,
        "cumulative_sbir_dollars": dollars,
        "award_amount_observed_count": award_count,
        "first_explicit_phase_ii_end": pd.Timestamp(f"{first_year}-12-31"),
        "primary_agency_group": "DoD",
        "agency_membership_block": "DoD",
        "dod_award_dollars": dollars,
        "hhs_award_dollars": 0.0,
        "nsf_award_dollars": 0.0,
        "other_award_dollars": 0.0,
        "dod_award_count": award_count,
        "hhs_award_count": 0,
        "nsf_award_count": 0,
        "other_award_count": 0,
        "post_phase_ii_net_prime_obligations": 1.0 if contract_signal else 0.0,
        "post_phase_ii_contract_action_count": 1 if contract_signal else 0,
        "contract_persistence_fired": contract_signal,
        "form_d_signal": form_d_signal,
        "form_d_searchable": searchable,
        "ma_signal": ma_signal,
        "ma_searchable": searchable,
        "ipo_signal": False,
    }


def _base(*, searchable: bool) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _firm(
                "firm-a",
                first_year=1990,
                last_year=2002,
                award_count=2,
                dollars=100.0,
                searchable=searchable,
            ),
            _firm(
                "firm-b",
                first_year=1995,
                last_year=1996,
                award_count=10,
                dollars=200.0,
                form_d_signal=True,
                searchable=searchable,
            ),
            _firm(
                "firm-c",
                first_year=2000,
                last_year=2001,
                award_count=2,
                dollars=300.0,
                searchable=searchable,
            ),
            _firm(
                "firm-d",
                first_year=1990,
                last_year=1992,
                award_count=2,
                dollars=400.0,
                ma_signal=True,
                contract_signal=True,
                searchable=searchable,
            ),
            _firm(
                "firm-e",
                first_year=2020,
                last_year=2021,
                award_count=2,
                dollars=500.0,
                searchable=searchable,
            ),
            _firm(
                "firm-f",
                first_year=1998,
                last_year=1999,
                award_count=2,
                dollars=600.0,
                searchable=searchable,
            ),
        ]
    )


def _central(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[
        frame["t_years"].eq(10) & frame["n_awards"].eq(6) & frame["window_years"].eq(15)
    ]


def test_missing_required_searches_stay_unknown_and_suppress_headline(tmp_path: Path) -> None:
    base = _base(searchable=False)
    grid = MODULE._build_grid(base)
    central = _central(grid).set_index("firm_id")

    assert len(grid) == 6 * 18
    assert "private_firm_name" not in grid
    assert "firm_key" not in grid
    assert central.at["firm-a", "venture_state"] == "unknown_venture"
    assert central.at["firm-a", "signal_absent_reason"] == "not_searchable"
    assert central.at["firm-b", "venture_state"] == "venture"
    assert central.at["firm-b", "signal_absent_reason"] == "signal_present"
    assert central.at["firm-e", "signal_absent_reason"] == "window_censored"
    assert central["validation_status"].eq("blocked_missing_required_signal_inputs").all()

    summary = MODULE._build_summary(grid)
    total = summary.loc[
        summary["is_central_grid"]
        & summary["stratification"].eq("overall")
        & summary["matrix_cell"].eq("TOTAL")
    ].iloc[0]
    assert not total["headline_available"]
    assert pd.isna(total["supplier_firm_share"])
    assert pd.isna(total["supplier_dollar_share"])
    assert not MODULE._write_validation_sample(base, grid, tmp_path / "sample.csv")


def test_complete_searches_emit_matrix_arithmetic_sample_and_curve(tmp_path: Path) -> None:
    base = _base(searchable=True)
    grid = MODULE._build_grid(base)
    central = _central(grid).set_index("firm_id")

    assert central.at["firm-a", "matrix_cell"] == "persistent_no_venture"
    assert central.at["firm-b", "matrix_cell"] == "persistent_venture"
    assert central.at["firm-c", "matrix_cell"] == "not_persistent_no_venture"
    assert central.at["firm-d", "matrix_cell"] == "persistent_venture"
    assert central.at["firm-e", "venture_state"] == "unknown_venture"
    assert central.at["firm-f", "matrix_cell"] == "not_persistent_no_venture"
    assert central.at["firm-f", "cumulative_dollar_decile"] == 1
    assert central.at["firm-a", "cumulative_dollar_decile"] == 9
    assert (
        central.loc[central["headline_eligible"], "validation_status"]
        .eq("pending_hand_adjudication")
        .all()
    )

    summary = MODULE._build_summary(grid)
    total = summary.loc[
        summary["is_central_grid"]
        & summary["stratification"].eq("overall")
        & summary["matrix_cell"].eq("TOTAL")
    ].iloc[0]
    assert total["total_firms"] == 5
    assert total["headline_available"]
    assert total["supplier_firm_share"] == pytest.approx(1 / 5)
    assert total["supplier_dollar_share"] == pytest.approx(100 / 1600)
    assert total["supplier_top_decile_dollar_share"] == pytest.approx(0.0)
    assert pd.notna(total["placebo_supplier_dollar_share"])
    assert total["supplier_minus_placebo_dollar_share"] == pytest.approx(
        total["supplier_dollar_share"] - total["placebo_supplier_dollar_share"]
    )

    deciles = summary.loc[
        summary["is_central_grid"]
        & summary["stratification"].eq("cumulative_dollar_decile")
        & summary["matrix_cell"].eq("TOTAL")
    ]
    assert list(deciles["stratum"]) == [f"D{value:02d}" for value in range(1, 11)]
    assert deciles["firm_count"].sum() == 5

    sample_path = tmp_path / "private" / "validation_sample.csv"
    assert MODULE._write_validation_sample(base, grid, sample_path)
    sample = pd.read_csv(sample_path)
    assert len(sample) == 5
    assert set(sample["private_firm_name"]) == {
        "Private firm-a",
        "Private firm-b",
        "Private firm-c",
        "Private firm-d",
        "Private firm-f",
    }
    assert sample["validation_status"].eq("pending_hand_adjudication").all()
    assert sample["epistemic_tier"].eq("exploratory").all()
    assert sample["citable"].eq(False).all()

    figure_path = tmp_path / "cohort_curve.svg"
    MODULE._write_figure(summary, as_of_year=2026, path=figure_path)
    figure = figure_path.read_text()
    assert "polyline" in figure
    assert "Exploratory / non-citable" in figure
    assert "12-year cutoff" in figure
    assert "15-year cutoff" in figure


def test_frozen_spec_hashes_match() -> None:
    freeze = MODULE._verify_freeze()

    assert freeze["design_sha256"] == MODULE.DESIGN_SHA256
    assert freeze["amendments_sha256"] == MODULE.AMENDMENTS_SHA256


def test_efts_error_rows_do_not_establish_ma_search_coverage(tmp_path: Path) -> None:
    firms = pd.DataFrame({"firm_key": ["NAME:alpha", "NAME:beta", "NAME:gamma"]})
    exact_names = {
        "alpha": "NAME:alpha",
        "beta": "NAME:beta",
        "gamma": "NAME:gamma",
    }
    lookups = {
        "uei": {},
        "duns": {},
        "exact_name": exact_names,
        "join_name": {MODULE._name_key(name): firm_key for name, firm_key in exact_names.items()},
        "ambiguous": {
            "uei": set(),
            "duns": set(),
            "exact_name": set(),
            "join_name": set(),
        },
    }
    scan_path = tmp_path / "efts.jsonl"
    rows = [
        {"company_name": "Alpha", "mention_count": 0},
        {"company_name": "Beta", "error": "timeout"},
        {"company_name": "Gamma", "mention_count": 0, "had_server_errors": True},
    ]
    scan_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    form_d_path = tmp_path / "form-d.jsonl"
    form_d_path.write_text("")
    awards = pd.DataFrame(
        {
            "source_name": ["Alpha", "Beta", "Gamma"],
            "firm_key": ["NAME:alpha", "NAME:beta", "NAME:gamma"],
        }
    )

    signals, metadata = MODULE._load_ma_signals(
        tmp_path / "missing-events.jsonl",
        scan_path,
        form_d_path,
        awards,
        firms,
        lookups,
        search_complete=False,
    )

    searchable = signals.set_index("firm_key")["ma_searchable"].to_dict()
    assert searchable == {
        "NAME:alpha": False,
        "NAME:beta": False,
        "NAME:gamma": False,
    }
    assert metadata["scan_rows"] == 3
    assert metadata["scan_error_rows"] == 2
    assert metadata["scan_covered_firms"] == 1
    assert metadata["derivation_consistent"] is False
    assert "distinct from upstream Form D entity-match confidence" in metadata["threshold_policy"]


def test_ma_coverage_requires_every_alias_and_complete_context(tmp_path: Path) -> None:
    firms = pd.DataFrame({"firm_key": ["NAME:alpha"]})
    awards = pd.DataFrame(
        {
            "source_name": ["Alpha", "Alpha Labs"],
            "firm_key": ["NAME:alpha", "NAME:alpha"],
        }
    )
    lookups = {
        "uei": {},
        "duns": {},
        "exact_name": {"alpha": "NAME:alpha", "alpha labs": "NAME:alpha"},
        "join_name": {
            MODULE._name_key("Alpha"): "NAME:alpha",
            MODULE._name_key("Alpha Labs"): "NAME:alpha",
        },
        "ambiguous": {
            "uei": set(),
            "duns": set(),
            "exact_name": set(),
            "join_name": set(),
        },
    }
    events_path = tmp_path / "events.jsonl"
    events_path.write_text("")
    form_d_path = tmp_path / "form-d.jsonl"
    form_d_path.write_text("")
    scan_path = tmp_path / "efts.jsonl"
    scan_path.write_text(
        json.dumps({"company_name": "Alpha", "mention_types": []})
        + "\n"
        + json.dumps(
            {
                "company_name": "Alpha Labs",
                "mention_types": ["filing_mention"],
            }
        )
        + "\n"
    )

    signals, metadata = MODULE._load_ma_signals(
        events_path,
        scan_path,
        form_d_path,
        awards,
        firms,
        lookups,
        search_complete=False,
    )

    assert not signals.iloc[0]["ma_searchable"]
    assert metadata["derivation_consistent"] is True
    assert metadata["scan_context_incomplete_rows"] == 1
    assert metadata["scan_covered_firms"] == 0


def test_jsonl_loader_fails_closed_on_malformed_rows(tmp_path: Path) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text('{"ok": true}\nnot-json\n')

    with pytest.raises(ValueError, match="malformed JSON"):
        MODULE._jsonl_rows(path)


def test_agency_firm_membership_uses_award_count_not_positive_dollars() -> None:
    base = _base(searchable=True)
    base.loc[base["firm_id"].eq("firm-a"), "cumulative_sbir_dollars"] = pd.NA
    base.loc[base["firm_id"].eq("firm-a"), "dod_award_dollars"] = pd.NA
    grid = MODULE._build_grid(base)
    summary = MODULE._build_summary(grid)
    MODULE._validate_summary(grid, summary)

    dod = summary.loc[
        summary["is_central_grid"]
        & summary["stratification"].eq("agency")
        & summary["stratum"].eq("DoD")
        & summary["matrix_cell"].eq("TOTAL")
    ].iloc[0]
    assert dod["firm_count"] == 5
