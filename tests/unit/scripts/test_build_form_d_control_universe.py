import argparse
import csv
import importlib.util
import json
import zipfile
from collections import Counter
from pathlib import Path
from types import ModuleType

import pytest


SCRIPT = Path(__file__).parents[3] / "scripts/data/build_form_d_control_universe.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_form_d_control_universe", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


producer = _load_module()

SUBMISSION_HEADERS = [
    "ACCESSIONNUMBER",
    "FILING_DATE",
    "SIC_CODE",
    "SUBMISSIONTYPE",
    "TESTORLIVE",
]
ISSUER_HEADERS = [
    "ACCESSIONNUMBER",
    "IS_PRIMARYISSUER_FLAG",
    "CIK",
    "ENTITYNAME",
    "STREET1",
    "STREET2",
    "CITY",
    "STATEORCOUNTRY",
    "ZIPCODE",
    "ISSUERPHONENUMBER",
    "JURISDICTIONOFINC",
    "ENTITYTYPE",
    "YEAROFINC_TIMESPAN_CHOICE",
    "YEAROFINC_VALUE_ENTERED",
    "ISSUER_PREVIOUSNAME_1",
    "ISSUER_PREVIOUSNAME_2",
    "ISSUER_PREVIOUSNAME_3",
    "EDGAR_PREVIOUSNAME_1",
    "EDGAR_PREVIOUSNAME_2",
    "EDGAR_PREVIOUSNAME_3",
]
OFFERING_HEADERS = [
    "ACCESSIONNUMBER",
    "INDUSTRYGROUPTYPE",
    "ISAMENDMENT",
    "PREVIOUSACCESSIONNUMBER",
    "SALE_DATE",
    "ISEQUITYTYPE",
    "ISDEBTTYPE",
    "ISOPTIONTOACQUIRETYPE",
    "ISSECURITYTOBEACQUIREDTYPE",
    "ISPOOLEDINVESTMENTFUNDTYPE",
    "ISTENANTINCOMMONTYPE",
    "ISMINERALPROPERTYTYPE",
    "ISOTHERTYPE",
    "ISBUSINESSCOMBINATIONTRANS",
    "TOTALOFFERINGAMOUNT",
    "TOTALAMOUNTSOLD",
    "TOTALREMAINING",
]


def _tsv(headers: list[str], rows: list[dict[str, str]]) -> str:
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=headers,
        delimiter="\t",
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _write_archive(
    path: Path,
    *,
    submissions: list[dict[str, str]] | None = None,
    issuers: list[dict[str, str]] | None = None,
    offerings: list[dict[str, str]] | None = None,
    submission_headers: list[str] | None = None,
) -> None:
    submissions = submissions or [
        {
            "ACCESSIONNUMBER": "0001",
            "FILING_DATE": "31-DEC-2024",
            "SIC_CODE": "3571",
            "SUBMISSIONTYPE": "D",
            "TESTORLIVE": "LIVE",
        }
    ]
    issuers = issuers or [
        {
            "ACCESSIONNUMBER": "0001",
            "IS_PRIMARYISSUER_FLAG": "true",
            "CIK": "00000123",
            "ENTITYNAME": "Acme, Inc.",
            "STREET1": "1 Market Street",
            "STREET2": "Suite 200",
            "CITY": "San Francisco",
            "STATEORCOUNTRY": "CA",
            "ZIPCODE": "94105",
            "ISSUERPHONENUMBER": "415-555-0100",
            "JURISDICTIONOFINC": "DE",
            "ENTITYTYPE": "Corporation",
            "YEAROFINC_TIMESPAN_CHOICE": "Within Five Years",
            "YEAROFINC_VALUE_ENTERED": "2020",
        }
    ]
    offerings = offerings or [
        {
            "ACCESSIONNUMBER": "0001",
            "INDUSTRYGROUPTYPE": "Technology",
            "ISAMENDMENT": "false",
            "PREVIOUSACCESSIONNUMBER": "",
            "SALE_DATE": "2024-12-01",
            "ISEQUITYTYPE": "true",
            "ISDEBTTYPE": "false",
            "ISOPTIONTOACQUIRETYPE": "false",
            "ISSECURITYTOBEACQUIREDTYPE": "false",
            "ISPOOLEDINVESTMENTFUNDTYPE": "false",
            "ISTENANTINCOMMONTYPE": "false",
            "ISMINERALPROPERTYTYPE": "false",
            "ISOTHERTYPE": "false",
            "ISBUSINESSCOMBINATIONTRANS": "false",
            "TOTALOFFERINGAMOUNT": "1000000",
            "TOTALAMOUNTSOLD": "250000",
            "TOTALREMAINING": "750000",
        }
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "2024Q4_d/FORMDSUBMISSION.tsv",
            _tsv(submission_headers or SUBMISSION_HEADERS, submissions),
        )
        archive.writestr("2024Q4_d/ISSUERS.tsv", _tsv(ISSUER_HEADERS, issuers))
        archive.writestr("2024Q4_d/OFFERING.tsv", _tsv(OFFERING_HEADERS, offerings))


def _award_csv(path: Path, names: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Company", "Award Year"])
        writer.writeheader()
        for index, name in enumerate(names):
            writer.writerow({"Company": name, "Award Year": 1983 + index})


def test_quarter_range_and_catalog_historical_filename() -> None:
    assert producer.quarter_range("2009Q4", "2010Q2") == ["2009Q4", "2010Q1", "2010Q2"]
    html = b"""
      <a href='/files/structureddata/data/form-d-data-sets/2009q1_d_0.zip'>old</a>
      <a href='/files/datastandardsinnovation/data/form-d-data-sets/2024q4_d.zip'>new</a>
    """
    links = producer.parse_catalog_links(
        html,
        base_url="https://www.sec.gov/catalog",
        expected=["2009Q1", "2024Q4"],
    )
    assert links["2009Q1"].endswith("2009q1_d_0.zip")
    assert links["2024Q4"].endswith("2024q4_d.zip")


def test_catalog_fails_when_any_expected_quarter_is_missing() -> None:
    with pytest.raises(producer.BuildError, match="missing expected"):
        producer.parse_catalog_links(
            b"<a href='2024q4_d.zip'>Q4</a>",
            base_url="https://example.test/",
            expected=["2024Q3", "2024Q4"],
        )


def test_parse_quarter_filters_and_normalizes(tmp_path: Path) -> None:
    archive = tmp_path / "quarter.zip"
    submissions = [
        {
            "ACCESSIONNUMBER": "0001",
            "FILING_DATE": "2009-03-31 17:22:50",
            "SIC_CODE": "3571",
            "SUBMISSIONTYPE": "D",
            "TESTORLIVE": "LIVE",
        },
        {
            "ACCESSIONNUMBER": "0002",
            "FILING_DATE": "31-DEC-2024",
            "SIC_CODE": "3571",
            "SUBMISSIONTYPE": "D/A",
            "TESTORLIVE": "LIVE",
        },
        {
            "ACCESSIONNUMBER": "0003",
            "FILING_DATE": "31-DEC-2024",
            "SIC_CODE": "3571",
            "SUBMISSIONTYPE": "D",
            "TESTORLIVE": "TEST",
        },
    ]
    issuers = [
        {
            "ACCESSIONNUMBER": accession,
            "IS_PRIMARYISSUER_FLAG": "true",
            "CIK": "00000123",
            "ENTITYNAME": name,
            "ISSUER_PREVIOUSNAME_1": "Legacy Acme LLC" if accession == "0002" else "",
            "STREET1": "1 Market Street",
            "STREET2": "Suite 200",
            "CITY": "San Francisco",
            "STATEORCOUNTRY": "CA",
            "ZIPCODE": "94105",
            "ISSUERPHONENUMBER": "415-555-0100",
            "JURISDICTIONOFINC": "DE",
            "ENTITYTYPE": "Corporation",
            "YEAROFINC_TIMESPAN_CHOICE": "Within Five Years",
            "YEAROFINC_VALUE_ENTERED": "2020",
        }
        for accession, name in [("0001", "Acme, Inc."), ("0002", "Acme Corp"), ("0003", "Test")]
    ]
    offerings = [
        {
            "ACCESSIONNUMBER": accession,
            "INDUSTRYGROUPTYPE": "Technology",
            "ISAMENDMENT": "true" if accession == "0002" else "false",
            "PREVIOUSACCESSIONNUMBER": "0001" if accession == "0002" else "",
            "SALE_DATE": "2024-12-01",
            "ISEQUITYTYPE": "true",
            "ISDEBTTYPE": "true" if accession == "0002" else "false",
            "ISOPTIONTOACQUIRETYPE": "false",
            "ISSECURITYTOBEACQUIREDTYPE": "false",
            "ISPOOLEDINVESTMENTFUNDTYPE": "false",
            "ISTENANTINCOMMONTYPE": "false",
            "ISMINERALPROPERTYTYPE": "false",
            "ISOTHERTYPE": "false",
            "ISBUSINESSCOMBINATIONTRANS": "true" if accession == "0002" else "false",
            "TOTALOFFERINGAMOUNT": "1,000,000",
            "TOTALAMOUNTSOLD": "250000",
            "TOTALREMAINING": "750000",
        }
        for accession in ("0001", "0002", "0003")
    ]
    _write_archive(archive, submissions=submissions, issuers=issuers, offerings=offerings)

    rows, metadata = producer.parse_quarter(archive, quarter="2024Q4")

    assert [row["accession_number"] for row in rows] == ["0001", "0002"]
    assert rows[0]["cik"] == "123"
    assert rows[0]["filing_date"] == "2009-03-31"
    assert rows[1]["is_amendment"] is True
    assert rows[1]["is_business_combination"] is True
    assert rows[1]["security_types"] == ["debt", "equity"]
    assert rows[1]["previous_accession_number"] == "0001"
    assert rows[1]["street1"] == "1 Market Street"
    assert rows[1]["street2"] == "Suite 200"
    assert rows[1]["city"] == "San Francisco"
    assert rows[1]["issuer_phone"] == "415-555-0100"
    assert rows[1]["jurisdiction_of_incorporation"] == "DE"
    assert metadata["counters"]["test_submissions"] == 1

    issuers_out = producer.aggregate_issuers(rows)
    assert len(issuers_out) == 1
    assert issuers_out[0]["filing_count"] == 2
    assert issuers_out[0]["first_accession_number"] == "0001"
    assert "Legacy Acme LLC" in issuers_out[0]["issuer_name_aliases"]
    assert producer.aggregate_issuers(reversed(rows)) == issuers_out


def test_parse_quarter_counts_malformed_cik(tmp_path: Path) -> None:
    archive = tmp_path / "quarter.zip"
    _write_archive(
        archive,
        issuers=[
            {
                "ACCESSIONNUMBER": "0001",
                "IS_PRIMARYISSUER_FLAG": "true",
                "CIK": "bad-cik",
                "ENTITYNAME": "Acme",
                "STATEORCOUNTRY": "CA",
                "ZIPCODE": "94105",
                "ENTITYTYPE": "Corporation",
                "YEAROFINC_TIMESPAN_CHOICE": "",
                "YEAROFINC_VALUE_ENTERED": "",
            }
        ],
    )
    rows, metadata = producer.parse_quarter(archive, quarter="2024Q4")
    assert rows == []
    assert metadata["counters"]["invalid_cik_filings"] == 1


def test_optional_source_dirt_is_counted_and_preserved(tmp_path: Path) -> None:
    archive = tmp_path / "quarter.zip"
    issuers = [
        {
            "ACCESSIONNUMBER": "0001",
            "IS_PRIMARYISSUER_FLAG": "true",
            "CIK": "123",
            "ENTITYNAME": "Acme",
            "STATEORCOUNTRY": "CA",
            "ZIPCODE": "",
            "ENTITYTYPE": "Corporation",
            "YEAROFINC_TIMESPAN_CHOICE": "Exact",
            "YEAROFINC_VALUE_ENTERED": "unknown",
        }
    ]
    offerings = [
        {
            "ACCESSIONNUMBER": "0001",
            "INDUSTRYGROUPTYPE": "Technology",
            "ISAMENDMENT": "false",
            "PREVIOUSACCESSIONNUMBER": "",
            "SALE_DATE": "not-a-date",
            "ISEQUITYTYPE": "true",
            "ISDEBTTYPE": "false",
            "ISOPTIONTOACQUIRETYPE": "false",
            "ISSECURITYTOBEACQUIREDTYPE": "false",
            "ISPOOLEDINVESTMENTFUNDTYPE": "false",
            "ISTENANTINCOMMONTYPE": "false",
            "ISMINERALPROPERTYTYPE": "false",
            "ISOTHERTYPE": "false",
            "ISBUSINESSCOMBINATIONTRANS": "false",
            "TOTALOFFERINGAMOUNT": "NaN",
            "TOTALAMOUNTSOLD": "-1",
            "TOTALREMAINING": "bad",
        }
    ]
    _write_archive(archive, issuers=issuers, offerings=offerings)
    rows, metadata = producer.parse_quarter(archive, quarter="2024Q4")
    row = rows[0]
    assert row["date_of_first_sale"] is None
    assert row["date_of_first_sale_raw"] == "not-a-date"
    assert row["total_amount_sold"] is None
    assert row["total_amount_sold_raw"] == "-1"
    assert row["year_of_incorporation"] is None
    assert row["year_of_incorporation_raw"] == "unknown"
    assert metadata["counters"]["invalid_amount_values"] == 3
    assert metadata["counters"]["invalid_optional_date_values"] == 1
    assert metadata["counters"]["invalid_year_of_incorporation_values"] == 1


def test_parse_quarter_fails_on_schema_drift_and_broken_join(tmp_path: Path) -> None:
    schema_archive = tmp_path / "schema.zip"
    _write_archive(
        schema_archive,
        submission_headers=[header for header in SUBMISSION_HEADERS if header != "SIC_CODE"],
    )
    with pytest.raises(producer.BuildError, match="schema is missing: SIC_CODE"):
        producer.parse_quarter(schema_archive, quarter="2024Q4")

    join_archive = tmp_path / "join.zip"
    _write_archive(
        join_archive,
        issuers=[
            {
                "ACCESSIONNUMBER": "0001",
                "IS_PRIMARYISSUER_FLAG": "false",
                "CIK": "123",
                "ENTITYNAME": "Acme",
                "STATEORCOUNTRY": "CA",
                "ZIPCODE": "",
                "ENTITYTYPE": "Corporation",
                "YEAROFINC_TIMESPAN_CHOICE": "",
                "YEAROFINC_VALUE_ENTERED": "",
            }
        ],
    )
    with pytest.raises(producer.BuildError, match="broken accession joins"):
        producer.parse_quarter(join_archive, quarter="2024Q4")


def test_archive_validation_rejects_bad_zip_and_missing_table(tmp_path: Path) -> None:
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"not a zip")
    with pytest.raises(producer.BuildError, match="not a valid ZIP"):
        producer._validate_zip(bad_zip, quarter="2024Q4")

    missing_table = tmp_path / "missing.zip"
    with zipfile.ZipFile(missing_table, "w") as archive:
        archive.writestr("FORMDSUBMISSION.tsv", _tsv(SUBMISSION_HEADERS, []))
        archive.writestr("ISSUERS.tsv", _tsv(ISSUER_HEADERS, []))
    with pytest.raises(producer.BuildError, match="OFFERING.tsv"):
        producer._validate_zip(missing_table, quarter="2024Q4")


def test_build_exclusions_uses_all_names_and_unions_explicit_ciks(tmp_path: Path) -> None:
    awards = tmp_path / "awards.csv"
    _award_csv(awards, [" ACME ", "Acme, Inc.", "!!!", "Unmatched LLC"])
    explicit = tmp_path / "resolved.jsonl"
    explicit.write_text(
        json.dumps({"sec_cik": "0003", "offerings": [{"cik": "0004"}]}) + "\n",
        encoding="utf-8",
    )
    issuers = [
        {"cik": "1", "issuer_name_aliases": ["Acme, Inc."]},
        {"cik": "2", "issuer_name_aliases": ["ACME LLC", "Old Two"]},
        {"cik": "9", "issuer_name_aliases": ["Other"]},
    ]

    exclusions, metadata = producer.build_exclusions(
        issuers,
        awards_csv=awards,
        explicit_evidence_paths=[explicit],
    )

    assert [row["cik"] for row in exclusions] == ["1", "2", "3", "4"]
    assert metadata["exact_match"]["matched_normalized_name_count"] == 1
    assert metadata["exact_match"]["normalized_names_mapping_to_multiple_ciks"] == 1
    exact_rows = [
        row for row in exclusions if "candidate_exact_normalized_name" in row["resolution_methods"]
    ]
    assert len(exact_rows) == 2
    assert exact_rows[0]["evidence"][0]["normalizer_version"] == "organization-key-v1"


def test_build_exclusions_fails_closed_without_awards(tmp_path: Path) -> None:
    with pytest.raises(producer.BuildError, match="awards CSV is missing"):
        producer.build_exclusions([], awards_csv=tmp_path / "missing.csv")


def test_explicit_cik_evidence_rejects_invalid_json_contract(tmp_path: Path) -> None:
    invalid_json = tmp_path / "invalid.jsonl"
    invalid_json.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(producer.BuildError, match="Invalid JSON"):
        producer._explicit_cik_evidence([invalid_json])

    scalar = tmp_path / "scalar.jsonl"
    scalar.write_text("123\n", encoding="utf-8")
    with pytest.raises(producer.BuildError, match="must be a JSON object"):
        producer._explicit_cik_evidence([scalar])


def test_amount_rejects_negative_and_non_finite_values() -> None:
    counters: Counter[str] = Counter()
    assert producer._amount("-1", counters=counters) is None
    assert producer._amount("inf", counters=counters) is None
    assert producer._amount("25", counters=counters) == 25.0
    assert counters["invalid_amount_values"] == 2


def test_complete_build_is_deterministic_and_identity_only(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    output = tmp_path / "output"
    cache.mkdir()
    archive = cache / "2024q4_d.zip"
    _write_archive(archive)
    catalog = cache / "catalog.html"
    catalog.write_text(
        "<a href='https://www.sec.gov/files/structureddata/data/form-d-data-sets/2024q4_d.zip'>Q4</a>",
        encoding="utf-8",
    )
    awards = tmp_path / "awards.csv"
    _award_csv(awards, ["Acme"])
    args = argparse.Namespace(
        awards_csv=awards,
        cache_dir=cache,
        catalog_cache=catalog,
        catalog_url=producer.CATALOG_URL,
        cik_evidence_jsonl=[],
        code_version="test-commit",
        end_quarter="2024Q4",
        output_dir=output,
        refresh_catalog=False,
        sec_user_agent="unused@example.test",
        start_quarter="2024Q4",
    )

    manifest = producer.build(args)
    first_bytes = {path.name: path.read_bytes() for path in sorted(output.iterdir())}
    second = producer.build(args)
    second_bytes = {path.name: path.read_bytes() for path in sorted(output.iterdir())}

    assert first_bytes == second_bytes
    assert manifest == second
    assert manifest["complete"] is True
    assert manifest["complete_sbir_exclusion"] is False
    assert manifest["exclusion_recall"] == "unknown"
    assert manifest["identity_only"] is True
    assert manifest["covariates_ready"] is False
    assert manifest["ready_for_matching"] is False
    assert manifest["invariants"]["ready_for_matching_is_false"] is True
    assert manifest["invariants"]["control_exclusion_overlap_count"] == 0
    assert manifest["identity_evidence_contract"] == {
        "fields": [
            "issuer_name",
            "street1",
            "street2",
            "city",
            "state",
            "zip_code",
            "issuer_phone",
            "jurisdiction_of_incorporation",
            "year_of_incorporation",
        ],
        "grain": "form_d_filing_accession",
        "historical_aliases_retained": True,
        "source_table": "ISSUERS.tsv",
    }
    assert manifest["identity_field_coverage"] == {
        "cik_grain": {
            "rows": 1,
            "with_field": {
                "city": 1,
                "historical_alias_beyond_filing_name": 0,
                "issuer_name": 1,
                "issuer_phone": 1,
                "jurisdiction_of_incorporation": 1,
                "state": 1,
                "street1": 1,
                "street2": 1,
                "year_of_incorporation": 1,
                "zip_code": 1,
            },
        },
        "filing_grain": {
            "rows": 1,
            "with_field": {
                "city": 1,
                "issuer_name": 1,
                "issuer_phone": 1,
                "jurisdiction_of_incorporation": 1,
                "state": 1,
                "street1": 1,
                "street2": 1,
                "year_of_incorporation": 1,
                "zip_code": 1,
            },
        },
    }
    assert manifest["source_counts"] == {
        "excluded_broad_ciks": 1,
        "filings": 1,
        "issuer_ciks": 1,
        "provisional_control_ciks": 0,
    }
