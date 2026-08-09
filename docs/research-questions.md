# Research Questions Inventory

This is the canonical list of what the SBIR ETL pipeline exists to answer.

Questions are grouped by **policy area** (which audience or statutory goal the
answer serves), then by **complexity tier** (descriptive → relational →
inferential → predictive). Within a tier, foundational work comes before the
work that depends on it.

**Policy areas:**

- [A. National security, industrial base, and supply chain](#a-national-security-industrial-base-and-supply-chain)
- [B. Technology commercialization & entrepreneurship](#b-technology-commercialization--entrepreneurship)
- [C. Innovation & knowledge generation (R&D policy)](#c-innovation--knowledge-generation-rd-policy)
- [D. Economic & fiscal impact](#d-economic--fiscal-impact)
- [E. Program management & data infrastructure](#e-program-management--data-infrastructure)
- [F. Capital formation & entrepreneurial finance](#f-capital-formation--entrepreneurial-finance)

## How to read this document

Each question is written in a fixed shape:

```text
- **Short title** (lens tags, legacy IDs)
  The question itself, as a question.
  Caveat — a stated limit on what the answer can support, when one applies.
  Status: whether it is computable, validated, or citable today.
  Deps / Refs / Spec: what it needs, what it benchmarks against, where it is specified.
```

The **title**, **question**, and **Status** slots are written for an outside
reader — a congressional staffer or program officer who arrived from
[Where to start, by audience](#where-to-start-by-audience). Keep them in plain
language. The *Deps*, *Spec*, and implementation notes are for maintainers and
may use pipeline shorthand freely.

**Status** appears where implementation or evidence maturity needs explanation.
`Computable` means the repository can produce a bounded result; it does not mean
the interpretation is validated or externally citable. `Validated` and
`citable` require a matching [study contract](../studies/README.md) at that
status. A question with no status line is an inventory target, not an implicit
claim that it is implemented.

**Lower-bound proxy** marks a question whose answer can only ever undercount.
It appears wherever we detect ownership or capital through public filings: SEC
EDGAR shows disclosed, structured ownership and disclosed private capital, so
anything held privately or beneath a corporate layer is invisible to us. A
"zero" on such a question means *we found none*, never *there are none*.

**Spec** links point at tracked spec directories and design documents. A
`(PR #…)` tag records where work landed. Unmerged branch-only proposals are not
treated as current specs; retain them in git history or a dated research note.

**Refs** are public studies and statutes, cited as `[L#]` and listed under
[Prior literature & benchmarks](#prior-literature--benchmarks).

**Deps** are the pipeline capabilities a question needs before it can be answered:

| Tag | Meaning |
|-----|---------|
| `ER` | Entity resolution (UEI/CAGE/DUNS/fuzzy-name cascade) |
| `ID` | SBIR/STTR identification classifier |
| `CET` | CET technology classifier |
| `PATLINK` | Patent-to-award linkage |
| `IMP` | Imputed fields for missing data |
| `M&A signals` | M&A event detection (8-K/Form D parsing, ownership-change signals) |
| `SEC EDGAR` | SEC EDGAR filings (Form D Reg D, Form 8-K) for SBIR-firm transactions |
| `UCC-1` | UCC-1 financing statements (state secured-debt registries; separates equipment finance, depository-bank loans, and venture debt) |
| `NAICS` | Industry classification derived from NAICS codes |
| `fiscal model` | Fiscal-impact modeling inputs and assumptions |
| `BEA I-O` | BEA input-output tables for economic-impact estimation |
| `transitions` | Commercialization / phase-transition outcome definitions |
| `NIPA rate provider` | BEA NIPA-derived effective tax rates (Tables 3.2/3.3) |
| `state rate provider` | State-specific effective tax rates for jurisdiction decomposition |

## Where to start, by audience

Every pointer below lands in a section that mixes implemented and spec-only
work. Use the per-question *Status* and *Spec* slots to tell what is answerable
today from what is still a research target.

- **Policymakers** — Congress, OMB, agency leadership, congressional defense
  committees. Start with the **DoD follow-on funding multiplier** ([A3](#a3-inferential-tier-3);
  reproduces NASEM's ~4:1 benchmark, which NASEM calls the *leverage ratio*),
  then **[D2](#d2-relational-tier-2)** (Treasury ROI and tax receipts from SBIR
  spending) and **[F3](#f3-inferential-tier-3)** (private-to-SBIR leverage, the
  private-side mirror of the DoD multiplier).
- **SBIR program managers** — NSF, NIH, DoD, DOE, SBA program offices. Start
  with **[B](#b-technology-commercialization--entrepreneurship)** (transitions,
  Phase II→III latency, company performance), **[C1](#c1-descriptive-tier-1)**
  (cross-agency CET portfolio composition), and **[E6](#e6-continuous-monitoring--rolling-analytics-tier-4-capstone)**
  (rolling quarterly snapshots).
- **Investors** — VC, PE, angels, family offices, corporate VC. Start with
  **[F1](#f1-descriptive-tier-1)** (Form D fundraising profile, M&A exit rate by
  funding agency, capital-event timeline) and **[F2](#f2-relational-tier-2)**
  (cohort outcomes vs. published VC/PE baselines, acquirer-type concentration).
- **OSTP / congressional oversight** — OSTP, armed-services, science, and
  small-business committees. Start with the **choke-point fragility watchlist**
  ([A4](#a4-risk-monitoring--prediction-tier-4), A-CP13 — the flagship composite)
  and the **capability density & choke-point concentration map**
  ([A1](#a1-descriptive-tier-1), A-CP1/A-CP2/A-CP3). Note that the choke-point
  questions are research targets, not yet scoped or implemented.

## A. National security, industrial base, and supply chain

*Audience: DoD acquisition leadership, congressional defense / armed-services
committees, OSTP, congressional science / small-business committees, CSIS-style
industrial-base analysts.*

<a id="the-master-question-industrial-capability-vs-vulnerability"></a>

**Master question:** Across the CET areas, where does SBIR/STTR build domestic
industrial capability that strengthens the defense industrial base, and where
are awardees exposed to adversary ownership/control or capability concentration
that creates vulnerability?

Two lenses run through every tier. Questions are tagged for the lens they read:

- **(cap)** — capability. Does SBIR/STTR build domestic industrial capability?
- **(vuln)** — vulnerability. Are awardees exposed to adversary control or to
  capability concentration?
- **(cap/vuln)** — the question reads both.

Award data answers the capability side well and the vulnerability side only
weakly, so each question carries its own status and the strong capability
metrics are not allowed to lend confidence to the weak vulnerability inferences.
Choke-point questions keep their original `A-CP#` identifiers so prior
references still resolve. Physical and sub-tier supply-chain questions that
award data cannot answer are listed in
[Out of scope](#out-of-scope--physical--sub-tier-supply-chain) rather than
graded as metrics.

Background on the CET taxonomy and the statutory basis for both lenses is in
[Section A framing notes](#section-a-framing-notes) at the end of the section.

For SBIR-firm capital structure and exit analysis from an entrepreneurial-finance
perspective, see [F. Capital formation & entrepreneurial finance](#f-capital-formation--entrepreneurial-finance).

### A1. Descriptive (Tier 1)

- **Portfolio composition by DoD component**
  How do DoD SBIR awards break down by component (Army, Navy, Air Force, DARPA,
  DLA), phase, and vintage?
  *Deps: none · Refs: [L18]*

- **Supplier base size and concentration per CET area** (cap/vuln) (A-CP1 concentration map, A-CP2 supplier-base thickness, A-CP3 geographic distribution)
  In each CET area, how many distinct firms hold awards, how much award money do
  they hold, and how much of that money is concentrated in a few of them —
  measured by **HHI** (the Herfindahl-Hirschman Index, the standard antitrust
  measure of market concentration; higher means award dollars are concentrated
  among fewer or larger firms) and broken out by NAICS sector and by geography
  (state, congressional district)?
  More independent awardees suggest a broader in-program supplier base. Fewer
  awardees and a higher HHI flag potential concentration for review; these
  award-data signals do not by themselves establish supplier health or a
  physical choke point. The geographic view also flags areas whose suppliers
  are clustered in one part of the country. GAO's program-wide Phase II HHI of
  ~11 [L14] is the diffuse baseline that area-level concentration is measured
  against.
  **Status:** Computable for the classified DoD subset; not yet backed by a citable study manifest.
  *Deps: CET, ER, NAICS · Refs: [L14], [L16], [L29] · Spec: [dod_supply_chain_initial_analysis.md](research/dod_supply_chain_initial_analysis.md) (reproducible baseline and its limitations)*

- **Coverage gaps** (cap) (house shorthand: *whitespace*)
  Which CET subfields does DoD appear to want work in, but few SBIR awards
  cover?
  Found by semantic search over award and solicitation text.
  **Status:** Partially computable as an exploratory analysis. The SBIR.gov bulk
  award snapshot supplies exact solicitation/topic identifiers for 49.1% of all
  award rows and 99.9% of NSF award rows from 2022 onward, but it does not supply
  solicitation or attachment text. Results remain source-coverage bounded and
  are not yet validated as requirement evidence.
  *Deps: CET · Plan: [solicitation document evidence](research/solicitation_document_evidence_plan.md) · Evidence: [bulk linkage coverage](research/solicitation_source_coverage_status.md)*

- **Capital formation / firm health per CET area** (cap)
  How healthy are awardees financially in each technology area, proxied by Form D
  raises and follow-on funding? (The defense-CET slice of [F1](#f1-descriptive-tier-1).)
  **Status:** Partial — SEC/Form D filers only.
  *Deps: ER, CET, SEC EDGAR*

- **Foreign ownership / control (FOCI) exposure per CET area** (vuln) (A-CP4)
  What share of awardees — and of award dollars — in each CET area sit under
  disclosed foreign ownership, control, or influence, when screened against the
  eight Pub. L. 119-83 restricted-entity lists?
  *Lower-bound proxy* — ownership is read from EDGAR Exhibit 21 and 8-K filings.
  **Status:** Computable for the SEC-filer subset; the private majority needs
  data acquisition.
  *Deps: ER, SEC EDGAR, M&A signals · Refs: [L26] (screening lists), [L30] (foreign-supplier dependence), [L17] (foreign-acquisition risk)*

### A2. Relational (Tier 2)

- **Agency continuity signal**
  Do firms show higher transition rates within the same awarding agency?
  *Deps: ER, ID*

- **Observed SBIR-to-prime supply network** (cap/vuln)
  Which current and former NSF SBIR/STTR awardees receive DoD funding as prime
  recipients or reported first-tier subcontractors, by instrument and fiscal
  year; which DoD award relationships persist; and which directly sourced NSF
  award texts merit CET-based critical-supply-chain review? Direct NSF records
  supply authoritative performance dates. USAspending FPDS/FABS transactions
  supply signed prime procurement, assistance, and other-transaction flows;
  SAM.gov/FSRS supplies reported subawards. UEI/DUNS edges enter verified totals
  and name-only matches remain candidates. The graph keeps NSF awards, legal
  entities, DoD awards, agencies, and CET areas distinct. It does not infer that
  NSF-funded work was used on a DoD award or that a supplier is critical or
  irreplaceable. DoD-14/NDIS-8 policy mapping remains deferred, and FOCI is not
  in this analysis.
  **Status:** Computable as a manifest-pinned public-data lower bound with
  signed prime/subaward ledgers, evidence tables, quality gates, and an analyst
  graph; not a BoM or dependency claim.
  *Deps: ER, direct NSF awards, USAspending FPDS/FABS, USAspending subawards, CET · Spec: [nsf_sbir_defense_funding_plan.md](research/nsf_sbir_defense_funding_plan.md)*

- **DIB integration** (cap)
  What is the Phase II→III transition rate per CET area via FPDS, and how do
  SAM.gov subaward links connect awardees to prime contractors?
  Aligns with NASEM's "knowledge transfer to primes" finding [L1].
  **Status:** Computable with moderate confidence — FPDS Phase III tagging is
  historically incomplete [L14].
  *Deps: ER, ID, CET, transitions · Refs: [L1], [L14] · Spec: [../specs/ot-consortium-subaward-attribution/](../specs/ot-consortium-subaward-attribution/) (FFATA/FSRS sub-award T1 recovery)*

- **Awardees that control the key patents** (cap/vuln) (A-CP6)
  Within a CET area, do patent assignment chains (`ASSIGNED_VIA/FROM/TO`) show a
  handful of awardees supplying most of the patents that primes go on to rely on
  — a choke point in knowledge rather than in manufacturing?
  Builds on the [C2](#c2-relational-tier-2) patent-linkage work. The
  citation-centrality "who-depends-on-whom" variant needs patent-citation edge
  ingestion; a `PatentCitation` model exists but citations are not yet graph
  relationships.
  **Status:** Partial — the assignment-chain lens is buildable now;
  citation-centrality needs ingestion.
  *Deps: ER, PATLINK, CET · Refs: [L1]*

- **Adversary-affiliation screening** (vuln)
  Do awardees or their key personnel resolve to entities on the named
  restricted-entity lists, or to foreign countries of concern?
  **Status:** Partial via public lists; full coverage needs agency-held
  due-diligence data.
  *Deps: ER*

- **Concentrated areas that also fail to graduate firms** (vuln) (A-CP5)
  Do the CET areas served by the fewest firms also have the fewest firms
  reaching Phase III — few suppliers *and* no pipeline replacing them?
  *Caveat:* the FPDS Phase III undercount [L14] bounds confidence.
  **Status:** Research target — not yet scoped.
  *Deps: ER, ID, CET, transitions · Refs: [L14]*

- **New-entrant vs. repeat-winner mix per CET area** (vuln) (A-CP7)
  What share of awards in each CET area go to first-time winners versus repeat
  winners — that is, are new firms still entering the program, and do they go on
  to win again?
  The DoD classified-subset baseline reports first-observed entrants against the
  complete retained FY2012+ DoD award history. It cannot see earlier activity, so
  a firm that first won in 2009 can still look like a new entrant
  (*left-censoring*).
  **Status:** Partially computable for the classified DoD subset.
  *Deps: ER, ID, CET · Refs: [L32] · Spec: [dod_supply_chain_initial_analysis.md](research/dod_supply_chain_initial_analysis.md)*

*The SBIR-vs-non-SBIR identification question and the underlying patent-to-award
linkage are foundational and live at their canonical homes —
see [E1](#e1-sbir-identification-foundation-tier-12) and
[C2](#c2-relational-tier-2) — rather than being restated here.*

### A3. Inferential (Tier 3)

#### DoD follow-on funding multiplier

NASEM calls this quantity the *leverage ratio*.

- **Aggregate multiplier**
  What is the aggregate follow-on funding multiplier — non-SBIR DoD obligations
  ÷ SBIR/STTR obligations — for DoD SBIR firms?
  **Target:** reproduce NASEM's ~4:1 for 2012–2020.
  *Deps: ER, ID · Refs: [L1], [L2] · Spec: [../specs/archive/completed-features/follow-on-multiplier-analysis/](../specs/archive/completed-features/follow-on-multiplier-analysis/), [../specs/archive/completed-features/load-contract-nodes/](../specs/archive/completed-features/load-contract-nodes/) (FPDS contract-node ingestion)*

- **Multiplier stratification**
  How does the multiplier vary by award vintage, firm size, technology area, and
  firm experience (new vs. repeat winner)?
  NASEM reports SBIR firms as ~1/3 of DoD's extramural R&D base [L1].
  *Deps: ER, ID, CET · Refs: [L1]*

- **Multiplier over time**
  How is the multiplier changing over time?
  *Deps: ER, ID*

- **Civilian-agency multiplier**
  What is the multiplier for civilian agencies such as DOE?
  *Deps: ER, ID · Refs: [L9], [L5] (baselines)*

#### Concentration & choke-point inference

- **When concentration becomes fragility** (vuln)
  Where one firm or a handful of firms dominate a CET area, should that be read
  as risk rather than as strength? Has the number of firms serving an area grown
  or shrunk over time, and which single-supplier firms would — if acquired or
  lost — take a capability with them that no other firm in the program can
  supply?
  Same measure as [A1](#a1-descriptive-tier-1), read for risk instead of health,
  and including areas whose suppliers sit in one part of the country.
  *Caveat:* the DoD classified-subset baseline supports concentration screening
  but not physical sole-source conclusions.
  **Status:** Computable for the classified DoD subset; not yet backed by a citable study manifest.
  *Deps: ER, CET · Spec: [dod_supply_chain_initial_analysis.md](research/dod_supply_chain_initial_analysis.md)*

- **Areas fragile on every measure at once** (vuln) (A-CP10)
  Which CET areas are served by few firms, graduating few of them to Phase III,
  *and* attracting few new entrants — all at the same time?
  Combines few suppliers (A-CP1/A-CP2), suppliers clustered in one region
  (A-CP3), few firms reaching Phase III (A-CP5), and few new entrants (A-CP7)
  into a single per-area judgment.
  **Status:** Research target — not yet scoped.
  *Deps: CET, ER, ID, NAICS, transitions · Refs: [L28], [L30]*

- **Program leverage at choke points** (vuln) (A-CP11)
  Narrow the DoD follow-on multiplier and the private-to-SBIR leverage ratio
  ([F3](#f3-inferential-tier-3)) to firms at choke points: do the areas with the
  fewest suppliers attract more follow-on money per SBIR dollar, or less?
  *Lower-bound proxy.*
  *Anchor:* the verifiable DoD SBIR Fast Track match of up to four SBIR dollars
  per outside-investor dollar [L33]. NSF's reported portfolio leverage carries a
  `[TODO: verify NSF primary source for the ~18:1 figure]` — found only in trade
  press, not confirmed against an NSF publication; **do not state as fact until
  verified**.
  **Status:** Research target — not yet scoped.
  *Deps: ER, ID, SEC EDGAR, CET · Refs: [L33]*

- **Firms on a plausible path to foreign acquisition** (vuln) (A-CP12)
  Judging from disclosed ownership structure and past M&A activity, which
  choke-point firms look like plausible foreign acquisition targets when screened
  against the restricted-entity lists?
  *Lower-bound proxy.*
  **Status:** Research target — not yet scoped.
  *Deps: ER, SEC EDGAR, M&A signals, CET · Refs: [L26], [L30]*

### A4. Risk, monitoring & prediction (Tier 4)

#### M&A detection & transition pathways

- **Foreign-acquirer M&A detection**
  Did a defense-funded SBIR company undergo M&A activity, particularly involving
  a foreign acquirer?
  *Deps: ER, M&A signals · Spec: [../specs/archive/completed-features/merger_acquisition_detection/](../specs/archive/completed-features/merger_acquisition_detection/)*

- **Inbound M&A via 8-K full-text search**
  For SBIR firms acquired by public companies, can inbound M&A be detected
  through 8-K full-text search?
  *Deps: ER, SEC EDGAR · Spec: (PR #286)*

- **Acquirer concentration among defense primes**
  Which defense primes concentrate SBIR-firm acquisitions (e.g. Titan, Teledyne,
  Ametek, Kratos), and are any of those acquirers themselves foreign-owned or
  under CFIUS review?
  *Deps: ER, M&A signals*

- **M&A effect on transition pathways**
  How does M&A activity affect Phase III / federal-contract transition pathways?
  *Deps: ER, M&A signals, transitions*

#### Choke-point monitoring & prediction

- **Acquisitions that thin an already-small supplier base** (vuln) (A-CP8)
  Do acquisitions pull sole or dominant suppliers out of CET areas that already
  had few firms, so that consolidation costs the program a capability?
  *Lower-bound proxy* for the foreign-acquisition component.
  **Status:** Research target — not yet scoped.
  *Deps: ER, M&A signals, CET · Refs: [L31] (defense-sector consolidation), [L17] (foreign-acquisition risk)*

- **UCC-1 financial-distress signal** (vuln) (A-CP9)
  Do shifts in UCC-1 secured-debt filing patterns — lapses, new liens, lender
  churn — flag financial distress among choke-point firms ahead of exit or
  capability loss?
  *Caveat:* no external benchmark exists; this is a novel signal.
  **Status:** Research target — not yet scoped.
  *Deps: ER, UCC-1, CET*

- **Choke-point fragility watchlist** (vuln) (A-CP13 — flagship)
  Which CET areas — and which individual sole- or dominant-supplier firms within
  them — would, if acquired or lost, remove a capability with no in-program
  substitute?
  A forward-looking watchlist combining every signal above: few suppliers
  (A-CP1/A-CP2), suppliers clustered in one region (A-CP3), foreign ownership
  (A-CP4), few firms reaching Phase III (A-CP5), position in the IP chain
  (A-CP6), few new entrants (A-CP7), acquisitions thinning the base (A-CP8),
  secured-debt distress (A-CP9), and the combined per-area judgment (A-CP10).
  *Lower-bound proxy* for the foreign-ownership and foreign-acquisition inputs.
  **Status:** Research target — flagship; not yet scoped or implemented.
  *Deps: CET, ER, ID, transitions, M&A signals, UCC-1, SEC EDGAR · Refs: [L28] (NDIS supply-chain resilience), [L31] (priority sectors), [L30] (sub-tier-visibility gap)*

- **Early warning before a supplier is lost** (vuln) (A-CP14)
  How likely is a given choke-point firm to disappear — through acquisition or
  financial failure — within the next few years?
  Feeds the continuous-monitoring loop
  ([E6](#e6-continuous-monitoring--rolling-analytics-tier-4-capstone)) so the
  flag is raised while the capability can still be preserved.
  *Lower-bound proxy* for the foreign-acquisition component.
  **Status:** Research target — not yet scoped.
  *Deps: ER, M&A signals, UCC-1, CET, transitions · Refs: [L30], [L31]*

> **Implementation note — M&A detection is script-driven, not orchestrated.**
> M&A event detection runs as a CLI script
> (`scripts/archive/data/detect_sbir_ma_events.py`), not as a Dagster asset. The
> script merges two signals: Form D filings (entity_type-based
> business-combination heuristics) and an SEC EDGAR full-text mention scan across
> multiple filing types — operationally 8-K, 10-K, DEFM14A, PREM14A, SC TO-T, and
> SC 14D9 (see `scripts/archive/data/refine_ma_medium_tier.py`).
>
> The orchestrated graph has no continuous M&A-event materialization. Rerunning
> the script is how the M&A signal feeding the vulnerability (A1/A3/A4) and
> F-area questions gets refreshed. The former
> `packages/sbir-analytics/sbir_analytics/assets/ma_detection.py` stub was a
> placeholder, never wired into the M&A pipeline, and was removed in PR #317.

<a id="out-of-scope--physical--sub-tier-supply-chain-data-the-project-does-not-ingest"></a>

### Out of scope — physical & sub-tier supply chain

*Reported first-tier subcontract relationships are now an A2 research target.
The questions below remain outside that boundary: they require bill-of-materials,
customs, contractual country-of-origin, production, or supplier-to-supplier data
that federal first-tier subaward records do not expose. They are listed for
visibility, stated explicitly rather than graded as metrics. GAO-25-107283 [L30]
documents this deeper visibility gap.*

- **Physical input chokepoints** — dependence on contested physical inputs (rare
  earths, castings, advanced chips, APIs); sole-source inputs, foreign-content
  percentages, and surge capacity.
- **Tiered BoM / deeper supplier-tier maps** — Tier 3/N relationships below a
  reported first-tier subcontractor, and Tier 2/3/N bill-of-material dependency
  mapping for a CET capability.
- **Critical-mineral dependency** — exposure of a CET area to contested minerals
  and materials (rare earths, gallium, etc.).
- **Allied-supplier substitution** — whether an allied or partner-nation supplier
  could substitute for a domestic choke point.
- **Customs / trade-flow dependency** — import dependence and trade-flow
  chokepoints for inputs to a CET capability.
- **Sub-tier foreign integration** — foreign content or foreign-owned sub-tier
  suppliers buried below the prime/awardee tier.

### Section A framing notes

**Scope consolidation.** This section merges three previously separate framings —
the defense-industrial-base questions, the supply-chain / technology choke-point
set, and the former standalone "industrial-base resilience" section — into one
complexity-tier ladder. They serve the same audience and statutory goal and draw
on the same `CET`, `NAICS`, `ER`, `SEC EDGAR`, and `M&A signals` data.

**CET spine.** The organizing spine is the repo's **21-area `NSTC-2025Q1`**
taxonomy in `config/cet/taxonomy.yaml`.
`packages/sbir-ml/sbir_ml/ml/config/taxonomy_loader.py` expects exactly 21 areas
and logs a warning on any mismatch — a soft check, not a hard-failing
validation.

This is *not* the external 18-area Feb-2024 NSTC Critical and Emerging
Technologies list [L29], nor DoD's 14 Critical Technology Areas. Both are
narrower external frameworks, and the repo's 21-area set already blends NSTC CET
areas with several DoD critical-technology areas (Hypersonics, Directed Energy,
Advanced Gas Turbine Engine Technologies, Integrated Network
Systems-of-Systems).

*Crosswalk note:* DoD-facing outputs would benefit from **DoD-14** and NDIS
supply-chain-priority tags, but no authoritative mapping is materialized in the
repository. Those tags and associated policy prose remain deferred; current
outputs expose the source CET classification and the deferred-mapping status
rather than inventing an **NDIS-8** framework.

Two other, divergent CET taxonomies exist in code — a 10-area transition-system
set and a 19-area reporting-analyzer set — and are not yet reconciled to the
canonical 21. See [Maintenance](#maintenance).

**Statutory grounding.** The vulnerability lens maps to the risk-based
due-diligence factors of the SBIR/STTR reauthorization, **Pub. L. 119-83**
(signed April 13, 2026), and its eight restricted-entity screening lists — the
UFLPA Entity List, the Non-SDN Chinese Military-Industrial Complex Companies
(NS-CMIC) List, the Section 889 Prohibition List, the 1260H list, the Military
End-User (MEU) List, the BIS Entity List, the FCC Covered List, and the CBP
WRO/Findings List [L26]. The FY2026 NDAA [L27] carries related DIB authorities.

The capability lens maps to the same law's Strategic Breakthrough Allocation and
Phase III provisions. The choke-point questions are framed by the DoD National
Defense Industrial Strategy [L28] and the DoD State of Competition report [L31].
(Statutes are linked, not reproduced.)

## B. Technology commercialization & entrepreneurship

*Audience: SBA oversight, agency program offices, awardee firms. The core
statutory goal is Phase III commercialization.*

### B1. Descriptive (Tier 1)

- **Firm mode: product, service, or mixed**
  Is this SBIR company primarily a product, service, or mixed-mode firm, judged
  from its full federal contract portfolio?
  *Deps: ER · Spec: [../specs/company-categorization/](../specs/company-categorization/)*

- **Product vs. service revenue split**
  What percentage of a company's revenue comes from product contracts versus
  service contracts?
  *Deps: ER*

- **Top and repeat transition performers**
  Which SBIR companies show the highest transition success rate, and which are
  consistent repeat performers?
  Lerner [L10] found growth concentrated in high-VC zip codes.
  *Deps: ER · Refs: [L10] · Spec: [queries/transition-queries.md](queries/transition-queries.md)*

### B2. Relational (Tier 2)

- **Award-to-contract transition**
  Did this SBIR-funded research result in a federal contract?
  *Deps: ER, ID · Refs: [L1], [L2] (NASEM DoD), [L12] (Link & Scott, ~50% commercialization probability), [L3], [L4], [L6] (NASEM program reviews) · Spec: [transition/overview.md](transition/overview.md), [../specs/archive/completed-features/transition_detection/](../specs/archive/completed-features/transition_detection/)*

- **Follow-on contracts that were never labelled Phase III**
  When a firm wins a federal contract after its SBIR award ends — the same firm
  by exact UEI, with no Phase III label required — how many of those contracts
  hold up as likely follow-on work? And how does that count shift as we vary the
  matching rules, the agency, and the time window?
  *Method:* the matching rules were written down and frozen before the counts
  were run, so the result cannot be tuned after the fact.
  **Status:** Reproducible and falsification-tested, but not validated or citable,
  for the frozen audit estimand. The complete census, matched negative-control,
  and fixed-seed placebo tables were materialized from provenance-verified
  February inputs. The actual frame exceeds the cross-firm date placebo on every
  final-stage metric and in all six sensitivity cells, so the temporal link changes
  the proxy under the preregistered placebo. Within the limited exact-match common-
  support subset, however, treated and control firm distributions still overlap
  substantially. Hand-labelled validation remains unresolved, so this is an uncoded
  follow-on proxy rather than proof of statutory Phase III.
  *Deps: ER, ID, NAICS/PSC · Spec: [../specs/phase-iii-census/](../specs/phase-iii-census/) · Audits: [February 2026 data-cut materialization](../studies/phase-iii-census/materialization-2026-02-06.md), [matched negative-control outcomes](../studies/phase-iii-census/negative-control-outcomes-2026-08-03.md), [full-census placebo](../studies/phase-iii-census/placebo-results-2026-08-03.md)*

- **Research-to-procurement transitions**
  Which SBIR-funded companies transitioned research into federal procurements?
  *Deps: ER, ID · Spec: [transition/detection-algorithm.md](transition/detection-algorithm.md)*

- **Time to transition by technology area**
  What is the average time from award to transition, by technology area?
  *Deps: ER, ID, CET*

- **Patent-enabled transitions**
  Which SBIR awards transitioned with patent backing, and what share of all
  transitions are patent-enabled?
  *Deps: ER, ID, PATLINK · Refs: [L10], [L11]*

### B3. Inferential (Tier 3)

- **Phase II → III latency**
  What is the elapsed time between Phase II completion and the first Phase III
  contract?
  GAO documents the newer §638(qq)(3) performance-standard framework and notes
  that commercialization progress is measured from multiple SBA data sources
  [L14].
  *Deps: ER, ID · Refs: [L14] · Spec: [phase-transition-latency.md](phase-transition-latency.md)*

- **Phase II → III survival probability**
  What is the probability that a Phase II awardee wins Phase III work within a
  defined follow-up period, and how does it vary by agency, firm size, and award
  vintage?
  Awardees whose follow-up period is not yet complete are still under observation
  (*right-censored*), not counted as failures.
  *Deps: ER, ID*

- **Latency by technology area**
  Does Phase II → III latency vary by technology area?
  *Deps: ER, ID, CET*

- **Transition effectiveness rate**
  What share of awards reach a federal contract, broken out by CET area, agency,
  and firm size — and how does that compare to the published baselines?
  *Deps: ER, ID, CET · Refs: [L12], [L1], [L3], [L4]*

- **How much Phase III work goes unrecorded**
  How many Phase III contracts does each agency fail to code as Phase III?
  Corroborated by GAO [L14] and NASEM [L1], [L3]. The protocol depends on
  award-grade identity and record granularity (issue #447 / PR #449); production
  source lifecycle belongs to issue #442.
  **Status:** Partially computable. The deterministic census, sensitivity
  diagnostic, matched negative-control comparison, and fixed-seed placebo are
  materialized. The placebo does not reproduce the actual final-stage totals, so
  the temporal link contributes to this proxy under the frozen perturbation. The
  controls still show substantial distribution overlap within a narrow common-
  support subset. Before the proxy can be called an undercount, it still needs a
  hand-labelled sample; one cyclic placebo is not labeled validation or an
  inferential permutation distribution.
  *Deps: ID · Refs: [L14], [L1], [L3] · Audits: [February 2026 data-cut census materialization](../studies/phase-iii-census/materialization-2026-02-06.md), [matched negative-control outcomes](../studies/phase-iii-census/negative-control-outcomes-2026-08-03.md), [full-census placebo](../studies/phase-iii-census/placebo-results-2026-08-03.md) · Spec: [../specs/phase3-match-benchmark/](../specs/phase3-match-benchmark/) (protocol and current evidence limits), [../specs/phase-3-solicitation-alerts/](../specs/phase-3-solicitation-alerts/) (solicitation monitoring)*

- **Categorization vs. transition likelihood**
  Are product firms, service firms, or mixed-mode firms (as categorized in
  [B1](#b1-descriptive-tier-1)) more likely to reach a federal contract?
  *Deps: ER, ID · Refs: [L12]*

- **Statutory Commercialization Benchmark**
  Which Phase II awardees subject to §638(qq)(3) Increased Performance Standards
  meet the statutory Commercialization Benchmark — sales plus private investment
  over the 10-FY covered period ÷ SBIR funding ≥ the specified ratio?
  Grounded in Pub. L. 117-183, the SBIR/STTR Extension Act of 2022, §638(qq)(3).
  Implementation on `main`: `scripts/run_benchmark.py` (evaluate / sensitivity /
  company-level CLI) backed by `sbir_etl/models/benchmark_models.py`, with tests
  in `tests/unit/test_benchmark_evaluator.py`.
  *Caveat:* the fuller methodology is committed, but its additional per-firm audit
  infrastructure and FY2026 cohort are not reproducible from this repository — see
  [Output products](#commercialization-benchmark-methodology-historical-not-reproducible).
  *Deps: ER, ID, transitions, SEC EDGAR · Spec: [../specs/archive/completed-features/commercialization-benchmark/](../specs/archive/completed-features/commercialization-benchmark/)*

### B4. Predictive (Tier 4)

- **Forward transition probability**
  What is the forward-looking transition probability for Phase II awards nearing
  completion, and which firms are the top candidates for outreach?
  A per-firm **Phase III prospect digest** builder exists at commit
  [`4470b921`](https://github.com/hollomancer/sbir-analytics/commit/4470b921).
  It is not on `main` — it was developed on a since-removed feature branch, and
  should be re-introduced as needed. Uses B1–B3 features as scoring inputs.
  *Deps: all of B1–B3*

## C. Innovation & knowledge generation (R&D policy)

*Audience: OSTP, agency R&D directors, innovation researchers. Does federal SBIR
spending produce measurable new knowledge?*

### C1. Descriptive (Tier 1)

- **Cross-agency portfolio composition**
  How does the federal SBIR portfolio compose across all 11 agencies by
  technology area?
  *Deps: CET · Refs: [L16] · Spec: [../specs/cross-agency-taxonomy/](../specs/cross-agency-taxonomy/)*

- **Cross-agency CET overlap**
  Which CET areas are funded by multiple agencies?
  *Deps: CET*

- **Technology mix over time**
  How does the SBIR technology mix shift over time, by agency?
  *Deps: CET · Refs: [L18]*

- **CET alignment per award**
  Which SBIR awards align with each CET area, and with what calibrated
  probability?
  *Deps: none · Spec: [ml/cet-classifier.md](ml/cet-classifier.md)*

### C2. Relational (Tier 2)

- **Patent-to-award linkage**
  Which USPTO patents are linked to specific SBIR awards, and with what
  confidence?
  Parallels Jaffe-Trajtenberg-Henderson [L13].
  *Deps: ER, PATLINK · Refs: [L13] · Spec: [transition/vendor-matching.md](transition/vendor-matching.md)*

- **Semantic patent similarity**
  Which patents are semantically similar to specific SBIR awards
  (ModernBERT-Embed)?
  *Deps: PATLINK · Spec: [../specs/modernbert_analysis_layer/](../specs/modernbert_analysis_layer/)*

- **Award-contract technology alignment**
  Do SBIR awards and the contracts that result from them share the same
  technology focus?
  *Deps: ER, ID, CET*

- **Patent linkage distribution**
  How many patents are linked to each award, and what does the matching-confidence
  distribution look like?
  *Deps: PATLINK*

### C3. Inferential (Tier 3)

- **Marginal cost per patent**
  What is the marginal cost per patent by agency (award dollars ÷ linked
  patents)?
  Compare against the NIH/NSF figures in NASEM reviews.
  *Deps: ER, PATLINK · Refs: [L3], [L4], [L6] · Spec: [../specs/patent-cost-spillover/](../specs/patent-cost-spillover/)*

- **Spillover multiplier**
  What is the spillover multiplier — non-SBIR patent citations to SBIR patents?
  **Target:** reproduce Myers & Lanahan's ~3× for DOE, with ~60% U.S.-retained.
  *Deps: PATLINK · Refs: [L9], [L5]*

- **Cost and spillover variation**
  How do patent cost and spillover vary by technology area, firm size, and award
  vintage?
  *Deps: ER, PATLINK, CET*

## D. Economic & fiscal impact

*Audience: Treasury, OMB, JCT, state economic-development offices. What is the
dollar return on the SBIR program?*

### D1. Descriptive (Tier 1)

- **Award totals**
  What are award totals by state, agency, and phase?
  *Deps: none · Refs: [L18]*

- **NAICS coverage and fallback usage**
  What is NAICS-sector coverage across awards, and how often is the fallback
  used?
  *Deps: IMP for NAICS · Spec: [../specs/naics-enricher-consolidation/](../specs/naics-enricher-consolidation/)*

### D2. Relational (Tier 2)

- **Federal fiscal returns**
  What are the federal fiscal returns (tax receipts) from SBIR program spending?
  TechLink's DoD-wide 1995–2018 study reports ~22:1 total-output ROI, 8.4:1 sales
  ROI, and $39.4B in tax revenue; Air Force ~12:1 and Navy ~19.5:1 [L19]. NCI
  published a separate economic-impact study [L20].
  *Deps: ER, ID, NAICS, BEA I-O · Refs: [L19], [L20] · Spec: [fiscal/](fiscal/), [../specs/fiscal-tax-impact-v2.md](../specs/fiscal-tax-impact-v2.md)*

- **Employment and income impacts**
  What are the employment, wage, proprietor-income, and production impacts per
  award?
  *Deps: fiscal model*

- **Returns by state and sector**
  How do fiscal returns stratify by state and NAICS sector?
  *Deps: ER, NAICS*

- **Highest-multiplier sectors**
  Which NAICS sectors show the highest fiscal return multipliers?
  *Deps: fiscal model*

- **Treasury payback period**
  What is the payback period for Treasury investment recovery?
  *Deps: fiscal model*

- **Jurisdiction decomposition**
  What share of total tax impact accrues where, decomposed into federal income,
  payroll, corporate, and excise versus state/local income, sales, and property?
  *Deps: fiscal model with state rates*

### D3. Uncertainty & reconciliation (Tier 3)

- **Sensitivity of fiscal estimates**
  How robust are fiscal return estimates to parameter uncertainty (sensitivity
  bands)?
  *Deps: full fiscal model*

- **Reconciliation to NASEM figures**
  What match rates and entity-resolution coverage are needed to reconcile to the
  NASEM follow-on funding multiplier and impact figures?
  *Deps: ER, ID · Refs: [L1], [L2]*

- **NIPA-derived vs. hardcoded tax rates**
  Are tax-impact estimates more credible when derived from BEA NIPA tables [L22]
  than from hardcoded effective rates? Does state-specific variation — Texas with
  no income tax versus California at 13.3% — materially change state-by-state ROI
  estimates?
  *Deps: NIPA rate provider, state rate provider · Refs: [L22]*

## E. Program management & data infrastructure

*Audience: SBA, agency program managers, GAO, internal pipeline engineers.
Foundational — most questions in A–D depend on work here.*

### E1. SBIR identification (foundation, Tier 1–2)

- **SBIR vs. non-SBIR classification**
  Which federal awards are SBIR/STTR versus non-SBIR, and with what confidence?
  A three-tier classifier: FPDS research field (1.0) → ALN (0.8–1.0) →
  description parsing (0.5–0.7).
  **Status:** Partially computable. The negative-control study now provides a
  conservative entity-level screened-negative table using exact identifiers and
  fail-closed collision quarantine across the available award history. Confirmed
  and indeterminate possible SBIR entities are excluded; it does not supply the
  requested award-level confidence classifier or make every candidate screenable.
  *Deps: none · Refs: [L15], [L14] · Audit: [identity and eligibility](../studies/phase-iii-census/identity-eligibility-audit-2026-08-03.md) · Spec: [sbir-identification-methodology.md](sbir-identification-methodology.md), [../specs/archive/completed-features/sbir-identification/](../specs/archive/completed-features/sbir-identification/)*

- **Shared-ALN false positives**
  What are the false-positive rates for shared-ALN grant identification (e.g.
  NIH at ~20%)?
  *Deps: ID*

- **SBIR.gov ↔ USAspending/FPDS reconciliation**
  How does SBIR.gov data reconcile with federal USAspending/FPDS records?
  **Status:** Partially computable. The census input path verified the complete
  available SBIR.gov v2 snapshot and the generated-award Phase II collapse
  against the selected February USAspending/FPDS snapshot. It reconciles only
  exact normalized raw PIID/source identifiers and fails closed on ambiguity or
  taxonomy conflict; broader cross-source completeness remains unvalidated.
  *Deps: none · Refs: [L14], [L1], [L3] (tracking-data limits)*

### E2. Entity resolution (foundation, Tier 1–2)

- **Recipient ↔ contractor identity**
  Is this SBIR recipient the same entity that won the federal contract?
  Resolved through a UEI → CAGE → DUNS → fuzzy-name cascade.
  *Deps: none · Spec: [transition/vendor-matching.md](transition/vendor-matching.md); graph schema in [../specs/archive/completed-features/unify-graph-node-labels/](../specs/archive/completed-features/unify-graph-node-labels/) (Phase 1, `:Award`→`:FinancialTransaction`) and [../specs/archive/completed-features/unify-company-into-organization/](../specs/archive/completed-features/unify-company-into-organization/) (Phase 2, `:Company`→`:Organization`)*

- **Match rate and match quality**
  What is the entity-resolution match rate, and what is the exact-versus-fuzzy
  share?
  *Deps: ER*

- **Identity breaks from corporate change**
  Have companies undergone acquisitions or rebrandings that break matching?
  *Deps: ER*

### E3. Data quality & completeness (Tier 1)

- **NAICS validity and fallback rate**
  What percentage of awards have valid NAICS codes, and what is the fallback
  usage rate?
  *Deps: none · Spec: [../specs/naics-enricher-consolidation/](../specs/naics-enricher-consolidation/)*

- **Missing firm identifiers**
  How many awards lack UEI/DUNS identifiers?
  *Deps: none*

- **Source freshness lag**
  What is the data-freshness lag for SBIR.gov, USAspending, USPTO, and BEA I-O
  sources?
  *Deps: none · Spec: [../specs/iterative_api_enrichment/](../specs/iterative_api_enrichment/)*

- **Missing critical fields**
  Which awards have missing or null critical fields (amount, dates, recipient)?
  *Deps: none*

<a id="e4-data-imputation-tier-23-spec-merged-via-pr-277-implementation-not-yet-started"></a>

### E4. Data imputation (Tier 2–3)

*Spec merged via PR #277; implementation not yet started.*

- **Missing `award_date`**
  Why is `award_date` missing on ~50% of records, and can it be recovered
  non-destructively?
  *Deps: E3 · Spec: [../specs/data-imputation/](../specs/data-imputation/)*

- **Imputation methods and confidence tiers**
  For each imputable field (award date, amount, contract dates, NAICS,
  identifiers), which methods are available, and at what confidence tier — high
  ≥90%, medium 75–90%, low <75%?
  *Deps: E3*

- **Backtest accuracy**
  What is per-method backtest accuracy / MAE against ground-truth holdouts?
  *Deps: IMP*

- **Topic → NAICS crosswalk**
  Can solicitation topics be mapped to NAICS with agency-topic crosswalk top-1
  accuracy ≥75%?
  *Deps: IMP, CET*

- **Imputation effect on transition precision**
  Does the phase-transition precision benchmark remain ≥85% when imputed values
  are included?
  *Deps: IMP + transition detection*

- **Raw vs. effective values downstream**
  Which downstream consumers (Neo4j, CET, transition detection) should use raw
  versus effective values?
  *Deps: IMP*

### E5. External data source evaluation (Tier 2)

**Status:** Research agenda. The earlier branch-only evaluation was not merged;
the questions remain useful, but there is no active umbrella spec.

- **SAM.gov Entity Extracts for UEI backfill**
  Does SAM.gov Entity Extracts materially improve UEI backfill recall?
  *Deps: ER*

- **SAM.gov Opportunities API vs. scraping**
  Does the SAM.gov Opportunities API replace agency-page scraping for
  solicitation ceilings and periods of performance?
  *Deps: E3 · Spec: [../specs/phase-3-solicitation-alerts/](../specs/phase-3-solicitation-alerts/)*

- **Solicitation and attachment coverage**
  Which official sources expose solicitation topics, subtopics, requirement
  text, revisions, and attachments; how much can be retrieved and linked at
  award grain; and does that evidence improve coverage-gap review beyond award
  abstracts and short opportunity descriptions?
  Candidate program/timing or text links must remain separate from exact source
  identifiers, and solicitation similarity does not establish award use or a
  supply-chain dependency.
  **Status:** Initial award-linkage coverage is measured from the full SBIR.gov
  bulk award snapshot. Source-native solicitation text, revisions, and attachment
  coverage remain open.
  *Deps: E3, CET · Plan: [solicitation document evidence](research/solicitation_document_evidence_plan.md) · Evidence: [bulk linkage coverage](research/solicitation_source_coverage_status.md)*

- **FSCPSC NAICS prediction**
  Does FSCPSC NAICS prediction beat our abstract-nearest-neighbor baseline?
  *Deps: IMP*

- **PSC Selection Tool crosswalk**
  Does the PSC Selection Tool provide the NAICS ↔ PSC crosswalk needed for
  topic-derived NAICS?
  *Deps: IMP*

- **DIIG CSIS lookup tables**
  Do DIIG CSIS lookup tables feed our NAICS hierarchy or agency normalization?
  *Deps: none*

- **Third-party procurement clients**
  Should we adopt third-party procurement-tools clients such as
  `makegov/procurement-tools` or `tandemgov/fpds`?
  *Deps: none*

### E6. Continuous monitoring & rolling analytics (Tier 4, capstone)

- **Current-quarter metrics**
  What are the current-quarter SBIR metrics and trends, on weekly snapshots?
  Fills the gap between point-in-time NASEM reviews.
  *Deps: E1–E5 plus the A–D pipelines · Refs: [L1], [L3], [L4], [L5] · Spec: [../specs/weekly-awards-report-refactor/](../specs/weekly-awards-report-refactor/)*

- **Typed LM programs for weekly narratives**
  Can typed, optimized LM programs improve weekly award-narrative schema
  reliability, solicitation grounding, and operator cost beyond the current
  prompt and provider-native structured output?
  *Deps: weekly-awards-report-refactor · Spec: [DSPy evaluation](decisions/dspy-evaluation.md), [prototype spec](../specs/dspy-weekly-awards-prototype/)*

- **Quarter-over-quarter change**
  How have transition rates, patent output, and fiscal returns changed
  quarter-over-quarter?
  *Deps: all*

- **Underperforming agencies**
  Which agencies are under-performing on transitions versus historical baseline?
  *Deps: all*

## F. Capital formation & entrepreneurial finance

*Audience: NVCA, Kauffman Foundation, NBER entrepreneurship researchers, VC/PE
analysts, and agencies (NSF, NIH) running founder-track programs. Does SBIR
funding substitute for, complement, or seed private capital?*

This area treats the SBIR awardee as a **firm with a capital history**, not as a
federal-contract counterparty. Data comes from SEC EDGAR (Form D, 8-K), state
UCC-1 financing-statement registries, and the unified capital-event timeline.
The relevant literature is Lerner [L10], Howell [L11], Kortum & Lerner [L24], and
the NVCA Yearbook [L25] — rather than NASEM and GAO.

### F1. Descriptive (Tier 1)

- **Form D fundraising profile**
  What is the Form D [L23] private-placement fundraising profile of SBIR
  awardees?
  *Deps: ER, SEC EDGAR · Spec: [../specs/archive/completed-features/form-d-pipeline/](../specs/archive/completed-features/form-d-pipeline/) (PR #286 merged)*

- **Debt vs. equity composition**
  In SBIR-firm Form D filings, how much of the money raised is debt versus
  equity, and what share of each announced offering actually sells (the fill
  rate)?
  *Deps: ER, SEC EDGAR · Spec: (PR #286 merged)*

- **Secured-debt activity**
  What fraction of SBIR awardees show secured-debt activity (UCC-1 filings), and
  what mix of equipment finance, depository-bank lending, and venture debt do
  those filings represent, by lender?
  UCC-1 complements Form D's equity view. The CA-only pilot found equipment and
  community-bank patterns, and an absence of venture-debt lenders in the CA
  channel.
  *Deps: ER, UCC-1 · Spec: [../specs/archive/completed-features/ucc1-financing-analysis/](../specs/archive/completed-features/ucc1-financing-analysis/) (PRs #303 / #305 merged)*

- **Unified capital-event timeline**
  What does a single firm history look like when federal awards, private
  placements, M&A, and patent events are placed on one timeline?
  *Deps: ER, SEC EDGAR, UCC-1, M&A signals · Spec: (PR #307 merged)*

- **M&A exit rate by agency**
  What is the SBIR-firm M&A exit rate, and how does it stratify by funding agency
  (HHS biotech ~9.3% vs. DoD defense ~5.8%)?
  *Deps: ER, M&A signals · Spec: (PR #286 merged)*

- **Time to exit**
  What is the median time from first SBIR award to M&A exit?
  Roughly 15 years, per PR #286.
  *Deps: ER, M&A signals*

### F2. Relational (Tier 2)

- **Acquirer-type concentration**
  Among acquirers of SBIR firms, what share are life-sciences consolidators
  (Bruker, Ligand, Thermo Fisher) versus defense primes versus financial
  sponsors? What fraction of acquirers are serial buyers with 3+ SBIR-firm
  targets?
  *Deps: ER, M&A signals*

- **Filers vs. non-filers**
  Do Form D filers and non-filers differ on transition, patent, and exit
  outcomes, controlling for vintage, agency, and CET area?
  *Deps: ER, ID, CET, SEC EDGAR · Spec: (PR #314)*

- **SBIR ↔ M&A match rate by fiscal year**
  What is the SBIR ↔ M&A-event match rate by fiscal year, and how is coverage
  trending?
  *Deps: ER, M&A signals · Spec: [../specs/sbir_ma_match_rate_by_fy/](../specs/sbir_ma_match_rate_by_fy/) (PR #313)*

- **Capital structure vs. NVCA cohort**
  How does SBIR-firm capital structure benchmark against the NVCA Yearbook [L25]
  cohort of comparable-stage VC-backed startups?
  *Deps: ER, SEC EDGAR · Refs: [L25]*

### F3. Inferential (Tier 3)

- **Private-to-SBIR leverage ratio**
  What is the private-to-SBIR leverage ratio (private capital raised ÷ SBIR
  funding) by agency, vintage, and firm size?
  The private-side mirror of NASEM's 4:1 DoD follow-on funding multiplier [L1].
  *Deps: ER, ID, SEC EDGAR · Refs: [L1] · Spec: [../specs/archive/completed-features/form-d-pipeline/](../specs/archive/completed-features/form-d-pipeline/), [../specs/agency-private-capital-comparison/](../specs/agency-private-capital-comparison/)*

- **Outcomes vs. private-capital baselines**
  For Phase II awardees of any agency, do follow-on funding and exit outcomes
  match the published private-capital-backed-startup baselines from the NVCA
  Yearbook [L25]?
  *Deps: ER, SEC EDGAR · Refs: [L25] · Spec: (PR #321 merged, supersedes #311; agency-parameterized via the `agency_private_capital_baseline_comparison` asset in group `agency_private_capital`, with terminology changed from "VC" to "private capital")*

- **Crowd-in vs. crowd-out**
  Does SBIR funding crowd in or crowd out subsequent private capital?
  **Target:** reproduce or extend Howell's finding that an early-stage DOE SBIR
  grant roughly doubles the probability of subsequent VC [L11]. Compare against
  Kortum & Lerner [L24] on VC's contribution to innovation.
  *Deps: ER, ID, SEC EDGAR · Refs: [L11], [L24]*

- **Geographic concentration of effects**
  Does Lerner's finding [L10] — that SBIR growth effects concentrate in VC-rich
  zip codes — still hold post-2010 and across all eleven agencies?
  *Deps: ER, ID, SEC EDGAR · Refs: [L10]*

### F4. Predictive (Tier 4)

- **Forward exit probability**
  What is the forward-looking probability of an exit event (M&A or IPO) for a
  given SBIR firm, conditional on its capital-event history and CET area?
  *Deps: all of F1–F3*

## Output products & audiences

Documents and reports this inventory has produced for specific readers. Each is
a synthesis of A–F questions for a particular audience, not a new research
question.

### Congressional district success-story briefings

**Audience:** members of Congress and their staff, for constituent-facing
communication.

**Format:** a per-district briefing identifying 3–5 SBIR firms within the
member's district that represent the strongest success stories — FDA-cleared
products, defense supplier roles, follow-on capital raises, M&A exits — with
political-safety vetting. Vetting depth covers press review, SEC Form D filings,
M&A history, and political-sensitivity factors (foreign ownership, classified
work exposure, recent acquisition).

No district briefing artifacts are committed. Until a reproducible briefing
workflow and its evidence packet are present, this remains a proposed output
rather than a repository capability.

**Supporting code:** `sbir_etl/enrichers/congressional_district_resolver.py`
(UEI → district resolver), `scripts/setup_congressional_districts.py` (district
reference data).

**Pulls from:** Section A (portfolio composition; A1 foreign-ownership and A4
acquisition screens), B1–B3 (commercialization signals), F1–F2 (capital events,
M&A). Classified-work exposure remains a manual political-sensitivity vetting
factor, not an automated pipeline screen — there is no vulnerability signal for
it.

### Form D fundraising analysis (published)

**Audience:** F-area analysts, investor researchers, and policy staff studying
program-wide private-capital leverage.

**Format:**

- `docs/research/sbir-form-d-fundraising-analysis.md` — canonical, on `main`.
  Includes Appendix A (firm-level bootstrap CIs, PR #338) and Appendix B (PIF
  cross-link integrity audit, PR #341).
- `docs/research/dod-form-d-leverage.md` — DoD Branch decomposition, per-firm and
  time-series and acquirer-type follow-ups, and the Form D vs. FPDS substitution
  test (PRs #342 / #343 / #350).
- `docs/research/form-d-data-dictionary.md` — field reference.

**Pulls from:** F1 (Form D profile), F3 (private-to-SBIR leverage), A1/A4
(DoD-specific firm-health and acquisition decomposition).

### Commercialization-benchmark methodology (historical, not reproducible)

**Audience:** SBA program oversight, statutory compliance reviewers, GAO.

**Format:** [Commercialization benchmark methodology](commercialization-benchmark-methodology.md)
is committed and documents the §638(qq)(3) statutory framework, FY2026 evaluation
method, data-source provenance (FPDS/USAspending contracts, SEC Form D investment,
and SBIR.gov FABS grants), and per-firm audit protocol.

The methodology document refers to an audit harness and FY2026 cohort that are
not committed and therefore cannot be independently reviewed or reproduced.
Its numerical results are historical context, not citable repository outputs.
The maintained counterpart is `scripts/run_benchmark.py` plus
`sbir_etl/models/benchmark_models.py`, which implements the same statutory
framework through a different CLI shape.

Migrating the missing audit behavior into the maintained CLI, with committed
synthetic fixtures and validation checks, remains the coverage gap.

**Pulls from:** B3 (transition effectiveness and the §638(qq) benchmark
question), F1 (Form D investment signal), F2 (NVCA-baseline comparison).

## Prior literature & benchmarks

Public studies this inventory draws from or benchmarks against.

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
- **[L30]** GAO-25-107283 (2025). *Defense Industrial Base: Actions Needed to Address Risks Posed by Dependence on Foreign Suppliers.* Finds DoD relies on 200,000+ suppliers with little visibility past the prime-contractor tier — the documented sub-tier-visibility gap behind the out-of-scope choke-point questions. <https://www.gao.gov/products/gao-25-107283>
- **[L31]** DoD. *State of Competition within the Defense Industrial Base* (February 15, 2022). Documents defense-sector consolidation (prime contractors 51→5 since the 1990s; small businesses in the DIB down >40% over a decade) and five priority sectors (microelectronics, missiles & munitions, high-capacity batteries, castings & forgings, critical minerals & materials). <https://media.defense.gov/2022/Feb/15/2002939087/-1/-1/1/STATE-OF-COMPETITION-WITHIN-THE-DEFENSE-INDUSTRIAL-BASE.PDF>
- **[L32]** CSIS Center for the Industrial Base. *New Entrants and Small Business Graduation in the Market for Federal Contracts.* FPDS-based analysis (2001–2016) of entrant, exit, and small-business graduation rates in federal contracting. <https://www.csis.org/analysis/new-entrants-and-small-business-graduation-market-federal-contracts>
- **[L33]** DoD SBIR/STTR Fast Track. Match mechanism of up to four SBIR/STTR dollars per outside-investor dollar (1:1 to 1:4), contingent on Phase II selection. Verified leverage anchor for A-CP11. <https://www.sbir.gov/tutorials/individual-agency-requirements/DOD-services>

---

## Maintenance

**Last reviewed:** 2026-08-03. Status vocabulary now distinguishes computable,
validated, and citable work; unmerged branch-only references were removed. Git
history preserves earlier editorial and section-consolidation notes.

Open source-verification items:

- **A-CP11 / NSF ~18:1 portfolio leverage** — the ~18:1 private-to-public figure
  was found only in trade press, not confirmed against an NSF publication (NSF
  primary pages returned 403 during the review; a separate NSF page cites "$6.5B
  private investment since 2015," which does not reconcile). Marked
  `[TODO: verify]` inline and **not stated as fact**. The DoD Fast Track 1:4
  anchor [L33] is verified.
- **A3 / "4:1 NASEM" multiplier attribution** — the A3 "~4:1" figure and its
  NASEM attribution [L1], [L2] were left untouched per scope.
  `[TODO: verify A3 4:1 attribution against NASEM source]` before the next
  citation audit relies on it.

The next audit should verify:

- All `(PR #…)` references resolve to merged or otherwise tracked PRs
  (closed-without-merge PRs need explicit successor links — PR #311 → #321 was
  the prior failure mode).
- Internal links to `../specs/` and `docs/` directories resolve.
- Each *Deps* slot accurately reflects current pipeline structure (M&A signals
  are script-driven, not orchestrated — flagged in the implementation note under
  [A4](#a4-risk-monitoring--prediction-tier-4)).
- Coverage gaps: cross-reference recent merged feature PRs against this
  inventory to surface work not yet documented here.
- CET taxonomy consistency: the canonical spine is the 21-area `NSTC-2025Q1` set
  (`config/cet/taxonomy.yaml`, validated by `taxonomy_loader.py`). Two divergent
  code-level taxonomies remain unreconciled — a 10-area transition-system set
  (`docs/transition/cet-integration.md`, code in transition CET inference) and a
  19-area hardcoded reporting set
  (`sbir_etl/utils/reporting/analyzers/cet_analyzer.py`). Reconciling these to
  the 21-area spine is a code change with test/precision-benchmark risk and
  should be scoped separately.
