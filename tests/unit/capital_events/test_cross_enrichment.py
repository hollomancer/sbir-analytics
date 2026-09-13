"""Tests for provenance-aware Form D/M&A cross-enrichment."""

from sbir_etl.capital_events.cross_enrichment import (
    enrich_form_d_and_ma,
    evidence_sources,
    independent_source_count,
    is_independent_of_form_d,
    relationship_source_classes,
)


def _offering(accession: str, date: str, *, combination: bool = False, amount: float = 0):
    return {
        "accession_number": accession,
        "cik": "0000123",
        "filing_date": date,
        "total_amount_sold": amount,
        "is_business_combination": combination,
        "is_amendment": False,
    }


def _form_d_record(
    name: str,
    offerings: list[dict[str, object]],
    *,
    cik: str = "0000123",
    tier: str = "high",
):
    return {
        "company_name": name,
        "form_d_cik": cik,
        "match_confidence": {"tier": tier},
        "offerings": offerings,
    }


def test_form_d_only_composite_does_not_claim_independent_corroboration():
    form_d = [
        _form_d_record(
            "Acme, Inc.",
            [
                _offering("ACC-COMBO", "2020-01-15", combination=True, amount=5_000_000),
                _offering("ACC-AFTER", "2021-03-01", amount=2_000_000),
            ],
        ),
        _form_d_record(
            "Giant Co",
            [_offering("GIANT-AFTER", "2022-01-01", amount=7_000_000)],
            cik="0000999",
        ),
    ]
    ma = [
        {
            "company_name": "ACME INC",
            "event_date": "2020-02-01",
            "acquirer": "Giant Co",
            "confidence": "high",
            "signals": {"form_d_business_combination": True},
            "form_d_detail": {"filing_date": "2020-01-15"},
            "efts_detail": None,
        }
    ]

    enriched, relationships, crosswalk = enrich_form_d_and_ma(form_d, ma)
    provenance = enriched[0]["cross_enrichment"]
    assert provenance["same_source_only"] is True
    assert provenance["independent_of_form_d"] is False
    assert provenance["source_class_count"] == 1
    assert provenance["independent_source_count"] == 0
    assert provenance["form_d_accession_numbers"] == ["ACC-COMBO"]
    assert provenance["post_event_target_form_d_raw_filing_count"] == 1
    assert provenance["acquirer_form_d_accession_numbers"] == ["GIANT-AFTER"]
    assert provenance["candidate_status"] == "unvalidated_public_record_candidate"
    assert provenance["legal_event_validated"] is False
    assert provenance["deal_terms_captured"] is False
    assert provenance["enterprise_value_observed"] is False
    assert (
        provenance["form_d_amount_sold_measure"]
        == "business_combination_associated_exempt_securities_sold"
    )
    assert provenance["form_d_amount_sold_is_deal_value"] is False
    assert provenance["acquirer_alias_candidate"]["auto_merge"] is False
    assert relationships[0]["relationship_type"] == "candidate_acquired_by"
    assert relationships[0]["legal_event_validated"] is False
    linked = next(row for row in crosswalk if row["accession_number"] == "ACC-COMBO")
    assert linked["evidence_role"] == "originating_evidence"
    assert linked["confidence_credit"] is False
    assert linked["legal_event_validated"] is False
    assert linked["match_tier"] == "high"


def test_independent_efts_event_can_be_corroborated_by_form_d():
    form_d = [
        _form_d_record(
            "Beta Labs LLC",
            [_offering("BETA-COMBO", "2023-01-01", combination=True)],
            cik="456",
        )
    ]
    ma = [
        {
            "company_name": "BETA LABS",
            "event_date": "2023-03-01",
            "acquirer": "Buyer Inc",
            "confidence": "medium",
            "signals": {"efts_acquisition_text": True},
            "efts_detail": {"mention_types": ["acquisition"]},
            "form_d_detail": None,
        }
    ]

    enriched, _, crosswalk = enrich_form_d_and_ma(form_d, ma)
    provenance = enriched[0]["cross_enrichment"]
    assert provenance["evidence_sources"] == ["efts"]
    assert provenance["independent_of_form_d"] is True
    assert provenance["source_class_count"] == 1
    assert provenance["independent_source_count"] == 1
    linked = next(row for row in crosswalk if row["accession_number"] == "BETA-COMBO")
    assert linked["evidence_role"] == "independent_corroboration"
    assert linked["confidence_credit"] is True
    assert linked["match_tier"] == "high"


def test_source_classification_uses_underlying_evidence_not_composite_row():
    form_d_only = {
        "signals": {"form_d_business_combination": True},
        "form_d_detail": {"filing_date": "2020-01-01"},
    }
    both = {
        **form_d_only,
        "efts_detail": {"mention_types": ["subsidiary"]},
    }
    assert evidence_sources(form_d_only) == ["form_d"]
    assert is_independent_of_form_d(form_d_only) is False
    assert evidence_sources(both) == ["efts", "form_d"]
    assert is_independent_of_form_d(both) is True


def test_discovery_confirmed_signal_is_independent_evidence():
    inserted = {
        "company_name": "Gamma Co",
        "event_date": "2021-06-01",
        "confidence": "medium",
        "signals": {"discovery_confirmed": True},
        "source": "https://news.example/deal",
        "evidence": "Buyer Inc acquired Gamma Co",
    }
    assert evidence_sources(inserted) == ["discovery"]
    assert is_independent_of_form_d(inserted) is True
    enriched, _, _ = enrich_form_d_and_ma([], [inserted])
    provenance = enriched[0]["cross_enrichment"]
    assert provenance["evidence_sources"] == ["discovery"]
    assert provenance["independent_of_form_d"] is True
    assert provenance["independent_source_count"] == 1


def test_raw_press_hits_are_not_independent_corroboration():
    form_d_plus_hits = {
        "signals": {"form_d_business_combination": True},
        "form_d_detail": {"filing_date": "2020-01-01"},
        "press_wire_signals": [
            {"title": "Unrelated hit", "link": "https://example.com", "source": "PRNewswire"}
        ],
    }
    assert evidence_sources(form_d_plus_hits) == ["form_d"]
    assert is_independent_of_form_d(form_d_plus_hits) is False
    hits_only = {"press_wire_signals": form_d_plus_hits["press_wire_signals"]}
    assert evidence_sources(hits_only) == []
    assert is_independent_of_form_d(hits_only) is False
    extract_token = {"source": "form_d", "evidence": "business combination offering"}
    assert evidence_sources(extract_token) == []


def test_unlinked_form_d_combination_is_preserved_for_review():
    form_d = [
        _form_d_record(
            "No Match LLC",
            [_offering("UNLINKED", "2018-01-01", combination=True)],
            cik="777",
        )
    ]
    _, relationships, crosswalk = enrich_form_d_and_ma(form_d, [])
    assert relationships == []
    assert crosswalk == [
        {
            "accession_number": "UNLINKED",
            "form_d_cik": "123",
            "target_name": "No Match LLC",
            "relationship_id": None,
            "acquirer_name": None,
            "link_status": "unlinked",
            "legal_event_validated": False,
            "evidence_role": "form_d_only",
            "confidence_credit": False,
            "match_tier": "high",
            "date_distance_days": None,
        }
    ]


def test_low_tier_form_d_combination_is_not_linked():
    form_d = [
        _form_d_record(
            "3D Control Systems, Inc.",
            [_offering("LOW-COMBO", "2020-06-01", combination=True)],
            tier="low",
        )
    ]
    ma = [
        {
            "company_name": "3D Control Systems, Inc.",
            "event_date": "2020-06-15",
            "acquirer": None,
            "confidence": "high",
            "signals": {"efts_acquisition_text": True},
            "efts_detail": {"mention_types": ["acquisition"]},
            "form_d_detail": None,
        }
    ]
    _, _, crosswalk = enrich_form_d_and_ma(form_d, ma)
    assert crosswalk == []


def test_originating_form_d_links_by_filing_not_composite_event_date():
    form_d = [
        _form_d_record(
            "Acme, Inc.",
            [
                _offering("ORIG-2013", "2013-04-01", combination=True),
                _offering("NEAR-EFTS", "2026-01-10", combination=True),
            ],
        )
    ]
    ma = [
        {
            "company_name": "ACME INC",
            "event_date": "2026-01-15",
            "acquirer": "Buyer Inc",
            "confidence": "high",
            "signals": {
                "form_d_business_combination": True,
                "efts_acquisition_text": True,
            },
            "form_d_detail": {
                "filing_date": "2013-04-01",
                "accession_number": "ORIG-2013",
            },
            "efts_detail": {
                "mention_types": ["acquisition"],
                "latest_mention_date": "2026-01-15",
            },
        }
    ]
    enriched, _, crosswalk = enrich_form_d_and_ma(form_d, ma)
    provenance = enriched[0]["cross_enrichment"]
    assert provenance["form_d_accession_numbers"] == ["ORIG-2013"]
    linked = {row["accession_number"]: row for row in crosswalk if row["link_status"] == "linked"}
    assert set(linked) == {"ORIG-2013"}
    assert linked["ORIG-2013"]["evidence_role"] == "originating_evidence"
    assert linked["ORIG-2013"]["confidence_credit"] is False
    unlinked = next(row for row in crosswalk if row["accession_number"] == "NEAR-EFTS")
    assert unlinked["link_status"] == "unlinked"
    assert unlinked["evidence_role"] != "originating_evidence"


def test_same_date_other_accession_is_not_originating_when_accession_is_known():
    form_d = [
        _form_d_record(
            "Acme, Inc.",
            [
                _offering("ORIG-2013", "2013-04-01", combination=True),
                _offering("OTHER-2013", "2013-04-01", combination=True),
            ],
        )
    ]
    ma = [
        {
            "company_name": "ACME INC",
            "event_date": "2026-01-15",
            "acquirer": None,
            "confidence": "high",
            "signals": {"form_d_business_combination": True},
            "form_d_detail": {
                "filing_date": "2013-04-01",
                "accession_number": "ORIG-2013",
            },
        }
    ]
    _, _, crosswalk = enrich_form_d_and_ma(form_d, ma)
    linked = {row["accession_number"]: row for row in crosswalk if row["link_status"] == "linked"}
    assert set(linked) == {"ORIG-2013"}
    other = next(row for row in crosswalk if row["accession_number"] == "OTHER-2013")
    assert other["link_status"] == "unlinked"


def test_empty_accession_is_not_written_to_crosswalk():
    form_d = [
        _form_d_record(
            "Blank Accession LLC",
            [_offering("", "2019-01-01", combination=True)],
        )
    ]
    ma = [
        {
            "company_name": "Blank Accession LLC",
            "event_date": "2019-01-15",
            "acquirer": None,
            "confidence": "high",
            "signals": {"form_d_business_combination": True},
            "form_d_detail": {"filing_date": "2019-01-01"},
        }
    ]
    _, _, crosswalk = enrich_form_d_and_ma(form_d, ma)
    assert crosswalk == []


def test_independent_source_count_excludes_form_d():
    assert independent_source_count(["form_d"]) == 0
    assert independent_source_count(["efts", "form_d"]) == 1
    assert independent_source_count(["efts", "press"]) == 2


def test_relationship_source_classes_count_linked_form_d():
    row = {
        "evidence_sources": ["efts"],
        "form_d_accession_numbers": ["ACC-1"],
        "matched_form_d_combination_count": 1,
    }
    assert relationship_source_classes(row) == ["efts", "form_d"]
