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

- **Policymakers** (Congress, OMB, agency leadership, congressional defense committees): start with the **DoD follow-on funding multiplier** question (Section **A3**, inferential tier; reproduces NASEM's ~4:1 benchmark — NASEM calls this quantity the *leverage ratio*), **D2** (Treasury ROI / tax receipts from SBIR spending), and **F3** (private-to-SBIR leverage as the private-side mirror to the DoD follow-on funding multiplier).
- **SBIR program managers** (NSF, NIH, DoD, DOE, SBA program offices): start with **B** (transitions, Phase II→III latency, company performance), **C1** (cross-agency CET portfolio composition), and **E6** (rolling quarterly snapshots / continuous monitoring).
- **Investors** (VC, PE, angels, family offices, corporate VC): start with **F1** (Form D fundraising profile, M&A exit rate by funding agency, capital-event timeline) and **F2** (cohort outcomes vs. published VC/PE baselines, acquirer-type concentration).
- **OSTP / congressional oversight** (OSTP, armed-services / science / small-business committees): start with the **choke-point fragility watchlist** (Section **A4**, A-CP13 — the flagship composite) and the **capability density & choke-point concentration map** (Section **A1**, A-CP1/A-CP2/A-CP3). The choke-point questions are research targets, not yet scoped or implemented — see their inline status labels.

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

*Audience: DoD acquisition leadership, congressional defense / armed-services committees, OSTP, congressional science / small-business committees, CSIS-style industrial-base analysts. This section merges three previously-separate framings — the defense-industrial-base questions, the supply-chain / technology choke-point set, and the former standalone "industrial-base resilience" section — into one complexity-tier ladder. They serve the same audience and statutory goal and draw on the same `CET`, `NAICS`, `ER`, `SEC EDGAR`, and `M&A signals` data. For SBIR-firm capital structure and exit analysis from an entrepreneurial-finance perspective, see [F. Capital formation & entrepreneurial finance](#f-capital-formation--entrepreneurial-finance).*

### The master question: industrial capability vs. vulnerability

**Master question:** Across the CET areas, where does SBIR/STTR build domestic industrial capability that strengthens the DIB, and where are awardees exposed to adversary ownership/control or capability concentration that creates vulnerability?

Two lenses run through every tier below — **capability** (does SBIR/STTR build domestic industrial capability?) and **vulnerability / choke-point exposure** (are awardees exposed to adversary control or capability concentration?). The framing is only honest because award data answers the capability side **well** and the vulnerability / choke-point side **only weakly**: strong capability metrics must not lend false confidence to weak vulnerability inferences, so every question keeps its own answerability label and weak ones are not allowed to free-ride. Questions are tagged **(cap)**, **(vuln)**, or **(cap/vuln)** for the lens(es) they read; the supply-chain choke-point questions carry their original `A-CP#` identifiers inline so prior references still resolve. Physical / sub-tier supply-chain questions that award data cannot answer are listed in the **Out of scope** appendix at the end of the section, stated explicitly rather than as graded metrics.

**CET spine.** The organizing spine is the repo's **21-area `NSTC-2025Q1`** taxonomy defined in `config/cet/taxonomy.yaml`; `packages/sbir-ml/sbir_ml/ml/config/taxonomy_loader.py` expects exactly 21 areas and logs a warning on any mismatch (a soft check, not a hard-failing validation). This is *not* the external 18-area Feb-2024 NSTC Critical and Emerging Technologies list [L29], nor DoD's 14 Critical Technology Areas — both are narrower external frameworks, and the repo's 21-area set already blends NSTC CET areas with several DoD critical-technology areas (Hypersonics, Directed Energy, Advanced Gas Turbine Engine Technologies, Integrated Network Systems-of-Systems). **Crosswalk note:** for DoD-facing outputs each CET area should also carry a **DoD-14** and an **NDIS-8** (National Defense Industrial Strategy supply-chain-priority) tag where a mapping exists, so results speak to both NSTC and DoD audiences. (Two other, divergent CET taxonomies exist in code — a 10-area transition-system set and a 19-area reporting-analyzer set — and are not yet reconciled to the canonical 21; see Maintenance.)

**Statutory grounding.** The vulnerability lens maps to the risk-based due-diligence factors of the SBIR/STTR reauthorization, **Pub. L. 119-83** (signed April 13, 2026), and its eight restricted-entity screening lists — the UFLPA Entity List, the Non-SDN Chinese Military-Industrial Complex Companies (NS-CMIC) List, the Section 889 Prohibition List, the 1260H list, the Military End-User (MEU) List, the BIS Entity List, the FCC Covered List, and the CBP WRO/Findings List [L26]; the FY2026 NDAA [L27] carries related DIB authorities. The capability lens maps to the same law's Strategic Breakthrough Allocation and Phase III provisions. The choke-point questions are framed by the DoD National Defense Industrial Strategy [L28] and the DoD State of Competition report [L31]. (Statutes linked, not reproduced.)

### A1. Descriptive (Tier 1)

- Portfolio composition by DoD component (Army/Navy/AF/DARPA/DLA), phase, and vintage — SBA annual reports [L18]. *(deps: —)*
- **(cap/vuln) Capability density & choke-point concentration map per CET area** *(A-CP1 concentration map / A-CP2 supplier-base thickness / A-CP3 geographic distribution)* — distinct awardee counts, award volume, and an awardee **HHI** per CET area, read across NAICS sector and geography (state / congressional district). High density reads as capability; the same HHI inverted is the choke-point concentration map, flagging single-/thin-supplier clusters and geographically narrow bases. GAO's program-wide Phase II HHI of ~11 [L14] is the diffuse baseline that area-level concentration is measured against. CSIS Center for the Industrial Base [L16]; cross-read against the external NSTC CET list [L29]. **[Answerable now]** *(deps: CET, ER, NAICS)*
- **(cap) Whitespace** — CET subfields with DoD demand signals but sparse SBIR coverage, surfaced via semantic search over award and solicitation text. **[Answerable now]** *(deps: CET)*
- **(cap) Capital formation / firm health per CET area** — Form D raises and follow-on funding as a proxy for awardee financial health by technology area (the defense-CET slice of F1). **[Partial — SEC/Form D filers only]** *(deps: ER, CET, SEC EDGAR)*
- **(vuln) Foreign ownership / control (FOCI) exposure share per CET area** *(A-CP4; LOWER-BOUND proxy — EDGAR Exhibit 21 / 8-K plus entity resolution detect only disclosed/structured ownership, not private beneficial ownership)* — share of awardees and award volume per CET area under disclosed foreign ownership / control / influence, screened against the eight Pub. L. 119-83 restricted-entity lists [L26] and read alongside GAO's foreign-supplier-dependence findings [L30]. Foreign-acquisition risk flagged by CSIS [L17]. **[Now for the SEC-filer subset; needs data acquisition for the private majority]** *(deps: ER, SEC EDGAR, M&A signals)*

### A2. Relational (Tier 2)

- Do firms show higher transition rates within the same awarding agency (agency continuity signal)? *(deps: ER, ID)*
- **(cap) DIB integration** — Phase II→III transition rate per CET area via FPDS, plus SAM.gov subaward links to prime contractors — [../specs/ot-consortium-subaward-attribution/](../specs/ot-consortium-subaward-attribution/) (FFATA/FSRS sub-award T1 recovery). Aligns with NASEM's "knowledge transfer to primes" finding [L1]. **[Answerable now, moderate confidence — FPDS Phase III tagging is historically incomplete; GAO [L14]]** *(deps: ER, ID, CET, transitions)*
- **(cap/vuln) Awardee-as-IP-chokepoint** *(A-CP6)* — within a CET area, do patent assignment chains (`ASSIGNED_VIA/FROM/TO`) show a small number of awardees as the dominant source of enabling IP flowing to primes (knowledge-supply-chain position)? Builds on the C2 patent-linkage work; the citation-centrality "who-depends-on-whom" variant needs patent-citation edge ingestion (a `PatentCitation` model exists but citations are not yet graph relationships). Aligns with NASEM's knowledge-transfer-to-primes finding [L1]. **[Partial — assignment-chain lens buildable now; citation-centrality needs ingestion]** *(deps: ER, PATLINK, CET)*
- **(vuln) Adversary-affiliation screening** — entity resolution of awardees and key personnel against the named restricted-entity lists and foreign-country-of-concern ties. **[Partial via public lists; full coverage needs agency-held due-diligence data]** *(deps: ER)*
- **(vuln) Concentration vs. transition-thinness** *(A-CP5)* — do the most concentrated (thin-base) CET areas also show the thinnest Phase II→III transition pipelines, compounding fragility (concentrated AND failing to graduate)? FPDS Phase III undercount [L14] bounds confidence. **[Research target — not yet scoped]** *(deps: ER, ID, CET, transitions)*
- **(vuln) New-entrant vs. repeat-winner mix per CET area** *(A-CP7)* — share of awards going to first-time vs. repeat winners, as a read on entrant-pipeline health and graduation (CSIS new-entrant / small-business-graduation analysis [L32]). **[Research target — not yet scoped]** *(deps: ER, ID, CET)*

*The SBIR-vs-non-SBIR identification question and the underlying patent-to-award linkage are foundational and live at their canonical homes — see **E1** and **C2** — rather than being restated here.*

### A3. Inferential (Tier 3)

**DoD follow-on funding multiplier** (NASEM calls this the *leverage ratio*).

- What is the aggregate follow-on funding multiplier (non-SBIR DoD obligations ÷ SBIR/STTR obligations) for DoD SBIR firms? **Target: reproduce NASEM's ~4:1 for 2012–2020** [L1][L2] — [../specs/archive/completed-features/follow-on-multiplier-analysis/](../specs/archive/completed-features/follow-on-multiplier-analysis/) (FPDS contract-node ingestion: [../specs/archive/completed-features/load-contract-nodes/](../specs/archive/completed-features/load-contract-nodes/)). *(deps: ER, ID)*
- How does the multiplier stratify by award vintage, firm size, technology area, and firm experience (new vs. repeat)? NASEM reports SBIR firms = ~1/3 of DoD's extramural R&D base [L1]. *(deps: ER, ID, CET)*
- How is the multiplier changing over time? *(deps: ER, ID)*
- What is the multiplier for civilian agencies (e.g., DOE)? Myers & Lanahan [L9] and NASEM DOE [L5] supply baselines. *(deps: ER, ID)*

**Concentration & choke-point inference.**

- **(vuln) Concentration-as-fragility** — single-firm or thin-base dominance within a CET cluster, read as risk rather than capability (the A1 HHI inverted, including geographically narrow bases). Has the base for a given area thinned or thickened over time, and which sole-supplier firms would, if acquired or lost, remove a capability with no in-program substitute? **[Answerable now]** *(deps: ER, CET)*
- **(vuln) Composite fragility inference per CET area** *(A-CP10)* — combine concentration (A-CP1/A-CP2), geographic narrowness (A-CP3), transition-thinness (A-CP5), and new-entrant deficit (A-CP7) into a per-area fragility judgment that flags areas concentrated, failing to graduate, and starved of new entrants at once [L28][L30]. **[Research target — not yet scoped]** *(deps: CET, ER, ID, NAICS, transitions)*
- **(vuln) Program leverage at choke points** *(A-CP11; LOWER-BOUND proxy — EDGAR captures only disclosed private capital)* — the DoD follow-on funding multiplier above and the private-to-SBIR leverage ratio (**F3**) sliced to choke-point firms: does thin-base concentration coincide with low or high leverage? Anchor to the verifiable DoD SBIR Fast Track match of up to four SBIR dollars per outside-investor dollar [L33] and NSF's reported portfolio leverage [TODO: verify NSF primary source for the ~18:1 figure — found only in trade press, not confirmed against an NSF publication; do not state as fact until verified]. **[Research target — not yet scoped]** *(deps: ER, ID, SEC EDGAR, CET)*
- **(vuln) Foreign-acquisition-pathway inference** *(A-CP12; LOWER-BOUND proxy — only disclosed/structured ownership and M&A signals are detectable, not private beneficial ownership)* — from disclosed ownership structure and M&A signals, infer which choke-point firms sit on a plausible foreign-acquisition pathway, screened against the restricted-entity lists [L26] and GAO's foreign-dependence findings [L30]. **[Research target — not yet scoped]** *(deps: ER, SEC EDGAR, M&A signals, CET)*

### A4. Risk, monitoring & prediction (Tier 4)

**M&A detection & transition pathways.**

- Did a defense-funded SBIR company undergo M&A activity, especially involving a foreign acquirer? — [../specs/archive/completed-features/merger_acquisition_detection/](../specs/archive/completed-features/merger_acquisition_detection/). *(deps: ER, M&A signals)*
- For SBIR firms acquired by public companies, can inbound M&A be detected via 8-K full-text search? *(PR #286)* *(deps: ER, SEC EDGAR)*
- Which defense primes concentrate SBIR-firm acquisitions (e.g., Titan, Teledyne, Ametek, Kratos), and are any of those acquirers themselves foreign-owned or under CFIUS review? *(deps: ER, M&A signals)*
- How does M&A activity affect Phase III / federal-contract transition pathways? *(deps: ER, M&A signals, transitions)*

**Choke-point monitoring & prediction.**

- **(vuln) Acquisition-erosion of thin bases** *(A-CP8; foreign-acquisition component is a LOWER-BOUND proxy)* — do M&A events remove sole- or dominant-supplier firms from already-thin CET bases, eroding capability through consolidation? Defense-sector consolidation [L31] and foreign-acquisition risk [L17] frame the concern. **[Research target — not yet scoped]** *(deps: ER, M&A signals, CET)*
- **(vuln) UCC-1 financial-distress signal** *(A-CP9)* — do shifts in UCC-1 secured-debt filing patterns (lapses, new liens, lender churn) flag financial distress among choke-point firms ahead of exit or capability loss? No external benchmark; novel signal. **[Research target — not yet scoped]** *(deps: ER, UCC-1, CET)*
- **(vuln) Choke-point fragility watchlist** *(A-CP13 — flagship).* A composite, forward-looking watchlist ranking CET areas — and the individual sole-/dominant-supplier firms within them — whose acquisition or loss would remove a capability with no in-program substitute. It fuses every signal above: concentration (A-CP1/A-CP2), geographic narrowness (A-CP3), FOCI (A-CP4), transition-thinness (A-CP5), IP-flow position (A-CP6), new-entrant deficit (A-CP7), composite fragility (A-CP10), acquisition-erosion (A-CP8), and UCC-1 distress (A-CP9); the FOCI and foreign-acquisition inputs are LOWER-BOUND proxies. Grounded in the NDIS supply-chain-resilience priority [L28], the State of Competition priority-sector framing [L31], and GAO-25-107283's sub-tier-visibility gap [L30]. **[Research target — flagship; not yet scoped or implemented]** *(deps: CET, ER, ID, transitions, M&A signals, UCC-1, SEC EDGAR)*
- **(vuln) Predictive erosion / early warning** *(A-CP14; foreign-acquisition component is a LOWER-BOUND proxy)* — forward probability that a given choke-point firm exits (M&A or financial distress) within a horizon, feeding the continuous-monitoring loop (**E6**) so a fragility flag is raised before the capability is lost [L30][L31]. **[Research target — not yet scoped]** *(deps: ER, M&A signals, UCC-1, CET, transitions)*

*Implementation note: M&A event detection runs as a CLI script
(`scripts/archive/data/detect_sbir_ma_events.py`), not as a Dagster asset. The script
merges two signals: Form D filings (entity_type-based business-combination
heuristics) and SEC EDGAR full-text mention scan across multiple filing types
(operationally: 8-K, 10-K, DEFM14A, PREM14A, SC TO-T, SC 14D9 — see
`scripts/archive/data/refine_ma_medium_tier.py`). The orchestrated graph has no
continuous M&A-event materialization; rerunning the script is how the M&A
signal that feeds the vulnerability (A1/A3/A4) and F-area questions gets
refreshed. The previously-existing
`packages/sbir-analytics/sbir_analytics/assets/ma_detection.py` stub was a
placeholder, never wired into the M&A pipeline, and was removed in PR #317.*

### Out of scope — physical & sub-tier supply chain (data the project does not ingest)

*Listed for visibility, these choke-point questions are **not answerable** with award-type data and are **not research targets** for this pipeline. Each requires bill-of-materials, customs, contractual country-of-origin, or sub-tier supplier data the pipeline does not ingest. Stated explicitly, not as graded metrics. GAO-25-107283 documents exactly this sub-tier-visibility gap [L30].*

- **Physical input chokepoints** — dependence on contested physical inputs (rare earths, castings, advanced chips, APIs); sole-source inputs, foreign-content percentages, and surge capacity. *(deps: — / out of scope)*
- **Tiered BoM / supplier-tier maps** — sub-tier (Tier 2/3/N) supplier-dependency mapping for a CET capability. *(deps: — / out of scope)*
- **Critical-mineral dependency** — exposure of a CET area to contested minerals/materials (rare earths, gallium, etc.). *(deps: — / out of scope)*
- **Allied-supplier substitution** — whether an allied or partner-nation supplier could substitute for a domestic choke point. *(deps: — / out of scope)*
- **Customs / trade-flow dependency** — import-dependence and trade-flow chokepoints for inputs to a CET capability. *(deps: — / out of scope)*
- **Sub-tier foreign integration** — foreign content or foreign-owned sub-tier suppliers buried below the prime/awardee tier. *(deps: — / out of scope)*

## B. Technology commercialization & entrepreneurship

*Audience: SBA oversight, agency program offices, awardee firms. Core statutory goal is Phase III commercialization.*

### B1. Descriptive (Tier 1)

- Is this SBIR company primarily a product, service, or mixed-mode firm (based on full federal contract portfolio)? — [../specs/company-categorization/](../specs/company-categorization/). *(deps: ER)*
- What percentage of a company's revenue comes from product vs. service contracts? *(deps: ER)*
- Which SBIR companies show the highest transition success rate, and which are consistent repeat performers? — [queries/transition-queries.md](queries/transition-queries.md). Lerner [L10] found growth concentrated in high-VC zip codes. *(deps: ER)*

### B2. Relational (Tier 2)

- Did this SBIR-funded research result in a federal contract? — [transition/overview.md](transition/overview.md), [../specs/archive/completed-features/transition_detection/](../specs/archive/completed-features/transition_detection/). Baselines: NASEM DoD [L1][L2]; Link & Scott ~50% commercialization probability [L12]; NASEM program reviews [L3][L4][L6]. *(deps: ER, ID)*
- Which SBIR-funded companies transitioned research into federal procurements? — [transition/detection-algorithm.md](transition/detection-algorithm.md). *(deps: ER, ID)*
- What is the average time from award to transition by technology area? *(deps: ER, ID, CET)*
- Which SBIR awards transitioned with patent backing, and what share of transitions are patent-enabled? Related to Lerner [L10] and Howell [L11]. *(deps: ER, ID, PATLINK)*

### B3. Inferential (Tier 3)

- What is the elapsed time between Phase II completion and first Phase III contract? — [phase-transition-latency.md](phase-transition-latency.md). GAO documents the newer §638(qq)(3) performance-standard framework and notes that commercialization progress is measured from multiple SBA data sources [L14]. *(deps: ER, ID)*
- Phase II → III survival probability by agency, firm size, and vintage. *(deps: ER, ID)*
- Does Phase II → III latency vary by technology area? *(deps: ER, ID, CET)*
- Transition effectiveness rate by CET area, agency, and firm size — compare to Link & Scott [L12] and NASEM [L1][L3][L4]. *(deps: ER, ID, CET)*
- How much undercount exists in Phase III coding by agency? Corroborated by GAO [L14] and NASEM [L1][L3]. FPDS Element 10Q (`research`, SR3/ST3) is reachable via the FPDS ATOM feed and drives the **status-denial flags** product: [../specs/product-1-status-denial-flags/](../specs/product-1-status-denial-flags/). Phase III solicitation monitoring: [../specs/phase-3-solicitation-alerts/](../specs/phase-3-solicitation-alerts/). **[Now for the 10Q-coded + SBIR-keyword subset; needs the full contract population (M0a) for complete coverage]** *(deps: ER, ID)* *(branch: claude/phase3-detection-phase0)*
- Which awards/solicitations to entity X plausibly derive from firm Y's Phase II work (Y ≠ X)? Ranked **bypass leads** for human review — never violation findings — gated on a text-match benchmark: [../specs/product-2-bypass-leads/](../specs/product-2-bypass-leads/), [../specs/phase3-match-benchmark/](../specs/phase3-match-benchmark/). Benchmark result: against true same-office negatives, embedding separability ≈ chance (AUC 0.56) and no better than lexical; realistic retrieval weak (P@1 0.23, ~2× random, optimistic). **[Research target — text-similarity ranker descoped to Tier-1 string-evidence; embedding ranker reopens only after full-population (M0a) precision@k]** *(deps: ER, ID, transitions)* *(branch: claude/phase3-detection-phase0)*
- Which expiring contract vehicles carry SBIR-derived content and are approaching recompete (6–18 months out)? Monthly **recompete watchlist** for pre-solicitation engagement: [../specs/product-4-recompete-watchlist/](../specs/product-4-recompete-watchlist/). **[Research target — buildable; bounded by ~20% IDV↔order linkage fill]** *(deps: ER, ID, transitions)* *(branch: claude/phase3-detection-phase0)*
- How does company categorization relate to transition likelihood? Baseline: Link & Scott commercialization-probability econometrics [L12]. *(deps: ER, ID)*
- Which Phase II awardees subject to §638(qq)(3) Increased Performance Standards meet the **statutory Commercialization Benchmark** (sales + private investment over the 10-FY covered period ÷ SBIR funding ≥ specified ratio)? Pub. L. 117-183 SBIR/STTR Extension Act of 2022 §638(qq)(3). Implementation on main: `scripts/run_benchmark.py` (evaluate / sensitivity / company-level CLI) backed by `sbir_etl/models/benchmark_models.py`, with tests in `tests/unit/test_benchmark_evaluator.py`. Spec: [../specs/archive/completed-features/commercialization-benchmark/](../specs/archive/completed-features/commercialization-benchmark/). Additional per-firm audit infrastructure and a more comprehensive methodology doc exist as local-only / uncommitted work — see "Output products" section below for the in-progress status. *(deps: ER, ID, transitions, SEC EDGAR)*

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
- NAICS-sector coverage and fallback usage — [../specs/naics-enricher-consolidation/](../specs/naics-enricher-consolidation/). *(deps: IMP for NAICS)*

### D2. Relational (Tier 2)

- What are federal fiscal returns (tax receipts) from SBIR program spending? — [fiscal/](fiscal/) ([../specs/fiscal-tax-impact-v2.md](../specs/fiscal-tax-impact-v2.md)). TechLink's DoD-wide 1995–2018 study reports ~22:1 total-output ROI, 8.4:1 sales ROI, $39.4B tax revenue [L19]; Air Force ~12:1, Navy ~19.5:1 [L19]; NCI published a separate economic-impact study [L20]. *(deps: ER, ID, NAICS, BEA I-O)*
- What are employment, wage, proprietor-income, and production impacts by award? *(deps: fiscal model)*
- How do fiscal returns stratify by state and NAICS sector? *(deps: ER, NAICS)*
- Which NAICS sectors show the highest fiscal return multipliers? *(deps: fiscal model)*
- What is the payback period for Treasury investment recovery? *(deps: fiscal model)*
- Decomposed by jurisdiction: federal income, payroll, corporate, and excise vs. state/local income, sales, and property — what share of total tax impact accrues where? *(deps: fiscal model with state rates)*

### D3. Uncertainty & reconciliation (Tier 3)

- How robust are fiscal return estimates to parameter uncertainty (sensitivity bands)? *(deps: full fiscal model)*
- What are match rates and entity-resolution coverage needed to reconcile to NASEM follow-on funding multiplier and impact figures [L1][L2]? *(deps: ER, ID)*
- Are tax-impact estimates more credible when derived from BEA NIPA tables [L22] than from hardcoded effective rates? Does state-specific variation (e.g., TX with no income tax vs. CA at 13.3%) materially change state-by-state ROI estimates? *(deps: NIPA rate provider, state rate provider)*

## E. Program management & data infrastructure

*Audience: SBA, agency program managers, GAO, internal pipeline engineers. Foundational — most questions in A–D depend on work here.*

### E1. SBIR identification (foundation, Tier 1–2)

- Which federal awards are SBIR/STTR vs. non-SBIR, and with what confidence? Three-tier classifier (FPDS research field 1.0 → ALN 0.8–1.0 → description parsing 0.5–0.7) — [sbir-identification-methodology.md](sbir-identification-methodology.md), [../specs/archive/completed-features/sbir-identification/](../specs/archive/completed-features/sbir-identification/). CRS [L15], GAO [L14]. *(deps: —)*
- What are false-positive rates for shared-ALN grant identification (e.g., NIH ~20%)? *(deps: ID)*
- How does SBIR.gov data reconcile with federal USAspending/FPDS records? GAO [L14] and NASEM [L1][L3] flag tracking-data limits. *(deps: —)*

### E2. Entity resolution (foundation, Tier 1–2)

- Is this SBIR recipient the same entity that won the federal contract? UEI → CAGE → DUNS → fuzzy-name cascade — [transition/vendor-matching.md](transition/vendor-matching.md). Graph schema: [../specs/archive/completed-features/unify-graph-node-labels/](../specs/archive/completed-features/unify-graph-node-labels/) (Phase 1, `:Award`→`:FinancialTransaction`) and [../specs/archive/completed-features/unify-company-into-organization/](../specs/archive/completed-features/unify-company-into-organization/) (Phase 2, `:Company`→`:Organization`). *(deps: —)*
- What is the entity-resolution match rate, and what is the exact-vs-fuzzy share? *(deps: ER)*
- Have companies undergone acquisitions or rebrandings that break matching? *(deps: ER)*

### E3. Data quality & completeness (Tier 1)

- What percentage of awards have valid NAICS codes, and what is the fallback usage rate? — [../specs/naics-enricher-consolidation/](../specs/naics-enricher-consolidation/). *(deps: —)*
- How many awards lack UEI/DUNS identifiers? *(deps: —)*
- What is the data-freshness lag for SBIR.gov, USAspending, USPTO, and BEA I-O sources? — [../specs/iterative_api_enrichment/](../specs/iterative_api_enrichment/). *(deps: —)*
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
- Does the SAM.gov Opportunities API replace agency-page scraping for solicitation ceilings and periods of performance? — [../specs/phase-3-solicitation-alerts/](../specs/phase-3-solicitation-alerts/). *(deps: E3)*
- Does FSCPSC NAICS prediction beat our abstract-nearest-neighbor baseline? *(deps: IMP)*
- Does the PSC Selection Tool provide the NAICS ↔ PSC crosswalk needed for topic-derived NAICS? *(deps: IMP)*
- Do DIIG CSIS lookup tables feed our NAICS hierarchy or agency normalization? *(deps: —)*
- Should we adopt third-party procurement-tools clients (e.g., `makegov/procurement-tools`, `tandemgov/fpds`)? — `docs/decisions/procurement-tools-evaluation.md` *(branch)*. *(deps: —)*

### E6. Continuous monitoring & rolling analytics (Tier 4, capstone)

- What are current-quarter SBIR metrics and trends (weekly snapshots)? — [research-plan-alignment.md](research-plan-alignment.md), [../specs/weekly-awards-report-refactor/](../specs/weekly-awards-report-refactor/). Fills the gap between point-in-time NASEM reviews [L1][L3][L4][L5]. *(deps: E1–E5 + A–D pipelines)*
- How have transition rates, patent output, and fiscal returns changed quarter-over-quarter? *(deps: all)*
- Which agencies are under-performing on transitions vs. historical baseline? *(deps: all)*

## F. Capital formation & entrepreneurial finance

*Audience: NVCA, Kauffman Foundation, NBER entrepreneurship researchers, VC/PE analysts, agencies (NSF, NIH) running founder-track programs. Does SBIR funding substitute for, complement, or seed private capital?*

This area treats the SBIR awardee as a **firm with a capital history**, not as a federal-contract counterparty. Data comes from SEC EDGAR (Form D, 8-K), state UCC-1 financing-statement registries, and the unified capital-event timeline. The literature is Lerner [L10], Howell [L11], Kortum & Lerner [L24], and the NVCA Yearbook [L25] rather than NASEM and GAO.

### F1. Descriptive (Tier 1)

- What is the Form D [L23] private-placement fundraising profile of SBIR awardees? *(PR #286 merged)* — [../specs/archive/completed-features/form-d-pipeline/](../specs/archive/completed-features/form-d-pipeline/). *(deps: ER, SEC EDGAR)*
- What is the debt-vs-equity composition and offering fill rate of SBIR-firm Form D filings? *(PR #286 merged)* *(deps: ER, SEC EDGAR)*
- What fraction of SBIR awardees show secured-debt activity (UCC-1 filings), and what mix of equipment finance, depository-bank lending, and venture debt do those filings represent by lender? UCC-1 complements Form D's equity view — [../specs/ucc1-financing-analysis/](../specs/ucc1-financing-analysis/) *(PRs #303 / #305 merged, CA-only pilot found equipment + community-bank patterns and an absence of venture-debt lenders in the CA channel)*. *(deps: ER, UCC-1)*
- Unified capital-event timeline: federal awards, private placements, M&A, and patent events on a single firm history *(PR #307 merged)*. *(deps: ER, SEC EDGAR, UCC-1, M&A signals)*
- What is the SBIR-firm M&A exit rate, and how does it stratify by funding agency (HHS biotech ~9.3% vs. DoD defense ~5.8%)? *(PR #286 merged)* *(deps: ER, M&A signals)*
- What is the median time from first SBIR award to M&A exit (~15 years per PR #286)? *(deps: ER, M&A signals)*

### F2. Relational (Tier 2)

- Among acquirers of SBIR firms, what share are life-sciences consolidators (Bruker, Ligand, Thermo Fisher) vs. defense primes vs. financial sponsors? What fraction of acquirers are serial (3+ SBIR-firm targets)? *(deps: ER, M&A signals)*
- Do Form D filers and non-filers differ on transition, patent, and exit outcomes — controlling for vintage, agency, and CET area? *(PR #314)* *(deps: ER, ID, CET, SEC EDGAR)*
- What is the SBIR ↔ M&A-event match rate by fiscal year, and how is coverage trending? *(PR #313)* — [../specs/sbir_ma_match_rate_by_fy/](../specs/sbir_ma_match_rate_by_fy/). *(deps: ER, M&A signals)*
- How does SBIR-firm capital structure benchmark against the NVCA Yearbook [L25] cohort of comparable-stage VC-backed startups? *(deps: ER, SEC EDGAR)*

### F3. Inferential (Tier 3)

- What is the **private-to-SBIR leverage ratio** (private capital raised ÷ SBIR funding) by agency, vintage, and firm size? The private-side mirror to NASEM's 4:1 DoD follow-on funding multiplier [L1] — [../specs/archive/completed-features/form-d-pipeline/](../specs/archive/completed-features/form-d-pipeline/), [../specs/agency-private-capital-comparison/](../specs/agency-private-capital-comparison/). *(deps: ER, ID, SEC EDGAR)*
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
**Pulls from:** Section A (portfolio composition; A1 foreign-ownership / A4 acquisition screens), B1-B3 (commercialization signals), F1-F2 (capital events, M&A). (Classified-work exposure remains a manual political-sensitivity vetting factor, not an automated pipeline screen — there is no vulnerability signal for it.)

### Form D fundraising analysis (published)

**Audience:** F-area analysts, investor researchers, policy staff studying program-wide private-capital leverage.
**Format:** `docs/research/sbir-form-d-fundraising-analysis.md` (canonical, on main; now includes Appendix A — firm-level bootstrap CIs, PR #338 — and Appendix B — PIF cross-link integrity audit, PR #341); `docs/research/dod-form-d-leverage.md` (DoD Branch decomposition + per-firm/time-series/acquirer-type follow-ups + Form D vs. FPDS substitution test, PRs #342/#343/#350); `docs/research/form-d-data-dictionary.md` (field reference).
**Pulls from:** F1 (Form D profile), F3 (private-to-SBIR leverage), A1/A4 (DoD-specific firm-health and acquisition decomposition).

### Commercialization-benchmark methodology (in progress, not yet committed)

**Audience:** SBA program oversight, statutory compliance reviewers, GAO.
**Format:** `docs/commercialization-benchmark-methodology.md` (locally present but **not committed** to the repo) documenting the §638(qq)(3) statutory framework, the FY2026 evaluation methodology, the data-source provenance (FPDS/USAspending contracts, SEC Form D investment, SBIR.gov FABS grants), and the per-firm audit protocol. The methodology doc pairs with a per-firm audit harness (`scripts/archive/data/run_commercialization_benchmark.py` and `scripts/data/audit_one_firm.py`) and an FY2026 audited cohort CSV — all of which are **local-only / uncommitted** on the author's machine. The shippable counterpart on main is `scripts/run_benchmark.py` + `sbir_etl/models/benchmark_models.py`, which implements the same statutory framework via a different CLI shape. **The methodology doc + audit harness should be committed once stabilized** — the untracked status is itself a coverage gap worth closing.
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

- **[L14]** GAO-24-106398 (2024). *Small Business Research Programs: Increased Performance Standards Likely Affect Few Businesses Receiving Multiple Awards.* Documents the §638(qq)(3) increased performance standards and SBA data sources for transition/commercialization measures. <https://www.gao.gov/assets/d24106398.pdf>
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

- **[L26]** Pub. L. 119-83 — SBIR/STTR reauthorization, enacting S.3971, the *Small Business Innovation and Economic Security Act of 2026* (signed April 13, 2026). Establishes the risk-based due-diligence factors and the eight restricted-entity screening lists (UFLPA Entity List; NS-CMIC List; Section 889 Prohibition List; 1260H list; Military End-User List; BIS Entity List; FCC Covered List; CBP WRO/Findings List) that ground the Section A **vulnerability** lens, plus the Strategic Breakthrough Allocation and Phase III provisions that ground the **capability** lens. <https://www.congress.gov/bill/119th-congress/senate-bill/3971>
- **[L27]** Pub. L. 119-60 — *National Defense Authorization Act for Fiscal Year 2026* (S.1071; signed December 18, 2025). FY2026 DIB and small-business authorities that contextualize the choke-point question set. <https://www.congress.gov/bill/119th-congress/senate-bill/1071>

**Industrial-base resilience & choke-point sources (for the Section A choke-point questions):**

- **[L28]** DoD. *National Defense Industrial Strategy (NDIS)* (released January 11, 2024). First-ever DoD industrial strategy; four priorities (supply-chain resilience, workforce readiness, flexible acquisition, economic deterrence) and ten systemic challenges including sub-tier supplier fragility. <https://www.businessdefense.gov/docs/ndis/2023-NDIS.pdf>
- **[L29]** OSTP / NSTC. *Critical and Emerging Technologies List — 2024 Update* (February 2024). NSTC interagency CET list; external reference framework distinct from the repo's 21-area `NSTC-2025Q1` spine. <https://bidenwhitehouse.archives.gov/wp-content/uploads/2024/02/Critical-and-Emerging-Technologies-List-2024-Update.pdf>
- **[L30]** GAO-25-107283 (2025). *Defense Industrial Base: Actions Needed to Address Risks Posed by Dependence on Foreign Suppliers.* Finds DoD relies on 200,000+ suppliers with little visibility past the prime-contractor tier — the documented sub-tier-visibility gap behind the out-of-boundary choke-point questions. <https://www.gao.gov/products/gao-25-107283>
- **[L31]** DoD. *State of Competition within the Defense Industrial Base* (February 15, 2022). Documents defense-sector consolidation (prime contractors 51→5 since the 1990s; small businesses in the DIB down >40% over a decade) and five priority sectors (microelectronics, missiles & munitions, high-capacity batteries, castings & forgings, critical minerals & materials). <https://media.defense.gov/2022/Feb/15/2002939087/-1/-1/1/STATE-OF-COMPETITION-WITHIN-THE-DEFENSE-INDUSTRIAL-BASE.PDF>
- **[L32]** CSIS Center for the Industrial Base. *New Entrants and Small Business Graduation in the Market for Federal Contracts.* FPDS-based analysis (2001–2016) of entrant, exit, and small-business graduation rates in federal contracting. <https://www.csis.org/analysis/new-entrants-and-small-business-graduation-market-federal-contracts>
- **[L33]** DoD SBIR/STTR Fast Track. Match mechanism of up to four SBIR/STTR dollars per outside-investor dollar (1:1 to 1:4), contingent on Phase II selection. Verified leverage anchor for A-CP11. <https://www.sbir.gov/tutorials/individual-agency-requirements/DOD-services>

---

## Maintenance

**Last reviewed:** 2026-06-27 — **consolidated Section A** into a single complexity-tier ladder (A1 Descriptive → A4 Risk/monitoring/prediction) following a holistic overlap/redundancy review. This collapsed the three previously-coexisting sub-structures (the Axis A / Axis B "capability vs. vulnerability" split, the separately-tiered "Supporting DIB questions," and the interleaved A-CP1–A-CP9 choke-point extensions) and folded in the former **Section G** (Industrial-base resilience), which was removed as a standalone policy area because its audience and content fully overlapped Section A. Each question now appears once at its highest tier; the capability/vulnerability distinction is preserved as inline **(cap)** / **(vuln)** tags and per-question answerability labels; the choke-point questions retain their `A-CP#` identifiers inline so prior references resolve. Fixes the prior `A1–A4` / `B1–B4` label collision (Axis B's `B1–B4` had clashed with Section B). The out-of-scope physical / sub-tier supply-chain questions (former B4 + Section G's G3 list) are merged into one **Out of scope** appendix at the end of Section A. De-duplicated the foundational SBIR-identification and patent-flow bullets out of Section A (they live at E1 / C2). No questions were dropped and no citations changed; the choke-point citation set (L27–L33, GAO-24-106398/L14 reuse) and the open `[TODO: verify]` items below carry over from the prior choke-point addition.

**Open [TODO: verify] items from the choke-point set (resolve before relying on the figures):**

- **A-CP11 / NSF ~18:1 portfolio leverage** — the ~18:1 private-to-public figure was found only in trade press, not confirmed against an NSF publication (NSF primary pages returned 403 during the review; a separate NSF page cites "$6.5B private investment since 2015," which does not reconcile). Marked `[TODO: verify]` inline and **not stated as fact**. The DoD Fast Track 1:4 anchor [L33] is verified.
- **A3 / "4:1 NASEM" multiplier attribution** — the existing A3 (Inferential — DoD follow-on funding multiplier) "~4:1" figure and its NASEM attribution [L1][L2] were left untouched in this pass per scope. `[TODO: verify A3 4:1 attribution against NASEM source]` before the next citation audit relies on it.

When this doc is reviewed next, the audit should cover:

- All `*(PR #...)*` references resolve to merged or otherwise tracked PRs (closed-without-merge PRs need explicit successor links — PR #311 → #321 was the prior failure mode)
- All `*(branch: ...)*` tags point at branches that still exist on origin (`claude/sbir-data-imputation-strategy` was the prior failure mode — branch deleted, work landed under a different name)
- Internal links to `../specs/` and `docs/` directories resolve
- Each "deps:" tag accurately reflects current pipeline structure (M&A signals are script-driven, not orchestrated — flagged in the M&A implementation note under Section A → A4)
- Coverage gaps: cross-reference recent merged feature PRs against the question inventory to surface work not yet documented here
- CET taxonomy consistency: the canonical spine is the 21-area `NSTC-2025Q1` set (`config/cet/taxonomy.yaml`, validated by `taxonomy_loader.py`). Two divergent code-level taxonomies remain unreconciled — a 10-area transition-system set (`docs/transition/cet-integration.md`, code in transition CET inference) and a 19-area hardcoded reporting set (`sbir_etl/utils/reporting/analyzers/cet_analyzer.py`). Reconciling these to the 21-area spine is a code change with test/precision-benchmark risk and should be scoped separately.

Update this footer with the new review date when the audit completes.

