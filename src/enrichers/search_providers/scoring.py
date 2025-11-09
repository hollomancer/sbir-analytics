"""
Scoring helpers for search enrichment benchmark.

This module provides small, dependency-free utilities to:
- compute text similarity between provider snippets and ground-truth fields
- compute citation / URL matching scores
- compute per-result and aggregated metrics (precision, recall, F1,
  citation-coverage, latency-weighted metrics)
- produce JSON-serializable reports for benchmark harnesses

Design goals:
- Keep functions deterministic and easy to unit test
- Avoid heavy external dependencies so these helpers can be used in CI
- Provide sensible defaults and lightweight configurability for weights
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse


# Import project-normalized types when available to keep type hints helpful.
# If unavailable at runtime in some contexts, callers can still use the
# functions by passing plain dicts / objects that have the expected attributes.
try:
    from .base import ProviderResponse, ProviderResult
except Exception:
    ProviderResponse = Any  # type: ignore
    ProviderResult = Any  # type: ignore


# -------------------------------
# Small utilities
# -------------------------------


def normalize_url(u: str | None) -> str | None:
    """Return a normalized URL with scheme and hostname lowercased and
    without query/fragment. Returns None for falsy inputs."""
    if not u:
        return None
    try:
        p = urlparse(u)
        if not p.scheme:
            # Assume http if scheme missing
            p = urlparse("http://" + u)
        netloc = p.netloc.lower()
        path = p.path.rstrip("/")
        return f"{p.scheme.lower()}://{netloc}{path}"
    except Exception:
        return u.strip()


def domain_of_url(u: str | None) -> str | None:
    """Return the effective domain/host for a URL or None."""
    nu = normalize_url(u)
    if not nu:
        return None
    try:
        return urlparse(nu).netloc.lower()
    except Exception:
        return None


def tokenize_text(s: str | None) -> list[str]:
    """Very small tokenizer: lowercase, split on whitespace and punctuation.
    Keeps tokens of length >= 2 to avoid noise."""
    if not s:
        return []
    # Basic normalization and split
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in s)
    toks = [t for t in cleaned.split() if len(t) >= 2]
    return toks


def jaccard_similarity(a: Sequence[str], b: Sequence[str]) -> float:
    """Compute Jaccard similarity between two token sequences."""
    sa = set(a)
    sb = set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    inter = sa.intersection(sb)
    uni = sa.union(sb)
    return len(inter) / len(uni)


def sequence_similarity(a: str, b: str) -> float:
    """Use difflib.SequenceMatcher ratio as a lightweight similarity metric."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def text_similarity(a: str | None, b: str | None) -> float:
    """Combine token Jaccard and sequence similarity for a stable score in [0,1].

    We compute:
      - jaccard over tokens (captures overlap)
      - sequence matcher ratio (captures order/phrasing)
    Then return a weighted average (0.6*J + 0.4*S) which empirically balances
    recall of phrase matches and token overlap.
    """
    if not a and not b:
        return 1.0
    a = (a or "").strip()
    b = (b or "").strip()
    toks_a = tokenize_text(a)
    toks_b = tokenize_text(b)
    j = jaccard_similarity(toks_a, toks_b)
    s = sequence_similarity(a, b)
    return 0.6 * j + 0.4 * s


# -------------------------------
# Scoring data structures
# -------------------------------


@dataclass
class FieldMatchScore:
    """Per-field match scoring summary."""

    field: str
    truth: str | None
    candidate: str | None
    similarity: float


@dataclass
class ResultScore:
    """Score summary for a single ProviderResult vs. a ground-truth entity.

    Attributes:
        provider: provider short name
        query: original query string
        rank: result rank (1-indexed)
        url: result URL (if any)
        text_similarity: aggregated similarity between snippet/title and truth
        field_scores: list of FieldMatchScore for structured fields checked
        citation_score: 0..1 indicating match to authoritative site (exact/domain)
        latency_ms: reported latency for provider request (optional)
    """

    provider: str
    query: str
    rank: int
    url: str | None
    title: str | None
    snippet: str | None
    text_similarity: float
    field_scores: list[FieldMatchScore]
    citation_score: float
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Convert dataclasses in field_scores to dicts
        d["field_scores"] = [asdict(fs) for fs in self.field_scores]
        return d


# -------------------------------
# Per-result scoring functions
# -------------------------------


def score_citation(candidate_url: str | None, truth_url: str | None) -> float:
    """Score how well a candidate URL matches the authoritative truth URL.

    - 1.0 for exact normalized URL match
    - 0.8 for same domain (e.g., truth: acme.com, candidate: www.acme.com/path)
    - 0.0 otherwise
    """
    if not truth_url:
        return 0.0
    if not candidate_url:
        return 0.0
    try:
        n_cand = normalize_url(candidate_url)
        n_truth = normalize_url(truth_url)
        if n_cand == n_truth:
            return 1.0
        d_c = domain_of_url(n_cand)
        d_t = domain_of_url(n_truth)
        if d_c and d_t and d_c == d_t:
            return 0.8
    except Exception:
        pass
    return 0.0


def score_result_against_truth(
    result: ProviderResult,
    truth: dict[str, Any],
    fields_to_check: Sequence[str] | None = None,
    text_weight: float = 0.5,
) -> ResultScore:
    """Score a single `ProviderResult` against ground-truth entity.

    Args:
        result: ProviderResult (from ProviderResponse.results)
        truth: dict containing canonical fields for the target entity. Common
            keys: 'name', 'uei', 'duns', 'website', 'pi', 'address', etc.
        fields_to_check: explicit list of truth keys to compute field matches for.
            If None, we will check a sensible default subset.
        text_weight: weight (0..1) used when combining snippet/title similarity
            with structured-field similarity to produce `text_similarity`.

    Returns:
        ResultScore dataclass.
    """
    # Determine which fields to evaluate
    default_fields = ["name", "website", "uei", "duns", "pi"]
    keys = list(fields_to_check) if fields_to_check else default_fields

    # Build aggregated text to compare (title + snippet)
    title = getattr(result, "title", None)
    snippet = getattr(result, "snippet", None)
    combined_text = " ".join([t for t in (title or "", snippet or "") if t]).strip()

    # Compute per-field similarities
    field_scores: list[FieldMatchScore] = []
    structured_sims: list[float] = []
    for k in keys:
        truth_val = truth.get(k)
        # For website, prefer URL normalization + domain comparison
        if k == "website":
            cand_url = getattr(result, "url", None)
            sim = score_citation(cand_url, truth_val)  # 0..1
            # Because citation is a different notion than text-similarity,
            # map domain/exact match to [0..1] directly.
            field_scores.append(
                FieldMatchScore(field=k, truth=truth_val, candidate=cand_url, similarity=sim)
            )
            structured_sims.append(sim)
            continue

        # For other structured fields, compare text in the combined snippet/title
        cand_text = None
        if k in ("uei", "duns"):
            # numeric identifiers may appear raw in snippet or as metadata
            cand_text = None
            # try result.metadata if present
            if hasattr(result, "metadata") and isinstance(result.metadata, dict):
                cand_text = result.metadata.get(k)
        if cand_text is None:
            # fall back to searching combined_text for presence
            cand_text = combined_text

        sim = 0.0
        try:
            sim = text_similarity(str(truth_val) if truth_val is not None else None, cand_text)
        except Exception:
            sim = 0.0

        field_scores.append(
            FieldMatchScore(
                field=k,
                truth=str(truth_val) if truth_val is not None else None,
                candidate=cand_text,
                similarity=sim,
            )
        )
        structured_sims.append(sim)

    # Aggregate structured similarity (average of field sims)
    structured_agg = float(sum(structured_sims) / len(structured_sims)) if structured_sims else 0.0

    # Text similarity to truth name (prefer name field if present)
    name_truth = truth.get("name")
    name_sim = text_similarity(name_truth, combined_text) if name_truth else 0.0

    # Combine name/text similarity and structured fields into a single value
    # text_weight controls the emphasis on snippet/title (vs. structured fields)
    text_similarity_score = (text_weight * name_sim) + ((1.0 - text_weight) * structured_agg)

    citation_score = score_citation(getattr(result, "url", None), truth.get("website"))

    # Compose ResultScore
    rank = getattr(result, "metadata", {}).get("rank") or 0
    try:
        rank = int(rank) if rank else 0
    except Exception:
        rank = 0

    rs = ResultScore(
        provider=getattr(result, "source", "")
        or getattr(result, "metadata", {}).get("provider", ""),
        query=truth.get("__query__", "") or "",
        rank=rank,
        url=getattr(result, "url", None),
        title=title,
        snippet=snippet,
        text_similarity=round(text_similarity_score, 4),
        field_scores=field_scores,
        citation_score=round(citation_score, 3),
        latency_ms=getattr(result, "metadata", {}).get("latency_ms") or None,
    )
    return rs


# -------------------------------
# Aggregation and run-level metrics
# -------------------------------


def precision_at_k(result_scores: Sequence[ResultScore], k: int, threshold: float = 0.5) -> float:
    """Compute precision@k: fraction of the top-k results whose
    `text_similarity` or `citation_score` is >= threshold.

    A result counts as positive if either text_similarity >= threshold OR
    citation_score >= threshold.
    """
    if k <= 0:
        return 0.0
    top = list(result_scores)[:k]
    if not top:
        return 0.0
    positives = 0
    for r in top:
        if (r.text_similarity >= threshold) or (r.citation_score >= threshold):
            positives += 1
    return positives / len(top)


def recall_at_k(result_scores: Sequence[ResultScore], k: int, threshold: float = 0.5) -> float:
    """Compute recall@k relative to a single ground-truth entity.

    Since we score results for a single target, recall@k is equivalent to
    whether a correct (thresholded) result appears in the top-k. We return
    1.0 if any of the top-k satisfies the threshold, else 0.0.
    """
    if k <= 0:
        return 0.0
    top = list(result_scores)[:k]
    for r in top:
        if (r.text_similarity >= threshold) or (r.citation_score >= threshold):
            return 1.0
    return 0.0


def f1_from_precision_recall(p: float, r: float) -> float:
    if p + r == 0:
        return 0.0
    return 2.0 * (p * r) / (p + r)


def aggregate_run_metrics(
    provider_response: ProviderResponse,
    truth: dict[str, Any],
    top_k: int = 5,
    threshold: float = 0.5,
    fields_to_check: Sequence[str] | None = None,
    text_weight: float = 0.5,
) -> dict[str, Any]:
    """Score a provider response (single query) against a ground-truth dict.

    Returns a dict with:
      - per_result: list of ResultScore dicts (one per result)
      - precision@k, recall@k, f1@k
      - citation_coverage (fraction of top_k with a citation match > 0)
      - avg_latency_ms (if latency values present in result metadata)
    """
    # Be resilient if ProviderResponse is a plain dict
    provider_name = None
    query = truth.get("__query__", "")
    latency_values: list[float] = []

    if isinstance(provider_response, dict):
        provider_name = provider_response.get("provider", "")
        raw_results = provider_response.get("results", [])
    else:
        provider_name = (
            getattr(provider_response, "provider", "") or provider_response.__class__.__name__
        )
        raw_results = getattr(provider_response, "results", [])

    scored_results: list[ResultScore] = []
    for idx, rr in enumerate(raw_results, start=1):
        # rr may be dict-like or ProviderResult
        if isinstance(rr, dict):
            # adapt minimal fields expected by score_result_against_truth
            from types import SimpleNamespace

            rr_obj = SimpleNamespace(
                **{
                    "title": rr.get("title"),
                    "snippet": rr.get("snippet"),
                    "url": rr.get("url"),
                    "source": rr.get("source") or provider_name,
                    "metadata": rr.get("metadata", {"rank": idx}),
                }
            )
        else:
            rr_obj = rr

        # ensure rank metadata
        if not getattr(rr_obj, "metadata", None):
            rr_obj.metadata = {"rank": idx}
        else:
            if "rank" not in rr_obj.metadata:
                try:
                    rr_obj.metadata["rank"] = idx
                except Exception:
                    pass

        # pass through truth-aware query
        if isinstance(rr_obj.metadata, dict):
            rr_obj.metadata.setdefault("provider", provider_name)
            # optionally set latency_ms metadata if available on result
            if getattr(rr_obj, "latency_ms", None) is not None:
                rr_obj.metadata.setdefault("latency_ms", rr_obj.latency_ms)

        rs = score_result_against_truth(
            rr_obj, truth, fields_to_check=fields_to_check, text_weight=text_weight
        )
        # attach provider & query
        rs.provider = provider_name or rs.provider
        rs.query = query or rs.query or ""

        scored_results.append(rs)

        if rs.latency_ms:
            try:
                latency_values.append(float(rs.latency_ms))
            except Exception:
                pass

    # Metrics
    p_at_k = precision_at_k(scored_results, top_k, threshold)
    r_at_k = recall_at_k(scored_results, top_k, threshold)
    f1_at_k = f1_from_precision_recall(p_at_k, r_at_k)
    citation_cov = 0.0
    if scored_results:
        top = scored_results[:top_k]
        citation_cov = sum(1 for r in top if r.citation_score > 0.0) / len(top)

    avg_latency = float(sum(latency_values) / len(latency_values)) if latency_values else None

    return {
        "provider": provider_name,
        "query": query,
        "top_k": top_k,
        "threshold": threshold,
        "precision_at_k": round(p_at_k, 4),
        "recall_at_k": round(r_at_k, 4),
        "f1_at_k": round(f1_at_k, 4),
        "citation_coverage_top_k": round(citation_cov, 4),
        "avg_latency_ms": round(avg_latency, 2) if avg_latency is not None else None,
        "per_result": [r.to_dict() for r in scored_results],
    }


# -------------------------------
# Helpers for batch/runs
# -------------------------------


def score_provider_run(
    provider_responses: Iterable[ProviderResponse],
    truths: Iterable[dict[str, Any]],
    top_k: int = 5,
    threshold: float = 0.5,
    fields_to_check: Sequence[str] | None = None,
    text_weight: float = 0.5,
) -> dict[str, Any]:
    """Score a sequence of provider responses against an aligned sequence of truths.

    Both iterables must be in the same order and have the same length; each
    provider response is scored against the corresponding truth dict.

    Returns:
        A dict containing per-query metrics and aggregated summary:
          - items: list of individual aggregate_run_metrics() outputs
          - summary: averages across the run (precision@k, recall@k, f1@k,
            citation coverage, avg_latency)
    """
    items = []
    total_p = 0.0
    total_r = 0.0
    total_f1 = 0.0
    total_citation = 0.0
    latency_vals: list[float] = []
    count = 0

    for pr, truth in zip(provider_responses, truths, strict=False):
        m = aggregate_run_metrics(
            pr,
            truth,
            top_k=top_k,
            threshold=threshold,
            fields_to_check=fields_to_check,
            text_weight=text_weight,
        )
        items.append(m)
        total_p += m.get("precision_at_k", 0.0)
        total_r += m.get("recall_at_k", 0.0)
        total_f1 += m.get("f1_at_k", 0.0)
        total_citation += m.get("citation_coverage_top_k", 0.0)
        if m.get("avg_latency_ms") is not None:
            latency_vals.append(float(m["avg_latency_ms"]))
        count += 1

    if count == 0:
        return {"items": [], "summary": {}}

    summary = {
        "n": count,
        "avg_precision_at_k": round(total_p / count, 4),
        "avg_recall_at_k": round(total_r / count, 4),
        "avg_f1_at_k": round(total_f1 / count, 4),
        "avg_citation_coverage_top_k": round(total_citation / count, 4),
        "avg_latency_ms": round(sum(latency_vals) / len(latency_vals), 2) if latency_vals else None,
    }

    return {"items": items, "summary": summary}
