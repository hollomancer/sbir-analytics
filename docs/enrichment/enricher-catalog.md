# Enricher Catalog

Every enricher in `sbir_etl/enrichers/`, the external source it hits, and the
credential (if any) it needs. Most credentialed enrichers **degrade gracefully**
when their key is unset (they skip and log a warning) — the two exceptions that
raise are noted.

## Credentialed enrichers

| Enricher | Source | Env var | Behavior if unset |
|----------|--------|---------|-------------------|
| `sam_gov/` | SAM.gov Entity API v3 | `SAM_GOV_API_KEY` | Warns and skips |
| `patentsview.py` | USPTO ODP API | `USPTO_ODP_API_KEY` | **Raises `ConfigurationError`** |
| `openai_client.py` | OpenAI chat/responses API | `OPENAI_API_KEY` | Caller passes the key in (e.g. the weekly report); AI stages skip if absent |
| `lens_patents.py` | Lens.org patent API | `LENS_API_TOKEN` | Short-circuits (no enrichment) |
| `semantic_scholar.py` | Semantic Scholar Graph API | `SEMANTIC_SCHOLAR_API_KEY` | Works without it (lower rate limit) |
| `opencorporates.py` | OpenCorporates API | `OPENCORPORATES_API_TOKEN` | Works on the free tier |
| `orcid_client.py` | ORCID public API | `ORCID_ACCESS_TOKEN` | Works without it |
| `sec_edgar/` | SEC EDGAR (data.sec.gov) | `SEC_EDGAR_CONTACT_EMAIL` | Contact email for the User-Agent (SEC fair-access policy), not a secret |

SAM.gov and SEC EDGAR also read config under `enrichment.sam_gov` / `enrichment.sec_edgar`
in `config/base.yaml` (base URL, `api_key_env_var`, caching). The SEC EDGAR refresh is
opt-in: `SBIR_ETL__ENRICHMENT_REFRESH__SEC_EDGAR__ENABLED=true`.

## Keyless enrichers (no credentials)

| Enricher | Source |
|----------|--------|
| `usaspending/` | USASpending.gov API v2 |
| `press_wire.py` | PRNewswire / BusinessWire / GlobeNewsWire RSS feeds |
| `fpds_atom.py` | FPDS Atom feed (fpds.gov) |
| `congressional_district_resolver.py` | US Census Geocoder API (optional HUD crosswalk file) |
| `geographic_resolver.py` | Local state standardization (uses `FiscalAnalysisConfig`) |
| `inflation_adjuster.py` | Local BEA GDP-deflator data |
| `award_history.py` | Local SBIR CSV/DataFrame aggregation |
| `fiscal_bea_mapper.py`, `company_categorization.py`, `company_fuzzy_matcher.py`, `matching.py`, `pi_enrichment.py`, `naics/` | Local computation / lookups |

Per-source response caching is toggled with `enrichment.<source>.cache.enabled` in
`config/base.yaml`.

## Related

- [SAM.gov integration](sam-gov-integration.md)
- [USASpending iterative refresh](usaspending-iterative-refresh.md)
- [Enhanced matching](enhanced-matching.md)
