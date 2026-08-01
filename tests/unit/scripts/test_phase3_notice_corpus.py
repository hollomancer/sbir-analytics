"""Offline fixture tests for the notice-corpus recovery scripts."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from scripts.phase3_benchmark.build_notice_corpus import (
    build_corpus,
    frame_hash,
    load_filtered_notices,
)
from scripts.phase3_benchmark.pull_gsa_archive import (
    KEEP_COLUMNS,
    normalize_key,
    pull_fiscal_year,
    row_matches,
)


pytestmark = pytest.mark.fast


_ARCHIVE_CSV = (
    '"NoticeId","Title","Sol#","Department/Ind.Agency","Sub-Tier","Office","PostedDate",'
    '"Type","BaseType","NaicsCode","ClassificationCode","AwardNumber","AwardDate","Awardee",'
    '"Link","Description"\n'
    # Row 1: award-number match to N00014-20-C-0055 (firm ACME, office NAVAIR).
    '"n1","Sole source","SOL-1","NAVY","ONR","NAVAIR","2021-03-01","Justification",'
    '"Justification","541715","AC13","N00014-20-C-0055","2021-03-01","ACME",'
    '"http://x","J&A: this SBIR Phase III continues work under N00014-20-C-0055 on autonomous sensing."\n'
    # Row 2: award-number match to N00014-21-C-9999 (firm OTHER, same office NAVAIR)
    # — a diff-firm same-office recovered notice, i.e. ACME's hard negative.
    '"n2","Radar buy","SOL-2","NAVY","ONR","NAVAIR","2021-04-01","Award Notice",'
    '"Award Notice","541715","AC13","N00014-21-C-9999","2021-04-01","OTHER",'
    '"http://y","SBIR Phase III radar signal processing under N00014-21-C-9999."\n'
    # Row 3: text-citation match (no key column, cites in description).
    '"n3","Follow-on","SOL-3","ARMY","","RDECOM","2022-01-01","Presolicitation",'
    '"Presolicitation","541712","AC12","","","ARMYCO",'
    '"http://z","This SBIR effort extends award W911NF19C0100 for counter-uas sensing."\n'
    # Row 4: no match at all — dropped.
    '"n4","Furniture","SOL-4","GSA","","FAS","2022-02-01","Award Notice",'
    '"Award Notice","337214","","GS00F1234","2022-02-01","DESKCO","http://q","Office chairs."\n'
)

_JOIN_KEYS = frozenset(
    {
        normalize_key("N00014-20-C-0055"),
        normalize_key("N00014-21-C-9999"),
        normalize_key("W911NF19C0100"),
    }
)


def test_row_matches_recognizes_each_join_rule():
    reader = list(pd.read_csv(io.StringIO(_ARCHIVE_CSV)).fillna("").to_dict("records"))
    assert row_matches(reader[0], _JOIN_KEYS) == "award_number"
    assert row_matches(reader[1], _JOIN_KEYS) == "award_number"
    assert row_matches(reader[2], _JOIN_KEYS) == "text_citation"
    # A non-SBIR notice with no key match is dropped.
    assert row_matches(reader[3], _JOIN_KEYS) is None


def test_text_citation_requires_sbir_context():
    # Same PIID substring but no "sbir" in the description -> not a text match
    # (the cheap gate that keeps the normalized scan from firing on every row).
    row = {"AwardNumber": "", "Sol#": "", "Description": "Extends award W911NF19C0100 for radar."}
    assert row_matches(row, _JOIN_KEYS) is None


def test_pull_fiscal_year_streams_filters_and_manifests(tmp_path):
    def _opener(_url: str) -> io.StringIO:
        return io.StringIO(_ARCHIVE_CSV)

    entry = pull_fiscal_year(2021, _JOIN_KEYS, tmp_path, opener=_opener)  # type: ignore[arg-type]

    assert entry["rows_scanned"] == 4
    assert entry["rows_kept"] == 3  # two award_number + one text_citation
    frame = pd.read_parquet(tmp_path / "FY2021_filtered.parquet")
    assert set(frame.columns) == {*KEEP_COLUMNS, "match_rule"}
    assert set(frame["match_rule"]) == {"award_number", "text_citation"}


def _write_filtered(tmp_path):
    def _opener(_url: str) -> io.StringIO:
        return io.StringIO(_ARCHIVE_CSV)

    pull_fiscal_year(2021, _JOIN_KEYS, tmp_path, opener=_opener)  # type: ignore[arg-type]
    return load_filtered_notices(tmp_path)


def test_build_corpus_links_notice_and_builds_hard_negatives(tmp_path):
    notices = _write_filtered(tmp_path)
    seed = pd.DataFrame(
        [
            {
                "piid_key": normalize_key("N00014-20-C-0055"),
                "firm": "ACME",
                "label_channel": "coded",
            },
            {
                "piid_key": normalize_key("N00014-21-C-9999"),
                "firm": "OTHER",
                "label_channel": "description",
            },
        ]
    )
    abstracts = pd.DataFrame(
        [
            {
                "uei": "ACME",
                "firm": "ACME",
                "abstract": "Autonomous sensing for maritime platforms.",
            },
            {"uei": "OTHER", "firm": "OTHER", "abstract": "Radar signal processing chains."},
        ]
    )

    corpus = build_corpus(seed, notices, abstracts)

    acme = corpus.loc[(corpus["firm_uei"] == "ACME") & (corpus["label"] == 1)].iloc[0]
    assert acme["notice_id"] == "n1"
    assert "continues work under" in acme["notice_text"]
    assert acme["id_cited"] == 1  # the J&A cites ACME's award PIID
    assert acme["label_channel"] == "coded"

    # ACME's hard negative is OTHER's same-office (NAVAIR) recovered notice.
    acme_negatives = corpus.loc[(corpus["owner"] == acme["owner"]) & (corpus["label"] == 0)]
    assert list(acme_negatives["notice_id"]) == ["n2"]
    # And the negative carries ACME's query abstract against OTHER's notice text.
    assert acme_negatives.iloc[0]["query_abstract"] == acme["query_abstract"]
    assert "radar signal processing" in acme_negatives.iloc[0]["notice_text"].lower()


def test_build_corpus_skips_firms_without_an_abstract(tmp_path):
    notices = _write_filtered(tmp_path)
    seed = pd.DataFrame(
        [{"piid_key": normalize_key("N00014-20-C-0055"), "firm": "ACME", "label_channel": "coded"}]
    )
    assert build_corpus(seed, notices, pd.DataFrame(columns=["uei", "firm", "abstract"])).empty


def test_frame_hash_is_order_independent(tmp_path):
    notices = _write_filtered(tmp_path)
    seed = pd.DataFrame(
        [{"piid_key": normalize_key("N00014-20-C-0055"), "firm": "ACME", "label_channel": "coded"}]
    )
    abstracts = pd.DataFrame([{"uei": "ACME", "firm": "ACME", "abstract": "Autonomous sensing."}])
    corpus = build_corpus(seed, notices, abstracts)
    assert frame_hash(corpus) == frame_hash(corpus.iloc[::-1].reset_index(drop=True))
