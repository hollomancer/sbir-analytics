# SBIR awardees in the observed defense supply network

## Purpose

Identify where companies with SBIR/STTR award histories appear in reported DoD
subcontract activity, which prime contractors integrate them, and which
relationships are persistent or concentrated.

For NSF specifically, identify current and former direct NSF SBIR/STTR
awardees with observed signed DoD prime or reported-subaward funding, then use
award-level CET evidence to prioritize records for critical-supply-chain
review.

This is a contractual-network view. It does not identify physical inputs,
bills of material, production capacity, country of origin, or suppliers below
the first reported subcontract tier.

## Tier convention

“First tier” is overloaded in the source data. USAspending describes a
subcontract directly reported under a prime award as a *first-tier subaward*.
For this research product, the DIB-oriented convention is:

| DIB tier | Observable role |
| --- | --- |
| Tier 1 | Organization holding the direct DoD prime award |
| Tier 2 | SBIR awardee reported as the Tier 1 prime's subcontractor |
| Tier 3+ | Not visible in USAspending first-tier subaward data |

The stored fields retain both conventions:
`federal_reporting_level=first_tier_subaward`,
`dib_customer_tier=tier_1_prime`, and `dib_supplier_tier=tier_2`.

## Evidence model

| Grade | Match | Permitted interpretation |
| --- | --- | --- |
| `verified_identifier` | Exact subawardee UEI, then exact DUNS, to the SBIR registry | Observed reported subcontract edge |
| `candidate_name` | Unique exact normalized organization name | Review candidate only |
| No match | No unambiguous identifier or name match | No conclusion |

Absence is never negative evidence. Subawards below reporting thresholds,
unreported relationships, OT consortium distributions, and data-quality gaps
remain invisible.

The supplier-to-prime edge records the parent prime award, PIID, prime and
parent identifiers, subaward number, reported amount, action date, description,
NAICS, source URL, and source last-modified timestamp. Repeated facts aggregate
to a legal-entity prime edge while retaining a parent-family rollup.
SAM report IDs can represent repeated versions of the same economic record.
Facts are therefore de-versioned on parent award, subaward number, action date,
and resolved recipient. Reported amount is versioned content: the row with the
latest source last-modified timestamp is retained, with stable report-ID and row
hash tie-breakers, while preserving the selected report ID and number of source
versions observed. Distinct action dates remain distinct economic facts.

The expanded NSF screen adds three distinct evidence layers:

1. Direct NSF records validate award identifiers, text, amounts, organizations,
   and authoritative performance dates against the SBIR.gov baseline.
2. USAspending prime and reported-subaward records resolve to the same legal
   entity by UEI, then legacy DUNS; unique normalized-name matches remain
   candidates outside verified totals.
3. Direct award title, program elements, and abstract are screened by the
   versioned local CET classifier. A positive initial review screen requires
   both CET text evidence and verified observed DoD funding to the legal entity.

DoD-14 and NDIS-8 policy mappings remain explicitly deferred because no
authoritative mapping is materialized in the repository. A positive CET screen
is a review candidate. It does not establish that the NSF-funded work was used
on a DoD award, physical-input dependence, supplier substitutability, or
criticality. FOCI is outside this analysis.

## Expanded NSF funding-lineage release

The current release path uses source-native records for four separate facts:

| Fact | Source and grain | Boundary |
| --- | --- | --- |
| NSF SBIR/STTR award | Direct NSF Award Search API or annual award JSON, one NSF award | NSF dates determine current/former status; award year is never substituted |
| DoD prime procurement/assistance | USAspending Advanced Search plus `/transactions/`, one signed FPDS/FABS transaction | Exact recipient UEI only; coverage starts 2007-10-01 |
| DoD prime other transaction | Recipient-filtered USAspending Contracts Full archive, one FPDS transaction | O/R instrument codes remain separate from procurement |
| Reported DoD subaward | USAspending/SAM.gov/FSRS file, one de-versioned reported subaward fact | First reported tier only; absence is not negative evidence |

Every flow preserves negative, zero, and positive obligations. Summaries are at
`legal entity × fiscal year × funding mode × instrument` grain. Prime
procurement, assistance, other transactions, contract subawards, and assistance
subawards never collapse into one measure. Each aggregate contains its source
transaction IDs; the release manifest pins input and product checksums.
Award-level search results are expanded through `/transactions/`, then clipped
again by transaction action date so older modifications on a matched award do
not leak outside the requested analysis window.

The product `nsf_award_defense_evidence.parquet` crosses an NSF award only with
DoD awards observed for the same resolved entity. It records whether periods
occur before, during, or after one another, but always sets
`specific_award_usage_status=not_established` and
`temporal_association_is_causal_evidence=false` unless direct capability-level
evidence is supplied later.

Current/former describes NSF award performance, not whether the company is
operating:

- `current`: at least one direct NSF SBIR/STTR performance period is active on
  the recorded analysis date;
- `former`: historical direct NSF awards and no active performance period;
- `upcoming_only` or `indeterminate`: authoritative dates do not support either
  of the first two labels.

## Legacy subaward-only local slice

The initial materialization uses the official USAspending DoD contract-subaward
downloads for FY2021–FY2025 and the local public SBIR.gov awardee registry:

- 873,320 source subaward rows before report-version de-duplication.
- 17,160 distinct SBIR awardee identities in the retained all-agency registry.
- 47,387 exact-identifier subaward facts after de-versioning.
- 8,428 verified SBIR-supplier-to-prime legal-entity edges.
- 2,387 matched SBIR awardees (13.9% of the registry).
- 975 matched prime legal entities.
- $52.79 billion in net reported subaward amounts.
- 3,187 name-only candidate facts across 512 candidate edges, held outside
  the verified network.
- 1,739 verified edges observed in at least three fiscal years; 364 observed
  in all five years.

These are pre-fix diagnostic figures from the initial materialization, whose
de-version key included reported amount. They are not parity targets for the
current amount-independent correction semantics and must be regenerated before
being cited as current results.

These amounts describe reported subawards involving firms that have an SBIR
history. They do not prove that the subcontract uses the firm's SBIR-funded
technology.

### Largest observed prime-family integration hubs

| Prime family | Matched SBIR suppliers | Persistent edges (3+ FYs) |
| --- | ---: | ---: |
| Lockheed Martin | 332 | 241 |
| Atlantic Diving Supply | 257 | 103 |
| Northrop Grumman Systems | 238 | 53 |
| Raytheon | 223 | 78 |
| Leidos | 221 | 32 |
| Booz Allen Hamilton | 197 | 38 |
| Boeing | 176 | 94 |
| Science Applications International Corporation | 164 | 21 |
| HII Mission Technologies | 163 | 33 |
| CACI | 160 | 9 |

These counts are integration hubs within the identifier-matched SBIR-awardee
network. They are not the prime families' total supplier counts and do not
establish dependence on any listed supplier.

### Relationship persistence

| Fiscal years observed | Supplier–prime legal-entity edges |
| ---: | ---: |
| 1 | 4,998 |
| 2 | 1,691 |
| 3 | 849 |
| 4 | 526 |
| 5 | 364 |

## Legacy NSF SBIR screen

The all-agency registry contains 3,723 NSF SBIR awardees. Exact UEI/DUNS
matching finds 301 of them in reported DoD subcontract activity: 907
supplier-to-prime legal-entity edges across 277 prime families. Sixty-eight
NSF awardees have at least one relationship observed in three or more fiscal
years; 131 NSF supplier-to-prime edges meet that persistence threshold.

Those 301 organizations resolve to 1,246 de-duplicated specific NSF SBIR
records. The award-to-firm association is identifier-based for 1,240 records;
six use a unique normalized name and require additional review. The local CET
screen classifies 439 awards across 174 observed suppliers. The category counts
below came from the legacy repository crosswalk and are retained only to
reproduce that initial slice; the expanded lineage release does not treat them
as authoritative DoD-14 or NDIS-8 mappings.

The mapped categories are non-exclusive:

| Defense-supply-chain category | Screened NSF awards |
| --- | ---: |
| Manufacturing | 303 |
| Castings and forgings | 148 |
| Microelectronics | 107 |
| Kinetic capabilities | 84 |
| Cyber posture | 66 |
| Energy storage and batteries | 39 |

Illustrative high-persistence records in the review queue include:

| NSF SBIR awardee and award | Primary CET → supply-chain screen | Observed supplier footprint |
| --- | --- | --- |
| Areté Associates — *Affordable Optically Pumped Semiconductor Lasers for Polychromatic Guide Star Systems* | Semiconductors and microelectronics → microelectronics, manufacturing | 5 FY; 13 prime families |
| Sioux Manufacturing — *Protective Metal Foam Hybrid Composites* | Advanced engineering materials → castings and forgings, manufacturing | 5 FY; 3 prime families |
| Novatio Engineering — *Robust Ceramic Turbine Blades for Gas Turbines* | Advanced gas-turbine engines → kinetic capabilities, manufacturing | 5 FY; 2 prime families |
| Advanced Cooling Technologies — *Microscale Thermal Management in Pulsed Semiconductor Devices* | Semiconductors and microelectronics → microelectronics, manufacturing | 4 FY; 17 prime families |
| UES — *Novel Wafer Fabrication Technology for Semiconductor Sensors* | Semiconductors and microelectronics → microelectronics, manufacturing | 4 FY; 7 prime families |
| Max Power — *Improving Electrolyte Stability in Li-Air Batteries Using Superoxide Dismutase* | Renewable-energy generation and storage → energy storage and batteries | 4 FY; 5 prime families |

These examples identify where to inspect award and subcontract descriptions;
they do not assert a link between the named NSF project and any specific DoD
subcontract. The classifier has not been validated as a critical-supplier
model, and `enabling` crosswalks can be broad. Decision use requires manual
review, capability-to-contract alignment, evidence of alternatives, and
production/capacity data.

## Dependency screens

The first derived screen measures the SBIR supplier's observed customer
concentration:

- number of observed prime families;
- reported subaward amount and count;
- top observed prime-family share; and
- HHI across observed prime-family amounts.

Net reported totals retain negative corrections. Customer shares and HHI use
positive net supplier-to-prime edge amounts; nonpositive edges are counted and
excluded from the concentration denominator.

Across the five-year slice, 1,052 SBIR awardees have only one observed prime
family, 505 have multiple families but at least 75% of positive net reported
amounts associated with one family, and 821 have a more distributed observed
customer set. Nine suppliers have no positive net edge amount after
corrections. These are review strata, not dependency labels.

This is not yet a dependency determination. An incomplete federal subaward
slice cannot establish total-revenue dependence, supplier
substitutability, technical criticality, or a prime's dependence on the
supplier. Multi-year persistence is required before even labeling a
relationship a dependency candidate.

The next decision-grade screen should require all of:

1. exact identifier evidence;
2. recurrence across multiple fiscal years or prime awards;
3. a high customer-share or repeated-integration signal;
4. CET/capability alignment between the SBIR work and subcontract description;
5. evidence about alternatives or substitutability; and
6. manual review of the parent awards and descriptions.

## Path to deeper tiers

Public federal subaward data stops at the prime's reported subcontractor. Tier
3+ work therefore needs additional evidence:

- supplier and teaming disclosures from primes and awardees;
- program, contract, or platform supplier lists;
- SEC filings and acquisition disclosures;
- patent assignment/citation edges, explicitly labeled as knowledge rather than
  physical-supply relationships;
- structured surveys or direct data-sharing with primes and program offices; or
- licensed bill-of-material and supplier-risk data.

Those sources must retain their own provenance and confidence. Semantic
similarity, shared programs, NAICS, PSC, or CET alignment may prioritize review
but must not create a supplier edge by themselves.

## Reproduction

First materialize direct NSF awards for a fixed analysis date. With no
`--direct-source`, the command creates immutable per-award API snapshots; a
saved API snapshot or annual NSF JSON directory can be supplied for an offline
rebuild:

```bash
uv run python scripts/data/build_nsf_sbir_direct_awards.py \
  --analysis-date 2026-08-03
```

Then build signed DoD funding. The API snapshot path may be created in this run
with `--fetch-prime-api` or supplied with `--prime-snapshot`. Contract archive
input is recipient-filtered through the existing archive extractor; when API
transactions are present it contributes O/R other transactions by default so
procurement is not double counted:

```bash
uv run python scripts/data/build_nsf_defense_funding.py \
  --analysis-date 2026-08-03 \
  --fetch-prime-api \
  --prime-contract-archive data/raw/usaspending/FY2026_DoD_Contracts_Full.zip \
  --subaward data/raw/usaspending/dod_contract_subawards_fy2025.zip \
  --subaward data/raw/usaspending/dod_contract_subawards_fy2026.zip
```

Mixed API-plus-archive runs always restrict archive input to O/R other
transactions. Archive-only runs include complete archive procurement by
default. There is no configuration that overlays complete archive procurement
on API transactions, whose transaction identifiers use a different namespace.

The release in `data/processed/nsf_sbir_defense_lineage/` contains:

- `nsf_sbir_awards_direct.parquet` and award reconciliation/status tables;
- `nsf_awardee_dod_prime_transactions.parquet`;
- `nsf_awardee_dod_subaward_transactions.parquet`;
- `nsf_awardee_defense_funding_summary.parquet`;
- `nsf_award_defense_evidence.parquet`;
- `nsf_sbir_critical_supply_chain_screen.parquet`; and
- checksum-pinned manifest, quality, and fiscal-year/funding-mode partitions.

The opt-in Dagster job `nsf_defense_lineage_refresh_job` runs direct NSF,
funding, validation, and graph assets. Its monthly schedule is stopped by
default. Source lists are path-separated environment variables under
`SBIR_ETL__NSF_DEFENSE_LINEAGE__`, including `DIRECT_NSF_SOURCES`,
`PRIME_API_SNAPSHOTS`, `PRIME_CONTRACT_ARCHIVES`, and `SUBAWARD_SOURCES`.
`FETCH_PRIME_API=true` enables live prime retrieval. Validation fails schema,
checksum, inconsistent-analysis-date, stale-release, and evidence-guardrail
checks closed.

The legacy subaward-only network remains reproducible from official
USAspending CSV/ZIP downloads:

```bash
uv run python scripts/data/build_sbir_dib_subaward_network.py \
  --subawards \
    data/raw/usaspending/dod_contract_subawards_fy2021.zip \
    data/raw/usaspending/dod_contract_subawards_fy2022.zip \
    data/raw/usaspending/dod_contract_subawards_fy2023.zip \
    data/raw/usaspending/dod_contract_subawards_fy2024.zip \
    data/raw/usaspending/dod_contract_subawards_fy2025.zip
```

Legacy registry, fact, edge, customer-exposure, and metadata artifacts are
written to `data/processed/sbir_dib_subaward_network/`. NSF-specific outputs
are:

- `nsf_sbir_supplier_prime_edges.parquet` — verified organization-to-prime edges;
- `nsf_sbir_supply_chain_candidates.parquet` — one supplier-level screen row;
- `nsf_sbir_award_candidates.parquet` — specific NSF award text, CET evidence,
  crosswalk mappings, and explicit non-determination fields.

## Graph explorer

Export the expanded lineage into the static browser data contract and CSV
downloads:

```bash
uv run python scripts/data/export_sbir_dib_network_web.py
```

Then serve `tools/sbir-dib-network-explorer/` locally:

```bash
uv run python -m http.server 8080 --directory tools/sbir-dib-network-explorer
```

The explorer renders agencies, NSF awards, legal entities, DoD awards, and CET
areas as distinct nodes. Controls filter current/former status, fiscal-year
persistence, funding instrument, verified versus candidate edges, and CET
review candidates. Solid funding edges trace to source IDs; dashed name,
classifier, and temporal edges remain candidates. The details pane and CSV
downloads retain match method, confidence, source paths/checksums, signed
amounts, and the explicit non-determination fields.

## Sources

- [USAspending custom award data](https://www.usaspending.gov/download_center/custom_award_data)
- [USAspending search-download API contract](https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/download/search.md)
- [USAspending subaward API contract](https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/subawards.md)
- [SBIR.gov data resources](https://www.sbir.gov/data-resources)
- [NSF Award Search](https://www.nsf.gov/funding/award-search)
