"""Tests for M&A event detection."""

import json
import sys
from pathlib import Path

import pytest

from sbir_etl.enrichers.sec_edgar.form_d_scoring import FORM_D_TIER_RULE_VERSION


sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "archive" / "data"))

from detect_sbir_ma_events import (
    assign_confidence,
    build_signals_dict,
    extract_efts_signals,
    extract_form_d_signals,
    is_acquirer_side_only,
    main,
    merge_events,
)


def test_extract_form_d_signals_finds_business_combination():
    records = [
        {
            "company_name": "ACME INC",
            "match_confidence": {
                "rule_version": FORM_D_TIER_RULE_VERSION,
                "tier": "high",
            },
            "offerings": [
                {
                    "filing_date": "2019-03-15",
                    "is_business_combination": True,
                    "total_amount_sold": 25_000_000,
                    "related_persons": [{"name": "Jane Doe", "title": "Executive Officer"}],
                },
                {
                    "filing_date": "2020-01-01",
                    "is_business_combination": False,
                    "total_amount_sold": 5_000_000,
                    "related_persons": [],
                },
            ],
        }
    ]
    events = extract_form_d_signals(records)
    assert len(events) == 1
    e = events[0]
    assert e["company_name"] == "ACME INC"
    assert e["event_date"] == "2019-03-15"
    assert e["form_d_detail"]["total_amount_sold"] == 25_000_000
    assert e["form_d_detail"]["related_persons"][0]["name"] == "Jane Doe"
    assert e["form_d_detail"]["tier_rule_version"] == FORM_D_TIER_RULE_VERSION


def test_extract_form_d_signals_skips_non_combo():
    records = [
        {
            "company_name": "BORING INC",
            "match_confidence": {
                "rule_version": FORM_D_TIER_RULE_VERSION,
                "tier": "medium",
            },
            "offerings": [
                {
                    "filing_date": "2020-06-01",
                    "is_business_combination": False,
                    "total_amount_sold": 1_000_000,
                    "related_persons": [],
                }
            ],
        }
    ]
    events = extract_form_d_signals(records)
    assert len(events) == 0


def test_extract_form_d_signals_uses_earliest_combo_date():
    records = [
        {
            "company_name": "MULTI INC",
            "match_confidence": {
                "rule_version": FORM_D_TIER_RULE_VERSION,
                "tier": "high",
            },
            "offerings": [
                {
                    "filing_date": "2021-06-01",
                    "is_business_combination": True,
                    "total_amount_sold": 10_000_000,
                    "related_persons": [{"name": "A", "title": "Director"}],
                },
                {
                    "filing_date": "2020-01-15",
                    "is_business_combination": True,
                    "total_amount_sold": 5_000_000,
                    "related_persons": [{"name": "B", "title": "Director"}],
                },
            ],
        }
    ]
    events = extract_form_d_signals(records)
    assert len(events) == 1
    assert events[0]["event_date"] == "2020-01-15"


def test_extract_form_d_signals_refuses_unversioned_tiers():
    with pytest.raises(ValueError, match="Rescore the complete input"):
        extract_form_d_signals(
            [
                {
                    "company_name": "LEGACY INC",
                    "match_confidence": {"tier": "high"},
                    "offerings": [],
                }
            ]
        )


# --- EFTS extraction ---


def test_extract_efts_signals_subsidiary():
    records = [
        {
            "company_name": "TARGET INC",
            "mention_types": ["subsidiary", "filing_mention"],
            "mention_filers": ["BIG CORP"],
            "latest_mention_date": "2020-06-15",
        }
    ]
    events = extract_efts_signals(records)
    assert len(events) == 1
    assert events[0]["efts_detail"]["efts_tier"] == "high"
    assert events[0]["efts_detail"]["mention_filers"] == ["BIG CORP"]


def test_extract_efts_signals_skips_passive():
    records = [
        {
            "company_name": "PASSIVE INC",
            "mention_types": ["ownership_passive"],
            "mention_filers": ["FUND LP"],
            "latest_mention_date": "2021-01-01",
        }
    ]
    events = extract_efts_signals(records)
    assert len(events) == 0


def test_extract_efts_signals_no_ma_types():
    records = [
        {
            "company_name": "BORING INC",
            "mention_types": ["filing_mention", "disclosure"],
            "mention_filers": ["SOMEONE"],
            "latest_mention_date": "2020-01-01",
        }
    ]
    events = extract_efts_signals(records)
    assert len(events) == 0


# --- Merge ---


def test_merge_events_both_sources():
    fd = [
        {
            "company_name": "ACME",
            "event_date": "2020-03-01",
            "source": "form_d",
            "form_d_detail": {
                "filing_date": "2020-03-01",
                "total_amount_sold": 1e6,
                "combo_count": 1,
                "related_persons": [],
            },
        }
    ]
    efts = [
        {
            "company_name": "ACME",
            "event_date": "2020-01-15",
            "source": "efts",
            "efts_detail": {
                "mention_filers": ["BIG CO"],
                "mention_types": ["ma_definitive"],
                "latest_mention_date": "2020-01-15",
                "efts_tier": "medium",
            },
        }
    ]
    merged = merge_events(fd, efts)
    assert len(merged) == 1
    assert merged[0]["form_d_detail"] is not None
    assert merged[0]["efts_detail"] is not None
    assert merged[0]["event_date"] == "2020-01-15"


def test_merge_events_separate_companies():
    fd = [
        {
            "company_name": "A",
            "event_date": "2020-01-01",
            "source": "form_d",
            "form_d_detail": {
                "filing_date": "2020-01-01",
                "total_amount_sold": None,
                "combo_count": 1,
                "related_persons": [],
            },
        }
    ]
    efts = [
        {
            "company_name": "B",
            "event_date": "2021-06-01",
            "source": "efts",
            "efts_detail": {
                "mention_filers": ["X"],
                "mention_types": ["subsidiary"],
                "latest_mention_date": "2021-06-01",
                "efts_tier": "high",
            },
        }
    ]
    merged = merge_events(fd, efts)
    assert len(merged) == 2


# --- Confidence ---


def test_assign_confidence_form_d_alone_is_not_high():
    """Form D Item 10 is filed by the acquirer, so alone it is wrong-direction evidence.

    This test previously asserted `high`, which is the defect: grading an
    acquirer-side flag as strong exit evidence inflated the exit population with
    rows recording purchases by the SBIR firm.
    """
    event = {"form_d_detail": {"filing_date": "2020-01-01"}, "efts_detail": None}
    assert assign_confidence(event) == "low"


def test_form_d_with_target_side_efts_still_reaches_high():
    """A Form D flag alongside target-side evidence is not demoted."""
    event = {
        "form_d_detail": {"filing_date": "2020-01-01"},
        "efts_detail": {"mention_types": ["subsidiary"]},
    }
    assert assign_confidence(event) == "high"


def test_acquirer_side_only_predicate():
    """The predicate alone. Writer behaviour is asserted end-to-end below."""
    assert is_acquirer_side_only({"form_d_business_combination": True})


def _combo_record(company: str, tier: str) -> dict:
    return {
        "company_name": company,
        "match_confidence": {"rule_version": FORM_D_TIER_RULE_VERSION, "tier": tier},
        "offerings": [
            {
                "filing_date": "2019-03-15",
                "is_business_combination": True,
                "total_amount_sold": 1_000_000,
                "related_persons": [],
            }
        ],
    }


def test_tier_gate_drops_a_combination_record_below_high():
    """The gate is the main population change, so test it on a real combo row.

    A medium-tier record that *has* a business-combination offering is the only
    case that distinguishes the gate from the combo check. Without it, a
    regression that removed or inverted the gate would still pass.
    """
    events = extract_form_d_signals(
        [_combo_record("HIGH CO", "high"), _combo_record("MEDIUM CO", "medium")]
    )

    assert [e["company_name"] for e in events] == ["HIGH CO"]


def test_tier_gate_drops_low_as_well_as_medium():
    events = extract_form_d_signals(
        [_combo_record("HIGH CO", "high"), _combo_record("LOW CO", "low")]
    )

    assert [e["company_name"] for e in events] == ["HIGH CO"]


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_writer_routes_acquirer_side_rows_to_the_sibling_file(tmp_path, monkeypatch, capsys):
    """End-to-end: the two artifacts, and the reason value on the sibling row.

    The predicate test above would still pass if the writer sent the row to
    --output, dropped non_exit_reason, or never wrote the sibling at all.
    """
    form_d = _write_jsonl(tmp_path / "form_d.jsonl", [_combo_record("ACME INC", "high")])
    efts = _write_jsonl(
        tmp_path / "efts.jsonl",
        [
            {
                "company_name": "TARGET CO",
                "mention_types": ["subsidiary"],
                "filing_date": "2020-02-02",
            }
        ],
    )
    awards = tmp_path / "awards.csv"
    awards.write_text("Company,Agency\n", encoding="utf-8")
    out = tmp_path / "events.jsonl"
    non_exit = tmp_path / "non_exit.jsonl"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "detect",
            "--form-d",
            str(form_d),
            "--efts",
            str(efts),
            "--awards",
            str(awards),
            "--output",
            str(out),
            "--non-exit-output",
            str(non_exit),
        ],
    )
    main()
    capsys.readouterr()

    exit_rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    non_exit_rows = [json.loads(line) for line in non_exit.read_text().splitlines() if line.strip()]

    assert [r["company_name"] for r in non_exit_rows] == ["ACME INC"]
    assert non_exit_rows[0]["non_exit_reason"] == "acquirer_side"
    assert "ACME INC" not in [r["company_name"] for r in exit_rows]
    assert [r["company_name"] for r in exit_rows] == ["TARGET CO"]
    assert "non_exit_reason" not in exit_rows[0]


def test_writer_refuses_to_write_both_artifacts_to_one_path(tmp_path, monkeypatch):
    """Two buffered handles on one path truncate and overwrite each other."""
    form_d = _write_jsonl(tmp_path / "form_d.jsonl", [_combo_record("ACME INC", "high")])
    efts = _write_jsonl(tmp_path / "efts.jsonl", [])
    awards = tmp_path / "awards.csv"
    awards.write_text("Company,Agency\n", encoding="utf-8")
    same = tmp_path / "both.jsonl"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "detect",
            "--form-d",
            str(form_d),
            "--efts",
            str(efts),
            "--awards",
            str(awards),
            "--output",
            str(same),
            "--non-exit-output",
            str(same),
        ],
    )
    with pytest.raises(SystemExit, match="same file"):
        main()


def test_target_side_efts_keeps_a_row_in_the_exit_artifact():
    for signal in ("efts_subsidiary", "efts_ma_definitive", "efts_acquisition_text"):
        assert not is_acquirer_side_only({"form_d_business_combination": True, signal: True}), (
            signal
        )


def test_low_grade_efts_mentions_do_not_rescue_an_acquirer_side_row():
    """ma_proxy and ownership_active are graded Low and are not target-side.

    A comparable-table entry or a >5% stake with intent is not evidence the SBIR
    firm was acquired, so neither keeps an otherwise acquirer-side row in the
    exit artifact.
    """
    for signal in ("efts_ma_proxy", "efts_ownership_active"):
        assert is_acquirer_side_only({"form_d_business_combination": True, signal: True}), signal


def test_a_row_without_a_form_d_flag_is_never_acquirer_side_only():
    assert not is_acquirer_side_only({"efts_subsidiary": True})


def test_assign_confidence_subsidiary_is_high():
    event = {
        "form_d_detail": None,
        "efts_detail": {"mention_types": ["subsidiary", "ma_definitive"]},
    }
    assert assign_confidence(event) == "high"


def test_assign_confidence_acquisition_text_is_medium():
    event = {"form_d_detail": None, "efts_detail": {"mention_types": ["acquisition"]}}
    assert assign_confidence(event) == "medium"


def test_assign_confidence_ma_definitive_alone_is_low():
    event = {"form_d_detail": None, "efts_detail": {"mention_types": ["ma_definitive"]}}
    assert assign_confidence(event) == "low"


def test_assign_confidence_ownership_only_is_low():
    event = {"form_d_detail": None, "efts_detail": {"mention_types": ["ownership_active"]}}
    assert assign_confidence(event) == "low"


# --- Signals dict ---


def test_build_signals_dict():
    event = {
        "form_d_detail": {"filing_date": "2020-01-01"},
        "efts_detail": {"mention_types": ["subsidiary", "ma_definitive"]},
    }
    signals = build_signals_dict(event)
    assert signals["form_d_business_combination"] is True
    assert signals["efts_subsidiary"] is True
    assert signals["efts_ma_definitive"] is True
    assert signals["efts_acquisition_text"] is False
