import importlib.util
from pathlib import Path

import pandas as pd

from sbir_etl.exceptions import RateLimitError


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "data" / "hydrate_candidate_opportunity_descriptions.py"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "hydrate_candidate_opportunity_descriptions", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_script()


def test_hydrates_title_fallback_once_and_preserves_substantive_text():
    opportunities = pd.DataFrame(
        [
            {
                "notice_id": "O-1",
                "title": "Autonomy integration",
                "description": "Autonomy integration",
                "description_url": "https://api.sam.gov/descriptions/O-1",
                "content_hash": "old-hash-1",
            },
            {
                "notice_id": "O-2",
                "title": "Sensor prototype",
                "description": "Integrate a multispectral sensor onto the target platform.",
                "description_url": "https://api.sam.gov/descriptions/O-2",
                "content_hash": "old-hash-2",
            },
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "target_id": "O-1",
                "candidate_score": 0.82,
                "is_high_confidence": True,
            },
            {
                "target_id": "O-1",
                "candidate_score": 0.60,
                "is_high_confidence": False,
            },
            {
                "target_id": "O-2",
                "candidate_score": 0.90,
                "is_high_confidence": True,
            },
        ]
    )
    requested = []

    def fetch(url):
        requested.append(url)
        return "Integrate autonomous navigation and obstacle sensing into a ground vehicle."

    hydrated, stats = mod.hydrate_candidate_descriptions(
        opportunities, candidates, fetch, max_records=10
    )

    assert requested == ["https://api.sam.gov/descriptions/O-1"]
    assert hydrated.loc[0, "description"].startswith("Integrate autonomous navigation")
    assert hydrated.loc[0, "description_source"] == "sam.gov description endpoint"
    assert hydrated.loc[0, "description_retrieved_at"]
    assert hydrated.loc[0, "content_hash"] == "old-hash-1"
    assert len(hydrated.loc[0, "description_content_hash"]) == 64
    assert hydrated.loc[1, "description"] == opportunities.loc[1, "description"]
    assert stats == {
        "candidate_targets": 2,
        "pre_screen_targets": 0,
        "selected_targets": 2,
        "already_substantive": 1,
        "fetch_attempts": 1,
        "hydrated": 1,
        "missing_opportunity": 0,
        "missing_description_url": 0,
        "empty_response": 0,
        "api_failures": 0,
        "rate_limited": 0,
        "cap_reached": 0,
    }


def test_prioritizes_high_confidence_and_honors_fetch_cap():
    opportunities = pd.DataFrame(
        [
            {
                "notice_id": "LOW",
                "title": "Low-priority title",
                "description": pd.NA,
                "description_url": "https://api.sam.gov/descriptions/LOW",
            },
            {
                "notice_id": "HIGH",
                "title": "High-priority title",
                "description": "High-priority title",
                "description_url": "https://api.sam.gov/descriptions/HIGH",
            },
        ]
    )
    candidates = pd.DataFrame(
        [
            {"target_id": "LOW", "candidate_score": 0.99, "is_high_confidence": False},
            {"target_id": "HIGH", "candidate_score": 0.75, "is_high_confidence": True},
        ]
    )
    requested = []

    def fetch(url):
        requested.append(url)
        return "Substantive description returned by SAM.gov."

    hydrated, stats = mod.hydrate_candidate_descriptions(
        opportunities, candidates, fetch, max_records=1
    )

    assert requested == ["https://api.sam.gov/descriptions/HIGH"]
    assert hydrated.loc[1, "description"] == "Substantive description returned by SAM.gov."
    assert pd.isna(hydrated.loc[0, "description"])
    assert stats["fetch_attempts"] == 1
    assert stats["hydrated"] == 1


def test_pre_screen_hydrates_description_dependent_match_without_candidate():
    awards = pd.DataFrame(
        [
            {
                "award_id": "A-1",
                "agency": "DEPARTMENT OF THE ARMY",
                "branch": "ARMY",
                "uei": "EXAMPLEUEI",
                "naics_code": None,
                "psc_code": None,
            }
        ]
    )
    opportunities = pd.DataFrame(
        [
            {
                "notice_id": "HIDDEN",
                "notice_type_code": "o",
                "active": True,
                "agency": "DEPARTMENT OF THE ARMY",
                "title": "Prototype integration",
                "description": "Prototype integration",
                "description_url": "https://api.sam.gov/descriptions/HIDDEN",
            },
            {
                "notice_id": "OTHER",
                "notice_type_code": "o",
                "active": True,
                "agency": "DEPARTMENT OF THE NAVY",
                "title": "Other prototype",
                "description": "Other prototype",
                "description_url": "https://api.sam.gov/descriptions/OTHER",
            },
            {
                "notice_id": "EXPIRED",
                "notice_type_code": "o",
                "active": True,
                "response_deadline": "2020-01-01",
                "agency": "DEPARTMENT OF THE ARMY",
                "title": "Expired prototype",
                "description": "Expired prototype",
                "description_url": "https://api.sam.gov/descriptions/EXPIRED",
            },
            {
                "notice_id": "UNKNOWN",
                "notice_type_code": "x",
                "active": True,
                "agency": "DEPARTMENT OF THE ARMY",
                "title": "Unsupported notice",
                "description": "Unsupported notice",
                "description_url": "https://api.sam.gov/descriptions/UNKNOWN",
            },
        ]
    )
    requested = []

    def fetch(url):
        requested.append(url)
        return "Continuation of autonomous Army logistics work under a new prototype effort."

    hydrated, stats = mod.hydrate_candidate_descriptions(
        opportunities,
        pd.DataFrame(),
        fetch,
        awards=awards,
        max_records=10,
    )

    assert requested == ["https://api.sam.gov/descriptions/HIDDEN"]
    assert hydrated.loc[0, "description"].startswith("Continuation of autonomous")
    assert hydrated.loc[1, "description"] == "Other prototype"
    assert hydrated.loc[2, "description"] == "Expired prototype"
    assert hydrated.loc[3, "description"] == "Unsupported notice"
    assert stats["candidate_targets"] == 0
    assert stats["pre_screen_targets"] == 1


def test_rate_limit_keeps_partial_output_and_records_stop():
    opportunities = pd.DataFrame(
        [
            {
                "notice_id": "O-1",
                "title": "Prototype",
                "description": "Prototype",
                "description_url": "https://api.sam.gov/descriptions/O-1",
            }
        ]
    )
    candidates = pd.DataFrame(
        [{"target_id": "O-1", "candidate_score": 0.8, "is_high_confidence": True}]
    )

    def fetch(_url):
        raise RateLimitError("quota exhausted", api_name="sam.gov")

    hydrated, stats = mod.hydrate_candidate_descriptions(
        opportunities, candidates, fetch, max_records=10
    )

    assert hydrated.loc[0, "description"] == "Prototype"
    assert stats["rate_limited"] == 1
    assert stats["hydrated"] == 0
