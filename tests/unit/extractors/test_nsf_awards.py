import json
import zipfile
from datetime import UTC, datetime

import httpx
import pandas as pd
import pytest

from sbir_etl.exceptions import APIError
from sbir_etl.extractors.nsf_awards import (
    NSFAwardAPIClient,
    fetch_nsf_award_snapshots,
    load_nsf_awards,
    load_nsf_snapshot_index,
    normalize_nsf_award_id,
    normalize_nsf_award_record,
)


def _payload(award_id: str = "0620588") -> dict[str, object]:
    return {
        "response": {
            "award": [
                {
                    "id": award_id,
                    "title": "SBIR Phase II: Resilient material production",
                    "abstractText": "A direct NSF abstract.",
                    "activeAwd": "true",
                    "histAwd": "false",
                    "awardeeName": "Example Materials, Inc.",
                    "ueiNumber": "ABCDEFGHIJKL",
                    "date": "06/01/2024",
                    "startDate": "06/01/2024",
                    "expDate": "05/31/2026",
                    "estimatedTotalAmt": "1,000,000",
                    "fundsObligatedAmt": "900000",
                    "fundProgramName": "Small Business Innovation Research",
                    "progEleCode": ["5371"],
                }
            ]
        }
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("620588", "0620588"),
        (620588.0, "0620588"),
        ("123", "0000123"),
        (pd.NA, None),
        ("0", None),
        ("bad", None),
    ],
)
def test_normalize_nsf_award_id(value: object, expected: str | None) -> None:
    assert normalize_nsf_award_id(value) == expected


def test_client_preserves_raw_response_and_rejects_mismatch() -> None:
    content = json.dumps(_payload(), indent=3).encode()
    client = NSFAwardAPIClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200, content=content, headers={"content-type": "application/json"}
                )
            )
        )
    )
    result = client.fetch_award("620588")
    assert result.resolved_award_id == "0620588"
    assert result.content == content

    mismatch = NSFAwardAPIClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json=_payload("7654321"))
            )
        )
    )
    with pytest.raises(APIError, match="mismatched identifier"):
        mismatch.fetch_award("0620588")


def test_snapshot_restart_index_and_checksum_verification(tmp_path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        award_id = request.url.path.rsplit("/", 1)[-1].removesuffix(".json")
        calls.append(award_id)
        response = _payload(award_id) if award_id == "0620588" else {"response": {"award": []}}
        return httpx.Response(200, json=response)

    snapshot = tmp_path / "snapshot"
    client = NSFAwardAPIClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    first = fetch_nsf_award_snapshots(["620588", "1234567"], snapshot, client=client, max_workers=2)
    second = fetch_nsf_award_snapshots(
        ["1234567", "0620588"], snapshot, client=client, max_workers=2
    )
    assert first == second
    assert sorted(calls) == ["0620588", "1234567"]
    assert first["found_award_count"] == 1
    index = load_nsf_snapshot_index(snapshot).set_index("nsf_lookup_requested_award_id")
    assert index.loc["0620588", "nsf_lookup_status"] == "found"
    assert index.loc["1234567", "nsf_lookup_status"] == "not_found"
    with pytest.raises(FileExistsError, match="different identifier set"):
        fetch_nsf_award_snapshots(["0620588"], snapshot, client=client)

    (snapshot / "0620588.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_nsf_snapshot_index(snapshot)


def test_normalize_api_and_annual_records() -> None:
    retrieved = datetime(2026, 8, 3, tzinfo=UTC)
    api_record = _payload()["response"]["award"][0]  # type: ignore[index]
    api = normalize_nsf_award_record(
        api_record,
        source_path="api.json",
        source_sha256="api-sha",
        source_retrieved_at=retrieved,
    )
    annual = normalize_nsf_award_record(
        {
            "awd_id": "1234567",
            "awd_titl_txt": "STTR Phase I: Secure component",
            "awd_eff_date": "01/01/2020",
            "awd_exp_date": "12/31/2021",
            "awd_amount": "250000",
            "inst": {"inst_name": "Secure Components LLC", "org_uei_num": "MNOPQRSTUVWX"},
            "pgm_ele": [{"pgm_ele_name": "STTR"}],
        },
        source_path="annual.zip!award.json",
        source_sha256="annual-sha",
        source_retrieved_at=retrieved,
    )
    assert api["nsf_program"] == "SBIR"
    assert api["nsf_phase"] == "II"
    assert api["nsf_obligated_amount"] == 900_000
    assert annual["nsf_program"] == "STTR"
    assert annual["nsf_awardee_uei"] == "MNOPQRSTUVWX"


def test_load_sources_prefers_api_and_counts_duplicates(tmp_path) -> None:
    snapshot = tmp_path / "api"
    snapshot.mkdir()
    (snapshot / "0620588.json").write_text(json.dumps(_payload()), encoding="utf-8")
    archive_path = tmp_path / "annual.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "award.json",
            json.dumps(
                {
                    "awd_id": "0620588",
                    "awd_titl_txt": "Older annual title",
                    "awd_eff_date": "2024-06-01",
                    "awd_exp_date": "2026-05-31",
                }
            ),
        )
    loaded = load_nsf_awards([archive_path, snapshot])
    assert loaded["nsf_award_id"].tolist() == ["0620588"]
    assert loaded.iloc[0]["nsf_award_title"].startswith("SBIR Phase II")
    assert loaded.iloc[0]["direct_source_record_count"] == 2
