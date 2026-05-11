"""Company categorization enricher: USAspending contract retrieval.

Retrieves federal contract portfolios for SBIR companies so they can be
categorized as Product/Service/Mixed firms. SBIR/STTR awards are excluded
from the categorization signal (they reflect R&D, not the company's core
business model) but can be retrieved separately for reporting.

Two retrieval paths exist for both contracts and SBIR awards: a DuckDB
query against a local USAspending dump, and an HTTP fallback against the
USAspending API. The API path also tries autocomplete-based fuzzy name
matching when UEI/DUNS are missing or wrong.

Public functions:
    retrieve_company_contracts, retrieve_company_contracts_api
    retrieve_sbir_awards,        retrieve_sbir_awards_api
    batch_retrieve_company_contracts
"""

import re
from collections.abc import Iterator
from typing import Any

import pandas as pd
from loguru import logger

from sbir_etl.config.loader import get_config
from sbir_etl.enrichers.usaspending import USAspendingAPIClient
from sbir_etl.enrichers.usaspending.client import CONTRACT_TYPE_CODES
from sbir_etl.exceptions import APIError, RateLimitError
from sbir_etl.extractors.usaspending import DuckDBUSAspendingExtractor
from sbir_etl.utils.async_tools import run_sync
from sbir_etl.utils.cache.api_cache import APICache


PSC_DETAIL_LOOKUP_LIMIT = 50
MAX_PAGES = 1000
MAX_RECORDS = 100_000

SBIR_KEYWORDS = ("SBIR", "STTR", "SMALL BUSINESS INNOVATION", "SMALL BUSINESS TECH")
_SBIR_SQL_PREDICATE = " OR ".join(
    f"UPPER(award_description) LIKE '%{k}%'" for k in SBIR_KEYWORDS
)
_SBIR_REGEX = re.compile("|".join(SBIR_KEYWORDS))

_IDENTIFIER_COLUMNS = {
    "uei": ("recipient_uei", "awardee_or_recipient_uei"),
    "duns": ("recipient_duns", "awardee_or_recipient_uniqu"),
    "cage": ("cage_code", "vendor_doing_as_business_n"),
}

_TRANSACTION_FIELDS = [
    "Award ID",
    "Recipient Name",
    "Transaction Amount",
    "Transaction Description",
    "Action Date",
    "PSC",
    "Recipient UEI",
    "Award Type",
    "Awarding Agency",
    "Awarding Sub Agency",
    "internal_id",
]


# ---------------------------------------------------------------------------
# Identifier and name helpers
# ---------------------------------------------------------------------------


def _is_valid_identifier(value: Any) -> bool:
    """True if value is a non-empty identifier (not None, NaN, 'nan', etc.)."""
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    if isinstance(value, str) and value.strip().lower() in ("", "nan", "none", "null"):
        return False
    return True


_NAME_ABBREVIATIONS = {
    r"\bIntl\.?\b": "International",
    r"\bInt\'l\.?\b": "International",
    r"\bInc\.?\b": "Incorporated",
    r"\bCo\.?\b": "Company",
    r"\bCorp\.?\b": "Corporation",
    r"\bLtd\.?\b": "Limited",
    r"\bLLC\.?\b": "Limited Liability Company",
    r"\bLLP\.?\b": "Limited Liability Partnership",
    r"\bL\.?L\.?C\.?\b": "Limited Liability Company",
    r"\bL\.?P\.?\b": "Limited Partnership",
    r"\bTech\.?\b": "Technology",
    r"\bMfg\.?\b": "Manufacturing",
    r"\bSys\.?\b": "Systems",
    r"\bSvcs\.?\b": "Services",
    r"\bMgmt\.?\b": "Management",
    r"\bDev\.?\b": "Development",
}

_SUFFIX_STRIPS = [
    re.compile(
        r",?\s*(Inc\.?|Incorporated|LLC|L\.L\.C\.?|Ltd\.?|Limited|Corp\.?|Corporation|Company|Co\.?)$",
        re.IGNORECASE,
    ),
    re.compile(r",?\s*\([^)]+\)$"),
]


def _normalize_company_name_for_search(company_name: str) -> list[str]:
    """Generate name variations for fuzzy matching, ordered most→least specific."""
    if not company_name or not isinstance(company_name, str):
        return []

    variations: list[str] = [company_name.strip()]

    expanded = company_name
    for pattern, repl in _NAME_ABBREVIATIONS.items():
        expanded = re.sub(pattern, repl, expanded, flags=re.IGNORECASE)
    if expanded != company_name:
        variations.append(expanded.strip())

    normalized = expanded.replace("/", " AND ").replace("&", " AND ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized and normalized not in variations:
        variations.append(normalized)

    base = normalized
    for pattern in _SUFFIX_STRIPS:
        base = pattern.sub("", base)
    base = base.strip().rstrip(",").strip()
    if base and len(base) >= 10 and base not in variations:
        variations.append(base)

    significant = [w for w in base.split() if len(w) > 2]
    if len(significant) >= 3:
        core = " ".join(significant[:5])
        if len(core) >= 10 and core not in variations:
            variations.append(core)

    # Add uppercase variants of the first few (USAspending often uppercases names).
    upper_variants = [v.upper() for v in variations[:3] if v != v.upper() and len(v) >= 5]
    variations = variations[:3] + upper_variants + variations[3:]

    # Dedupe case-insensitively, preferring uppercase forms.
    seen: dict[str, str] = {}
    for v in variations:
        if len(v) < 5:
            continue
        key = v.lower()
        if key not in seen or (v.isupper() and not seen[key].isupper()):
            seen[key] = v
    return list(dict.fromkeys(seen[v.lower()] for v in variations if len(v) >= 5))


def _extract_sbir_phase(description: str | None) -> str | None:
    """Return SBIR phase ('I'/'II'/'III') if description references SBIR/STTR work."""
    if not description or not isinstance(description, str):
        return None
    desc = description.upper()
    if not any(k in desc for k in ("SBIR", "STTR", "SMALL BUSINESS", "INNOVATION", "RESEARCH")):
        return None
    # Order matters: match III before II before I.
    for pattern, phase in (
        (r"\bPHASE\s*(III|3)\b", "III"),
        (r"\bPHASE\s*(II|2)\b", "II"),
        (r"\bPHASE\s*(I|1)\b", "I"),
    ):
        if re.search(pattern, desc):
            return phase
    return None


def _build_identifier_where_clause(
    uei: str | None, duns: str | None, cage: str | None
) -> str:
    """Build a DuckDB WHERE fragment matching any of the provided identifiers."""
    clauses = []
    for value, key in ((uei, "uei"), (duns, "duns"), (cage, "cage")):
        if not value:
            continue
        for col in _IDENTIFIER_COLUMNS[key]:
            clauses.append(f"{col} = '{value}'")
    return " OR ".join(clauses)


def _build_recipient_search_terms(
    uei: str | None, duns: str | None, name: str | None, *, valid_uei: bool, valid_duns: bool
) -> list[str]:
    terms: list[str] = []
    if valid_uei and uei:
        terms.append(uei)
    if valid_duns and duns:
        terms.append(duns)
    if name and _is_valid_identifier(name):
        terms.append(name)
    return terms


# ---------------------------------------------------------------------------
# Cache initialization
# ---------------------------------------------------------------------------


def _init_api_cache(config: Any, default_type: str = "contracts") -> APICache:
    try:
        cfg = config or get_config()
        c = cfg.enrichment_refresh.usaspending.cache
        ttl_hours = c.ttl_hours if c.ttl_hours is not None else (c.ttl_seconds // 3600)
        return APICache(
            cache_dir=c.cache_dir,
            enabled=c.enabled,
            ttl_hours=ttl_hours,
            default_cache_type=default_type,
        )
    except Exception as e:
        logger.debug(f"Could not initialize cache, proceeding without caching: {e}")
        return APICache(
            cache_dir="data/cache/usaspending",
            enabled=False,
            default_cache_type=default_type,
        )


# ---------------------------------------------------------------------------
# Autocomplete fuzzy matching
# ---------------------------------------------------------------------------


def _fuzzy_match_recipient(
    company_name: str, client: USAspendingAPIClient
) -> dict[str, Any] | None:
    """Search USAspending autocomplete for the best recipient match."""
    if not company_name or not isinstance(company_name, str):
        return None

    variations = _normalize_company_name_for_search(company_name)
    if not variations:
        return None

    fallback: dict[str, Any] | None = None
    for idx, search_name in enumerate(variations, 1):
        try:
            data = run_sync(client.autocomplete_recipient(search_name, limit=5))
        except RateLimitError as e:
            logger.warning(f"Rate limit during autocomplete for '{search_name}': {e}")
            break
        except APIError as e:
            logger.debug(f"Autocomplete error for '{search_name}': {e}")
            continue

        results = data.get("results") or []
        if not results:
            continue

        best = results[0]
        match = {
            "uei": best.get("uei"),
            "name": best.get("legal_business_name", ""),
            "duns": best.get("duns"),
        }

        if _is_valid_identifier(match["uei"]) or _is_valid_identifier(match["duns"]):
            logger.info(
                f"Autocomplete matched '{company_name}'"
                f"{f' via variation #{idx}' if idx > 1 else ''} → "
                f"'{match['name']}' (UEI: {match['uei']})"
            )
            return match

        if _is_valid_identifier(match["name"]) and fallback is None:
            fallback = match

    if fallback:
        logger.info(
            f"Autocomplete matched '{company_name}' to name "
            f"'{fallback['name']}' (no UEI/DUNS); will use matched name for search"
        )
    return fallback


# ---------------------------------------------------------------------------
# Transaction pagination + processing (API path)
# ---------------------------------------------------------------------------


def _iter_transactions(
    client: USAspendingAPIClient,
    filters: dict[str, Any],
    fields: list[str],
    page_size: int,
) -> Iterator[dict[str, Any]]:
    """Yield raw transaction dicts from spending_by_transaction, paginated."""
    page = 1
    yielded = 0
    while page <= MAX_PAGES:
        try:
            data = run_sync(
                client.search_transactions(
                    filters=filters,
                    fields=fields,
                    page=page,
                    limit=page_size,
                    sort="Transaction Amount",
                    order="desc",
                )
            )
        except RateLimitError as e:
            logger.error(f"Rate limit on page {page}: {e}")
            return
        except APIError as e:
            logger.error(f"API error on page {page}: {e}")
            return

        results = data.get("results") or []
        if not results:
            return

        for t in results:
            yield t
            yielded += 1
            if yielded >= MAX_RECORDS:
                logger.warning(
                    f"Reached MAX_RECORDS ({MAX_RECORDS}); stopping pagination at page {page}"
                )
                return

        if not data.get("page_metadata", {}).get("hasNext", False):
            return
        page += 1

    logger.warning(f"Reached MAX_PAGES ({MAX_PAGES}); stopping pagination")


def _extract_psc(transaction: dict[str, Any]) -> str | None:
    raw = transaction.get("PSC")
    if isinstance(raw, dict):
        return raw.get("code") or raw.get("psc_code") or raw.get("psc")
    if isinstance(raw, str):
        return raw or None
    return None


def _process_transaction(
    t: dict[str, Any],
    *,
    uei: str | None,
    duns: str | None,
    client: USAspendingAPIClient,
    psc_lookups_used: list[int],
    index: int,
) -> dict[str, Any]:
    """Normalize a raw transaction dict; fetch PSC details if missing (bounded)."""
    award_id = t.get("Award ID") or t.get("internal_id") or f"UNKNOWN_{index}"
    psc = _extract_psc(t)
    if not psc and psc_lookups_used[0] < PSC_DETAIL_LOOKUP_LIMIT:
        detail = _fetch_award_details(award_id, client)
        if detail and detail.get("psc"):
            psc = detail["psc"]
            psc_lookups_used[0] += 1

    return {
        "award_id": award_id,
        "psc": psc,
        "contract_type": t.get("Award Type"),
        "pricing": t.get("Award Type"),
        "description": t.get("Transaction Description"),
        "award_amount": t.get("Transaction Amount", 0),
        "recipient_uei": t.get("Recipient UEI") or uei,
        "recipient_duns": duns,
        "action_date": t.get("Action Date"),
        "award_type": t.get("Award Type"),
        "awarding_agency": t.get("Awarding Agency"),
        "awarding_sub_agency": t.get("Awarding Sub Agency"),
    }


def _fetch_award_details(
    award_id: str, client: USAspendingAPIClient
) -> dict[str, Any] | None:
    """Fetch PSC code from the per-award endpoint as a fallback."""
    try:
        data = run_sync(client.fetch_award_details(award_id))
    except RateLimitError as e:
        logger.warning(f"Rate limit fetching details for {award_id}: {e}")
        return None
    except APIError as e:
        logger.warning(f"API error fetching details for {award_id}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error fetching details for {award_id}: {e}")
        return None

    if not isinstance(data, dict):
        return None

    psc = (data.get("latest_transaction_contract_data") or {}).get("product_or_service_code")
    if not psc:
        psc = (
            data.get("product_or_service_code")
            or data.get("psc")
            or (data.get("latest_transaction") or {}).get("product_or_service_code")
            or (data.get("contract_data") or {}).get("product_or_service_code")
            or (data.get("base_transaction") or {}).get("product_or_service_code")
        )
    if not psc:
        logger.warning(
            f"PSC not found for award {award_id}. Keys: {list(data.keys())[:10]}"
        )
        return None
    return {"psc": psc}


# ---------------------------------------------------------------------------
# DuckDB path (local USAspending dump)
# ---------------------------------------------------------------------------


def _query_awards_duckdb(
    extractor: DuckDBUSAspendingExtractor,
    *,
    uei: str | None,
    duns: str | None,
    cage: str | None,
    table_name: str,
    sbir_only: bool,
) -> pd.DataFrame:
    if not any([uei, duns, cage]):
        logger.warning("No company identifiers provided, returning empty DataFrame")
        return pd.DataFrame()

    where_clause = _build_identifier_where_clause(uei, duns, cage)
    sbir_filter = (
        f"AND ({_SBIR_SQL_PREDICATE})"
        if sbir_only
        else f"AND (award_description IS NULL OR NOT ({_SBIR_SQL_PREDICATE}))"
    )
    select_cols = (
        # SBIR-only path returns a smaller projection used for reporting.
        """COALESCE(award_id_piid, piid, fain, uri, award_id) as award_id,
           award_description as description,
           CAST(federal_action_obligation as DOUBLE) as award_amount,
           action_date, fiscal_year"""
        if sbir_only
        else """COALESCE(award_id_piid, piid, fain, uri, award_id) as award_id,
                product_or_service_code as psc,
                type_of_contract_pricing as contract_type,
                type_of_contract_pricing as pricing,
                award_description as description,
                CAST(federal_action_obligation as DOUBLE) as award_amount,
                recipient_uei, awardee_or_recipient_uei,
                COALESCE(recipient_duns, awardee_or_recipient_uniqu) as recipient_duns,
                cage_code, action_date, fiscal_year"""
    )

    query = f"""
    SELECT {select_cols}
    FROM {table_name}
    WHERE ({where_clause})
      AND federal_action_obligation IS NOT NULL
      AND federal_action_obligation != 0
      {sbir_filter}
    """

    try:
        result = extractor.connect().execute(query).fetchdf()
    except Exception as e:
        logger.error(
            f"Failed to query USAspending (UEI={uei}, DUNS={duns}, CAGE={cage}): {e}"
        )
        return pd.DataFrame()

    if result.empty:
        return pd.DataFrame()

    if not sbir_only and {"recipient_uei", "awardee_or_recipient_uei"}.issubset(result.columns):
        result["recipient_uei"] = result["recipient_uei"].fillna(
            result["awardee_or_recipient_uei"]
        )
        result = result.drop(columns=["awardee_or_recipient_uei"])

    result = result[result["award_id"].notna()]
    result["award_amount"] = pd.to_numeric(result["award_amount"], errors="coerce")
    if not sbir_only:
        result["sbir_phase"] = result["description"].apply(_extract_sbir_phase)
    result = result.drop_duplicates(subset=["award_id"])

    logger.info(
        f"Retrieved {len(result)} {'SBIR/STTR' if sbir_only else 'non-SBIR'} "
        f"awards (UEI={uei}, DUNS={duns}, CAGE={cage})"
    )
    return result


def retrieve_company_contracts(
    extractor: DuckDBUSAspendingExtractor,
    uei: str | None = None,
    duns: str | None = None,
    cage: str | None = None,
    table_name: str = "usaspending_awards",
) -> pd.DataFrame:
    """Retrieve all non-SBIR federal contracts for a company from a USAspending dump."""
    return _query_awards_duckdb(
        extractor, uei=uei, duns=duns, cage=cage, table_name=table_name, sbir_only=False
    )


def retrieve_sbir_awards(
    extractor: DuckDBUSAspendingExtractor,
    uei: str | None = None,
    duns: str | None = None,
    cage: str | None = None,
    table_name: str = "usaspending_awards",
) -> pd.DataFrame:
    """Retrieve only SBIR/STTR awards for a company (reporting; not categorization)."""
    return _query_awards_duckdb(
        extractor, uei=uei, duns=duns, cage=cage, table_name=table_name, sbir_only=True
    )


# ---------------------------------------------------------------------------
# API path (USAspending HTTP)
# ---------------------------------------------------------------------------


def _description_is_sbir(desc: str | None) -> bool:
    if not desc:
        return False
    return bool(_SBIR_REGEX.search(desc.upper()))


def _query_awards_api(
    *,
    uei: str | None,
    duns: str | None,
    company_name: str | None,
    page_size: int,
    config: Any,
    client: USAspendingAPIClient | None,
    sbir_only: bool,
) -> pd.DataFrame:
    valid_uei = _is_valid_identifier(uei)
    valid_duns = _is_valid_identifier(duns)
    valid_name = _is_valid_identifier(company_name)

    if not any([valid_uei, valid_duns, valid_name]):
        logger.warning("No valid company identifiers; returning empty DataFrame")
        return pd.DataFrame()

    cache_type = "sbir" if sbir_only else "contracts"
    cache = _init_api_cache(config, default_type=cache_type)
    cached = cache.get(uei=uei, duns=duns, company_name=company_name, cache_type=cache_type)
    if cached is not None:
        logger.debug(
            f"Cache hit for {cache_type} (UEI={uei}, DUNS={duns}, name={company_name})"
        )
        return cached

    if client is None:
        client = USAspendingAPIClient()

    # Fuzzy-match by name when we lack a usable UEI/DUNS.
    matched_name: str | None = None
    if not (valid_uei or valid_duns) and valid_name and company_name:
        match = _fuzzy_match_recipient(company_name, client)
        if match:
            if _is_valid_identifier(match["uei"]):
                uei, valid_uei = match["uei"], True
            if _is_valid_identifier(match["duns"]):
                duns, valid_duns = match["duns"], True
            if not (valid_uei or valid_duns) and _is_valid_identifier(match["name"]):
                matched_name = match["name"]
                company_name = matched_name

    filters: dict[str, Any] = {"award_type_codes": list(CONTRACT_TYPE_CODES)}
    terms = _build_recipient_search_terms(
        uei, duns, matched_name or company_name, valid_uei=valid_uei, valid_duns=valid_duns
    )
    if terms:
        filters["recipient_search_text"] = terms

    fields = (
        ["Award ID", "Transaction Amount", "Transaction Description", "Action Date", "internal_id"]
        if sbir_only
        else _TRANSACTION_FIELDS
    )

    psc_lookups = [0]  # mutable counter for _process_transaction

    def fetch(active_filters: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for raw in _iter_transactions(client, active_filters, fields, page_size):
            if sbir_only:
                # For SBIR-only, filter by description and use a compact projection.
                desc = raw.get("Transaction Description") or ""
                if not _description_is_sbir(desc):
                    continue
                out.append(
                    {
                        "award_id": raw.get("Award ID") or raw.get("internal_id"),
                        "description": desc,
                        "award_amount": raw.get("Transaction Amount", 0),
                        "action_date": raw.get("Action Date"),
                    }
                )
            else:
                out.append(
                    _process_transaction(
                        raw, uei=uei, duns=duns, client=client,
                        psc_lookups_used=psc_lookups, index=len(out),
                    )
                )
        return out

    transactions = fetch(filters)

    # Non-SBIR fallback: if we searched by UEI/DUNS and got nothing, retry by name variations.
    if not transactions and not sbir_only and (valid_uei or valid_duns) and valid_name:
        logger.info(f"No transactions via UEI/DUNS; retrying with name search: {company_name}")
        name_variations = _normalize_company_name_for_search(company_name or "")
        name_terms = [v for v in name_variations[:3] if len(v) >= 10] or (
            [company_name] if company_name else []
        )
        if name_terms:
            transactions = fetch(
                {**filters, "recipient_search_text": name_terms}
            )

    if not transactions:
        logger.warning(
            f"No {'SBIR' if sbir_only else 'non-SBIR'} transactions found "
            f"(UEI={uei}, DUNS={duns}, name={company_name})"
        )
        return pd.DataFrame()

    df = pd.DataFrame(transactions)

    # Non-SBIR path: exclude any straggling SBIR/STTR rows that snuck through search.
    if not sbir_only:
        before = len(df)
        df = df[df["description"].isna() | ~df["description"].fillna("").str.upper().str.contains(
            _SBIR_REGEX, regex=True, na=False
        )]
        if (filtered := before - len(df)) > 0:
            logger.info(f"Filtered {filtered}/{before} SBIR-tagged rows from contract results")
        if df.empty:
            return pd.DataFrame()
        df["sbir_phase"] = df["description"].apply(_extract_sbir_phase)
        psc_count = (~df["psc"].isna()).sum()
        logger.info(f"PSC coverage: {psc_count}/{len(df)} ({psc_count / len(df) * 100:.1f}%)")

    df["award_amount"] = pd.to_numeric(df["award_amount"], errors="coerce")
    df = df.drop_duplicates(subset=["award_id"])
    logger.info(f"Processed {len(df)} unique {'SBIR' if sbir_only else 'contract'} rows")

    cache.set(df, uei=uei, duns=duns, company_name=company_name, cache_type=cache_type)
    return df


def retrieve_company_contracts_api(
    uei: str | None = None,
    duns: str | None = None,
    company_name: str | None = None,
    page_size: int = 100,
    config: Any = None,
    client: USAspendingAPIClient | None = None,
) -> pd.DataFrame:
    """Retrieve all non-SBIR contracts for a company from the USAspending API.

    Tries UEI/DUNS first, then autocomplete fuzzy name match, then direct
    name-variant search as a last resort. Fetches PSC codes via per-award
    detail lookups (capped) when the transaction endpoint omits them.
    """
    return _query_awards_api(
        uei=uei,
        duns=duns,
        company_name=company_name,
        page_size=page_size,
        config=config,
        client=client,
        sbir_only=False,
    )


def retrieve_sbir_awards_api(
    uei: str | None = None,
    duns: str | None = None,
    company_name: str | None = None,
    page_size: int = 100,
    config: Any = None,
    client: USAspendingAPIClient | None = None,
) -> pd.DataFrame:
    """Retrieve only SBIR/STTR awards via the USAspending API (reporting only)."""
    return _query_awards_api(
        uei=uei,
        duns=duns,
        company_name=company_name,
        page_size=page_size,
        config=config,
        client=client,
        sbir_only=True,
    )


# ---------------------------------------------------------------------------
# Batch helper
# ---------------------------------------------------------------------------


def batch_retrieve_company_contracts(
    extractor: DuckDBUSAspendingExtractor,
    companies: pd.DataFrame,
    uei_col: str = "company_uei",
    duns_col: str = "company_duns",
    cage_col: str = "company_cage",
    batch_size: int = 100,
) -> dict[str, pd.DataFrame]:
    """Retrieve contracts for many companies; keyed by UEI/DUNS/CAGE."""
    results: dict[str, pd.DataFrame] = {}
    total = len(companies)
    for i in range(0, total, batch_size):
        batch = companies.iloc[i : i + batch_size]
        logger.info(
            f"Processing batch {i // batch_size + 1} ({i + 1}-{min(i + batch_size, total)} of {total})"
        )
        for _, company in batch.iterrows():
            uei = company.get(uei_col) if uei_col in company else None
            duns = company.get(duns_col) if duns_col in company else None
            cage = company.get(cage_col) if cage_col in company else None
            key = uei or duns or cage
            if not key:
                logger.warning("Company has no identifiers, skipping")
                continue
            results[key] = retrieve_company_contracts(extractor, uei=uei, duns=duns, cage=cage)
    logger.info(f"Retrieved contracts for {len(results)} companies")
    return results
