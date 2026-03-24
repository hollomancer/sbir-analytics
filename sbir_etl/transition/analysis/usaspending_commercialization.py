"""Build a commercialization DataFrame from USAspending transaction data.

Supports two data sources:

1. **Parquet file** — from a prior :class:`ContractExtractor` run or S3 dump.
2. **USAspending API** — live queries against ``api.usaspending.gov/api/v2``
   using UEIs extracted from the SBIR awards DataFrame.

Both paths produce the ``commercialization_df`` schema that
:class:`BenchmarkEligibilityEvaluator` accepts.

USAspending obligation amounts are a proxy for the "sales and investment"
metric in the SBIR/STTR commercialization benchmark.  They capture the
federal side but do **not** include private capital or commercial revenue.

Typical usage::

    # From Parquet
    comm_df = build_commercialization_from_usaspending(
        transaction_path="data/usaspending/contracts.parquet",
        evaluation_fy=2026,
    )

    # From API
    comm_df = fetch_commercialization_from_api(
        awards_df=awards_df, evaluation_fy=2026,
    )
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

_API_BASE = "https://api.usaspending.gov/api/v2"
_USER_AGENT = "SBIR-Analytics/1.0"
_PAGE_LIMIT = 100  # max per page
_SSL_CTX: ssl.SSLContext | None = None  # lazily initialized
_CONCURRENCY = 10  # parallel API workers
_CACHE_SAVE_INTERVAL = 500  # save cache every N completed queries


# ═══════════════════════════════════════════════════════════════════════
# Parquet-based path
# ═══════════════════════════════════════════════════════════════════════

def build_commercialization_from_usaspending(
    transaction_path: str | Path,
    evaluation_fy: int = 2026,
    *,
    lookback_years: int = 10,
    exclude_recent_years: int = 2,
    uei_filter: set[str] | None = None,
) -> pd.DataFrame:
    """Aggregate USAspending transactions into per-company commercialization data.

    Parameters
    ----------
    transaction_path :
        Path to a Parquet file produced by :class:`ContractExtractor`.
        Expected columns: ``vendor_uei``, ``vendor_duns``, ``vendor_name``,
        ``obligation_amount``, ``start_date``.
    evaluation_fy :
        The fiscal year being evaluated (e.g. 2026).
    lookback_years :
        Number of years in the commercialization window (default 10).
    exclude_recent_years :
        Number of most-recent FYs to exclude (default 2).
    uei_filter :
        Optional set of UEIs to restrict aggregation to.  Rows whose
        vendor UEI is not in this set are dropped before aggregation.

    Returns
    -------
    pd.DataFrame
        Columns: ``company_id``, ``total_sales_and_investment``, ``patent_count``.
    """
    transaction_path = Path(transaction_path)
    df = pd.read_parquet(transaction_path)

    if "start_date" in df.columns:
        df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
        df["_fy"] = df["start_date"].dt.year + (df["start_date"].dt.month >= 10).astype(int)
    elif "action_date" in df.columns:
        df["action_date"] = pd.to_datetime(df["action_date"], errors="coerce")
        df["_fy"] = df["action_date"].dt.year + (df["action_date"].dt.month >= 10).astype(int)
    else:
        raise ValueError(
            "Transaction data must contain 'start_date' or 'action_date' column"
        )

    end_fy = evaluation_fy - exclude_recent_years
    start_fy = end_fy - lookback_years + 1
    df = df[(df["_fy"] >= start_fy) & (df["_fy"] <= end_fy)]

    if uei_filter is not None:
        uei_col = _first_present(df, ["vendor_uei", "uei", "UEI"])
        if uei_col:
            before = len(df)
            df = df[df[uei_col].astype(str).str.strip().isin(uei_filter)]
            print(f"  Filtered Parquet to {len(df):,} rows (from {before:,}) for {len(uei_filter)} candidate UEIs")

    if df.empty:
        return _empty_commercialization_df()

    df["_company_id"] = _resolve_company_id(df)
    df = df[df["_company_id"] != ""]

    amount_col = _first_present(df, ["obligation_amount", "federal_action_obligation"])
    if amount_col is None:
        raise ValueError(
            "Transaction data must contain 'obligation_amount' or "
            "'federal_action_obligation' column"
        )

    df[amount_col] = pd.to_numeric(df[amount_col], errors="coerce").fillna(0.0)

    agg = df.groupby("_company_id", as_index=False).agg(
        total_sales_and_investment=(amount_col, "sum"),
    )
    agg = agg.rename(columns={"_company_id": "company_id"})
    agg["patent_count"] = 0
    return agg


# ═══════════════════════════════════════════════════════════════════════
# API-based path
# ═══════════════════════════════════════════════════════════════════════

def fetch_commercialization_from_api(
    awards_df: pd.DataFrame,
    evaluation_fy: int = 2026,
    *,
    lookback_years: int = 10,
    exclude_recent_years: int = 2,
    rate_limit_delay: float = 0.6,
    cache_path: str | Path | None = None,
    concurrency: int = _CONCURRENCY,
    uei_filter: set[str] | None = None,
) -> pd.DataFrame:
    """Fetch obligation data from the USAspending API for each SBIR company.

    Queries ``/search/spending_by_transaction/`` once per unique UEI found
    in *awards_df*, filtered to procurement contract types within the
    commercialization FY window.  Results are aggregated into the same
    ``commercialization_df`` schema the evaluator expects.

    Uses concurrent workers (default 10) with a shared rate limiter to
    stay within API limits while completing in ~1/10th the time of
    sequential queries.

    Parameters
    ----------
    awards_df :
        SBIR awards DataFrame (same one passed to the evaluator).
    evaluation_fy :
        Fiscal year being evaluated.
    lookback_years / exclude_recent_years :
        Commercialization window parameters.
    rate_limit_delay :
        Minimum seconds between API calls *per worker* (default 0.6).
        With 10 workers this yields ~16 req/s overall.
    cache_path :
        Optional path to a JSON cache file.  If it exists, cached results
        are loaded and only missing UEIs are fetched.  New results are
        appended and written back periodically and at completion.
    concurrency :
        Number of parallel API workers (default 10).
    uei_filter :
        Optional set of UEIs to restrict queries to.  When provided, only
        these UEIs are queried (intersected with UEIs found in awards_df).
        Use with ``BenchmarkEligibilityEvaluator.get_commercialization_candidates()``
        to avoid querying companies that won't be subject to the benchmark.

    Returns
    -------
    pd.DataFrame
        Columns: ``company_id``, ``total_sales_and_investment``, ``patent_count``.
    """
    end_fy = evaluation_fy - exclude_recent_years
    start_fy = end_fy - lookback_years + 1

    # Commercialization window as calendar dates (Oct start of fiscal year)
    date_start = f"{start_fy - 1}-10-01"
    date_end = f"{end_fy}-09-30"

    ueis = _extract_unique_ueis(awards_df)
    if uei_filter is not None:
        before = len(ueis)
        ueis = [u for u in ueis if u in uei_filter]
        print(f"  Filtered to {len(ueis)} UEIs (from {before} total, {len(uei_filter)} candidates)")
    if not ueis:
        print("  No UEIs found in awards data; cannot query API.", file=sys.stderr)
        return _empty_commercialization_df()

    print(f"  Unique UEIs to query: {len(ueis)}")
    print(f"  Commercialization window: {date_start} to {date_end}")

    # Load cache
    cache: dict[str, float] = {}
    if cache_path:
        cache_path = Path(cache_path)
        if cache_path.exists():
            with open(cache_path) as f:
                cache = json.load(f)
            print(f"  Loaded {len(cache)} cached results from {cache_path}")

    # Separate cached vs. uncached UEIs
    results: dict[str, float] = {}
    cached_hits = 0
    to_fetch: list[str] = []
    for uei in ueis:
        if uei in cache:
            results[uei] = cache[uei]
            cached_hits += 1
        else:
            to_fetch.append(uei)

    print(f"  Cache hits: {cached_hits}, remaining to fetch: {len(to_fetch)}")

    if not to_fetch:
        print("  All UEIs cached, skipping API queries.")
    else:
        # Rate limiter: controls overall request rate across all workers
        rate_lock = threading.Lock()
        last_request_time = [0.0]  # mutable container for closure
        completed = [0]
        errors = [0]
        since_last_save = [0]

        def _rate_limited_fetch(uei: str) -> tuple[str, float | None]:
            # Enforce minimum delay between requests globally
            with rate_lock:
                now = time.monotonic()
                elapsed = now - last_request_time[0]
                if elapsed < rate_limit_delay:
                    time.sleep(rate_limit_delay - elapsed)
                last_request_time[0] = time.monotonic()

            result = _fetch_obligations_for_uei(uei, date_start, date_end)

            with rate_lock:
                completed[0] += 1
                if result is None:
                    errors[0] += 1
                if completed[0] % 100 == 0 or completed[0] == len(to_fetch):
                    print(
                        f"  Progress: {cached_hits + completed[0]}/{len(ueis)} "
                        f"({cached_hits} cached, {completed[0]} queried, "
                        f"{errors[0]} errors)"
                    )

            return uei, result

        def _save_cache_if_needed() -> None:
            """Periodically persist cache to avoid losing progress."""
            if not cache_path:
                return
            with rate_lock:
                since_last_save[0] += 1
                if since_last_save[0] < _CACHE_SAVE_INTERVAL:
                    return
                since_last_save[0] = 0
            # Write outside the lock
            _write_cache(cache_path, cache)

        workers = min(concurrency, len(to_fetch))
        print(f"  Fetching with {workers} concurrent workers...")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_rate_limited_fetch, uei): uei
                for uei in to_fetch
            }
            for future in as_completed(futures):
                uei, total = future.result()
                if total is not None:
                    results[uei] = total
                    cache[uei] = total
                _save_cache_if_needed()

    # Final cache save
    if cache_path:
        _write_cache(cache_path, cache)
        print(f"  Cache saved to {cache_path} ({len(cache)} entries)")

    if not results:
        return _empty_commercialization_df()

    rows = [
        {
            "company_id": f"uei:{uei}",
            "total_sales_and_investment": amount,
            "patent_count": 0,
        }
        for uei, amount in results.items()
    ]
    return pd.DataFrame(rows)


def _write_cache(cache_path: Path, cache: dict[str, float]) -> None:
    """Write cache to disk atomically."""
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(cache, f, indent=2)
    tmp.replace(cache_path)


def _fetch_obligations_for_uei(
    uei: str,
    date_start: str,
    date_end: str,
) -> float | None:
    """Query the USAspending API for total obligation amount for a single UEI.

    Uses ``/search/spending_by_award/`` which returns award-level aggregates
    instead of individual transactions — far fewer rows and less server load.
    Paginates through all results and sums ``Award Amount``.
    Returns None on error.
    """
    total = 0.0
    page = 1

    while True:
        payload = {
            "filters": {
                "award_type_codes": ["A", "B", "C", "D"],
                "recipient_search_text": [uei],
                "time_period": [{"start_date": date_start, "end_date": date_end}],
            },
            "fields": [
                "Award Amount",
                "Recipient Name",
                "Recipient UEI",
                "Award ID",
                "Start Date",
            ],
            "sort": "Award Amount",
            "order": "desc",
            "page": page,
            "limit": _PAGE_LIMIT,
            "subawards": False,
        }

        try:
            data = _api_post("/search/spending_by_award/", payload)
        except Exception as e:
            print(f"    API error for UEI {uei}: {e}", file=sys.stderr)
            return None

        results = data.get("results", [])
        for award in results:
            amount = award.get("Award Amount")
            if amount is not None:
                try:
                    total += float(amount)
                except (ValueError, TypeError):
                    pass

        has_next = data.get("page_metadata", {}).get("hasNext", False)
        if not has_next or not results:
            break
        page += 1

    return total


def _get_ssl_context() -> ssl.SSLContext:
    """Build an SSL context, respecting env vars for custom CA bundles.

    Checks (in order):
    1. ``SSL_CERT_FILE`` — path to a CA bundle PEM file
    2. ``REQUESTS_CA_BUNDLE`` — same, used by requests/pip/etc.
    3. ``CURL_CA_BUNDLE`` — same, used by curl
    4. ``SSL_NO_VERIFY=1`` — disables verification entirely (last resort)
    5. Falls back to the system default context
    """
    global _SSL_CTX  # noqa: PLW0603
    if _SSL_CTX is not None:
        return _SSL_CTX

    ca_file = (
        os.environ.get("SSL_CERT_FILE")
        or os.environ.get("REQUESTS_CA_BUNDLE")
        or os.environ.get("CURL_CA_BUNDLE")
    )

    if os.environ.get("SSL_NO_VERIFY", "").strip() in ("1", "true", "yes"):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        print("  WARNING: SSL verification disabled (SSL_NO_VERIFY=1)", file=sys.stderr)
        _SSL_CTX = ctx
        return ctx

    if ca_file and Path(ca_file).is_file():
        ctx = ssl.create_default_context(cafile=ca_file)
        print(f"  Using custom CA bundle: {ca_file}", file=sys.stderr)
        _SSL_CTX = ctx
        return ctx

    _SSL_CTX = ssl.create_default_context()
    return _SSL_CTX


def _api_post(endpoint: str, payload: dict, *, retries: int = 3) -> dict:
    """POST to the USAspending API with retry logic.  Uses only stdlib."""
    url = f"{_API_BASE}{endpoint}"
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }
    ctx = _get_ssl_context()

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                wait = 2 ** (attempt + 1)
                label = "Rate limited" if e.code == 429 else f"Server error {e.code}"
                print(f"    {label}, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                last_exc = e
                continue
            raise
        except (urllib.error.URLError, OSError) as e:
            wait = 2 ** (attempt + 1)
            time.sleep(wait)
            last_exc = e
            continue

    raise RuntimeError(f"API request failed after {retries} retries: {last_exc}")


# ═══════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════

def _extract_unique_ueis(df: pd.DataFrame) -> list[str]:
    """Extract unique non-empty UEI values from an awards DataFrame."""
    uei_col = _first_present(df, ["UEI", "uei", "company_uei", "vendor_uei"])
    if uei_col is None:
        return []

    ueis = df[uei_col].dropna().astype(str).str.strip()
    ueis = ueis[
        (ueis != "") & (~ueis.isin(["None", "nan", "NaN"])) & (ueis.str.len() == 12)
    ]
    return sorted(ueis.unique().tolist())


def _empty_commercialization_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["company_id", "total_sales_and_investment", "patent_count"]
    )


def _resolve_company_id(df: pd.DataFrame) -> pd.Series:
    """Mirror the evaluator's company ID resolution: UEI > DUNS > name."""
    result = pd.Series("", index=df.index, dtype="object")

    uei_col = _first_present(df, ["vendor_uei", "uei", "UEI", "recipient_uei"])
    duns_col = _first_present(df, ["vendor_duns", "duns", "Duns", "recipient_duns"])
    name_col = _first_present(df, ["vendor_name", "recipient_name", "Company", "company_name"])

    if uei_col is not None:
        uei = df[uei_col].astype(str).str.strip()
        valid = (uei != "") & (~uei.isin(["None", "nan", "NaN"]))
        result = result.mask(valid, "uei:" + uei)
    if duns_col is not None:
        duns = df[duns_col].astype(str).str.strip()
        valid = (duns != "") & (~duns.isin(["None", "nan", "NaN"]))
        result = result.mask((result == "") & valid, "duns:" + duns)
    if name_col is not None:
        names = df[name_col].astype(str).str.strip().str.lower()
        valid = (names != "") & (~names.isin(["none", "nan"]))
        result = result.mask((result == "") & valid, "name:" + names)

    return result


def _first_present(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first column name from *candidates* that exists in *df*."""
    for col in candidates:
        if col in df.columns:
            return col
    return None
