from datetime import date

import httpx
import pytest

from sbir_etl.exceptions import APIError
from sbir_etl.extractors.sam_gov_opportunities import SamGovOpportunitiesExtractor


def _record(notice_id: str) -> dict:
    return {
        "noticeId": notice_id,
        "type": "Solicitation",
        "title": "Autonomous navigation prototype",
        "active": "Yes",
        "postedDate": "2026-06-01",
        "responseDeadLine": "2026-08-01T17:00:00Z",
        "fullParentPathName": "DEFENSE.NAVY.NAVAIR",
        "fullParentPathCode": "097.1700.NAVAIR",
        "naicsCode": "541715",
        "classificationCode": "AJ11",
        "uiLink": "https://sam.gov/opp/1",
    }


def test_normalizes_public_record():
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200)))
    extractor = SamGovOpportunitiesExtractor(api_key="test", http_client=client)
    opportunity = extractor.normalize_record(_record("N-1"))
    assert opportunity.notice_id == "N-1"
    assert opportunity.notice_type_code == "o"
    assert opportunity.office == "NAVAIR"
    assert opportunity.psc_code == "AJ11"
    assert opportunity.active is True
    assert len(opportunity.content_hash) == 64


def test_paginates_without_partial_results():
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        rows = [_record(f"N-{offset}")] if offset < 2 else []
        return httpx.Response(200, json={"totalRecords": 2, "opportunitiesData": rows})

    extractor = SamGovOpportunitiesExtractor(
        api_key="test", page_size=1, http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    rows = list(extractor.iter_raw_records(posted_from=date(2026, 6, 1), posted_to=date(2026, 6, 30)))
    assert [row["noticeId"] for row in rows] == ["N-0", "N-1"]


def test_page_cap_raises_instead_of_returning_partial_data():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, json={"totalRecords": 5, "opportunitiesData": [_record("N-1")]}
            )
        )
    )
    extractor = SamGovOpportunitiesExtractor(
        api_key="test", page_size=1, max_pages=1, http_client=client
    )
    with pytest.raises(APIError, match="page cap"):
        list(extractor.iter_raw_records(posted_from=date(2026, 6, 1), posted_to=date(2026, 6, 30)))
