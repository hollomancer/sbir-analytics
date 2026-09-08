"""Tests for the exploratory M&A discovery sample-run CLI helpers."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest
import yaml

from sbir_etl.enrichers.ma_discovery.extractor import ExtractionVerdict

from scripts.data.run_ma_discovery_sample import (
    RecordingSearchTool,
    _TimedExtractor,
    bound_queries,
    build_review_queue,
    check_run_manifest,
    drop_recorded_queries,
    gate_failures,
    is_live_capture,
    live_capture_errors,
    load_cut_protocol,
    load_recorded_queries,
    main,
    precision_from_labels,
    protocol_pin_errors,
    should_fail_on_gate,
    strict_medium_high_n,
)


pytestmark = pytest.mark.fast


def test_review_queue_keeps_medium_discovery_rows_only() -> None:
    queue = build_review_queue(
        [
            {
                "company_name": "A",
                "acquirer": "B",
                "confidence": "medium",
                "signals": {"discovery_confirmed": True},
                "source": "https://example.com/a",
                "evidence": "B acquired A.",
            },
            {
                "company_name": "C",
                "acquirer": "D",
                "confidence": "high",
                "signals": {"discovery_confirmed": True},
            },
            {
                "company_name": "E",
                "acquirer": "F",
                "confidence": "medium",
                "signals": {},
            },
        ],
        limit=20,
    )
    assert len(queue) == 1
    assert queue[0]["review_outcome"] == "unreviewed"
    assert queue[0]["company_name"] == "A"


def test_bound_queries_caps_pairs_and_templates() -> None:
    rows = [
        {"company_name": "A", "acquirer": "B", "query": "q1"},
        {"company_name": "A", "acquirer": "B", "query": "q2"},
        {"company_name": "A", "acquirer": "B", "query": "q3"},
        {"company_name": "C", "acquirer": "D", "query": "q4"},
        {"company_name": "E", "acquirer": "F", "query": "q5"},
    ]
    kept = bound_queries(rows, max_candidates=2, queries_per_pair=1)
    assert [(r["company_name"], r["query"]) for r in kept] == [("A", "q1"), ("C", "q4")]


def test_bound_queries_skips_leading_pairs() -> None:
    rows = [
        {"company_name": "A", "acquirer": "B", "query": "q1"},
        {"company_name": "C", "acquirer": "D", "query": "q2"},
        {"company_name": "E", "acquirer": "F", "query": "q3"},
    ]
    kept = bound_queries(rows, max_candidates=1, queries_per_pair=1, skip_pairs=1)
    assert [(r["company_name"], r["query"]) for r in kept] == [("C", "q2")]


def test_drop_recorded_queries_skips_frozen_strings() -> None:
    rows = [
        {"company_name": "A", "acquirer": "B", "query": "q1"},
        {"company_name": "C", "acquirer": "D", "query": "q2"},
    ]
    kept = drop_recorded_queries(rows, {"q1"})
    assert [r["query"] for r in kept] == ["q2"]


@pytest.mark.asyncio
async def test_recording_search_tool_checkpoints_each_query(tmp_path) -> None:
    path = tmp_path / "snippets.jsonl"

    class _Inner:
        async def search(self, query: str) -> list[dict[str, str]]:
            return [{"snippet": "hit", "link": f"http://example.com/{query}"}]

    sink: list[dict[str, object]] = []
    tool = RecordingSearchTool(_Inner(), sink, path=path)
    await tool.search("q1")
    await tool.search("q2")
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["query"] for row in lines] == ["q1", "q2"]
    assert sink == lines


def test_load_recorded_queries_reads_jsonl(tmp_path) -> None:
    path = tmp_path / "snippets.jsonl"
    path.write_text(
        '{"query": "q1", "snippet": "s", "link": "http://a"}\n'
        '{"query": "q1", "snippet": "t", "link": "http://b"}\n'
        '{"query": "q2", "snippet": "", "link": null}\n',
        encoding="utf-8",
    )
    assert load_recorded_queries(path) == {"q1", "q2"}
    assert load_recorded_queries(tmp_path / "missing.jsonl") == set()


def test_strict_medium_high_excludes_already_medium_pairs() -> None:
    events = [
        {"company_name": "GINER INC", "acquirer": "ENER1 INC", "confidence": "medium"},
        {"company_name": "SDL Inc", "acquirer": "JDS UNIPHASE CORP /CA/", "confidence": "low"},
    ]
    mutated = [
        {"company_name": "GINER INC", "acquirer": "ENER1 INC", "confidence": "medium"},
        {"company_name": "SDL Inc", "acquirer": "JDS UNIPHASE CORP /CA/", "confidence": "medium"},
    ]
    assert strict_medium_high_n(events, mutated) == 1


def test_check_run_manifest_detects_mismatch(tmp_path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text("{}\n", encoding="utf-8")
    snippets = tmp_path / "sn.jsonl"
    snippets.write_text("{}\n", encoding="utf-8")
    manifest = tmp_path / "run-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "inputs": {
                    "events": {"sha256": "0" * 64},
                    "snippets": {"sha256": hashlib.sha256(snippets.read_bytes()).hexdigest()},
                }
            }
        ),
        encoding="utf-8",
    )
    errors = check_run_manifest(manifest, events=events, snippets=snippets, llm=None)
    assert any("events SHA mismatch" in e for e in errors)
    assert not any("snippets SHA mismatch" in e for e in errors)


_EVENTS_SHA = "a" * 64


def _protocol_payload(**overrides: object) -> dict:
    payload: dict = {
        "protocol_id": "held-out-1501",
        "protocol_md": "notes/cut.md",
        "skip_pairs": 1500,
        "max_candidates": 1000,
        "queries_per_pair": 1,
        "stop_when": "dated_confirm",
        "strict_recall": True,
        "fail_on_gate": True,
        "confirm": "llm",
        "search_backend_capture": "brave",
        "search_backend_rerun": "snippets",
        "events_path": "data/sbir_ma_events.jsonl",
        "events_sha256": _EVENTS_SHA,
        "output_dir": "data/processed/ma_discovery_heldout_1501",
        "intended_rank": "validated",
        "recall_floor": 10,
        "precision_fp_cap": 0.25,
        "cost_per_pair_cap_usd": 0.10,
    }
    payload.update(overrides)
    return payload


def _write_protocol(root: Path, payload: dict | None = None) -> Path:
    notes = root / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    md = notes / "cut.md"
    md.write_text("# cut\n", encoding="utf-8")
    path = notes / "cut.yaml"
    path.write_text(
        yaml.safe_dump(_protocol_payload() if payload is None else payload), encoding="utf-8"
    )
    return path


def test_is_live_capture_only_for_brave_tavily_or_llm() -> None:
    assert is_live_capture(search_backend="brave", capture_llm=False)
    assert is_live_capture(search_backend="tavily", capture_llm=False)
    assert is_live_capture(search_backend="snippets", capture_llm=True)
    assert not is_live_capture(search_backend="snippets", capture_llm=False)
    assert not is_live_capture(search_backend="mock", capture_llm=False)
    assert not is_live_capture(search_backend="none", capture_llm=False)
    assert not is_live_capture(search_backend=None, capture_llm=False)


def test_live_capture_refused_without_protocol() -> None:
    errors = live_capture_errors(search_backend="brave", capture_llm=False, protocol=None)
    assert any("hashed in HEAD" in e for e in errors)


def test_live_capture_backend_must_match_protocol(tmp_path: Path) -> None:
    protocol = load_cut_protocol(_write_protocol(tmp_path))
    errors = live_capture_errors(search_backend="tavily", capture_llm=True, protocol=protocol)
    assert any("does not match protocol" in e for e in errors)
    assert live_capture_errors(search_backend="brave", capture_llm=True, protocol=protocol) == []


def test_load_cut_protocol_rejects_unknown_fields(tmp_path: Path) -> None:
    path = _write_protocol(tmp_path, _protocol_payload(extra_field="nope"))
    with pytest.raises(ValueError, match="unknown fields"):
        load_cut_protocol(path)


def test_protocol_pin_errors_require_head_and_study_hash(tmp_path: Path) -> None:
    protocol_path = _write_protocol(tmp_path)
    protocol = load_cut_protocol(protocol_path)
    md = tmp_path / protocol.protocol_md
    yaml_bytes = protocol_path.read_bytes()
    md_bytes = md.read_bytes()
    study = tmp_path / "study.yaml"
    study.write_text(
        yaml.safe_dump(
            {
                "frozen_artifacts": [
                    {
                        "path": "notes/cut.yaml",
                        "sha256": hashlib.sha256(yaml_bytes).hexdigest(),
                    },
                    {
                        "path": "notes/cut.md",
                        "sha256": hashlib.sha256(md_bytes).hexdigest(),
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    head = {"notes/cut.yaml": yaml_bytes, "notes/cut.md": md_bytes}
    assert (
        protocol_pin_errors(
            protocol,
            protocol_path,
            repository_root=tmp_path,
            study_yaml=study,
            head_blob=head.get,
        )
        == []
    )
    missing_head = protocol_pin_errors(
        protocol,
        protocol_path,
        repository_root=tmp_path,
        study_yaml=study,
        head_blob=lambda _rel: None,
    )
    assert any("protocol not in HEAD: notes/cut.yaml" in e for e in missing_head)
    drifted = protocol_pin_errors(
        protocol,
        protocol_path,
        repository_root=tmp_path,
        study_yaml=study,
        head_blob=lambda rel: b"stale" if rel.endswith(".yaml") else head.get(rel),
    )
    assert any("differs from HEAD: notes/cut.yaml" in e for e in drifted)


def test_protocol_pin_errors_require_study_yaml_pin(tmp_path: Path) -> None:
    protocol_path = _write_protocol(tmp_path)
    protocol = load_cut_protocol(protocol_path)
    study = tmp_path / "study.yaml"
    study.write_text(yaml.safe_dump({"frozen_artifacts": []}), encoding="utf-8")
    blobs = {
        "notes/cut.yaml": protocol_path.read_bytes(),
        "notes/cut.md": (tmp_path / protocol.protocol_md).read_bytes(),
    }
    errors = protocol_pin_errors(
        protocol,
        protocol_path,
        repository_root=tmp_path,
        study_yaml=study,
        head_blob=blobs.get,
    )
    assert any("not pinned in study.yaml: notes/cut.yaml" in e for e in errors)
    assert any("not pinned in study.yaml: notes/cut.md" in e for e in errors)


def test_should_fail_on_gate_for_protocol_or_run_manifest(tmp_path: Path) -> None:
    protocol = load_cut_protocol(_write_protocol(tmp_path))
    assert should_fail_on_gate(flag=False, protocol=None, run_manifest=None) is False
    assert should_fail_on_gate(flag=True, protocol=None, run_manifest=None) is True
    assert should_fail_on_gate(flag=False, protocol=protocol, run_manifest=None) is True
    assert (
        should_fail_on_gate(flag=False, protocol=None, run_manifest=tmp_path / "run.json") is True
    )


def test_precision_from_labels_excludes_ambiguous() -> None:
    stats = precision_from_labels(
        [
            {"review_outcome": "true"},
            {"review_outcome": "true"},
            {"review_outcome": "false"},
            {"review_outcome": "ambiguous"},
            {"review_outcome": "unreviewed"},
        ]
    )
    assert stats["true_n"] == 2
    assert stats["false_n"] == 1
    assert stats["ambiguous_n"] == 1
    assert stats["unreviewed_n"] == 1
    assert stats["fp_rate"] == pytest.approx(1 / 3)
    assert stats["complete"] is False


def test_gate_failures_skip_incomplete_precision() -> None:
    incomplete = precision_from_labels([{"review_outcome": "unreviewed"}])
    assert (
        gate_failures(
            recall_n=13,
            recall_floor=10,
            labels=incomplete,
            precision_fp_cap=0.25,
            cost_per_pair_usd=None,
            cost_cap=0.10,
        )
        == []
    )
    complete = precision_from_labels([{"review_outcome": "false"}, {"review_outcome": "false"}])
    errors = gate_failures(
        recall_n=9,
        recall_floor=10,
        labels=complete,
        precision_fp_cap=0.25,
        cost_per_pair_usd=0.2,
        cost_cap=0.10,
    )
    assert any("recall floor missed" in e for e in errors)
    assert any("precision FP" in e for e in errors)
    assert any("cost per pair" in e for e in errors)


def test_faults_do_not_fail_a_recall_pass() -> None:
    """Faults only understate recall, so a pass carrying them is conservative.

    A fault scores its pair unconfirmed and can never add a confirmation. If
    the floor cleared anyway, true recall is at least the observed number.
    """
    errors = gate_failures(
        recall_n=13,
        recall_floor=10,
        labels=None,
        precision_fp_cap=0.25,
        cost_per_pair_usd=None,
        cost_cap=0.10,
        llm_timeout_n=2,
        search_failure_n=3,
    )
    assert errors == []


def test_faults_void_a_recall_miss() -> None:
    """A miss carrying faults is not a miss; the faulted pairs may hold hits."""
    errors = gate_failures(
        recall_n=9,
        recall_floor=10,
        labels=None,
        precision_fp_cap=0.25,
        cost_per_pair_usd=None,
        cost_cap=0.10,
        llm_timeout_n=2,
        search_failure_n=3,
    )
    assert any("not measured" in e for e in errors)
    assert any("5 faults" in e for e in errors)


def test_clean_recall_miss_is_a_miss() -> None:
    """A miss with no faults is a miss. It must not be softened into a retry."""
    errors = gate_failures(
        recall_n=9,
        recall_floor=10,
        labels=None,
        precision_fp_cap=0.25,
        cost_per_pair_usd=None,
        cost_cap=0.10,
    )
    assert any("recall floor missed" in e for e in errors)
    assert not any("not measured" in e for e in errors)


def test_faulted_query_is_not_frozen(tmp_path: Path) -> None:
    """A faulted row must not freeze its query, or the rerun inherits the fault."""
    cut = tmp_path / "snippets.jsonl"
    cut.write_text(
        json.dumps({"query": "real zero hit", "snippet": "", "link": None, "hit_count": 0})
        + "\n"
        + json.dumps(
            {"query": "faulted", "snippet": "", "link": None, "hit_count": 0, "fault": True}
        )
        + "\n",
        encoding="utf-8",
    )
    recorded = load_recorded_queries(cut)
    assert "real zero hit" in recorded
    assert "faulted" not in recorded


def test_timed_extractor_counts_timeouts() -> None:
    """A hung extract() is counted, not silently scored as a rejection."""

    class _Hang:
        name = "hang"

        def extract(self, item: object) -> ExtractionVerdict:
            time.sleep(5)
            raise AssertionError("should not finish")

    timed = _TimedExtractor(_Hang(), timeout=0.05)
    verdict = timed.extract(object())
    assert verdict.confirmed is False
    assert timed.timeout_n == 1


@pytest.mark.asyncio
async def test_recording_search_tool_counts_failures(tmp_path: Path) -> None:
    """A search that raises is counted, and its empty hit is not read as absence."""

    class _Boom:
        async def search(self, query: str) -> list[dict[str, object]]:
            raise OSError("connection reset")

    sink: list[dict[str, object]] = []
    tool = RecordingSearchTool(_Boom(), sink, path=tmp_path / "snippets.jsonl")
    hits = await tool.search("acme acquired by globex")
    assert hits == []
    assert tool.failure_n == 1
    assert sink[0]["hit_count"] == 0


def test_main_fails_and_reports_when_search_faults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A faulted miss names the faults and marks the queries for retry.

    Covers the plumbing the component tests cannot reach: counter to summary
    to gate to reported failure. This asserts the fault wording, not just the
    exit code; a clean recall miss also exits 1 and would mask the gate.
    """

    class _Boom:
        async def search(self, query: str) -> list[dict[str, object]]:
            raise OSError("connection reset")

    monkeypatch.setattr(
        "scripts.data.run_ma_discovery_sample.build_search_tool",
        lambda *a, **kw: _Boom(),
    )

    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(
            {
                "company_name": "Acme Robotics, Inc.",
                "event_date": "2020-01-13",
                "acquirer": "Globex Corporation",
                "confidence": "low",
                "signals": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_ma_discovery_sample.py",
            "--events",
            str(events),
            "--search-backend",
            "mock",
            "--confirm",
            "keyword",
            "--output-dir",
            str(out),
            "--fail-on-gate",
        ],
    )

    assert main() == 1
    assert "the miss is not measured" in capsys.readouterr().out

    summary = json.loads((out / "sample_run_summary.json").read_text(encoding="utf-8"))
    assert summary["search_failure_n"] >= 1
    assert summary["kill_gate"]["fully_measured"] is False
    assert summary["kill_gate"]["accepted"] is False

    # The faulted query must stay retryable, or the rerun inherits the fault.
    assert load_recorded_queries(out / "search_snippets.jsonl") == set()


def test_main_refuses_live_capture_without_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["run_ma_discovery_sample.py", "--search-backend", "brave"],
    )
    with pytest.raises(SystemExit, match="hashed in HEAD"):
        main()


def test_main_refuses_capture_llm_without_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["run_ma_discovery_sample.py", "--capture-llm"],
    )
    with pytest.raises(SystemExit, match="hashed in HEAD"):
        main()


def test_checked_in_held_out_1501_protocol_loads() -> None:
    protocol = load_cut_protocol(Path("studies/ma-discovery-recall/held-out-1501.yaml"))
    assert protocol.protocol_id == "held-out-1501"
    assert protocol.skip_pairs == 1500
    assert protocol.max_candidates == 1000
    assert protocol.queries_per_pair == 1
    assert protocol.stop_when == "dated_confirm"
    assert protocol.strict_recall is True
    assert protocol.fail_on_gate is True
    assert protocol.confirm == "llm"
    assert protocol.search_backend_capture == "brave"
    assert protocol.intended_rank == "validated"
    assert protocol.events_sha256 == (
        "6ffc8481a240b2ee9bd9fdef806395d3f62e9d1f3ba12a68490d28fb53a1cf49"
    )
