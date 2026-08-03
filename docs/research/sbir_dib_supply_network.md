# SBIR awardees in the observed defense supply network

## Purpose

Identify where companies with SBIR/STTR award histories appear in reported DoD
subcontract activity, which prime contractors integrate them, and which
relationships are persistent or concentrated.

For NSF specifically, identify awardees with verified observed DoD supplier
relationships and use award-level CET evidence to prioritize records that may
intersect defense-critical supply-chain categories.

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
amount, and recipient, while retaining the latest report ID and the number of
source versions observed.

The NSF screen adds two distinct evidence layers:

1. Specific NSF SBIR records are associated with an observed supplier by UEI,
   then DUNS, with unique normalized name retained as an explicitly weaker
   fallback.
2. Award title, topic code, and abstract are screened by
   `CET-RULES-2026Q3`; the primary CET is mapped through
   `DOD-CROSSWALK-2026Q3` to the repository's `DOD-SC-8-2022` framework.

`DOD-SC-8-2022` is a repository label for the four focus areas and four
strategic enablers in DoD's 2022 supply-chain report, not an official
“NDIS-8” taxonomy. A positive text screen is a review candidate. It does not
establish that the NSF-funded work was used on the observed subcontract,
physical-input dependence, supplier substitutability, or criticality.

## Initial local slice

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

## Initial NSF SBIR screen

The all-agency registry contains 3,723 NSF SBIR awardees. Exact UEI/DUNS
matching finds 301 of them in reported DoD subcontract activity: 907
supplier-to-prime legal-entity edges across 277 prime families. Sixty-eight
NSF awardees have at least one relationship observed in three or more fiscal
years; 131 NSF supplier-to-prime edges meet that persistence threshold.

Those 301 organizations resolve to 1,246 de-duplicated specific NSF SBIR
records. The award-to-firm association is identifier-based for 1,240 records;
six use a unique normalized name and require additional review. The local CET
screen classifies 439 awards across 174 observed suppliers, all of which map to
at least one defense-supply-chain category through the current crosswalk.

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

Build a network from one or more official USAspending CSV/ZIP downloads:

```bash
uv run python scripts/data/build_sbir_dib_subaward_network.py \
  --subawards \
    data/raw/usaspending/dod_contract_subawards_fy2021.zip \
    data/raw/usaspending/dod_contract_subawards_fy2022.zip \
    data/raw/usaspending/dod_contract_subawards_fy2023.zip \
    data/raw/usaspending/dod_contract_subawards_fy2024.zip \
    data/raw/usaspending/dod_contract_subawards_fy2025.zip
```

Generated registry, fact, edge, customer-exposure, and metadata artifacts are
written to `data/processed/sbir_dib_subaward_network/`. NSF-specific outputs
are:

- `nsf_sbir_supplier_prime_edges.parquet` — verified organization-to-prime edges;
- `nsf_sbir_supply_chain_candidates.parquet` — one supplier-level screen row;
- `nsf_sbir_award_candidates.parquet` — specific NSF award text, CET evidence,
  crosswalk mappings, and explicit non-determination fields.

## Graph explorer

Export the verified network into the static browser data contract:

```bash
uv run python scripts/data/export_sbir_dib_network_web.py
```

Then serve `tools/sbir-dib-network-explorer/` locally:

```bash
uv run python -m http.server 8080 --directory tools/sbir-dib-network-explorer
```

The explorer defaults to persistent, high-ranked relationships rather than
rendering the full network as a hairball. Search can focus any supplier or prime
family in the complete payload. Node details retain the evidence grade,
persistence, observed amounts, exposure screen, NSF award history, and the
explicit `dependency_status=not_established` guardrail. NSF-only and CET
supply-chain-screen filters expose the candidate cohort without turning the
screen into a criticality claim.

## Sources

- [USAspending custom award data](https://www.usaspending.gov/download_center/custom_award_data)
- [USAspending search-download API contract](https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/download/search.md)
- [USAspending subaward API contract](https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/subawards.md)
- [SBIR.gov data resources](https://www.sbir.gov/data-resources)
- [NSF Award Search](https://www.nsf.gov/funding/award-search)
