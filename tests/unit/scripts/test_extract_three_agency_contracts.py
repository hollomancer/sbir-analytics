import importlib.util
import sys
from pathlib import Path

import pandas as pd

from sbir_etl.extractors.usaspending_award_archive import AWARD_ARCHIVE_PROVENANCE_VERSION


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/data/extract_three_agency_contracts.py"
SPEC = importlib.util.spec_from_file_location("extract_three_agency_contracts", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _fingerprint(**overrides):
    payload = {
        "archive_name": "FY2009_All_Contracts_Full_20240101.zip",
        "archive_sha256": "a" * 64,
        "awards_sha256": "b" * 64,
        "cutoff": "2024-12-31",
        "filter_sha256": "c" * 64,
    }
    payload.update(overrides)
    return MODULE.extract_fingerprint(**payload)


def test_sidecar_reuse_requires_matching_fingerprint(tmp_path):
    output = tmp_path / "contracts_fy2009.parquet"
    pd.DataFrame({"piid": ["X1"]}).to_parquet(output)
    expected = _fingerprint()
    assert not MODULE.sidecar_allows_reuse(output, expected)

    MODULE.write_provenance_sidecar(
        output,
        {
            **expected,
            "output_sha256": MODULE.sha256_file(output),
            "rows": 1,
        },
    )
    assert MODULE.sidecar_allows_reuse(output, expected)
    assert expected["extractor_provenance_version"] == AWARD_ARCHIVE_PROVENANCE_VERSION

    stale_filter = _fingerprint(filter_sha256="d" * 64)
    assert not MODULE.sidecar_allows_reuse(output, stale_filter)

    output.write_bytes(output.read_bytes() + b"\x00")
    assert not MODULE.sidecar_allows_reuse(output, expected)


def test_missing_sidecar_does_not_reuse_existing_parquet(tmp_path):
    output = tmp_path / "contracts_fy2010.parquet"
    pd.DataFrame({"piid": ["X1"]}).to_parquet(output)
    assert not MODULE.sidecar_allows_reuse(output, _fingerprint())
