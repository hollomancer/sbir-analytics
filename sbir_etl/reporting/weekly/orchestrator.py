"""Pipeline orchestration for the weekly SBIR awards report.

Composes the fetching, enrichment, LLM, and rendering stages. The CLI script
(scripts/data/weekly_awards_report.py) parses arguments and delegates here.

Stage functions are called through their modules (``fetching.fetch_weekly_awards``
etc.) so tests can stub any stage by patching the module attribute.
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from sbir_etl.enrichers.company_enrichment import (
    FederalAwardSummary as PIFederalAwardRecord,
    SAMEntityRecord,
    USARecipientProfile,
    lookup_company_federal_awards as _lib_lookup_company_federal_awards,
)
from sbir_etl.enrichers.opencorporates import CorporateRecord
from sbir_etl.enrichers.press_wire import PressRelease

from sbir_etl.reporting.weekly import enrichment, fetching, link_verification, llm, rendering
from sbir_etl.reporting.weekly.debug import _debug, debug_enabled
from sbir_etl.reporting.weekly.enrichment import (
    STAGE_TIMEOUT,
    _past_deadline,
    _stage_deadline,
    _usaspending_limiter,
)
from sbir_etl.reporting.weekly.models import CompanyResearch


@dataclass
class WeeklyAwardsReportBuilder:
    """Build the weekly awards markdown report.

    Flag semantics match the CLI: see scripts/data/weekly_awards_report.py.
    """

    days: int = 7
    no_ai: bool = False
    no_company_research: bool = False
    no_diligence: bool = False
    skip_sbir_api: bool = False
    timeout: int = 720
    api_key: str = ""

    def run(self) -> str:
        pipeline_start = time.monotonic()
        pipeline_deadline = pipeline_start + self.timeout

        def _pipeline_expired() -> bool:
            return time.monotonic() > pipeline_deadline

        awards, freshness_warnings, shared_source, shared_ext, shared_table = (
            fetching.fetch_weekly_awards(days=self.days)
        )
        _debug(f"Fetched {len(awards)} raw awards (freshness_warnings={freshness_warnings})")

        # Clean, validate, and deduplicate
        awards, cleaning_stats = fetching.clean_and_dedup_awards(awards)
        _debug(f"After cleaning: {len(awards)} awards | stats={cleaning_stats}")
        if debug_enabled() and awards:
            sample = awards[0]
            _debug(f"Sample award keys: {list(sample.keys())}")
            _debug(
                f"Sample award: Company='{sample.get('Company')}' "
                f"Contract='{sample.get('Contract')}' "
                f"Solicitation='{sample.get('Solicitation Number')}' "
                f"Topic='{sample.get('Topic Code')}'"
            )

        # Generate AI content if API key is available
        synopsis = None
        descriptions = None
        company_info: dict[str, CompanyResearch] | None = None
        co_diligence: dict[str, str] | None = None
        pi_dilig: dict[str, str] | None = None
        api_key = self.api_key

        # --- Stage 1: Parallel API fetches (solicitation topics + USAspending +
        # SAM + OpenCorporates + press wire) ---
        sol_topics = None
        usa_descs: dict[str, str] | None = None
        usa_recipients: dict[str, USARecipientProfile] | None = None
        sam_data: dict[str, SAMEntityRecord] | None = None
        oc_data: dict[str, CorporateRecord] | None = None
        press_hits: dict[str, list[PressRelease]] | None = None
        if awards:
            fetch_futures: dict = {}
            with ThreadPoolExecutor(max_workers=6) as fetch_pool:
                if not self.skip_sbir_api:
                    fetch_futures["sol_topics"] = fetch_pool.submit(
                        enrichment.fetch_solicitation_topics, awards
                    )
                else:
                    print("Skipping SBIR.gov API calls (--skip-sbir-api)", file=sys.stderr)

                # Government data APIs (USAspending, SAM.gov) are independent of AI —
                # always fetch when awards exist so enrichment data (BEA sectors,
                # congressional districts, recipient profiles) is available regardless
                # of whether AI descriptions are generated.
                fetch_futures["usa_descs"] = fetch_pool.submit(
                    enrichment.fetch_usaspending_contract_descriptions, awards
                )
                fetch_futures["usa_recipients"] = fetch_pool.submit(
                    enrichment.lookup_usaspending_recipients, awards
                )
                fetch_futures["sam_data"] = fetch_pool.submit(
                    enrichment.lookup_sam_entities, awards
                )
                # OpenCorporates — state corporation filings (free tier, no key required)
                fetch_futures["oc_data"] = fetch_pool.submit(
                    enrichment.lookup_opencorporates, awards
                )
                # Press wire feeds — RSS polling (free, no key required)
                fetch_futures["press_hits"] = fetch_pool.submit(enrichment.poll_press_wire, awards)

                # Collect results
                for name, future in fetch_futures.items():
                    try:
                        result = future.result()
                        if name == "sol_topics":
                            sol_topics = result
                        elif name == "usa_descs":
                            usa_descs = result
                        elif name == "usa_recipients":
                            usa_recipients = result
                        elif name == "sam_data":
                            sam_data = result
                        elif name == "oc_data":
                            oc_data = result
                        elif name == "press_hits":
                            press_hits = result
                    except Exception as e:
                        print(f"Warning: {name} fetch failed: {e}", file=sys.stderr)

        # Local enrichments (no network I/O except congressional district Census fallback)
        inflation_data: dict[str, float] = {}
        congressional: dict[str, str] = {}
        bea_sectors: dict[str, str] = {}
        if awards:
            inflation_data = enrichment.enrich_with_inflation(awards)
            # BEA sector mapping from SAM.gov NAICS codes (local YAML lookup)
            if sam_data:
                all_naics: list[str] = []
                for sam_rec in sam_data.values():
                    for code in sam_rec.naics_codes or []:
                        if code and code not in all_naics:
                            all_naics.append(code)
                bea_sectors = enrichment.map_naics_to_bea_sectors(all_naics)
        # Congressional district resolution may call Census API — only when AI is enabled
        if awards and api_key and not self.no_ai:
            congressional = enrichment.resolve_congressional_districts(awards)

        if api_key and not self.no_ai:
            # --- Stage 2: Company research (parallelized within) ---
            if not self.no_company_research and not _pipeline_expired():
                company_info = llm.research_companies(api_key, awards)
            if _pipeline_expired():
                print(
                    f"Pipeline timeout ({self.timeout}s) — skipping remaining AI enrichment",
                    file=sys.stderr,
                )
            else:
                # --- Stage 3: Synopsis + descriptions in parallel ---
                with ThreadPoolExecutor(max_workers=2) as ai_pool:
                    synopsis_future = ai_pool.submit(
                        llm.generate_weekly_synopsis,
                        api_key,
                        awards,
                        self.days,
                        company_info,
                        sol_topics,
                        usa_descs,
                        sam_data,
                        oc_data,
                        press_hits,
                    )
                    desc_future = ai_pool.submit(
                        llm.generate_award_descriptions,
                        api_key,
                        awards,
                        company_info,
                        sol_topics,
                        usa_descs,
                        sam_data,
                        oc_data,
                        press_hits,
                    )
                    try:
                        synopsis = synopsis_future.result()
                    except Exception as e:
                        print(f"Warning: synopsis generation failed: {e}", file=sys.stderr)
                    try:
                        descriptions = desc_future.result()
                    except Exception as e:
                        print(f"Warning: description generation failed: {e}", file=sys.stderr)

            if not self.no_diligence and not _pipeline_expired():
                # Reuse the source/extractor/table from fetch_weekly_awards() to
                # avoid re-downloading and re-importing the ~376 MB CSV.
                # Build history sequentially — both use the same DuckDB connection
                # which is not thread-safe for concurrent queries.
                print("Building historical context...", file=sys.stderr)
                co_history = fetching.get_company_history(
                    awards, shared_source, shared_ext, shared_table
                )
                pi_history = fetching.get_pi_history(
                    awards, shared_source, shared_ext, shared_table
                )

                # SAM.gov entity data was already fetched above for LLM context;
                # reuse sam_data for diligence.

                # --- Stage 5: Company federal awards (already parallelized) ---
                print("Looking up company federal awards on USAspending...", file=sys.stderr)
                co_fed: dict[str, PIFederalAwardRecord] = {}
                co_names: dict[str, dict] = {}
                for a in awards:
                    name = str(a.get("Company", "")).strip()
                    if not name:
                        continue
                    key = fetching._company_key(a)
                    if key not in co_names:
                        co_names[key] = {
                            "name": name,
                            "uei": str(a.get("Company UEI", a.get("UEI", ""))).strip() or None,
                        }

                def _lookup_co_fed(
                    item: tuple[str, dict],
                ) -> tuple[str, PIFederalAwardRecord | None]:
                    k, info = item
                    return k, _lib_lookup_company_federal_awards(
                        info["name"], info["uei"], rate_limiter=_usaspending_limiter
                    )

                co_fed_deadline = _stage_deadline()
                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures = {
                        executor.submit(_lookup_co_fed, item): item for item in co_names.items()
                    }
                    for future in as_completed(futures):
                        if _past_deadline(co_fed_deadline):
                            print(
                                f"USAspending stage timeout ({STAGE_TIMEOUT}s) — "
                                f"completed {len(co_fed)}/{len(co_names)}, skipping remainder",
                                file=sys.stderr,
                            )
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        try:
                            key, result = future.result(timeout=10)
                            if result:
                                co_fed[key] = result
                        except Exception:
                            pass
                print(
                    f"Found federal awards for {len(co_fed)}/{len(co_names)} companies",
                    file=sys.stderr,
                )

                # Supplement BEA mapping with NAICS codes from USAspending awards
                if co_fed:
                    usa_naics: list[str] = []
                    for fed_rec in co_fed.values():
                        for code in fed_rec.naics_codes or []:
                            if code and code not in usa_naics:
                                usa_naics.append(code)
                    if usa_naics:
                        extra_bea = enrichment.map_naics_to_bea_sectors(usa_naics)
                        for code, sector in extra_bea.items():
                            if code not in bea_sectors:
                                bea_sectors[code] = sector
                        _debug(f"USAspending NAICS→BEA supplement: {len(extra_bea)} codes")

                # Fetch external PI data (patents, publications, ORCID).
                # Reuse co_fed to avoid duplicate USAspending calls per company.
                pi_ext: dict[str, dict] = {}
                if not _pipeline_expired():
                    print("Looking up PI patents, publications, and ORCID...", file=sys.stderr)
                    pi_ext = enrichment.lookup_pi_external_data(awards, co_fed)

                # --- Stage 6: Company + PI diligence in parallel ---
                if not _pipeline_expired():
                    with ThreadPoolExecutor(max_workers=2) as dilig_pool:
                        co_dilig_future = dilig_pool.submit(
                            llm.generate_company_diligence,
                            api_key,
                            awards,
                            company_info,
                            co_history,
                            sam_data,
                            co_fed,
                            usa_recipients,
                            congressional,
                            bea_sectors,
                            oc_data,
                            press_hits,
                        )
                        pi_dilig_future = dilig_pool.submit(
                            llm.generate_pi_diligence,
                            api_key,
                            awards,
                            pi_history,
                            company_info,
                            pi_ext,
                        )
                        try:
                            co_diligence = co_dilig_future.result()
                        except Exception as e:
                            print(f"Warning: company diligence failed: {e}", file=sys.stderr)
                        try:
                            pi_dilig = pi_dilig_future.result()
                        except Exception as e:
                            print(f"Warning: PI diligence failed: {e}", file=sys.stderr)

                if _pipeline_expired():
                    elapsed = int(time.monotonic() - pipeline_start)
                    print(
                        f"Pipeline timeout ({self.timeout}s) at {elapsed}s — "
                        f"generating report with partial enrichment",
                        file=sys.stderr,
                    )
        elif not api_key and not self.no_ai:
            print(
                "OPENAI_API_KEY not set - skipping AI summaries. "
                "Set the env var or use --no-ai to silence this message.",
                file=sys.stderr,
            )

        # Print debug summary of all data collection results before report generation
        if debug_enabled():
            self._print_debug_summary(
                awards,
                freshness_warnings,
                sol_topics,
                company_info,
                usa_descs,
                sam_data,
                usa_recipients,
                oc_data,
                press_hits,
                synopsis,
                descriptions,
                co_diligence,
                pi_dilig,
            )

        return rendering.generate_markdown(
            awards,
            days=self.days,
            synopsis=synopsis,
            descriptions=descriptions,
            company_research=company_info,
            freshness_warnings=freshness_warnings,
            company_diligence=co_diligence,
            pi_diligence=pi_dilig,
            inflation_data=inflation_data,
        )

    @staticmethod
    def _print_debug_summary(
        awards,
        freshness_warnings,
        sol_topics,
        company_info,
        usa_descs,
        sam_data,
        usa_recipients,
        oc_data,
        press_hits,
        synopsis,
        descriptions,
        co_diligence,
        pi_dilig,
    ) -> None:
        print("\n" + "=" * 72, file=sys.stderr)
        print("[DEBUG] === API Data Collection Summary ===", file=sys.stderr)
        print(f"[DEBUG] Awards loaded: {len(awards)}", file=sys.stderr)
        print(
            f"[DEBUG] Freshness warnings: {len(freshness_warnings) if freshness_warnings else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] Solicitation topics fetched: {len(sol_topics) if sol_topics else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] Company research results: {len(company_info) if company_info else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] USAspending contract descriptions: {len(usa_descs) if usa_descs else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] SAM.gov entity records: {len(sam_data) if sam_data else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] USAspending recipient profiles: "
            f"{len(usa_recipients) if usa_recipients else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] OpenCorporates records: {len(oc_data) if oc_data else 0}",
            file=sys.stderr,
        )
        oc_parents = sum(1 for r in (oc_data or {}).values() if r.parent_company)
        if oc_parents:
            print(
                f"[DEBUG]   Companies with parent (subsidiary): {oc_parents}",
                file=sys.stderr,
            )
        press_total = sum(len(v) for v in (press_hits or {}).values())
        print(
            f"[DEBUG] Press wire hits: {press_total} releases for "
            f"{len(press_hits) if press_hits else 0} companies",
            file=sys.stderr,
        )
        print(f"[DEBUG] Synopsis generated: {'yes' if synopsis else 'no'}", file=sys.stderr)
        print(
            f"[DEBUG] Award descriptions generated: {len(descriptions) if descriptions else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] Company diligence paragraphs: {len(co_diligence) if co_diligence else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] PI diligence paragraphs: {len(pi_dilig) if pi_dilig else 0}",
            file=sys.stderr,
        )
        # Show which awards have all reference link components
        missing_contracts = sum(1 for a in awards if not str(a.get("Contract", "")).strip())
        missing_sol = sum(
            1
            for a in awards
            if not str(a.get("Solicitation Number", "")).strip()
            and not str(a.get("Topic Code", "")).strip()
        )
        print(
            f"[DEBUG] Awards missing Contract (no USAspending link): "
            f"{missing_contracts}/{len(awards)}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] Awards missing Solicitation+Topic (no solicitation link): "
            f"{missing_sol}/{len(awards)}",
            file=sys.stderr,
        )
        # Verify reference links with HTTP HEAD requests
        if awards:
            link_checks = link_verification.verify_reference_links(awards, company_info)
            link_verification._print_link_verification_report(link_checks)
        print("=" * 72 + "\n", file=sys.stderr)


def build_report(
    *,
    days: int = 7,
    no_ai: bool = False,
    no_company_research: bool = False,
    no_diligence: bool = False,
    skip_sbir_api: bool = False,
    timeout: int = 720,
    api_key: str | None = None,
) -> str:
    """Convenience wrapper: build the weekly report with CLI-equivalent options."""
    return WeeklyAwardsReportBuilder(
        days=days,
        no_ai=no_ai,
        no_company_research=no_company_research,
        no_diligence=no_diligence,
        skip_sbir_api=skip_sbir_api,
        timeout=timeout,
        api_key=api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", ""),
    ).run()
