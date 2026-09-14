---
Type: Research plan
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-09-14
Status: proposed
---

# Literature replication roadmap

**Audience:** Repository maintainers and research leads

This roadmap orders exact replications of studies that support the questions in
[`docs/research-questions.md`](../research-questions.md). It starts with descriptive public-data
studies that fit the current pipeline. It ends with causal studies that require restricted or
unavailable inputs.

Each selected study has two separate products:

1. A **published-sample replication** uses the original period, cohort, definitions, and source
   vintage. It attempts to reproduce the published tables and estimates.
2. A **current-data extension** applies the unchanged published method to a newer pinned data cut.
   It is not part of the published-sample replication and must be reported separately.

Do not substitute a public-data proxy for a missing variable and call the result a replication.
For example, Form D is not a venture-capital database, an inferred follow-on contract is not a
statutory Phase III award, and a citation-count ratio is not the Myers-Lanahan identification
strategy.

## Completion standard

The first goal is `reproducible`, not `citable`. Each replication must have:

- a frozen protocol that names the paper version, estimand, cohort, source tables, exclusions,
  transformations, and expected tables or figures;
- a `studies/<study-id>/study.yaml` manifest with pinned inputs and outputs;
- a cohort-flow table, source-coverage report, benchmark reconciliation, and documented
  sensitivity checks;
- blocking checks for identifiers, grain, row counts, duplicate joins, and denominator integrity;
- a clear outcome of `reproduced`, `diverged with explanation`, or `blocked`;
- separate output directories and claims for the original sample and the current-data extension.

Use the existing `StudyManifest.reproduction` contract for live upstreams. Pin each retrieval
manifest and declare its identity grain, upstream-size measure, checked quantities, tolerances,
and tolerance derivation. Use `sbir_etl.quality.reproduction` to distinguish upstream drift from
pipeline regression. Promotion beyond `reproducible` is separate work under the
[epistemic-tier contract](../steering/epistemic-tiers.md).

## Execution order

Do not begin a later wave merely because an earlier estimate diverges. Continue when the earlier
study reaches one of the three documented outcomes above and all unexplained pipeline failures are
closed.

| Order | Study or benchmark | Questions | Why it is in this position | Start gate |
| ---: | --- | --- | --- | --- |
| 1 | SBA annual-report tables [L18] | A1, C1, D1 | Direct grouping of public award records | Exact table definitions and report-year source files captured |
| 2 | CSIS entrant and graduation analysis [L32], with GAO concentration benchmarks [L14] | A1-A3 | Current code already computes HHI, top shares, geography, and entrants | Published cohort and classification rules recovered |
| 3 | NASEM DoD follow-on multiplier [L1], with [L2] as the earlier benchmark | A3, D3 | The core multiplier asset already exists | NASEM numerator, denominator, window, and dollar-basis rules recovered |
| 4 | NASEM agency patent-cost tables [L3-L6] | C2, C3 | Award-patent linkage exists; no citation network is required | Published patent and award denominator definitions recovered |
| 5 | Agency transition and commercialization tables [L1-L4, L6, L12, L47] | A2, B2, B3 | Transition and Phase III census machinery exists, but label validity is unresolved | Original outcome data are accessible and Phase III labels are independently validated |
| 6 | Repeat-awardee economic contributions [L41] | B, C, D | Award, patent, and procurement channels exist; several published outcomes do not | Every published outcome source and coding protocol is available |
| 7 | DOE knowledge spillovers [L9] | C3 | The exact design needs new text, policy, patent-universe, and econometric inputs | The AEA package and all licensed inputs can be executed locally |
| 8 | Restricted-data causal and structural studies [L10, L11, L34, L36, L40, L43, L44] | A, B, D, E, F | Core treatment, control, or outcome records are unavailable in the current repository | Data-use approval and the original replication package are in hand |

### 1. SBA annual-report tables

Reproduce award dollars and counts by agency, state, phase, fiscal year, and first-time-winner
status. Start with the most recent annual report whose underlying source export can be recovered.

- Recreate each selected table from the report's source vintage.
- Match the report's treatment of STTR, amendments, zero-dollar records, and fiscal year.
- Match its first-time-winner history window. Report left-censoring when the available history is
  shorter.
- Compare every cell against the published value. Classify differences as rounding, revised
  upstream data, definition mismatch, or pipeline defect.
- After the published tables reconcile, run the same code on the current award snapshot.

**Done when:** Each published cell matches within its declared rounding tolerance or has a
row-level explanation. The manifest and reconciliation report can be rebuilt from the declared
inputs.

### 2. CSIS entrants, graduation, and concentration

Reproduce the published 2001-2016 entrant, exit, and small-business graduation analysis in [L32].
Use [L14] only for the concentration values and definitions it publishes.

- Implement the exact FPDS population, action grain, organization identity, entry, exit, and
  graduation definitions.
- Keep first-observed entry separate from confirmed entry. Quantify the history required before a
  firm can be called new.
- Reconcile the published aggregate time series before adding CET, geography, or DoD-component
  extensions.
- Reuse the existing DoD supply-chain calculations after their cohort rules are parameterized;
  do not create a second HHI or entrant implementation.

**Done when:** The original aggregate series and concentration benchmarks reconcile. Current-data
extensions retain the original definitions and label any source-taxonomy changes.

### 3. NASEM DoD follow-on multiplier

Reproduce the 2012-2020 ratio of non-SBIR DoD obligations to SBIR/STTR obligations for SBIR firms.
The published target is greater than 4:1.

- Resolve the exact FPDS/USAspending tables, transaction grain, firm universe, cohort years,
  agency scope, STTR treatment, inflation basis, deobligation treatment, and numerator timing.
- Use the current `follow_on_multiplier` asset as the only calculation path.
- Implement the independent invariants, sensitivity grid, deterministic review sample, and report
  gate described by `specs/follow-on-multiplier-validation/`.
- Review sampled entity links and SBIR classifications before interpreting the result.
- Do not tune the method to reach 4:1. Explain divergence by source coverage or method.

**Done when:** Numerator and denominator reconcile independently to their source ledgers, join
fan-out checks pass, reviewed classifications meet the frozen threshold, and the NASEM comparison
has a row-level audit trail.

### 4. NASEM marginal cost per patent

Reproduce each selected agency review's published patent count and award-dollar denominator before
computing cost per patent.

- Recover the original award period, patent type, linkage rule, application or grant-date rule,
  citation-lag exclusion, agency scope, and duplicate-patent treatment.
- Reconcile published award and patent counts separately before dividing them.
- Report linkage coverage beside every cost estimate.
- Suppress any current-extension subgroup that does not meet a frozen small-cell rule.
- Keep this work independent of the DOE spillover replication in step 7.

**Done when:** The agency totals and cost benchmark reproduce or every difference maps to a named
source or rule difference.

### 5. Transition and commercialization studies

Select one agency study after an input audit establishes that its outcome data are available.
Prefer [L47] if its Navy Phase III and commercialization outcome definitions can be reconstructed.

- Freeze the paper's award cohort, follow-up window, transition definition, censoring policy, and
  commercialization outcome.
- Complete the planned hand-label validation before treating inferred follow-on work as Phase III.
- Extract Kaplan-Meier, competing-risk, and observation-window logic from research scripts into a
  single reusable analysis path before calculating estimates.
- Reproduce published transition tables first. Add technology-area or current-period cuts only as
  extensions.
- Mark survey-derived outcomes `blocked` if the original respondent-level data are unavailable.

**Done when:** The paper-defined outcomes reproduce from the original data. Proxy outcomes remain
separate and do not satisfy this step.

### 6. Repeat-awardee economic contributions

Attempt [L41] only after a method-and-data audit identifies every published outcome source.

- Reproduce the award-count strata, top-recipient selection, random comparison sampling, and seed.
- Add canonical sources for publications, products, spinoffs, and principal-investigator careers.
- Reuse current patent and procurement pipelines for those outcome channels.
- Preserve the published manual-coding protocol. Add blinded double review and disagreement
  resolution where manual labels affect a table.

**Stop condition:** If any published outcome category or comparison sample cannot be rebuilt, mark
the exact replication blocked. Do not replace the missing outcome with an available channel.

### 7. Myers-Lanahan DOE spillovers

Replace the current citation-ratio concept in `specs/patent-cost-spillover/` before implementation.
The paper uses state matching-policy variation and technology-space similarity. Patent citation
ingestion alone does not reproduce its estimand.

- Run the authors' AEA replication package against the original inputs as a baseline.
- Add versioned DOE funding-opportunity text and state matching-policy timing and amount data.
- Build the full patent-universe panel with abstracts, classes, assignee and inventor geography,
  and SBIR-recipient links.
- Implement the published instrument, sample restrictions, fixed effects, standard errors, and
  technology-similarity construction.
- Reproduce the main specification tables, the approximately 3x spillover estimate, and the
  approximately 60% domestic-retention result.
- Add citation-network results only as a separately named extension.

**Done when:** The original package runs deterministically and the repository implementation
reproduces its principal tables within frozen numeric tolerances.

### 8. Restricted-data causal and structural studies

Create no implementation spec until the required data and code are available.

- [L11] and [L43] require unsuccessful DOE applicants, proposal ranks or cutoffs, and restricted
  firm or worker outcomes.
- [L34] requires Air Force application and competition records, not only observed awards.
- [L40] requires an eligible nonrecipient frame and longitudinal employment histories.
- [L10] requires historical matched nonrecipients, sales, employment, and venture-capital context.
- [L36] requires a university licensing and spinoff population.
- [L44] requires the procurement-contest inputs used by its structural model.

For each study, first execute the authors' released package unchanged. Then map its inputs to a
versioned restricted-data adapter. Keep restricted bytes outside git and record only permitted
hashes and aggregates.

**Stop condition:** If the treatment assignment, comparison population, or primary outcome is not
available, record the study as externally blocked. Award-only or Form D analyses are not exact
replications of these studies.

## Missing capabilities

The repository already has stable award identities, USAspending transactions, transition assets,
patent links, CET classification, fiscal transforms, a modular analysis runner, study manifests,
and live-upstream reproduction checks. The remaining gaps are:

1. **A replication registry.** The literature map is bibliographic, while `study.yaml` records
   epistemic status. Neither stores the complete paper-to-estimand-to-code crosswalk.
2. **Staged historical cuts.** The development checkout does not contain the canonical historical
   SBIR, USAspending, SAM.gov, and USPTO cuts needed for the first replications.
3. **Uniform retrieval manifests.** Some live producers still lack the upstream-size and identity
   records required by the reproduction contract.
4. **A longitudinal research panel.** There is no shared firm-award-year frame for awards,
   obligations, transitions, patents, geography, NAICS, CET, and observation windows.
5. **Reusable statistical methods.** Survival, matching, balance, bootstrap, panel, event-study,
   regression-discontinuity, and instrumental-variable code is absent or scattered in scripts.
6. **Patent-spillover inputs.** Citation edges, the full patent universe, assignee history, DOE
   funding-opportunity text, and state matching-policy data are missing.
7. **Firm outcomes and comparison populations.** The repository lacks a maintained eligible
   nonrecipient frame and longitudinal employment, revenue, product, publication, and spinoff
   outcomes.
8. **Independent labels.** Entity lineage and Phase III validation remain too limited for citable
   transition claims.
9. **Question-to-literature links.** Recent additions [L34-L48] appear in the bibliography but are
   not connected to the individual questions they support.

## First implementation tranche

Start with the shared registry and the minimum retrieval-manifest work needed by steps 1-3. Do not
build a general research framework beyond those three studies.

1. Add replication registry entries and frozen method notes for [L18], [L32], and [L1].
2. Stage and verify the historical source cuts for their published periods.
3. Reproduce the SBA tables and CSIS series.
4. Complete and run the multiplier validation design on the 2012-2020 cohort.
5. Create one study manifest per replication at `exploratory`; promote it to `reproducible` only
   after its published-sample gate passes.
6. Run the unchanged methods on current cuts and publish the extensions in separate artifacts.

This tranche proves the replication workflow on one descriptive report, one longitudinal
descriptive study, and one linked administrative-data benchmark before new econometric or
restricted-data infrastructure is funded.
