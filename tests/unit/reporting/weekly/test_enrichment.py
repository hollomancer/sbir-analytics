"""Hermetic tests for weekly report enrichment orchestration."""

from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from sbir_etl.enrichers.press_wire import PressRelease
from sbir_etl.reporting.weekly import enrichment


pytestmark = pytest.mark.fast


def test_lookup_pi_external_data_reuses_company_results_and_deduplicates(monkeypatch):
    patents = object()
    publications = object()
    orcid = object()
    federal_awards = object()
    patent_lookup = Mock(return_value=patents)
    publication_lookup = Mock(return_value=publications)
    orcid_lookup = Mock(return_value=orcid)
    company_lookup = Mock(side_effect=AssertionError("company lookup should be reused"))
    monkeypatch.setattr(enrichment, "_lib_lookup_pi_patents_with_fallback", patent_lookup)
    monkeypatch.setattr(enrichment, "_lib_lookup_pi_publications_with_fallback", publication_lookup)
    monkeypatch.setattr(enrichment, "_lib_lookup_pi_orcid_with_fallback", orcid_lookup)
    monkeypatch.setattr(enrichment, "_lib_lookup_company_federal_awards", company_lookup)

    awards = [
        {
            "PI Name": " Jane Doe ",
            "Company": "Acme Labs",
            "Company UEI": "UEI-1",
            "_normalized_company": "acme labs",
        },
        {
            "PI Name": "Jane Doe",
            "Company": "Duplicate Company Context",
            "_normalized_company": "duplicate",
        },
        {"PI Name": "   ", "Company": "Ignored"},
    ]

    result = enrichment.lookup_pi_external_data(
        awards, company_federal_awards={"acme labs": federal_awards}
    )

    assert result == {
        "JANE DOE": {
            "patents": patents,
            "publications": publications,
            "orcid": orcid,
            "federal_awards": federal_awards,
        }
    }
    patent_lookup.assert_called_once_with(
        "Jane Doe", "Acme Labs", lens_rate_limiter=enrichment._lens_limiter
    )
    publication_lookup.assert_called_once_with(
        "Jane Doe",
        rate_limiter=enrichment._semantic_scholar_limiter,
        orcid_rate_limiter=enrichment._orcid_limiter,
    )
    orcid_lookup.assert_called_once_with(
        "Jane Doe",
        rate_limiter=enrichment._orcid_limiter,
        semantic_scholar_rate_limiter=enrichment._semantic_scholar_limiter,
    )
    company_lookup.assert_not_called()


def test_lookup_pi_external_data_queries_company_and_isolates_pi_errors(monkeypatch, capsys):
    def patent_lookup(name, _company, **_kwargs):
        if name == "Broken PI":
            raise RuntimeError("patent service unavailable")
        return f"patents:{name}"

    monkeypatch.setattr(enrichment, "_lib_lookup_pi_patents_with_fallback", patent_lookup)
    monkeypatch.setattr(
        enrichment,
        "_lib_lookup_pi_publications_with_fallback",
        lambda name, **_kwargs: f"publications:{name}",
    )
    monkeypatch.setattr(
        enrichment,
        "_lib_lookup_pi_orcid_with_fallback",
        lambda name, **_kwargs: f"orcid:{name}",
    )
    company_lookup = Mock(return_value="federal-history")
    monkeypatch.setattr(enrichment, "_lib_lookup_company_federal_awards", company_lookup)

    result = enrichment.lookup_pi_external_data(
        [
            {"PI Name": "Good PI", "Company": "Good Co", "UEI": "LEGACY-UEI"},
            {"PI Name": "Broken PI", "Company": "Broken Co"},
        ]
    )

    assert result == {
        "GOOD PI": {
            "patents": "patents:Good PI",
            "publications": "publications:Good PI",
            "orcid": "orcid:Good PI",
            "federal_awards": "federal-history",
        }
    }
    company_lookup.assert_called_once_with(
        "Good Co", "LEGACY-UEI", rate_limiter=enrichment._usaspending_limiter
    )
    assert (
        "PI external data error for Broken PI: patent service unavailable"
        in capsys.readouterr().err
    )


def test_lookup_usaspending_recipients_keeps_hits_and_isolates_failures(monkeypatch, capsys):
    profile = object()

    def lookup(name, _uei, **_kwargs):
        if name == "Broken Co":
            raise RuntimeError("recipient API down")
        if name == "No Match Co":
            return None
        return profile

    lookup_mock = Mock(side_effect=lookup)
    monkeypatch.setattr(enrichment, "_lib_lookup_usaspending_recipient_with_fallback", lookup_mock)

    result = enrichment.lookup_usaspending_recipients(
        [
            {"Company": " Acme Co ", "Company UEI": "UEI-1"},
            {"Company": "Acme Co", "Company UEI": "ignored duplicate"},
            {"Company": "No Match Co"},
            {"Company": "Broken Co"},
            {"Company": "  "},
        ]
    )

    assert result == {"ACME CO": profile}
    assert lookup_mock.call_count == 3
    stderr = capsys.readouterr().err
    assert (
        "Warning: USAspending recipient lookup failed for BROKEN CO: recipient API down" in stderr
    )
    assert "Found 1/3 recipient profiles" in stderr


def test_lookup_usaspending_recipients_stops_after_stage_deadline(monkeypatch, capsys):
    monkeypatch.setattr(
        enrichment,
        "_lib_lookup_usaspending_recipient_with_fallback",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(enrichment, "_past_deadline", lambda _deadline: True)

    result = enrichment.lookup_usaspending_recipients([{"Company": "Acme Co"}])

    assert result == {}
    assert "USAspending recipient stage timeout" in capsys.readouterr().err


def test_lookup_sam_entities_skips_without_api_key(monkeypatch, capsys):
    lookup = Mock(side_effect=AssertionError("SAM lookup should not run without a key"))
    monkeypatch.delenv("SAM_GOV_API_KEY", raising=False)
    monkeypatch.setattr(enrichment, "_lib_lookup_sam_entity_with_fallback", lookup)

    assert enrichment.lookup_sam_entities([{"Company": "Acme Co"}]) == {}
    lookup.assert_not_called()
    assert "SAM_GOV_API_KEY not set" in capsys.readouterr().err


def test_lookup_sam_entities_passes_identifiers_and_collects_records(monkeypatch):
    record = object()
    lookup = Mock(return_value=record)
    monkeypatch.setenv("SAM_GOV_API_KEY", "test-key")
    monkeypatch.setattr(enrichment, "_lib_lookup_sam_entity_with_fallback", lookup)

    result = enrichment.lookup_sam_entities(
        [{"Company": "Acme Co", "UEI": "LEGACY-UEI", "CAGE": "1ABC2"}]
    )

    assert result == {"ACME CO": record}
    lookup.assert_called_once_with(
        "Acme Co",
        "LEGACY-UEI",
        "1ABC2",
        rate_limiter=enrichment._sam_gov_limiter,
        fallback_rate_limiter=enrichment._usaspending_limiter,
    )


def test_lookup_opencorporates_uses_jurisdiction_and_isolates_errors(monkeypatch, capsys):
    record = object()
    calls = []

    class FakeOpenCorporatesClient:
        def __init__(self, *, shared_limiter):
            assert shared_limiter is enrichment._opencorporates_limiter

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            return None

        def lookup_company(self, name, *, jurisdiction):
            calls.append((name, jurisdiction))
            if name == "Broken Co":
                raise RuntimeError("registry unavailable")
            return record

    monkeypatch.setattr(enrichment, "SyncOpenCorporatesClient", FakeOpenCorporatesClient)

    result = enrichment.lookup_opencorporates(
        [
            {"Company": "Acme Co", "State": "VA", "_normalized_company": "acme"},
            {"Company": "Broken Co", "State": "Virginia", "_normalized_company": "broken"},
        ]
    )

    assert result == {"acme": record}
    assert set(calls) == {("Acme Co", "us_va"), ("Broken Co", None)}
    assert "Warning: OpenCorporates lookup failed for broken: registry unavailable" in (
        capsys.readouterr().err
    )


def test_poll_press_wire_groups_only_known_company_hits(monkeypatch):
    hits = [
        PressRelease(title="First", link="https://example.test/1", matched_company="Acme Co"),
        PressRelease(title="Second", link="https://example.test/2", matched_company="Acme Co"),
        PressRelease(title="Other", link="https://example.test/3", matched_company="Unknown Co"),
    ]

    class FakePressWireClient:
        watchlist = None

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            return None

        def set_watchlist(self, watchlist):
            type(self).watchlist = watchlist

        def poll(self):
            return hits

    monkeypatch.setattr(enrichment, "SyncPressWireClient", FakePressWireClient)

    result = enrichment.poll_press_wire(
        [
            {"Company": "Acme Co", "_normalized_company": "acme"},
            {"Company": "Acme Co", "_normalized_company": "acme"},
            {"Company": "  "},
        ]
    )

    assert FakePressWireClient.watchlist == ["Acme Co"]
    assert result == {"acme": hits[:2]}


def test_fetch_solicitation_topics_uses_batch_keyword_and_awards_fallback(monkeypatch):
    long_batch_description = "x" * 3001
    long_fallback_description = "y" * 3001
    extractor = SimpleNamespace(
        extract_topics=Mock(
            return_value=pd.DataFrame(
                [
                    {
                        "topic_code": "YEAR-TOPIC",
                        "topicTitle": "Batch title",
                        "topicDescription": long_batch_description,
                        "solicitationNumber": "API-SOLICITATION",
                        "agency": "DOD",
                        "program": "SBIR",
                    }
                ]
            )
        ),
        deduplicate_topics=Mock(side_effect=lambda frame: frame),
        query_by_keyword=Mock(
            return_value=[
                {"topicCode": "OTHER", "topicTitle": "Ignore"},
                {"topicCode": "SEARCH-TOPIC", "topicTitle": "Keyword title"},
            ]
        ),
        query_awards_for_topic=Mock(
            return_value={
                "title": "Awards fallback title",
                "description": long_fallback_description,
                "agency": "NASA",
                "program": "STTR",
            }
        ),
        close=Mock(),
    )
    monkeypatch.setattr(enrichment, "SolicitationExtractor", Mock(return_value=extractor))

    result = enrichment.fetch_solicitation_topics(
        [
            {"Topic Code": "YEAR-TOPIC", "Solicitation Number": "DOD-2025-1"},
            {"Topic Code": "SEARCH-TOPIC", "Solicitation Number": "BAA-X"},
            {"Topic Code": "FALLBACK-TOPIC", "Solicitation Number": "NASA 2025"},
            {"Topic Code": "YEAR-TOPIC", "Solicitation Number": "duplicate"},
        ]
    )

    assert set(result) == {"YEAR-TOPIC", "SEARCH-TOPIC", "FALLBACK-TOPIC"}
    assert result["YEAR-TOPIC"].solicitation_number == "API-SOLICITATION"
    assert result["YEAR-TOPIC"].description == long_batch_description[:3000] + "..."
    assert result["SEARCH-TOPIC"].title == "Keyword title"
    assert result["FALLBACK-TOPIC"].description == long_fallback_description[:3000] + "..."
    extractor.extract_topics.assert_called_once_with(year=2025, max_results=1000)
    extractor.query_by_keyword.assert_called_once_with("BAA-X")
    extractor.query_awards_for_topic.assert_called_once_with("FALLBACK-TOPIC")
    extractor.close.assert_called_once_with()


def test_fetch_solicitation_topics_returns_early_when_codes_are_missing(monkeypatch):
    constructor = Mock(side_effect=AssertionError("extractor should not be constructed"))
    monkeypatch.setattr(enrichment, "SolicitationExtractor", constructor)

    assert enrichment.fetch_solicitation_topics([{"Topic Code": "  "}, {}]) == {}
    constructor.assert_not_called()


def test_fetch_solicitation_topics_closes_extractor_after_error(monkeypatch):
    extractor = SimpleNamespace(
        extract_topics=Mock(side_effect=RuntimeError("SBIR API unavailable")),
        close=Mock(),
    )
    monkeypatch.setattr(enrichment, "SolicitationExtractor", Mock(return_value=extractor))

    with pytest.raises(RuntimeError, match="SBIR API unavailable"):
        enrichment.fetch_solicitation_topics(
            [{"Topic Code": "TOPIC-1", "Solicitation Number": "DOD 2025"}]
        )

    extractor.close.assert_called_once_with()


def test_fetch_usaspending_contract_descriptions_delegates_with_shared_limiter(monkeypatch):
    awards = [{"Contract": "C-1"}]
    delegated = {"C-1": "Contract description"}
    fetch = Mock(return_value=delegated)
    monkeypatch.setattr(enrichment, "_lib_fetch_usaspending_contract_descriptions", fetch)

    assert enrichment.fetch_usaspending_contract_descriptions(awards) is delegated
    fetch.assert_called_once_with(awards, rate_limiter=enrichment._usaspending_limiter)


def test_enrich_with_inflation_normalizes_report_columns(monkeypatch):
    captured = {}

    class FakeInflationAdjuster:
        def __init__(self, *, config):
            captured["config"] = config

        def adjust_awards_dataframe(self, frame):
            captured["frame"] = frame.copy()
            return pd.DataFrame(
                {
                    "fiscal_adjusted_amount": [1250.0, 50.0],
                    "fiscal_base_year": [2025, 2025],
                }
            )

    monkeypatch.setattr(enrichment, "InflationAdjuster", FakeInflationAdjuster)

    result = enrichment.enrich_with_inflation(
        [
            {"Award Amount": "$1,000", "Proposal Award Date": "2023-01-01"},
            {"Award Amount": "not available", "Proposal Award Date": "2024-01-01"},
        ],
        base_year=2025,
    )

    assert result == {"adjusted_total": 1300.0, "base_year": 2025}
    assert captured["config"] == {"base_year": 2025}
    assert captured["frame"]["award_amount"].tolist() == [1000.0, 0.0]
    assert captured["frame"]["award_date"].tolist() == ["2023-01-01", "2024-01-01"]


def test_enrich_with_inflation_returns_empty_on_adjuster_error(monkeypatch):
    debug = Mock()
    monkeypatch.setattr(
        enrichment,
        "InflationAdjuster",
        Mock(side_effect=RuntimeError("missing CPI data")),
    )
    monkeypatch.setattr(enrichment, "_debug", debug)

    assert enrichment.enrich_with_inflation([{"Award Amount": "100"}]) == {}
    debug.assert_called_once_with("InflationAdjuster error: missing CPI data")


def test_resolve_congressional_districts_skips_missing_zip_and_isolates_errors(monkeypatch):
    calls = []

    class FakeResolver:
        def __init__(self, *, method):
            assert method == "auto"

        def resolve_single_address(self, **address):
            calls.append(address)
            if address["zip_code"] == "22222":
                raise RuntimeError("Census unavailable")
            if address["zip_code"] == "33333":
                return SimpleNamespace(congressional_district=None, method="zip")
            return SimpleNamespace(congressional_district="VA-08", method="census")

    monkeypatch.setattr(enrichment, "CongressionalDistrictResolver", FakeResolver)

    result = enrichment.resolve_congressional_districts(
        [
            {
                "Company": "Acme Co",
                "Zip": "22102-1234",
                "State": "VA",
                "City": "McLean",
                "Address1": "1 Main St",
            },
            {"Company": "Acme Co", "Zip": "99999"},
            {"Company": "No Zip Co", "Zip": ""},
            {"Company": "Broken Co", "Zip": "22222"},
            {"Company": "No Match Co", "Zip": "33333", "State": "VA"},
            {"Company": "  ", "Zip": "11111"},
        ]
    )

    assert result == {"ACME CO": "VA-08"}
    assert [call["zip_code"] for call in calls] == ["22102", "22222", "33333"]
    assert calls[0] == {
        "address": "1 Main St",
        "city": "McLean",
        "state": "VA",
        "zip_code": "22102",
    }


def test_map_naics_to_bea_sectors_selects_highest_weight_and_continues(monkeypatch, capsys):
    low_weight = SimpleNamespace(allocation_weight=0.25, bea_sector_name="Low weight")
    high_weight = SimpleNamespace(allocation_weight=0.75, bea_sector_name="High weight")

    class FakeMapper:
        def __init__(self, *, crosswalk_path, fallback_config_path):
            assert crosswalk_path is None
            assert fallback_config_path == "config/fiscal/naics_bea_mappings.yaml"

        def map_naics_to_bea(self, code):
            if code == "broken":
                raise ValueError("invalid NAICS")
            if code == "unmapped":
                return []
            return [low_weight, high_weight]

    monkeypatch.setattr(enrichment, "NAICSToBEAMapper", FakeMapper)

    result = enrichment.map_naics_to_bea_sectors(["541715", "unmapped", "broken"])

    assert result == {"541715": "High weight"}
    assert "mapping failed for 1 codes: ['broken']" in capsys.readouterr().err


def test_map_naics_to_bea_sectors_returns_empty_when_mapper_init_fails(monkeypatch):
    debug = Mock()
    monkeypatch.setattr(
        enrichment,
        "NAICSToBEAMapper",
        Mock(side_effect=RuntimeError("mapping config missing")),
    )
    monkeypatch.setattr(enrichment, "_debug", debug)

    assert enrichment.map_naics_to_bea_sectors(["541715"]) == {}
    debug.assert_called_once_with("NAICSToBEAMapper init error: mapping config missing")
