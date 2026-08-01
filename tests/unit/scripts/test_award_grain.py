"""Tests for award-grain citation attribution."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.phase3_benchmark.award_grain import (
    attribute_by_citation,
    build_award_index,
    extract_cited_piids,
    normalize_piid,
)


pytestmark = pytest.mark.fast


def test_extract_cited_piids_handles_common_dod_forms():
    text = (
        "SBIR Phase III J&A continuing work under contract N00014-20-C-0055 and "
        "prior award HQ085022C0009; see also FA8650-19-C-1234."
    )
    cited = extract_cited_piids(text)
    assert "N0001420C0055" in cited
    assert "HQ085022C0009" in cited
    assert "FA865019C1234" in cited


def test_extract_ignores_short_or_absent_numbers():
    assert extract_cited_piids("no contract cited here") == set()
    assert extract_cited_piids("topic AF15 only") == set()  # too short
    assert extract_cited_piids(None) == set()


def test_normalize_piid_strips_separators():
    assert normalize_piid("N00014-20-C-0055") == "N0001420C0055"
    assert normalize_piid("hq0850 22 c 0009") == "HQ085022C0009"


def _award_data() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Contract": "N00014-20-C-0055",
                "UEI": "UEI000000001",
                "Company": "Acme Photonics",
                "Abstract": "A" * 80,
            },
            {  # a different, more recent award for the same firm
                "Contract": "N00014-22-C-9000",
                "UEI": "UEI000000001",
                "Company": "Acme Photonics",
                "Abstract": "B" * 80,
            },
            {"Contract": "SHORT", "UEI": "x", "Company": "y", "Abstract": "C" * 80},
            {"Contract": "N00014-21-C-1111", "UEI": "z", "Company": "w", "Abstract": "tiny"},
        ]
    )


def test_build_award_index_keys_by_contract_with_usable_abstract():
    index = build_award_index(_award_data())
    assert "N0001420C0055" in index
    assert index["N0001420C0055"]["company"] == "Acme Photonics"
    assert "SHORT" not in index  # too-short key dropped
    assert "N0001421C1111" not in index  # abstract too short


def test_attribute_resolves_the_specific_cited_award():
    index = build_award_index(_award_data())
    # The notice cites the FIRST award — attribution yields *that* award's abstract,
    # not the firm's other (more recent) award.
    result = attribute_by_citation(
        "SBIR Phase III sole source continuing N00014-20-C-0055 for sensing.", index
    )
    assert result is not None
    piid, award = result
    assert piid == "N0001420C0055"
    assert award["abstract"] == "A" * 80


def test_attribute_returns_none_without_a_resolvable_citation():
    index = build_award_index(_award_data())
    assert attribute_by_citation("SBIR work, no contract number.", index) is None
    assert attribute_by_citation("cites unknown N00014-99-C-0000.", index) is None
