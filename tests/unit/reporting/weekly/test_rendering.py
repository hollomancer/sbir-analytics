"""Unit tests for sbir_etl.reporting.weekly.rendering (spec T1.1)."""

from sbir_etl.reporting.weekly.rendering import (
    SBIR_AWARD_SEARCH_URL,
    _escape_md_cell,
    _format_date,
    build_sbir_award_url,
    build_solicitation_url,
    build_usaspending_url,
    format_amount,
    generate_markdown,
)


class TestEscapeMdCell:
    def test_escapes_pipes_and_newlines(self):
        assert _escape_md_cell("a|b\nc\rd") == "a\\|b cd"

    def test_plain_text_unchanged(self):
        assert _escape_md_cell("Acme Inc.") == "Acme Inc."


class TestFormatAmount:
    def test_millions(self):
        assert format_amount("1500000") == "$1.50M"

    def test_thousands(self):
        assert format_amount("150000") == "$150K"

    def test_small_amounts(self):
        assert format_amount("999") == "$999"

    def test_strips_currency_formatting(self):
        assert format_amount("$1,000,000") == "$1.00M"

    def test_unparseable_returned_verbatim(self):
        assert format_amount("TBD") == "TBD"

    def test_empty_is_na(self):
        assert format_amount("") == "N/A"


class TestFormatDate:
    def test_iso_passthrough(self):
        assert _format_date("2026-03-15") == "2026-03-15"

    def test_empty_value(self):
        assert _format_date("") == ""

    def test_unparseable_returned_as_string(self):
        assert _format_date("not-a-date") == "not-a-date"


class TestBuildUrls:
    def test_award_url_prefers_contract(self):
        url = build_sbir_award_url({"Contract": "FA8650-23-C-0001", "Company": "Acme"})
        assert url == f"{SBIR_AWARD_SEARCH_URL}?keyword=FA8650-23-C-0001"

    def test_award_url_falls_back_to_company(self):
        url = build_sbir_award_url({"Company": "Acme Inc"})
        assert url == f"{SBIR_AWARD_SEARCH_URL}?keyword=Acme%20Inc"

    def test_award_url_base_when_nothing(self):
        assert build_sbir_award_url({}) == SBIR_AWARD_SEARCH_URL

    def test_solicitation_url_prefers_solicitation_number(self):
        url = build_solicitation_url({"Solicitation Number": "SBIR-23.1", "Topic Code": "AF1"})
        assert url is not None and "SBIR-23.1" in url

    def test_solicitation_url_topic_fallback_and_none(self):
        assert build_solicitation_url({"Topic Code": "AF231-001"}) is not None
        assert build_solicitation_url({}) is None

    def test_usaspending_url_requires_contract(self):
        assert build_usaspending_url({}) is None
        url = build_usaspending_url({"Contract": "W911NF-23-C-0001"})
        assert url is not None and "W911NF-23-C-0001" in url


class TestGenerateMarkdown:
    AWARD = {
        "Company": "Acme Inc",
        "Award Title": "Widget Research",
        "Agency": "DOD",
        "Program": "SBIR",
        "Phase": "Phase I",
        "Award Amount": "150000",
        "State": "VA",
        "Contract": "C-1",
        "Proposal Award Date": "2026-03-15",
        "PI Name": "Jane Doe",
    }

    def test_empty_awards_short_report(self):
        report = generate_markdown([], days=7)
        assert "No new awards found for this period." in report
        assert "**Total new awards:** 0" in report

    def test_report_contains_award_and_summary(self):
        report = generate_markdown([self.AWARD], days=7)
        assert "### 1. Widget Research" in report
        assert "| Total Awards | 1 |" in report
        assert "**References:**" in report

    def test_freshness_warnings_rendered(self):
        report = generate_markdown([], days=7, freshness_warnings=["stale data"])
        assert "> - stale data" in report

    def test_diligence_sections_keyed_by_normalized_name(self):
        report = generate_markdown(
            [self.AWARD],
            days=7,
            company_diligence={"acme": "Solid firm."},
            pi_diligence={"JANE DOE": "Prolific PI."},
        )
        assert "**Company Diligence — Acme Inc:**" in report
        assert "**Principal Investigator — Jane Doe:**" in report
