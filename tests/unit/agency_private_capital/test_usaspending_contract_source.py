"""Tests for the fail-closed USAspending contract-action source contract."""

import copy
import csv
import hashlib
import io
import shutil
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from sbir_analytics.assets.agency_private_capital import usaspending_contract_source as contract


HEADERS = [*contract.REQUIRED_HEADERS, "recipient_name"]


def _row(fiscal_year: int, transaction: str, **overrides: str) -> dict[str, str]:
    action_year = fiscal_year - 1
    row = dict.fromkeys(HEADERS, "")
    row.update(
        {
            "action_date": f"{action_year}-10-01",
            "action_date_fiscal_year": str(fiscal_year),
            "action_type_code": "A",
            "award_or_idv_flag": "AWARD",
            "award_type_code": "A",
            "contract_award_unique_key": f"AWARD-{fiscal_year}",
            "contract_transaction_unique_key": transaction,
            "federal_action_obligation": "100.00",
            "idv_type_code": "",
            "modification_number": "0",
            "period_of_performance_start_date": f"{action_year}-10-01",
            "recipient_duns": "000000001",
            "recipient_name": "MUST NOT LEAK LLC",
            "recipient_uei": "ABC123456789",
        }
    )
    row.update(overrides)
    return row


def _write_archive(
    path: Path,
    members: list[tuple[str, list[dict[str, str]], list[str]]],
    *,
    duplicate_first_member: bool = False,
    force_zip64: bool = False,
) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for index, (member_name, rows, headers) in enumerate(members):
            text = io.StringIO(newline="")
            writer = csv.DictWriter(
                text,
                fieldnames=headers,
                extrasaction="ignore",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
            payload = text.getvalue().encode()
            if force_zip64 and index == 0:
                with archive.open(member_name, "w", force_zip64=True) as raw:
                    raw.write(payload)
            else:
                archive.writestr(member_name, payload)
        if duplicate_first_member:
            member_name, rows, headers = members[0]
            text = io.StringIO(newline="")
            writer = csv.DictWriter(
                text,
                fieldnames=headers,
                extrasaction="ignore",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
            archive.writestr(member_name, text.getvalue())

    with zipfile.ZipFile(path) as archive:
        infos = sorted(archive.infolist(), key=lambda item: item.filename)
    headers_by_name = {name: headers for name, _, headers in members}
    return [
        {
            "crc32": info.CRC,
            "headers": headers_by_name[info.filename],
            "member_name": info.filename,
            "size_bytes": info.file_size,
        }
        for info in infos
    ]


def _source_fixture(
    tmp_path: Path,
    *,
    fiscal_years: tuple[int, ...] = (2024, 2025),
    snapshot_date: str = "2026-08-09",
    rows_by_year: dict[int, list[dict[str, str]]] | None = None,
    headers: list[str] | None = None,
    duplicate_member_year: int | None = None,
    force_zip64_year: int | None = None,
) -> tuple[dict[str, Any], Path]:
    root = tmp_path / "source"
    root.mkdir(parents=True)
    selected_headers = headers or HEADERS
    archives: list[dict[str, Any]] = []
    for fiscal_year in fiscal_years:
        filename = f"FY{fiscal_year}_All_Contracts_Full_20260806.zip"
        path = root / filename
        rows = (
            rows_by_year[fiscal_year]
            if rows_by_year is not None
            else [_row(fiscal_year, f"TX-{fiscal_year}")]
        )
        if fiscal_year == fiscal_years[0]:
            split = max(1, len(rows) - 1)
            member_rows = [rows[:split], rows[split:]] if len(rows) > 1 else [rows]
        else:
            member_rows = [rows]
        members = [
            (f"{filename.removesuffix('.zip')}_{index}.csv", part, selected_headers)
            for index, part in enumerate(member_rows, start=1)
        ]
        pinned_members = _write_archive(
            path,
            members,
            duplicate_first_member=fiscal_year == duplicate_member_year,
            force_zip64=fiscal_year == force_zip64_year,
        )
        payload = path.read_bytes()
        archives.append(
            {
                "downloaded_at": "2026-08-09T12:00:00Z",
                "filename": filename,
                "fiscal_year": fiscal_year,
                "local_path": filename,
                "members": pinned_members,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
                "source_url": f"https://files.usaspending.gov/award_data_archive/{filename}",
                "upstream_updated_date": "2026-08-06",
            }
        )
    manifest = {
        "archives": archives,
        "downloaded_at": "2026-08-09T12:00:00Z",
        "end_fiscal_year": max(fiscal_years),
        "product": "All_Contracts_Full",
        "schema_version": 1,
        "source_snapshot_date": snapshot_date,
        "start_fiscal_year": min(fiscal_years),
    }
    return manifest, root


def _archive_row(manifest: dict[str, Any], fiscal_year: int) -> dict[str, Any]:
    return next(row for row in manifest["archives"] if row["fiscal_year"] == fiscal_year)


def test_valid_bundle_is_content_addressed_and_order_independent(tmp_path: Path) -> None:
    rows = {
        2024: [
            _row(2024, "TX-A", federal_action_obligation="100.000000000000000001"),
            _row(
                2024,
                "TX-B",
                contract_award_unique_key="AWARD-2024",
                modification_number="1",
                action_date="2024-09-30",
                federal_action_obligation="-25.00",
                recipient_uei="",
                recipient_duns="",
            ),
        ],
        2025: [
            _row(
                2025,
                "TX-C",
                award_or_idv_flag="IDV",
                award_type_code="",
                idv_type_code="B",
                federal_action_obligation="-0.00",
                recipient_uei="ABC-123456789",
                recipient_duns="000-000-001",
            )
        ],
    }
    manifest, root = _source_fixture(tmp_path, rows_by_year=rows)
    first = contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)

    copied = root / "copied"
    copied.mkdir()
    reordered = copy.deepcopy(manifest)
    reordered["archives"].reverse()
    reordered["downloaded_at"] = "2099-01-01T00:00:00Z"
    for archive_row in reordered["archives"]:
        archive_row["members"].reverse()
        source = root / archive_row["local_path"]
        destination = copied / source.name
        shutil.copyfile(source, destination)
        archive_row["local_path"] = f"copied/{destination.name}"
        archive_row["downloaded_at"] = "2099-01-01T00:00:00Z"
    second = contract.validate_usaspending_contract_source_bundle(reordered, base_dir=root)

    assert first.source_release_id == second.source_release_id
    assert set(first.archives) == {2024, 2025}
    pinned = copy.deepcopy(manifest)
    pinned["source_release_id"] = first.source_release_id
    assert contract.validate_usaspending_contract_source_bundle(pinned, base_dir=root) == first

    events = contract.materialize_usaspending_contract_action_events(first)
    assert [event["contract_transaction_unique_key"] for event in events] == [
        "TX-A",
        "TX-B",
        "TX-C",
    ]
    assert [event["contract_award_unique_key"] for event in events[:2]] == [
        "AWARD-2024",
        "AWARD-2024",
    ]
    assert [event["federal_action_obligation"] for event in events] == [
        "100.000000000000000001",
        "-25.00",
        "-0.00",
    ]
    assert events[1]["recipient_uei"] is None
    assert events[1]["recipient_duns"] is None
    assert events[2]["recipient_uei"] == "ABC123456789"
    assert events[2]["recipient_duns"] == "000000001"
    assert events[2]["award_or_idv_flag"] == "IDV"
    assert all(set(event) == contract.EVENT_FIELDS for event in events)
    assert all(event["event_type"] == "usaspending_prime_contract_action" for event in events)
    forbidden = {
        "arm",
        "available",
        "denominator",
        "event_date",
        "firm_key",
        "form_d_cik",
        "index_date",
        "is_new_award",
        "rate",
        "recipient_name",
        "transition",
        "value",
    }
    assert not any(forbidden & set(event) for event in events)


def test_release_id_changes_with_semantic_metadata_bytes_and_headers(tmp_path: Path) -> None:
    manifest, root = _source_fixture(tmp_path / "baseline")
    baseline = contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)

    updated = copy.deepcopy(manifest)
    archive_row = updated["archives"][0]
    archive_row["upstream_updated_date"] = "2026-08-07"
    archive_row["filename"] = archive_row["filename"].replace("20260806", "20260807")
    archive_row["source_url"] = archive_row["source_url"].replace("20260806", "20260807")
    changed_metadata = contract.validate_usaspending_contract_source_bundle(updated, base_dir=root)

    changed_rows = {
        2024: [_row(2024, "TX-2024", federal_action_obligation="101.00")],
        2025: [_row(2025, "TX-2025")],
    }
    changed_manifest, changed_root = _source_fixture(tmp_path / "bytes", rows_by_year=changed_rows)
    changed_bytes = contract.validate_usaspending_contract_source_bundle(
        changed_manifest, base_dir=changed_root
    )

    extended_headers = [*HEADERS, "future_source_field"]
    header_manifest, header_root = _source_fixture(tmp_path / "headers", headers=extended_headers)
    changed_headers = contract.validate_usaspending_contract_source_bundle(
        header_manifest, base_dir=header_root
    )

    assert (
        len(
            {
                baseline.source_release_id,
                changed_metadata.source_release_id,
                changed_bytes.source_release_id,
                changed_headers.source_release_id,
            }
        )
        == 4
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda manifest: manifest.update(schema_version=True), "schema_version"),
        (lambda manifest: manifest.update(product="Contracts_Full"), "product"),
        (lambda manifest: manifest.update(source_snapshot_date="August 2026"), "ISO date"),
        (lambda manifest: manifest.update(source_snapshot_date="20260809"), "canonical ISO date"),
        (lambda manifest: manifest["archives"].pop(), "exactly one"),
        (
            lambda manifest: manifest["archives"].__setitem__(
                1, copy.deepcopy(manifest["archives"][0])
            ),
            "duplicate",
        ),
        (lambda manifest: manifest.update(start_fiscal_year=2026), "must not precede"),
    ],
)
def test_manifest_shape_fails_closed(tmp_path: Path, mutate, message: str) -> None:
    manifest, root = _source_fixture(tmp_path)
    mutate(manifest)
    with pytest.raises(contract.USAspendingContractSourceError, match=message):
        contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)


def test_open_fiscal_year_fails_closed(tmp_path: Path) -> None:
    manifest, root = _source_fixture(
        tmp_path, fiscal_years=(2025, 2026), snapshot_date="2026-08-09"
    )
    with pytest.raises(contract.USAspendingContractSourceError, match="not closed"):
        contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("FY2024_DoD_Contracts_Full_20260806.zip", "all-agency"),
        ("FY2024_All_Assistance_Full_20260806.zip", "all-agency"),
        ("FY2024_All_Contracts_Delta_20260806.zip", "all-agency"),
        ("FY2025_All_Contracts_Full_20260806.zip", "fiscal year"),
        ("FY2024_All_Contracts_Full_20260807.zip", "update date"),
    ],
)
def test_archive_filename_contract_fails_closed(
    tmp_path: Path, replacement: str, message: str
) -> None:
    manifest, root = _source_fixture(tmp_path)
    _archive_row(manifest, 2024)["filename"] = replacement
    with pytest.raises(contract.USAspendingContractSourceError, match=message):
        contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)


@pytest.mark.parametrize(
    "source_url",
    [
        "http://files.usaspending.gov/award_data_archive/file.zip",
        "https://example.test/award_data_archive/file.zip",
        "https://files.usaspending.gov/other/file.zip",
        "https://user@files.usaspending.gov/award_data_archive/{filename}",
        "https://files.usaspending.gov:443/award_data_archive/{filename}",
        "https://files.usaspending.gov/award_data_archive/../award_data_archive/{filename}",
        "https://files.usaspending.gov/award_data_archive//{filename}",
    ],
)
def test_archive_source_url_must_be_official(tmp_path: Path, source_url: str) -> None:
    manifest, root = _source_fixture(tmp_path)
    archive_row = _archive_row(manifest, 2024)
    archive_row["source_url"] = source_url.format(filename=archive_row["filename"])
    with pytest.raises(contract.USAspendingContractSourceError, match="official archive URL"):
        contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)


def test_zip64_and_multiple_csv_members_are_supported(tmp_path: Path) -> None:
    rows = {
        2024: [_row(2024, "TX-A"), _row(2024, "TX-B")],
        2025: [_row(2025, "TX-C")],
    }
    manifest, root = _source_fixture(
        tmp_path,
        rows_by_year=rows,
        force_zip64_year=2024,
    )
    archive_row = _archive_row(manifest, 2024)
    with zipfile.ZipFile(root / archive_row["local_path"]) as archive:
        assert len(archive.infolist()) == 2
        assert archive.infolist()[0].extract_version >= 45

    bundle = contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)
    assert [
        event["contract_transaction_unique_key"]
        for event in contract.materialize_usaspending_contract_action_events(bundle)
    ] == ["TX-A", "TX-B", "TX-C"]


def test_upstream_update_cannot_follow_snapshot(tmp_path: Path) -> None:
    manifest, root = _source_fixture(tmp_path)
    archive_row = _archive_row(manifest, 2024)
    archive_row["upstream_updated_date"] = "2026-08-10"
    archive_row["filename"] = archive_row["filename"].replace("20260806", "20260810")
    archive_row["source_url"] = archive_row["source_url"].replace("20260806", "20260810")
    with pytest.raises(contract.USAspendingContractSourceError, match="follows"):
        contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)


@pytest.mark.parametrize("bad_path", ["../archive.zip", "/tmp/archive.zip"])
def test_local_paths_cannot_escape_base_dir(tmp_path: Path, bad_path: str) -> None:
    manifest, root = _source_fixture(tmp_path)
    _archive_row(manifest, 2024)["local_path"] = bad_path
    with pytest.raises(contract.USAspendingContractSourceError, match="base_dir"):
        contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)


@pytest.mark.parametrize("field", ["sha256", "size_bytes"])
def test_archive_file_pins_are_recomputed(tmp_path: Path, field: str) -> None:
    manifest, root = _source_fixture(tmp_path)
    archive_row = _archive_row(manifest, 2024)
    archive_row[field] = "0" * 64 if field == "sha256" else archive_row[field] + 1
    with pytest.raises(contract.USAspendingContractSourceError, match="(SHA-256|size)"):
        contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)


@pytest.mark.parametrize("field", ["member_name", "size_bytes", "crc32", "headers"])
def test_member_pins_are_recomputed(tmp_path: Path, field: str) -> None:
    manifest, root = _source_fixture(tmp_path)
    member = _archive_row(manifest, 2024)["members"][0]
    if field == "member_name":
        member[field] = "other.csv"
    elif field in {"size_bytes", "crc32"}:
        member[field] += 1
    else:
        member[field] = list(reversed(member[field]))
    with pytest.raises(contract.USAspendingContractSourceError, match="(members|size|CRC|headers)"):
        contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)


def test_required_headers_and_duplicate_members_fail_closed(tmp_path: Path) -> None:
    missing = [header for header in HEADERS if header != "action_type_code"]
    manifest, root = _source_fixture(tmp_path / "missing", headers=missing)
    with pytest.raises(contract.USAspendingContractSourceError, match="missing required headers"):
        contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)

    with pytest.warns(UserWarning, match="Duplicate name"):
        manifest, root = _source_fixture(tmp_path / "duplicate", duplicate_member_year=2024)
    with pytest.raises(contract.USAspendingContractSourceError, match="duplicate"):
        contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)


@pytest.mark.parametrize("extra_member", ["notes.txt", "folder/"])
def test_extra_non_csv_or_directory_members_fail_closed(tmp_path: Path, extra_member: str) -> None:
    manifest, root = _source_fixture(tmp_path)
    archive_row = _archive_row(manifest, 2024)
    path = root / archive_row["local_path"]
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(extra_member, "not contract data")
    payload = path.read_bytes()
    archive_row["sha256"] = hashlib.sha256(payload).hexdigest()
    archive_row["size_bytes"] = len(payload)

    with pytest.raises(contract.USAspendingContractSourceError, match="(members|flat CSV)"):
        contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)


def test_materialization_rechecks_archive_and_bundle_identity(tmp_path: Path) -> None:
    manifest, root = _source_fixture(tmp_path)
    bundle = contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)

    with pytest.raises(contract.USAspendingContractSourceError, match="stale"):
        contract.materialize_usaspending_contract_action_events(
            replace(bundle, source_release_id="f" * 64)
        )

    incomplete = dict(bundle.archives)
    incomplete.pop(2024)
    with pytest.raises(contract.USAspendingContractSourceError, match="contiguous"):
        contract.materialize_usaspending_contract_action_events(
            replace(bundle, archives=incomplete)
        )

    bundle.archives[2024].path.write_bytes(b"changed after validation")
    with pytest.raises(contract.USAspendingContractSourceError, match="changed after validation"):
        contract.materialize_usaspending_contract_action_events(bundle)


def test_duplicate_transaction_keys_fail_even_when_rows_are_identical(tmp_path: Path) -> None:
    duplicate = _row(2024, "TX-DUPLICATE")
    rows = {
        2024: [duplicate, dict(duplicate)],
        2025: [_row(2025, "TX-2025")],
    }
    manifest, root = _source_fixture(tmp_path, rows_by_year=rows)
    bundle = contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)
    with pytest.raises(contract.USAspendingContractSourceError, match="duplicate contract"):
        contract.materialize_usaspending_contract_action_events(bundle)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"contract_transaction_unique_key": ""}, "nonblank"),
        ({"contract_transaction_unique_key": " TX "}, "whitespace"),
        ({"contract_award_unique_key": ""}, "nonblank"),
        ({"action_date": "not-a-date"}, "ISO date"),
        ({"action_date": "20231001"}, "canonical ISO date"),
        ({"action_date": "2024-10-01"}, "disagrees"),
        ({"action_date_fiscal_year": "2025"}, "disagrees"),
        ({"action_date_fiscal_year": "٢٠٢٤"}, "four-digit"),
        ({"award_or_idv_flag": "CONTRACT"}, "AWARD or IDV"),
        ({"period_of_performance_start_date": "bad-date"}, "ISO date"),
        ({"period_of_performance_start_date": "20231001"}, "canonical ISO date"),
        ({"period_of_performance_start_date": " "}, "nonblank"),
        ({"action_type_code": " A "}, "surrounding whitespace"),
        ({"modification_number": " 1 "}, "surrounding whitespace"),
        ({"federal_action_obligation": "NaN"}, "canonical decimal"),
        ({"federal_action_obligation": "+1"}, "canonical decimal"),
        ({"federal_action_obligation": "01.00"}, "canonical decimal"),
        ({"federal_action_obligation": " 1.00 "}, "canonical decimal"),
        ({"federal_action_obligation": " "}, "canonical decimal"),
        ({"recipient_uei": "BAD"}, "valid UEI"),
        ({"recipient_uei": "ABCDEFGHIJK١"}, "valid UEI"),
        ({"recipient_uei": "ABC!123456789"}, "valid UEI"),
        ({"recipient_duns": "123"}, "valid DUNS"),
        ({"recipient_duns": "٠٠٠٠٠٠٠٠١"}, "valid DUNS"),
        ({"recipient_duns": "ABC000000001"}, "valid DUNS"),
    ],
)
def test_malformed_source_rows_fail_closed(
    tmp_path: Path, overrides: dict[str, str], message: str
) -> None:
    rows = {
        2024: [_row(2024, "TX-BAD", **overrides)],
        2025: [_row(2025, "TX-2025")],
    }
    manifest, root = _source_fixture(tmp_path, rows_by_year=rows)
    bundle = contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)
    with pytest.raises(contract.USAspendingContractSourceError, match=message):
        contract.materialize_usaspending_contract_action_events(bundle)


def test_nullable_optional_source_values_remain_null(tmp_path: Path) -> None:
    rows = {
        2024: [
            _row(
                2024,
                "TX-NULL",
                action_type_code="",
                award_type_code="",
                federal_action_obligation="",
                idv_type_code="",
                modification_number="",
                period_of_performance_start_date="",
                recipient_duns="",
                recipient_uei="",
            )
        ],
        2025: [_row(2025, "TX-2025")],
    }
    manifest, root = _source_fixture(tmp_path, rows_by_year=rows)
    bundle = contract.validate_usaspending_contract_source_bundle(manifest, base_dir=root)
    event = contract.materialize_usaspending_contract_action_events(bundle)[0]
    nullable = {
        "action_type_code",
        "award_type_code",
        "federal_action_obligation",
        "idv_type_code",
        "modification_number",
        "period_of_performance_start_date",
        "recipient_duns",
        "recipient_uei",
    }
    assert all(event[field] is None for field in nullable)
