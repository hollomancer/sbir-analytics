"""Unit tests for sbir_etl.extractors.solicitation.SolicitationExtractor.

Uses httpx.MockTransport (no network, no extra dependency) so the real
request/response parsing path is exercised end-to-end.
"""

import httpx
import pandas as pd
import pytest

from sbir_etl.exceptions import APIError
from sbir_etl.extractors.solicitation import SolicitationExtractor


pytestmark = pytest.mark.fast


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _solicitation(
    sol_number="DOE-2024-1",
    agency="DOE",
    program="SBIR",
    topics=None,
):
    return {
        "solicitation_number": sol_number,
        "agency": agency,
        "program": program,
        "solicitation_topics": topics
        if topics is not None
        else [
            {
                "topic_number": "DOE-2024-1-A1",
                "topic_title": "Advanced Battery Materials",
                "topic_description": "Seeking novel solid-state electrolyte chemistries.",
            }
        ],
    }


class TestExtractTopics:
    def test_flattens_nested_topics(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["year"] == "2024"
            return httpx.Response(200, json=[_solicitation()])

        extractor = SolicitationExtractor(http_client=_client(handler))
        df = extractor.extract_topics(year=2024)

        assert list(df["topic_code"]) == ["DOE-2024-1-A1"]
        assert df.iloc[0]["title"] == "Advanced Battery Materials"
        assert df.iloc[0]["agency"] == "DOE"
        assert df.iloc[0]["solicitation_number"] == "DOE-2024-1"

    def test_paginates_until_short_page(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            start = int(request.url.params["start"])
            calls.append(start)
            if start == 0:
                sols = [
                    _solicitation(
                        sol_number=f"S-{i}",
                        topics=[{"topic_number": f"T-{i}", "topic_title": f"Topic {i}"}],
                    )
                    for i in range(100)
                ]
                return httpx.Response(200, json=sols)
            return httpx.Response(200, json=[])

        extractor = SolicitationExtractor(http_client=_client(handler))
        df = extractor.extract_topics(year=2024, max_results=1000, page_size=100)

        assert calls == [0, 100]
        assert len(df) == 100

    def test_empty_response_returns_empty_dataframe_with_columns(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[])

        extractor = SolicitationExtractor(http_client=_client(handler))
        df = extractor.extract_topics(year=2024)

        assert df.empty
        assert "topic_code" in df.columns

    def test_topic_without_code_is_skipped(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[_solicitation(topics=[{"topic_title": "No code here"}])],
            )

        extractor = SolicitationExtractor(http_client=_client(handler))
        df = extractor.extract_topics(year=2024)

        assert df.empty

    def test_flat_record_with_no_nested_topics_list(self):
        """A solicitation record that IS a topic (no nested topics list)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    {
                        "solicitation_number": "NASA-2024-1",
                        "topic_number": "NASA-2024-1-H1",
                        "topic_title": "In-Space Manufacturing",
                        "agency": "NASA",
                    }
                ],
            )

        extractor = SolicitationExtractor(http_client=_client(handler))
        df = extractor.extract_topics(year=2024)

        assert list(df["topic_code"]) == ["NASA-2024-1-H1"]
        assert df.iloc[0]["agency"] == "NASA"

    def test_non_200_raises_api_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="server error")

        extractor = SolicitationExtractor(http_client=_client(handler), timeout=1.0)
        with pytest.raises(APIError):
            extractor.extract_topics(year=2024)

    def test_alternate_camelcase_field_names(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    {
                        "solicitationNumber": "AF-2024-1",
                        "topics": [
                            {
                                "topicCode": "AF241-001",
                                "topicTitle": "Hypersonic Sensors",
                                "topicDescription": "Sensor systems for hypersonic flight.",
                            }
                        ],
                    }
                ],
            )

        extractor = SolicitationExtractor(http_client=_client(handler))
        df = extractor.extract_topics(year=2024)

        assert df.iloc[0]["topic_code"] == "AF241-001"
        assert df.iloc[0]["title"] == "Hypersonic Sensors"
        assert df.iloc[0]["solicitation_number"] == "AF-2024-1"


class TestDeduplicateTopics:
    def test_drops_duplicates_preferring_description(self):
        df = pd.DataFrame(
            [
                {"topic_code": "A1", "title": "A1", "description": None},
                {"topic_code": "A1", "title": "A1 with desc", "description": "full text"},
            ]
        )
        deduped = SolicitationExtractor.deduplicate_topics(df)

        assert len(deduped) == 1
        assert deduped.iloc[0]["description"] == "full text"

    def test_empty_dataframe_passthrough(self):
        df = pd.DataFrame(columns=["topic_code", "title"])
        assert SolicitationExtractor.deduplicate_topics(df).empty

    def test_missing_topic_code_column_passthrough(self):
        df = pd.DataFrame([{"title": "no topic code column"}])
        result = SolicitationExtractor.deduplicate_topics(df)
        assert len(result) == 1


class TestQueryByKeyword:
    def test_returns_flattened_topics(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["keyword"] == "battery"
            return httpx.Response(200, json=[_solicitation()])

        extractor = SolicitationExtractor(http_client=_client(handler))
        results = extractor.query_by_keyword("battery")

        assert len(results) == 1
        assert results[0]["topic_code"] == "DOE-2024-1-A1"


class TestQueryAwardsForTopic:
    def test_returns_dict_from_matching_award(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["topic_code"] == "DOE-2024-1-A1"
            return httpx.Response(
                200,
                json=[
                    {
                        "award_title": "Solid-State Battery Research",
                        "abstract": "Long-form abstract text.",
                        "agency": "DOE",
                        "program": "SBIR",
                    }
                ],
            )

        extractor = SolicitationExtractor(http_client=_client(handler))
        result = extractor.query_awards_for_topic("DOE-2024-1-A1")

        assert result == {
            "title": "Solid-State Battery Research",
            "description": "Long-form abstract text.",
            "agency": "DOE",
            "program": "SBIR",
        }

    def test_no_match_returns_none(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[])

        extractor = SolicitationExtractor(http_client=_client(handler))
        assert extractor.query_awards_for_topic("UNKNOWN-1") is None

    def test_non_200_returns_none_not_raise(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="not found")

        extractor = SolicitationExtractor(http_client=_client(handler))
        assert extractor.query_awards_for_topic("MISSING-1") is None

    def test_transport_error_returns_none_not_raise(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out", request=request)

        extractor = SolicitationExtractor(http_client=_client(handler))
        assert extractor.query_awards_for_topic("TIMEOUT-1") is None


class TestClientLifecycle:
    def test_close_is_idempotent(self):
        extractor = SolicitationExtractor()
        extractor.close()
        extractor.close()  # must not raise

    def test_context_manager_closes_client(self):
        with SolicitationExtractor() as extractor:
            assert extractor._client is None  # lazy — not yet created
        # No assertion beyond "no exception" — close() on an unopened
        # client is a no-op by design.

    def test_lazy_client_created_on_first_access(self):
        extractor = SolicitationExtractor()
        assert extractor._client is None
        client = extractor.client
        assert isinstance(client, httpx.Client)
        extractor.close()
        assert extractor._client is None
