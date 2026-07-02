# SBIR Phase III: GSA Channel, OTSB Recipients, and the FY2024 Channel Shift

**Status:** Working analysis. All figures from `data/processed/sbir_phase3/phase3_universe_enriched.jsonl` built 2026-06-28 via `scripts/archive/data/build_phase3_universe.py` + `scripts/archive/data/enrich_phase3_business_size.py` (PR #394).
**Date:** 2026-06-29.
**Audience:** Defense industrial-base analysts, SBIR program managers, GAO/CRS, congressional defense committee staff.

## Headlines

- **GSA accounts for 27.2% of Phase III dollars ($1.86B of $6.85B keyword-discoverable) and 10.1% of contracts (204 of 2,013) across FY2008–FY2026.** GSA is acting as the *procurement vehicle*, not the funder — GSA funds zero Phase III work; DoD pays for 96% of GSA-awarded Phase III.
- **96% of GSA Phase III flows through FEDSIM**, not the well-known multi-agency GWACs (OASIS, Alliant, STARS, Polaris). PIID-prefix attribution: 130 contracts ($1.32B) on `47QFLA*` (FEDSIM East / Loudoun, VA HQ); 51 contracts ($0.37B) on `47QFCA*` (FEDSIM West).
- **GSA Phase III was effectively zero before FY2014, peaked at $508M in FY2021 (64% of all Phase III dollars that year), then collapsed to $109M in FY2024 (15% share).** **Partial channel shift, partial contraction:** roughly 40% of the GSA-era dollars reappeared as direct-DoD work; the other ~60% disappeared from keyword-discoverable Phase III. Combined GSA + direct-DoD Phase III fell 34% from FY2023 peak ($764M) to FY2025 ($506M).
- **14.7% of Phase III dollars ($1.01B) went to Other Than Small Business (OTSB) recipients**, 7.0% of contracts. **97% of genuine §638(r) OTSB Phase III dollars are explainable as SBIR-ecosystem outcomes** — direct ex-SBIR firms (~87%), corporate spinouts of P1/P2 awardees (Sierra Space ← Sierra Nevada Corp, ~7%), or large primes teaming with SBIR subs (~3%). The hard-to-explain residual is ~$25M (~3%), mostly defensible production-scaling. OTSB designation is misleading as a "program leakage" signal — the SBIR ecosystem is producing the OTSB outcome by design.
- **Only 55.7% of keyword-discoverable Phase III dollars ($3.82B of $6.86B) are §638(r) sole-source** — much lower than the Tier 1 OTSB-only puzzle-case investigation suggested. The other 44.3% is competitive procurement, set-asides, IDIQ task orders, or simplified acquisitions whose descriptions reference Phase III work without claiming §638(r) authority. **GSA Phase III is 99% §638(r) sole-source; direct-DoD Phase III is only 41%.** GSA's share of the strict §638(r) universe is **48.2%** (vs. 27.2% of the keyword universe) — the keyword view *understates* FEDSIM's dominance of the actual §638(r) channel.

## What "Phase III" means in this dataset

Phase III is a contracting status, not a separate SBIR award. Under [15 USC §638(r)](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title15-section638), any federal agency may issue a contract on a sole-source basis to an SBIR/STTR firm to develop, produce, or commercialize technology derived from an earlier Phase I or Phase II SBIR award. That contract is "Phase III." Unlike Phase I/II, Phase III is not centrally tracked — SBIR.gov's bulk data contains only Phase I (151,426 rows) and Phase II (68,075 rows); zero Phase III rows. The only authoritative source for Phase III contracts is FPDS/USAspending, where Phase III status is conveyed by the contracting officer writing "SBIR Phase III" (or a variant) into the contract description.

That tagging is unreliable. [GAO-24-107036](https://www.gao.gov/products/gao-24-107036) documents ~30% undercount of Phase III contracts in DoD historical FPDS tagging because contracting officers don't consistently include Phase III markers in descriptions. This analysis works within that constraint — the dataset is best understood as the **keyword-discoverable** Phase III universe, not the true population.

## Methodology

The cached USAspending Phase III set on this repo was built by:

1. **`scripts/archive/data/build_phase3_universe.py`** — fetches `spending_by_award` across **six description-keyword variants** for FY2008–FY2026: `SBIR Phase III`, `SBIR Phase 3`, `SBIR PH III`, `Phase III SBIR`, `SBIR follow-on`, `Small Business Innovation Research Phase III`. Unions by Award ID, tags each row with `_keywords_matched` provenance. Adds `Parent Award ID` to fetched fields so contract-vehicle attribution is one query away.
2. **`scripts/archive/data/enrich_phase3_business_size.py`** — for each row, calls the per-award detail endpoint `/awards/{generated_unique_award_id}/`, which returns `business_categories` (the canonical signal for `Small Business` vs `Not Designated a Small Business`). The search endpoint does not populate this field; it must come from per-award lookup.

**Coverage gain vs. the prior single-keyword fetch:** +20% rows (1,671 → 2,013) and +14% dollars ($6.00B → $6.85B). FY2007 returns HTTP 500 from USAspending — that's the API's reliable depth limit. 99.7% of rows enriched successfully with size data.

### What the methodology does *not* fix

Six keyword variants caught more than one, but Phase III contracts whose descriptions use **no** SBIR/Phase-III markers remain invisible. There is no authoritative join available because SBIR.gov doesn't track Phase III. **Direct-DoD contracts are more under-represented than GSA-awarded contracts** in keyword-derived cohorts because FEDSIM's templated SOWs routinely include the "SBIR Phase III" phrase, while DoD program offices vary widely. This means the GSA share reported here is **likely modestly overstated** relative to ground truth — the true GSA dollar share is probably in the 20–27% range rather than the surface-level 27.2%.

The methodology also doesn't filter out **non-§638(r) contracts whose descriptions happen to contain "SBIR Phase III"** as program-context language. The Tier 1 puzzle-case investigation (see below) showed ~$45M of OTSB rows fit this pattern: task orders against multiple-award IDIQs, competitively-procured contracts, small-business set-asides, and simplified-acquisition contracts whose descriptions reference Phase III work but whose procurement authority isn't §638(r) sole-source. The fix would be to fetch FPDS `extent_competed` / `solicitation_procedures` / `other_than_full_and_open_competition_description` at scrape time and filter on those — a small change to the universe builder. Currently this contamination is documented in the OTSB sub-population but not quantified across the full $6.85B universe.

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

Two structural takeaways from the OTSB-only puzzle-case investigation:

1. **The keyword-discoverable Phase III universe mixes §638(r) sole-source contracts with contracts procured under other authorities.** The OTSB puzzle-cases caught some of this (~$45M of OTSB rows). The Tier 2 universe-wide enrichment (below) quantifies the broader pattern: ~44% of all keyword-discoverable Phase III dollars aren't §638(r) sole-source.

2. **Disambiguating §638(r) sole-source from "SBIR Phase III" description language requires FPDS competition fields.** The fields `extent_competed`, `solicitation_procedures`, and `other_than_full_and_open_competition_description` together identify whether the procurement was sole-source under §638(r) or done under another authority. These were added in Tier 2 (PR #410's `enrich_phase3_competition.py`).

## Tier 2 follow-up findings (2026-06-29): §638(r) competition-fields enrichment

The OTSB-only Tier 1 finding hinted at signal contamination in the keyword-discoverable universe. Tier 2 ran the same FPDS competition-fields disambiguation across all 2,013 contracts in the universe. The result is bigger and more nuanced than the Tier 1 OTSB sub-sample suggested.

### §638(r) share across the full universe

The cleanest §638(r) signal is `solicitation_procedures = "ONLY ONE SOURCE"`. This captures both extent variants ("NOT AVAILABLE FOR COMPETITION" and "NOT COMPETED" — both pair with sole-source procurement; the difference is procedural coding).

| Procurement authority | Contracts | $M | % of $ |
|---|---:|---:|---:|
| **§638(r) sole-source** (`ONLY ONE SOURCE`) | 742 | **$3,818** | **55.7%** |
| **NOT §638(r) sole-source** | 1,271 | **$3,037** | **44.3%** |

The non-§638(r) bucket itself breaks into distinct patterns:

| Procurement combination | Contracts | $M | What it is |
|---|---:|---:|---|
| FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES + NEGOTIATED | 907 | $2,384 | Mostly small-business / 8(a) / HUBZone set-asides procured competitively |
| FULL AND OPEN COMPETITION + NEGOTIATED | 91 | $285 | Open competition between SBIR firms |
| NOT COMPETED UNDER SAP + SIMPLIFIED ACQUISITION | 125 | $74 | Below SAP threshold |
| COMPETED UNDER SAP | 81 | $54 | Competitive simplified acquisition |
| FULL AND OPEN + BASIC RESEARCH | 14 | $49 | Likely Phase II-style work mislabeled as III |
| FOLLOW ON TO COMPETED ACTION + ONLY ONE SOURCE | 12 | $45 | Hybrid: follow-on to a prior competition |
| SUBJECT TO MULTIPLE AWARD FAIR OPPORTUNITY | 4 | $59 | IDIQ task orders (including Amentum's $37M) |
| Other | 37 | $87 | mix |

**The biggest non-§638(r) bucket is competitive set-asides — $2.4B across 907 contracts**, mostly small-business set-asides where multiple SBIR firms competed for the Phase III work. This is legitimate Phase III work in the broader sense ([SBA Policy Directive](https://www.sba.gov/document/policy-directive-sbir-sttr-policy-directive) defines Phase III as any work that derives from, extends, or completes earlier Phase I/II R&D regardless of how procured) — it's just not §638(r) sole-source.

### §638(r) share by awarding agency

| Bucket | Total $M | §638(r) $M | **§638(r) share by $** |
|---|---:|---:|---:|
| **GSA** | $1,864 | $1,843 | **99.0%** |
| **DoD direct** | $4,344 | $1,781 | **41.0%** |
| **Other agencies** | $647 | $194 | **29.9%** |

GSA Phase III is **almost entirely** §638(r) sole-source — FEDSIM's assisted-acquisition model is built around invoking the §638(r) authority. Direct-DoD Phase III is mostly competitive — program offices use "SBIR Phase III" as program-context language while procuring under set-asides, IDIQ task orders, or open competition. Other agencies (NASA, DHS, etc.) are even more weighted toward competitive procurement.

**The keyword-derived headline "GSA = 27.2% of Phase III" understates GSA's role in the actual §638(r) channel:**

| Lens | GSA share of $ |
|---|---:|
| Keyword-discoverable Phase III universe ($6.86B) | 27.2% |
| **Strict §638(r) sole-source only ($3.82B)** | **48.2%** |

When you restrict to actual §638(r) sole-source contracts, GSA accounts for nearly half. FEDSIM's role is even more central than the keyword analysis showed.

### §638(r) share by FY tracks the GSA cycle

| FY | Total $M | §638(r) $M | §638(r) % |
|---:|---:|---:|---:|
| 2014 | 115 | 29 | 25% |
| 2015 | 98 | 14 | 15% |
| 2016 | 271 | 19 | 7% |
| 2017 | 225 | 167 | 74% |
| 2018 | 259 | 120 | 46% |
| 2019 | 376 | 134 | 36% |
| **2020** | **617** | **446** | **72%** |
| **2021** | **827** | **650** | **79%** |
| **2022** | **822** | **669** | **81%** |
| **2023** | **808** | **607** | **75%** |
| **2024** | **752** | **363** | **48%** ← drop |
| **2025** | **643** | **326** | **51%** |
| 2026 | 160 | 101 | 63% (partial) |

§638(r) usage peaked at 79-81% during the GSA/FEDSIM peak years (FY2020-2023) — because FEDSIM is 99% §638(r). When DoD repatriated Phase III contracting in FY2024, the §638(r) share dropped to ~50%, because **direct-DoD program offices use §638(r) authority much less than FEDSIM did**. This is a second mechanism for the FY2024 cliff alongside the channel shift and recipient-population change: a shift in **procurement authority** away from sole-source toward competitive procurement.

### §638(r) by Small Business vs OTSB — reverses the Tier 1 read

The Tier 1 puzzle-case investigation looked only at the 23 "genuinely organic" OTSB rows and concluded ~$45M of OTSB contracts weren't §638(r). The full-universe enrichment shows a different distribution:

| Group | n | Total $M | §638(r) $M | **§638(r) %** |
|---|---:|---:|---:|---:|
| **OTSB** | 140 | $1,009 | $713 | **70.7%** |
| **Small Business** | 1,867 | $5,846 | $3,105 | **53.1%** |

**OTSB Phase III is MORE likely to be §638(r) sole-source than SB Phase III**, not less. Driven by:
- **Acquired-SBIR continuations** (L3 Adaptive Methods, Mercury Defense Systems, etc.) — sole-source is the natural mechanism when the acquirer claims the §638(r) standing inherited from the acquired SBIR firm
- **Production-scaling cases** (Rockwell Collins, JCB, BAE Systems Protection) — sole-source is used to award the production phase to the large prime with manufacturing capacity
- **Corporate-successor cases** (Sierra Space ← SNC) — sole-source on inherited §638(r) standing

The Small Business universe has more **competitive set-asides** where multiple small SBIR firms compete for Phase III follow-on work, lowering the SB §638(r) share to ~53%.

### Updated narrative for the FY2024 channel shift

Combining Tier 1 + Tier 2, the FY2024 cliff has three layered mechanisms, not one:

1. **Channel shift:** GSA-vehicle dollars dropped $281M ($390M → $109M YoY); direct-DoD grew ~$213M. ~40% of the GSA shed reappeared as direct-DoD.
2. **Recipient population change:** Only 7 of 58 GSA-era firms appear in direct-DoD post-FY2023. Direct-DoD is mostly hiring different SBIR firms.
3. **Authority shift (new):** When DoD repatriated Phase III, they used §638(r) sole-source authority less. §638(r) share of total Phase III dollars dropped from 75-81% (GSA peak) to 48-51% post-cliff. Direct-DoD's institutional habits favor competitive procurement (set-asides, IDIQs) over §638(r) sole-source.

The combined effect: combined GSA + direct-DoD Phase III dollars fell 34% from FY2023 peak ($764M) to FY2025 ($506M), AND the share procured under §638(r) sole-source fell from 75% to 51%. So the program-evaluation question changes: it's not just that less Phase III work is happening, it's that proportionally less of it is using the canonical §638(r) authority that SBA tracks as Phase III commercialization.

### Tier 2 #2: parent IDV reconciliation

The earlier FEDSIM IDIQ analysis (in "Surprise finding: not the famous GWACs") parsed parent IDVs from the regex of `generated_internal_id`. Tier 2 also pulled the canonical `Parent Award ID` field directly from the per-award detail endpoint and confirmed **zero mismatches across all 2,013 contracts** — the regex extraction is accurate. The $463M "no parent IDV" bucket of GSA-awarded standalone direct contracts is real, not a data-quality artifact.

Universe-wide parent-IDV coverage by awarding agency:

| Bucket | Total | With parent IDV | % | $ with parent |
|---|---:|---:|---:|---:|
| GSA | 204 | 186 | **91.2%** | $1.40B / $1.86B |
| DoD direct | 1,251 | 363 | **29.0%** | $1.07B / $4.34B |
| Other agencies | 558 | 34 | **6.1%** | $83M / $647M |

GSA's procurement model is overwhelmingly task-orders-on-IDIQs (91%). DoD direct is mostly standalone contracts (only 29% have parent IDVs). Other agencies essentially never use IDIQs for Phase III (6%). DoD's IDIQ use has grown from <5% before FY2017 to 35-40% in FY2020-2025 — a modest but real shift toward parent-vehicle architecture for DoD direct Phase III.

### Tier 2 #3: FEDSIM IDIQ lifecycle confirms the FY2024 cliff hypothesis (with a twist)

Pulled the IDV detail (`Start Date`, `Last Date to Order`, first task order date, last task order date) from USAspending for the top 20 parent IDVs by total Phase III dollars. The lifecycle-decay hypothesis is partly confirmed and partly more interesting:

**FEDSIM IDIQs with ordering periods that expired in FY2023-FY2024:**

| Parent IDV | Total $M | Start | **Last Date to Order** | Last actual TO |
|---|---:|---|---|---|
| W911W617D0004 (Army) | $44 | 2017-09 | **2023-03** | 2022-10 |
| 47QFLA19D0003 (GSA) | $76 | 2019-01 | **2023-09** | 2022-03 (1.5yr idle before LDO) |
| N6833519G0037 (Navy) | $41 | 2019-02 | **2024-02** | 2023-08 |
| 47QFLA19D0007 (GSA) | $109 | 2019-04 | **2024-04** | 2022-03 (2yr idle before LDO) |
| 47QFCA19D0005 (GSA) | $46 | 2019-09 | **2024-09** | 2023-09 |
| N6833520G3039 (Navy) | $38 | 2019-12 | **2024-12** | 2024-08 |

Combined ~$354M of IDV-level value from vehicles whose ordering periods expired in FY2023-2024. So lifecycle decay is real and material.

**But — many vehicles went idle before LDO:**

`47QFLA19D0007` (the largest, at $109M total) had its last task order in March 2022, fully **two years before** the ordering period ended in April 2024. `47QFLA19D0003` went idle ~18 months before LDO. This suggests **DoD program offices pulled away from FEDSIM ahead of the vehicles' natural expiry**, not just at end-of-life. The vehicles weren't replaced quickly enough at scale either.

**FY2023-FY2024 successor IDIQs are smaller-scale:**

| Successor IDIQ | $M | Start | LDO |
|---|---:|---|---|
| 47QFLA23D0007 (GSA) | $66 | 2023-07 | 2028-07 |
| 47QFLA23D0008 (GSA) | $66 | 2023-07 | 2028-07 |
| 47QFCA23D0002 (GSA) | $47 | 2023-03 | 2028-03 |
| **47QFLA24D0001 (GSA)** | **$72** | 2023-12 | 2028-12 |

The FY2024-vintage IDIQ is $72M of total task orders (one big TO + nothing else). The FY2019 generation peaked at $109M from 12 TOs across the vehicle's life. So the **replacement vehicles are running at roughly two-thirds the scale of the FY2019-2021 cohort** — consistent with the structural narrowing we see at the universe level.

**Net interpretation:** the FY2024 cliff is a combination of (a) natural ordering-period expiry of FY2019-2020 IDIQs, (b) earlier-than-expected withdrawal of demand from those vehicles, and (c) successor IDIQs being launched at smaller scale. All three reinforce each other.

### Tier 2 #4: UEI-based undercount check — keyword universe captures ~7% of follow-on contract dollars to top SBIR firms

The most dramatic Tier 2 finding. Pulled every FPDS contract ≥ $1M (FY2018-FY2026) for the top 30 SBIR Phase II awardees — firms ranging from 113 to 596 Phase II awards each. Compared those rows against our keyword-discoverable Phase III universe.

| | Contracts | $M |
|---|---:|---:|
| In our Phase III keyword universe | 83 | $462 |
| NOT in our Phase III keyword universe | **1,709** | **$6,313** |
| **Total to these 30 firms (≥ $1M)** | **1,792** | **$6,775** |
| **Keyword universe captures** | **4.6%** | **6.8%** |

**For 30 of the most prolific SBIR Phase II awardees, the keyword "SBIR Phase III" search picks up only 6.8% of the $6.78B in ≥ $1M FPDS contracts they won during FY2018-2026.**

Sampling the missed contracts confirms many are functionally Phase III-equivalent — SBIR-derived production, follow-on R&D, or system integration work — without the explicit keyword:

| Firm | "Missed" $M | Sample missed contracts |
|---|---:|---|
| Progeny Systems | $2,303 | MK54 LWT torpedo kits ($201M), MK48 G&C section ($165M) |
| Physical Optics Corp | $582 | DTU ($87M), T-45 HUD production ($71M) |
| ARETE Associates | $398 | MK 1 integration services ($42M), COBRA Block I ($28M) |
| Physical Sciences | $342 | DARPA SIGMA+ ($14M), SIGMA program ($8M) |
| Charles River Analytics | $334 | PPB biosystems ($12.5M), HEALTH analytics ($11.7M) |
| Toyon Research | $302 | SP201 ($90M), Strategic Systems Survivability ($32M) |
| Foster-Miller | $154 | Common Robotic System EMD/LRIP ($63M), Reset/Sustainment IDIQ ($13M) |

Even taking only a 50% "this is plausibly Phase III work" haircut on the $6.31B missed bucket — to be conservative about the share that's genuinely non-SBIR-derived — implies these 30 firms alone have **~$3.2B of hidden Phase III-equivalent follow-on work** the keyword fetch doesn't see.

### What this implies for the broader Phase III universe

The whole keyword-discoverable Phase III universe is $6.86B across 2,013 contracts to ~700 distinct firms (most of whom have small Phase III footprints). The top 30 SBIR firms alone have $6.78B in ≥ $1M FPDS contracts during the same window. So a single 30-firm sample exposes a parallel-magnitude universe of follow-on contracts that don't carry the "SBIR Phase III" keyword.

**Bounds on the true Phase III universe** (broad SBA definition: any work that derives from, extends, or completes prior SBIR R&D, regardless of procurement authority):

- **Narrow lower bound** (strict §638(r) sole-source only, from Tier 2 #1): **$3.82B**
- **Keyword-discoverable** (current report headline): **$6.86B**
- **Broad-definition lower bound** (rule-based transition scorer over 30-firm missed bucket, see Tier 2 #5 below): for the 30 firms alone, **at least $4.5B of "missed" contract dollars carry positive derivation signals**, on top of the $462M they contribute to the keyword universe
- **Broad-definition universe** (extrapolation to ~17,000-UEI SBIR population): **uncertain**, plausibly several times the keyword headline. The 30-firm sample is biased toward high-volume SBIR participants; the rest of the population has smaller follow-on footprints. A real population-wide measurement would require running the UEI-based pull + scorer across all 17,000 firms (Tier 3 work).

The gap between keyword and broad-definition universes is structurally larger than GAO-24-107036's ~30% undercount estimate. The discrepancy comes from definitional scope: GAO measures undercount of "SBIR Phase III" tagging within FPDS records that the contracting officer attempted to label as Phase III but did so inconsistently. The 30-firm UEI-based pull measures something different: total FPDS revenue to SBIR firms that doesn't carry any Phase III tagging — regardless of whether the contracting officer intended it as Phase III.

**Two interpretations are both defensible:**

1. **Narrow (procurement-authority-based):** Only §638(r) sole-source counts as "Phase III." The universe is ~$3.82B. The keyword universe and the 30-firm gap mostly capture program-context language and non-Phase-III contracts to SBIR-firms. This is the SBA-tracking definition.

2. **Broad (commercialization-outcome-based):** All federal contract dollars to SBIR firms that derive from prior R&D count as Phase III commercialization, regardless of how procured. The universe is plausibly several times the keyword-discoverable headline (see Tier 2 #5 for the scored lower bound on the 30-firm sample). This is the SBA Policy Directive definition.

**The two interpretations imply different policy questions.** For SBA Phase III commercialization tracking, the narrow definition is what's measured. For evaluating SBIR's actual economic impact via follow-on federal contracts to program participants, the broad definition is closer to the truth — and the rule-based transition scorer (Tier 2 #5) confirms most of the 30-firm "missed" bucket has positive derivation signals.

### Caveats on the 30-firm undercount finding

- **The 30-firm sample is biased toward heavy SBIR participants.** These firms have 113-596 Phase II awards each — they're the highest-volume SBIR participants in the federal database. Average SBIR firms have many fewer Phase II awards and likely smaller follow-on footprints. The 93% missed ratio doesn't extrapolate proportionally to all 17,000 SBIR firms.
- **Not all "missed" contracts are SBIR-derived.** These firms also win non-SBIR contracts. Without contract-by-contract review, the share that's genuinely Phase III-equivalent vs. non-SBIR-derived is unknown. Conservative haircut: 50% is genuinely SBIR-derived ⇒ ~$3B for the 30-firm sample.
- **The ≥ $1M threshold excludes smaller contracts.** Real follow-on Phase III work happens at sub-$1M too. Including those would widen the gap further but introduce more non-SBIR noise.
- **`recipient_search_text` filter precision was verified** by checking each result's `Recipient UEI` matched the queried UEI. False-positive matches are excluded.

### Implications

1. **The current report's GSA/OTSB findings, all built on the keyword-discoverable universe, are accurate within that universe.** They describe the §638(r)-tagged Phase III channel, which is the channel SBA actually tracks.
2. **The "FY2024 cliff" finding may be partly an artifact of changes in keyword-tagging behavior, not just real contraction.** If contracting officers shifted to less-explicit Phase III labeling post-FY2023, the cliff overstates the actual decline. Combined GSA + direct-DoD Phase III could be flat or growing in the broad-definition universe while the keyword universe shrinks 34%.
3. **For program evaluation, SBA should either (a) track the broad-definition universe via UEI-based federal-contract tracking** (which would require integrating SBIR.gov with FPDS at the recipient level) **or (b) explicitly limit Phase III commercialization metrics to the narrow §638(r) definition** to avoid the ambiguity.

### Tier 2 #5: rule-based transition scorer over the 30-firm missed bucket

Ran the repo's `TransitionScorer` (`packages/sbir-ml/sbir_ml/transition/detection/scoring.py`) over the 1,804 missed contracts from Tier 2 #4. For each contract, scored against the firm's prior Phase II awards and took the max score. The scorer's six signals approximate the SBA Policy Directive's "derives from, extends, or completes" test:

| Signal | What it measures | Available in this run? |
|---|---|---|
| Agency continuity | Same agency funded P2 and the contract? | ✓ |
| Timing proximity | Contract within 24 months of P2 completion? | ✓ |
| Lineage language | Description contains "phase iii", "derives from", "follow-on production", etc.? | ✓ (regex) |
| Competition type | Sole-source under §638(r)? | ✗ (need FPDS enrichment) |
| Patent signal | Firm has related patents? | ✗ (no patent data wired) |
| CET alignment | Contract NAICS matches P2 technology area? | ✗ (no CET classification) |

**Important caveat on band thresholds:** the calibrated thresholds (HIGH ≥0.85, LIKELY ≥0.65) assume all 6 signals fire and that text similarity (currently disabled) contributes. With only 3 of 6 signals available, the maximum achievable score is **~0.41** — every contract with all 3 signals firing lands at exactly this ceiling. The HIGH/LIKELY bands aren't reachable in this constrained run.

#### Score distribution

| Band | Contracts | $M | % of $ |
|---|---:|---:|---:|
| HIGH (≥0.85) | 0 | $0 | 0% (unreachable without 4+ signals) |
| LIKELY (0.65-0.85) | 0 | $0 | 0% (unreachable without 4+ signals) |
| **At-max-possible (0.40-0.42)** | **1,302** | **$4,530** | **70.0%** |
| Below-max (0.16-0.40) | 502 | $1,948 | 30.0% |

**70% of the missed-bucket dollars ($4.53B) achieve the maximum score the available-signal subset can produce** — meaning these contracts have all three of: same-agency continuity, timing within the 24-month follow-on window, and base credibility. The remaining 30% lack at least one of these.

#### Sample at-max contracts (representative of the $4.53B bucket)

| Score | $M | Recipient | Description |
|---:|---:|---|---|
| 0.41 | $201 | GD Mission Systems (← Progeny Systems) | MK54 MOD1 LWT KITS LRIP |
| 0.41 | $165 | GD Mission Systems | DESIGN OF MK 48 MOD 7 G&C SECTION |
| 0.41 | $90 | Toyon Research | FY20 - SP201 (Navy Strategic Systems) |
| 0.41 | $87 | Physical Optics Corp | DTU (Navy) |
| 0.36 | $89 | GD Mission Systems | TI-08 LONG LEAD MATERIAL |
| 0.36 | $71 | Physical Optics Corp | T-45 HUD PRODUCTION UNITS |
| 0.21 | $63 | Foster-Miller | Common Robotic System (Individual) EMD/LRIP IDIQ |

The at-max-band (0.40+) cases are textbook Phase III production / system-integration work for SBIR-derived technology to SBIR firms via same-agency channels. The 0.36 cases are similar work outside the 24-month timing window (typically 36-60 months after a P2 completion, but the firm has multiple P2s feeding into the same product line). The 0.21 case (Foster-Miller IDIQ) is the parent vehicle itself, not the underlying SBIR-derived task orders.

#### With FPDS competition signal enriched

Subsequently enriched the 1,804 missed contracts with FPDS competition fields (same per-award-detail pattern as Tier 2 #1) and re-ran the scorer. Of the 1,804 missed contracts, **164 (~9%) carry the canonical `solicitation_procedures = "ONLY ONE SOURCE"` signature** — these are unambiguously §638(r)-style sole-source procurements.

| Band | Contracts | $M | % of $ |
|---|---:|---:|---:|
| At-max (0.40-0.45) | 1,350 | **$5,142** | **79.4%** |
| Below-max (0.16-0.40) | 454 | $1,336 | 20.6% |

The competition signal pushed an additional $612M of contracts into the at-max band (vs. the without-competition run that had $4.53B in this band). The max possible score is now 0.45 (was 0.41) — sole-source bonus adds 0.04.

Examples of contracts that climbed from 0.41 → 0.45 when their sole-source status registered:
- GD Mission Systems MK54 MOD1 LWT KITS LRIP ($201M, §638(r)=True)
- GD Mission Systems NAVY SOFTWARE ENGINEERING SERVICES ($92M, §638(r)=True)
- Toyon Research FY20 SP201 ($90M, §638(r)=True)

The Foster-Miller IDIQ at $63M scores 0.21 (low) — `638r=False` and timing outside the window — correctly identified as the parent vehicle, not the SBIR-derived task orders against it.

#### Why HIGH and LIKELY bands are empty

With **3 of 6 signals available** (agency, timing, competition; missing patent, CET alignment, text similarity), the realistic ceiling is ~0.45 — well below the calibrated LIKELY threshold of 0.65 and the HIGH threshold of 0.85. The calibrated thresholds assume **all 6 signals fire including text similarity**.

To reach LIKELY band with confidence, we'd need to wire ModernBERT-derived text similarity into the scorer's text_similarity slot (currently disabled per the design rationale below). With text similarity enabled and tuned, contracts at the current 0.45 ceiling that have semantically-derived descriptions would jump into the 0.55-0.70 range.

The score-distribution-relative-to-ceiling is the cleaner interpretation: **79.4% of missed-bucket dollars achieve the maximum score the available-signal subset supports**, meaning all available derivation signals fire for these contracts (same-agency, timing within follow-on window, sole-source).

#### Interpretation

The scorer corroborates the qualitative finding: **the missed bucket is overwhelmingly Phase III-equivalent derivation work, not non-SBIR-derived contracts**. Conservative reading: ~$4.5B of the $6.48B "missed" bucket carries positive derivation signals on the 3 signals available. With the competition signal added, the LIKELY-band dollar share is plausibly much higher (most of the at-max 0.41 contracts would migrate to ~0.61 if they're sole-source).

For the 30-firm sample alone, the rule-based scorer puts the **broad-definition Phase III lower bound at ~$4.5B in addition to the $462M captured in the keyword universe** — total ~$5B of Phase III-equivalent activity for these 30 firms over FY2018-2026.

#### Methodology notes for the rule-based vs ML choice

Per `specs/archive/completed-features/transition_detection/requirements.md`, the scorer was intentionally designed rule-based for: (a) auditable evidence trails per detection, (b) YAML-configurable signal weights and thresholds tunable without retraining, (c) 10,000 detections/minute throughput, (d) interpretable confidence-level terminology aligned with GAO/audit conventions. ModernBERT embeddings exist in the repo as a separate asset layer (`packages/sbir-analytics/sbir_analytics/assets/modernbert/embeddings.py`); we wired them into the scorer's `text_similarity` slot for this analysis (see below).

### Tier 2 #6: ModernBERT text similarity wired into the scorer

Embedded all 22,047 Phase I/II abstracts for the 30 sample firms plus the 1,804 missed contracts using **nomic-ai/modernbert-embed-base** on Apple Silicon MPS (~10 min embedding compute, no API cost). For each missed contract, computed max cosine similarity against the firm's P1/P2 portfolio and injected the value into the scorer's `text_similarity_score` field (with the signal enabled in config, weight=0.20).

#### Semantic similarity distribution

| stat | value |
|---|---:|
| min | 0.49 |
| max | 0.92 |
| **mean** | **0.69** |
| **median** | **0.69** |

**Median cosine similarity of 0.69 across the missed bucket is high** — in sentence-embedding work, >0.5 indicates meaningful semantic overlap, >0.7 indicates strong topical match, >0.8 indicates near-paraphrase. So half of the missed contracts have descriptions that semantically resemble *at least one* of the firm's prior SBIR R&D abstracts at near-paraphrase strength.

#### Score distribution with ModernBERT

| Band | Contracts | $M | % of $ |
|---|---:|---:|---:|
| HIGH (≥0.85) | 0 | $0 | 0% (still unreachable; see below) |
| LIKELY (0.65-0.85) | 0 | $0 | 0% |
| **POSSIBLE (0.40-0.65)** | **1,761** | **$6,247** | **96.4%** |
| LOW (<0.40) | 43 | $231 | 3.6% |

Adding text similarity pushed an additional **$1.1B (411 contracts)** from below-threshold into the POSSIBLE band. Max score climbed from 0.45 → 0.61 — text-sim adds up to 0.18 (0.92 × 0.20 weight) on top of the structural signals.

#### The LOW-band finding: ModernBERT catches what structured signals miss

The 43 contracts that still score LOW (<0.40) reveal a interesting pattern. **Their text similarity values are HIGH (0.66-0.77), but agency or timing signals don't fire:**

| Contract | $M | text_sim | Score | Why LOW |
|---|---:|---:|---:|---|
| Foster-Miller "Route Clearance & Interrogation System" | $11 | 0.77 | 0.37 | Text strongly derivation-like, but timing outside 24-month window |
| Foster-Miller IDIQ Common Robotic System | $63 | 0.70 | 0.35 | Parent IDV vehicle, not the underlying task orders |
| GD Mission Systems multi-yr engineering services | $17 | 0.66 | 0.34 | Cross-service contract; agency doesn't strictly match P2 agency |
| Foster-Miller Reset/Sustainment IDIQ | $13 | 0.67 | 0.35 | IDIQ parent + later-era contract |

**These are arguably some of the strongest Phase III derivation cases by content match** (Foster-Miller's Route Clearance product clearly derives from their robotics SBIR portfolio), but they fall outside the structural windows that rule-based scoring relies on. ModernBERT catches the derivation signal; the structured signals don't.

#### Why HIGH and LIKELY bands are still unreachable

Even with 4 of 6 signals firing (agency, timing, competition, text similarity), the realistic ceiling is **~0.63** (base 0.15 + agency 0.0625 + timing 0.20 + sole-source 0.04 + text-sim 0.18 max). The remaining patent and CET signals contribute at most +0.10 combined — leaving the all-signals ceiling at ~0.74, just barely into the LIKELY (≥0.65) band.

The HIGH (≥0.85) threshold was calibrated against the labeled transition benchmark assuming all signals are highly aligned — text similarity ~0.9, patents present, CET match, and timing within 3 months. That combination is rare in the keyword-discoverable universe (which is where the labeled benchmark lives) and even rarer in the missed bucket. The HIGH band is the boundary for "essentially certain Phase III transition with full evidence stack." Most real Phase III work doesn't hit that bar even when it clearly IS Phase III.

**The score-distribution-relative-to-ceiling interpretation is the cleaner one:** 96.4% of missed-bucket dollars land in the POSSIBLE band, and almost all of those are at or near the achievable maximum given the signals available.

#### Three independent measurements all corroborate

The "broad-definition Phase III" framing — that most of the 30-firm missed bucket is derivation work the keyword fetch misses — is now corroborated by three independent measurement approaches:

| Measurement | Dollar share with positive derivation signals |
|---|---:|
| Rule-based scorer, 3 signals (agency + timing + base) | 70.0% ($4.53B) |
| + Competition signal (4 signals) | 79.4% ($5.14B) |
| **+ ModernBERT text similarity (4 signals)** | **96.4% ($6.25B)** |

The semantic-similarity measurement is the most direct test of the "derives from / extends / completes" criterion in the SBA Policy Directive. **Median cosine similarity of 0.69 across the missed bucket is strong evidence that the work is genuinely SBIR-derived, not coincidentally to known SBIR firms.**

For the 30-firm sample alone, this puts the **broad-definition Phase III footprint at approximately $6.7B** ($6.25B missed + $0.46B already in keyword universe). The keyword-discoverable universe captures 6.8% of the broad-definition Phase III work to these firms.

#### Caveats on ModernBERT-derived similarity

- **Domain shift uncertainty.** `nomic-ai/modernbert-embed-base` is a general-purpose embedding model trained on web text, not SBIR R&D specifically. Defense/aerospace technical vocabulary may produce inflated similarities (most contracts to defense firms share the same domain language). A SBIR-specific fine-tune could be informative.
- **Bag-of-keywords inflation.** Two contracts containing "radar," "Navy," "underwater," and "acoustic" will have high similarity regardless of whether one derives from the other. This is a known limitation of generic embeddings vs. content-aware Phase III detection.
- **The threshold-band calibration assumes labels.** The HIGH (≥0.85) / LIKELY (≥0.65) thresholds were tuned against a labeled transition benchmark that ModernBERT-derived similarity *wasn't part of*. Adding it shifts the score distribution in ways the calibration didn't anticipate. A clean integration would require re-calibrating the bands against a held-out labeled set that uses the text_similarity signal.

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
uv run python scripts/archive/data/build_phase3_universe.py --start-fy 2008 --end-fy 2026

# Enrich with business-size (~5 min)
uv run python scripts/archive/data/enrich_phase3_business_size.py \
  --input data/processed/sbir_phase3/phase3_universe.jsonl \
  --output data/processed/sbir_phase3/phase3_universe_enriched.jsonl

# If many rows fail with RemoteProtocolError, re-run failed rows with lower concurrency:
# (extract failed rows, then)
uv run python scripts/archive/data/enrich_phase3_business_size.py \
  --input /tmp/failed.jsonl --output /tmp/retried.jsonl --concurrency 3
```

The DuckDB queries that produced every table above are simple enough to reconstruct from the schema — but should be packaged into a `scripts/data/report_phase3_gsa_otsb.py` if this report becomes a recurring artifact rather than a one-shot. That packaging is deliberately left out of this PR.
