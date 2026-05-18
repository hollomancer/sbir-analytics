"""Tests for the CA-organized cohort filter."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from ucc.cohort_state_filter import (  # noqa: E402
    generate_name_variants,
    is_ca_organized,
    lookup_ca_sos_with_variants,
    narrow_to_ca_organized,
    pick_best_match,
)


def test_ca_organized_when_california_domestic():
    record = {"FORMED_IN": "CALIFORNIA", "ENTITY_TYPE": "Stock Corporation - CA - Stock"}
    assert is_ca_organized(record) is True


def test_ca_organized_when_california_llc():
    record = {"FORMED_IN": "CALIFORNIA", "ENTITY_TYPE": "Limited Liability Company"}
    assert is_ca_organized(record) is True


def test_not_ca_organized_when_foreign_in_ca():
    record = {"FORMED_IN": "CALIFORNIA", "ENTITY_TYPE": "Stock Corporation - Out of State - Stock"}
    assert is_ca_organized(record) is False


def test_not_ca_organized_when_formed_in_delaware():
    record = {"FORMED_IN": "DELAWARE", "ENTITY_TYPE": "Stock Corporation - Out of State - Stock"}
    assert is_ca_organized(record) is False


def test_not_ca_organized_when_record_none():
    assert is_ca_organized(None) is False


def test_not_ca_organized_when_record_empty():
    assert is_ca_organized({}) is False


def test_pick_best_match_prefers_active_status():
    rows = {
        "1": {"STATUS": "Terminated", "FORMED_IN": "CALIFORNIA"},
        "2": {"STATUS": "Active", "FORMED_IN": "CALIFORNIA"},
    }
    best = pick_best_match(rows)
    assert best["STATUS"] == "Active"


def test_pick_best_match_returns_none_for_empty():
    assert pick_best_match({}) is None


def test_pick_best_match_returns_first_active_then_first_overall():
    rows = {
        "1": {"STATUS": "Terminated", "SORT_INDEX": 1, "FORMED_IN": "CALIFORNIA"},
        "2": {"STATUS": "Terminated", "SORT_INDEX": 0, "FORMED_IN": "CALIFORNIA"},
    }
    # No Active — should return SORT_INDEX 0
    best = pick_best_match(rows)
    assert best["SORT_INDEX"] == 0


def test_narrow_to_ca_organized_keeps_ca_drops_de():
    cohort = [
        {"company_name": "CA Co", "state": "CA"},
        {"company_name": "DE Co", "state": "CA"},
        {"company_name": "No Match Co", "state": "TX"},
    ]
    lookups = iter(
        [
            {"FORMED_IN": "CALIFORNIA", "ENTITY_TYPE": "Limited Liability Company"},
            {"FORMED_IN": "DELAWARE", "ENTITY_TYPE": "Stock Corporation - Out of State - Stock"},
            None,
        ]
    )
    fn = MagicMock(side_effect=lambda name: next(lookups))

    kept, lookups_done = narrow_to_ca_organized(cohort, lookup_fn=fn, delay_seconds=0)
    assert [r["company_name"] for r in kept] == ["CA Co"]
    assert lookups_done == 3


def test_generate_name_variants_strips_suffix():
    variants = generate_name_variants("Acme Tech, Inc.")
    assert "Acme Tech, Inc." in variants
    assert "Acme Tech" in variants
    assert "Acme Tech HOLDING" in variants


def test_generate_name_variants_handles_llc():
    variants = generate_name_variants("AADI, LLC")
    assert "AADI, LLC" in variants
    assert "AADI" in variants


def test_generate_name_variants_includes_first_word_for_long_names():
    variants = generate_name_variants("Pacific Biosciences of California, Inc.")
    assert "Pacific" in variants


def test_generate_name_variants_skips_too_short_first_word_for_long_names():
    """For a multi-word firm name, the first-word heuristic should not add
    short tokens like 'AI' (would match tons of unrelated entities).

    Note: when the suffix-strip itself yields a short core (e.g., "AI" from
    "AI, Inc."), that's a legitimate variant and we keep it — different rule.
    """
    variants = generate_name_variants("AI Research Industries Inc")
    # "AI" is too short to be added via the first-word rule
    assert "AI" not in variants
    # But the stripped core "AI Research Industries" should be there
    assert "AI Research Industries" in variants


def test_generate_name_variants_keeps_digit_first_word():
    variants = generate_name_variants("3D Systems Corporation")
    # "3D" has a digit so it should be included even though length < 4
    assert "3D" in variants


def test_generate_name_variants_dedupes():
    """If suffix strip yields the same as original, no dupes in the output."""
    variants = generate_name_variants("Acme Industries")
    # No entity suffix, so original == stripped
    # But HOLDING and first-word may still add — check no exact dupes
    assert len(variants) == len({v.lower() for v in variants})


def test_generate_name_variants_returns_empty_for_blank():
    assert generate_name_variants("") == []
    assert generate_name_variants(None) == []


def test_lookup_with_variants_returns_first_match():
    """Variant retry: first call (original) → empty; second call (stripped) → hit."""
    from unittest.mock import MagicMock

    class FakeResp:
        def __init__(self, rows):
            self._rows = rows
            self.status_code = 200

        def json(self):
            return {"rows": self._rows}

        def raise_for_status(self):
            pass

    client = MagicMock()
    # First call (original "23ANDME, INC.") returns no rows
    # Second call (stripped "23ANDME") returns a hit
    client.post.side_effect = [
        FakeResp({}),
        FakeResp(
            {
                "123": {
                    "SORT_INDEX": 0,
                    "FORMED_IN": "DELAWARE",
                    "ENTITY_TYPE": "Stock Corporation - Out of State",
                    "STATUS": "Active",
                }
            }
        ),
    ]
    rec, variant = lookup_ca_sos_with_variants("23ANDME, INC.", client=client)
    assert rec is not None
    assert rec["FORMED_IN"] == "DELAWARE"
    assert variant == "23ANDME"  # the stripped variant
    assert client.post.call_count == 2


def test_lookup_with_variants_returns_none_when_all_variants_fail():
    from unittest.mock import MagicMock

    class FakeResp:
        status_code = 200

        def json(self):
            return {"rows": {}}

        def raise_for_status(self):
            pass

    client = MagicMock()
    client.post.return_value = FakeResp()
    rec, variant = lookup_ca_sos_with_variants("UnknownCorp, Inc.", client=client)
    assert rec is None
    assert variant is None
    assert client.post.call_count >= 2  # at least original + one variant tried


def test_narrow_to_ca_organized_skips_checkpointed(tmp_path):
    cohort = [
        {"company_name": "CA Co", "state": "CA"},
        {"company_name": "Skip Me", "state": "CA"},
    ]
    checkpoint = tmp_path / "ckpt.jsonl"
    # Pre-populate checkpoint with "Skip Me" as CA-organized
    import json

    checkpoint.write_text(
        json.dumps(
            {
                "company_name": "Skip Me",
                "is_ca_organized": True,
                "business_record": {"FORMED_IN": "CALIFORNIA", "ENTITY_TYPE": "LLC"},
            }
        )
        + "\n"
    )

    lookups = iter(
        [
            {"FORMED_IN": "CALIFORNIA", "ENTITY_TYPE": "LLC"},
        ]
    )
    fn = MagicMock(side_effect=lambda name: next(lookups))

    kept, lookups_done = narrow_to_ca_organized(
        cohort,
        lookup_fn=fn,
        delay_seconds=0,
        checkpoint_path=checkpoint,
    )
    names = [r["company_name"] for r in kept]
    assert "CA Co" in names
    assert "Skip Me" in names  # restored from checkpoint
    assert lookups_done == 1  # only CA Co triggered a lookup


def test_narrow_to_ca_organized_retries_errored_checkpoint_entries(tmp_path):
    """Checkpoint rows with a non-null error are retried on resume rather than
    treated as confirmed non-CA-organized. Prevents silent under-counting when
    an Imperva block trips the extractor mid-run.
    """
    import json

    cohort = [{"company_name": "Retry Me", "state": "CA"}]
    checkpoint = tmp_path / "ckpt.jsonl"
    # Pre-populate checkpoint with an error row (is_ca_organized=False, error set)
    checkpoint.write_text(
        json.dumps(
            {
                "company_name": "Retry Me",
                "is_ca_organized": False,
                "business_record": None,
                "error": "RequestsError: 403",
            }
        )
        + "\n"
    )

    # On retry, the lookup succeeds and returns a CA-organized record
    lookups = iter([{"FORMED_IN": "CALIFORNIA", "ENTITY_TYPE": "LLC"}])
    fn = MagicMock(side_effect=lambda name: next(lookups))

    kept, lookups_done = narrow_to_ca_organized(
        cohort,
        lookup_fn=fn,
        delay_seconds=0,
        checkpoint_path=checkpoint,
    )
    assert [r["company_name"] for r in kept] == ["Retry Me"]
    assert lookups_done == 1  # retried, not skipped
