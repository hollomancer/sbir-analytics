import csv
import json
import sys
from pathlib import Path

import pytest

from scripts.data.build_sbir_ma_form_d_candidates import main


AWARD_COLUMNS = (
    "Company",
    "Proposal Award Date",
    "UEI",
    "Duns",
    "Agency Tracking Number",
    "Contract",
)


def _awards(path: Path, companies: list[str]) -> Path:
    # Written with csv so a company name containing a comma survives quoting.
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(AWARD_COLUMNS)
        for index, company in enumerate(companies):
            writer.writerow(
                [company, "2020-01-15", f"UEI{index}", f"DUNS{index}", f"TRK{index}", f"C{index}"]
            )
    return path


def _index(directory: Path, filings: list[tuple[str, str, str]]) -> Path:
    """Write an EDGAR-shaped form index: (filer_name, cik, accession)."""
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        f"D           {filer:<60}{cik:<12}2020-06-30  edgar/data/{cik}/{accession}.txt\n"
        for filer, cik, accession in filings
    ]
    (directory / "2020_QTR2.idx").write_text("".join(lines), encoding="utf-8")
    return directory


def _run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    companies: list[str],
    filings: list[tuple[str, str, str]],
    *,
    widen: bool,
) -> list[dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    awards = _awards(tmp_path / "awards.csv", companies)
    index = _index(tmp_path / "idx", filings)
    out = tmp_path / ("widened.jsonl" if widen else "exact.jsonl")
    argv = [
        "build_sbir_ma_form_d_candidates.py",
        "--awards",
        str(awards),
        "--form-d-index-dir",
        str(index),
        "--output",
        str(out),
    ]
    if widen:
        argv.append("--include-legal-form-variants")
    monkeypatch.setattr(sys, "argv", argv)

    assert main() == 0
    if not out.exists():
        return []
    return [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line]


def test_legal_form_difference_is_not_a_candidate_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rows = _run(
        monkeypatch,
        tmp_path,
        ["Luna Innovations, LLC"],
        [("LUNA INNOVATIONS", "111", "a-1")],
        widen=False,
    )

    assert rows == []


def test_legal_form_difference_becomes_a_candidate_when_widened(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rows = _run(
        monkeypatch,
        tmp_path,
        ["Luna Innovations, LLC"],
        [("LUNA INNOVATIONS", "111", "a-1")],
        widen=True,
    )

    assert len(rows) == 1
    assert rows[0]["match_rationale"] == "legal_form_stripped_recipient_v1_name_key"
    assert rows[0]["name_key_profile"] == "recipient-v1"
    assert rows[0]["name_key_ambiguous"] is False
    assert rows[0]["sbir_exact_key_count"] == 1


def test_exact_rows_carry_no_widening_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The frozen study ledger has a fixed record shape; an exact row must keep
    # it so the committed cut stays byte-reproducible.
    rows = _run(monkeypatch, tmp_path, ["ACME CORP"], [("ACME CORP", "111", "a-1")], widen=True)

    assert len(rows) == 1
    assert rows[0]["match_rationale"] == "exact_form_d_join_v1_name_key"
    for field in ("name_key_ambiguous", "form_d_cik_count", "sbir_exact_key_count"):
        assert field not in rows[0]


def test_widened_output_reproduces_the_exact_ledger_when_filtered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Both runs share one index directory: form_d_index.index_path records the
    # source path, so comparing runs from different directories would differ on
    # provenance rather than on content.
    companies = ["ACME CORP", "Luna Innovations, LLC"]
    filings = [("ACME CORP", "111", "a-1"), ("LUNA INNOVATIONS", "222", "a-2")]
    awards = _awards(tmp_path / "awards.csv", companies)
    index = _index(tmp_path / "idx", filings)
    base = [
        "build_sbir_ma_form_d_candidates.py",
        "--awards",
        str(awards),
        "--form-d-index-dir",
        str(index),
    ]

    exact_out = tmp_path / "exact.jsonl"
    monkeypatch.setattr(sys, "argv", [*base, "--output", str(exact_out)])
    assert main() == 0
    widened_out = tmp_path / "widened.jsonl"
    monkeypatch.setattr(
        sys, "argv", [*base, "--output", str(widened_out), "--include-legal-form-variants"]
    )
    assert main() == 0

    exact = [json.loads(line) for line in exact_out.read_text(encoding="utf-8").splitlines()]
    widened = [json.loads(line) for line in widened_out.read_text(encoding="utf-8").splitlines()]
    kept = [r for r in widened if r["match_rationale"] == "exact_form_d_join_v1_name_key"]

    assert kept == exact
    assert len(widened) == len(exact) + 1


def test_an_exact_match_is_not_also_emitted_as_a_widened_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rows = _run(
        monkeypatch, tmp_path, ["ACME CORP INC"], [("ACME CORP INC", "111", "a-1")], widen=True
    )

    assert len(rows) == 1
    assert rows[0]["match_rationale"] == "exact_form_d_join_v1_name_key"


def test_a_key_reaching_two_ciks_is_flagged_ambiguous(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rows = _run(
        monkeypatch,
        tmp_path,
        ["Beam Technologies, Inc."],
        [("BEAM TECHNOLOGIES LLC", "111", "a-1"), ("BEAM TECHNOLOGIES", "222", "a-2")],
        widen=True,
    )

    assert len(rows) == 2
    assert all(r["name_key_ambiguous"] is True for r in rows)
    assert {r["form_d_cik_count"] for r in rows} == {2}


def test_two_sbir_spellings_collapsing_onto_one_key_are_recorded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Whether these are one firm is not decided here; the collapse is surfaced
    # for adjudication.
    rows = _run(
        monkeypatch,
        tmp_path,
        ["DATASHAPES, INC.", "DATASHAPES, LLC"],
        [("DATASHAPES", "111", "a-1")],
        widen=True,
    )

    assert len(rows) == 1
    assert rows[0]["sbir_exact_key_count"] == 2
    # form-d-join-v1 keeps punctuation, so the exact keys still carry the comma.
    assert rows[0]["sbir_exact_keys"] == ["DATASHAPES, INC.", "DATASHAPES, LLC"]
    assert rows[0]["sbir_aliases"] == ["DATASHAPES, INC.", "DATASHAPES, LLC"]
