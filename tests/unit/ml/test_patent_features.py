# sbir-etl/tests/unit/ml/test_patent_features.py

import pytest

pytestmark = pytest.mark.fast

from src.ml.features.patent_features import (
    DEFAULT_KEYWORDS_MAP,
    PatentFeatureVector,
    bag_of_keywords_features,
    extract_features,
    extract_ipc_cpc,
    guess_assignee_type,
    normalize_title,
    remove_stopwords,
    tokenize,
)


def test_normalize_title_and_tokenize_basic():
    title = "Machine-Learning: An Approach to Imaging; 2021!"
    norm = normalize_title(title)
    # punctuation removed and lowercased
    assert "machine" in norm
    assert "learning" in norm
    assert ":" not in norm and ";" not in norm and "!" not in norm
    tokens = tokenize(norm)
    # tokens should include words and numbers (2021)
    assert "machine" in tokens
    assert "learning" in tokens
    assert "2021" in tokens


def test_remove_stopwords_filters_defaults_and_single_chars():
    tokens = ["the", "a", "i", "x", "ml", "data", "3"]
    filtered = remove_stopwords(tokens)  # uses DEFAULT_STOPWORDS
    # 'the' and 'a' removed; 'i' single letter removed; 'x' removed (single letter)
    assert "the" not in filtered
    assert "a" not in filtered
    assert "i" not in filtered
    assert "x" not in filtered
    # numeric single char '3' should be kept
    assert "3" in filtered
    assert "data" in filtered
    assert "ml" in filtered


def test_extract_ipc_cpc_from_string_and_mapping():
    # Free-text extraction
    txt = "This invention relates to G06F 17/30 and also mentions H04L."
    found = extract_ipc_cpc(txt)
    # IPC/CPC list should include G06F and H04L (normalized uppercase, unique)
    assert "G06F" in found["ipc"] or "G06F" in found["cpc"]
    assert "H04L" in found["ipc"] or "H04L" in found["cpc"]

    # Mapping with explicit ipc and cpc values (string)
    rec = {"ipc": "G06F 17/30", "cpc": ["H04L 9/00", "G06F 17/30"]}
    m = extract_ipc_cpc(rec)
    assert "G06F" in m["ipc"]
    assert "H04L" in m["cpc"]
    # deduplication preserves single entry once
    assert m["ipc"].count("G06F") == 1


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Acme Technologies, Inc.", "company"),
        ("Massachusetts Institute of Technology", "academic"),
        ("U.S. Department of Energy", "government"),
        ("Jane Doe", "individual"),
        (None, "unknown"),
    ],
)
def test_guess_assignee_type_various(name, expected):
    assert guess_assignee_type(name) == expected


def test_bag_of_keywords_features_counts_and_presence():
    title = "A novel deep learning neural network for image segmentation and machine learning"
    # Use a small custom keywords map
    kms = {"ml": ["machine learning", "deep learning"], "quantum": ["quantum", "qubit"]}
    feats = bag_of_keywords_features(title, keywords_map=kms)
    # ml phrases appear twice (deep learning + machine learning)
    assert feats["ml__presence"] == 1
    assert feats["ml__count"] >= 2
    # quantum absent
    assert feats["quantum__presence"] == 0
    assert feats["quantum__count"] == 0


def test_extract_features_full_record():
    record = {
        "title": "Qubit-based quantum processor with improved coherence",
        "abstract": "We demonstrate a qubit and quantum error correction.",
        "assignee": "National Quantum Lab",
        "ipc": ["G06F 17/30"],
        "cpc": "H04L 9/00",
        "application_year": "2019",
    }
    fv = extract_features(record, keywords_map=DEFAULT_KEYWORDS_MAP)
    assert isinstance(fv, PatentFeatureVector)
    d = fv.as_dict()
    # normalized title lowercased and contains 'quantum'
    assert "quantum" in d["normalized_title"]
    # tokens present
    assert isinstance(d["tokens"], list)
    # assignee type guessed as government (National ... Lab)
    assert d["assignee_type"] in ("government", "company", "academic")
    # IPC/CPC presence flags consistent with codes
    assert d["has_ipc"] is True
    assert d["has_cpc"] is True
    # application year parsed to integer
    assert d["application_year"] == 2019


def test_extract_features_handles_none_record():
    fv = extract_features(None)
    assert isinstance(fv, PatentFeatureVector)
    d = fv.as_dict()
    # defaults: empty normalized title, zero token counts
    assert d["normalized_title"] == ""
    assert d["n_tokens"] == 0
    assert d["n_tokens_no_stopwords"] == 0
    assert d["ipc_codes"] == []
    assert d["cpc_codes"] == []
    assert d["application_year"] is None
