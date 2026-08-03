import gzip
import hashlib
import io
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_negative_controls.february_mirror import (
    AwardSearchMirrorPin,
    FebruaryAwardSearchExtractor,
    _ordered_columns_sha256,
)
from sbir_analytics.assets.phase_iii_negative_controls.source_keys import (
    USA_FAIN_ADAPTER,
    USA_PIID_ADAPTER,
    USA_URI_ADAPTER,
)


pytestmark = pytest.mark.fast

_COLUMNS = (
    "award_id",
    "generated_unique_award_id",
    "piid",
    "fain",
    "uri",
    "recipient_unique_id",
    "recipient_uei",
    "awarding_toptier_agency_name",
)


def _attempts() -> pd.DataFrame:
    records = []
    for adapter in (USA_PIID_ADAPTER, USA_FAIN_ADAPTER, USA_URI_ADAPTER):
        records.append(
            {
                "adapter": adapter,
                "agency_key": "DEPARTMENT OF DEFENSE",
                "canonical_award_key": "FA1234",
            }
        )
    return pd.DataFrame(records)


def _pin(toc: bytes = b"pinned toc") -> AwardSearchMirrorPin:
    return AwardSearchMirrorPin(
        snapshot_date="2026-02-06",
        archive_url="https://example.test/archive.zip",
        replica_urls=(),
        archive_total_bytes=1,
        archive_etag='"etag"',
        toc_sha256=hashlib.sha256(toc).hexdigest(),
        dump_id="5923",
        member_crc32="12345678",
        member_bytes=100,
        ordered_columns_sha256=_ordered_columns_sha256(_COLUMNS),
    )


def test_schema_resolution_pins_table_and_ordered_columns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toc = b"pinned toc"
    toc_path = tmp_path / "toc.dat"
    toc_path.write_bytes(toc)
    copy_sql = f"COPY rpt.award_search ({', '.join(_COLUMNS)}) FROM stdin;\n\\.\n"

    def fake_pg_restore(
        dump_dir: Path,
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        if arguments == ("--list",):
            stdout = "5923; 0 0 TABLE DATA rpt award_search etl_user\n"
        else:
            stdout = copy_sql
        return subprocess.CompletedProcess([], 0, stdout, "")

    monkeypatch.setattr(FebruaryAwardSearchExtractor, "_run_pg_restore", fake_pg_restore)

    source = FebruaryAwardSearchExtractor._resolve_source(toc_path, _pin(toc))

    assert source.member_name == "5923.dat.gz"
    assert source.columns == _COLUMNS


def test_python_recheck_requires_exact_agency_and_key() -> None:
    extractor = FebruaryAwardSearchExtractor(_attempts(), pin=_pin())
    rows = [
        "1\tASST-1\tFA-12-34\t\\N\t\\N\t123456789\tUEI000000001\tDepartment of Defense\n",
        "2\tASST-2\tFA-12-34\t\\N\t\\N\t987654321\tUEI000000002\tDepartment of Energy\n",
    ]

    result = list(extractor._parse_candidates(iter(rows), _COLUMNS))

    assert len(result) == 1
    assert result[0]["official_record_id"] == "ASST-1"
    assert result[0]["matched_adapters"] == (USA_PIID_ADAPTER,)


def test_awk_prefilter_is_conservative_and_reports_scan_counts() -> None:
    extractor = FebruaryAwardSearchExtractor(_attempts(), pin=_pin())
    serialized = (
        b"1\tASST-1\tFA-12-34\t\\N\t\\N\t123456789\tUEI000000001\t"
        b"Department of Defense\n"
        b"2\tASST-2\tOTHER\t\\N\t\\N\t987654321\tUEI000000002\t"
        b"Department of Defense\n"
        b"\\.\n"
    )

    with gzip.GzipFile(fileobj=io.BytesIO(gzip.compress(serialized))) as source:
        candidates = list(extractor._prefilter_lines(source, _COLUMNS, awk_path="awk"))

    assert len(candidates) == 1
    assert "ASST-1" in candidates[0]
    assert extractor.stats == {
        "records_scanned": 2,
        "prefilter_matches": 1,
        "exact_matches": 0,
    }
