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
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

_API_BASE = "https://api.usaspending.gov/api/v2"
_USER_AGENT = "SBIR-Analytics/1.0"
_PAGE_LIMIT = 100  # max per page
_SSL_CTX: ssl.SSLContext | None = None  # lazily initialized


# ═══════════════════════════════════════════════════════════════════════
# Parquet-based path
# ═══════════════════════════════════════════════════════════════════════

def build_commercialization_from_usaspending(
    transaction_path: str | Path,
    evaluation_fy: int = 2026,
    *,
    lookback_years: int = 10,
    exclude_recent_years: int = 2,
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
) -> pd.DataFrame:
    """Fetch obligation data from the USAspending API for each SBIR company.

    Queries ``/search/spending_by_transaction/`` once per unique UEI found
    in *awards_df*, filtered to procurement contract types within the
    commercialization FY window.  Results are aggregated into the same
    ``commercialization_df`` schema the evaluator expects.

    Parameters
    ----------
    awards_df :
        SBIR awards DataFrame (same one passed to the evaluator).
    evaluation_fy :
        Fiscal year being evaluated.
    lookback_years / exclude_recent_years :
        Commercialization window parameters.
    rate_limit_delay :
        Seconds to wait between API calls (default 0.6 ≈ 100 req/min).
    cache_path :
        Optional path to a JSON cache file.  If it exists, cached results
        are loaded and only missing UEIs are fetched.  New results are
        appended and written back.

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

    results: dict[str, float] = {}
    queried = 0
    cached_hits = 0
    errors = 0

    for i, uei in enumerate(ueis, 1):
        # Check cache first
        if uei in cache:
            results[uei] = cache[uei]
            cached_hits += 1
            continue

        if queried > 0:
            time.sleep(rate_limit_delay)

        total = _fetch_obligations_for_uei(uei, date_start, date_end)
        queried += 1

        if total is not None:
            results[uei] = total
            cache[uei] = total
        else:
            errors += 1

        if i % 25 == 0 or i == len(ueis):
            print(
                f"  Progress: {i}/{len(ueis)} "
                f"({cached_hits} cached, {queried} queried, {errors} errors)"
            )

    # Save cache
    if cache_path:
        cache_path = Path(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(cache, f, indent=2)
        print(f"  Cache saved to {cache_path}")

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


def _fetch_obligations_for_uei(
    uei: str,
    date_start: str,
    date_end: str,
) -> float | None:
    """Query the USAspending API for total obligation amount for a single UEI.

    Paginates through all results and sums ``Transaction Amount``.
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
            "fields": ["Transaction Amount", "Recipient UEI"],
            "sort": "Transaction Amount",
            "order": "desc",
            "page": page,
            "limit": _PAGE_LIMIT,
        }

        try:
            data = _api_post("/search/spending_by_transaction/", payload)
        except Exception as e:
            print(f"    API error for UEI {uei}: {e}", file=sys.stderr)
            return None

        results = data.get("results", [])
        for txn in results:
            amount = txn.get("Transaction Amount")
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
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 ** (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...", file=sys.stderr)
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
