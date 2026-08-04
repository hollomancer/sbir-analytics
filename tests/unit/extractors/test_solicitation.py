"""Unit tests for sbir_etl.extractors.solicitation.SolicitationExtractor.

Uses httpx.MockTransport (no network, no extra dependency) so the real
request/response parsing path is exercised end-to-end.
"""

import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

from sbir_etl.exceptions import APIError
from sbir_etl.extractors.solicitation import (
    LEGACY_TOPIC_COLUMNS,
    SOLICITATION_TOPIC_COLUMNS,
    SOLICITATION_VERSION_COLUMNS,
    SolicitationExtractor,
    audit_solicitation_schema,
    normalize_solicitations,
)


pytestmark = pytest.mark.fast

DOCUMENTED_FIXTURE = (
    Path(__file__).parents[2] / "fixtures/extractors/sbir_gov_solicitations/documented_shape.json"
)


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
        assert list(df.columns) == LEGACY_TOPIC_COLUMNS

    def test_clamps_page_size_to_documented_api_limit(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["rows"] == "50"
            return httpx.Response(200, json=[])

        extractor = SolicitationExtractor(http_client=_client(handler))
        extractor.extract_topics(year=2024, page_size=500)

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


class TestNormalizedSolicitationTables:
    def test_documented_fixture_round_trips_without_field_loss(self):
        records = json.loads(DOCUMENTED_FIXTURE.read_text(encoding="utf-8"))

        tables = normalize_solicitations(
            records,
            source_url="https://api.www.sbir.gov/public/api/solicitations?rows=1",
            source_query={"rows": 1},
            retrieved_at="2026-08-04T12:00:00+00:00",
        )

        assert list(tables.solicitation_versions.columns) == SOLICITATION_VERSION_COLUMNS
        assert list(tables.topics.columns) == SOLICITATION_TOPIC_COLUMNS
        assert len(tables.solicitation_versions) == 1
        assert json.loads(tables.solicitation_versions.iloc[0]["source_record_json"]) == records[0]
        assert tables.solicitation_versions.iloc[0]["application_due_dates"] == [
            "2026-02-27",
            "2026-03-31",
        ]

    def test_preserves_topic_and_subtopic_hierarchy_with_unique_ids(self):
        records = json.loads(DOCUMENTED_FIXTURE.read_text(encoding="utf-8"))
        topics = normalize_solicitations(records).topics

        assert list(topics["topic_level"]) == ["topic", "subtopic"]
        assert topics["topic_id"].is_unique
        assert topics.iloc[1]["parent_topic_id"] == topics.iloc[0]["topic_id"]
        assert topics.iloc[1]["parent_topic_code"] == "TEST-2026-001-T01"
        assert topics.iloc[1]["topic_code"] == "TEST-2026-001-T01-S01"

    def test_legacy_view_remains_top_level_only(self):
        records = json.loads(DOCUMENTED_FIXTURE.read_text(encoding="utf-8"))

        legacy = SolicitationExtractor._flatten_to_topics(records)

        assert [row["topic_code"] for row in legacy] == ["TEST-2026-001-T01"]

    def test_source_and_legacy_views_do_not_truncate_description(self):
        description = "requirement " * 500
        record = _solicitation(topics=[{"topic_number": "T-LONG", "description": description}])

        tables = normalize_solicitations([record])
        legacy = SolicitationExtractor._flatten_to_topics([record])

        assert tables.topics.iloc[0]["description"] == description
        assert legacy[0]["description"] == description

    def test_retains_uncoded_nested_topic_in_source_table_but_not_legacy_view(self):
        record = _solicitation(topics=[{"topic_title": "No source identifier"}])

        tables = normalize_solicitations([record])
        legacy = SolicitationExtractor._flatten_to_topics([record])

        assert len(tables.topics) == 1
        assert tables.topics.iloc[0]["topic_code"] is None
        assert legacy == []

    def test_canonical_record_preserves_unknown_fields_and_audit_flags_drift(self):
        record = _solicitation()
        record["new_source_field"] = {"nested": True}

        tables = normalize_solicitations([record])
        coverage = audit_solicitation_schema([record])

        restored = json.loads(tables.solicitation_versions.iloc[0]["source_record_json"])
        assert restored["new_source_field"] == {"nested": True}
        assert coverage["unknown_fields"]["solicitation"] == ["new_source_field"]

    def test_schema_audit_maps_every_documented_field(self):
        records = json.loads(DOCUMENTED_FIXTURE.read_text(encoding="utf-8"))
        coverage = audit_solicitation_schema(records)

        assert coverage["documented_field_count"] == 25
        assert coverage["retained_documented_field_count"] == 25
        assert coverage["retention_rate"] == 1.0
        assert coverage["topic_record_count"] == 1
        assert coverage["subtopic_record_count"] == 1
        assert not any(coverage["unknown_fields"].values())

    def test_exact_duplicate_source_record_is_one_version(self):
        record = _solicitation()
        tables = normalize_solicitations([record, record])
        coverage = audit_solicitation_schema([record, record])

        assert len(tables.solicitation_versions) == 1
        assert coverage["duplicate_source_record_count"] == 1

    def test_extract_tables_records_query_and_retrieval_provenance(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[_solicitation()])

        extractor = SolicitationExtractor(
            base_url="https://example.test/public/api",
            http_client=_client(handler),
        )
        tables = extractor.extract_solicitation_tables(year=2024)
        row = tables.solicitation_versions.iloc[0]

        assert row["source_url"] == "https://example.test/public/api/solicitations"
        assert json.loads(row["source_query_json"])["year"] == 2024
        assert row["retrieved_at"].endswith("+00:00")


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
