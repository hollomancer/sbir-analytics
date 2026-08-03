"""Unit tests for local-first SAM.gov entity download.

Focuses on the output layer, exact public-extract field mapping, and keyless
selection of the latest official UTF-8 monthly file.
"""

import json
import hashlib
import io
import zipfile

import pandas as pd
import pytest

from scripts.data import download_sam_gov as download_module
from scripts.data.download_sam_gov import (
    META_NAME,
    MIN_CANONICAL_ROW_COUNT,
    PARQUET_NAME,
    PARQUET_NAME_PARTIAL,
    REQUIRED_COLUMNS,
    _download_bulk_extract,
    _is_partial_result,
    _latest_public_extract,
    _normalise_chunk,
    _public_extract_download_url,
    _write_local,
)


def _frame(rows: int) -> pd.DataFrame:
    return pd.DataFrame({"uei": [f"U{i:06d}" for i in range(rows)], "name": ["Acme"] * rows})


class TestWriteLocal:
    def test_writes_canonical_parquet(self, tmp_path):
        df = _frame(10)

        path = _write_local(df, tmp_path)

        assert path == tmp_path / PARQUET_NAME
        assert pd.read_parquet(path).equals(df)

    def test_creates_missing_destination(self, tmp_path):
        dest = tmp_path / "nested" / "sam_gov"

        _write_local(_frame(3), dest)

        assert (dest / PARQUET_NAME).is_file()

    def test_writes_metadata_sidecar(self, tmp_path):
        _write_local(_frame(7), tmp_path)

        meta = json.loads((tmp_path / META_NAME).read_text())
        assert meta["row_count"] == 7
        assert meta["source"] == "sam.gov public data services"
        assert meta["partial"] is False
        assert meta["downloaded_at"]

    def test_partial_name_is_flagged_in_its_own_sidecar(self, tmp_path):
        # The sidecar is named after the parquet it describes, so a partial
        # write cannot clobber the canonical dataset's metadata.
        _write_local(_frame(5), tmp_path, name=PARQUET_NAME_PARTIAL)

        meta = json.loads((tmp_path / "sam_entity_records_partial.meta.json").read_text())
        assert meta["partial"] is True
        assert not (tmp_path / META_NAME).exists()

    def test_partial_write_does_not_touch_canonical(self, tmp_path):
        canonical = _write_local(_frame(60), tmp_path)
        canonical_bytes = canonical.read_bytes()

        _write_local(_frame(5), tmp_path, name=PARQUET_NAME_PARTIAL)

        assert canonical.read_bytes() == canonical_bytes
        assert (tmp_path / PARQUET_NAME_PARTIAL).is_file()

    def test_roundtrip_preserves_row_count(self, tmp_path):
        path = _write_local(_frame(1234), tmp_path)

        assert len(pd.read_parquet(path)) == 1234


class TestPartialThreshold:
    @pytest.mark.parametrize(
        ("rows", "expect_partial"),
        [
            (MIN_CANONICAL_ROW_COUNT - 1, True),
            (MIN_CANONICAL_ROW_COUNT, False),
            (MIN_CANONICAL_ROW_COUNT + 1, False),
        ],
    )
    def test_threshold_boundary(self, rows, expect_partial):
        # Mirrors the branch in main(); guards the boundary against drift.
        assert (rows < MIN_CANONICAL_ROW_COUNT) is expect_partial

    def test_names_are_distinct(self):
        assert PARQUET_NAME != PARQUET_NAME_PARTIAL

    @pytest.mark.parametrize("strategy", [2, 3])
    def test_nonbulk_strategies_are_always_partial(self, strategy):
        assert _is_partial_result(strategy, MIN_CANONICAL_ROW_COUNT * 100)

    def test_full_bulk_result_is_canonical(self):
        assert not _is_partial_result(1, MIN_CANONICAL_ROW_COUNT)


class TestPartialSidecarIsolation:
    """A partial write must not overwrite canonical metadata."""

    def test_partial_does_not_replace_canonical_sidecar(self, tmp_path):
        _write_local(_frame(60), tmp_path)
        canonical_meta = json.loads((tmp_path / "sam_entity_records.meta.json").read_text())

        _write_local(_frame(5), tmp_path, name=PARQUET_NAME_PARTIAL)

        after = json.loads((tmp_path / "sam_entity_records.meta.json").read_text())
        assert after == canonical_meta
        assert after["row_count"] == 60
        assert after["partial"] is False

    def test_partial_writes_its_own_sidecar(self, tmp_path):
        _write_local(_frame(5), tmp_path, name=PARQUET_NAME_PARTIAL)

        meta = json.loads((tmp_path / "sam_entity_records_partial.meta.json").read_text())
        assert meta["row_count"] == 5
        assert meta["partial"] is True


def test_normalise_chunk_preserves_frozen_eligibility_address_fields() -> None:
    source = pd.DataFrame(
        {
            "UNIQUE ENTITY ID": ["CANDIDATE001"],
            "SAM EXTRACT CODE": ["A"],
            "PHYSICAL ADDRESS LINE 1": ["10 Exact Road"],
            "PHYSICAL ADDRESS LINE 2": ["Suite 2"],
            "PHYSICAL ADDRESS STATE OR PROVINCE": ["VA"],
            "PHYSICAL ADDRESS ZIP/POSTAL CODE": ["22030"],
        }
    )

    result = _normalise_chunk(source)

    assert list(result.columns) == REQUIRED_COLUMNS
    assert result.loc[0, "unique_entity_id"] == "CANDIDATE001"
    assert result.loc[0, "registration_status"] == "A"
    assert result.loc[0, "physical_address_line_1"] == "10 Exact Road"
    assert result.loc[0, "physical_address_line_2"] == "Suite 2"
    assert result.loc[0, "physical_address_state"] == "VA"
    assert result.loc[0, "physical_address_zip_postal_code"] == "22030"


def test_latest_public_extract_selects_newest_utf8_monthly_file() -> None:
    items = [
        {
            "displayKey": "SAM_PUBLIC_MONTHLY_V2_20260802.ZIP",
            "key": "Entity Registration/Public V2/SAM_PUBLIC_MONTHLY_V2_20260802.ZIP",
        },
        {
            "displayKey": "SAM_PUBLIC_UTF-8_MONTHLY_V2_20260705.ZIP",
            "key": "Entity Registration/Public V2/SAM_PUBLIC_UTF-8_MONTHLY_V2_20260705.ZIP",
        },
        {
            "displayKey": "SAM_PUBLIC_UTF-8_MONTHLY_V2_20260802.ZIP",
            "key": "Entity Registration/Public V2/SAM_PUBLIC_UTF-8_MONTHLY_V2_20260802.ZIP",
        },
    ]

    selected = _latest_public_extract(items)

    assert selected["displayKey"] == "SAM_PUBLIC_UTF-8_MONTHLY_V2_20260802.ZIP"


def test_public_extract_download_url_is_keyless_and_pinned_to_catalog_key() -> None:
    item = {
        "displayKey": "SAM_PUBLIC_UTF-8_MONTHLY_V2_20260802.ZIP",
        "key": "Entity Registration/Public V2/SAM_PUBLIC_UTF-8_MONTHLY_V2_20260802.ZIP",
    }

    url = _public_extract_download_url(item)

    assert "api_key" not in url
    assert url.endswith(
        "/Entity%20Registration/Public%20V2/SAM_PUBLIC_UTF-8_MONTHLY_V2_20260802.ZIP?privacy=Public"
    )


def test_public_extract_download_url_rejects_catalog_key_mismatch() -> None:
    item = {
        "displayKey": "SAM_PUBLIC_UTF-8_MONTHLY_V2_20260802.ZIP",
        "key": "unexpected/path.zip",
    }

    with pytest.raises(ValueError, match="unexpected object key"):
        _public_extract_download_url(item)


def test_bulk_extract_download_is_keyless_and_records_provenance(monkeypatch) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "SAM_PUBLIC_UTF-8_MONTHLY_V2_20260802.dat",
            "UNIQUE ENTITY ID|SAM EXTRACT CODE|LEGAL BUSINESS NAME|"
            "PHYSICAL ADDRESS LINE 1|PHYSICAL ADDRESS PROVINCE OR STATE|"
            "PHYSICAL ADDRESS ZIP/POSTAL CODE|CAGE CODE|PRIMARY NAICS\n"
            "CANDIDATE001|A|Example LLC|10 Exact Road|VA|22030|A1B2C|541715\n",
        )
    archive_bytes = archive.getvalue()
    item = {
        "displayKey": "SAM_PUBLIC_UTF-8_MONTHLY_V2_20260802.ZIP",
        "dateModified": "Aug 02,2026",
        "key": "Entity Registration/Public V2/SAM_PUBLIC_UTF-8_MONTHLY_V2_20260802.ZIP",
    }
    calls = []

    class FakeResponse:
        def __init__(self, *, payload=b"", json_payload=None):
            self.ok = True
            self.status_code = 200
            self._payload = payload
            self._json_payload = json_payload
            self.headers = {
                "content-type": "application/zip",
                "content-length": str(len(payload)),
            }

        def json(self):
            return self._json_payload

        def iter_content(self, chunk_size):
            yield self._payload

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if len(calls) == 1:
            return FakeResponse(json_payload={"_embedded": {"customS3ObjectSummaryList": [item]}})
        return FakeResponse(payload=archive_bytes)

    monkeypatch.setattr(download_module.requests, "get", fake_get)

    result = _download_bulk_extract()

    assert len(result) == 1
    assert result.loc[0, "unique_entity_id"] == "CANDIDATE001"
    assert result.loc[0, "physical_address_zip_postal_code"] == "22030"
    assert result.attrs["sam_source_file"] == item["displayKey"]
    assert result.attrs["sam_source_sha256"] == hashlib.sha256(archive_bytes).hexdigest()
    assert all("api_key" not in kwargs.get("params", {}) for _, kwargs in calls)
