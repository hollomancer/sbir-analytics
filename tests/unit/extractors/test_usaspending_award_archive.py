"""Tests for public USAspending Award Data Archive ingestion."""

import csv
import hashlib
import io
import json
import zipfile

import httpx
import pandas as pd
import pytest

from sbir_etl.extractors.contract_extractor import ArchiveSchemaError, SourceDataError
from sbir_etl.extractors.usaspending_award_archive import (
    AWARD_ARCHIVE_SOURCE_KIND,
    AwardArchiveContractExtractor,
    AwardArchiveFile,
    CONTRACT_ARCHIVE_COLUMNS,
    discover_full_award_archive,
    download_award_archive,
    find_latest_local_contract_archive,
)


pytestmark = pytest.mark.fast


def _archive_row(**overrides: str) -> dict[str, str]:
    row = dict.fromkeys(CONTRACT_ARCHIVE_COLUMNS, "")
    row.update(
        {
            "contract_transaction_unique_key": "TX-ARCHIVE-1",
            "contract_award_unique_key": "CONT_AWD_ARCHIVE_1",
            "award_id_piid": "ARCHIVE001",
            "modification_number": "0",
            "federal_action_obligation": "125000.00",
            "action_date": "2026-06-01",
            "period_of_performance_start_date": "2026-06-01",
            "period_of_performance_current_end_date": "2027-06-01",
            "awarding_agency_name": "Department of Defense",
            "awarding_sub_agency_name": "Department of the Air Force",
            "funding_agency_name": "Department of Defense",
            "recipient_uei": "ABC123456789",  # pragma: allowlist secret
            "recipient_duns": "123456789",
            "recipient_name": "TEST COMPANY INC",
            "cage_code": "1A2B3",
            "recipient_state_code": "VA",
            "award_or_idv_flag": "AWARD",
            "award_type_code": "A",
            "award_type": "Definitive Contract",
            "transaction_description": "Archive contract",
            "product_or_service_code": "AC12",
            "naics_code": "541715",
            "extent_competed": "FULL",
            "research": "SR2",
        }
    )
    row.update(overrides)
    return row


def _zip_bytes(members: dict[str, list[dict[str, str]]], *, columns=None) -> bytes:
    buffer = io.BytesIO()
    fieldnames = list(columns or CONTRACT_ARCHIVE_COLUMNS)
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, rows in members.items():
            text = io.StringIO(newline="")
            writer = csv.DictWriter(text, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            archive.writestr(name, text.getvalue())
    return buffer.getvalue()


def test_discover_full_archive_uses_public_listing_without_auth() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") is None
        assert json.loads(request.content) == {
            "agency": "all",
            "fiscal_year": 2026,
            "type": "contracts",
        }
        return httpx.Response(
            200,
            json={
                "monthly_files": [
                    {
                        "fiscal_year": 2026,
                        "agency_name": "All",
                        "agency_acronym": None,
                        "type": "contracts",
                        "updated_date": "2026-07-06",
                        "file_name": "FY2026_All_Contracts_Full_20260706.zip",
                        "url": (
                            "https://files.usaspending.gov/award_data_archive/"
                            "FY2026_All_Contracts_Full_20260706.zip"
                        ),
                    },
                    {
                        "fiscal_year": None,
                        "agency_name": "All",
                        "agency_acronym": None,
                        "type": "contracts",
                        "updated_date": "2026-07-06",
                        "file_name": "FY(All)_All_Contracts_Delta_20260706.zip",
                        "url": (
                            "https://files.usaspending.gov/award_data_archive/"
                            "FY(All)_All_Contracts_Delta_20260706.zip"
                        ),
                    },
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        archive = discover_full_award_archive(2026, "contracts", client=client)

    assert archive.file_name == "FY2026_All_Contracts_Full_20260706.zip"
    assert archive.fiscal_year == 2026


def test_archive_file_rejects_non_usaspending_download_host() -> None:
    with pytest.raises(SourceDataError, match="Unexpected USAspending archive URL"):
        AwardArchiveFile(
            fiscal_year=2026,
            agency_name="All",
            agency_acronym=None,
            award_type="contracts",
            updated_date="2026-07-06",
            file_name="FY2026_All_Contracts_Full_20260706.zip",
            url="https://example.test/FY2026_All_Contracts_Full_20260706.zip",
        )


def test_download_is_atomic_and_writes_verified_metadata(tmp_path) -> None:
    payload = _zip_bytes({"contracts.csv": [_archive_row()]})
    source = AwardArchiveFile(
        fiscal_year=2026,
        agency_name="All",
        agency_acronym=None,
        award_type="contracts",
        updated_date="2026-07-06",
        file_name="FY2026_All_Contracts_Full_20260706.zip",
        url=(
            "https://files.usaspending.gov/award_data_archive/"
            "FY2026_All_Contracts_Full_20260706.zip"
        ),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") is None
        return httpx.Response(200, content=payload, headers={"content-length": str(len(payload))})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path, metadata = download_award_archive(source, tmp_path, client=client)

    assert path.read_bytes() == payload
    assert not (tmp_path / f".{source.file_name}.part").exists()
    assert metadata["sha256"] == hashlib.sha256(payload).hexdigest()
    assert metadata["size_bytes"] == len(payload)
    assert path.with_suffix(".metadata.json").is_file()


def test_download_resumes_partial_file_with_http_range(tmp_path) -> None:
    payload = _zip_bytes({"contracts.csv": [_archive_row()]})
    source = AwardArchiveFile(
        fiscal_year=2026,
        agency_name="All",
        agency_acronym=None,
        award_type="contracts",
        updated_date="2026-07-06",
        file_name="FY2026_All_Contracts_Full_20260706.zip",
        url=(
            "https://files.usaspending.gov/award_data_archive/"
            "FY2026_All_Contracts_Full_20260706.zip"
        ),
    )
    offset = len(payload) // 2
    partial = tmp_path / f".{source.file_name}.part"
    partial.write_bytes(payload[:offset])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["range"] == f"bytes={offset}-"
        return httpx.Response(
            206,
            content=payload[offset:],
            headers={
                "content-length": str(len(payload) - offset),
                "content-range": f"bytes {offset}-{len(payload) - 1}/{len(payload)}",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path, metadata = download_award_archive(source, tmp_path, client=client)

    assert path.read_bytes() == payload
    assert metadata["sha256"] == hashlib.sha256(payload).hexdigest()


def test_archive_extractor_filters_all_members_and_reuses_contract_schema(
    tmp_path,
    sample_vendor_filters,
) -> None:
    unmatched = _archive_row(
        contract_transaction_unique_key="TX-NO-MATCH",
        contract_award_unique_key="CONT_AWD_NO_MATCH",
        award_id_piid="NO-MATCH",
        recipient_uei="NOPE00000001",
        recipient_duns="000000000",
        recipient_name="UNMATCHED LLC",
    )
    name_match = _archive_row(
        contract_transaction_unique_key="TX-NAME-MATCH",
        contract_award_unique_key="CONT_AWD_NAME_MATCH",
        award_id_piid="NAME001",
        recipient_uei="NOPE00000002",
        recipient_duns="000000001",
        recipient_name=" acme corporation ",
    )
    archive_path = tmp_path / "FY2026_All_Contracts_Full_20260706.zip"
    archive_path.write_bytes(
        _zip_bytes(
            {
                "FY2026_All_Contracts_Full_20260706_1.csv": [_archive_row(), unmatched],
                "FY2026_All_Contracts_Full_20260706_2.csv": [name_match],
            }
        )
    )
    output = tmp_path / "contracts.parquet"

    extractor = AwardArchiveContractExtractor(sample_vendor_filters, batch_size=1, block_size=1024)
    count = extractor.extract_from_archive(archive_path, output)
    frame = pd.read_parquet(output).sort_values("transaction_unique_id")

    assert count == 2
    assert frame["transaction_unique_id"].tolist() == ["TX-ARCHIVE-1", "TX-NAME-MATCH"]
    assert frame["generated_unique_award_id"].notna().all()
    assert frame["research"].tolist() == ["SR2", "SR2"]
    assert frame["contract_award_type"].tolist() == ["A", "A"]
    assert extractor.stats["records_scanned"] == 3
    assert extractor.stats["contracts_found"] == 3
    assert extractor.stats["vendor_matches"] == 2
    assert extractor.source_provenance["source_kind"] == AWARD_ARCHIVE_SOURCE_KIND
    assert (
        extractor.source_provenance["archive_sha256"]
        == hashlib.sha256(archive_path.read_bytes()).hexdigest()
    )


def test_archive_extractor_fails_closed_on_missing_vendor_filter(tmp_path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text('{"uei": [], "duns": [], "company_names": []}')

    with pytest.raises(ValueError, match="requires a non-empty SBIR vendor filter"):
        AwardArchiveContractExtractor(empty)


def test_archive_extractor_fails_closed_on_schema_drift(tmp_path, sample_vendor_filters) -> None:
    columns = [column for column in CONTRACT_ARCHIVE_COLUMNS if column != "research"]
    archive_path = tmp_path / "FY2026_All_Contracts_Full_20260706.zip"
    archive_path.write_bytes(_zip_bytes({"contracts.csv": [_archive_row()]}, columns=columns))

    with pytest.raises(ArchiveSchemaError, match="missing columns: research"):
        AwardArchiveContractExtractor(sample_vendor_filters).extract_from_archive(
            archive_path,
            tmp_path / "contracts.parquet",
        )


def test_find_latest_contract_archive_prefers_generation_date(tmp_path) -> None:
    older = tmp_path / "FY2025_All_Contracts_Full_20260701.zip"
    newer = tmp_path / "FY2026_All_Contracts_Full_20260706.zip"
    assistance = tmp_path / "FY2026_All_Assistance_Full_20260707.zip"
    for path in (older, newer, assistance):
        path.touch()

    assert find_latest_local_contract_archive(tmp_path) == newer
