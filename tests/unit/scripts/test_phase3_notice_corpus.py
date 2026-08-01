"""Offline fixture tests for the firm-attribution notice-corpus recovery."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from scripts.phase3_benchmark.build_notice_corpus import (
    build_corpus,
    frame_hash,
    load_filtered_notices,
)
from scripts.phase3_benchmark.notice_matching import (
    attribute_notice,
    build_firm_keys,
    normalize_firm_name,
)
from scripts.phase3_benchmark.pull_gsa_archive import KEEP_COLUMNS, pull_fiscal_year


pytestmark = pytest.mark.fast


# Two firms whose full names are distinctive; one shares an office with the other.
_FIRMS = build_firm_keys(
    [
        {"firm": "Charles River Analytics, Inc.", "piids": ["N0001420C0055"]},
        {"firm": "MZA Associates Corporation", "piids": []},
        # A firm whose only token is generic — must NOT match on the token alone.
        {"firm": "Technology Service Corp", "piids": []},
    ]
)


def test_attribution_is_full_name_not_token():
    # Distinctive full name in the description attributes.
    assert attribute_notice(
        "This SBIR effort continues Charles River Analytics work.", "", _FIRMS
    ) == (
        "Charles River Analytics, Inc.",
        "name_in_desc",
    )
    # A generic token ("service") must not attribute to Technology Service Corp.
    assert attribute_notice("SBIR support services for the fleet.", "", _FIRMS) is None
    # Awardee-field name beats description.
    assert attribute_notice("SBIR award.", "MZA ASSOCIATES CORPORATION", _FIRMS) == (
        "MZA Associates Corporation",
        "name_in_awardee",
    )
    # PIID citation is dispositive.
    assert attribute_notice("SBIR III under N00014-20-C-0055.", "", _FIRMS) == (
        "Charles River Analytics, Inc.",
        "piid_cite",
    )


_ARCHIVE_CSV = (
    '"NoticeId","Title","Sol#","Department/Ind.Agency","Sub-Tier","Office","PostedDate",'
    '"Type","BaseType","NaicsCode","ClassificationCode","AwardNumber","AwardDate","Awardee",'
    '"Link","Description"\n'
    '"n1","x","S1","NAVY","ONR","NAVAIR","2021-03-01","Special Notice","Special Notice",'
    '"541715","AC13","","","","http://x",'
    '"SBIR Phase III sole source to Charles River Analytics for autonomous sensing."\n'
    '"n2","y","S2","NAVY","ONR","NAVAIR","2021-04-01","Award Notice","Award Notice",'
    '"541715","AC13","","","","http://y","Routine furniture buy, no research content."\n'
)


def test_pull_gates_on_sbir_and_attributes(tmp_path):
    def opener(_url: str) -> io.StringIO:
        return io.StringIO(_ARCHIVE_CSV)

    entry = pull_fiscal_year(2021, _FIRMS, tmp_path, opener=opener)  # type: ignore[arg-type]

    assert entry["rows_scanned"] == 2
    assert entry["sbir_notices"] == 1  # only n1 mentions SBIR
    assert entry["rows_kept"] == 1
    frame = pd.read_parquet(tmp_path / "FY2021_filtered.parquet")
    assert set(frame.columns) == {*KEEP_COLUMNS, "firm", "match_rule"}
    assert frame.iloc[0]["firm"] == "Charles River Analytics, Inc."


def _seed() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "firm": "Charles River Analytics, Inc.",
                "name_key": normalize_firm_name("Charles River Analytics, Inc."),
                "abstract": "A" * 80,
                "label_channel": "coded",
            },
            {
                "firm": "MZA Associates Corporation",
                "name_key": normalize_firm_name("MZA Associates Corporation"),
                "abstract": "B" * 80,
                "label_channel": "description",
            },
        ]
    )


def _notices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                **dict.fromkeys(KEEP_COLUMNS, ""),
                "NoticeId": "n1",
                "Office": "NAVAIR",
                "Sub-Tier": "ONR",
                "BaseType": "Justification and Approval (J&A)",
                "Description": "CRA J&A text",
                "firm": "Charles River Analytics, Inc.",
                "match_rule": "name_in_desc",
            },
            {
                **dict.fromkeys(KEEP_COLUMNS, ""),
                "NoticeId": "n2",
                "Office": "NAVAIR",
                "Sub-Tier": "ONR",
                "BaseType": "Award Notice",
                "Description": "MZA solicitation text",
                "firm": "MZA Associates Corporation",
                "match_rule": "name_in_awardee",
            },
        ]
    )


def test_build_corpus_pairs_abstract_with_notice_and_same_office_negative():
    corpus = build_corpus(_notices(), _seed())

    cra = corpus.loc[(corpus["firm_name"].str.startswith("Charles")) & (corpus["label"] == 1)].iloc[
        0
    ]
    assert cra["notice_id"] == "n1"
    assert cra["query_abstract"] == "A" * 80
    assert cra["label_channel"] == "coded"
    # MZA's same-office notice is CRA's hard negative, carrying CRA's abstract.
    negatives = corpus.loc[(corpus["owner"] == cra["owner"]) & (corpus["label"] == 0)]
    assert list(negatives["notice_id"]) == ["n2"]
    assert negatives.iloc[0]["query_abstract"] == "A" * 80
    assert "MZA solicitation" in negatives.iloc[0]["notice_text"]


def test_high_precision_filter_drops_generic_name_in_desc():
    # A non-J&A solicitation attributed only by name-in-description is dropped by
    # default (the contaminated rule); an awardee/J&A attribution is kept.
    notices = _notices().copy()
    notices.loc[len(notices)] = {
        **dict.fromkeys(KEEP_COLUMNS, ""),
        "NoticeId": "n3",
        "Office": "RDECOM",
        "Sub-Tier": "ARMY",
        "BaseType": "Solicitation",
        "Description": "generic SBIR BAA",
        "firm": "MZA Associates Corporation",
        "match_rule": "name_in_desc",
    }
    default = build_corpus(notices, _seed())
    kept = build_corpus(notices, _seed(), high_precision_only=False)
    assert "n3" not in set(default.loc[default["label"] == 1, "notice_id"])
    assert "n3" in set(kept.loc[kept["label"] == 1, "notice_id"])


def test_build_corpus_skips_firms_without_abstract():
    seed = _seed().assign(abstract=["", ""])  # no usable abstracts
    assert build_corpus(_notices(), seed).empty


def test_frame_hash_is_order_independent():
    corpus = build_corpus(_notices(), _seed())
    assert frame_hash(corpus) == frame_hash(corpus.iloc[::-1].reset_index(drop=True))


def test_load_filtered_notices_empty_dir(tmp_path):
    assert load_filtered_notices(tmp_path).empty
