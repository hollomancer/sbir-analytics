"""Tests for the fail-closed PatentsView source contract."""

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

from sbir_analytics.assets.agency_private_capital import patent_source_contract as contract


def _tsv(headers: list[str], rows: list[dict[str, str]]) -> bytes:
    text = io.StringIO(newline="")
    writer = csv.DictWriter(
        text,
        fieldnames=headers,
        delimiter="\t",
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return text.getvalue().encode()


def _write_zip(
    path: Path,
    *,
    member: str,
    headers: list[str],
    rows: list[dict[str, str]],
    duplicate_member: bool = False,
) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, _tsv(headers, rows))
        if duplicate_member:
            archive.writestr(member, _tsv(headers, rows))


def _default_rows() -> dict[str, list[dict[str, str]]]:
    return {
        "application": [
            {
                "application_id": "APP-1",
                "patent_id": "P1",
                "patent_application_type": "utility",
                "filing_date": "2019-01-10",
                "series_code": "16",
                "rule_47_flag": "0",
            },
            {
                "application_id": "APP-2",
                "patent_id": "P2",
                "patent_application_type": "utility",
                "filing_date": "",
                "series_code": "16",
                "rule_47_flag": "0",
            },
        ],
        "assignee": [
            {
                "patent_id": "P1",
                "assignee_sequence": "1",
                "assignee_id": "A2",
                "disambig_assignee_individual_name_first": "",
                "disambig_assignee_individual_name_last": "",
                "disambig_assignee_organization": "Beta Labs",
                "assignee_type": "2",
                "location_id": "L2",
            },
            {
                "patent_id": "P1",
                "assignee_sequence": "0",
                "assignee_id": "A1",
                "disambig_assignee_individual_name_first": "",
                "disambig_assignee_individual_name_last": "",
                "disambig_assignee_organization": "Alpha Systems",
                "assignee_type": "2",
                "location_id": "L1",
            },
            {
                "patent_id": "P2",
                "assignee_sequence": "0",
                "assignee_id": "A3",
                "disambig_assignee_individual_name_first": "Ada",
                "disambig_assignee_individual_name_last": "Lovelace",
                "disambig_assignee_organization": "",
                "assignee_type": "1",
                "location_id": "L3",
            },
        ],
        "patent": [
            {
                "patent_id": "P1",
                "patent_type": "utility",
                "patent_date": "2020-01-15",
                "patent_title": "First invention",
                "wipo_kind": "B2",
                "num_claims": "12",
                "withdrawn": "0",
                "filename": "ipg.xml",
            },
            {
                "patent_id": "P2",
                "patent_type": "utility",
                "patent_date": "2021-02-20",
                "patent_title": "Second invention",
                "wipo_kind": "B2",
                "num_claims": "4",
                "withdrawn": "0",
                "filename": "ipg.xml",
            },
        ],
    }


def _source_fixture(
    tmp_path: Path,
    *,
    rows: dict[str, list[dict[str, str]]] | None = None,
    headers: dict[str, list[str]] | None = None,
    duplicate_member_role: str | None = None,
) -> tuple[dict[str, Any], Path]:
    root = tmp_path / "source"
    root.mkdir(parents=True)
    source_rows = rows or _default_rows()
    source_headers = headers or {
        role: list(contract.REQUIRED_HEADERS[role]) for role in contract.ROLE_MEMBERS
    }
    files: list[dict[str, Any]] = []
    for role in ("patent", "application", "assignee"):
        zip_name = f"{role}.zip"
        zip_path = root / zip_name
        _write_zip(
            zip_path,
            member=contract.ROLE_MEMBERS[role],
            headers=source_headers[role],
            rows=source_rows[role],
            duplicate_member=role == duplicate_member_role,
        )
        data = zip_path.read_bytes()
        files.append(
            {
                "archive_member": contract.ROLE_MEMBERS[role],
                "headers": source_headers[role],
                "local_path": zip_name,
                "role": role,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        )
    manifest = {
        "data_through_date": "2026-03-31",
        "downloaded_at": "2026-08-09T12:00:00Z",
        "files": files,
        "license_url": "https://example.test/patentsview-license",
        "product": "PVGPATDIS",
        "release_date": "2026-06-30",
        "schema_version": 1,
        "source_url": "https://example.test/patentsview-source",
    }
    return manifest, root


def _bridge_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "assignee_id": "A1",
        "bridge_schema_version": 1,
        "candidate_status": "candidate",
        "evidence_method": "exact_normalized_name",
        "form_d_cik": "12345",
        "normalized_name_key": "ALPHA SYSTEMS",
        "normalizer_profile": "organization-key-v1",
        "source_release_id": "a" * 64,
    }
    row.update(overrides)
    return row


def test_valid_bundle_release_id_ignores_order_paths_and_download_time(tmp_path: Path) -> None:
    manifest, root = _source_fixture(tmp_path)
    first = contract.validate_patent_source_bundle(manifest, base_dir=root)

    copied = root / "copied"
    copied.mkdir()
    second_manifest = copy.deepcopy(manifest)
    second_manifest["files"].reverse()
    second_manifest["downloaded_at"] = "2099-01-01T00:00:00Z"
    second_manifest["verified"] = True
    for file_row in second_manifest["files"]:
        source = root / file_row["local_path"]
        destination = copied / file_row["local_path"]
        shutil.copyfile(source, destination)
        file_row["local_path"] = f"copied/{destination.name}"

    second = contract.validate_patent_source_bundle(second_manifest, base_dir=root)

    assert first.source_release_id == second.source_release_id
    assert set(first.files) == {"application", "assignee", "patent"}
    pinned = copy.deepcopy(manifest)
    pinned["source_release_id"] = first.source_release_id
    assert contract.validate_patent_source_bundle(pinned, base_dir=root) == first


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda manifest: manifest["files"].pop(), "exactly"),
        (
            lambda manifest: manifest["files"].__setitem__(0, copy.deepcopy(manifest["files"][2])),
            "duplicate",
        ),
        (lambda manifest: manifest["files"][0].update(role="inventor"), "unknown"),
    ],
)
def test_required_roles_fail_closed(tmp_path: Path, mutation, message: str) -> None:
    manifest, root = _source_fixture(tmp_path)
    mutation(manifest)
    with pytest.raises(contract.PatentSourceContractError, match=message):
        contract.validate_patent_source_bundle(manifest, base_dir=root)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", True, "schema_version"),
        ("product", "OTHER", "product"),
        ("release_date", "June 2026", "ISO date"),
        ("data_through_date", "2027-01-01", "must not follow"),
        ("source_url", "http://example.test/source", "HTTPS"),
        ("license_url", "", "nonblank"),
    ],
)
def test_manifest_metadata_fails_closed(
    tmp_path: Path, field: str, value: Any, message: str
) -> None:
    manifest, root = _source_fixture(tmp_path)
    manifest[field] = value
    with pytest.raises(contract.PatentSourceContractError, match=message):
        contract.validate_patent_source_bundle(manifest, base_dir=root)


@pytest.mark.parametrize("bad_path", ["../patent.zip", "/tmp/patent.zip"])
def test_local_paths_cannot_escape_base_dir(tmp_path: Path, bad_path: str) -> None:
    manifest, root = _source_fixture(tmp_path)
    manifest["files"][0]["local_path"] = bad_path
    with pytest.raises(contract.PatentSourceContractError, match="base_dir"):
        contract.validate_patent_source_bundle(manifest, base_dir=root)


@pytest.mark.parametrize("field", ["sha256", "size_bytes", "archive_member", "headers"])
def test_file_pins_are_recomputed(tmp_path: Path, field: str) -> None:
    manifest, root = _source_fixture(tmp_path)
    file_row = manifest["files"][0]
    if field == "sha256":
        file_row[field] = "0" * 64
    elif field == "size_bytes":
        file_row[field] += 1
    elif field == "archive_member":
        file_row[field] = "other.tsv"
    else:
        file_row[field] = list(reversed(file_row[field]))
    with pytest.raises(contract.PatentSourceContractError, match="(SHA|size|member|headers)"):
        contract.validate_patent_source_bundle(manifest, base_dir=root)


def test_self_asserted_verification_cannot_bypass_corruption(tmp_path: Path) -> None:
    manifest, root = _source_fixture(tmp_path)
    manifest["verified"] = True
    (root / manifest["files"][0]["local_path"]).write_bytes(b"not a zip")
    with pytest.raises(contract.PatentSourceContractError, match="(size|SHA|readable)"):
        contract.validate_patent_source_bundle(manifest, base_dir=root)


def test_materialization_rechecks_validated_archive_bytes(tmp_path: Path) -> None:
    manifest, root = _source_fixture(tmp_path)
    bundle = contract.validate_patent_source_bundle(manifest, base_dir=root)
    bundle.files["patent"].path.write_bytes(b"changed after validation")

    with pytest.raises(contract.PatentSourceContractError, match="changed after validation"):
        contract.materialize_patent_grant_events(bundle)


def test_missing_required_header_and_duplicate_member_fail(tmp_path: Path) -> None:
    headers = {role: list(contract.REQUIRED_HEADERS[role]) for role in contract.ROLE_MEMBERS}
    headers["patent"].remove("patent_date")
    manifest, root = _source_fixture(tmp_path / "missing", headers=headers)
    with pytest.raises(contract.PatentSourceContractError, match="missing headers"):
        contract.validate_patent_source_bundle(manifest, base_dir=root)

    with pytest.warns(UserWarning, match="Duplicate name"):
        manifest, root = _source_fixture(tmp_path / "duplicate", duplicate_member_role="patent")
    with pytest.raises(contract.PatentSourceContractError, match="exactly once"):
        contract.validate_patent_source_bundle(manifest, base_dir=root)


@pytest.mark.parametrize("location", ["declared", "archive"])
def test_header_pins_reject_surrounding_whitespace(tmp_path: Path, location: str) -> None:
    headers = {role: list(contract.REQUIRED_HEADERS[role]) for role in contract.ROLE_MEMBERS}
    headers["patent"][0] = " patent_id"
    manifest, root = _source_fixture(tmp_path, headers=headers)
    if location == "archive":
        manifest["files"][0]["headers"] = list(contract.REQUIRED_HEADERS["patent"])

    with pytest.raises(contract.PatentSourceContractError, match="whitespace"):
        contract.validate_patent_source_bundle(manifest, base_dir=root)


def test_native_grant_events_have_exact_schema_and_joint_assignees(tmp_path: Path) -> None:
    manifest, root = _source_fixture(tmp_path)
    bundle = contract.validate_patent_source_bundle(manifest, base_dir=root)

    events = contract.materialize_patent_grant_events(bundle)

    assert [(row["assignee_id"], row["patent_id"]) for row in events] == [
        ("A1", "P1"),
        ("A2", "P1"),
        ("A3", "P2"),
    ]
    assert all(set(row) == contract.EVENT_FIELDS for row in events)
    assert all(row["event_type"] == "patent_grant" for row in events)
    assert all(row["source_release_id"] == bundle.source_release_id for row in events)
    assert events[0]["event_date"] == "2020-01-15"
    assert events[0]["application_filing_date"] == "2019-01-10"
    assert events[2]["application_filing_date"] is None
    assert events[2]["assignee_organization"] is None
    forbidden = {"available", "arm", "denominator", "firm_key", "form_d_cik", "rate", "value"}
    assert not any(forbidden & set(row) for row in events)


def test_missing_application_join_is_nullable(tmp_path: Path) -> None:
    rows = _default_rows()
    rows["application"] = rows["application"][:1]
    manifest, root = _source_fixture(tmp_path, rows=rows)
    bundle = contract.validate_patent_source_bundle(manifest, base_dir=root)

    events = contract.materialize_patent_grant_events(bundle)

    assert (
        next(row for row in events if row["patent_id"] == "P2")["application_filing_date"] is None
    )


def test_materialization_rejects_stale_bundle_identity(tmp_path: Path) -> None:
    manifest, root = _source_fixture(tmp_path)
    bundle = contract.validate_patent_source_bundle(manifest, base_dir=root)

    with pytest.raises(contract.PatentSourceContractError, match="source_release_id is stale"):
        contract.materialize_patent_grant_events(replace(bundle, source_release_id="f" * 64))

    incomplete_files = {role: file for role, file in bundle.files.items() if role != "application"}
    with pytest.raises(contract.PatentSourceContractError, match="exactly three roles"):
        contract.materialize_patent_grant_events(replace(bundle, files=incomplete_files))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda rows: rows["patent"][0].update(patent_date="2026-04-01"),
            "data_through_date",
        ),
        (
            lambda rows: rows["application"][0].update(filing_date="2020-01-16"),
            "follows its patent grant date",
        ),
    ],
)
def test_native_reducer_rejects_temporal_inconsistency(
    tmp_path: Path, mutate, message: str
) -> None:
    rows = _default_rows()
    mutate(rows)
    manifest, root = _source_fixture(tmp_path, rows=rows)
    manifest["data_through_date"] = "2026-03-31"
    bundle = contract.validate_patent_source_bundle(manifest, base_dir=root)

    with pytest.raises(contract.PatentSourceContractError, match=message):
        contract.materialize_patent_grant_events(bundle)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda rows: rows["patent"][0].update(patent_date="not-a-date"),
            "ISO date",
        ),
        (
            lambda rows: rows["application"][0].update(filing_date="2020-99-99"),
            "ISO date",
        ),
        (
            lambda rows: rows["assignee"][0].update(patent_id="UNKNOWN"),
            "unknown patent",
        ),
        (
            lambda rows: rows["application"][0].update(patent_id="UNKNOWN"),
            "unknown patent",
        ),
        (
            lambda rows: rows["assignee"][0].update(assignee_id=""),
            "nonblank",
        ),
        (
            lambda rows: rows["patent"][0].update(patent_id=" P1 "),
            "surrounding whitespace",
        ),
    ],
)
def test_native_reducer_rejects_malformed_source_rows(tmp_path: Path, mutate, message: str) -> None:
    rows = _default_rows()
    mutate(rows)
    manifest, root = _source_fixture(tmp_path, rows=rows)
    bundle = contract.validate_patent_source_bundle(manifest, base_dir=root)
    with pytest.raises(contract.PatentSourceContractError, match=message):
        contract.materialize_patent_grant_events(bundle)


@pytest.mark.parametrize("role", ["patent", "application", "assignee"])
def test_conflicting_duplicate_rows_fail_closed(tmp_path: Path, role: str) -> None:
    rows = _default_rows()
    duplicate = dict(rows[role][0])
    if role == "patent":
        duplicate["patent_title"] = "Conflicting title"
    elif role == "application":
        duplicate["filing_date"] = "2018-01-10"
    else:
        duplicate["disambig_assignee_organization"] = "Conflicting organization"
    rows[role].append(duplicate)
    manifest, root = _source_fixture(tmp_path, rows=rows)
    bundle = contract.validate_patent_source_bundle(manifest, base_dir=root)
    with pytest.raises(contract.PatentSourceContractError, match="conflicting"):
        contract.materialize_patent_grant_events(bundle)


def test_identical_duplicate_rows_are_deduplicated(tmp_path: Path) -> None:
    rows = _default_rows()
    for role in rows:
        rows[role].append(dict(rows[role][0]))
    manifest, root = _source_fixture(tmp_path, rows=rows)
    bundle = contract.validate_patent_source_bundle(manifest, base_dir=root)

    events = contract.materialize_patent_grant_events(bundle)

    assert len(events) == 3


def test_bridge_candidates_are_minimal_sorted_and_candidate_only() -> None:
    rows = [
        _bridge_row(form_d_cik="999", assignee_id="Z9", normalized_name_key="ZETA SYSTEMS"),
        _bridge_row(),
    ]

    candidates = contract.validate_patent_bridge_candidates(rows, source_release_id="a" * 64)

    assert [row["normalized_name_key"] for row in candidates] == [
        "ALPHA SYSTEMS",
        "ZETA SYSTEMS",
    ]
    assert all(set(row) == contract.BRIDGE_FIELDS for row in candidates)
    assert all(row["candidate_status"] in {"candidate", "ambiguous"} for row in candidates)
    assert not any("accepted" in row.values() for row in candidates)


def test_bridge_collisions_must_be_ambiguous() -> None:
    rows = [
        _bridge_row(),
        _bridge_row(form_d_cik="67890", assignee_id="A2"),
    ]
    with pytest.raises(contract.PatentSourceContractError, match="must be ambiguous"):
        contract.validate_patent_bridge_candidates(rows, source_release_id="a" * 64)

    for row in rows:
        row["candidate_status"] = "ambiguous"
    candidates = contract.validate_patent_bridge_candidates(rows, source_release_id="a" * 64)
    assert len(candidates) == 2
    assert all(row["candidate_status"] == "ambiguous" for row in candidates)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"source_release_id": "b" * 64}, "source_release_id"),
        ({"form_d_cik": "00123"}, "CIK"),
        ({"assignee_id": ""}, "nonblank"),
        ({"assignee_id": " A1 "}, "surrounding whitespace"),
        ({"candidate_status": "accepted"}, "candidate or ambiguous"),
        ({"candidate_status": []}, "candidate or ambiguous"),
        ({"normalizer_profile": "other"}, "normalizer"),
        ({"normalized_name_key": "Alpha Systems, Inc."}, "canonical"),
        ({"evidence_method": "fuzzy"}, "exact normalized name"),
        ({"bridge_schema_version": True}, "integer"),
    ],
)
def test_bridge_invalid_rows_fail_closed(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(contract.PatentSourceContractError, match=message):
        contract.validate_patent_bridge_candidates(
            [_bridge_row(**overrides)], source_release_id="a" * 64
        )


@pytest.mark.parametrize("cik", ["0", "00123", "12345678901", " 12345 ", "١٢٣٤٥"])
def test_bridge_cik_requires_one_to_ten_ascii_digits(cik: str) -> None:
    with pytest.raises(contract.PatentSourceContractError, match="unpadded SEC CIK"):
        contract.validate_patent_bridge_candidates(
            [_bridge_row(form_d_cik=cik)], source_release_id="a" * 64
        )


def test_bridge_rejects_extra_study_or_confidence_fields() -> None:
    for field in ("available", "arm", "confidence", "rate"):
        row = _bridge_row()
        row[field] = True
        with pytest.raises(contract.PatentSourceContractError, match="only"):
            contract.validate_patent_bridge_candidates([row], source_release_id="a" * 64)


def test_bridge_requires_content_addressed_source_release_id() -> None:
    with pytest.raises(contract.PatentSourceContractError, match="lowercase SHA-256"):
        contract.validate_patent_bridge_candidates(
            [_bridge_row(source_release_id="not-a-digest")],
            source_release_id="not-a-digest",
        )
