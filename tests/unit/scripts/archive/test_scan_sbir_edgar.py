import json
from pathlib import Path

import pytest

from scripts.archive.data import scan_sbir_edgar
from scripts.archive.data.scan_sbir_edgar import _prepare_checkpoint, _ServerErrorTracker


def _checkpoint_rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_prepare_checkpoint_fresh_run_truncates_existing_output(tmp_path: Path) -> None:
    checkpoint = tmp_path / "scan.jsonl"
    checkpoint.write_text('{"company_name": "stale"}\n')

    done = _prepare_checkpoint(
        checkpoint,
        requested_names={"Acme Labs"},
        resume=False,
        rescan_errors=False,
    )

    assert done == set()
    assert checkpoint.read_text() == ""


def test_prepare_checkpoint_resume_compacts_to_best_row_per_company(tmp_path: Path) -> None:
    checkpoint = tmp_path / "scan.jsonl"
    rows = [
        {"company_name": "Acme Labs", "attempt": "clean", "mention_count": 1},
        {"company_name": "Beta Inc", "attempt": 1, "error": "timeout"},
        {"company_name": "Acme Labs", "attempt": "retry", "had_server_errors": True},
        {"company_name": "Beta Inc", "attempt": 2, "document_fetch_errors": True},
        {"company_name": "Gamma LLC", "attempt": 1},
        {"company_name": "Gamma LLC", "attempt": 2},
        {"company_name": "Delta Corp", "attempt": "retry", "error": "timeout"},
        {"company_name": "Delta Corp", "attempt": "clean", "mention_count": 2},
    ]
    checkpoint.write_text(
        "".join(f"{json.dumps(row)}\n" for row in rows) + '["not", "a", "record"]\n{',
    )

    done = _prepare_checkpoint(
        checkpoint,
        requested_names={"Acme Labs", "Beta Inc"},
        resume=True,
        rescan_errors=False,
    )

    compacted = {row["company_name"]: row for row in _checkpoint_rows(checkpoint)}
    assert done == {"Acme Labs", "Beta Inc"}
    assert set(compacted) == {"Acme Labs", "Beta Inc", "Gamma LLC", "Delta Corp"}
    assert compacted["Acme Labs"]["attempt"] == "clean"
    assert compacted["Beta Inc"]["attempt"] == 2
    assert compacted["Gamma LLC"]["attempt"] == 2
    assert compacted["Delta Corp"]["attempt"] == "clean"
    assert checkpoint.read_text().endswith("\n")


def test_prepare_checkpoint_rescan_removes_requested_retryable_rows(tmp_path: Path) -> None:
    checkpoint = tmp_path / "scan.jsonl"
    rows = [
        {"company_name": "server", "had_server_errors": True},
        {"company_name": "document", "document_fetch_errors": True},
        {"company_name": "context", "context_classification_complete": False},
        {"company_name": "legacy-context", "mention_types": ["filing_mention"]},
        {"company_name": "exception", "error": "boom"},
        {"company_name": "clean", "context_classification_complete": True},
        {"company_name": "legacy-clean", "mention_types": []},
        {"company_name": "outside-limit", "error": "preserve for a later run"},
    ]
    checkpoint.write_text("".join(f"{json.dumps(row)}\n" for row in rows))

    done = _prepare_checkpoint(
        checkpoint,
        requested_names={
            "server",
            "document",
            "context",
            "legacy-context",
            "exception",
            "clean",
            "legacy-clean",
        },
        resume=False,
        rescan_errors=True,
    )

    assert done == {"clean", "legacy-clean"}
    assert _checkpoint_rows(checkpoint) == [
        {"company_name": "clean", "context_classification_complete": True},
        {"company_name": "legacy-clean", "mention_types": []},
        {"company_name": "outside-limit", "error": "preserve for a later run"},
    ]


def test_prepare_checkpoint_rescan_replacement_is_idempotent(tmp_path: Path) -> None:
    checkpoint = tmp_path / "scan.jsonl"
    checkpoint.write_text('{"company_name": "Acme Labs", "error": "timeout"}\n')
    requested_names = {"Acme Labs"}

    done = _prepare_checkpoint(
        checkpoint,
        requested_names=requested_names,
        resume=False,
        rescan_errors=True,
    )
    assert done == set()

    with checkpoint.open("a") as out:
        out.write('{"company_name": "Acme Labs", "mention_count": 1}\n')

    done = _prepare_checkpoint(
        checkpoint,
        requested_names=requested_names,
        resume=False,
        rescan_errors=True,
    )

    assert done == {"Acme Labs"}
    assert _checkpoint_rows(checkpoint) == [{"company_name": "Acme Labs", "mention_count": 1}]


def test_prepare_checkpoint_replace_failure_preserves_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = tmp_path / "scan.jsonl"
    original = b'{"company_name": "Acme Labs"}\n{"company_name": "Acme Labs"}\n'
    checkpoint.write_bytes(original)

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError(f"cannot replace {source} with {destination}")

    monkeypatch.setattr(scan_sbir_edgar.os, "replace", fail_replace)

    with pytest.raises(OSError, match="cannot replace"):
        _prepare_checkpoint(
            checkpoint,
            requested_names={"Acme Labs"},
            resume=True,
            rescan_errors=False,
        )

    assert checkpoint.read_bytes() == original
    assert list(tmp_path.glob(".scan.jsonl.*.tmp")) == []


def test_request_error_tracker_marks_rate_limited_company() -> None:
    tracker = _ServerErrorTracker()
    tracker.register("Acme Labs")

    tracker.write("EDGAR filing mention search failed for 'Acme Labs': 429 Too Many Requests")

    assert tracker.had_error("Acme Labs")


def test_request_error_tracker_ignores_unrelated_warning() -> None:
    tracker = _ServerErrorTracker()
    tracker.register("Acme Labs")

    tracker.write("A warning unrelated to an EFTS request")

    assert not tracker.had_error("Acme Labs")


def test_request_error_tracker_uses_exact_active_company_name() -> None:
    tracker = _ServerErrorTracker()
    tracker.register("Acme")
    tracker.register("Acme Labs")

    tracker.write("EDGAR filing mention search failed for 'Acme Labs': HTTP 500")

    assert not tracker.had_error("Acme")
    assert tracker.had_error("Acme Labs")


def test_request_error_tracker_stops_at_first_closing_quote() -> None:
    tracker = _ServerErrorTracker()
    tracker.register("Acme Labs")

    tracker.write("EDGAR filing mention search failed for 'Acme Labs': later quoted 'detail': 500")

    assert tracker.had_error("Acme Labs")
