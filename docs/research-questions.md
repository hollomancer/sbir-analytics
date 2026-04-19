# Research Questions Inventory

The SBIR ETL pipeline is designed to answer a broad set of questions about the
SBIR/STTR program. Questions are grouped by theme; each links to the spec, doc,
or feature branch where the methodology lives. Items marked *(branch: …)* are
in-progress on a feature branch and not yet merged to `main`.

## Transitions & commercialization

- Did this SBIR-funded research result in a federal contract? — [transition/overview.md](transition/overview.md)
- Which SBIR-funded companies transitioned research into federal procurements? — [transition/detection-algorithm.md](transition/detection-algorithm.md)
- What is the transition effectiveness rate by CET area, agency, and firm size?
- What is the average time from award to transition by technology area?
- Which SBIR awards transitioned with patent backing, and what share of transitions are patent-enabled?
- Do firms show higher transition rates within the same awarding agency (agency continuity signal)?
- Which companies are consistent repeat performers across multiple awards? — [queries/transition-queries.md](queries/transition-queries.md)

## Phase II → Phase III latency

- What is the elapsed time between Phase II completion and first Phase III contract? — [phase-transition-latency.md](phase-transition-latency.md)
- What is the Phase II → Phase III survival probability by agency, firm size, and vintage?
- Does Phase II → Phase III latency vary by technology area?
- How much undercount exists in Phase III coding by agency (data-quality caveat)?

## DOD leverage ratio & follow-on funding

- What is the aggregate leverage ratio (non-SBIR DOD obligations ÷ SBIR/STTR obligations) for DOD SBIR firms? Does it reproduce NASEM's ~4:1? — [../specs/leverage-ratio-analysis/](../specs/leverage-ratio-analysis/)
- How does the leverage ratio stratify by award vintage, firm size, technology area, and firm experience (new vs. repeat)?
- What is the leverage ratio for civilian agencies (e.g., DOE)?
- How is the leverage ratio changing over time?
- What are match rates and entity-resolution coverage for reconciliation to NASEM?

## Patent linkage & knowledge spillover

- What is the marginal cost per patent by agency (award $ ÷ linked patents)? Does it match NIH's ~$1.5M benchmark? — [../specs/patent-cost-spillover/](../specs/patent-cost-spillover/)
- What is the spillover multiplier (non-SBIR patent citations to SBIR patents)? Does it match DOE's 3× benchmark?
- How do patent cost and spillover vary by technology area, firm size, and vintage?
- Which USPTO patents are linked to specific SBIR awards, and with what confidence? — [transition/vendor-matching.md](transition/vendor-matching.md)
- Which patents are semantically similar to specific SBIR awards (ModernBERT-Embed)? — [../specs/paecter_analysis_layer/](../specs/paecter_analysis_layer/)
- Can assignment chains show SBIR patent flow through prime contractors?

## Cross-agency technology taxonomy (CET)

- What is the federal SBIR portfolio composition across all 11 agencies by technology area? — [../specs/cross-agency-taxonomy/](../specs/cross-agency-taxonomy/)
- Which CET areas are funded by multiple agencies? Which are single-agency dominated (concentration risk)?
- How does the SBIR technology mix shift over time by agency?
- Which SBIR awards align with each CET area, and with what calibrated probability? — [ml/cet-classifier.md](ml/cet-classifier.md)
- Do SBIR awards and resulting contracts share the same technology focus (CET alignment signal)?

## Fiscal returns & Treasury ROI

- What are federal fiscal returns (tax receipts) from SBIR program spending? — [fiscal/](fiscal/)
- What is the payback period for Treasury investment recovery?
- How do fiscal returns stratify by state and NAICS sector?
- What are employment, wage, proprietor-income, and production impacts by award?
- Which NAICS sectors show the highest fiscal return multipliers?
- How robust are fiscal return estimates to parameter uncertainty (sensitivity bands)?

## Company categorization & performance

- Is this SBIR company primarily a product, service, or mixed-mode firm (based on full federal contract portfolio)? — [../specs/company-categorization/](../specs/company-categorization/)
- What percentage of a company's revenue comes from product vs. service contracts?
- How does company categorization relate to transition likelihood?
- Which SBIR companies show the highest transition success rate?

## Entity resolution & SBIR identification

- Is this SBIR recipient the same entity that won the federal contract? (UEI → CAGE → DUNS → fuzzy-name cascade) — [transition/vendor-matching.md](transition/vendor-matching.md)
- What is the entity-resolution match rate, and what fraction is exact vs. fuzzy?
- Have companies undergone acquisitions or rebrandings that break matching?
- Which federal awards are SBIR/STTR vs. non-SBIR, and with what confidence? — [sbir-identification-methodology.md](sbir-identification-methodology.md)
- What are false-positive rates for shared-ALN grant identification (e.g., NIH)?

## M&A & corporate-event detection

- Did an SBIR-funded company undergo merger or acquisition activity? — [../specs/merger_acquisition_detection/](../specs/merger_acquisition_detection/)
- How does M&A activity affect transition pathways?
- Can SEC EDGAR filings enrich SBIR company financial profiles (revenue, R&D, net income, assets)? *(branch: claude/integrate-sec-edgar-sbir)*
- For SBIR firms acquired by public companies, can inbound M&A be detected via 8-K full-text search? *(branch: claude/integrate-sec-edgar-sbir)*

## Continuous monitoring & rolling analytics

- What are current-quarter SBIR metrics and trends (weekly snapshots)? — [research-plan-alignment.md](research-plan-alignment.md)
- How have transition rates, patent output, and fiscal returns changed quarter-over-quarter?
- Which agencies are under-performing on transitions vs. historical baseline?
- What are forward-looking transition probabilities for Phase II awards nearing completion?

## Data imputation & coverage *(branch: claude/sbir-data-imputation-strategy)*

- Why is `award_date` missing on ~50% of records, and can it be recovered non-destructively? — `specs/data-imputation/` *(branch)*
- For each imputable field (award date, amount, contract dates, NAICS, identifiers), which methods are available and at what confidence?
- What is per-method backtest accuracy / MAE against ground-truth holdouts?
- Does the phase-transition precision benchmark remain ≥85% when imputed values are included?
- Can solicitation topics be mapped to NAICS (agency-topic crosswalk accuracy ≥75%)?
- Which downstream consumers (Neo4j, CET, transition detection) should use raw vs. effective values?

## External data source evaluation *(branch: claude/procurement-data-sources-eval)*

- Does SAM.gov Entity Extracts materially improve UEI backfill recall? — `specs/procurement-data-sources-eval/` *(branch)*
- Does the SAM.gov Opportunities API replace agency-page scraping for solicitation ceilings and periods of performance?
- Does FSCPSC NAICS prediction beat our abstract-nearest-neighbor baseline?
- Does the PSC Selection Tool provide the NAICS ↔ PSC crosswalk needed for topic-derived NAICS?
- Do DIIG CSIS lookup tables feed our NAICS hierarchy or agency normalization?
- Should we adopt third-party procurement-tools clients (e.g., `makegov/procurement-tools`, `tandemgov/fpds`)? — `docs/decisions/procurement-tools-evaluation.md` *(branch)*

## Data quality & completeness

- What percentage of awards have valid NAICS codes, and what is the fallback usage rate?
- How many awards lack UEI/DUNS identifiers?
- What is the data-freshness lag for SBIR.gov, USAspending, USPTO, and BEA I-O sources?
- Which awards have missing or null critical fields (amount, dates, recipient)?
- How does SBIR.gov data reconcile with federal USAspending/FPDS records?
