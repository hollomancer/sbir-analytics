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

from sbir_etl.extractors.source_downloads import sam_gov as download_module
from sbir_etl.extractors.source_downloads.sam_gov import (
    META_NAME,
    PARQUET_NAME,
    PARQUET_NAME_PARTIAL,
    PUBLIC_V2_FIELD_COUNT,
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


class TestPartialStrategy:
    def test_names_are_distinct(self):
        assert PARQUET_NAME != PARQUET_NAME_PARTIAL

    @pytest.mark.parametrize("strategy", [2, 3])
    def test_nonbulk_strategies_are_always_partial(self, strategy):
        assert _is_partial_result(strategy)

    def test_structurally_validated_bulk_result_is_canonical(self):
        assert not _is_partial_result(1)


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


def _public_v2_record(
    *,
    uei: str = "CANDIDATE001",
    status: str = "A",
    legal_name: str = "Example LLC",
) -> str:
    fields = [""] * PUBLIC_V2_FIELD_COUNT
    fields[0] = uei
    fields[3] = "A1B2C"
    fields[5] = status
    fields[11] = legal_name
    fields[15] = "10 Exact Road"
    fields[18] = "VA"
    fields[19] = "22030"
    fields[32] = "541715"
    fields[34] = "541715Y"
    fields[141] = "!end"
    return "|".join(fields)


def _public_v2_file(*records: str, declared_rows: int | None = None) -> str:
    row_count = len(records) if declared_rows is None else declared_rows
    control_suffix = f" PUBLIC V2 00000000 20260802 {row_count:07d} 0008305"
    return "\n".join([f"BOF{control_suffix}", *records, f"EOF{control_suffix}"])


def test_bulk_extract_download_is_keyless_and_records_provenance(monkeypatch) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "SAM_PUBLIC_UTF-8_MONTHLY_V2_20260802.dat",
            _public_v2_file(_public_v2_record(legal_name='"Example LLC')),
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
    assert result.loc[0, "legal_business_name"] == '"Example LLC'
    assert result.loc[0, "physical_address_zip_postal_code"] == "22030"
    assert result.attrs["sam_source_file"] == item["displayKey"]
    assert result.attrs["sam_source_sha256"] == hashlib.sha256(archive_bytes).hexdigest()
    assert result.attrs["sam_expected_row_count"] == 1
    assert all("api_key" not in kwargs.get("params", {}) for _, kwargs in calls)


def test_public_v2_parser_fails_closed_on_control_record_count_mismatch() -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "SAM_PUBLIC_UTF-8_MONTHLY_V2_20260802.dat",
            _public_v2_file(_public_v2_record(), declared_rows=2),
        )
    archive.seek(0)

    with pytest.raises(ValueError, match="entity count does not match"):
        download_module._parse_zip(archive)


def test_public_v2_parser_fails_closed_on_positional_drift() -> None:
    malformed = _public_v2_record().rsplit("|", 1)[0]
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "SAM_PUBLIC_UTF-8_MONTHLY_V2_20260802.dat",
            _public_v2_file(malformed),
        )
    archive.seek(0)

    with pytest.raises(ValueError, match="malformed positional record"):
        download_module._parse_zip(archive)


@pytest.mark.parametrize("entities", [2, 4])
def test_public_v2_parser_handles_entity_count_on_a_chunk_boundary(monkeypatch, entities) -> None:
    # With the count a multiple of the chunk size, the EOF line used to form a
    # one-field chunk on its own, which pandas rejected.
    monkeypatch.setattr(download_module, "PUBLIC_V2_CHUNK_ROWS", 2)
    records = [_public_v2_record(uei=f"CANDIDATE{i:03d}") for i in range(entities)]
    archive = io.BytesIO(_zip_bytes("SAM.dat", _public_v2_file(*records)))

    result = download_module._parse_zip(archive)

    assert result is not None
    assert len(result) == entities
    assert result.attrs["sam_expected_row_count"] == entities


def test_public_v2_parser_fails_closed_without_eof_control_record() -> None:
    body = _public_v2_file(_public_v2_record()).rsplit("\n", 1)[0]
    archive = io.BytesIO(_zip_bytes("SAM.dat", body))

    with pytest.raises(ValueError, match="missing or mismatched EOF control record"):
        download_module._parse_zip(archive)


def test_public_v2_parser_fails_closed_on_mismatched_eof_control_record() -> None:
    body = _public_v2_file(_public_v2_record()).replace(
        "EOF PUBLIC V2 00000000 20260802", "EOF PUBLIC V2 00000000 20260901"
    )
    archive = io.BytesIO(_zip_bytes("SAM.dat", body))

    with pytest.raises(ValueError, match="missing or mismatched EOF control record"):
        download_module._parse_zip(archive)


def test_public_v2_parser_fails_closed_on_duplicated_eof_control_record() -> None:
    body = _public_v2_file(_public_v2_record())
    body += "\n" + body.rsplit("\n", 1)[1]
    archive = io.BytesIO(_zip_bytes("SAM.dat", body))

    with pytest.raises(ValueError, match="data after its EOF control record"):
        download_module._parse_zip(archive)


def test_public_v2_repair_on_a_chunk_boundary_keeps_row_positions(monkeypatch) -> None:
    # Combines the two stream jobs: a repaired record in the second chunk, an
    # entity count that is a chunk multiple, and the EOF line diverted.
    monkeypatch.setattr(download_module, "PUBLIC_V2_CHUNK_ROWS", 2)
    records = [_public_v2_record(uei=f"CANDIDATE{i:03d}") for i in range(3)]
    records.append(_with_extra_pipe(_public_v2_record(uei="BADUEI000001")))
    archive = io.BytesIO(_zip_bytes("SAM.dat", _public_v2_file(*records)))

    result = download_module._parse_zip(archive)

    assert result is not None
    assert len(result) == 4
    assert result.loc[3, "unique_entity_id"] == "BADUEI000001"
    assert result.loc[3, "legal_business_name"] == ""
    assert (result.loc[:2, "legal_business_name"] == "Example LLC").all()
    assert result.attrs["sam_repaired_unescaped_delimiter_ueis"] == ["BADUEI000001"]


def test_public_v2_blank_name_on_unrepaired_row_fails_across_chunks(monkeypatch) -> None:
    # The exemption is by position: a blank name on an unrepaired row in a later
    # chunk must still fail, even when a repaired row sits in an earlier chunk.
    monkeypatch.setattr(download_module, "PUBLIC_V2_CHUNK_ROWS", 2)
    records = [
        _with_extra_pipe(_public_v2_record(uei="BADUEI000001")),
        _public_v2_record(uei="CANDIDATE001"),
        _public_v2_record(uei="CANDIDATE002", legal_name=""),
        _public_v2_record(uei="CANDIDATE003"),
    ]
    archive = io.BytesIO(_zip_bytes("SAM.dat", _public_v2_file(*records)))

    with pytest.raises(ValueError, match="missing legal business name"):
        download_module._parse_zip(archive)


def test_public_v2_parser_fails_closed_on_control_records_only() -> None:
    archive = io.BytesIO(_zip_bytes("SAM.dat", _public_v2_file(declared_rows=0)))

    with pytest.raises(ValueError, match="no entity records"):
        download_module._parse_zip(archive)


def _zip_bytes(name: str, payload: bytes | str) -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(name, payload)
    return archive.getvalue()


def test_public_v2_parser_opens_nested_zip() -> None:
    inner = _zip_bytes(
        "SAM_PUBLIC_UTF-8_MONTHLY_V2_20261101_abc.dat",
        _public_v2_file(_public_v2_record()),
    )
    outer = io.BytesIO(_zip_bytes("SAM_PUBLIC_UTF-8_MONTHLY_V2_20261101.ZIP", inner))

    result = download_module._parse_zip(outer)

    assert result is not None
    assert len(result) == 1
    assert result.loc[0, "unique_entity_id"] == "CANDIDATE001"
    assert result.attrs["sam_expected_row_count"] == 1


def test_nested_zip_still_fails_closed_on_control_record_mismatch() -> None:
    inner = _zip_bytes(
        "SAM_PUBLIC_UTF-8_MONTHLY_V2_20261101_abc.dat",
        _public_v2_file(_public_v2_record(), declared_rows=2),
    )
    outer = io.BytesIO(_zip_bytes("SAM_PUBLIC_UTF-8_MONTHLY_V2_20261101.ZIP", inner))

    with pytest.raises(ValueError, match="entity count does not match"):
        download_module._parse_zip(outer)


def test_nested_zip_beyond_depth_limit_returns_none() -> None:
    payload: bytes = _zip_bytes("data.dat", _public_v2_file(_public_v2_record()))
    for level in range(download_module.MAX_NESTED_ZIP_DEPTH + 1):
        payload = _zip_bytes(f"level{level}.zip", payload)

    assert download_module._parse_zip(io.BytesIO(payload)) is None


def test_zip_with_two_nested_zips_and_no_data_returns_none() -> None:
    inner = _zip_bytes("data.dat", _public_v2_file(_public_v2_record()))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("a.zip", inner)
        bundle.writestr("b.zip", inner)
    archive.seek(0)

    assert download_module._parse_zip(archive) is None


def _with_extra_pipe(record: str, extra: int = 1) -> str:
    fields = record.split("|")
    fields[11] = fields[11] + "|X" * extra  # literal "|" inside the legal name
    return "|".join(fields)


def test_public_v2_parser_keeps_records_with_unescaped_pipes() -> None:
    good = _public_v2_record(uei="GOODUEI00001")
    bad = _with_extra_pipe(_public_v2_record(uei="BADUEI000001"))
    bad2 = _with_extra_pipe(_public_v2_record(uei="BADUEI000002", status="E"), extra=2)
    archive = io.BytesIO(_zip_bytes("SAM.dat", _public_v2_file(good, bad, bad2)))

    result = download_module._parse_zip(archive)

    assert result is not None
    # The entity stays in the canonical file, so a UEI join still finds it.
    assert list(result["unique_entity_id"]) == ["GOODUEI00001", "BADUEI000001", "BADUEI000002"]
    repaired = result.set_index("unique_entity_id").loc[["BADUEI000001", "BADUEI000002"]]
    # Fields before the first free-text field are trusted ...
    assert list(repaired["registration_status"]) == ["A", "E"]
    assert list(repaired["cage_code"]) == ["A1B2C", "A1B2C"]
    # ... and every field that a stray "|" could shift is blank, not misplaced.
    shiftable = ["legal_business_name", "physical_address_state", "primary_naics"]
    assert (repaired[shiftable] == "").all().all()
    good_row = result.set_index("unique_entity_id").loc["GOODUEI00001"]
    assert good_row["legal_business_name"] == "Example LLC"
    assert good_row["primary_naics"] == "541715"
    assert result.attrs["sam_expected_row_count"] == 3
    assert result.attrs["sam_repaired_unescaped_delimiter_records"] == 2
    assert result.attrs["sam_repaired_unescaped_delimiter_ueis"] == ["BADUEI000001", "BADUEI000002"]


def test_public_v2_repair_exempts_only_the_repaired_row_not_its_uei() -> None:
    # A UEI can appear on more than one row. Repairing one of them must not hide a
    # blank legal name on another row with the same UEI.
    repaired = _with_extra_pipe(_public_v2_record(uei="SHAREDUEI001"))
    blank_sibling = _public_v2_record(uei="SHAREDUEI001", legal_name="")
    archive = io.BytesIO(_zip_bytes("SAM.dat", _public_v2_file(repaired, blank_sibling)))

    with pytest.raises(ValueError, match="missing legal business name"):
        download_module._parse_zip(archive)


def test_public_v2_repaired_row_and_named_sibling_with_same_uei_are_kept() -> None:
    repaired = _with_extra_pipe(_public_v2_record(uei="SHAREDUEI001"))
    sibling = _public_v2_record(uei="SHAREDUEI001")
    archive = io.BytesIO(_zip_bytes("SAM.dat", _public_v2_file(repaired, sibling)))

    result = download_module._parse_zip(archive)

    assert result is not None
    assert list(result["legal_business_name"]) == ["", "Example LLC"]
    assert result.attrs["sam_repaired_unescaped_delimiter_records"] == 1


def test_public_v2_well_formed_records_are_not_repaired() -> None:
    archive = io.BytesIO(_zip_bytes("SAM.dat", _public_v2_file(_public_v2_record())))

    result = download_module._parse_zip(archive)

    assert result is not None
    assert result.attrs["sam_repaired_unescaped_delimiter_records"] == 0
    assert result.loc[0, "legal_business_name"] == "Example LLC"


def test_public_v2_extra_fields_without_end_marker_still_fail_closed() -> None:
    bad = _with_extra_pipe(_public_v2_record()).rsplit("|", 1)[0] + "|notend"
    archive = io.BytesIO(_zip_bytes("SAM.dat", _public_v2_file(_public_v2_record(), bad)))

    with pytest.raises(ValueError, match="malformed positional record"):
        download_module._parse_zip(archive)


def test_public_v2_repaired_junk_line_fails_uei_check() -> None:
    # A junk prefix must not stand in for a missing entity.
    junk = "junk|" + _with_extra_pipe(_public_v2_record(uei="BADUEI000001"))
    archive = io.BytesIO(_zip_bytes("SAM.dat", _public_v2_file(_public_v2_record(), junk)))

    with pytest.raises(ValueError, match="missing or malformed UEI"):
        download_module._parse_zip(archive)


def test_public_v2_record_after_eof_fails_closed() -> None:
    late = _with_extra_pipe(_public_v2_record(uei="LATEUEI00001"))
    body = _public_v2_file(_public_v2_record(), declared_rows=2) + "\n" + late
    archive = io.BytesIO(_zip_bytes("SAM.dat", body))

    with pytest.raises(ValueError, match="data after its EOF control record"):
        download_module._parse_zip(archive)


def test_public_v2_repaired_record_with_invalid_utf8_uei_fails_closed() -> None:
    bad = _with_extra_pipe(_public_v2_record(uei="BADUEI000001")).encode()
    bad = b"\xffBADUEI00001" + bad[len("BADUEI000001") :]
    good = _public_v2_record().encode()
    control = b" PUBLIC V2 00000000 20260802 0000002 0008305"
    body = b"\n".join([b"BOF" + control, good, bad, b"EOF" + control])
    archive = io.BytesIO(_zip_bytes("SAM.dat", body))

    with pytest.raises(ValueError):
        download_module._parse_zip(archive)


def test_public_v2_repair_cap_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(download_module, "MIN_REPAIRED_PUBLIC_V2_CAP", 1)
    records = [_with_extra_pipe(_public_v2_record(uei=f"BADUEI00000{i}")) for i in range(2)]
    archive = io.BytesIO(_zip_bytes("SAM.dat", _public_v2_file(_public_v2_record(), *records)))

    with pytest.raises(ValueError, match="too many records with extra fields"):
        download_module._parse_zip(archive)


def test_public_v2_repaired_records_still_reconcile_with_control_count() -> None:
    bad = _with_extra_pipe(_public_v2_record(uei="BADUEI000001"))
    archive = io.BytesIO(
        _zip_bytes("SAM.dat", _public_v2_file(_public_v2_record(), bad, declared_rows=3))
    )

    with pytest.raises(ValueError, match="entity count does not match"):
        download_module._parse_zip(archive)


def test_write_local_sidecar_records_repaired_records(tmp_path) -> None:
    frame = _frame(1)
    frame.attrs["sam_repaired_unescaped_delimiter_records"] = 2
    frame.attrs["sam_repaired_unescaped_delimiter_ueis"] = ["A", "B"]

    _write_local(frame, tmp_path)

    meta = json.loads((tmp_path / META_NAME).read_text())
    assert meta["repaired_unescaped_delimiter_records"] == 2
    assert meta["repaired_unescaped_delimiter_ueis"] == ["A", "B"]
