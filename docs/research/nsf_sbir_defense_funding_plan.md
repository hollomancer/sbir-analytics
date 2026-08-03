# NSF SBIR defense-funding lineage plan

## Objective

Extend the initial SBIR-to-DIB network so an analyst can determine which current and former
NSF SBIR awardees received Department of Defense (DoD) funding as a prime recipient or a
reported subcontractor, while preserving the distinction between observed funding and an
inferred supply-chain dependency.

The implementation must answer four separate questions:

1. Which legal entities received NSF SBIR or STTR awards, and when were those awards active?
2. Which of those entities received DoD prime or subaward funding, by instrument and fiscal
   year?
3. Which NSF-funded capabilities are candidates for critical-supply-chain review?
4. What evidence, if any, connects a specific NSF award to a specific DoD requirement?

The fourth question is not answered by shared firm identity alone. It requires award-, contract-,
product-, or capability-level evidence and must remain `not_established` when that evidence is
absent.

## Current baseline

The repository now provides an initial, reproducible screen built from:

- the SBIR.gov bulk award registry for the SBIR/STTR awardee universe and award text;
- DoD contract subaward records from USAspending for fiscal years 2021–2025;
- UEI and legacy DUNS identity matches, with unique-name matches retained as candidates;
- the existing CET classifier and DoD critical-technology crosswalk; and
- a static graph explorer for reviewing suppliers, primes, persistence, and NSF award candidates.

This baseline does **not** yet ingest NSF's direct award records, materialize DoD prime funding,
or prove that a specific NSF award supported a particular DoD procurement. Its graph edges are
observed legal-entity funding relationships, not dependency claims.

## Scope and non-goals

### In scope

- Current and historical NSF SBIR/STTR awards and awardees.
- Direct NSF validation of award identifiers, abstracts, program metadata, dates, and funding.
- DoD prime procurement, prime assistance, other-transaction, and reported subaward funding.
- Awardee identity resolution with explicit match methods and confidence.
- Time-aware funding summaries and graph relationships.
- Candidate screening for critical technology and supply-chain relevance.
- Source provenance, reconciliation results, and quality metrics.

### Deferred or excluded

- FOCI analysis.
- Unreported lower-tier supplier relationships or bill-of-material dependencies.
- A claim that DoD funding used a particular NSF-funded invention without direct evidence.
- Grants.gov as an award or payment ledger.
- DoD-14/NDIS-8 mappings until an authoritative, citable mapping is available.

## Source-of-truth matrix

| Question | Primary source | Use | Important boundary |
| --- | --- | --- | --- |
| SBIR/STTR universe | [SBIR.gov data resources](https://www.sbir.gov/data-resources) | Cross-agency baseline, phase, topic, award text | Reconcile rather than silently overwrite direct NSF data |
| Direct NSF awards | [NSF Award Search and API](https://www.nsf.gov/awardsearch/download.jsp) plus NSF annual XML downloads | Award ID, title, abstract, dates, amount, program and organization metadata | NSF is authoritative for its own awards |
| DoD prime contracts | USAspending contract transactions derived from FPDS | Signed transaction obligations by recipient, award, agency, date, and instrument | Preserve deobligations and transaction grain |
| DoD prime assistance | USAspending assistance transactions derived from FABS | Grants and cooperative-agreement obligations | Keep separate from procurement |
| DoD other transactions | Existing repository OT ingestion path | Prime OT obligations | Keep instrument identity and source provenance |
| DoD subawards | USAspending File F/FSRS subaward records | Reported first-tier subcontract and assistance-subaward obligations | Reporting coverage is incomplete and not equivalent to all tiers |
| Solicitation context | [Grants.gov](https://www.grants.gov/) | Optional NOFO/solicitation text and program context | Never use to validate an award or payment |

The pipeline should preserve source-native agency identifiers and names. “Department of War” is
treated as the user's research label; source records and outputs continue to use their native DoD
designations unless an authoritative source changes them.

## Definitions

- **Current NSF awardee:** a resolved legal entity with at least one direct NSF SBIR/STTR award
  whose authoritative performance period is active as of the analysis date.
- **Former NSF awardee:** a resolved legal entity with historical direct NSF SBIR/STTR funding and
  no active award as of the analysis date. This does not imply that the business is inactive.
- **DoD-funded prime:** the resolved entity is the recipient on a DoD prime transaction.
- **DoD-funded subcontractor:** the resolved entity is the subaward recipient on a reported DoD
  subaward transaction.
- **Supply-chain review candidate:** award text or observed relationships satisfy a documented
  screen. It is not a confirmed critical dependency.
- **Specific-award use:** direct evidence connects an NSF award's capability or work product to a
  DoD award, requirement, deliverable, or product. Firm-level co-occurrence is insufficient.

## Identity and award reconciliation

1. Normalize organization identifiers without discarding their source values.
2. Match NSF and SBIR.gov awards first by NSF award ID or agency tracking number.
3. Resolve organizations by UEI, then legacy DUNS; use normalized names only as review candidates.
4. Record every match as `match_method`, `match_confidence`, and `match_evidence`.
5. Emit conflicting dates, amounts, abstracts, or organizations as reconciliation findings instead
   of choosing a value silently.
6. Maintain a stable internal organization ID so prime and subaward transactions resolve to the
   same legal-entity node without merging weak name candidates.

## Planned data products

| Product | Grain | Purpose |
| --- | --- | --- |
| `nsf_sbir_awards_direct.parquet` | One direct NSF award | Authoritative NSF award snapshot |
| `nsf_sbir_award_reconciliation.parquet` | One NSF/SBIR.gov comparison | Match method and field-level discrepancies |
| `nsf_awardee_dod_prime_transactions.parquet` | One signed DoD prime transaction | Procurement, assistance, and OT funding lineage |
| `nsf_awardee_dod_subaward_transactions.parquet` | One reported DoD subaward transaction | First-tier reported funding lineage |
| `nsf_awardee_defense_funding_summary.parquet` | Awardee × fiscal year × funding mode | Analysis-ready totals without mixing instruments |
| `nsf_award_defense_evidence.parquet` | NSF award × DoD award evidence assertion | Explicit evidence and `not_established` outcomes |
| `nsf_defense_lineage_quality.json` | One build | Coverage, reconciliation, provenance, and invariant results |

Generated data remains outside version control. Code, schemas, small fixtures, quality thresholds,
and methodology stay in the repository.

## Funding semantics

- Aggregate signed transaction obligations, including deobligations; do not substitute current
  award ceilings or potential values for historical flow.
- Keep prime contracts, prime assistance, other transactions, contract subawards, and assistance
  subawards as separate measures.
- Preserve source award IDs, transaction IDs, action dates, awarding/subtier agencies, NAICS/PSC,
  and place of performance where available.
- Compute timing relative to the NSF award start and end dates, but label it as temporal association
  rather than causation.
- Do not add amounts from incompatible grains. Award-level totals and transaction-level flows must
  be named and reported separately.
- Retain zero and negative transactions so fiscal-year totals reconcile to the source.

## Implementation phases

### Phase 1 — Direct NSF ingestion and reconciliation

- Add a direct NSF extractor with immutable raw snapshots, checksum metadata, and an analysis-date
  parameter.
- Normalize NSF award IDs, program elements, organization identifiers, dates, abstracts, and award
  amounts.
- Reconcile direct NSF records to the SBIR.gov baseline and derive current/former status from
  authoritative performance dates.
- Publish coverage and discrepancy metrics.

**Verify:** source snapshots are reproducible; award IDs are unique at the declared grain; exact-ID,
identifier, and name-candidate matches are counted separately; no current/former label is inferred
from award year alone.

### Phase 2 — DoD prime-funding materialization

- Reuse the repository's USAspending/FPDS and FABS extraction infrastructure to select transactions
  for resolved NSF awardees.
- Include procurement, assistance, and the existing OT path with an explicit instrument dimension.
- Preserve transaction-level provenance and signed obligations.
- Partition outputs by fiscal year and funding mode for incremental refresh.

**Verify:** transaction IDs are unique at the source grain; signed totals reconcile to source query
results within documented rounding tolerance; deobligations survive transformation; agency filters
use source identifiers rather than string aliases alone.

### Phase 3 — Unified prime/subaward ledger

- Bring the existing DoD subaward observations into the same organization and fiscal-year model.
- Produce separate prime and subaward totals plus first/last observed funding dates and persistence.
- Add temporal features relative to each NSF award without assigning a DoD transaction to a specific
  NSF award unless evidence supports that link.

**Verify:** prime and subaward records never collapse into one edge type; no double counting occurs
across instruments; every aggregate traces to source transaction IDs; weak-name candidates remain
excluded from verified totals.

### Phase 4 — Evidence and critical-supply-chain screening

- Apply the versioned CET and defense crosswalk screens to reconciled NSF title/abstract/topic text.
- Add evidence records for solicitation, contract description, product/service code, capability, or
  other source material that may connect an NSF award to a DoD requirement.
- Keep `critical_supply_chain_status=not_assessed` and
  `specific_award_usage_status=not_established` unless reviewable evidence changes those states.

**Verify:** classifier and crosswalk versions are present on every screen result; evidence assertions
cite their source and method; firm-level funding alone cannot promote either status.

### Phase 5 — Graph and analyst experience

- Add current/former NSF status and prime/subaward/assistance/OT toggles to the explorer.
- Represent NSF awards, legal entities, DoD awards, agencies, and technology areas as distinct node
  types where the evidence supports them.
- Expose match method, source provenance, temporal overlap, and quality warnings in the details pane.
- Provide downloadable filtered evidence tables alongside the graph.

**Verify:** every visible edge resolves to existing nodes and source records; filters do not change
underlying totals; candidate and verified relationships remain visually distinct; accessibility and
large-payload performance are tested.

### Phase 6 — Research release and recurring validation

- Add an orchestrated refresh, source freshness checks, schema-drift alerts, and a dated manifest.
- Produce a research table answering current/former status and DoD funding by mode, with uncertainty
  fields included by default.
- Document coverage gaps, especially subaward reporting limits and unresolved organizations.

**Verify:** a clean run reproduces the release from pinned inputs; all products share the same
analysis date; quality gates fail closed on schema or reconciliation regressions; published figures
can be recomputed from the release tables.

## Definition of done

The expanded analysis is ready when:

- every NSF record has direct-source provenance and a reconciliation disposition;
- current/former status follows authoritative award dates and a recorded analysis date;
- DoD prime and reported subaward funding are available separately by instrument and fiscal year;
- signed totals reconcile to their source transactions and negative obligations are preserved;
- all organization joins expose method and confidence, and name-only matches remain candidates;
- every graph edge and aggregate is traceable to source record identifiers;
- critical-supply-chain and specific-award-use conclusions remain evidence-gated; and
- Grants.gov is used only for optional solicitation context, never for award or funding validation.

## Recommended delivery order

Implement direct NSF reconciliation first, then DoD prime transactions, then unify the existing
subaward observations. This resolves the largest evidence gaps before expanding the graph and avoids
building analyst features on ambiguous award identities or incomplete funding semantics.
