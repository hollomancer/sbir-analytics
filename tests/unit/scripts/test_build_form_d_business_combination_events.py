"""Focused tests for the Form D filing-proxy event producer."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


SCRIPT = Path(__file__).parents[3] / "scripts/data/build_form_d_business_combination_events.py"
REPORT = (
    Path(__file__).parents[3]
    / "docs/research/agency-private-capital-form-d-business-combination-proxy.md"
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_form_d_business_combination_events", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


producer = _load_module()


def _jsonl_bytes(rows: list[dict[str, object]]) -> bytes:
    return b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode(
            "utf-8"
        )
        for row in rows
    )


def _filing(
    accession: str,
    filing_date: str,
    source_quarter: str,
    *,
    event: bool,
    amendment: bool = False,
    previous_accession: str | None = None,
) -> dict[str, object]:
    return {
        "accession_number": accession,
        "filing_date": filing_date,
        "is_amendment": amendment,
        "is_business_combination": event,
        "previous_accession_number": previous_accession,
        "source_quarter": source_quarter,
        "submission_type": "D/A" if amendment else "D",
    }


def _issuer(cik: str, filings: list[dict[str, object]]) -> dict[str, object]:
    canonical_filings = [{**filing, "cik": cik} for filing in filings]
    return {
        "cik": cik,
        "filing_count": len(canonical_filings),
        "filings": canonical_filings,
        "firm_key": f"form_d_cik:{cik}",
        "issuer_name": f"Issuer {cik}",
    }


def _write_fixture(
    tmp_path: Path,
    *,
    rows: list[dict[str, object]] | None = None,
) -> tuple[Path, Path, dict[str, object]]:
    if rows is None:
        rows = [
            _issuer(
                "1",
                [
                    _filing("ACC-1", "2019-01-01", "2019Q1", event=True),
                    _filing(
                        "ACC-2",
                        "2020-02-02",
                        "2020Q1",
                        event=True,
                        amendment=True,
                        previous_accession="ACC-1",
                    ),
                ],
            ),
            _issuer("2", [_filing("ACC-3", "2024-12-31", "2024Q4", event=False)]),
        ]
    universe = tmp_path / "issuer-universe.jsonl"
    universe_data = _jsonl_bytes(rows)
    universe.write_bytes(universe_data)
    quarters = producer._expected_quarters()
    quarter_metadata = {
        quarter: {
            "counters": {
                "emitted_business_combination_filings": 0,
                "emitted_filings": 0,
                "invalid_business_combination_flags": 0,
                "omitted_business_combination_filings": 0,
                "selected_business_combination_filings": 0,
                "selected_non_business_combination_filings": 0,
                "selected_submissions": 0,
            },
            "headers": {"OFFERING.tsv": ["ISBUSINESSCOMBINATIONTRANS"]},
        }
        for quarter in quarters
    }
    for issuer in rows:
        for filing in issuer["filings"]:
            counters = quarter_metadata[filing["source_quarter"]]["counters"]
            counters["selected_submissions"] += 1
            counters["emitted_filings"] += 1
            if filing["is_business_combination"]:
                counters["selected_business_combination_filings"] += 1
                counters["emitted_business_combination_filings"] += 1
            else:
                counters["selected_non_business_combination_filings"] += 1
    manifest: dict[str, object] = {
        "complete": True,
        "inputs": {"quarters": quarter_metadata},
        "invariants": {"broad_ciks_unique": True},
        "outputs": {
            "broad_issuer_universe": {
                "path": universe.name,
                "row_count": len(rows),
                "sha256": hashlib.sha256(universe_data).hexdigest(),
                "size_bytes": len(universe_data),
            }
        },
        "parameters": {
            "end_quarter": "2024Q4",
            "quarter_count": 64,
            "quarters": quarters,
            "start_quarter": "2009Q1",
        },
        "source_counts": {
            "filings": sum(len(issuer["filings"]) for issuer in rows),
            "issuer_ciks": len(rows),
        },
    }
    manifest_path = tmp_path / "source-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path, universe, manifest


def _args(manifest: Path, universe: Path, output: Path) -> argparse.Namespace:
    return argparse.Namespace(
        code_version="test-commit",
        issuer_universe=universe,
        output_dir=output,
        source_manifest=manifest,
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_build_streams_deterministic_events_coverage_and_manifest(tmp_path: Path) -> None:
    source_manifest, universe, _ = _write_fixture(tmp_path)
    output = tmp_path / "output"
    args = _args(source_manifest, universe, output)

    manifest = producer.build(args)
    first_bytes = {path.name: path.read_bytes() for path in sorted(output.iterdir())}
    second_manifest = producer.build(args)
    second_bytes = {path.name: path.read_bytes() for path in sorted(output.iterdir())}

    assert manifest == second_manifest
    assert first_bytes == second_bytes
    assert manifest["complete"] is True
    assert manifest["event_type"] == "form_d_business_combination_filing_proxy"
    assert manifest["counters"] == {
        "amendment_event_rows": 1,
        "coverage_rows": 2,
        "event_rows": 2,
        "filing_rows": 3,
        "firms_with_event": 1,
        "firms_without_event": 1,
        "issuer_rows": 2,
    }
    assert manifest["event_counts_by_source_quarter"] == {"2019Q1": 1, "2020Q1": 1}
    assert manifest["filing_counts_by_source_quarter"] == {
        "2019Q1": 1,
        "2020Q1": 1,
        "2024Q4": 1,
    }
    assert manifest["invariants"] == {
        "accessions_unique": True,
        "content_addressed_outputs": True,
        "coverage_equals_verified_issuer_rows": True,
        "event_counts_reconcile_by_source_quarter": True,
        "event_ids_unique": True,
        "filing_counts_reconcile_by_source_quarter": True,
        "filing_rows_equal_source_manifest": True,
        "flagged_source_filings_omitted": 0,
        "flagged_source_filings_reconciled": True,
        "source_input_hash_rows_bytes_verified": True,
        "source_quarters_complete": True,
    }

    events_path = output / manifest["outputs"]["events"]["path"]
    coverage_path = output / manifest["outputs"]["coverage"]["path"]
    events = _read_jsonl(events_path)
    coverage = _read_jsonl(coverage_path)

    assert [event["accession_number"] for event in events] == ["ACC-1", "ACC-2"]
    assert events[0]["event_type"] == "form_d_business_combination_filing_proxy"
    assert events[0]["event_date"] == events[0]["filing_date"] == "2019-01-01"
    assert events[0]["date_basis"] == "filing_date"
    assert events[0]["evidence_kind"] == "proxy"
    assert events[1]["is_amendment"] is True
    assert events[1]["previous_accession_number"] == "ACC-1"
    assert events[1]["source_quarter"] == "2020Q1"
    assert all(event["firm_key"] == "form_d_cik:1" for event in events)
    assert all(event["source_snapshot_id"] for event in events)

    assert [row["firm_key"] for row in coverage] == ["form_d_cik:1", "form_d_cik:2"]
    assert coverage[0]["metric"] == "form_d_business_combination_filing_proxy"
    assert coverage[0]["coverage_start_date"] == "2009-01-01"
    assert coverage[0]["coverage_end_date"] == "2024-12-31"
    assert coverage[0]["source_snapshot_date"] == "2024-12-31"
    assert coverage[0]["source_complete"] is True
    assert coverage[0]["source"] == producer.SOURCE
    assert coverage[0]["source_snapshot_id"] == events[0]["source_snapshot_id"]

    for output_name in ("events", "coverage"):
        product = manifest["outputs"][output_name]
        path = output / product["path"]
        assert product["sha256"] in product["path"]
        assert product["row_count"] == len(_read_jsonl(path))
        assert product["size_bytes"] == path.stat().st_size
        assert product["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_missing_required_quarter_fails_before_outputs_are_emitted(tmp_path: Path) -> None:
    source_manifest, universe, manifest = _write_fixture(tmp_path)
    del manifest["inputs"]["quarters"]["2017Q3"]
    source_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "output"

    with pytest.raises(producer.BuildError, match="missing required quarter.*2017Q3"):
        producer.build(_args(source_manifest, universe, output))

    assert not output.exists()


def test_missing_business_combination_header_fails_source_contract(tmp_path: Path) -> None:
    source_manifest, universe, manifest = _write_fixture(tmp_path)
    manifest["inputs"]["quarters"]["2017Q3"]["headers"]["OFFERING.tsv"] = ["ISAMENDMENT"]
    source_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(producer.BuildError, match="2017Q3.*ISBUSINESSCOMBINATIONTRANS"):
        producer.build(_args(source_manifest, universe, tmp_path / "output"))


def test_omitted_business_combination_filing_fails_source_contract(tmp_path: Path) -> None:
    source_manifest, universe, manifest = _write_fixture(tmp_path)
    counters = manifest["inputs"]["quarters"]["2017Q3"]["counters"]
    counters["selected_business_combination_filings"] = 1
    counters["omitted_business_combination_filings"] = 1
    counters["selected_submissions"] = 1
    source_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(producer.BuildError, match="2017Q3 omitted 1"):
        producer.build(_args(source_manifest, universe, tmp_path / "output"))


def test_missing_business_combination_audit_counters_fail_source_contract(
    tmp_path: Path,
) -> None:
    source_manifest, universe, manifest = _write_fixture(tmp_path)
    del manifest["inputs"]["quarters"]["2017Q3"]["counters"]["omitted_business_combination_filings"]
    source_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(producer.BuildError, match="2017Q3 omitted_business.*non-negative"):
        producer.build(_args(source_manifest, universe, tmp_path / "output"))


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("sha256", "SHA-256"),
        ("row_count", "row count"),
        ("size_bytes", "byte count"),
    ],
)
def test_input_universe_hash_rows_and_bytes_are_verified(
    tmp_path: Path, field: str, message: str
) -> None:
    source_manifest, universe, original = _write_fixture(tmp_path)
    manifest = copy.deepcopy(original)
    product = manifest["outputs"]["broad_issuer_universe"]
    if field == "sha256":
        product[field] = "0" * 64
    else:
        product[field] += 1
    if field == "row_count":
        manifest["source_counts"]["issuer_ciks"] += 1
    source_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    sentinels = {
        output / f"{producer.EVENT_TYPE}.events.jsonl": b"prior-events\n",
        output / f"{producer.EVENT_TYPE}.coverage.jsonl": b"prior-coverage\n",
        output / f"{producer.EVENT_TYPE}.manifest.json": b"prior-manifest\n",
    }
    for path, data in sentinels.items():
        path.write_bytes(data)

    with pytest.raises(producer.BuildError, match=message):
        producer.build(_args(source_manifest, universe, output))

    assert {path: path.read_bytes() for path in sentinels} == sentinels


def test_invalid_or_noncanonical_cik_firm_key_fails_closed(tmp_path: Path) -> None:
    row = _issuer("1", [_filing("ACC-1", "2020-01-01", "2020Q1", event=False)])
    row["firm_key"] = "name:issuer-one"
    source_manifest, universe, _ = _write_fixture(tmp_path, rows=[row])
    output = tmp_path / "output"

    with pytest.raises(producer.BuildError, match="exact firm_key"):
        producer.build(_args(source_manifest, universe, output))

    assert not list(output.glob("*.jsonl"))


def test_incomplete_source_manifest_is_rejected(tmp_path: Path) -> None:
    source_manifest, universe, manifest = _write_fixture(tmp_path)
    manifest["complete"] = False
    source_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(producer.BuildError, match="complete=true"):
        producer.build(_args(source_manifest, universe, tmp_path / "output"))


def test_empty_complete_source_manifest_is_rejected(tmp_path: Path) -> None:
    source_manifest, universe, _ = _write_fixture(tmp_path, rows=[])

    with pytest.raises(producer.BuildError, match="positive integer"):
        producer.build(_args(source_manifest, universe, tmp_path / "output"))


def test_nested_filing_count_and_cik_must_match_parent(tmp_path: Path) -> None:
    row = _issuer("1", [_filing("ACC-1", "2020-01-01", "2020Q1", event=False)])
    row["filing_count"] = 2
    source_manifest, universe, _ = _write_fixture(tmp_path, rows=[row])
    with pytest.raises(producer.BuildError, match="filing_count does not match"):
        producer.build(_args(source_manifest, universe, tmp_path / "count-output"))

    row = _issuer("1", [_filing("ACC-1", "2020-01-01", "2020Q1", event=False)])
    row["filings"][0]["cik"] = "2"
    source_manifest, universe, _ = _write_fixture(tmp_path, rows=[row])
    with pytest.raises(producer.BuildError, match="filing CIK does not match"):
        producer.build(_args(source_manifest, universe, tmp_path / "cik-output"))


def test_source_quarter_must_match_filing_date(tmp_path: Path) -> None:
    row = _issuer("1", [_filing("ACC-1", "2020-01-01", "2020Q2", event=True)])
    source_manifest, universe, _ = _write_fixture(tmp_path, rows=[row])

    with pytest.raises(producer.BuildError, match="source_quarter does not match"):
        producer.build(_args(source_manifest, universe, tmp_path / "output"))


def test_source_manifest_counts_must_reconcile_for_each_quarter(tmp_path: Path) -> None:
    source_manifest, universe, manifest = _write_fixture(tmp_path)
    quarters = manifest["inputs"]["quarters"]
    quarter_2019_q1 = quarters["2019Q1"]["counters"]
    quarter_2019_q2 = quarters["2019Q2"]["counters"]
    for counter in (
        "emitted_business_combination_filings",
        "emitted_filings",
        "selected_business_combination_filings",
        "selected_submissions",
    ):
        quarter_2019_q1[counter] -= 1
        quarter_2019_q2[counter] += 1
    source_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(
        producer.BuildError, match="filing counts do not reconcile by source quarter"
    ):
        producer.build(_args(source_manifest, universe, tmp_path / "output"))


def test_accessions_are_unique_across_all_issuer_records(tmp_path: Path) -> None:
    rows = [
        _issuer("1", [_filing("DUPLICATE", "2020-01-01", "2020Q1", event=True)]),
        _issuer("2", [_filing("DUPLICATE", "2020-01-02", "2020Q1", event=True)]),
    ]
    source_manifest, universe, _ = _write_fixture(tmp_path, rows=rows)

    with pytest.raises(producer.BuildError, match="repeats accession DUPLICATE"):
        producer.build(_args(source_manifest, universe, tmp_path / "output"))


def test_manifest_staging_failure_does_not_publish_unmanifested_products(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_manifest, universe, _ = _write_fixture(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    sentinels = {
        output / f"{producer.EVENT_TYPE}.events.jsonl": b"prior-events\n",
        output / f"{producer.EVENT_TYPE}.coverage.jsonl": b"prior-coverage\n",
        output / f"{producer.EVENT_TYPE}.manifest.json": b"prior-manifest\n",
    }
    for path, data in sentinels.items():
        path.write_bytes(data)

    original = producer.tempfile.NamedTemporaryFile
    calls = 0

    def fail_manifest_stage(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("manifest staging failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(producer.tempfile, "NamedTemporaryFile", fail_manifest_stage)
    with pytest.raises(OSError, match="manifest staging failed"):
        producer.build(_args(source_manifest, universe, output))

    assert {path: path.read_bytes() for path in sentinels} == sentinels


def test_product_publish_failure_preserves_prior_manifest_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prior_fixture = tmp_path / "prior"
    prior_fixture.mkdir()
    source_manifest, universe, _ = _write_fixture(prior_fixture)
    output = tmp_path / "output"
    prior = producer.build(_args(source_manifest, universe, output))
    prior_manifest_path = output / f"{producer.EVENT_TYPE}.manifest.json"
    prior_manifest_bytes = prior_manifest_path.read_bytes()
    prior_products = {
        output / product["path"]: (product["sha256"], (output / product["path"]).read_bytes())
        for product in prior["outputs"].values()
    }

    next_fixture = tmp_path / "next"
    next_fixture.mkdir()
    next_rows = [_issuer("1", [_filing("ACC-NEW", "2021-03-03", "2021Q1", event=True)])]
    source_manifest, universe, _ = _write_fixture(next_fixture, rows=next_rows)

    original_replace = producer.os.replace
    replacements = 0

    def fail_second_publish(source: object, destination: object) -> None:
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("coverage publish failed")
        original_replace(source, destination)

    monkeypatch.setattr(producer.os, "replace", fail_second_publish)
    with pytest.raises(OSError, match="coverage publish failed"):
        producer.build(_args(source_manifest, universe, output))

    assert prior_manifest_path.read_bytes() == prior_manifest_bytes
    for path, (expected_sha, expected_bytes) in prior_products.items():
        assert path.read_bytes() == expected_bytes
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha


def test_report_keeps_exact_proxy_name_and_rejects_ma_exit_interpretation() -> None:
    report = REPORT.read_text(encoding="utf-8")

    assert "`form_d_business_combination_filing_proxy`" in report
    assert "not a verified acquisition, merger, or exit outcome" in report
    assert "be labeled as a verified acquisition or M&A exit" in report
