#!/usr/bin/env python3
"""Run a bounded M&A discovery sample and emit a human review queue.

Epistemic tier: exploratory. This is the sample-run / review-queue CLI for
``studies/ma-discovery-recall``. It does not promote a rank. Default search
backend is fail-closed; pass ``--search-backend mock`` or ``snippets``.
Live Brave/Tavily or ``--capture-llm`` requires ``--protocol`` hashed in HEAD.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from sbir_etl.config.schemas.domain import MADiscoveryConfig
from sbir_etl.config.yaml_io import read_yaml_mapping
from sbir_etl.enrichers.ma_discovery.collision import apply_c3, name_key
from sbir_etl.enrichers.ma_discovery.extractor import (
    ExtractionVerdict,
    FrozenLlmExtractor,
    RecordingLlmExtractor,
    SnippetExtractor,
    build_llm_extractor,
)
from sbir_etl.enrichers.ma_discovery.orchestrator import process_batch
from sbir_etl.enrichers.ma_discovery.queries import (
    load_ma_events,
    query_rows_from_events,
)
from sbir_etl.enrichers.ma_discovery.search import SearchTool, build_search_tool
from sbir_etl.exceptions import ConfigurationError


EPISTEMIC_TIER = "exploratory"
REVIEW_SIZE = 20
LIVE_SEARCH_BACKENDS = frozenset({"brave", "tavily"})
_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


def _brave_search_sync(api_key: str, query: str, max_results: int) -> list[dict[str, Any]]:
    """Blocking Brave GET with a real socket timeout. Exploratory capture helper."""
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            _BRAVE_SEARCH_URL,
            params={"q": query, "count": max_results},
            headers={
                "X-Subscription-Token": api_key,
                "Accept": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
    web = data.get("web") if isinstance(data, dict) else None
    results = web.get("results") if isinstance(web, dict) else None
    if not isinstance(results, list):
        return []
    hits: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        link = item.get("url")
        if not link:
            continue
        hit: dict[str, Any] = {
            "snippet": str(item.get("description") or ""),
            "link": str(link),
        }
        title = item.get("title")
        if title:
            hit["title"] = str(title)
        hits.append(hit)
    return hits


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STUDY_YAML = REPO_ROOT / "studies" / "ma-discovery-recall" / "study.yaml"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HeadBlob = Callable[[str], bytes | None]


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_review_queue(
    result_rows: list[dict[str, Any]],
    *,
    limit: int = REVIEW_SIZE,
) -> list[dict[str, Any]]:
    """Medium-confidence discovery-touched rows for human labeling."""
    queue: list[dict[str, Any]] = []
    for row in result_rows:
        signals = row.get("signals") or {}
        if row.get("confidence") != "medium":
            continue
        if not signals.get("discovery_confirmed"):
            continue
        queue.append(
            {
                "company_name": row.get("company_name"),
                "acquirer": row.get("acquirer"),
                "event_date": row.get("event_date"),
                "source": row.get("source"),
                "evidence": row.get("evidence"),
                "confidence": row.get("confidence"),
                "review_outcome": "unreviewed",
                "review_rationale": None,
            }
        )
        if len(queue) >= limit:
            break
    return queue


class RecordingSearchTool:
    """Wrap a SearchTool and append every query/hit to a sink. Exploratory.

    A failed search is recorded as an empty hit so the run can continue, but it
    is not evidence that no article exists. ``failure_n`` counts them so the
    caller can gate on them instead of reading them as absence.
    """

    def __init__(
        self,
        inner: SearchTool,
        sink: list[dict[str, Any]],
        *,
        path: Path | None = None,
    ) -> None:
        self._inner = inner
        self._sink = sink
        self._path = path
        self.failure_n = 0

    def _record(self, record: dict[str, Any]) -> None:
        self._sink.append(record)
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    async def search(self, query: str) -> list[dict[str, Any]]:
        api_key = getattr(self._inner, "_api_key", None)
        faulted = False
        try:
            if isinstance(api_key, str) and api_key:
                max_results = int(getattr(self._inner, "_max_results", 5) or 5)
                hits = await asyncio.to_thread(_brave_search_sync, api_key, query, max_results)
            else:
                hits = await asyncio.wait_for(self._inner.search(query), timeout=60)
        except (TimeoutError, httpx.HTTPError, OSError) as exc:
            self.failure_n += 1
            faulted = True
            print(f"search failed ({type(exc).__name__}); empty hit is not absence")
            hits = []
        if not hits:
            empty: dict[str, Any] = {
                "query": query,
                "snippet": "",
                "link": None,
                "hit_count": 0,
            }
            if faulted:
                empty["fault"] = True
            self._record(empty)
            return hits
        for hit in hits:
            record = {
                "query": query,
                "snippet": hit.get("snippet") or "",
                "link": hit.get("link"),
                "hit_count": len(hits),
            }
            title = hit.get("title")
            if title:
                record["title"] = title
            self._record(record)
        return hits

    async def aclose(self) -> None:
        aclose = getattr(self._inner, "aclose", None)
        if aclose is not None:
            await aclose()


class _TimedExtractor:
    """Run extract() in a thread so a hung TLS read cannot block the cut.

    A timeout writes no freeze row, so both this run and any replay score the
    pair unconfirmed. That is indistinguishable from the model reading the
    snippet and rejecting it. ``timeout_n`` counts them so the caller can gate
    on them instead of scoring a network fault as no acquisition.
    """

    name = "timed_llm"

    def __init__(self, inner: SnippetExtractor, *, timeout: float) -> None:
        self.inner = inner
        self._timeout = timeout
        self.timeout_n = 0

    def extract(self, item: Any) -> ExtractionVerdict:
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm-extract")
        future = pool.submit(self.inner.extract, item)
        try:
            return future.result(timeout=self._timeout)
        except FuturesTimeout:
            self.timeout_n += 1
            print("LLM extract timeout; unconfirmed here is not a rejection")
            return ExtractionVerdict(confirmed=False, reason="LLM timeout")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)


def bound_queries(
    queries: list[dict[str, str]],
    *,
    max_candidates: int,
    queries_per_pair: int,
    skip_pairs: int = 0,
) -> list[dict[str, str]]:
    """Keep the first ``queries_per_pair`` templates after skipping unique pairs."""
    kept: list[dict[str, str]] = []
    skipped: set[tuple[str, str]] = set()
    per_pair: dict[tuple[str, str], int] = {}
    for row in queries:
        key = (row["company_name"], row["acquirer"])
        if key in skipped:
            continue
        if key not in per_pair:
            if len(skipped) < skip_pairs:
                skipped.add(key)
                continue
            if len(per_pair) >= max_candidates:
                continue
        used = per_pair.get(key, 0)
        if used >= queries_per_pair:
            continue
        per_pair[key] = used + 1
        kept.append(row)
    return kept


def load_recorded_queries(path: Path) -> set[str]:
    """Return query strings already frozen in a snippets JSONL cut.

    Two markers stop a row from freezing its query, so a rerun retries that
    pair instead of inheriting the gap:

    ``fault``
        An exception was observed. A known non-observation.
    ``unverified_empty``
        The row is empty and was captured before fault marking existed, so a
        genuine zero hit and a swallowed fault cannot be told apart.

    An unmarked zero-hit row does freeze: the vendor answered and found
    nothing.
    """
    if not path.is_file():
        return set()
    recorded: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("fault") or record.get("unverified_empty"):
            continue
        query = record.get("query")
        if isinstance(query, str) and query:
            recorded.add(query)
    return recorded


def drop_recorded_queries(
    queries: list[dict[str, str]],
    recorded: set[str],
) -> list[dict[str, str]]:
    """Drop rows whose query string is already in a frozen snippets cut."""
    if not recorded:
        return list(queries)
    return [row for row in queries if row["query"] not in recorded]


def pair_key(company: object, acquirer: object) -> tuple[str, str]:
    return (name_key(str(company or "")), name_key(str(acquirer or "")))


def existing_medium_high_pairs(events: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Pairs the detector already called medium or high (any date)."""
    pairs: set[tuple[str, str]] = set()
    for row in events:
        if row.get("confidence") not in {"medium", "high"}:
            continue
        key = pair_key(row.get("company_name"), row.get("acquirer"))
        if key[0]:
            pairs.add(key)
    return pairs


def strict_medium_high_n(
    events: list[dict[str, Any]],
    mutated: list[dict[str, Any]],
) -> int:
    """Count insert/promote medium/high pairs that were not already medium/high."""
    already = existing_medium_high_pairs(events)
    seen: set[tuple[str, str]] = set()
    for row in mutated:
        if row.get("confidence") not in {"medium", "high"}:
            continue
        key = pair_key(row.get("company_name"), row.get("acquirer"))
        if not key[0] or key in already or key in seen:
            continue
        seen.add(key)
    return len(seen)


def check_run_manifest(
    manifest_path: Path,
    *,
    events: Path,
    snippets: Path,
    llm: Path | None,
) -> list[str]:
    """Return SHA mismatches vs a tracked run manifest. Empty means match."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    inputs = payload.get("inputs") if isinstance(payload, dict) else None
    if not isinstance(inputs, dict):
        return [f"run manifest missing inputs: {manifest_path}"]
    errors: list[str] = []
    mapping = {
        "events": events,
        "snippets": snippets,
        "llm_responses": llm,
    }
    for name, path in mapping.items():
        spec = inputs.get(name)
        if not isinstance(spec, dict):
            continue
        expected = spec.get("sha256")
        if not isinstance(expected, str) or not expected:
            continue
        if path is None or not path.is_file():
            errors.append(f"{name} freeze missing for SHA check: {path}")
            continue
        actual = _sha256(path)
        if actual != expected:
            errors.append(f"{name} SHA mismatch: expected {expected}, found {actual}")
    return errors


@dataclass(frozen=True)
class CutProtocol:
    """Machine-readable measured-cut contract. Exploratory CLI helper."""

    protocol_id: str
    protocol_md: str
    skip_pairs: int
    max_candidates: int
    queries_per_pair: int
    stop_when: str
    strict_recall: bool
    fail_on_gate: bool
    confirm: str
    search_backend_capture: str
    search_backend_rerun: str
    events_path: str
    events_sha256: str
    output_dir: str
    intended_rank: str
    recall_floor: int
    precision_fp_cap: float
    cost_per_pair_cap_usd: float


def is_live_capture(*, search_backend: str | None, capture_llm: bool) -> bool:
    """True when the run would call Brave, Tavily, or a live LLM."""
    backend = (search_backend or "").strip().lower()
    return bool(capture_llm) or backend in LIVE_SEARCH_BACKENDS


def load_cut_protocol(path: Path) -> CutProtocol:
    """Load a cut protocol YAML. Unknown or missing fields fail closed."""
    try:
        raw = read_yaml_mapping(path, description="cut protocol")
    except ConfigurationError as exc:
        raise ValueError(str(exc)) from exc
    expected = set(CutProtocol.__dataclass_fields__)
    missing = sorted(expected - raw.keys())
    extra = sorted(set(raw) - expected)
    if missing:
        raise ValueError(f"cut protocol missing fields: {missing}")
    if extra:
        raise ValueError(f"cut protocol unknown fields: {extra}")
    stop_when = raw["stop_when"]
    if stop_when not in {"first_confirm", "dated_confirm"}:
        raise ValueError(
            f"cut protocol stop_when must be dated_confirm or first_confirm: {stop_when!r}"
        )
    sha = raw["events_sha256"]
    if not isinstance(sha, str) or not _SHA256_RE.fullmatch(sha):
        raise ValueError("cut protocol events_sha256 must be 64 lowercase hex chars")
    return CutProtocol(
        protocol_id=str(raw["protocol_id"]),
        protocol_md=str(raw["protocol_md"]),
        skip_pairs=int(raw["skip_pairs"]),
        max_candidates=int(raw["max_candidates"]),
        queries_per_pair=int(raw["queries_per_pair"]),
        stop_when=str(stop_when),
        strict_recall=bool(raw["strict_recall"]),
        fail_on_gate=bool(raw["fail_on_gate"]),
        confirm=str(raw["confirm"]),
        search_backend_capture=str(raw["search_backend_capture"]),
        search_backend_rerun=str(raw["search_backend_rerun"]),
        events_path=str(raw["events_path"]),
        events_sha256=sha,
        output_dir=str(raw["output_dir"]),
        intended_rank=str(raw["intended_rank"]),
        recall_floor=int(raw["recall_floor"]),
        precision_fp_cap=float(raw["precision_fp_cap"]),
        cost_per_pair_cap_usd=float(raw["cost_per_pair_cap_usd"]),
    )


def git_head_blob(relative_path: str, *, cwd: Path) -> bytes | None:
    """Return ``git show HEAD:path`` bytes, or None if the path is not in HEAD."""
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative_path}"],
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _repo_relative(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def protocol_pin_errors(
    protocol: CutProtocol,
    protocol_path: Path,
    *,
    repository_root: Path,
    study_yaml: Path,
    head_blob: HeadBlob | None = None,
) -> list[str]:
    """Protocol files must match HEAD bytes and ``study.yaml`` frozen_artifacts."""
    lookup = head_blob or (lambda rel: git_head_blob(rel, cwd=repository_root))
    try:
        manifest = read_yaml_mapping(study_yaml, description="study manifest")
    except ConfigurationError as exc:
        return [str(exc)]
    artifacts = manifest.get("frozen_artifacts")
    pinned: dict[str, str] = {}
    if isinstance(artifacts, list):
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            art_path = item.get("path")
            art_sha = item.get("sha256")
            if isinstance(art_path, str) and isinstance(art_sha, str):
                pinned[art_path] = art_sha

    errors: list[str] = []
    yaml_rel = _repo_relative(protocol_path, repository_root)
    if yaml_rel is None:
        return [f"protocol path escapes repository root: {protocol_path}"]
    md_path = repository_root / protocol.protocol_md
    checks = [(yaml_rel, protocol_path), (protocol.protocol_md, md_path)]
    for relative, path in checks:
        if not path.is_file():
            errors.append(f"protocol file missing: {relative}")
            continue
        working = path.read_bytes()
        head = lookup(relative)
        if head is None:
            errors.append(
                f"protocol not in HEAD: {relative} (hash it in git before any live capture)"
            )
        elif head != working:
            errors.append(f"protocol working tree differs from HEAD: {relative}")
        expected = pinned.get(relative)
        actual = hashlib.sha256(working).hexdigest()
        if expected is None:
            errors.append(f"protocol not pinned in {study_yaml.name}: {relative}")
        elif expected != actual:
            errors.append(
                f"frozen_artifacts sha256 mismatch for {relative}: "
                f"expected {expected}, found {actual}"
            )
    return errors


def live_capture_errors(
    *,
    search_backend: str | None,
    capture_llm: bool,
    protocol: CutProtocol | None,
) -> list[str]:
    """Refuse live search/LLM unless a hashed protocol selected the cut."""
    if not is_live_capture(search_backend=search_backend, capture_llm=capture_llm):
        return []
    if protocol is None:
        return [
            "live Brave/Tavily/--capture-llm requires --protocol hashed in HEAD "
            "before any search or LLM call"
        ]
    errors: list[str] = []
    backend = (search_backend or "").strip().lower()
    if backend in LIVE_SEARCH_BACKENDS and backend != protocol.search_backend_capture:
        errors.append(
            f"live search backend {backend!r} does not match protocol "
            f"{protocol.search_backend_capture!r}"
        )
    if capture_llm and protocol.confirm != "llm":
        errors.append("protocol does not authorize --capture-llm")
    return errors


def apply_cut_protocol(args: argparse.Namespace, protocol: CutProtocol) -> None:
    """Overwrite cut flags from the protocol. Protocol is authoritative."""
    args.skip_pairs = protocol.skip_pairs
    args.max_candidates = protocol.max_candidates
    args.queries_per_pair = protocol.queries_per_pair
    args.stop_when = protocol.stop_when
    args.strict_recall = protocol.strict_recall
    args.fail_on_gate = True
    args.confirm = protocol.confirm
    args.output_dir = Path(protocol.output_dir)
    args.events = Path(protocol.events_path)


def should_fail_on_gate(
    *,
    flag: bool,
    protocol: CutProtocol | None,
    run_manifest: Path | None,
) -> bool:
    """Protocol runs and SHA-checked replays fail closed on missed gates."""
    return bool(flag) or protocol is not None or run_manifest is not None


def precision_from_labels(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """FP = false/(true+false). Ambiguous and unreviewed are excluded."""
    true_n = false_n = ambiguous_n = unreviewed_n = 0
    for row in rows:
        outcome = row.get("review_outcome")
        if outcome == "true":
            true_n += 1
        elif outcome == "false":
            false_n += 1
        elif outcome == "ambiguous":
            ambiguous_n += 1
        else:
            unreviewed_n += 1
    denom = true_n + false_n
    return {
        "true_n": true_n,
        "false_n": false_n,
        "ambiguous_n": ambiguous_n,
        "unreviewed_n": unreviewed_n,
        "fp_rate": (false_n / denom) if denom else None,
        "complete": bool(rows) and unreviewed_n == 0,
    }


def load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def gate_failures(
    *,
    recall_n: int,
    recall_floor: int,
    labels: dict[str, Any] | None,
    precision_fp_cap: float,
    cost_per_pair_usd: float | None,
    cost_cap: float,
    llm_timeout_n: int = 0,
    search_failure_n: int = 0,
) -> list[str]:
    """Automated gates that can fail a confirmatory/protocol run.

    Incomplete precision labels are not a failure; they keep ``accepted`` false.

    Network faults are asymmetric on recall. A fault scores the pair
    unconfirmed and can never manufacture a confirmation, so faults only ever
    understate recall. A recall pass carrying faults is therefore conservative
    and stands. A recall miss carrying faults is not a miss: the faulted pairs
    may hold the absent confirmations, so the number is not measured.
    """
    errors: list[str] = []
    faults = llm_timeout_n + search_failure_n
    if recall_n < recall_floor:
        if faults:
            errors.append(
                f"recall {recall_n} < {recall_floor} with {faults} faults "
                f"({llm_timeout_n} LLM timeout, {search_failure_n} search); "
                "the miss is not measured, retry the faulted pairs"
            )
        else:
            errors.append(f"recall floor missed ({recall_n} < {recall_floor})")
    if labels is not None and labels["complete"]:
        fp_rate = labels["fp_rate"]
        if fp_rate is None:
            errors.append("precision labels have no true/false rows")
        elif fp_rate > precision_fp_cap:
            errors.append(f"precision FP {fp_rate} exceeds cap {precision_fp_cap}")
    if cost_per_pair_usd is not None and cost_per_pair_usd > cost_cap:
        errors.append(f"cost per pair ${cost_per_pair_usd} exceeds cap ${cost_cap}")
    return errors


async def _search(
    queries: list[dict[str, str]],
    *,
    backend: str | None,
    api_key: str | None,
    snippets: Path | None,
    sink: list[dict[str, Any]],
    extractor: SnippetExtractor | None = None,
    record_path: Path | None = None,
    stop_when: str = "first_confirm",
) -> tuple[list[dict[str, Any]], int]:
    config = MADiscoveryConfig(
        search_backend=backend or "none",
        search_api_key=api_key,
        rate_limit_per_minute=20,
        max_results=5,
        snippets_path=str(snippets) if snippets else None,
    )
    inner = build_search_tool(
        backend,
        api_key=api_key,
        config=config,
        snippets_path=snippets,
    )
    tool = RecordingSearchTool(inner, sink, path=record_path)
    try:
        rows = await process_batch(queries, tool, extractor=extractor, stop_when=stop_when)
        return rows, tool.failure_n
    finally:
        await tool.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=Path("data/sbir_ma_events.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/ma_discovery"))
    parser.add_argument("--search-backend", default=None)
    parser.add_argument("--search-api-key", default=None)
    parser.add_argument("--snippets", type=Path, default=None)
    parser.add_argument("--max-candidates", type=int, default=200)
    parser.add_argument(
        "--skip-pairs",
        type=int,
        default=0,
        help="Skip this many unique pairs before applying --max-candidates (held-out cuts).",
    )
    parser.add_argument(
        "--queries-per-pair",
        type=int,
        default=1,
        help="Query templates per pair. Live capture uses 1 to bound API spend.",
    )
    parser.add_argument(
        "--stop-when",
        choices=("first_confirm", "dated_confirm"),
        default="first_confirm",
        help="first_confirm is the pilot rule; dated_confirm keeps scanning until medium/high.",
    )
    parser.add_argument(
        "--confirm",
        choices=("keyword", "llm"),
        default="keyword",
        help="Snippet confirmer. llm needs --llm-freeze (replay) or --capture-llm (live).",
    )
    parser.add_argument(
        "--llm-freeze",
        type=Path,
        default=None,
        help="Replay FrozenLlmExtractor from this JSONL. No network.",
    )
    parser.add_argument(
        "--capture-llm",
        action="store_true",
        help="Live OpenRouter/xAI capture; checkpoint into output-dir/llm_responses.jsonl.",
    )
    parser.add_argument(
        "--llm-api-key",
        default=None,
        help="Override OPENROUTER_API_KEY or XAI_API_KEY (capture only).",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=None,
        help="Fail if events/snippets/LLM SHA-256 do not match this tracked manifest.",
    )
    parser.add_argument(
        "--strict-recall",
        action="store_true",
        help="Recall floor counts only pairs not already medium/high in the events file.",
    )
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="Exit 1 when recall, complete precision, or measured cost misses a cap.",
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=None,
        help="Hashed cut protocol YAML. Required for live Brave/Tavily/--capture-llm.",
    )
    parser.add_argument(
        "--study-yaml",
        type=Path,
        default=DEFAULT_STUDY_YAML,
        help="Study manifest used to verify protocol frozen_artifacts pins.",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=None,
        help="JSONL human labels for the precision gate (review_outcome true/false/ambiguous).",
    )
    args = parser.parse_args()

    protocol: CutProtocol | None = None
    if args.protocol is not None:
        try:
            protocol = load_cut_protocol(args.protocol)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        apply_cut_protocol(args, protocol)
        pin_errors = protocol_pin_errors(
            protocol,
            args.protocol,
            repository_root=REPO_ROOT,
            study_yaml=args.study_yaml,
        )
        if pin_errors:
            raise SystemExit("protocol pin check failed:\n" + "\n".join(pin_errors))
        print(
            f"Using protocol {protocol.protocol_id}: skip={protocol.skip_pairs} "
            f"max={protocol.max_candidates} stop={protocol.stop_when}"
        )

    live_errors = live_capture_errors(
        search_backend=args.search_backend,
        capture_llm=args.capture_llm,
        protocol=protocol,
    )
    if live_errors:
        raise SystemExit("\n".join(live_errors))

    if protocol is not None:
        events_sha = _sha256(args.events)
        if events_sha != protocol.events_sha256:
            raise SystemExit(
                "events SHA mismatch vs protocol: "
                f"expected {protocol.events_sha256}, found {events_sha}"
            )

    args.fail_on_gate = should_fail_on_gate(
        flag=args.fail_on_gate,
        protocol=protocol,
        run_manifest=args.run_manifest,
    )

    events = load_ma_events(args.events)
    queries = query_rows_from_events(events)
    bounded = bound_queries(
        queries,
        max_candidates=args.max_candidates,
        queries_per_pair=args.queries_per_pair,
        skip_pairs=args.skip_pairs,
    )
    replay = args.snippets is not None
    snippets_path = args.output_dir / "search_snippets.jsonl"
    skipped_n = 0
    if not replay:
        recorded_queries = load_recorded_queries(snippets_path)
        if recorded_queries:
            before = len(bounded)
            bounded = drop_recorded_queries(bounded, recorded_queries)
            skipped_n = before - len(bounded)
    pair_n = len({(row["company_name"], row["acquirer"]) for row in bounded})
    skip_note = f", skipped {skipped_n} frozen" if skipped_n else ""
    print(
        f"Searching {len(bounded)} queries across {pair_n} pairs "
        f"(backend={args.search_backend!r}{skip_note})"
    )
    recorded: list[dict[str, Any]] = []
    llm_records: list[dict[str, Any]] = []
    extractor: SnippetExtractor | None = None
    llm_path = args.output_dir / "llm_responses.jsonl"
    if args.confirm == "llm":
        if args.capture_llm and args.llm_freeze is not None:
            raise SystemExit("use either --capture-llm or --llm-freeze, not both")
        if args.capture_llm:
            live = build_llm_extractor(api_key=args.llm_api_key)
            if live is None:
                raise SystemExit("OPENROUTER_API_KEY or XAI_API_KEY is required for --capture-llm")
            extractor = _TimedExtractor(
                RecordingLlmExtractor(live, llm_records, path=llm_path),
                timeout=90,
            )
        else:
            freeze = args.llm_freeze or llm_path
            if not freeze.is_file():
                raise SystemExit("--confirm llm requires --llm-freeze JSONL or --capture-llm")
            extractor = FrozenLlmExtractor(freeze)
            llm_path = freeze

    if args.run_manifest is not None:
        sha_errors = check_run_manifest(
            args.run_manifest,
            events=args.events,
            snippets=args.snippets or snippets_path,
            llm=llm_path if args.confirm == "llm" else None,
        )
        if sha_errors:
            raise SystemExit("run-manifest SHA check failed:\n" + "\n".join(sha_errors))

    discovered, search_failure_n = asyncio.run(
        _search(
            bounded,
            backend=args.search_backend,
            api_key=args.search_api_key,
            snippets=args.snippets,
            sink=recorded,
            extractor=extractor,
            record_path=None if replay else snippets_path,
            stop_when=args.stop_when,
        )
    )
    llm_timeout_n = int(getattr(extractor, "timeout_n", 0))
    collision = apply_c3(events, discovered)
    queue = build_review_queue(collision.inserted + collision.promoted)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    discovered_path = args.output_dir / "discovered_acquisitions.jsonl"
    queue_path = args.output_dir / "review_queue.jsonl"
    summary_path = args.output_dir / "sample_run_summary.json"
    with discovered_path.open("w", encoding="utf-8") as handle:
        for row in discovered:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    with queue_path.open("w", encoding="utf-8") as handle:
        for row in queue:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    medium_high = [row for row in discovered if row.get("confidence") in {"medium", "high"}]
    strict_n = strict_medium_high_n(events, collision.inserted + collision.promoted)
    recall_n = strict_n if args.strict_recall else len(medium_high)
    recall_floor = protocol.recall_floor if protocol is not None else 10
    recall_met = recall_n >= recall_floor
    precision_cap = protocol.precision_fp_cap if protocol is not None else 0.25
    cost_cap = protocol.cost_per_pair_cap_usd if protocol is not None else 0.10
    label_path = args.labels if args.labels is not None else queue_path
    label_rows = load_jsonl_rows(label_path) if label_path.is_file() else []
    labels = precision_from_labels(label_rows) if label_rows else None
    precision_complete = bool(labels and labels["complete"])
    fp_rate = labels["fp_rate"] if labels else None
    precision_cap_met = precision_complete and fp_rate is not None and fp_rate <= precision_cap
    failures = gate_failures(
        recall_n=recall_n,
        recall_floor=recall_floor,
        labels=labels,
        precision_fp_cap=precision_cap,
        cost_per_pair_usd=None,
        cost_cap=cost_cap,
        llm_timeout_n=llm_timeout_n,
        search_failure_n=search_failure_n,
    )
    fully_measured = not llm_timeout_n and not search_failure_n
    accepted = recall_met and precision_cap_met
    llm_n = len(llm_records)
    if not llm_n and args.confirm == "llm" and llm_path.is_file():
        llm_n = sum(1 for line in llm_path.read_text(encoding="utf-8").splitlines() if line.strip())
    summary = {
        "_epistemic": {
            "citable": False,
            "tier": "exploratory",
            "notice": "Sample run; not a validated or citable result.",
        },
        "as_of_utc": datetime.now(UTC).isoformat(),
        "protocol_id": protocol.protocol_id if protocol is not None else None,
        "events_path": str(args.events),
        "events_sha256": _sha256(args.events),
        "events_n": len(events),
        "query_rows": len(bounded),
        "candidate_pairs": pair_n,
        "skip_pairs": args.skip_pairs,
        "queries_per_pair": args.queries_per_pair,
        "stop_when": args.stop_when,
        "recorded_snippet_rows": len(recorded),
        "snippets_sha256": _sha256(args.snippets or snippets_path),
        "confirm": args.confirm,
        "llm_model": llm_records[0]["model"] if llm_records else None,
        "llm_response_n": llm_n,
        "llm_responses_sha256": _sha256(llm_path) if args.confirm == "llm" else None,
        "discovered_n": len(discovered),
        "discovered_medium_high_n": len(medium_high),
        "strict_medium_high_n": strict_n,
        "inserted_n": len(collision.inserted),
        "promoted_n": len(collision.promoted),
        "review_queue_n": len(queue),
        "search_backend": args.search_backend,
        "snippets_path": str(snippets_path),
        "snippets_input": str(args.snippets) if args.snippets else None,
        "llm_timeout_n": llm_timeout_n,
        "search_failure_n": search_failure_n,
        "kill_gate": {
            "fully_measured": fully_measured,
            "recall_floor_met": recall_met,
            "recall_n": recall_n,
            "recall_floor": recall_floor,
            "recall_rule": "strict" if args.strict_recall else "discovered_medium_high",
            "precision_review_complete": precision_complete,
            "precision_fp_rate": fp_rate,
            "precision_cap_met": precision_cap_met,
            "cost_cap_measured": False,
            "cost_per_pair_cap_usd": cost_cap,
            "accepted": accepted,
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Discovered {len(discovered)} rows; review queue {len(queue)} → {args.output_dir}")
    if args.fail_on_gate and failures:
        print("; ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
