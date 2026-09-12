import json
from pathlib import Path

import pytest

from scripts.archive.data import refine_ma_medium_tier
from scripts.archive.data.refine_ma_medium_tier import (
    _prepare_refinement_checkpoint,
    classify_direction,
    needs_directional_refinement,
    refine_events,
)


def _checkpoint_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _typed_refinement(
    company_name: str,
    direction: str = "target",
    *,
    context_complete: bool = True,
    reasons: list[str] | None = None,
    attempt: int | None = None,
) -> dict:
    record = {
        "company_name": company_name,
        "direction": direction,
        "context_classification_complete": context_complete,
    }
    if reasons is not None:
        record["context_incomplete_reasons"] = reasons
    if attempt is not None:
        record["attempt"] = attempt
    return record


def test_prepare_refinement_checkpoint_fresh_run_atomically_empties_output(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "refined.jsonl"
    checkpoint.write_text(json.dumps(_typed_refinement("stale")) + "\n")

    done = _prepare_refinement_checkpoint(
        checkpoint,
        requested_names={"Alpha"},
        resume=False,
    )

    assert done == set()
    assert checkpoint.read_text() == ""


def test_prepare_refinement_checkpoint_drops_legacy_and_invalid_rows_for_retry(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "refined.jsonl"
    rows = [
        {"company_name": "legacy", "direction": "target"},
        _typed_refinement("wrong-direction", direction="unknown"),
        _typed_refinement(
            "invalid-incomplete",
            direction="target",
            context_complete=False,
            reasons=["document_fetch_failed"],
        ),
        _typed_refinement("complete"),
        _typed_refinement(
            "completed-unknown",
            direction="context_incomplete",
            context_complete=False,
            reasons=["document_fetch_failed"],
        ),
    ]
    checkpoint.write_text("".join(f"{json.dumps(row)}\n" for row in rows))

    requested = {str(row["company_name"]) for row in rows}
    done = _prepare_refinement_checkpoint(
        checkpoint,
        requested_names=requested,
        resume=True,
    )

    assert done == {"complete", "completed-unknown"}
    assert _checkpoint_rows(checkpoint) == rows[-2:]


def test_prepare_refinement_checkpoint_compacts_to_latest_valid_duplicate(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "refined.jsonl"
    rows = [
        _typed_refinement("Alpha", direction="target", attempt=1),
        _typed_refinement("Beta", direction="ambiguous", attempt=1),
        _typed_refinement("Alpha", direction="comparator", attempt=2),
    ]
    checkpoint.write_text("".join(f"{json.dumps(row)}\n" for row in rows))

    done = _prepare_refinement_checkpoint(
        checkpoint,
        requested_names={"Alpha", "Beta"},
        resume=True,
    )

    compacted = {row["company_name"]: row for row in _checkpoint_rows(checkpoint)}
    assert done == {"Alpha", "Beta"}
    assert len(compacted) == 2
    assert compacted["Alpha"]["attempt"] == 2
    assert compacted["Beta"]["attempt"] == 1


def test_prepare_refinement_checkpoint_heals_malformed_tail(tmp_path: Path) -> None:
    checkpoint = tmp_path / "refined.jsonl"
    checkpoint.write_text(json.dumps(_typed_refinement("Alpha")) + "\n{")

    done = _prepare_refinement_checkpoint(
        checkpoint,
        requested_names={"Alpha", "truncated"},
        resume=True,
    )

    assert done == {"Alpha"}
    assert _checkpoint_rows(checkpoint) == [_typed_refinement("Alpha")]
    assert checkpoint.read_text().endswith("\n")


def test_prepare_refinement_checkpoint_replace_failure_preserves_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = tmp_path / "refined.jsonl"
    original = b'{"company_name":"legacy","direction":"target"}\n'
    checkpoint.write_bytes(original)

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError(f"cannot replace {source} with {destination}")

    monkeypatch.setattr(refine_ma_medium_tier.os, "replace", fail_replace)

    with pytest.raises(OSError, match="cannot replace"):
        _prepare_refinement_checkpoint(
            checkpoint,
            requested_names={"legacy"},
            resume=True,
        )

    assert checkpoint.read_bytes() == original
    assert list(tmp_path.glob(".refined.jsonl.*.tmp")) == []


@pytest.mark.parametrize(
    ("confidence", "signals", "expected"),
    [
        ("medium", {"efts_acquisition_text": True}, True),
        ("low", {"efts_acquisition_text": True}, True),
        ("low", {"efts_ma_definitive": True}, True),
        (
            "medium",
            {"efts_acquisition_text": True, "form_d_business_combination": True},
            False,
        ),
        ("medium", {}, False),
    ],
)
def test_directional_refinement_selection_uses_signals_not_current_tier(
    confidence: str, signals: dict[str, bool], expected: bool
) -> None:
    event = {"confidence": confidence, "signals": signals}

    assert needs_directional_refinement(event) is expected


@pytest.mark.parametrize(
    "text",
    [
        "Globex Corporation acquired ACME Inc. for $40 million.",
        "Globex completed the acquisition of ACME Inc.",
        "ACME Inc. was acquired by Globex Corporation.",
        "ACME Inc. is a wholly-owned subsidiary of Globex Corporation.",
    ],
)
def test_direction_classifier_retains_anchored_target_phrasings(text: str) -> None:
    assert classify_direction(text, "ACME Inc.") == "target"


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (
            "The acquisition of Beta LLC closed. ACME Inc. served as financial advisor.",
            "verb belongs to a different deal",
        ),
        ("Globex acquired Beta LLC from ACME Inc.", "company is the seller"),
        ("Following its acquisition of Beta LLC, ACME Inc. expanded.", "company is the buyer"),
        ("ACME Inc. acquires Beta LLC.", "active voice names the buyer"),
        (
            "ACME Inc. acquired three businesses. Its portfolio companies now include Beta.",
            "portfolio language names the parent",
        ),
        (
            "Our segments are comprised of the following. ACME Inc. is discussed below.",
            "list boilerplate is not ownership",
        ),
        (
            "ACME Inc. and Globex Corporation entered into a merger agreement.",
            "merger boilerplate names both sides",
        ),
    ],
)
def test_direction_classifier_never_promotes_acquirer_seller_or_noise(
    text: str, reason: str
) -> None:
    assert classify_direction(text, "ACME Inc.") != "target", reason


def test_direction_classifier_preserves_demotion_rules() -> None:
    assert (
        classify_direction(
            "ACME Inc. acquired an exclusive license from Globex Corporation.",
            "ACME Inc.",
        )
        == "not_target"
    )
    assert (
        classify_direction(
            "Comparable companies include ACME Inc. and three industry peers.",
            "ACME Inc.",
        )
        == "comparator"
    )


class _IncompleteReferenceClient:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.incomplete_calls = 0
        self.fetch_calls = 0
        self.context_incomplete_callback = self._mark_incomplete

    def _mark_incomplete(self) -> None:
        self.incomplete_calls += 1

    async def search_filing_mentions(self, company_name: str, **kwargs):
        if self.mode == "search_error":
            raise RuntimeError("search failed")
        if self.mode == "malformed":
            return [{"doc_id": "malformed", "filer_cik": "12345"}]
        if self.mode == "incomplete":
            return [{"doc_id": ":doc.htm", "filer_cik": "12345"}]
        return [{"doc_id": "0000012345-20-000001:doc.htm", "filer_cik": "12345"}]

    async def fetch_filing_document(
        self, cik: str, accession: str, filename: str, *, raise_on_error: bool = False
    ):
        self.fetch_calls += 1
        if self.mode == "fetch_error":
            raise RuntimeError("fetch failed")
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_reason", "expected_fetches"),
    [
        ("malformed", "malformed_document_reference", 0),
        ("incomplete", "incomplete_document_reference", 0),
        ("search_error", "mention_search_failed", 0),
        ("fetch_error", "document_fetch_failed", 1),
        ("empty_document", "empty_document", 1),
    ],
)
async def test_directional_refinement_marks_incomplete_context(
    tmp_path, mode: str, expected_reason: str, expected_fetches: int
) -> None:
    client = _IncompleteReferenceClient(mode)
    output = tmp_path / "refined.jsonl"

    await refine_events(
        [{"company_name": "Alpha", "confidence": "medium"}],
        client,
        output,
        set(),
        concurrency=1,
    )

    row = json.loads(output.read_text())
    assert row["direction"] == "context_incomplete"
    assert row["context_classification_complete"] is False
    assert row["context_incomplete_reasons"] == [expected_reason]
    assert client.incomplete_calls == 1
    assert client.fetch_calls == expected_fetches


class _CompleteContextClient:
    def __init__(self, *, text: str | None = None) -> None:
        self.text = text
        self.context_incomplete_callback = None

    async def search_filing_mentions(self, company_name: str, **kwargs):
        if self.text is None:
            return []
        return [{"doc_id": "0000012345-20-000001:doc.htm", "filer_cik": "12345"}]

    async def fetch_filing_document(
        self, cik: str, accession: str, filename: str, *, raise_on_error: bool = False
    ):
        return self.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected_direction"),
    [
        (None, "no_filing"),
        ("Buyer acquired Alpha in 2020.", "target"),
        ("Alpha is mentioned without acquisition context.", "ambiguous"),
    ],
)
async def test_directional_refinement_records_complete_context(
    tmp_path, text: str | None, expected_direction: str
) -> None:
    output = tmp_path / "refined.jsonl"

    await refine_events(
        [{"company_name": "Alpha", "confidence": "medium"}],
        _CompleteContextClient(text=text),
        output,
        set(),
        concurrency=1,
    )

    row = json.loads(output.read_text())
    assert row["direction"] == expected_direction
    assert row["context_classification_complete"] is True
    assert "context_incomplete_reasons" not in row
