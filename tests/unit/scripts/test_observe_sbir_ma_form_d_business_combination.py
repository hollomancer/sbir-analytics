import hashlib
import json
from pathlib import Path

from scripts.data.observe_sbir_ma_form_d_business_combination import (
    _successful_xml_retrieval,
    _xml_provenance,
    main,
)


ACCESSION = "0001234567-24-000001"
XML_BYTES = (
    b"<edgarSubmission><offeringData><businessCombinationTransaction>"
    b"<isBusinessCombinationTransaction>true</isBusinessCombinationTransaction>"
    b"</businessCombinationTransaction></offeringData></edgarSubmission>"
)
XML_SHA256 = hashlib.sha256(XML_BYTES).hexdigest()


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text(
        "".join(f"{json.dumps(record, sort_keys=True)}\n" for record in records),
        encoding="utf-8",
    )
    return path


def _manifest_record(**overrides: object) -> dict:
    record = {
        "accession_number": ACCESSION,
        "status": 200,
        "bytes": len(XML_BYTES),
        "sha256": XML_SHA256,
    }
    record.update(overrides)
    return record


def test_empty_body_200_is_not_a_successful_retrieval() -> None:
    assert not _successful_xml_retrieval(_manifest_record(bytes=0, sha256=None))
    assert _successful_xml_retrieval(_manifest_record())


def test_xml_provenance_ignores_empty_body_200_and_keeps_later_complete_hash(
    tmp_path: Path,
) -> None:
    manifest = _write_jsonl(
        tmp_path / "xml_manifest.jsonl",
        [
            _manifest_record(bytes=0, sha256=None),
            _manifest_record(),
        ],
    )

    provenance = _xml_provenance(manifest)

    assert provenance == {ACCESSION: {"sha256": XML_SHA256}}


def test_xml_provenance_last_complete_retrieval_wins(tmp_path: Path) -> None:
    later_sha = "b" * 64
    manifest = _write_jsonl(
        tmp_path / "xml_manifest.jsonl",
        [
            _manifest_record(),
            _manifest_record(bytes=12, sha256=later_sha),
        ],
    )

    provenance = _xml_provenance(manifest)

    assert provenance[ACCESSION]["sha256"] == later_sha


def test_observe_rebuilds_ledger_from_retried_empty_body_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    xml_dir = tmp_path / "xml"
    xml_dir.mkdir()
    (xml_dir / f"{ACCESSION}.xml").write_bytes(XML_BYTES)
    candidates = _write_jsonl(
        tmp_path / "candidates.jsonl",
        [
            {
                "form_d_index": {
                    "accession_number": ACCESSION,
                    "cik": "1234567",
                    "filing_date": "2024-01-15",
                    "form_type": "D",
                }
            }
        ],
    )
    manifest = _write_jsonl(
        tmp_path / "xml_manifest.jsonl",
        [
            _manifest_record(bytes=0, sha256=None),
            _manifest_record(),
        ],
    )
    output = tmp_path / "observations.jsonl"
    monkeypatch.setattr(
        "sys.argv",
        [
            "observe_sbir_ma_form_d_business_combination.py",
            "--candidates",
            str(candidates),
            "--xml-dir",
            str(xml_dir),
            "--xml-manifest",
            str(manifest),
            "--output",
            str(output),
        ],
    )

    assert main() == 0

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {
            "accession_number": ACCESSION,
            "cik": "1234567",
            "claim_status": "source_field_observation",
            "filing_date": "2024-01-15",
            "form_type": "D",
            "predicate_path": (
                "offeringData/businessCombinationTransaction/isBusinessCombinationTransaction"
            ),
            "predicate_status": "true",
            "predicate_version": "form_d_business_combination_v1",
            "xml_sha256": XML_SHA256,
        }
    ]
