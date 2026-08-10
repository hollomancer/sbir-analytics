import csv
import importlib.util
import json
import sys
from io import StringIO
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/data/sbir_ma_signal_counts_by_fy.py"
SPEC = importlib.util.spec_from_file_location("sbir_ma_signal_counts_by_fy", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text(
        "".join(f"{json.dumps(record, sort_keys=True)}\n" for record in records),
        encoding="utf-8",
    )
    return path


def _dataset(tmp_path: Path, records: list[dict]):
    return MODULE.load_signal_dataset(_write_jsonl(tmp_path / "events.jsonl", records))


def test_federal_fy_boundary_and_tier_subtotals(tmp_path):
    dataset = _dataset(
        tmp_path,
        [
            {"company_name": "Sep Co", "event_date": "2023-09-30", "confidence": "high"},
            {"company_name": "Oct Co", "event_date": "2023-10-01", "confidence": "medium"},
            {"company_name": "Low Co", "event_date": "2023-10-01", "confidence": "low"},
        ],
    )

    result = MODULE.build_counts(dataset, 2023, 2024)

    assert result.rows == (
        {
            "fiscal_year": 2023,
            "high_signal_name_keys": 1,
            "medium_signal_name_keys": 0,
            "high_medium_signal_name_keys": 1,
            "low_sensitivity_signal_name_keys": 0,
            "total_signal_name_keys": 1,
        },
        {
            "fiscal_year": 2024,
            "high_signal_name_keys": 0,
            "medium_signal_name_keys": 1,
            "high_medium_signal_name_keys": 1,
            "low_sensitivity_signal_name_keys": 1,
            "total_signal_name_keys": 2,
        },
    )
    assert result.in_window_keys == 3


def test_missing_invalid_and_out_of_window_dates_are_separate(tmp_path):
    dataset = _dataset(
        tmp_path,
        [
            {"company_name": "Missing", "confidence": "high"},
            {"company_name": "Null", "event_date": None, "confidence": "medium"},
            {"company_name": "Malformed", "event_date": "2023-02-30", "confidence": "low"},
            {"company_name": "Not ISO", "event_date": "2023-2-03", "confidence": "high"},
            {"company_name": "Old", "event_date": "2013-12-01", "confidence": "medium"},
        ],
    )

    result = MODULE.build_counts(dataset, 2015, 2024)

    assert result.missing_date_keys == 2
    assert result.invalid_date_keys == 2
    assert result.valid_out_of_window_keys == 1
    assert result.in_window_keys == 0
    assert (
        result.missing_date_keys
        + result.invalid_date_keys
        + result.valid_out_of_window_keys
        + result.in_window_keys
        == len(dataset.records)
    )


def test_case_and_edge_whitespace_duplicates_collapse(tmp_path):
    dataset = _dataset(
        tmp_path,
        [
            {"company_name": "  Example Corp ", "event_date": "2022-01-02", "confidence": "high"},
            {"company_name": "example corp", "event_date": "2022-01-02", "confidence": "high"},
        ],
    )

    assert dataset.input_rows == 2
    assert len(dataset.records) == 1
    assert dataset.duplicate_rows == 1
    assert dataset.records[0].company_key == "example corp"


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_date", "2022-01-03"),
        ("confidence", "medium"),
    ],
)
def test_conflicting_duplicate_date_or_tier_fails(tmp_path, field, value):
    records = [
        {"company_name": "Example Corp", "event_date": "2022-01-02", "confidence": "high"},
        {"company_name": " example corp ", "event_date": "2022-01-02", "confidence": "high"},
    ]
    records[1][field] = value
    source = _write_jsonl(tmp_path / "events.jsonl", records)

    with pytest.raises(MODULE.InputValidationError, match="conflicting duplicate"):
        MODULE.load_signal_dataset(source)


@pytest.mark.parametrize(
    "content,error",
    [
        ('{"company_name": "A", "confidence": "HIGH"}\n', "confidence must be exactly"),
        ('{"company_name": "A", "confidence": "high"\n', "invalid JSON"),
        ('{"company_name": "A", "company_name": "B", "confidence": "high"}\n', "duplicate JSON"),
        ('{"company_name": "A", "confidence": "high"}\n\n', "blank JSONL"),
    ],
)
def test_strict_jsonl_validation(tmp_path, content, error):
    source = tmp_path / "events.jsonl"
    source.write_text(content, encoding="utf-8")

    with pytest.raises(MODULE.InputValidationError, match=error):
        MODULE.load_signal_dataset(source)


def test_empty_input_fails_before_all_zero_report_can_be_built(tmp_path):
    source = tmp_path / "events.jsonl"
    source.write_bytes(b"")

    with pytest.raises(MODULE.InputValidationError, match="zero JSONL records"):
        MODULE.load_signal_dataset(source)


def test_per_tier_and_date_status_reconciliation(tmp_path):
    dataset = _dataset(
        tmp_path,
        [
            {"company_name": "H", "event_date": "2021-06-01", "confidence": "high"},
            {"company_name": "M", "event_date": "2021-06-01", "confidence": "medium"},
            {"company_name": "L", "event_date": "2021-06-01", "confidence": "low"},
            {"company_name": "No date", "confidence": "low"},
        ],
    )

    result = MODULE.build_counts(dataset, 2021, 2021)
    row = result.rows[0]

    assert row["high_medium_signal_name_keys"] == (
        row["high_signal_name_keys"] + row["medium_signal_name_keys"]
    )
    assert row["total_signal_name_keys"] == (
        row["high_medium_signal_name_keys"] + row["low_sensitivity_signal_name_keys"]
    )
    assert result.distinct_tier_counts == {"high": 1, "medium": 1, "low": 2}
    assert sum(result.distinct_tier_counts.values()) == len(dataset.records)
    assert row["total_signal_name_keys"] + result.missing_date_keys == len(dataset.records)
    for tier in MODULE.CONFIDENCE_TIERS:
        assert sum(result.date_status_by_tier[tier].values()) == result.distinct_tier_counts[tier]


def test_outputs_are_byte_identical_and_include_fingerprint(tmp_path):
    source = _write_jsonl(
        tmp_path / "events.jsonl",
        [
            {"company_name": "B", "event_date": "2020-10-01", "confidence": "medium"},
            {"company_name": "A", "event_date": "2020-09-30", "confidence": "high"},
        ],
    )
    first_csv = tmp_path / "first" / "counts.csv"
    first_md = tmp_path / "first" / "counts.md"
    second_csv = tmp_path / "second" / "counts.csv"
    second_md = tmp_path / "second" / "counts.md"

    assert (
        MODULE.main(
            [
                "--input",
                str(source),
                "--csv-output",
                str(first_csv),
                "--markdown-output",
                str(first_md),
            ]
        )
        == 0
    )
    assert (
        MODULE.main(
            [
                "--input",
                str(source),
                "--csv-output",
                str(second_csv),
                "--markdown-output",
                str(second_md),
            ]
        )
        == 0
    )

    assert first_csv.read_bytes() == second_csv.read_bytes()
    assert first_md.read_bytes() == second_md.read_bytes()
    dataset = MODULE.load_signal_dataset(source)
    assert dataset.source_sha256.encode() in first_md.read_bytes()
    assert f"- Bytes: {dataset.source_bytes:,}" in first_md.read_text(encoding="utf-8")


def test_missing_input_returns_nonzero_without_writing_outputs(tmp_path, capsys):
    csv_output = tmp_path / "reports" / "counts.csv"
    markdown_output = tmp_path / "reports" / "counts.md"

    return_code = MODULE.main(
        [
            "--input",
            str(tmp_path / "absent.jsonl"),
            "--csv-output",
            str(csv_output),
            "--markdown-output",
            str(markdown_output),
        ]
    )

    assert return_code != 0
    assert not csv_output.exists()
    assert not markdown_output.exists()
    assert "input does not exist" in capsys.readouterr().err


@pytest.mark.parametrize("alias_input", [False, True])
def test_report_paths_must_not_alias_each_other_or_input(tmp_path, capsys, alias_input):
    source = _write_jsonl(
        tmp_path / "events.jsonl",
        [{"company_name": "A", "event_date": "2020-01-01", "confidence": "high"}],
    )
    original_source = source.read_bytes()
    csv_output = source if alias_input else tmp_path / "same-output"
    markdown_output = tmp_path / "other-output" if alias_input else csv_output

    return_code = MODULE.main(
        [
            "--input",
            str(source),
            "--csv-output",
            str(csv_output),
            "--markdown-output",
            str(markdown_output),
        ]
    )

    assert return_code != 0
    assert source.read_bytes() == original_source
    assert "paths must be distinct" in capsys.readouterr().err


def test_second_stage_failure_preserves_existing_report_pair(tmp_path, capsys, monkeypatch):
    source = _write_jsonl(
        tmp_path / "events.jsonl",
        [{"company_name": "A", "event_date": "2020-01-01", "confidence": "high"}],
    )
    csv_output = tmp_path / "counts.csv"
    markdown_output = tmp_path / "counts.md"
    csv_output.write_text("old csv\n", encoding="utf-8")
    markdown_output.write_text("old markdown\n", encoding="utf-8")
    original_stage_text = MODULE._stage_text
    calls = 0

    def fail_second_stage(destination, content):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated second-stage failure")
        return original_stage_text(destination, content)

    monkeypatch.setattr(MODULE, "_stage_text", fail_second_stage)
    return_code = MODULE.main(
        [
            "--input",
            str(source),
            "--csv-output",
            str(csv_output),
            "--markdown-output",
            str(markdown_output),
        ]
    )

    assert return_code != 0
    assert csv_output.read_text(encoding="utf-8") == "old csv\n"
    assert markdown_output.read_text(encoding="utf-8") == "old markdown\n"
    assert list(tmp_path.glob("*.tmp")) == []
    assert "simulated second-stage failure" in capsys.readouterr().err


def test_second_publish_failure_rolls_back_existing_report_pair(tmp_path, capsys, monkeypatch):
    source = _write_jsonl(
        tmp_path / "events.jsonl",
        [{"company_name": "A", "event_date": "2020-01-01", "confidence": "high"}],
    )
    csv_output = tmp_path / "counts.csv"
    markdown_output = tmp_path / "counts.md"
    csv_output.write_text("old csv\n", encoding="utf-8")
    markdown_output.write_text("old markdown\n", encoding="utf-8")
    original_replace = MODULE.os.replace
    failed = False

    def fail_markdown_publish(source_path, destination):
        nonlocal failed
        source_path = Path(source_path)
        destination = Path(destination)
        if not failed and source_path.suffix == ".tmp" and destination == markdown_output:
            failed = True
            raise OSError("simulated second-publish failure")
        return original_replace(source_path, destination)

    monkeypatch.setattr(MODULE.os, "replace", fail_markdown_publish)
    return_code = MODULE.main(
        [
            "--input",
            str(source),
            "--csv-output",
            str(csv_output),
            "--markdown-output",
            str(markdown_output),
        ]
    )

    assert return_code != 0
    assert csv_output.read_text(encoding="utf-8") == "old csv\n"
    assert markdown_output.read_text(encoding="utf-8") == "old markdown\n"
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob("*.backup")) == []
    assert "simulated second-publish failure" in capsys.readouterr().err


def test_csv_contract_and_markdown_avoid_rate_or_incidence_claims(tmp_path):
    dataset = _dataset(
        tmp_path,
        [{"company_name": "A", "event_date": "2020-01-01", "confidence": "high"}],
    )
    result = MODULE.build_counts(dataset, 2020, 2020)

    csv_text = MODULE.render_csv(result)
    fields = next(csv.reader(StringIO(csv_text)))
    markdown = MODULE.render_markdown(dataset, result, 2020, 2020).lower()

    assert fields == list(MODULE.CSV_COLUMNS)
    assert not any(
        forbidden in field for field in fields for forbidden in ("rate", "exit", "control")
    )
    assert "match rate" not in markdown
    assert "wilson" not in markdown
    assert "item 2.01" not in markdown
    assert " rose " not in markdown
    assert " fell " not in markdown
    assert "not verified firms, deals, acquisitions, or exits" in markdown
    assert "signal-observation date, not a transaction or close date" in markdown
    assert "no award denominator is used" in markdown
