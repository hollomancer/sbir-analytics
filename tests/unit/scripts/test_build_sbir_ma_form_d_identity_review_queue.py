import hashlib
import json
from pathlib import Path

from scripts.data.build_sbir_ma_form_d_identity_review_queue import main


ACCESSION = "0001234567-24-000001"
XML_BYTES = (
    b"<edgarSubmission><primaryIssuer>"
    b"<entityName>Acme Corp</entityName><cik>0001234567</cik>"
    b"</primaryIssuer></edgarSubmission>"
)
XML_SHA256 = hashlib.sha256(XML_BYTES).hexdigest()
TAMPERED_XML = XML_BYTES.replace(b"Acme Corp", b"Other Corp")


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text(
        "".join(f"{json.dumps(record, sort_keys=True)}\n" for record in records),
        encoding="utf-8",
    )
    return path


def _candidate() -> dict:
    return {
        "form_d_index": {
            "accession_number": ACCESSION,
            "cik": "1234567",
            "filing_date": "2024-01-15",
            "form_type": "D",
            "filer_name": "Acme Corp",
        },
        "name_key": "ACME CORP",
        "name_key_profile": "form-d-join-v1",
        "sbir_aliases": ["Acme Corp"],
        "sbir_award_identifiers": [],
    }


def _observation(**overrides: object) -> dict:
    record = {
        "accession_number": ACCESSION,
        "predicate_status": "true",
        "xml_sha256": XML_SHA256,
    }
    record.update(overrides)
    return record


def _run_queue(
    tmp_path: Path,
    monkeypatch,
    *,
    xml_bytes: bytes | None,
    observation: dict | None = None,
) -> dict:
    xml_dir = tmp_path / "xml"
    xml_dir.mkdir()
    if xml_bytes is not None:
        (xml_dir / f"{ACCESSION}.xml").write_bytes(xml_bytes)
    candidates = _write_jsonl(tmp_path / "candidates.jsonl", [_candidate()])
    observations = _write_jsonl(
        tmp_path / "observations.jsonl",
        [observation or _observation()],
    )
    output = tmp_path / "queue.jsonl"
    monkeypatch.setattr(
        "sys.argv",
        [
            "build_sbir_ma_form_d_identity_review_queue.py",
            "--candidates",
            str(candidates),
            "--observations",
            str(observations),
            "--xml-dir",
            str(xml_dir),
            "--output",
            str(output),
        ],
    )

    assert main() == 0
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    return rows[0]


def test_matching_xml_hash_parses_issuer_and_prefills_alias_agreement(
    tmp_path: Path, monkeypatch
) -> None:
    row = _run_queue(tmp_path, monkeypatch, xml_bytes=XML_BYTES)

    assert row["form_d_issuer_name"] == "Acme Corp"
    assert row["form_d_issuer_cik"] == "0001234567"
    assert row["xml_sha256"] == XML_SHA256
    assert row["prefilled_evidence_codes"] == [
        "exact_key_candidate",
        "issuer_name_alias_agreement",
    ]
    assert row["evidence_codes"] == []
    assert row["source_reference_ids"] == []
    assert row["review_outcome"] == "unreviewed"


def test_missing_xml_stays_in_queue_without_issuer_fields(
    tmp_path: Path, monkeypatch
) -> None:
    row = _run_queue(tmp_path, monkeypatch, xml_bytes=None)

    assert row["form_d_issuer_name"] is None
    assert row["form_d_issuer_cik"] is None
    assert row["xml_sha256"] is None
    assert row["prefilled_evidence_codes"] == ["exact_key_candidate"]
    assert row["evidence_codes"] == []
    assert row["source_reference_ids"] == []
    assert row["review_outcome"] == "unreviewed"


def test_mismatched_xml_hash_does_not_inherit_observation_sha_or_alias_agreement(
    tmp_path: Path, monkeypatch
) -> None:
    row = _run_queue(tmp_path, monkeypatch, xml_bytes=TAMPERED_XML)

    assert row["form_d_issuer_name"] is None
    assert row["form_d_issuer_cik"] is None
    assert row["xml_sha256"] is None
    assert "issuer_name_alias_agreement" not in row["prefilled_evidence_codes"]
    assert row["evidence_codes"] == []
    assert row["source_reference_ids"] == []
