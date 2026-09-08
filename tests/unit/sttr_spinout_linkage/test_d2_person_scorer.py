"""Probes for the D2 person-trail scorer (task 1.3's D2 slice).

Exploratory tier: covers the typed-absence branching the task brief calls out --
no PI/founder name, `generic_token_guard` failure, source-not-queried vs. a real
measured negative -- plus the exact/fuzzy scoring logic and the Form-D
officer/director join. No network calls: source clients are bare fakes
implementing only `.lookup(name)`, matching the mocked-client pattern in
`tests/unit/enrichers/test_openalex_client.py`. Not a comprehensive matrix.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from scripts.sttr_spinout_linkage.d2_person_scorer import (
    founder_names_for_company,
    load_form_d_founder_index,
    score_d2_person_trail,
)
from scripts.sttr_spinout_linkage.kernel import DimensionStatus, SignalAbsentReason
from sbir_etl.exceptions import APIError
from sbir_etl.identity import CompanyNameProfile, normalize_company_name


pytestmark = pytest.mark.fast


# ---------------------------------------------------------------------------
# Fake lookup clients / records -- duck-typed to match OpenAlexRecord /
# PubMedRecord / ORCIDRecord's relevant fields without importing them.
# ---------------------------------------------------------------------------


@dataclass
class _FakeOpenAlexRecord:
    display_name: str
    affiliations: list[str] = field(default_factory=list)


@dataclass
class _FakePubMedRecord:
    author_name: str
    affiliations: list[str] = field(default_factory=list)


@dataclass
class _FakeORCIDRecord:
    given_name: str | None
    family_name: str
    affiliations: list[str] = field(default_factory=list)


class _FakeClient:
    """A bare `.lookup(name)` stand-in; `responses` maps query name -> record|None."""

    def __init__(self, responses: dict[str, object | None]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def lookup(self, name: str) -> object | None:
        self.calls.append(name)
        return self._responses.get(name)


class _RaisingClient:
    def lookup(self, name: str) -> object | None:
        raise APIError("boom", api_name="fake", http_status=500)


RI_NAME = "Massachusetts Institute of Technology"


# ---------------------------------------------------------------------------
# Typed-absence branching
# ---------------------------------------------------------------------------


class TestTypedAbsence:
    def test_no_pi_or_founder_name_is_not_measurable_source_field_unavailable(self) -> None:
        trail = score_d2_person_trail(pi_name=None, founder_names=(), ri_name=RI_NAME)

        assert trail.status is DimensionStatus.NOT_MEASURABLE
        assert trail.reason is SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE
        assert trail.exact_person_ri_affiliation is False

    def test_blank_founder_names_and_blank_pi_is_not_measurable(self) -> None:
        trail = score_d2_person_trail(pi_name="  ", founder_names=("", None), ri_name=RI_NAME)

        assert trail.status is DimensionStatus.NOT_MEASURABLE
        assert trail.reason is SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE

    def test_blank_ri_name_is_not_measurable_source_field_unavailable(self) -> None:
        trail = score_d2_person_trail(pi_name="Jane Smith", ri_name=None)

        assert trail.status is DimensionStatus.NOT_MEASURABLE
        assert trail.reason is SignalAbsentReason.SOURCE_FIELD_UNAVAILABLE

    def test_generic_token_only_name_fails_the_guard(self) -> None:
        trail = score_d2_person_trail(
            pi_name="Dr. Jr.",
            ri_name=RI_NAME,
            openalex=_FakeClient({}),
        )

        assert trail.status is DimensionStatus.NOT_MEASURABLE
        assert trail.reason is SignalAbsentReason.NAME_GENERIC_TOKEN_GUARD_FAILED

    def test_guard_failure_never_silently_falls_through_to_no_signal(self) -> None:
        # A generic-token-only name must not be reported the same as a real
        # "queried and found nothing" measured negative.
        trail = score_d2_person_trail(pi_name="Prof.", ri_name=RI_NAME, openalex=_FakeClient({}))

        assert trail.status is not DimensionStatus.MEASURED
        assert trail.reason is SignalAbsentReason.NAME_GENERIC_TOKEN_GUARD_FAILED

    def test_no_source_clients_configured_is_not_evaluated_source_not_queried(self) -> None:
        trail = score_d2_person_trail(pi_name="Jane Smith", ri_name=RI_NAME)

        assert trail.status is DimensionStatus.NOT_EVALUATED
        assert trail.reason is SignalAbsentReason.SOURCE_NOT_QUERIED
        assert trail.exact_person_ri_affiliation is False

    def test_queried_but_no_ri_affiliated_hit_is_a_real_measured_negative(self) -> None:
        openalex = _FakeClient({"Jane Smith": _FakeOpenAlexRecord(display_name="Jane Smith")})

        trail = score_d2_person_trail(pi_name="Jane Smith", ri_name=RI_NAME, openalex=openalex)

        assert trail.status is DimensionStatus.MEASURED
        assert trail.exact_person_ri_affiliation is False
        assert trail.person_similarity is None
        assert trail.reason is None
        assert openalex.calls == ["Jane Smith"]

    def test_lookup_returning_none_is_still_a_measured_negative(self) -> None:
        openalex = _FakeClient({})  # no match for anything

        trail = score_d2_person_trail(pi_name="Jane Smith", ri_name=RI_NAME, openalex=openalex)

        assert trail.status is DimensionStatus.MEASURED
        assert trail.exact_person_ri_affiliation is False


# ---------------------------------------------------------------------------
# Exact match (Order 1 SPINOUT_T1 input)
# ---------------------------------------------------------------------------


class TestExactMatch:
    def test_exact_identity_and_ri_affiliation_sets_exact_person_ri_affiliation(self) -> None:
        openalex = _FakeClient(
            {
                "Jane Smith": _FakeOpenAlexRecord(
                    display_name="Jane Smith",
                    affiliations=["Massachusetts Institute of Technology"],
                )
            }
        )

        trail = score_d2_person_trail(pi_name="Jane Smith", ri_name=RI_NAME, openalex=openalex)

        assert trail.status is DimensionStatus.MEASURED
        assert trail.exact_person_ri_affiliation is True

    def test_pubmed_author_name_field_used_for_exact_match(self) -> None:
        pubmed = _FakeClient(
            {"Jane Smith": _FakePubMedRecord(author_name="Jane Smith", affiliations=[RI_NAME])}
        )

        trail = score_d2_person_trail(pi_name="Jane Smith", ri_name=RI_NAME, pubmed=pubmed)

        assert trail.exact_person_ri_affiliation is True

    def test_orcid_given_family_name_used_for_exact_match(self) -> None:
        orcid = _FakeClient(
            {
                "Jane Smith": _FakeORCIDRecord(
                    given_name="Jane", family_name="Smith", affiliations=[RI_NAME]
                )
            }
        )

        trail = score_d2_person_trail(pi_name="Jane Smith", ri_name=RI_NAME, orcid=orcid)

        assert trail.exact_person_ri_affiliation is True

    def test_affiliation_not_matching_ri_does_not_count_even_with_exact_name(self) -> None:
        openalex = _FakeClient(
            {
                "Jane Smith": _FakeOpenAlexRecord(
                    display_name="Jane Smith", affiliations=["Some Other University"]
                )
            }
        )

        trail = score_d2_person_trail(pi_name="Jane Smith", ri_name=RI_NAME, openalex=openalex)

        assert trail.exact_person_ri_affiliation is False
        assert trail.person_similarity is None


# ---------------------------------------------------------------------------
# Fuzzy match (feeds person_similarity / person_guard_passed, not thresholded here)
# ---------------------------------------------------------------------------


class TestFuzzyMatch:
    def test_ri_affiliated_but_name_mismatch_reports_similarity_not_exact(self) -> None:
        # Returned author name is a near-miss of the query name.
        openalex = _FakeClient(
            {"Jane Smith": _FakeOpenAlexRecord(display_name="Jane Smyth", affiliations=[RI_NAME])}
        )

        trail = score_d2_person_trail(pi_name="Jane Smith", ri_name=RI_NAME, openalex=openalex)

        assert trail.status is DimensionStatus.MEASURED
        assert trail.exact_person_ri_affiliation is False
        assert trail.person_similarity is not None
        assert 0.0 < trail.person_similarity < 1.0
        assert trail.person_guard_passed is True

    def test_scorer_does_not_apply_a_cutoff_itself(self) -> None:
        # Even a very low-similarity RI-affiliated hit is reported, not dropped --
        # thresholding is classify_linkage's job (O-3), not this scorer's.
        openalex = _FakeClient(
            {
                "Zephyr Quorlax": _FakeOpenAlexRecord(
                    display_name="Bob Jones", affiliations=[RI_NAME]
                )
            }
        )

        trail = score_d2_person_trail(pi_name="Zephyr Quorlax", ri_name=RI_NAME, openalex=openalex)

        assert trail.person_similarity is not None


# ---------------------------------------------------------------------------
# Founders (O-1) and multi-source / multi-candidate behavior
# ---------------------------------------------------------------------------


class TestFoundersAndMultiSource:
    def test_founder_name_can_supply_the_exact_match_when_pi_does_not(self) -> None:
        openalex = _FakeClient(
            {
                "Alex Founder": _FakeOpenAlexRecord(
                    display_name="Alex Founder", affiliations=[RI_NAME]
                )
            }
        )

        trail = score_d2_person_trail(
            pi_name="Jane Smith",
            founder_names=["Alex Founder"],
            ri_name=RI_NAME,
            openalex=openalex,
        )

        assert trail.exact_person_ri_affiliation is True

    def test_duplicate_normalized_names_are_queried_once(self) -> None:
        openalex = _FakeClient({"Jane Smith": _FakeOpenAlexRecord(display_name="Jane Smith")})

        score_d2_person_trail(
            pi_name="Jane Smith",
            founder_names=["Jane Smith", "jane smith"],
            ri_name=RI_NAME,
            openalex=openalex,
        )

        assert openalex.calls == ["Jane Smith"]

    def test_exact_hit_from_one_source_wins_even_if_another_source_has_no_hit(self) -> None:
        openalex = _FakeClient({"Jane Smith": None})
        pubmed = _FakeClient(
            {"Jane Smith": _FakePubMedRecord(author_name="Jane Smith", affiliations=[RI_NAME])}
        )

        trail = score_d2_person_trail(
            pi_name="Jane Smith", ri_name=RI_NAME, openalex=openalex, pubmed=pubmed
        )

        assert trail.exact_person_ri_affiliation is True

    def test_source_raising_api_error_is_treated_as_no_hit_not_a_crash(self) -> None:
        trail = score_d2_person_trail(
            pi_name="Jane Smith", ri_name=RI_NAME, openalex=_RaisingClient()
        )

        assert trail.status is DimensionStatus.MEASURED
        assert trail.exact_person_ri_affiliation is False


# ---------------------------------------------------------------------------
# Form-D officer/director founder-name join
# ---------------------------------------------------------------------------


FORM_D_LINES = [
    {
        "company_name": "Acme Robotics Inc",
        "match_confidence": {"tier": "high"},
        "offerings": [
            {
                "related_persons": [
                    {"name": "Alex Founder", "title": "Executive Officer, Director"},
                    {"name": "Casey Investor", "title": "Promoter"},
                ]
            },
            {
                "related_persons": [
                    {"name": "Alex Founder", "title": "Director"},
                    {"name": "Dana Board", "title": "Director"},
                ]
            },
        ],
    },
    {
        "company_name": "Low Confidence Co",
        "match_confidence": {"tier": "medium"},
        "offerings": [{"related_persons": [{"name": "Weak Match", "title": "Officer"}]}],
    },
    {
        "company_name": "No Persons Co",
        "match_confidence": {"tier": "high"},
        "offerings": [{"related_persons": []}],
    },
]


def _write_form_d_jsonl(path: Path, records: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return path


class TestFormDFounderIndex:
    def test_loads_deduped_officer_director_names_at_default_high_tier(
        self, tmp_path: Path
    ) -> None:
        path = _write_form_d_jsonl(tmp_path / "form_d.jsonl", FORM_D_LINES)

        index = load_form_d_founder_index(path)

        key = normalize_company_name("Acme Robotics Inc", profile=CompanyNameProfile.FORM_D_JOIN_V1)
        assert index[key] == ["Alex Founder", "Dana Board"]

    def test_excludes_non_officer_director_titles(self, tmp_path: Path) -> None:
        path = _write_form_d_jsonl(tmp_path / "form_d.jsonl", FORM_D_LINES)

        index = load_form_d_founder_index(path)

        key = normalize_company_name("Acme Robotics Inc", profile=CompanyNameProfile.FORM_D_JOIN_V1)
        assert "Casey Investor" not in index[key]

    def test_medium_tier_excluded_by_default(self, tmp_path: Path) -> None:
        path = _write_form_d_jsonl(tmp_path / "form_d.jsonl", FORM_D_LINES)

        index = load_form_d_founder_index(path)

        key = normalize_company_name("Low Confidence Co", profile=CompanyNameProfile.FORM_D_JOIN_V1)
        assert key not in index

    def test_missing_file_returns_empty_index_not_an_error(self, tmp_path: Path) -> None:
        index = load_form_d_founder_index(tmp_path / "does_not_exist.jsonl")

        assert index == {}

    def test_founder_names_for_company_falls_back_to_empty_list(self, tmp_path: Path) -> None:
        path = _write_form_d_jsonl(tmp_path / "form_d.jsonl", FORM_D_LINES)
        index = load_form_d_founder_index(path)

        assert founder_names_for_company("Unknown Firm Inc", index) == []
        assert founder_names_for_company(None, index) == []

    def test_founder_names_for_company_joins_by_name_key(self, tmp_path: Path) -> None:
        path = _write_form_d_jsonl(tmp_path / "form_d.jsonl", FORM_D_LINES)
        index = load_form_d_founder_index(path)

        # FORM_D_JOIN_V1 normalizes case but not punctuation; match on a
        # case-only variant of the stored company name.
        assert founder_names_for_company("acme robotics inc", index) == [
            "Alex Founder",
            "Dana Board",
        ]
