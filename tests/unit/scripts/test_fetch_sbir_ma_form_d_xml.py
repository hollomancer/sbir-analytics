import json
from pathlib import Path

from scripts.data.fetch_sbir_ma_form_d_xml import (
    _completed_accessions,
    _successful_xml_retrieval,
)
from scripts.data.observe_sbir_ma_form_d_business_combination import (
    _successful_xml_retrieval as observe_successful_xml_retrieval,
)


ACCESSION = "0001234567-24-000001"


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text(
        "".join(f"{json.dumps(record, sort_keys=True)}\n" for record in records),
        encoding="utf-8",
    )
    return path


def test_fetch_and_observe_share_successful_retrieval_rule() -> None:
    empty_body = {
        "accession_number": ACCESSION,
        "status": 200,
        "bytes": 0,
        "sha256": None,
    }
    complete = {
        "accession_number": ACCESSION,
        "status": 200,
        "bytes": 12,
        "sha256": "a" * 64,
    }

    assert _successful_xml_retrieval(empty_body) is False
    assert observe_successful_xml_retrieval(empty_body) is False
    assert _successful_xml_retrieval(complete) is True
    assert observe_successful_xml_retrieval(complete) is True


def test_completed_accessions_retries_empty_body_200(tmp_path: Path) -> None:
    manifest = _write_jsonl(
        tmp_path / "xml_manifest.jsonl",
        [
            {
                "accession_number": ACCESSION,
                "status": 200,
                "bytes": 0,
                "sha256": None,
            }
        ],
    )

    assert _completed_accessions(manifest) == set()


def test_completed_accessions_accepts_later_complete_retry(tmp_path: Path) -> None:
    manifest = _write_jsonl(
        tmp_path / "xml_manifest.jsonl",
        [
            {
                "accession_number": ACCESSION,
                "status": 200,
                "bytes": 0,
                "sha256": None,
            },
            {
                "accession_number": ACCESSION,
                "status": 200,
                "bytes": 12,
                "sha256": "a" * 64,
            },
        ],
    )

    assert _completed_accessions(manifest) == {ACCESSION}
