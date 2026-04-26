# Research Questions Inventory

The SBIR ETL pipeline is designed to answer a broad set of questions about the
SBIR/STTR program. Questions are organized by **policy area** (what audience /
statutory goal the answer serves), then within each area by **complexity tier**
(descriptive → relational → inferential → predictive), with **dependency order**
respected so foundational work appears before dependents.

**Policy areas:**

- [A. National security & defense industrial base](#a-national-security--defense-industrial-base)
- [B. Technology commercialization & entrepreneurship](#b-technology-commercialization--entrepreneurship)
- [C. Innovation & knowledge generation (R&D policy)](#c-innovation--knowledge-generation-rd-policy)
- [D. Economic & fiscal impact](#d-economic--fiscal-impact)
- [E. Program management & data infrastructure](#e-program-management--data-infrastructure)

**Dependency tags** used in parentheses after each question:

- `ER` — entity resolution (UEI/CAGE/DUNS/fuzzy-name cascade)
- `ID` — SBIR/STTR identification classifier
- `CET` — CET technology classifier
- `PATLINK` — patent-to-award linkage
- `IMP` — imputed fields for missing data

Items marked *(branch: …)* are in-progress on a feature branch and not yet
merged to `main`. Public-study citations appear as `[L#]` — see
[Prior literature & benchmarks](#prior-literature--benchmarks) at the bottom.

## A. National security & defense industrial base

*Audience: DoD acquisition leadership, congressional defense committees, CSIS-style industrial-base analysts.*

### A1. Descriptive (Tier 1)

- Portfolio composition by DoD component (Army/Navy/AF/DARPA/DLA), phase, and vintage — SBA annual reports [L18]. *(deps: —)*
- Which CET areas are single-agency-dominated vs. multi-agency, surfacing concentration risk for defense-critical tech — CSIS Center for the Industrial Base [L16]. *(deps: CET)*

### A2. Relational (Tier 2)

- Which federal awards are SBIR/STTR vs. non-SBIR, and with what confidence? — [sbir-identification-methodology.md](sbir-identification-methodology.md). CRS R43695 [L15]. *(deps: ID)*
- Do firms show higher transition rates within the same awarding agency (agency continuity signal)? *(deps: ER, ID)*
- Can assignment chains show SBIR patent flow through prime contractors? Aligns with NASEM's "knowledge transfer to primes" finding [L1]. *(deps: ER, PATLINK)*

### A3. Inferential (Tier 3)

- What is the aggregate leverage ratio (non-SBIR DoD obligations ÷ SBIR/STTR obligations) for DoD SBIR firms? **Target: reproduce NASEM's ~4:1 for 2012–2020** [L1][L2] — [../specs/leverage-ratio-analysis/](../specs/leverage-ratio-analysis/). *(deps: ER, ID)*
- How does the leverage ratio stratify by award vintage, firm size, technology area, and firm experience (new vs. repeat)? NASEM reports SBIR firms = ~1/3 of DoD's extramural R&D base [L1]. *(deps: ER, ID, CET)*
- How is the leverage ratio changing over time? *(deps: ER, ID)*
- What is the leverage ratio for civilian agencies (e.g., DOE)? Myers & Lanahan [L9] and NASEM DOE [L5] supply baselines. *(deps: ER, ID)*

### A4. Risk & monitoring (Tier 4)

**M&A exit detection (foreign-acquisition + ownership-change risk):**

- Did an SBIR-funded company undergo M&A activity? Foreign-acquisition risk flagged by CSIS [L17] — [../specs/merger_acquisition_detection/](../specs/merger_acquisition_detection/). *(deps: ER)*
- For SBIR firms acquired by public companies, can inbound M&A be detected via 8-K full-text search? *(branch: claude/integrate-sec-edgar-sbir)* *(deps: ER)*
- What is the SBIR-firm M&A exit rate, and how does it stratify by funding agency (e.g., HHS biotech vs. DoD defense)? *(deps: ER, M&A signals)*
- What is the median time from first SBIR award to M&A exit? *(deps: ER, M&A signals)*
- Which acquirers concentrate SBIR-firm acquisitions (defense primes vs. life-sciences consolidators), and what fraction are serial acquirers (3+ targets)? *(deps: ER, M&A signals)*
- How does M&A activity affect transition pathways? *(deps: ER, transitions)*

**Private capital signals (SBIR firms' non-federal funding posture):**

- What is the Form D [L23] private-placement fundraising profile of SBIR awardees, and how does it compare to SBIR funding (private-to-SBIR leverage ratio)? *(branch: claude/integrate-sec-edgar-sbir)* *(deps: ER, SEC EDGAR)*
- What is the debt-vs-equity composition and offering fill rate of SBIR-firm Form D filings? *(deps: ER, SEC EDGAR)*

## B. Technology commercialization & entrepreneurship

*Audience: SBA oversight, agency program offices, awardee firms. Core statutory goal is Phase III commercialization.*

### B1. Descriptive (Tier 1)

- Is this SBIR company primarily a product, service, or mixed-mode firm (based on full federal contract portfolio)? — [../specs/company-categorization/](../specs/company-categorization/). *(deps: ER)*
- What percentage of a company's revenue comes from product vs. service contracts? *(deps: ER)*
- Which SBIR companies show the highest transition success rate, and which are consistent repeat performers? — [queries/transition-queries.md](queries/transition-queries.md). Lerner [L10] found growth concentrated in high-VC zip codes. *(deps: ER)*

### B2. Relational (Tier 2)

- Did this SBIR-funded research result in a federal contract? — [transition/overview.md](transition/overview.md). Baselines: NASEM DoD [L1][L2], NIH/NSF ~50% commercialization [L3][L4][L6]. *(deps: ER, ID)*
- Which SBIR-funded companies transitioned research into federal procurements? — [transition/detection-algorithm.md](transition/detection-algorithm.md). *(deps: ER, ID)*
- What is the average time from award to transition by technology area? *(deps: ER, ID, CET)*
- Which SBIR awards transitioned with patent backing, and what share of transitions are patent-enabled? Related to Lerner [L10] and Howell [L11]. *(deps: ER, ID, PATLINK)*

### B3. Inferential (Tier 3)

- What is the elapsed time between Phase II completion and first Phase III contract? — [phase-transition-latency.md](phase-transition-latency.md). GAO flagged Phase III data as limited/unreliable [L14]; SBA ran the Commercialization Benchmark once (2014) for the same reason [L14]. *(deps: ER, ID)*
- Phase II → III survival probability by agency, firm size, and vintage. *(deps: ER, ID)*
- Does Phase II → III latency vary by technology area? *(deps: ER, ID, CET)*
- Transition effectiveness rate by CET area, agency, and firm size — compare to Link & Scott [L12] and NASEM [L1][L3][L4]. *(deps: ER, ID, CET)*
- How much undercount exists in Phase III coding by agency? Corroborated by GAO [L14] and NASEM [L1][L3]. *(deps: ID)*
- How does company categorization relate to transition likelihood? Baseline: Link & Scott commercialization-probability econometrics [L12]. *(deps: ER, ID)*

### B4. Predictive (Tier 4)

- Forward-looking transition probabilities for Phase II awards nearing completion. *(deps: all of B1–B3)*

## C. Innovation & knowledge generation (R&D policy)

*Audience: OSTP, agency R&D directors, innovation researchers. Does federal SBIR spending produce measurable new knowledge?*

### C1. Descriptive (Tier 1)

- Federal SBIR portfolio composition across all 11 agencies by technology area — [../specs/cross-agency-taxonomy/](../specs/cross-agency-taxonomy/). CSIS [L16]. *(deps: CET)*
- Which CET areas are funded by multiple agencies? Cross-agency overlap. *(deps: CET)*
- How does the SBIR technology mix shift over time by agency? SBA [L18]. *(deps: CET)*
- Which SBIR awards align with each CET area, and with what calibrated probability? — [ml/cet-classifier.md](ml/cet-classifier.md). *(deps: —)*

### C2. Relational (Tier 2)

- Which USPTO patents are linked to specific SBIR awards, and with what confidence? — [transition/vendor-matching.md](transition/vendor-matching.md). Parallels Jaffe-Trajtenberg-Henderson [L13]. *(deps: ER)*
- Which patents are semantically similar to specific SBIR awards (ModernBERT-Embed)? — [../specs/paecter_analysis_layer/](../specs/paecter_analysis_layer/). *(deps: PATLINK)*
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

### D2. Inferential (Tier 2)

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

### E4. Data imputation (Tier 2–3) *(branch: claude/sbir-data-imputation-strategy)*

- Why is `award_date` missing on ~50% of records, and can it be recovered non-destructively? — `specs/data-imputation/` *(branch)*. *(deps: E3)*
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

## Prior literature & benchmarks

Public studies the inventory draws from or benchmarks against.

**NASEM reviews (congressionally mandated):**

- **[L1]** NASEM (2024). *Review of the SBIR and STTR Programs at the Department of Defense.* Key finding: DoD SBIR firms attract >4× non-SBIR DoD funding per SBIR dollar (2012–2020); SBIR firms are ~1/3 of the defense R&D base. <https://www.nationalacademies.org/projects/PGA-STEP-17-08/publication/29329>
- **[L2]** NASEM (2014). *SBIR at the Department of Defense.* Earlier assessment — baseline for longitudinal comparison. <https://nap.nationalacademies.org/read/18821/>
- **[L3]** NASEM (2022). *Assessment of the SBIR and STTR Programs at the NIH.* <https://nap.nationalacademies.org/read/26376/>
- **[L4]** NASEM (2022). *Review of the SBIR and STTR Programs at the National Science Foundation.* <https://nap.nationalacademies.org/read/26884/>
- **[L5]** NASEM (2020). *Review of the SBIR and STTR Programs at the Department of Energy.* Draws on Myers & Lanahan spillover work. <https://nap.nationalacademies.org/read/25674/>
- **[L6]** NASEM (2016). *SBIR/STTR at the National Institutes of Health.* <https://www.ncbi.nlm.nih.gov/books/NBK338158/>
- **[L7]** NASEM (2016). *STTR: An Assessment of the Small Business Technology Transfer Program.* <https://www.ncbi.nlm.nih.gov/books/NBK338709/>
- **[L8]** NASEM. *Capitalizing on Science, Technology, and Innovation: An Assessment of the SBIR Program — Phase II.* <https://www.nationalacademies.org/our-work/capitalizing-on-science-technology-and-innovation-an-assessment-of-the-small-business-innovation-research-program---phase-ii>

**Peer-reviewed academic studies:**

- **[L9]** Myers, K. & Lanahan, L. (2022). "Estimating Spillovers from Publicly Funded R&D: Evidence from the US Department of Energy." *American Economic Review.* Finding: ~3× spillover multiplier; ~60% of spillovers retained in U.S. <https://www.aeaweb.org/articles?id=10.1257/aer.20210678>
- **[L10]** Lerner, J. (1999). "The Government as Venture Capitalist: The Long-Run Impact of the SBIR Program." *Journal of Business* 72(3), 285–318. Finding: SBIR awardees grew faster over 10 years; effect concentrated in VC-rich zip codes. NBER w5753. <https://www.nber.org/papers/w5753>
- **[L11]** Howell, S.T. (2017). "Financing Innovation: Evidence from R&D Grants." *American Economic Review* 107(4), 1136–64. Finding: early-stage DOE SBIR grant roughly doubles probability of subsequent VC; large positive effects on patenting and revenue. <https://www.aeaweb.org/articles?id=10.1257/aer.20150808>
- **[L12]** Link, A.N. & Scott, J.T. (2010, 2012). "Government as Entrepreneur: Evaluating the Commercialization Success of SBIR Projects" and related work. Econometric commercialization-probability models using the NRC SBIR database.
- **[L13]** Jaffe, A., Trajtenberg, M., & Henderson, R. (1993). "Geographic Localization of Knowledge Spillovers as Evidenced by Patent Citations." *Quarterly Journal of Economics.* Methodological foundation for citation-based spillover measurement.

**Government & policy reports:**

- **[L14]** GAO-24-107036 (2024). *Small Business Research Programs: Increased Performance Standards Likely to Require Better Data.* Documents Phase III data limitations and the single (2014) Commercialization Benchmark run. <https://www.gao.gov/assets/gao-24-107036.pdf>
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
