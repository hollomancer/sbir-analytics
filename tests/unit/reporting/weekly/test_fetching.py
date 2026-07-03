"""Unit tests for sbir_etl.reporting.weekly.fetching (spec T1.2)."""

from sbir_etl.reporting.weekly.fetching import _company_key, clean_and_dedup_awards


VALID_AWARD = {
    "Company": "Acme  Innovations Inc.",
    "Award Title": "Advanced Materials",
    "Agency": "Department of Defense",
    "Phase": "Phase I",
    "Program": "SBIR",
    "Contract": "FA8650-23-C-0001",
    "Proposal Award Date": "2026-03-15",
    # DuckDB-loaded records carry numeric types (df.to_dict("records"))
    "Award Year": 2026,
    "Award Amount": 150000.0,
    "PI Name": "Jane   Q  Doe",
    "Contact Name": "John  Smith",
}


class TestCompanyKey:
    def test_prefers_normalized_company(self):
        assert _company_key({"_normalized_company": "acme", "Company": "ACME Inc"}) == "acme"

    def test_falls_back_to_uppercased_raw_name(self):
        assert _company_key({"Company": " Acme Inc "}) == "ACME INC"

    def test_empty_award(self):
        assert _company_key({}) == ""


class TestCleanAndDedupAwards:
    def test_valid_award_kept_and_normalized(self):
        cleaned, stats = clean_and_dedup_awards([dict(VALID_AWARD)])
        assert stats["input"] == 1
        assert stats["output"] == 1
        award = cleaned[0]
        # Normalized company key added for downstream grouping
        assert award["_normalized_company"]
        # Multi-space collapse in name fields
        assert award["PI Name"] == "Jane Q Doe"
        assert award["Contact Name"] == "John Smith"

    def test_invalid_award_dropped_and_counted(self):
        invalid = {"Company": "", "Award Title": ""}  # fails required-field validation
        cleaned, stats = clean_and_dedup_awards([dict(VALID_AWARD), invalid])
        assert stats["input"] == 2
        assert stats["validation_errors"] >= 1
        assert stats["output"] == len(cleaned) == 1

    def test_empty_input(self):
        cleaned, stats = clean_and_dedup_awards([])
        assert cleaned == []
        assert stats["input"] == stats["output"] == 0
