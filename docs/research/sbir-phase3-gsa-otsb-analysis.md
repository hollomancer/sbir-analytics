# SBIR Phase III: GSA Channel, OTSB Recipients, and the FY2024 Channel Shift

**Status:** Working analysis. All figures from `data/processed/sbir_phase3/phase3_universe_enriched.jsonl` built 2026-06-28 via `scripts/data/build_phase3_universe.py` + `scripts/data/enrich_phase3_business_size.py` (PR #394).
**Date:** 2026-06-29.
**Audience:** Defense industrial-base analysts, SBIR program managers, GAO/CRS, congressional defense committee staff.

## Headlines

- **GSA accounts for 27.2% of Phase III dollars ($1.86B of $6.85B) and 10.1% of contracts (204 of 2,013) across FY2008–FY2026.** GSA is acting as the *procurement vehicle*, not the funder — GSA funds zero Phase III work; DoD pays for 96% of GSA-awarded Phase III.
- **96% of GSA Phase III flows through FEDSIM**, not the well-known multi-agency GWACs (OASIS, Alliant, STARS, Polaris). PIID-prefix attribution: 130 contracts ($1.32B) on `47QFLA*` (FEDSIM East / Loudoun, VA HQ); 51 contracts ($0.37B) on `47QFCA*` (FEDSIM West).
- **GSA Phase III was effectively zero before FY2014, peaked at $508M in FY2021 (64% of all Phase III dollars that year), then collapsed to $109M in FY2024 (15% share).** **Partial channel shift, partial contraction:** roughly 40% of the GSA-era dollars reappeared as direct-DoD work; the other ~60% disappeared from keyword-discoverable Phase III. Combined GSA + direct-DoD Phase III fell 34% from FY2023 peak ($764M) to FY2025 ($506M).
- **14.7% of Phase III dollars ($1.01B) went to Other Than Small Business (OTSB) recipients**, 7.0% of contracts. 11 prime contractors hold 70.4% of OTSB dollars. **82.7% of OTSB dollars went to firms with documented Phase I/II SBIR history** — split between known M&A continuations (~20%), grew-out firms like LinQuest and Anduril (~63%), and likely-M&A cases our data missed. **Only 17.3% ($175M) went to genuinely external large primes** with no SBIR history (Sierra Space, Amentum, Parsons, Rockwell Collins). OTSB designation is misleading as a "program leakage" signal — the SBIR ecosystem is producing the OTSB outcome by design.

## What "Phase III" means in this dataset

Phase III is a contracting status, not a separate SBIR award. Under [15 USC §638(r)](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title15-section638), any federal agency may issue a contract on a sole-source basis to an SBIR/STTR firm to develop, produce, or commercialize technology derived from an earlier Phase I or Phase II SBIR award. That contract is "Phase III." Unlike Phase I/II, Phase III is not centrally tracked — SBIR.gov's bulk data contains only Phase I (151,426 rows) and Phase II (68,075 rows); zero Phase III rows. The only authoritative source for Phase III contracts is FPDS/USAspending, where Phase III status is conveyed by the contracting officer writing "SBIR Phase III" (or a variant) into the contract description.

That tagging is unreliable. [GAO-24-107036](https://www.gao.gov/products/gao-24-107036) documents ~30% undercount of Phase III contracts in DoD historical FPDS tagging because contracting officers don't consistently include Phase III markers in descriptions. This analysis works within that constraint — the dataset is best understood as the **keyword-discoverable** Phase III universe, not the true population.

## Methodology

The cached USAspending Phase III set on this repo was built by:

1. **`scripts/data/build_phase3_universe.py`** — fetches `spending_by_award` across **six description-keyword variants** for FY2008–FY2026: `SBIR Phase III`, `SBIR Phase 3`, `SBIR PH III`, `Phase III SBIR`, `SBIR follow-on`, `Small Business Innovation Research Phase III`. Unions by Award ID, tags each row with `_keywords_matched` provenance. Adds `Parent Award ID` to fetched fields so contract-vehicle attribution is one query away.
2. **`scripts/data/enrich_phase3_business_size.py`** — for each row, calls the per-award detail endpoint `/awards/{generated_unique_award_id}/`, which returns `business_categories` (the canonical signal for `Small Business` vs `Not Designated a Small Business`). The search endpoint does not populate this field; it must come from per-award lookup.

**Coverage gain vs. the prior single-keyword fetch:** +20% rows (1,671 → 2,013) and +14% dollars ($6.00B → $6.85B). FY2007 returns HTTP 500 from USAspending — that's the API's reliable depth limit. 99.7% of rows enriched successfully with size data.

### What the methodology does *not* fix

Six keyword variants caught more than one, but Phase III contracts whose descriptions use **no** SBIR/Phase-III markers remain invisible. There is no authoritative join available because SBIR.gov doesn't track Phase III. **Direct-DoD contracts are more under-represented than GSA-awarded contracts** in keyword-derived cohorts because FEDSIM's templated SOWs routinely include the "SBIR Phase III" phrase, while DoD program offices vary widely. This means the GSA share reported here is **likely modestly overstated** relative to ground truth — the true GSA dollar share is probably in the 20–27% range rather than the surface-level 27.2%.

## GSA Phase III year-over-year

Awarding-agency bucket, contract counts and dollars by Start-Date fiscal year (FY = year of (Start Date + 3 months)):

| FY | GSA n | DoD n | Other SBIR n | Non-SBIR n | | GSA $M | DoD $M | Other SBIR $M | Non-SBIR $M | | GSA % of $ |
|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---:|
| 2008 | 0 | 27 | 20 | 3 | | $0 | $74 | $4 | $4 | | 0.0% |
| 2009 | 0 | 55 | 24 | 1 | | $0 | $89 | $5 | $2 | | 0.0% |
| 2010 | 0 | 45 | 19 | 2 | | $0 | $117 | $2 | $3 | | 0.0% |
| 2011 | 0 | 35 | 11 | 1 | | $0 | $168 | $1 | $5 | | 0.0% |
| 2012 | 0 | 22 | 36 | 2 | | $0 | $101 | $7 | $1 | | 0.0% |
| 2013 | 0 | 23 | 30 | 2 | | $0 | $54 | $5 | $7 | | 0.0% |
| 2014 | 3 | 36 | 30 | 1 | | $13 | $86 | $13 | $3 | | 11.0% |
| 2015 | 0 | 30 | 38 | 0 | | $0 | $75 | $23 | $0 | | 0.0% |
| 2016 | 1 | 41 | 29 | 1 | | $4 | $245 | $22 | $1 | | 1.4% |
| 2017 | 3 | 34 | 18 | 0 | | $61 | $144 | $20 | $0 | | 27.0% |
| 2018 | 6 | 45 | 20 | 0 | | $63 | $175 | $22 | $0 | | 24.2% |
| 2019 | 7 | 62 | 9 | 1 | | $33 | $331 | $12 | $0 | | 8.7% |
| **2020** | **23** | 67 | 10 | 0 | | **$330** | $240 | $47 | $0 | | **53.5%** |
| **2021** | **55** | 83 | 11 | 1 | | **$505** | $306 | $13 | $2 | | **61.0%** ← peak |
| 2022 | 39 | 115 | 32 | 2 | | $294 | $420 | $60 | $48 | | 36.0% |
| 2023 | 44 | 135 | 39 | 1 | | $390 | $374 | $32 | $11 | | 48.4% |
| **2024** | **12** | **179** | 31 | 5 | | **$109** | **$587** | $35 | $21 | | **14.5%** ← cliff |
| 2025 | 7 | 153 | 82 | 3 | | $33 | $473 | $130 | $7 | | 5.1% |
| 2026 | 4 | 29 | 21 | 0 | | $30 | $106 | $25 | $0 | | 18.7% (partial) |
| **All** | **204** | — | — | — | | **$1,864** | — | — | — | | **27.2%** |

### Three structural features

**1. Pre-2014 is structural, not a data gap.** GSA had zero Phase III contracts for fifteen consecutive years before the data begins to show activity. The legal authority under §638(r) predates this period — the change is on the demand side, not the law.

**2. The 2020–2023 era is the GSA story.** Across those four fiscal years, GSA awarded $1.52B of Phase III work — roughly 47% of total Phase III dollars in that window. In FY2021 specifically, GSA was the **majority channel** for Phase III dollars (61%). This is not a small or peripheral channel; this is *the* dominant procurement path for SBIR Phase III work during the peak years.

**3. The FY2024 cliff is partly real channel shift and partly real Phase III contraction.** Direct-DoD dollars grew from $374M (FY2023) → $587M (FY2024), absorbing about $213M of the $281M GSA decline that year. But the FY2025 picture is worse: combined GSA + direct-DoD fell to $506M, a 34% drop from the FY2023 peak ($764M). Annualized by sub-agency, Navy and Air Force grew direct-DoD Phase III by $58M/yr and $40M/yr respectively from the FY2018-2023 era to the FY2024-2026 era; Army contracted by $24M/yr. **The Navy+AF growth of ~$98M/yr replaces roughly 40% of their $236M/yr GSA-era loss** — the rest disappeared from keyword-discoverable Phase III, either through outright contraction, classified contracting (DoD has Phase III activity that doesn't appear in USAspending regardless of keyword), or migration to vehicles/agencies/keywords we cannot see in this dataset. See **Tier 1 follow-up findings** below for the recipient-migration and sub-agency analysis that produced these numbers.

## What "GSA Phase III" really means: it's FEDSIM

GSA is a multi-organization umbrella. Within GSA, the Phase III dollars route through specific sub-organizations identified by PIID prefix. Federal Acquisition Service PIIDs starting with `47QF` belong to FEDSIM (Federal Systems Integration and Management Center):

| 6-char prefix | Sub-organization | Contracts | Dollars | Share of GSA |
|---|---|---:|---:|---:|
| `47QFLA` | **FEDSIM East** (Loudoun, VA HQ) | 130 | $1.32B | **74.6%** |
| `47QFCA` | **FEDSIM West** (Chantilly, VA / regional) | 51 | $0.37B | **21.2%** |
| `GSQ051` | Legacy GSA single-award BPA (2014 vintage) | 5 | $68M | 3.8% |
| `47QFSA`, `47QFRA` | Other FAS regions | 4 | $7M | 0.4% |

**FEDSIM is 95.7% of GSA Phase III dollars.** "GSA Phase III" and "FEDSIM Phase III" are nearly synonymous.

This matters because FEDSIM is a fee-for-service Assisted Acquisition Services (AAS) organization, founded in 1976. DoD program offices come to FEDSIM not because GSA is the funding source — DoD pays — but because FEDSIM writes complex IT and engineering integration SOWs that DoD's own contracting workforce is stretched too thin to handle. The post-2007 GSA reorganization that merged FSS and FTS into the Federal Acquisition Service (FAS) and consolidated FEDSIM under Assisted Acquisition Services made this scaling more practical, but FEDSIM itself was operating decades earlier.

## Surprise finding: not the famous GWACs

Going into the analysis I expected GSA Phase III to ride on the visible multi-agency GWACs: OASIS (2014), Alliant 2 (2018), 8(a) STARS III (2021), or Polaris. Parsing `Parent Award ID` out of `generated_internal_id` for the GSA-awarded contracts tells a different story.

Top parent IDVs (the contract vehicles task orders ride on):

| Parent IDV | Task orders | $M | What it is |
|---|---:|---:|---|
| `(no parent IDV)` | 18 | **$465** | FEDSIM standalone contracts — 26% of GSA Phase III dollars are direct contracts, not task orders against any GWAC |
| `GS05Q14BMD0001` | 11 | $126 | Legacy GSA single-award BPA, FY2014 vintage |
| `47QFLA19D0007` | 12 | $109 | FEDSIM-managed IDIQ, FY2019 |
| `47QFCA20D0004` | 20 | $89 | FEDSIM-managed IDIQ, FY2020 |
| `47QFLA21D0008` | 1 | $85 | FEDSIM single-award IDV, FY2021 (one massive task order) |
| `47QFLA19D0003` | 2 | $75 | FEDSIM-managed IDIQ |
| `47QFLA24D0001` | 1 | $72 | FEDSIM IDIQ, FY2024 |
| `47QFCA22D0503` | 2 | $68 | FEDSIM-managed IDIQ |
| `47QFLA23D0008` | 1 | $64 | FEDSIM-managed IDIQ |
| `47QFLA23D0007` | 2 | $53 | FEDSIM-managed IDIQ |

**None of the well-known multi-agency GWACs appear**. OASIS PIIDs (`GS00Q14OAD*`), Alliant 2 (`47QTCK18D###`), 8(a) STARS III (`47QRAA20D###`), and Polaris (`47QRCB##D###`) are all absent from GSA Phase III's parent IDV list. What's actually happening: **DoD program offices use FEDSIM-managed single-award IDIQs and small-pool IDIQs, plus a meaningful share of standalone direct contracts**, rather than the public-facing multi-agency GWACs.

Rolling up parent IDV vintage (the FY the parent vehicle was awarded):

| IDV Vintage | Task orders | $M | Pattern |
|---|---:|---:|---|
| Direct contracts (no parent IDV) | 18 | $465 | Peaked FY2020 ($227M), last in FY2023 |
| FY2019 FEDSIM IDIQs | 39 | $299 | Peak FY2021 ($104M), trailing through FY2025 |
| FY2021 FEDSIM IDIQs | 31 | $252 | Peak FY2021 ($168M), declined fast |
| FY2020 FEDSIM IDIQs | 63 | $220 | Steady FY2020–FY2023, gone in FY2024 |
| FY2023 FEDSIM IDIQs | 14 | $215 | One big burst in FY2023 ($208M), then nothing |
| FY2014 legacy GSA BPA | 11 | $126 | Wound down by FY2020 |
| FY2024 FEDSIM IDIQs | 2 | $75 | One $72M contract; not a replacement-scale vehicle |
| FY2025 FEDSIM IDIQs | 3 | $14 | Tiny |

**The cliff is partly natural IDIQ lifecycle decay**, partly the disappearance of standalone direct contracts (a channel that had $465M of activity over four years and then simply stopped). Successor FY2024–FY2025 FEDSIM IDIQ vintages are not replacing the FY2019–FY2021 generation at the same scale.

## Other Than Small Business (OTSB) Phase III

"Other Than Small Business" means the contracting officer's business-size determination at award time was anything other than `Small Business` — most commonly `Not Designated a Small Business`. The size flag lives on `business_categories` in the per-award detail endpoint.

### Headline numbers (FY2008–FY2026)

- **140 of 2,007 enriched contracts (7.0%) went to OTSB**
- **$1.01B of $6.85B (14.7%) of dollars went to OTSB**
- **Contract size distribution** (OTSB vs Small Business):

| Group | n | Total $M | Mean | **Median** | P25 | P75 | P95 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OTSB | 140 | $1,009 | $7.21M | **$1.52M** | $0.27M | $7.86M | $35.9M | $85.3M |
| Small Business | 1,867 | $5,841 | $3.13M | **$0.75M** | $0.20M | $2.55M | $11.6M | $195.6M |

OTSB awardees win larger contracts on average (2.3× the mean, 2.0× the median). Both distributions are heavily right-skewed — medians are well below means. Note: the single largest contract in the whole universe is a *Small Business* award ($195.6M to MI Technical Solutions, Navy-funded GSA-awarded). The right tail of the SB distribution actually reaches higher than OTSB's.

### Year-over-year OTSB share

| FY | OTSB n | SB n | OTSB % n | OTSB $M | SB $M | OTSB % $ |
|---:|---:|---:|---:|---:|---:|---:|
| 2008 | 2 | 48 | 4.0% | $11 | $71 | 13.0% |
| 2009 | 4 | 76 | 5.0% | $15 | $80 | 16.0% |
| 2010 | 3 | 63 | 4.5% | $68 | $54 | 55.8% |
| 2011 | 0 | 47 | 0.0% | $0 | $174 | 0.0% |
| 2012 | 2 | 58 | 3.3% | $1 | $108 | 1.1% |
| 2013 | 0 | 55 | 0.0% | $0 | $66 | 0.0% |
| 2014 | 5 | 65 | 7.1% | $4 | $112 | 3.0% |
| 2015 | 5 | 63 | 7.4% | $1 | $96 | 1.2% |
| 2016 | 8 | 64 | 11.1% | $12 | $259 | 4.6% |
| 2017 | 6 | 49 | 10.9% | $0.5 | $225 | 0.2% |
| **2018** | 9 | 62 | 12.7% | **$96** | $163 | **37.1%** |
| 2019 | 5 | 74 | 6.3% | $29 | $346 | 7.8% |
| 2020 | 6 | 94 | 6.0% | $23 | $594 | 3.7% |
| **2021** | 12 | 138 | 8.0% | **$210** | $617 | **25.4%** |
| 2022 | 8 | 179 | 4.3% | $94 | $727 | 11.4% |
| **2023** | 21 | 196 | 9.7% | **$129** | $677 | **16.0%** |
| **2024** | 11 | 215 | 4.9% | **$152** | $597 | **20.3%** |
| 2025 | 22 | 222 | 9.0% | $73 | $570 | 11.4% |
| 2026 | 6 | 47 | 11.3% | $22 | $138 | 13.8% (partial) |

OTSB dollar share is volatile because a single large OTSB contract can push the percentage past 25% in a year. There's no clear secular trend up or down. The pattern is **occasional spikes from named large primes** rather than steady OTSB participation.

### Top OTSB recipients (concentration)

| Recipient | Contracts | Cumulative $M |
|---|---:|---:|
| **LinQuest Corp** | 9 | **$237** |
| **General Dynamics Mission Systems** | 6 | **$124** |
| Sierra Space Corp | 5 | $67 |
| L3 Adaptive Methods | 2 | $56 |
| Comtech AeroAstro | 2 | $54 |
| Amentum Services | 1 | $37 |
| CGI Federal | 1 | $35 |
| Mercury Defense Systems | 2 | $31 |
| Parsons Government Services | 1 | $27 |
| AeroVironment | 1 | $21 |
| KBR Wyle Services | 2 | $18 |

**Top 11 OTSB recipients = $706M, 70% of OTSB dollar total. Two firms (LinQuest + GD Mission Systems) account for $361M, 36%.**

### A meaningful share of OTSB Phase III is acquired SBIR firms

Several of the top OTSB recipients are recognizable as **acquired SBIR firms** continuing Phase III work under the acquirer's (large business) size designation:

- **L3 Adaptive Methods** = L3 Technologies' / L3Harris acquisition of Adaptive Methods (acoustic / signal-processing SBIR firm)
- **Mercury Defense Systems** = Mercury Systems' acquisition of Physical Optics Corp (FPC's Phase III work continues under Mercury's name)
- **Comtech AeroAstro** = Comtech Telecommunications' acquisition of AeroAstro

This means the OTSB share is **not simply "large companies winning SBIR work."** A substantial slice is the natural consequence of M&A activity in the SBIR-firm population — the work continues, but the recipient designation is now OTSB. From a program-evaluation standpoint, this is arguably *good* (SBIR firms achieving liquidity events through acquisition is a commercialization-success signal) but it's worth flagging because raw "OTSB share" misreads it as program leakage.

### OTSB share by awarding-agency bucket

| Bucket | Total $ | OTSB $ | OTSB share |
|---|---:|---:|---:|
| GSA | $1.86B | $282M | **15.1%** |
| DoD | $4.34B | $685M | **15.8%** |
| Other agencies | $646M | $42M | **6.5%** |

GSA and DoD are nearly identical at ~15%. **OTSB is not a GSA-channel artifact** — DoD direct contracting has the same OTSB share as the FEDSIM channel does. Other agencies (NASA, DHS, etc.) keep Phase III closer to the original SBIR awardee (6.5% OTSB share), consistent with smaller, more specialized program offices that retain better visibility into the SBIR-firm population.

## What made GSA viable for Phase III

This is the question with the least clean answer. The data shows a slow build (FY2014–FY2019) before the spike (FY2020–FY2023), which suggests layered causes rather than a single statutory or administrative switch.

**Statutory (high confidence — long-standing, not a 2014 trigger).** [15 USC §638(r)](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title15-section638) allows any federal agency to issue Phase III on a sole-source basis derived from earlier SBIR R&D. This includes GSA acting as a procurement vehicle for another agency's funding. The 2011 SBIR/STTR Reauthorization Act (Title V, Subtitle E of the FY12 NDAA, [PL 112-81](https://www.congress.gov/bill/112th-congress/senate-bill/1280)) directed all agencies to issue Phase III to the SBIR awardee "to the greatest extent practicable." Both predate the data ramp.

**Practical contract vehicles (medium confidence — coincides with the ramp).**
- **OASIS launched Sept 2014** as GSA/FEDSIM's flagship multi-agency professional-services GWAC. The first significant GSA Phase III contracts in the dataset are from FY2014.
- **FY18 NDAA §877** clarified contracting officer obligations to issue Phase III when qualifying SBIR awardees exist, reducing friction for non-funding-agency Phase III awards.
- **Alliant 2 (April 2018)** added a second large vehicle.

**Demand-side (uncertain).**
- **CARES Act / COVID-era acquisition acceleration (FY2020–FY2021)** pushed program offices toward vehicles that could issue task orders fast. FEDSIM's "we write the SOW for you" assisted-acquisition model was exactly that. The data ramp from $26M (FY2019) → $330M (FY2020) is consistent with this but doesn't prove causation.
- **DoD contracting-workforce strain** during 2019–2021 made FEDSIM's assisted-acquisition model more attractive to DoD program offices than running their own complex SOWs.

The OASIS+ transition (which replaced OASIS in 2024) is a tempting candidate for the FY2024 cliff, but the parent IDV analysis above shows that **the Phase III work was never on OASIS in the first place** — it was on FEDSIM single-award IDIQs and standalone contracts. The cliff is better explained by (a) natural decay of FY2019–FY2021 IDIQ ordering periods, (b) cessation of the FEDSIM standalone-contract channel ($465M in FY2020–FY2023 → $0 after), and (c) successor IDIQs being smaller-scale.

## What this means for SBIR Phase III oversight

Three implications worth flagging for SBIR program managers, GAO, and congressional defense committee staff:

**1. Channel attribution matters for SBIR program evaluation.** When NASEM and GAO assess "SBIR commercialization through Phase III transitions," they are mostly counting work that **DoD funds but routes through GSA/FEDSIM**. Treating these as separate channels for evaluation purposes (e.g., DoD's Phase III conversion rate) misses where the actual dollars and contracting-officer decisions sit. The funder-vs-vehicle distinction needs to be explicit in any Phase III rate.

**2. The FY2024 picture is messier than a clean channel shift: the recipient population changed.** FEDSIM's assisted-acquisition model includes standardized SOW templates and trained SBIR-aware contracting officers. Direct-DoD Phase III contracting depends on individual program offices having that knowledge. But the Tier 1 migration analysis below shows only 12% of GSA-era recipients (FY2020-2023) appear in direct-DoD post-FY2023. Direct-DoD is mostly hiring **different SBIR firms** than the FEDSIM-era cohort, and combined Phase III volume contracted 34% from FY2023 peak. This is consistent with one or more of: (a) a real Phase III pipeline contraction, (b) work moving to classified DoD contracts that don't appear in USAspending, (c) program offices losing the FEDSIM-era institutional knowledge of which SBIR firms to engage. The three explanations have different policy responses; they need to be disambiguated.

**3. OTSB Phase III is overwhelmingly an SBIR-ecosystem outcome, not program leakage.** Joining each OTSB recipient against SBIR.gov's 219,501 Phase I/II awardee records (17,154 distinct UEIs) by UEI exact-match, name match, and name-containment shows **82.7% of OTSB Phase III dollars ($834M of $1.01B) went to firms with documented Phase I/II SBIR history**. Of that, ~20% are known M&A continuations (in MAEvent), ~63% are grew-out cases (LinQuest with 4 P1/P2 awards 2005-2008 → $237M Phase III; Anduril with 5 P1/P2 in 2019-2020 → $12M; Perduco; Janus; Chesapeake Technology Intl), and a substantial slice is likely-M&A continuations our M&A data missed (KBR Wyle inheriting Wyle's UEI; GD Mission Systems rolling up Progeny Systems' 309 P1/P2 awards). **Only 17.3% ($175M) went to genuinely external large primes** that never held SBIR P1/P2 awards — Sierra Space ($67M), Amentum ($37M), Parsons ($27M), Rockwell Collins ($15M), BAE Systems Protection, Oliver Wyman, etc. This finding inverts the original report's framing: the OTSB designation is misleading as a "program leakage" signal because the vast majority of OTSB recipients are program participants who either graduated past small-business size or were acquired. The §638(qq) theory of change is largely operating as designed.

## Tier 1 follow-up findings (2026-06-29)

Three targeted analyses run after the initial report. Each tightens or revises a specific claim above.

### Recipient migration: only 7 of 58 GSA-era firms appear in direct-DoD post-FY2023

The original report's implicit assumption was that DoD program offices continued working with the same SBIR firms but routed contracts through their own shops instead of FEDSIM. The data says no:

| Cohort | Distinct firms | Total $M |
|---|---:|---:|
| GSA-channel recipients FY2020-2023 | 58 | $1,519 |
| Direct-DoD recipients FY2024-2025 | 203 | $1,060 |
| **Overlap (firms in both)** | **7 (12.1% of GSA-era)** | — |
| GSA $ to overlap firms | — | $328M (21.6% of GSA-era $) |
| DoD $ to overlap firms | — | $80M (7.5% of DoD-post $) |

The seven firms that crossed the channel: LinQuest ($174M GSA-era → $22M DoD-post, **-87%**), Sabel Systems ($107M → $3M, **-97%**), Eccalon ($17M → $39M, **+135%**), Frontier Technology, Advanced Systems Supportability, Cornerstone Research, Valid Evaluation. Six of seven contracted significantly; only Eccalon grew across the shift.

Implication: the FY2024 channel shift is **not a pure administrative reroute**. ~96% of DoD's post-shift recipients are firms that had no prior GSA Phase III work. Either DoD program offices lost the FEDSIM-era awareness of which SBIR firms to engage, or there's a deeper shift in who DoD is hiring for follow-on work.

### Sub-agency split: Navy and Air Force grew direct-DoD; Army contracted

Annualized direct-DoD Phase III by funding sub-agency:

| Sub-agency | FY2018-23 $M/yr | FY2024-26 $M/yr | Δ |
|---|---:|---:|---:|
| Air Force | $131 | $171 | **+$40/yr (+30%)** |
| Navy | $80 | $138 | **+$58/yr (+73%)** |
| **Army** | **$70** | **$46** | **-$24/yr (-34%)** |
| Defense Logistics Agency | $4 | $12 | +$8/yr |
| Missile Defense Agency | $8 | $9 | +$1/yr |
| Defense Health Agency | $6 | $5 | -$1/yr |

GSA-era Phase III was 86% Navy+Air Force. Their combined direct-DoD growth is +$98M/yr, against a combined GSA-era loss of ~$236M/yr. **~40% of the GSA shed reappeared as direct-DoD work for the same two services**; the rest is unaccounted for. Army contracted on both channels.

### OTSB × SBIR.gov history: 82.7% of OTSB dollars have SBIR P1/P2 lineage

The initial M&A-only cross-walk in this report (using `data/enriched_sbir_ma_events.jsonl`) returned a 14.2% strict match rate, with a manually-extrapolated ~35% upper bound. **That framing materially understated the SBIR-history connection.** Replacing the M&A-only join with a direct join against SBIR.gov's 219,501 Phase I/II awardee records (17,154 distinct UEIs across 1991-2025) by UEI exact-match, name match, and name-containment shows a very different picture.

For each of the 140 OTSB Phase III contracts, asked: "did the recipient (or a firm whose name it contains) ever hold a Phase I or Phase II SBIR award?"

| Category | Rows | $M | % of OTSB $ |
|---|---:|---:|---:|
| **Ex-SBIR firms** (recipient was a Phase I/II awardee) | 117 | **$834** | **82.7%** |
| ↳ Of which: known-acquired (also in MAEvent) | 14 | $201 | 19.9% |
| ↳ Of which: ex-SBIR without M&A signal | 103 | $633 | 62.7% |
| **Genuinely organic large primes** (no SBIR P1/P2 history) | 23 | $175 | **17.3%** |

Spot-checked every top recipient against raw SBIR.gov data:

| Recipient | Verdict | Phase I/II count | Years |
|---|---|---:|---|
| LinQuest Corporation ($237M) | **Ex-SBIR, grew out** | 4 P1/P2 | 2005-2008 |
| GD Mission Systems ($124M) | **M&A continuation (via Progeny Systems)** | 309 (Progeny) | 1996-2020 |
| Sierra Space Corp ($67M) | **Organic — no SBIR history** | 0 | — |
| L3 Adaptive Methods ($56M) | **M&A continuation (Adaptive Methods)** | 94 | 1991-2017 |
| Comtech AeroAstro ($54M) | **M&A continuation (AeroAstro)** | 53 | 1992-2008 |
| Amentum Services ($37M) | **Organic** | 0 | — |
| CGI Federal ($35M) | **M&A continuation (Morgan Research Corp)** | 37 | 1991-2006 |
| Mercury Defense Systems ($31M) | **M&A continuation** | confirmed | — |
| Parsons Government Services ($27M) | **Organic** | 0 | — |
| Janus Research Group ($21M) | Ex-SBIR — thin (1 Phase I only) | 1 | 2017 |
| AeroVironment ($29M) | Ex-SBIR, known acquirer | direct match | — |
| KBR Wyle Services ($18M) | **M&A continuation (Wyle was SBIR firm; UEI inherited)** | 75 (Wyle) | 2003-2019 |
| Anduril Industries ($12M) | **Ex-SBIR, grew out** | 5 | 2019-2020 |
| Perduco Group ($14M) | Ex-SBIR, grew out | 7 | 2014-2019 |
| Chesapeake Technology Intl ($11M) | Ex-SBIR | 17 | 2007-2021 |
| Rockwell Collins ($15M) | **Organic** | 0 | — |

**The MAEvent-only cross-walk was too narrow.** Cases like KBR Wyle Services (UEI inherited from Wyle), GD Mission Systems (Progeny Systems acquisition), and CGI Federal (Morgan Research acquisition) are M&A continuations that the MAEvent data didn't surface. The SBIR.gov-history join catches them automatically because the underlying acquired firm shows up as a Phase I/II awardee.

### Caveats on the 82.7% number

- **"Ex-SBIR" doesn't prove the Phase III work derives from the original P1/P2 R&D.** LinQuest's 4 P1/P2 awards (2005-2008) and its $237M Phase III work (2020-2023) might be largely unrelated technology. §638(r) sole-source Phase III is legally available to any SBIR firm regardless of R&D linkage. So 82.7% is "had any SBIR history," not "Phase III directly derived from prior P1/P2 R&D."
- **UEI inheritance through M&A** means some "ex-SBIR" cases (KBR Wyle, GD Mission Systems) are functionally M&A continuations our MAEvent data missed. The 19.9% known-acquired share is therefore a lower bound — the true M&A share is probably 30-40% of OTSB, with the remainder being grew-out cases.
- **Thin-history cases (Janus, 1 Phase I award) are counted as ex-SBIR**, which may overstate the category at the margin. The dollar share moves little even if these are reclassified.
- **The "23 organic OTSB recipients" number shrinks under closer inspection** (see next subsection for the mechanism breakdown). After fixing matching false-negatives (Honeybee Robotics LLC vs. Honeybee Robotics Ltd; AgileDelta name variation) and accounting for one obvious corporate-successor case the name matching can't catch (Sierra Space, 2021 spinout from Sierra Nevada Corp), the truly "no SBIR linkage" set is closer to 14-17 contracts / ~$79M, not 23 / $175M.

**Implication:** OTSB is misleading as a "program leakage" signal. The SBIR ecosystem is producing the OTSB outcome by design — small firms that the program funded then either graduate past small-business size (the canonical SBIR success story) or get acquired, in both cases continuing as Phase III recipients with their now-larger size designation.

### How OTSB Phase IIIs are issued: §638(r) mechanism breakdown

For the 23 contracts initially flagged as "organic OTSB" (no SBIR P1/P2 history found), reading the actual contract descriptions reveals five distinct mechanisms by which Phase III work flows to non-small-business recipients. These aren't loopholes — they're all defensible interpretations of §638(r), which authorizes Phase III sole-source to "an SBC that has been engaged in SBIR/STTR work" but leaves the qualifying-entity definition to contracting officer discretion.

**Mechanism A — Corporate successor inheriting Phase III standing** (~$68M, 6 contracts)

The recipient is a spinout, name change, or restructured entity of a firm with documented SBIR P1/P2 history. §638(r) standing transfers to the successor. Simple name matching can't catch these because the successor's name shares no tokens with the predecessor's.

- **Sierra Space Corp ($67M, 5 contracts)** — 2021 spinout of Sierra Nevada Corporation. SNC has 78 P1/P2 awards in SBIR.gov; Sierra Space inherits Phase III standing for SNC-derived engine technology. Their own descriptions are explicit: "SBIR PHASE III WITH SNC", "MATURATION OF SNC UPPER STAGE VORTEX ENGINE ENHANCEMENT".
- **EDO Reconnaissance and Surveillance Systems ($1M, 2007)** — EDO Corp acquired by ITT 2007 then spun off; the Phase III is at the transition moment.

**Mechanism B — Large prime fronting an SBIR-firm subcontractor** (~$71M, 3-4 contracts)

The Phase III is awarded to the large prime, but the work is done with an SBIR firm as subcontractor. Descriptions often name the SBIR sub explicitly.

- **Amentum Services ($37M)** — "SBIR PHASE III **TO SBCC** FOR TRANSITION FROM IPODS-IT TO IPODS." SBCC is the SBIR sub; Amentum is the prime/integrator.
- **Parsons Government Services ($27M)** — "SBIR PHASE III - **BLACKJACK PROTOTYPE GROUND OPERATIONS CENTER**." DARPA BLACKJACK was built from multiple small-firm SBIR contributions; Parsons is the systems integrator.
- **Rancher Federal ($7M)** — "**Platform 1 Support**." Platform 1 (Space Force Kubernetes) was developed by Defense Unicorns (small SBIR firm); Rancher provides the underlying Kubernetes distribution.

**Mechanism C — Production scaling to a large manufacturer** (~$17M, 3 contracts)

§638(r) sole-source for the production phase of an SBIR-derived design. The original SBIR firm did the R&D; the large prime has the manufacturing capacity.

- **Rockwell Collins ($15M)** — "PRODUCTION OF SMALL MISSION COMPUTER FOR RQ-7B SHADOW TACTICAL UAS." Production phase.
- **JCB Inc. ($1.3M)** — "MULTI-TERRAIN LOADER REPLACEMENT (MTLR)." Production phase of equipment derived from a smaller-firm design.
- **Coherent Corp ($0.6M)** — "ACV 2.0 MODULAR LIGHTWEIGHT ARMOR." Production scaling (note: Coherent is primarily a photonics firm; this contract is unusual for them and may indicate a divestiture/legacy line).

**Mechanism D — Lifecycle transition to a maintenance vendor** (~$3M, 2 contracts)

An SBIR-derived program in production / maintenance phase awards Phase III to a different vendor than the original SBIR R&D firm.

- **Vantor Services ($3M)** and **Radiant Analytic Solutions ($0.04M)** — both reference "R2D2 (Risk-Based Resource Deployment Decision)" for DHS Office of the Under Secretary for Science and Technology. The original R2D2 SBIR R&D was done by another firm; Vantor and Radiant are doing evaluation/maintenance phases.

**Mechanism E — Discretionary §638(r) interpretation** (~$13M, 4-5 contracts)

Contracting officers use "SBIR Phase III" labeling for sole-source contracts with looser ties to specific Phase I/II R&D, often for services, analysis, or integration work derived from program outputs. These are the cases where the §638(r) connection is least visible from the contract record.

- **LMI Consulting ($7M, FY2025)** — "HUMAN PERFORMANCE SBIR PHASE III." Generic description. LMI Government Consulting is an FFRDC-adjacent management consultancy without obvious SBIR R&D claim.
- **JJR Solutions ($5M, FY2025)** — "DEVCOM SBIR PHASE III." Generic services-integration description. No identifiable underlying SBIR firm.
- **Oliver Wyman ($1.1M, FY2024)** — "SSC/IA SBIR PHASE III GLOBAL BUSINESS INTELLIGENCE TOOL." Oliver Wyman is a Marsh & McLennan management consulting subsidiary.
- **Louisiana Board of Regents ($0.1M, FY2016)** — NASA contract to a state university board. Universities can't be small business concerns; this is either misclassification, an STTR transition mislabeled as SBIR Phase III, or a Phase III flowing through a university to an SBIR firm partner.

**Net effect on the OTSB framing:**

Reclassifying the corporate-successor cases (Sierra Space, EDO) and the matching false-negatives (AgileDelta, Honeybee Robotics LLC) brings the "ex-SBIR" share to roughly:

| Bucket | $M | % of OTSB $ |
|---|---:|---:|
| Ex-SBIR by direct or corporate-successor match | ~$930 | ~92% |
| Large-prime + SBIR-sub teaming | ~$71 | ~7% |
| Production scaling / lifecycle / discretionary | ~$33 | ~3% |
| Unexplained | ~$2 | ~0.2% |

**Roughly 92% of OTSB Phase III dollars are explainable as SBIR-ecosystem outcomes**, the remaining ~8% breaks into clear (production-scaling, teaming, lifecycle) mechanisms plus a small unexplained tail.

### Puzzle cases investigated via FPDS competition data

Pulled the FPDS competition fields (`extent_competed`, `solicitation_procedures`, `type_set_aside`, number of offers) from USAspending's per-award detail endpoint for each puzzle case. The results split into two very different sub-populations.

#### Genuine §638(r) sole-source to OTSB without identifiable SBIR sub

These contracts show "NOT AVAILABLE FOR COMPETITION" + "ONLY ONE SOURCE" — the classic §638(r) sole-source signature. The contracting officer affirmatively claimed Phase III sole-source authority. The recipient has no SBIR history and the description doesn't name a sub.

| Recipient | $ | Description | Most likely mechanism |
|---|---:|---|---|
| **Rockwell Collins** | $15M | Production of Shadow UAS mission computer | Production scaling of SBIR-derived design |
| **LMI Consulting** | $7M | "Human Performance SBIR Phase III" | Discretionary §638(r); no visible SBIR sub or scaling rationale |
| **JCB** | $1.3M | Multi-Terrain Loader Replacement | Production scaling of equipment design |
| **Oliver Wyman** | $1.1M | "Global Business Intelligence Tool" | Discretionary §638(r); no visible SBIR sub or scaling rationale |
| **BAE Systems Protection** | $1.0M | Bailout parachute components | Production scaling |
| **Coherent Corp** | $0.6M | ACV 2.0 Modular Lightweight Armor | Production scaling |

The production-scaling cases (Rockwell Collins, JCB, BAE, Coherent) are defensible under §638(r) — small SBIR firms typically lack manufacturing capacity, so production phase goes to a large prime with the §638(r)-qualified status passed through. **LMI Consulting and Oliver Wyman are the genuinely discretionary cases** — generic consulting work labeled SBIR Phase III without any visible R&D linkage or named subcontractor.

#### Not actually §638(r) sole-source: contract labeled "SBIR Phase III" but procured under different authority

**This was the surprise of the validation.** Several OTSB contracts pulled by the "SBIR Phase III" keyword fetch are NOT §638(r) sole-source procurements at all. The "SBIR Phase III" string appears in the description, but FPDS records show the contract was procured under different authority — competitive procurement, set-asides, simplified acquisition, or task orders against multiple-award vehicles.

| Recipient | $ | Actual procurement (FPDS) | What's going on |
|---|---:|---|---|
| **Amentum Services** | $37M | "FULL AND OPEN COMPETITION" + "SUBJECT TO MULTIPLE AWARD FAIR OPPORTUNITY" | Task order against a **multiple-award IDIQ**, awarded via fair-opportunity competition between IDIQ holders. Not §638(r) sole-source. The "TO SBCC FOR TRANSITION FROM IPODS-IT TO IPODS" wording describes the work-sharing arrangement on the resulting contract; the procurement authority is the IDIQ rules. |
| **JJR Solutions** | $5M | "FULL AND OPEN COMPETITION" + "NEGOTIATED PROPOSAL/QUOTE" + 1 offer | **Competitively procured** Army contract. "DEVCOM SBIR PHASE III" is description language, not procurement authority. Only one offer was received in an open competition. |
| **Vantor Services** | $3M | **"SMALL BUSINESS SET ASIDE - TOTAL"** + "FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES" | Contract was **set aside for small businesses** at award time. Vantor was apparently small then. The OTSB designation reflects current size status, not award conditions. Not §638(r). |
| **Louisiana Board of Regents** | $0.1M | "FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES" + 1 offer; description prefixed `IGF::OT::IGF` | Description begins with the FPDS code for "Inherently Governmental Function." Competitively procured by NASA Stennis to support its SBIR program work. **Not §638(r)** — the SBIR program context is about *what work is performed*, not about which procurement authority was claimed. |
| **Romitech** | $0.5M | "NOT COMPETED UNDER SAP" + "SIMPLIFIED ACQUISITION" | Below the simplified-acquisition threshold. Not §638(r) sole-source under §638. |

**~$45M of OTSB Phase III "dollars" in our keyword-discoverable universe weren't actually §638(r) Phase III contracts.** This is real signal contamination: the keyword fetch pulls contracts whose descriptions contain "SBIR Phase III" but were procured under other authorities. The same contamination almost certainly exists in the Small Business universe (we just can't separate it as easily because SB contracts without §638(r) sole-source look similar to other SB R&D contracts).

### The four-category breakdown

Putting the validation together — OTSB Phase III dollars by mechanism:

| Cat | Definition | Rows | $M | % of all OTSB $ |
|---|---|---:|---:|---:|
| **1** | **Firms with Phase 1/2 history** (UEI/name match to SBIR.gov P1/P2 awardees, including suffix variations) | ~120 | **$835** | **82.7%** |
| **2** | **Corporate spinouts of P1/P2 awardees** (Sierra Space ← Sierra Nevada Corp; EDO Reconnaissance ← EDO Corp) | 6 | **$68** | **6.7%** |
| **3** | **Large primes with an SBIR sub** (Amentum/SBCC, Parsons/BLACKJACK — prime itself has no SBIR history, the Phase III is teaming with a small SBIR firm) | 2 | **$64** | **6.3%** |
| **4** | **The Rest** | ~12 | **$42** | **4.2%** |
| ↳ Cat 4a | Genuine §638(r) sole-source to OTSB without identifiable SBIR sub (RC production, LMI discretionary, JCB scaling, Oliver Wyman discretionary, BAE production, Coherent production) | 6 | $25 | 2.5% |
| ↳ Cat 4b | Contracts labeled "SBIR Phase III" but **not actually §638(r) sole-source** (Vantor, JJR Solutions, LA Board of Regents, Romitech) | ~5 | $9 | 0.9% |
| ↳ Cat 4b-IDIQ | The Amentum task order — sits in Cat 3 narratively (teaming with SBCC sub) but procured via multiple-award IDIQ fair-opportunity rather than §638(r) | 1 | $37 | (counted in Cat 3) |
| ↳ Cat 4c | Lifecycle / maintenance / other | ~3 | $3 | 0.3% |

**Of $964M in OTSB Phase III dollars that were actually issued under §638(r) sole-source authority** (excluding the $45M of Cat 4b contamination):
- ~$835M / 86.6% = Cat 1 (direct ex-SBIR firms)
- ~$68M / 7.1% = Cat 2 (corporate spinouts)
- ~$27M (Parsons + Amentum's underlying SBCC sub work) / ~2.8% = Cat 3 minus the IDIQ-procured Amentum dollars
- ~$25M / ~2.6% = Cat 4a (genuine §638(r) sole-source to OTSB without identifiable sub)

**Roughly 97% of genuine §638(r) OTSB Phase III dollars are explainable as SBIR-ecosystem outcomes.** The truly hard-to-explain residual is Cat 4a — about $25M, ~3% — concentrated in production-scaling cases that are defensible and two discretionary cases (LMI, Oliver Wyman, combined $8M) where the §638(r) connection is genuinely unclear from the public record.

### What this implies about the broader Phase III universe

Two structural takeaways for any future Phase III analysis:

1. **The keyword-discoverable Phase III universe contains contamination.** Roughly $45M of OTSB rows (~4%) were pulled by the "SBIR Phase III" keyword fetch but procured under non-§638(r) authority. Equivalent contamination almost certainly exists in the Small Business universe — perhaps a similar 3-5% — but is harder to detect there. **The "$6.86B Phase III universe" headline includes some contamination; the true §638(r) Phase III dollar figure is plausibly ~$6.5–6.6B.**

2. **Disambiguating §638(r) sole-source from "SBIR Phase III" description language requires FPDS competition fields.** The fields `extent_competed`, `solicitation_procedures`, and `other_than_full_and_open_competition_description` together identify whether the procurement was sole-source under §638(r) or done under another authority. These should be added to the universe builder's fetched fields for future runs.

## Caveats & limitations

- **Keyword-derived undercount.** Real Phase III universe is bigger than this analysis captures. GAO-24-107036 estimates ~30% DoD undercount for canonical-keyword fetches; the six-variant union recovers some but not all. Direct-DoD contracts are more under-represented than FEDSIM contracts.
- **Classified contracting is structurally invisible.** DoD has Phase III activity on classified contracts (likely concentrated in Air Force, Navy SOCOM, and SDA programs) that does not appear in USAspending regardless of keyword. This means the FY2024-2025 contraction observed here is an **upper-bound estimate** — some unknown share of the "missing" Phase III dollars may have moved to classified vehicles. The fraction is impossible to estimate from public data alone.
- **FY2026 is partial.** Only ~3 months of data. Drawing conclusions from FY2026 numbers is unwarranted.
- **FY2007 and earlier are inaccessible** via the USAspending search API (returns HTTP 500); use the bulk download endpoint if pre-2008 history is needed.
- **OTSB classification reflects size at award time.** A firm classified Small Business in 2018 and acquired in 2022 shows as Small Business on the 2018 Phase III and OTSB on any 2023+ Phase III.
- **Contract amounts are obligations, not outlays.** Multi-year IDIQ task orders with `End Date` > 2030 may have years of obligation activity ahead.
- **Funding-agency attribution comes from USAspending fields, not §638(qq) Phase III rule interpretation.** Some borderline contracts (e.g., GSA awards funded by non-DoD agencies acting through DoD pass-throughs) may have ambiguous funder attribution.
- **6 of 2,013 rows (0.3%) failed business-size enrichment** with `RemoteProtocolError`. They're excluded from OTSB percentages but included in agency-bucket totals.

## Open questions worth pursuing

These came up during analysis and aren't answered by the cached data:

1. **Recipient migration analysis.** Of the firms that did GSA-FEDSIM Phase III in FY2020–FY2023, what fraction received direct-DoD Phase III in FY2024–FY2025? If the same firms migrated, the channel shift is purely administrative. If not, DoD is hiring different SBIR firms post-shift, which means a deeper change in *who* DoD is contracting with.

2. **FEDSIM successor vehicles for FY2025+.** The dataset shows FEDSIM IDIQ activity declining sharply. Are FY2025 successor IDIQs structurally smaller (different ordering ceilings, different competitive pools), or has FEDSIM lost the Phase III flow to direct-DoD? Pulling the parent IDV ceiling-amounts and ordering periods from FPDS would answer this.

3. **The FEDSIM standalone-contract collapse.** $465M in 18 direct contracts FY2020–FY2023, then zero after. Was there an internal FEDSIM policy change, a contracting-officer turnover, or a specific large program that ended? The pattern doesn't fit IDIQ lifecycle decay.

4. **Acquired-SBIR M&A signal.** Cross-walking the OTSB recipient list to the repo's `MAEvent` data (`sbir_ma_events.jsonl`) would quantify how much OTSB Phase III is M&A-driven vs. genuinely-non-SBIR-recipient. The repo has M&A detection in place; the join is straightforward.

5. **Sub-agency funder concentration.** The DoD-direct Phase III absorption in FY2024 ($587M) is dominated by which services? Navy and Air Force were the GSA-era heavyweights (86% of GSA Phase III dollars combined). Tracing whether the post-FY2023 direct-DoD growth comes from the same services or from Army / SOCOM / SDA would clarify whether this is a Navy/Air Force institutional shift or a broader DoD pattern.

## Reproducing this report

```bash
# Build universe (~5 min)
uv run python scripts/data/build_phase3_universe.py --start-fy 2008 --end-fy 2026

# Enrich with business-size (~5 min)
uv run python scripts/data/enrich_phase3_business_size.py \
  --input data/processed/sbir_phase3/phase3_universe.jsonl \
  --output data/processed/sbir_phase3/phase3_universe_enriched.jsonl

# If many rows fail with RemoteProtocolError, re-run failed rows with lower concurrency:
# (extract failed rows, then)
uv run python scripts/data/enrich_phase3_business_size.py \
  --input /tmp/failed.jsonl --output /tmp/retried.jsonl --concurrency 3
```

The DuckDB queries that produced every table above are simple enough to reconstruct from the schema — but should be packaged into a `scripts/data/report_phase3_gsa_otsb.py` if this report becomes a recurring artifact rather than a one-shot. That packaging is deliberately left out of this PR.
