# Research Questions Inventory

The SBIR ETL pipeline is designed to answer a broad set of questions about the
SBIR/STTR program. Questions are organized by **policy area** (what audience /
statutory goal the answer serves), then within each area by **complexity tier**
(descriptive → relational → inferential → predictive), with **dependency order**
respected so foundational work appears before dependents.

**Policy areas:**

- [A. National security, industrial base, and supply chain](#a-national-security-industrial-base-and-supply-chain)
- [B. Technology commercialization & entrepreneurship](#b-technology-commercialization--entrepreneurship)
- [C. Innovation & knowledge generation (R&D policy)](#c-innovation--knowledge-generation-rd-policy)
- [D. Economic & fiscal impact](#d-economic--fiscal-impact)
- [E. Program management & data infrastructure](#e-program-management--data-infrastructure)
- [F. Capital formation & entrepreneurial finance](#f-capital-formation--entrepreneurial-finance)

**Where to start, by audience:**

- **Policymakers** (Congress, OMB, agency leadership, congressional defense committees): start with the **DoD leverage ratio** question (Section A → Supporting DIB questions, inferential tier; reproduces NASEM's ~4:1 benchmark), **D2** (Treasury ROI / tax receipts from SBIR spending), and **F3** (private-to-SBIR leverage as the mirror to the DoD leverage ratio on the private side).
- **SBIR program managers** (NSF, NIH, DoD, DOE, SBA program offices): start with **B** (transitions, Phase II→III latency, company performance), **C1** (cross-agency CET portfolio composition), and **E6** (rolling quarterly snapshots / continuous monitoring).
- **Investors** (VC, PE, angels, family offices, corporate VC): start with **F1** (Form D fundraising profile, M&A exit rate by funding agency, capital-event timeline) and **F2** (cohort outcomes vs. published VC/PE baselines, acquirer-type concentration).

Each pointer above lands inside a section that mixes implemented and spec-only
work — see status banners in the linked specs, and the inline *(PR #)* /
*(branch: …)* tags on individual questions, to tell what's answerable today
from what's a research target.

**Dependency tags** used in parentheses after each question:

- `ER` — entity resolution (UEI/CAGE/DUNS/fuzzy-name cascade)
- `ID` — SBIR/STTR identification classifier
- `CET` — CET technology classifier
- `PATLINK` — patent-to-award linkage
- `IMP` — imputed fields for missing data
- `M&A signals` — M&A event detection (8-K/Form D parsing, ownership-change signals)
- `SEC EDGAR` — SEC EDGAR filings (Form D Reg D, Form 8-K) for SBIR-firm transactions
- `UCC-1` — UCC-1 financing-statement filings (state-level secured-debt registry; captures equipment finance, depository-bank loans, and venture debt as distinct sub-channels)
- `NAICS` — industry classification derived from NAICS codes
- `fiscal model` — fiscal-impact modeling inputs and assumptions
- `BEA I-O` — BEA input-output tables for economic-impact estimation
- `transitions` — commercialization/phase-transition outcome definitions
- `NIPA rate provider` — BEA NIPA-derived effective tax rates (Tables 3.2/3.3)
- `state rate provider` — state-specific effective tax rates for jurisdiction decomposition

Items marked *(branch: …)* are in-progress on a feature branch and not yet
merged to `main`. Public-study citations appear as `[L#]` — see
[Prior literature & benchmarks](#prior-literature--benchmarks) at the bottom.

## A. National security, industrial base, and supply chain

*Audience: DoD acquisition leadership, congressional defense committees, CSIS-style industrial-base analysts. The defense-industrial-base and critical-supply-chain questions are **merged into a single framing** below — they serve the same audience and statutory goal and draw on the same `CET`, `NAICS`, `ER`, and `M&A signals` data. Supporting DIB questions that fall outside that framing (leverage ratio, SBIR identification, patent-flow-to-primes) follow it, grouped by complexity tier.*

### The merged question: industrial capability vs. vulnerability

**Master question:** Across the CET areas, where does SBIR/STTR build domestic industrial capability that strengthens the DIB, and where are awardees exposed to adversary ownership/control or capability concentration that creates vulnerability?

The question splits into two axes — **Capability** (Axis A) and **Vulnerability** (Axis B) — each sub-question carrying an answerability label. The merge is only honest because award data answers the DIB/institutional (capability) side **well** and the supply-chain/chokepoint (vulnerability) side **only weakly**: strong capability metrics must not lend false confidence to weak vulnerability inferences, so every sub-question keeps its own label and weak ones are not allowed to free-ride.

**CET spine.** The organizing spine is the repo's **21-area `NSTC-2025Q1`** taxonomy defined in `config/cet/taxonomy.yaml`; `packages/sbir-ml/sbir_ml/ml/config/taxonomy_loader.py` expects exactly 21 areas and logs a warning on any mismatch (a soft check, not a hard-failing validation). This is *not* the external 18-area Feb-2024 NSTC Critical and Emerging Technologies list, nor DoD's 14 Critical Technology Areas — both are narrower external frameworks, and the repo's 21-area set already blends NSTC CET areas with several DoD critical-technology areas (Hypersonics, Directed Energy, Advanced Gas Turbine Engine Technologies, Integrated Network Systems-of-Systems). **Crosswalk note:** for DoD-facing outputs each CET area should also carry a **DoD-14** and an **NDIS-8** (National Defense Industrial Strategy supply-chain-priority) tag where a mapping exists, so results speak to both NSTC and DoD audiences. (Two other, divergent CET taxonomies exist in code — a 10-area transition-system set and a 19-area reporting-analyzer set — and are not yet reconciled to the canonical 21; see Maintenance.)

**Statutory grounding.** Axis B maps to the risk-based due-diligence factors of the SBIR/STTR reauthorization, **Pub. L. 119-83** (signed April 13, 2026), and its eight restricted-entity screening lists — the UFLPA Entity List, the Non-SDN Chinese Military-Industrial Complex Companies (NS-CMIC) List, the Section 889 Prohibition List, the 1260H list, the Military End-User (MEU) List, the BIS Entity List, the FCC Covered List, and the CBP WRO/Findings List [L26]. Axis A maps to the same law's Strategic Breakthrough Allocation and Phase III provisions. (Statute linked, not reproduced.)

#### Axis A — Capability (does SBIR/STTR build domestic industrial capability?)

- **A1. Domestic capability density per CET area** — distinct awardee counts and award volume per area, with an HHI on awardees to flag thin or concentrated clusters (the same density lens also reads across NAICS sector and geography — state / congressional district). CSIS Center for the Industrial Base [L16]. **[Answerable now]** *(deps: CET, ER, NAICS)*
- **A2. DIB integration** — Phase II→III transition rate per CET area via FPDS, plus SAM.gov subaward links to prime contractors. Aligns with NASEM's "knowledge transfer to primes" finding [L1]. **[Answerable now, moderate confidence — FPDS Phase III tagging is historically incomplete; GAO [L14]]** *(deps: ER, ID, CET, transitions)*
- **A3. Capital formation / firm health per CET area** — Form D raises and follow-on funding as a proxy for awardee financial health by technology area. **[Partial — SEC/Form D filers only]** *(deps: ER, CET, SEC EDGAR)*
- **A4. Whitespace** — CET subfields with DoD demand signals but sparse SBIR coverage, surfaced via semantic search over award and solicitation text. **[Answerable now]** *(deps: CET)*

#### Axis B — Vulnerability (are awardees exposed to adversary control or capability concentration?)

- **B1. Foreign ownership/control exposure** — EDGAR Exhibit 21 (subsidiary/parent structure) and 8-K M&A flags on awardees and their parents, screened against the eight Pub. L. 119-83 restricted-entity lists [L26]. Captures adversarial-capital exposure by technology area (which areas sit under foreign acquirers or foreign-owned primes). Foreign-acquisition risk flagged by CSIS [L17]. **[Now for the SEC-filer subset; needs data acquisition for the private majority]** *(deps: ER, SEC EDGAR, M&A signals)*
- **B2. Adversary-affiliation screening** — entity resolution of awardees and key personnel against the named restricted-entity lists and foreign-country-of-concern ties. **[Partial via public lists; full coverage needs agency-held due-diligence data]** *(deps: ER)*
- **B3. Concentration-as-fragility** — single-firm or thin-base dominance within a CET cluster, read as risk rather than capability (the same HHI as A1, inverted, including geographically narrow supplier bases). Has the base for a given area thinned or thickened over time, and which sole-supplier firms would, if acquired or lost, remove a capability with no in-program substitute? **[Answerable now]** *(deps: ER, CET)*
- **B4. Physical input chokepoints** — dependence on contested physical inputs (rare earths, castings, advanced chips, APIs). **NOT answerable with award-type data.** Identifying sole-source physical inputs, foreign-content percentages, surge capacity, or sub-tier chokepoints requires bill-of-materials, customs, or contractual country-of-origin data the pipeline does not ingest. **[Out of scope — stated explicitly, not as a research target]** *(deps: —)*

#### Proposed (unvetted)

*Candidate questions raised in review but not yet scoped against the data or methodology. Listed here rather than inline so they don't read as graded, answerable metrics until vetted.*

- **Awardee-as-chokepoint (knowledge/IP supply-chain position)** — identify SBIR awardees that are the sole or dominant holder of an enabling capability or IP in a CET area that downstream primes and follow-on programs depend on. Much of the machinery already exists: patents are linked to awardee `Company`/`Award` nodes in the graph and classified into the 21 CET areas, patent **assignment chains** (`ASSIGNED_VIA/FROM/TO`) already track IP flow to primes (the C2 question), and ModernBERT-Embed embeddings give semantic overlap across awards/patents/contracts — so the IP-concentration and ownership-transfer chokepoint lenses are largely buildable on current pieces. The missing input is patent **citation edges**: a `PatentCitation` model exists but citations are not yet ingested as graph relationships, which is what a true citation-centrality "who-depends-on-whom" measure would require. Distinct from **B4** (physical inputs, out of scope) and sharper than **B3** (adds supply-chain position). **[Proposed — mostly assembles existing patent/graph/embedding capability; needs a chokepoint definition, and patent-citation ingestion for the citation-centrality variant]** *(deps: ER, CET, PATLINK)*

### Supporting DIB questions (outside the capability/vulnerability frame)

*These defense-industrial-base questions predate the merged framing and remain organized by complexity tier. For SBIR-firm capital structure and exit analysis from an entrepreneurial-finance perspective, see [F. Capital formation & entrepreneurial finance](#f-capital-formation--entrepreneurial-finance).*

**Descriptive.** Portfolio composition by DoD component (Army/Navy/AF/DARPA/DLA), phase, and vintage — SBA annual reports [L18]. *(deps: —)*

**Relational.**

- Which federal awards are SBIR/STTR vs. non-SBIR, and with what confidence? — [sbir-identification-methodology.md](sbir-identification-methodology.md). CRS R43695 [L15]. *(deps: ID)*
- Do firms show higher transition rates within the same awarding agency (agency continuity signal)? *(deps: ER, ID)*
- Can assignment chains show SBIR patent flow through prime contractors? Aligns with NASEM's "knowledge transfer to primes" finding [L1]. *(deps: ER, PATLINK)*

**Inferential — DoD leverage ratio.**

- What is the aggregate leverage ratio (non-SBIR DoD obligations ÷ SBIR/STTR obligations) for DoD SBIR firms? **Target: reproduce NASEM's ~4:1 for 2012–2020** [L1][L2] — [../specs/leverage-ratio-analysis/](../specs/leverage-ratio-analysis/). *(deps: ER, ID)*
- How does the leverage ratio stratify by award vintage, firm size, technology area, and firm experience (new vs. repeat)? NASEM reports SBIR firms = ~1/3 of DoD's extramural R&D base [L1]. *(deps: ER, ID, CET)*
- How is the leverage ratio changing over time? *(deps: ER, ID)*
- What is the leverage ratio for civilian agencies (e.g., DOE)? Myers & Lanahan [L9] and NASEM DOE [L5] supply baselines. *(deps: ER, ID)*

**Risk & monitoring — M&A detection & transition pathways.** *(These feed Axis B; the operational M&A-detection questions are kept here because they carry concrete implementation status.)*

- Did a defense-funded SBIR company undergo M&A activity, especially involving a foreign acquirer? — [../specs/merger_acquisition_detection/](../specs/merger_acquisition_detection/). Feeds **B1**. *(deps: ER, M&A signals)*
- For SBIR firms acquired by public companies, can inbound M&A be detected via 8-K full-text search? *(PR #286)* *(deps: ER, SEC EDGAR)*
- Which defense primes concentrate SBIR-firm acquisitions (e.g., Titan, Teledyne, Ametek, Kratos), and are any of those acquirers themselves foreign-owned or under CFIUS review? Feeds **B1**. *(deps: ER, M&A signals)*
- How does M&A activity affect Phase III / federal-contract transition pathways? *(deps: ER, M&A signals, transitions)*

*Implementation note: M&A event detection runs as a CLI script
(`scripts/data/detect_sbir_ma_events.py`), not as a Dagster asset. The script
merges two signals: Form D filings (entity_type-based business-combination
heuristics) and SEC EDGAR full-text mention scan across multiple filing types
(operationally: 8-K, 10-K, DEFM14A, PREM14A, SC TO-T, SC 14D9 — see
`scripts/data/refine_ma_medium_tier.py`). The orchestrated graph has no
continuous M&A-event materialization; rerunning the script is how the M&A
signal that feeds the Axis B (vulnerability) and F-area questions gets
refreshed. The previously-existing
`packages/sbir-analytics/sbir_analytics/assets/ma_detection.py` stub was a
placeholder, never wired into the M&A pipeline, and was removed in PR #317.*

## B. Technology commercialization & entrepreneurship

*Audience: SBA oversight, agency program offices, awardee firms. Core statutory goal is Phase III commercialization.*

### B1. Descriptive (Tier 1)

- Is this SBIR company primarily a product, service, or mixed-mode firm (based on full federal contract portfolio)? — [../specs/company-categorization/](../specs/company-categorization/). *(deps: ER)*
- What percentage of a company's revenue comes from product vs. service contracts? *(deps: ER)*
- Which SBIR companies show the highest transition success rate, and which are consistent repeat performers? — [queries/transition-queries.md](queries/transition-queries.md). Lerner [L10] found growth concentrated in high-VC zip codes. *(deps: ER)*

### B2. Relational (Tier 2)

- Did this SBIR-funded research result in a federal contract? — [transition/overview.md](transition/overview.md). Baselines: NASEM DoD [L1][L2]; Link & Scott ~50% commercialization probability [L12]; NASEM program reviews [L3][L4][L6]. *(deps: ER, ID)*
- Which SBIR-funded companies transitioned research into federal procurements? — [transition/detection-algorithm.md](transition/detection-algorithm.md). *(deps: ER, ID)*
- What is the average time from award to transition by technology area? *(deps: ER, ID, CET)*
- Which SBIR awards transitioned with patent backing, and what share of transitions are patent-enabled? Related to Lerner [L10] and Howell [L11]. *(deps: ER, ID, PATLINK)*

### B3. Inferential (Tier 3)

- What is the elapsed time between Phase II completion and first Phase III contract? — [phase-transition-latency.md](phase-transition-latency.md). GAO flagged Phase III data as limited/unreliable [L14]; SBA ran the Commercialization Benchmark once (2014) for the same reason [L15]. *(deps: ER, ID)*
- Phase II → III survival probability by agency, firm size, and vintage. *(deps: ER, ID)*
- Does Phase II → III latency vary by technology area? *(deps: ER, ID, CET)*
- Transition effectiveness rate by CET area, agency, and firm size — compare to Link & Scott [L12] and NASEM [L1][L3][L4]. *(deps: ER, ID, CET)*
- How much undercount exists in Phase III coding by agency? Corroborated by GAO [L14] and NASEM [L1][L3]. *(deps: ID)*
- How does company categorization relate to transition likelihood? Baseline: Link & Scott commercialization-probability econometrics [L12]. *(deps: ER, ID)*
- Which Phase II awardees subject to §638(qq)(3) Increased Performance Standards meet the **statutory Commercialization Benchmark** (sales + private investment over the 10-FY covered period ÷ SBIR funding ≥ specified ratio)? Pub. L. 117-183 SBIR/STTR Extension Act of 2022 §638(qq)(3). Implementation on main: `scripts/run_benchmark.py` (evaluate / sensitivity / company-level CLI) backed by `sbir_etl/models/benchmark_models.py`, with tests in `tests/unit/test_benchmark_evaluator.py`. Additional per-firm audit infrastructure and a more comprehensive methodology doc exist as local-only / uncommitted work — see "Output products" section below for the in-progress status. *(deps: ER, ID, transitions, SEC EDGAR)*

### B4. Predictive (Tier 4)

- Forward-looking transition probabilities for Phase II awards nearing completion. Per-firm **Phase III prospect digest** builder exists at commit [`4470b921`](https://github.com/hollomancer/sbir-analytics/commit/4470b921) (not on `main`; was developed on a since-removed feature branch — re-introduce as needed). Surfaces top candidates for outreach using B1-B3 features as scoring inputs. *(deps: all of B1–B3)*

## C. Innovation & knowledge generation (R&D policy)

*Audience: OSTP, agency R&D directors, innovation researchers. Does federal SBIR spending produce measurable new knowledge?*

### C1. Descriptive (Tier 1)

- Federal SBIR portfolio composition across all 11 agencies by technology area — [../specs/cross-agency-taxonomy/](../specs/cross-agency-taxonomy/). CSIS [L16]. *(deps: CET)*
- Which CET areas are funded by multiple agencies? Cross-agency overlap. *(deps: CET)*
- How does the SBIR technology mix shift over time by agency? SBA [L18]. *(deps: CET)*
- Which SBIR awards align with each CET area, and with what calibrated probability? — [ml/cet-classifier.md](ml/cet-classifier.md). *(deps: —)*

### C2. Relational (Tier 2)

- Which USPTO patents are linked to specific SBIR awards, and with what confidence? — [transition/vendor-matching.md](transition/vendor-matching.md). Parallels Jaffe-Trajtenberg-Henderson [L13]. *(deps: ER, PATLINK)*
- Which patents are semantically similar to specific SBIR awards (ModernBERT-Embed)? — [../specs/modernbert_analysis_layer/](../specs/modernbert_analysis_layer/). *(deps: PATLINK)*
- Do SBIR awards and resulting contracts share the same technology focus (CET alignment signal)? *(deps: ER, ID, CET)*
- How many patents are linked to each award, and what is the matching confidence distribution? *(deps: PATLINK)*

### C3. Inferential (Tier 3)

- What is the marginal cost per patent by agency (award $ ÷ linked patents)? Compare against NIH/NSF figures in NASEM reviews [L3][L4][L6] — [../specs/patent-cost-spillover/](../specs/patent-cost-spillover/). *(deps: ER, PATLINK)*
- What is the spillover multiplier (non-SBIR patent citations to SBIR patents)? **Target: reproduce Myers & Lanahan ~3× for DOE, ~60% U.S.-retained** [L9][L5]. *(deps: PATLINK)*
- How do patent cost and spillover vary by technology area, firm size, and award vintage? *(deps: ER, PATLINK, CET)*

## D. Economic & fiscal impact

*Audience: Treasury, OMB, JCT, state economic-development offices. What is the dollar return on the SBIR program?*

### D1. Descriptive (Tier 1)

- Award totals by state, agency, and phase — SBA annual reports [L18]. *(deps: —)*
- NAICS-sector coverage and fallback usage. *(deps: IMP for NAICS)*

### D2. Relational (Tier 2)

- What are federal fiscal returns (tax receipts) from SBIR program spending? — [fiscal/](fiscal/). TechLink's DoD-wide 1995–2018 study reports ~22:1 total-output ROI, 8.4:1 sales ROI, $39.4B tax revenue [L19]; Air Force ~12:1, Navy ~19.5:1 [L19]; NCI published a separate economic-impact study [L20]. *(deps: ER, ID, NAICS, BEA I-O)*
- What are employment, wage, proprietor-income, and production impacts by award? *(deps: fiscal model)*
- How do fiscal returns stratify by state and NAICS sector? *(deps: ER, NAICS)*
- Which NAICS sectors show the highest fiscal return multipliers? *(deps: fiscal model)*
- What is the payback period for Treasury investment recovery? *(deps: fiscal model)*
- Decomposed by jurisdiction: federal income, payroll, corporate, and excise vs. state/local income, sales, and property — what share of total tax impact accrues where? *(deps: fiscal model with state rates)*

### D3. Uncertainty & reconciliation (Tier 3)

- How robust are fiscal return estimates to parameter uncertainty (sensitivity bands)? *(deps: full fiscal model)*
- What are match rates and entity-resolution coverage needed to reconcile to NASEM leverage and impact figures [L1][L2]? *(deps: ER, ID)*
- Are tax-impact estimates more credible when derived from BEA NIPA tables [L22] than from hardcoded effective rates? Does state-specific variation (e.g., TX with no income tax vs. CA at 13.3%) materially change state-by-state ROI estimates? *(deps: NIPA rate provider, state rate provider)*

## E. Program management & data infrastructure

*Audience: SBA, agency program managers, GAO, internal pipeline engineers. Foundational — most questions in A–D depend on work here.*

### E1. SBIR identification (foundation, Tier 1–2)

- Which federal awards are SBIR/STTR vs. non-SBIR, and with what confidence? Three-tier classifier (FPDS research field 1.0 → ALN 0.8–1.0 → description parsing 0.5–0.7) — [sbir-identification-methodology.md](sbir-identification-methodology.md). CRS [L15], GAO [L14]. *(deps: —)*
- What are false-positive rates for shared-ALN grant identification (e.g., NIH ~20%)? *(deps: ID)*
- How does SBIR.gov data reconcile with federal USAspending/FPDS records? GAO [L14] and NASEM [L1][L3] flag tracking-data limits. *(deps: —)*

### E2. Entity resolution (foundation, Tier 1–2)

- Is this SBIR recipient the same entity that won the federal contract? UEI → CAGE → DUNS → fuzzy-name cascade — [transition/vendor-matching.md](transition/vendor-matching.md). *(deps: —)*
- What is the entity-resolution match rate, and what is the exact-vs-fuzzy share? *(deps: ER)*
- Have companies undergone acquisitions or rebrandings that break matching? *(deps: ER)*

### E3. Data quality & completeness (Tier 1)

- What percentage of awards have valid NAICS codes, and what is the fallback usage rate? *(deps: —)*
- How many awards lack UEI/DUNS identifiers? *(deps: —)*
- What is the data-freshness lag for SBIR.gov, USAspending, USPTO, and BEA I-O sources? *(deps: —)*
- Which awards have missing or null critical fields (amount, dates, recipient)? *(deps: —)*

### E4. Data imputation (Tier 2–3) *(spec merged via PR #277; implementation not yet started)*

- Why is `award_date` missing on ~50% of records, and can it be recovered non-destructively? — [../specs/data-imputation/](../specs/data-imputation/). *(deps: E3)*
- For each imputable field (award date, amount, contract dates, NAICS, identifiers), which methods are available and at what confidence tier (high ≥90%, medium 75–90%, low <75%)? *(deps: E3)*
- What is per-method backtest accuracy / MAE against ground-truth holdouts? *(deps: IMP)*
- Can solicitation topics be mapped to NAICS (agency-topic crosswalk top-1 accuracy ≥75%)? *(deps: IMP, CET)*
- Does the phase-transition precision benchmark remain ≥85% when imputed values are included? *(deps: IMP + transition detection)*
- Which downstream consumers (Neo4j, CET, transition detection) should use raw vs. effective values? *(deps: IMP)*

### E5. External data source evaluation (Tier 2) *(branch: claude/procurement-data-sources-eval)*

- Does SAM.gov Entity Extracts materially improve UEI backfill recall? — `specs/procurement-data-sources-eval/` *(branch)*. *(deps: ER)*
- Does the SAM.gov Opportunities API replace agency-page scraping for solicitation ceilings and periods of performance? *(deps: E3)*
- Does FSCPSC NAICS prediction beat our abstract-nearest-neighbor baseline? *(deps: IMP)*
- Does the PSC Selection Tool provide the NAICS ↔ PSC crosswalk needed for topic-derived NAICS? *(deps: IMP)*
- Do DIIG CSIS lookup tables feed our NAICS hierarchy or agency normalization? *(deps: —)*
- Should we adopt third-party procurement-tools clients (e.g., `makegov/procurement-tools`, `tandemgov/fpds`)? — `docs/decisions/procurement-tools-evaluation.md` *(branch)*. *(deps: —)*

### E6. Continuous monitoring & rolling analytics (Tier 4, capstone)

- What are current-quarter SBIR metrics and trends (weekly snapshots)? — [research-plan-alignment.md](research-plan-alignment.md). Fills the gap between point-in-time NASEM reviews [L1][L3][L4][L5]. *(deps: E1–E5 + A–D pipelines)*
- How have transition rates, patent output, and fiscal returns changed quarter-over-quarter? *(deps: all)*
- Which agencies are under-performing on transitions vs. historical baseline? *(deps: all)*

## F. Capital formation & entrepreneurial finance

*Audience: NVCA, Kauffman Foundation, NBER entrepreneurship researchers, VC/PE analysts, agencies (NSF, NIH) running founder-track programs. Does SBIR funding substitute for, complement, or seed private capital?*

This area treats the SBIR awardee as a **firm with a capital history**, not as a federal-contract counterparty. Data comes from SEC EDGAR (Form D, 8-K), state UCC-1 financing-statement registries, and the unified capital-event timeline. The literature is Lerner [L10], Howell [L11], Kortum & Lerner [L24], and the NVCA Yearbook [L25] rather than NASEM and GAO.

### F1. Descriptive (Tier 1)

- What is the Form D [L23] private-placement fundraising profile of SBIR awardees? *(PR #286 merged)* *(deps: ER, SEC EDGAR)*
- What is the debt-vs-equity composition and offering fill rate of SBIR-firm Form D filings? *(PR #286 merged)* *(deps: ER, SEC EDGAR)*
- What fraction of SBIR awardees show secured-debt activity (UCC-1 filings), and what mix of equipment finance, depository-bank lending, and venture debt do those filings represent by lender? UCC-1 complements Form D's equity view — [../specs/ucc1-financing-analysis/](../specs/ucc1-financing-analysis/) *(PRs #303 / #305 merged, CA-only pilot found equipment + community-bank patterns and an absence of venture-debt lenders in the CA channel)*. *(deps: ER, UCC-1)*
- Unified capital-event timeline: federal awards, private placements, M&A, and patent events on a single firm history *(PR #307 merged)*. *(deps: ER, SEC EDGAR, UCC-1, M&A signals)*
- What is the SBIR-firm M&A exit rate, and how does it stratify by funding agency (HHS biotech ~9.3% vs. DoD defense ~5.8%)? *(PR #286 merged)* *(deps: ER, M&A signals)*
- What is the median time from first SBIR award to M&A exit (~15 years per PR #286)? *(deps: ER, M&A signals)*

### F2. Relational (Tier 2)

- Among acquirers of SBIR firms, what share are life-sciences consolidators (Bruker, Ligand, Thermo Fisher) vs. defense primes vs. financial sponsors? What fraction of acquirers are serial (3+ SBIR-firm targets)? *(deps: ER, M&A signals)*
- Do Form D filers and non-filers differ on transition, patent, and exit outcomes — controlling for vintage, agency, and CET area? *(PR #314)* *(deps: ER, ID, CET, SEC EDGAR)*
- What is the SBIR ↔ M&A-event match rate by fiscal year, and how is coverage trending? *(PR #313)* *(deps: ER, M&A signals)*
- How does SBIR-firm capital structure benchmark against the NVCA Yearbook [L25] cohort of comparable-stage VC-backed startups? *(deps: ER, SEC EDGAR)*

### F3. Inferential (Tier 3)

- What is the **private-to-SBIR leverage ratio** (private capital raised ÷ SBIR funding) by agency, vintage, and firm size? The private-side mirror to NASEM's 4:1 DoD non-SBIR-federal leverage [L1]. *(deps: ER, ID, SEC EDGAR)*
- For Phase II awardees of any agency, do follow-on funding and exit outcomes match the published private-capital-backed-startup baselines from the NVCA Yearbook [L25]? *(PR #321 merged, supersedes #311; agency-parameterized via the `agency_private_capital_baseline_comparison` asset in group `agency_private_capital`, terminology changed from "VC" to "private capital")* *(deps: ER, SEC EDGAR)*
- Does SBIR funding crowd in or crowd out subsequent private capital? **Target: reproduce or extend Howell's finding that an early-stage DOE SBIR grant roughly doubles the probability of subsequent VC** [L11]. Compare against Kortum & Lerner [L24] on VC's contribution to innovation. *(deps: ER, ID, SEC EDGAR)*
- Does the Lerner [L10] finding — SBIR growth effects concentrated in VC-rich zip codes — still hold post-2010 and across all eleven agencies? *(deps: ER, ID, SEC EDGAR)*

### F4. Predictive (Tier 4)

- Forward-looking probability of an exit event (M&A or IPO) for a given SBIR firm, conditional on capital-event history and CET area. *(deps: all of F1–F3)*

## Output products & audiences

Documents and reports the question inventory has produced for specific audiences. Each is a synthesis of A-F questions for a particular reader, not a new research question itself.

### Congressional district success-story briefings

**Audience:** members of Congress and their staff, for constituent-facing communication.
**Format:** per-district briefing identifying 3-5 SBIR firms within the member's district that represent the strongest success stories (FDA-cleared products, defense supplier roles, follow-on capital raises, M&A exits) with political-safety vetting.
**Districts covered to date** (in conversation; not yet committed as repo artifacts): KY-3 (McGarvey), NJ-10 (McIver), NY-16 (Latimer), NH-2 (Goodlander), MT-2 (Downing), TX-6 (Ellzey), and a CNMI null finding for King-Hinds. Vetting depth includes press review, SEC Form D filings, M&A history, and any political-sensitivity factors (foreign ownership, classified work exposure, recent acquisition).
**Supporting code:** `sbir_etl/enrichers/congressional_district_resolver.py` (UEI → district resolver), `scripts/setup_congressional_districts.py` (district reference data).
**Pulls from:** Section A (portfolio composition + Axis B foreign-ownership / acquisition screens, B1), B1-B3 (commercialization signals, §B), F1-F2 (capital events, M&A). (Classified-work exposure remains a manual political-sensitivity vetting factor, not an automated pipeline screen — there is no Axis B signal for it.)

### Form D fundraising analysis (published)

**Audience:** F-area analysts, investor researchers, policy staff studying program-wide private-capital leverage.
**Format:** `docs/research/sbir-form-d-fundraising-analysis.md` (canonical, on main) + companion methodology docs: `form-d-leverage-bootstrap-findings.md` (CIs, on main from PR #338); `form-d-pif-cross-link-audit.md` (PIF integrity, in [PR #340](https://github.com/hollomancer/sbir-analytics/pull/340)); `dod-form-d-leverage-deep-dive.md` (Branch decomposition, in [PR #342](https://github.com/hollomancer/sbir-analytics/pull/342)); `dod-form-d-followup-findings.md` (per-firm + time-series + acquirer-type, in [PR #343](https://github.com/hollomancer/sbir-analytics/pull/343)); `dod-fpds-substitution-test-findings.md` (Form D vs. FPDS substitution-channel follow-up, on main from PR #350).
**Pulls from:** F1 (Form D profile), F3 (private-to-SBIR leverage), Section A (DoD leverage ratio + Axis B vulnerability decomposition).

### Commercialization-benchmark methodology (in progress, not yet committed)

**Audience:** SBA program oversight, statutory compliance reviewers, GAO.
**Format:** `docs/commercialization-benchmark-methodology.md` (locally present but **not committed** to the repo) documenting the §638(qq)(3) statutory framework, the FY2026 evaluation methodology, the data-source provenance (FPDS/USAspending contracts, SEC Form D investment, SBIR.gov FABS grants), and the per-firm audit protocol. The methodology doc pairs with a per-firm audit harness (`scripts/data/run_commercialization_benchmark.py` and `scripts/data/audit_one_firm.py`) and an FY2026 audited cohort CSV — all of which are **local-only / uncommitted** on the author's machine. The shippable counterpart on main is `scripts/run_benchmark.py` + `sbir_etl/models/benchmark_models.py`, which implements the same statutory framework via a different CLI shape. **The methodology doc + audit harness should be committed once stabilized** — the untracked status is itself a coverage gap worth closing.
**Pulls from:** B3 (transition effectiveness + new §638(qq) benchmark question), F1 (Form D investment signal), F2 (NVCA-baseline comparison).

## Prior literature & benchmarks

Public studies the inventory draws from or benchmarks against.

**NASEM reviews (congressionally mandated):**

- **[L1]** NASEM (2026). *Review of the SBIR and STTR Programs at the Department of Defense.* Key finding: DoD SBIR firms attract >4× non-SBIR DoD funding per SBIR dollar (2012–2020); SBIR firms are ~1/3 of the defense R&D base. <https://www.nationalacademies.org/projects/PGA-STEP-17-08/publication/29329>
- **[L2]** NRC (2014). *SBIR at the Department of Defense.* Earlier assessment — baseline for longitudinal comparison. (Published under the National Research Council name, before the July 2015 NASEM rename.) <https://nap.nationalacademies.org/read/18821/>
- **[L3]** NASEM (2022). *Assessment of the SBIR and STTR Programs at the NIH.* <https://nap.nationalacademies.org/read/26376/>
- **[L4]** NASEM (2023). *Review of the SBIR and STTR Programs at the National Science Foundation.* <https://nap.nationalacademies.org/read/26884/>
- **[L5]** NASEM (2020). *Review of the SBIR and STTR Programs at the Department of Energy.* Draws on Myers & Lanahan spillover work. <https://nap.nationalacademies.org/read/25674/>
- **[L6]** NASEM (2015). *SBIR/STTR at the National Institutes of Health.* <https://www.ncbi.nlm.nih.gov/books/NBK338158/>
- **[L7]** NASEM (2016). *STTR: An Assessment of the Small Business Technology Transfer Program.* <https://www.ncbi.nlm.nih.gov/books/NBK338709/>
- **[L8]** NASEM. *Capitalizing on Science, Technology, and Innovation: An Assessment of the SBIR Program — Phase II.* <https://www.nationalacademies.org/our-work/capitalizing-on-science-technology-and-innovation-an-assessment-of-the-small-business-innovation-research-program---phase-ii>

**Peer-reviewed academic studies:**

- **[L9]** Myers, K. & Lanahan, L. (2022). "Estimating Spillovers from Publicly Funded R&D: Evidence from the US Department of Energy." *American Economic Review.* Finding: ~3× spillover multiplier; ~60% of spillovers retained in U.S. <https://www.aeaweb.org/articles?id=10.1257/aer.20210678>
- **[L10]** Lerner, J. (1999). "The Government as Venture Capitalist: The Long-Run Impact of the SBIR Program." *Journal of Business* 72(3), 285–318. Finding: SBIR awardees grew faster over 10 years; effect concentrated in VC-rich zip codes. NBER w5753. <https://www.nber.org/papers/w5753>
- **[L11]** Howell, S.T. (2017). "Financing Innovation: Evidence from R&D Grants." *American Economic Review* 107(4), 1136–64. Finding: early-stage DOE SBIR grant roughly doubles probability of subsequent VC; large positive effects on patenting and revenue. <https://www.aeaweb.org/articles?id=10.1257/aer.20150808>
- **[L12]** Link, A.N. & Scott, J.T. (2010, 2012). "Government as Entrepreneur: Evaluating the Commercialization Success of SBIR Projects" and related work. Econometric commercialization-probability models using the NRC SBIR database.
- **[L13]** Jaffe, A., Trajtenberg, M., & Henderson, R. (1993). "Geographic Localization of Knowledge Spillovers as Evidenced by Patent Citations." *Quarterly Journal of Economics.* Methodological foundation for citation-based spillover measurement.

**Government & policy reports:**

- **[L14]** GAO-24-107036 (2024). *Small Business Research Programs: Agencies Broadly Solicit Ideas, but Clearer Guidance Could Improve DOD Efforts.* Documents Phase III data limitations and open-topic solicitation practices. The "single (2014) Commercialization Benchmark run" finding is documented in CRS R43695 [L15], not this report. <https://www.gao.gov/assets/gao-24-107036.pdf>
- **[L15]** CRS R43695. *Small Business Research Programs: SBIR and STTR.* Statutory structure, three-phase model, identifier mechanics. <https://www.congress.gov/crs-product/R43695>
- **[L16]** CSIS Center for the Industrial Base (formerly DIIG). Defense-industrial-base research, including SBIR coverage. <https://www.csis.org/programs/center-industrial-base>
- **[L17]** CSIS (various). *SBIR and STTR Reauthorization and the Future of Small Business Innovation.* Policy analysis including foreign-acquisition risk. <https://www.csis.org/analysis/sbir-and-sttr-reauthorization-and-future-small-business-innovation>
- **[L18]** SBA. *SBIR/STTR Annual Reports* (FY20, FY21, FY22). Award totals by agency/state/phase; first-time-winner shares. <https://www.sbir.gov/sites/default/files/SBA_FY22_SBIR_STTR_Annual_Report.pdf>

**Economic impact studies:**

- **[L19]** TechLink / Montana State University. *National Economic Impacts from the DOD SBIR/STTR Programs, 1995–2018.* 22:1 total-output ROI; 8.4:1 sales ROI; $39.4B in federal + state + local tax revenue. Sub-studies for Air Force (~12:1), Navy (~19.5:1). <https://sbtc.org/wp-content/uploads/2019/09/National-Economic-Impacts-From-the-DOD-SBIR-STTR-Programs-1995-2018.pdf>
- **[L20]** NCI SBIR Development Center. *Economic Impact Study Report.* <https://sbir.cancer.gov/portfolio/impact-study/economic-impact-study-report.pdf>
- **[L21]** ITIF (2019). *Becoming America's Seed Fund: Why NSF's SBIR Program Should Be a Model for the Rest of Government.* <https://itif.org/publications/2019/09/26/becoming-americas-seed-fund-why-nsfs-sbir-program-should-be-model-rest/>

**Tax & macro data sources:**

- **[L22]** BEA. *NIPA Tables 3.2 (Federal Government Current Receipts), 3.3 (State & Local Government Current Receipts), and 1.5 (GDP by Major Type of Product).* Effective federal/state/local rate baselines for fiscal-impact modeling. <https://apps.bea.gov/iTable/>
- **[L23]** SEC. *Form D Notice of Exempt Offering of Securities (Reg D) and Form 8-K Current Report.* Public filings used for SBIR-firm M&A and private-placement detection. <https://www.sec.gov/forms>

**Entrepreneurial-finance literature & benchmarks:**

- **[L24]** Kortum, S. & Lerner, J. (2000). "Assessing the Contribution of Venture Capital to Innovation." *RAND Journal of Economics* 31(4), 674–692. Foundational study estimating VC's marginal contribution to patenting; reference point for SBIR-vs-VC innovation comparisons. <https://www.jstor.org/stable/2696354>
- **[L25]** National Venture Capital Association. *NVCA Yearbook* (annual). Industry-standard benchmarks for VC fundraising, deployment, deal stage/size, and exit activity used as the non-SBIR cohort for capital-formation comparisons. <https://nvca.org/research/nvca-yearbook/>

**Statute:**

- **[L26]** Pub. L. 119-83 — SBIR/STTR reauthorization (signed April 13, 2026). Establishes the risk-based due-diligence factors and the eight restricted-entity screening lists (UFLPA Entity List; NS-CMIC List; Section 889 Prohibition List; 1260H list; Military End-User List; BIS Entity List; FCC Covered List; CBP WRO/Findings List) that ground Axis B, plus the Strategic Breakthrough Allocation and Phase III provisions that ground Axis A. <https://www.congress.gov/public-laws/119th-congress>

---

## Maintenance

**Last reviewed:** 2026-06-21 — staleness audit verified all PR refs, branch tags, spec/doc links, and architectural notes against current `main`. Three corrections shipped via PR #335 (F3 supersession by #321, E4 spec landed via #277, A4 M&A pipeline architecture note). A follow-on PR #341 (currently open) proposes updating the published Form D fundraising doc with bootstrap CIs and PIF cross-link audit findings.

When this doc is reviewed next, the audit should cover:

- All `*(PR #...)*` references resolve to merged or otherwise tracked PRs (closed-without-merge PRs need explicit successor links — PR #311 → #321 was the prior failure mode)
- All `*(branch: ...)*` tags point at branches that still exist on origin (`claude/sbir-data-imputation-strategy` was the prior failure mode — branch deleted, work landed under a different name)
- Internal links to `../specs/` and `docs/` directories resolve
- Each "deps:" tag accurately reflects current pipeline structure (M&A signals are script-driven, not orchestrated — flagged in the M&A implementation note under Section A → Supporting DIB questions)
- Coverage gaps: cross-reference recent merged feature PRs against the question inventory to surface work not yet documented here
- CET taxonomy consistency: the canonical spine is the 21-area `NSTC-2025Q1` set (`config/cet/taxonomy.yaml`, validated by `taxonomy_loader.py`). Two divergent code-level taxonomies remain unreconciled — a 10-area transition-system set (`docs/transition/cet-integration.md`, code in transition CET inference) and a 19-area hardcoded reporting set (`sbir_etl/utils/reporting/analyzers/cet_analyzer.py`). Reconciling these to the 21-area spine is a code change with test/precision-benchmark risk and should be scoped separately.

Update this footer with the new review date when the audit completes.

