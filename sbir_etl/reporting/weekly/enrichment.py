"""External-data enrichment for the weekly report.

Thin wrappers over sbir_etl.enrichers.* that add per-stage wall-clock
budgeting, shared rate limiting, and report-shaped aggregation."""

import os
import sys


from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.enrichers.inflation_adjuster import InflationAdjuster
from sbir_etl.enrichers.congressional_district_resolver import CongressionalDistrictResolver
from sbir_etl.enrichers.fiscal_bea_mapper import NAICSToBEAMapper
from sbir_etl.enrichers.pi_enrichment import (
    lookup_pi_patents_with_fallback as _lib_lookup_pi_patents_with_fallback,
    lookup_pi_publications_with_fallback as _lib_lookup_pi_publications_with_fallback,
    lookup_pi_orcid_with_fallback as _lib_lookup_pi_orcid_with_fallback,
)
from sbir_etl.enrichers.company_enrichment import (
    FederalAwardSummary as PIFederalAwardRecord,
    USARecipientProfile,
    SAMEntityRecord,
    lookup_company_federal_awards as _lib_lookup_company_federal_awards,
    lookup_usaspending_recipient_with_fallback as _lib_lookup_usaspending_recipient_with_fallback,
    lookup_sam_entity_with_fallback as _lib_lookup_sam_entity_with_fallback,
    fetch_usaspending_contract_descriptions as _lib_fetch_usaspending_contract_descriptions,
)
from sbir_etl.enrichers.opencorporates import CorporateRecord
from sbir_etl.enrichers.sync_wrappers import SyncOpenCorporatesClient, SyncPressWireClient
from sbir_etl.enrichers.press_wire import PressRelease

from sbir_etl.reporting.weekly.debug import _debug
from sbir_etl.reporting.weekly.fetching import _company_key
from sbir_etl.reporting.weekly.models import SolicitationTopic

# SolicitationExtractor was lost from the tree (import fails on main as of
# 2026-07 — see fetch_solicitation_topics). Optional so the report still runs;
# topics degrade to empty, same as --skip-sbir-api.
try:
    from sbir_etl.extractors.solicitation import SolicitationExtractor
except ImportError:
    SolicitationExtractor = None  # type: ignore[assignment,misc]


STAGE_TIMEOUT = int(os.environ.get("STAGE_TIMEOUT", "60"))


def _stage_deadline(budget_seconds: int | None = None) -> float:
    """Return a monotonic deadline for the current pipeline stage."""
    import time

    return time.monotonic() + (budget_seconds or STAGE_TIMEOUT)


def _past_deadline(deadline: float) -> bool:
    """Check if we've exceeded the stage deadline."""
    import time

    return time.monotonic() > deadline


_usaspending_limiter = RateLimiter(rate_limit_per_minute=120)


_semantic_scholar_limiter = RateLimiter(rate_limit_per_minute=100)


_sam_gov_limiter = RateLimiter(rate_limit_per_minute=60)


_orcid_limiter = RateLimiter(rate_limit_per_minute=60)


_opencorporates_limiter = RateLimiter(rate_limit_per_minute=30)  # Free tier ~500/month


_lens_limiter = RateLimiter(rate_limit_per_minute=50)  # Lens.org free tier


def lookup_pi_external_data(
    awards: list[dict],
    company_federal_awards: dict[str, PIFederalAwardRecord] | None = None,
) -> dict[str, dict]:
    """Look up external data (patents, publications, ORCID, federal awards) for each PI.

    If company_federal_awards is provided, reuses those results instead of
    re-querying USAspending for each PI's company.

    Returns a dict keyed by upper-cased PI name, with sub-keys:
    - "patents": PIPatentRecord | None
    - "publications": PIPublicationRecord | None
    - "orcid": ORCIDRecord | None
    - "federal_awards": PIFederalAwardRecord | None
    """
    # Collect unique PIs with their company context
    pis: dict[str, dict] = {}
    for a in awards:
        pi = str(a.get("PI Name", "")).strip()
        if not pi:
            continue
        key = pi.upper()
        if key not in pis:
            pis[key] = {
                "name": pi,
                "company": str(a.get("Company", "")).strip(),
                "uei": str(a.get("Company UEI", a.get("UEI", ""))).strip(),
                "company_key": _company_key(a),
            }

    results: dict[str, dict] = {}
    total = len(pis)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _lookup_single_pi(key: str, info: dict) -> tuple[str, dict]:
        name = info["name"]
        company = info["company"]
        uei = info["uei"] or None

        # Run the 3 independent API calls concurrently per PI
        # Use _with_fallback variants for cross-API resilience
        with ThreadPoolExecutor(max_workers=3) as inner:
            patent_future = inner.submit(
                _lib_lookup_pi_patents_with_fallback,
                name,
                company,
                lens_rate_limiter=_lens_limiter,
            )
            pub_future = inner.submit(
                _lib_lookup_pi_publications_with_fallback,
                name,
                rate_limiter=_semantic_scholar_limiter,
                orcid_rate_limiter=_orcid_limiter,
            )
            orcid_future = inner.submit(
                _lib_lookup_pi_orcid_with_fallback,
                name,
                rate_limiter=_orcid_limiter,
                semantic_scholar_rate_limiter=_semantic_scholar_limiter,
            )

            patents = patent_future.result()
            publications = pub_future.result()
            orcid_rec = orcid_future.result()

        # Reuse company federal awards if already fetched, else query fresh
        fed = None
        if company_federal_awards is not None:
            fed = company_federal_awards.get(info["company_key"])
        if fed is None and company_federal_awards is None:
            fed = _lib_lookup_company_federal_awards(
                company, uei, rate_limiter=_usaspending_limiter
            )

        return key, {
            "patents": patents,
            "publications": publications,
            "orcid": orcid_rec,
            "federal_awards": fed,
        }

    # Process PIs concurrently (capped at 4 to respect API rate limits)
    deadline = _stage_deadline()
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_lookup_single_pi, key, info): (key, info) for key, info in pis.items()
        }
        done = 0
        for future in as_completed(futures):
            if _past_deadline(deadline):
                print(
                    f"PI external data stage timeout ({STAGE_TIMEOUT}s) — "
                    f"completed {done}/{total}, skipping remainder",
                    file=sys.stderr,
                )
                executor.shutdown(wait=False, cancel_futures=True)
                break
            done += 1
            key, info = futures[future]
            try:
                pi_key, pi_data = future.result(timeout=10)
                results[pi_key] = pi_data
                print(
                    f"Completed PI external data {done}/{total}: {info['name']}",
                    file=sys.stderr,
                )
            except Exception as e:
                print(
                    f"PI external data error for {info['name']}: {e}",
                    file=sys.stderr,
                )

    return results


def lookup_usaspending_recipients(
    awards: list[dict],
) -> dict[str, USARecipientProfile]:
    """Look up USAspending recipient profiles for each unique company.

    Returns a dict keyed by upper-cased company name.
    """
    companies: dict[str, dict] = {}
    for a in awards:
        name = str(a.get("Company", "")).strip()
        if not name:
            continue
        key = name.upper()
        if key not in companies:
            companies[key] = {
                "name": name,
                "uei": str(a.get("Company UEI", a.get("UEI", ""))).strip() or None,
            }

    results: dict[str, USARecipientProfile] = {}
    total = len(companies)
    deadline = _stage_deadline(60)  # lighter budget — profile lookups are fast
    print(f"Looking up {total} recipient profiles on USAspending...", file=sys.stderr)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _lookup_one(item: tuple[str, dict]) -> tuple[str, USARecipientProfile | None]:
        key, info = item
        return key, _lib_lookup_usaspending_recipient_with_fallback(
            info["name"],
            info["uei"],
            rate_limiter=_usaspending_limiter,
            fallback_rate_limiter=_sam_gov_limiter,
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_lookup_one, item): item for item in companies.items()}
        for future in as_completed(futures):
            if _past_deadline(deadline):
                print(
                    f"USAspending recipient stage timeout — "
                    f"completed {len(results)}/{total}, skipping remainder",
                    file=sys.stderr,
                )
                executor.shutdown(wait=False, cancel_futures=True)
                break
            try:
                key, profile = future.result(timeout=10)
                if profile:
                    results[key] = profile
            except Exception as e:
                item = futures[future]
                print(
                    f"Warning: USAspending recipient lookup failed for {item[0]}: {e}",
                    file=sys.stderr,
                )

    print(f"Found {len(results)}/{total} recipient profiles on USAspending", file=sys.stderr)
    return results


def lookup_sam_entities(
    awards: list[dict],
) -> dict[str, SAMEntityRecord]:
    """Look up SAM.gov registration data for each unique company.

    Returns a dict keyed by upper-cased company name.
    """
    api_key = os.environ.get("SAM_GOV_API_KEY", "")
    if not api_key:
        print(
            "SAM_GOV_API_KEY not set — skipping SAM.gov entity lookups.",
            file=sys.stderr,
        )
        return {}

    companies: dict[str, dict] = {}
    for a in awards:
        name = str(a.get("Company", "")).strip()
        if not name:
            continue
        key = name.upper()
        if key not in companies:
            companies[key] = {
                "name": name,
                "uei": str(a.get("Company UEI", a.get("UEI", ""))).strip() or None,
                "cage": str(a.get("Company CAGE", a.get("CAGE", ""))).strip() or None,
            }

    results: dict[str, SAMEntityRecord] = {}
    total = len(companies)
    deadline = _stage_deadline()
    print(f"Looking up {total} companies on SAM.gov...", file=sys.stderr)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _lookup_one(item: tuple[str, dict]) -> tuple[str, SAMEntityRecord | None]:
        key, info = item
        return key, _lib_lookup_sam_entity_with_fallback(
            info["name"],
            info["uei"],
            info["cage"],
            rate_limiter=_sam_gov_limiter,
            fallback_rate_limiter=_usaspending_limiter,
        )

    # Cap at 3 workers to respect SAM.gov 60 req/min rate limit
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_lookup_one, item): item for item in companies.items()}
        for future in as_completed(futures):
            if _past_deadline(deadline):
                print(
                    f"SAM.gov stage timeout ({STAGE_TIMEOUT}s) — "
                    f"completed {len(results)}/{total}, skipping remainder",
                    file=sys.stderr,
                )
                executor.shutdown(wait=False, cancel_futures=True)
                break
            try:
                key, record = future.result(timeout=10)
                if record:
                    results[key] = record
            except Exception as e:
                item = futures[future]
                print(
                    f"Warning: SAM.gov entity lookup failed for {item[0]}: {e}",
                    file=sys.stderr,
                )

    print(f"Found {len(results)}/{total} companies on SAM.gov", file=sys.stderr)
    return results


def lookup_opencorporates(
    awards: list[dict],
) -> dict[str, CorporateRecord]:
    """Look up state corporation filings for each unique company.

    Returns a dict keyed by normalized company key.
    """
    companies: dict[str, dict] = {}
    for a in awards:
        name = str(a.get("Company", "")).strip()
        if not name:
            continue
        key = _company_key(a)
        if key not in companies:
            state = str(a.get("State", "")).strip().lower()
            # Map state abbreviation to OpenCorporates jurisdiction code
            jurisdiction = f"us_{state}" if len(state) == 2 else None
            companies[key] = {"name": name, "jurisdiction": jurisdiction}

    results: dict[str, CorporateRecord] = {}
    total = len(companies)
    deadline = _stage_deadline()
    print(f"Looking up {total} companies on OpenCorporates...", file=sys.stderr)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _lookup_one(item: tuple[str, dict]) -> tuple[str, CorporateRecord | None]:
        key, info = item
        with SyncOpenCorporatesClient(shared_limiter=_opencorporates_limiter) as client:
            return key, client.lookup_company(info["name"], jurisdiction=info["jurisdiction"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(_lookup_one, item): item for item in companies.items()}
        for future in as_completed(futures):
            if _past_deadline(deadline):
                print(
                    f"OpenCorporates stage timeout ({STAGE_TIMEOUT}s) — "
                    f"completed {len(results)}/{total}, skipping remainder",
                    file=sys.stderr,
                )
                executor.shutdown(wait=False, cancel_futures=True)
                break
            try:
                key, record = future.result(timeout=10)
                if record:
                    results[key] = record
            except Exception as e:
                item = futures[future]
                print(
                    f"Warning: OpenCorporates lookup failed for {item[0]}: {e}",
                    file=sys.stderr,
                )

    print(f"Found {len(results)}/{total} companies on OpenCorporates", file=sys.stderr)
    return results


def poll_press_wire(
    awards: list[dict],
) -> dict[str, list[PressRelease]]:
    """Poll press wire RSS feeds for mentions of awardee companies.

    Returns a dict keyed by normalized company key, with lists of
    matching press releases per company.
    """
    company_names: dict[str, str] = {}  # original name -> key
    for a in awards:
        name = str(a.get("Company", "")).strip()
        if not name:
            continue
        key = _company_key(a)
        if name not in company_names:
            company_names[name] = key

    print(f"Polling press wire feeds for {len(company_names)} companies...", file=sys.stderr)

    with SyncPressWireClient() as client:
        client.set_watchlist(list(company_names.keys()))
        hits = client.poll()

    # Group by company key
    results: dict[str, list[PressRelease]] = {}
    for hit in hits:
        co_key = company_names.get(hit.matched_company)
        if co_key:
            results.setdefault(co_key, []).append(hit)

    total_hits = sum(len(v) for v in results.values())
    print(
        f"Press wire: {total_hits} matching releases for {len(results)} companies",
        file=sys.stderr,
    )
    return results


def fetch_solicitation_topics(awards: list[dict]) -> dict[str, SolicitationTopic]:
    """Fetch solicitation topic titles and descriptions from SBIR.gov API.

    Uses SolicitationExtractor when available (tenacity retry, pagination,
    keyword search, awards fallback). Falls back to hand-rolled queries
    otherwise.
    """
    # Collect unique topic codes
    topic_codes: dict[str, str] = {}  # topic_code -> solicitation_number
    for a in awards:
        tc = str(a.get("Topic Code", "")).strip()
        sol = str(a.get("Solicitation Number", "")).strip()
        if tc and tc not in topic_codes:
            topic_codes[tc] = sol

    if not topic_codes:
        return {}

    if SolicitationExtractor is None:
        print(
            "SolicitationExtractor unavailable (sbir_etl.extractors.solicitation "
            "missing) — skipping solicitation topics",
            file=sys.stderr,
        )
        return {}

    results: dict[str, SolicitationTopic] = {}
    total = len(topic_codes)
    print(f"Fetching {total} solicitation topics from SBIR.gov...", file=sys.stderr)

    def _parse_year(sol: str) -> int | None:
        for part in sol.replace("-", " ").replace(".", " ").split():
            if part.isdigit() and len(part) == 4:
                return int(part)
        return None

    def _make_topic(tc: str, sol_num: str, topic: dict) -> SolicitationTopic:
        desc = topic.get("topicDescription") or topic.get("description")
        if desc and len(str(desc)) > 3000:
            desc = str(desc)[:3000] + "..."
        return SolicitationTopic(
            topic_code=tc,
            solicitation_number=(
                topic.get("solicitationNumber") or topic.get("solicitation_number") or sol_num
            ),
            title=topic.get("topicTitle") or topic.get("title") or "",
            description=str(desc) if desc else None,
            agency=topic.get("agency"),
            program=topic.get("program"),
        )

    _debug("Using SolicitationExtractor")
    extractor = SolicitationExtractor()
    try:
        # Group topic codes by year
        sol_years: dict[int, list[str]] = {}
        no_year_codes: list[tuple[str, str]] = []
        for tc, sol in topic_codes.items():
            year = _parse_year(sol)
            if year:
                sol_years.setdefault(year, []).append(tc)
            else:
                no_year_codes.append((tc, sol))

        # Step 1: Year-based batch queries
        import pandas as pd

        all_topics = pd.DataFrame()
        for year in sol_years:
            df = extractor.extract_topics(year=year, max_results=1000)
            if not df.empty:
                all_topics = pd.concat([all_topics, df], ignore_index=True)

        if not all_topics.empty:
            all_topics = extractor.deduplicate_topics(all_topics)
            codes_set = set(topic_codes.keys())
            for _, row in all_topics.iterrows():
                tc = str(row.get("topic_code", "")).strip()
                if tc in codes_set and tc not in results:
                    results[tc] = _make_topic(tc, topic_codes.get(tc, ""), row.to_dict())

        # Step 2: Keyword search for no-year codes
        for tc, sol in no_year_codes:
            if tc in results:
                continue
            keyword = sol if sol else tc
            topics = extractor.query_by_keyword(keyword)
            for topic in topics:
                found_tc = topic.get("topicCode") or topic.get("topic_code") or ""
                if found_tc == tc:
                    results[tc] = _make_topic(tc, sol, topic)
                    break

        # Step 3: Awards fallback for anything still missing
        missing = [tc for tc in topic_codes if tc not in results]
        if missing:
            _debug(f"Awards fallback for {len(missing)} missing topic codes")
            for tc in missing:
                fallback = extractor.query_awards_for_topic(tc)
                if fallback:
                    results[tc] = SolicitationTopic(
                        topic_code=tc,
                        solicitation_number=topic_codes.get(tc, ""),
                        title=fallback.get("title", ""),
                        description=(
                            str(fallback["description"])[:3000] + "..."
                            if fallback.get("description")
                            and len(str(fallback["description"])) > 3000
                            else fallback.get("description")
                        ),
                        agency=fallback.get("agency"),
                        program=fallback.get("program"),
                    )

        print(f"SolicitationExtractor found {len(results)}/{total} topics", file=sys.stderr)
    finally:
        extractor.close()

    return results


def fetch_usaspending_contract_descriptions(
    awards: list[dict],
) -> dict[str, str]:
    """Fetch contract descriptions from USAspending + FPDS fallback.

    Delegates to :func:`sbir_etl.enrichers.company_enrichment.fetch_usaspending_contract_descriptions`.
    """
    return _lib_fetch_usaspending_contract_descriptions(
        awards,
        rate_limiter=_usaspending_limiter,
    )


def enrich_with_inflation(awards: list[dict], base_year: int | None = None) -> dict[str, float]:
    """Compute an inflation-adjusted total using InflationAdjuster.

    Returns a dict containing:
    - 'adjusted_total': the sum of inflation-adjusted award amounts
    - 'base_year': the dollar year used for the adjustment

    Returns an empty dict if inflation adjustment fails or raises an exception.
    """
    import pandas as pd

    try:
        adjuster = InflationAdjuster(config={"base_year": base_year or 2024})
        df = pd.DataFrame(awards)
        # Map column names to what InflationAdjuster expects
        if "Award Amount" in df.columns:
            df["award_amount"] = (
                df["Award Amount"].astype(str).str.replace(",", "").str.replace("$", "")
            )
            df["award_amount"] = pd.to_numeric(df["award_amount"], errors="coerce").fillna(0)
        if "Proposal Award Date" in df.columns:
            df["award_date"] = df["Proposal Award Date"]

        enriched = adjuster.adjust_awards_dataframe(df)
        adjusted_col = "fiscal_adjusted_amount"
        if adjusted_col in enriched.columns:
            adjusted_total = enriched[adjusted_col].sum()
            base = enriched.get("fiscal_base_year", pd.Series([2024])).iloc[0]
            _debug(f"Inflation adjustment: ${adjusted_total:,.0f} in {base} dollars")
            return {
                "adjusted_total": float(adjusted_total),
                "base_year": int(base),
            }
    except Exception as e:
        _debug(f"InflationAdjuster error: {e}")

    return {}


def resolve_congressional_districts(awards: list[dict]) -> dict[str, str]:
    """Resolve congressional districts for each unique company.

    Returns a dict keyed by upper-cased company name → "ST-DD" district string.
    """
    results: dict[str, str] = {}
    resolver = CongressionalDistrictResolver(method="auto")

    seen: dict[str, dict] = {}
    for a in awards:
        name = str(a.get("Company", "")).strip()
        if not name:
            continue
        key = name.upper()
        if key not in seen:
            seen[key] = {
                "zip": str(a.get("Zip", "")).strip()[:5],
                "state": str(a.get("State", "")).strip(),
                "city": str(a.get("City", "")).strip(),
                "address": str(a.get("Address1", "")).strip(),
            }

    _debug(f"Resolving congressional districts for {len(seen)} companies")
    for key, info in seen.items():
        if not info["zip"]:
            _debug(f"Congressional district skip {key}: no ZIP code")
            continue
        try:
            result = resolver.resolve_single_address(
                address=info["address"] or None,
                city=info["city"] or None,
                state=info["state"] or None,
                zip_code=info["zip"],
            )
            if result and result.congressional_district:
                results[key] = result.congressional_district
            else:
                missing = [f for f in ("address", "city", "state", "zip") if not info.get(f)]
                _debug(
                    f"Congressional district miss {key}: "
                    f"zip={info['zip']} state={info['state']} "
                    f"missing=[{','.join(missing)}] method={result.method if result else 'none'}"
                )
        except Exception as e:
            _debug(f"Congressional district error {key}: {e}")
            continue

    _debug(f"Congressional districts resolved: {len(results)}/{len(seen)}")
    return results


def map_naics_to_bea_sectors(naics_codes: list[str]) -> dict[str, str]:
    """Map NAICS codes to BEA sector names.

    Returns a dict keyed by NAICS code → BEA sector name.
    """
    try:
        mapper = NAICSToBEAMapper(
            crosswalk_path=None,  # Will use fallback YAML
            fallback_config_path="config/fiscal/naics_bea_mappings.yaml",
        )
    except Exception as e:
        _debug(f"NAICSToBEAMapper init error: {e}")
        return {}

    results: dict[str, str] = {}
    failed_codes: list[str] = []
    for code in naics_codes:
        try:
            mappings = mapper.map_naics_to_bea(code)
            if mappings:
                # Take the highest-weight mapping
                best = max(mappings, key=lambda m: m.allocation_weight)
                results[code] = best.bea_sector_name
        except Exception as e:
            failed_codes.append(code)
            _debug(f"NAICS→BEA mapping failed for {code}: {e}")
            continue

    _debug(f"NAICS→BEA mapped: {len(results)}/{len(naics_codes)}")
    if failed_codes:
        print(
            f"Warning: NAICS→BEA mapping failed for {len(failed_codes)} codes: "
            f"{failed_codes[:10]}{'...' if len(failed_codes) > 10 else ''}",
            file=sys.stderr,
        )
    return results
