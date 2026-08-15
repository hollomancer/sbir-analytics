import csv
import hashlib
import importlib.util
import io
import json
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

from sbir_analytics.assets.agency_private_capital import usaspending_contract_source as contract


SCRIPT = Path(__file__).parents[3] / "scripts/data/build_usaspending_contract_source_bundle.py"
TRACKED_MANIFEST = (
    Path(__file__).parents[3] / "docs/research/usaspending-contract-source-fy2025.manifest.json"
)
TRACKED_REPORT = Path(__file__).parents[3] / "docs/research/usaspending-contract-source-fy2025.md"
HEADERS = [*contract.REQUIRED_HEADERS, "recipient_name"]


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_usaspending_contract_source_bundle", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


producer = _load_module()


def _csv_header(headers: list[str]) -> bytes:
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerow(headers)
    return output.getvalue().encode("utf-8")


def _write_archive(
    root: Path,
    *,
    fiscal_year: int,
    updated: str = "20260806",
    members: list[tuple[str, list[str]]] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    filename = f"FY{fiscal_year}_All_Contracts_Full_{updated}.zip"
    path = root / filename
    selected = members or [(f"FY{fiscal_year}_part_1.csv", HEADERS)]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, headers in selected:
            archive.writestr(name, _csv_header(headers))
    return path


def test_build_is_deterministic_and_pins_validator_derived_release_id(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archives"
    _write_archive(archive_dir, fiscal_year=2025)
    _write_archive(
        archive_dir,
        fiscal_year=2024,
        members=[("FY2024_part_2.csv", HEADERS), ("FY2024_part_1.csv", HEADERS)],
    )
    first_output = tmp_path / "first.json"
    second_output = tmp_path / "second.json"

    first = producer.build_source_bundle(
        source_snapshot_date=producer.date(2026, 8, 9),
        fiscal_years=[2024, 2025],
        archive_dir=archive_dir,
        output=first_output,
    )
    second = producer.build_source_bundle(
        source_snapshot_date=producer.date(2026, 8, 9),
        fiscal_years=[2024, 2025],
        archive_dir=archive_dir,
        output=second_output,
    )

    assert first == second == json.loads(first_output.read_text(encoding="utf-8"))
    assert first_output.read_bytes() == second_output.read_bytes()
    assert [row["fiscal_year"] for row in first["archives"]] == [2024, 2025]
    assert [member["member_name"] for member in first["archives"][0]["members"]] == [
        "FY2024_part_1.csv",
        "FY2024_part_2.csv",
    ]
    assert not (
        {"compressed_size_bytes", "downloaded_at", "row_count"}
        & set(first["archives"][0]["members"][0])
    )

    validated = contract.validate_usaspending_contract_source_bundle(first, base_dir=archive_dir)
    assert first["source_release_id"] == validated.source_release_id


def test_failure_does_not_overwrite_existing_output(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archives"
    _write_archive(
        archive_dir,
        fiscal_year=2025,
        members=[("part_1.csv", HEADERS), ("part_2.csv", [*HEADERS, "changed_schema"])],
    )
    output = tmp_path / "manifest.json"
    output.write_text("existing output\n", encoding="utf-8")

    with pytest.raises(contract.USAspendingContractSourceError, match="different schemas"):
        producer.build_source_bundle(
            source_snapshot_date=producer.date(2026, 8, 9),
            fiscal_years=[2025],
            archive_dir=archive_dir,
            output=output,
        )

    assert output.read_text(encoding="utf-8") == "existing output\n"
    assert list(tmp_path.glob(".manifest.json.*.tmp")) == []


def test_output_must_not_overwrite_source_archive(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archives"
    archive = _write_archive(archive_dir, fiscal_year=2025)
    original_bytes = archive.read_bytes()

    with pytest.raises(producer.BundleBuildError, match="must not overwrite"):
        producer.build_source_bundle(
            source_snapshot_date=producer.date(2026, 8, 9),
            fiscal_years=[2025],
            archive_dir=archive_dir,
            output=archive,
        )

    assert archive.read_bytes() == original_bytes


def test_missing_required_header_fails_closed(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archives"
    _write_archive(
        archive_dir,
        fiscal_year=2025,
        members=[("part.csv", HEADERS[1:])],
    )

    with pytest.raises(contract.USAspendingContractSourceError, match="missing required"):
        producer.build_source_bundle(
            source_snapshot_date=producer.date(2026, 8, 9),
            fiscal_years=[2025],
            archive_dir=archive_dir,
            output=tmp_path / "manifest.json",
        )


@pytest.mark.parametrize(
    "member_name",
    ["README.txt", "nested/part.csv", "../part.csv"],
)
def test_non_csv_and_unsafe_member_paths_fail_closed(tmp_path: Path, member_name: str) -> None:
    archive_dir = tmp_path / "archives"
    _write_archive(
        archive_dir,
        fiscal_year=2025,
        members=[("part.csv", HEADERS), (member_name, HEADERS)],
    )

    with pytest.raises(contract.USAspendingContractSourceError, match="flat|CSV"):
        producer.build_source_bundle(
            source_snapshot_date=producer.date(2026, 8, 9),
            fiscal_years=[2025],
            archive_dir=archive_dir,
            output=tmp_path / "manifest.json",
        )


def test_symlinked_archive_path_fails_closed(tmp_path: Path) -> None:
    source = _write_archive(tmp_path / "outside", fiscal_year=2025)
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    (archive_dir / source.name).symlink_to(source)

    with pytest.raises(producer.BundleBuildError, match="symbolic link"):
        producer.build_source_bundle(
            source_snapshot_date=producer.date(2026, 8, 9),
            fiscal_years=[2025],
            archive_dir=archive_dir,
            output=tmp_path / "manifest.json",
        )


@pytest.mark.parametrize(
    ("filename", "message"),
    [
        ("FY2025_DoD_Contracts_Full_20260806.zip", "official All Contracts Full"),
        ("FY2025_All_Contracts_Full_20260230.zip", "invalid update date"),
        ("FY2025_All_Contracts_Full_20260806.ZIP", "official All Contracts Full"),
    ],
)
def test_malformed_archive_filename_or_date_fails_closed(
    tmp_path: Path, filename: str, message: str
) -> None:
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    with zipfile.ZipFile(archive_dir / filename, "w") as archive:
        archive.writestr("part.csv", _csv_header(HEADERS))

    with pytest.raises(producer.BundleBuildError, match=message):
        producer.build_source_bundle(
            source_snapshot_date=producer.date(2026, 8, 9),
            fiscal_years=[2025],
            archive_dir=archive_dir,
            output=tmp_path / "manifest.json",
        )


def test_corrupt_zip_fails_closed(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    (archive_dir / "FY2025_All_Contracts_Full_20260806.zip").write_bytes(b"not a zip")

    with pytest.raises(producer.BundleBuildError, match="not a readable ZIP"):
        producer.build_source_bundle(
            source_snapshot_date=producer.date(2026, 8, 9),
            fiscal_years=[2025],
            archive_dir=archive_dir,
            output=tmp_path / "manifest.json",
        )


def test_open_fiscal_year_fails_closed(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archives"
    _write_archive(archive_dir, fiscal_year=2026)

    with pytest.raises(producer.BundleBuildError, match="not closed"):
        producer.build_source_bundle(
            source_snapshot_date=producer.date(2026, 8, 9),
            fiscal_years=[2026],
            archive_dir=archive_dir,
            output=tmp_path / "manifest.json",
        )


@pytest.mark.parametrize("value", ["20260809", "2026-8-9", "August 9, 2026"])
def test_cli_rejects_noncanonical_snapshot_dates(value: str) -> None:
    with pytest.raises(SystemExit):
        producer.parse_args(
            [
                "--source-snapshot-date",
                value,
                "--fiscal-year",
                "2025",
                "--archive-dir",
                "archives",
                "--output",
                "manifest.json",
            ]
        )


def test_explicit_selection_ignores_unrequested_open_year(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archives"
    _write_archive(archive_dir, fiscal_year=2025)
    _write_archive(archive_dir, fiscal_year=2026)

    manifest = producer.build_source_bundle(
        source_snapshot_date=producer.date(2026, 8, 9),
        fiscal_years=[2025],
        archive_dir=archive_dir,
        output=tmp_path / "manifest.json",
    )

    assert manifest["start_fiscal_year"] == manifest["end_fiscal_year"] == 2025
    assert [row["fiscal_year"] for row in manifest["archives"]] == [2025]


@pytest.mark.parametrize(
    ("fiscal_years", "message"),
    [
        ([2024, 2024], "exactly once"),
        ([2023, 2025], "contiguous"),
        ([], "at least one"),
    ],
)
def test_invalid_explicit_fiscal_year_selection_fails_closed(
    tmp_path: Path, fiscal_years: list[int], message: str
) -> None:
    archive_dir = tmp_path / "archives"
    _write_archive(archive_dir, fiscal_year=2024)

    with pytest.raises(producer.BundleBuildError, match=message):
        producer.build_source_bundle(
            source_snapshot_date=producer.date(2026, 8, 9),
            fiscal_years=fiscal_years,
            archive_dir=archive_dir,
            output=tmp_path / "manifest.json",
        )


def test_missing_requested_fiscal_year_fails_closed(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archives"
    _write_archive(archive_dir, fiscal_year=2024)

    with pytest.raises(producer.BundleBuildError, match="missing"):
        producer.build_source_bundle(
            source_snapshot_date=producer.date(2026, 8, 9),
            fiscal_years=[2025],
            archive_dir=archive_dir,
            output=tmp_path / "manifest.json",
        )


def test_tracked_real_bundle_and_report_reconcile() -> None:
    payload = TRACKED_MANIFEST.read_bytes()
    manifest = json.loads(payload)
    archive = manifest["archives"][0]
    members = archive["members"]

    assert hashlib.sha256(payload).hexdigest() == (
        "2dc362cb16c398f2d81de346fd4df8531130bedc58231ec72c583961297b10a1"
    )
    assert len(payload) == 94_016
    assert manifest["schema_version"] == 1
    assert manifest["product"] == "All_Contracts_Full"
    assert manifest["source_snapshot_date"] == "2026-08-09"
    assert manifest["start_fiscal_year"] == manifest["end_fiscal_year"] == 2025
    assert manifest["source_release_id"] == (
        "f727f7041869106b3c60039dbd8ccc2cc0c8e50884cb2820e3a36d6aa84cb408"
    )
    assert archive["filename"] == "FY2025_All_Contracts_Full_20260806.zip"
    assert archive["local_path"] == archive["filename"]
    assert archive["source_url"].endswith(f"/{archive['filename']}")
    assert archive["upstream_updated_date"] == "2026-08-06"
    assert archive["sha256"] == ("69e90f438b61de135a79f30ea3d35f1dfd5a0225b6e68d2a4fa523283174fcbb")
    assert archive["size_bytes"] == 1_975_007_443
    assert len(members) == 7
    assert sum(member["size_bytes"] for member in members) == 14_274_207_079
    assert {len(member["headers"]) for member in members} == {297}
    assert all(member["headers"] == members[0]["headers"] for member in members[1:])
    assert set(contract.REQUIRED_HEADERS) <= set(members[0]["headers"])

    report = TRACKED_REPORT.read_text(encoding="utf-8")
    for expected in (
        "1,975,007,443",
        "14,274,207,079",
        manifest["source_release_id"],
        archive["sha256"],
        hashlib.sha256(payload).hexdigest(),
    ):
        assert expected in report
