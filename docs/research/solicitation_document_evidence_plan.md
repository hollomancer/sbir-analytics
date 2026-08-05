# Solicitation Document and Requirement Evidence Plan

**Status:** In progress — bulk award linkage gate passed; solicitation documents remain open

**Last reviewed:** 2026-08-04

**Research anchors:** A1 coverage gaps; E5 external-source evaluation

## Implementation progress

The first implementation increments add the Phase 1 source schema and make the SBIR.gov bulk award
export, rather than the unavailable solicitation endpoint, the initial award-linkage source:

- `scripts/data/build_sbir_bulk_solicitation_links.py` consumes the existing versioned
  `award_data.csv`, validates its schema and metadata sidecar, and materializes exact
  award-to-solicitation/topic assertions plus agency/year-stratified coverage.
- The 2026-08-03 snapshot passes the linkage adapter gate: 115,147 unique assertions from 219,503
  award rows. It contains both solicitation and topic identifiers for 49.1% of all award rows and
  99.9% of NSF award rows from 2022 onward.
- Award titles and abstracts remain explicitly typed as award text. They are not promoted to
  solicitation titles, topic descriptions, attachments, or government requirements.

- `SolicitationExtractor.extract_solicitation_tables()` now returns one lossless
  solicitation-version table and one topic/subtopic table with deterministic identifiers,
  canonical source JSON, hashes, retrieval provenance, all documented fields, and explicit parent
  topic links.
- The existing six-column `extract_topics()` and keyword-search interfaces remain compatible with
  weekly reporting. Report-layer excerpt limits remain outside the source tables.
- `scripts/data/audit_sbir_solicitation_source_coverage.py` and its documentation-derived fixture
  still validate the full solicitation/topic/subtopic shape for a future source-native capture.
- A documentation-derived full-shape fixture exercises all 25 documented solicitation, topic, and
  subtopic fields. It is explicitly not live research evidence.

The solicitation API remains unavailable as of 2026-08-04, but it no longer blocks award-linkage
analysis. It still blocks source-native solicitation descriptions, nested subtopics, status, and
agency URLs. NSF publication, SAM.gov attachment, and Grants.gov source spikes remain pending; see
the [Phase 0 status](solicitation_source_coverage_status.md).

## Purpose

Build a source-traceable corpus of federal solicitation records, topics, subtopics, notices, and
document versions so analysts can compare what agencies asked for with what SBIR/STTR awards
proposed and what later procurement records describe.

The immediate research questions are:

1. Which technical requirements, components, materials, standards, platforms, and manufacturing
   constraints appear in solicitations but not in award abstracts?
2. Which NSF SBIR/STTR awards can be linked exactly to their source solicitation and topic?
3. Does richer government-authored requirement text improve CET coverage-gap and transition
   candidate review over award abstracts and short opportunity descriptions alone?
4. What solicitation and attachment coverage is available by source, agency, year, document type,
   and linkage confidence?

This plan creates evidence for review. It does not establish that a funded capability was used on a
specific contract, that a supplier is critical, or that a physical supply-chain dependency exists.

## Decision

Extend the existing source-specific extractors and evidence conventions. Do not build a general web
crawler or a second opportunity-ingestion stack.

The repository already has useful seams:

- `scripts/data/download_sbir.py` already maintains the official bulk award CSV, a SHA-256 sidecar,
  and dated vintages; `docs/data/sbir_awards_columns.json` defines the reviewed source schema.
- Before this increment, `sbir_etl/extractors/solicitation.py` retrieved SBIR.gov solicitation
  topics but retained only a subset of the documented source fields.
- `sbir_etl/extractors/sam_gov_opportunities.py` retains SAM.gov description, additional-information,
  and attachment URLs.
- `scripts/data/hydrate_candidate_opportunity_descriptions.py` hydrates selected SAM.gov description
  endpoints, but not attachment bodies.
- `specs/phase3-notice-corpus-fusion/` demonstrates that the GSA archive often contains sufficient
  inline notice text and that precise award-grain attribution matters more than indiscriminate text
  collection.
- `specs/transition-coverage-expansion/` demonstrates that Grants.gov NOFOs are rich but often broad
  and sparsely linked to individual awards.
- `specs/phase-3-solicitation-alerts/` owns Phase III opportunity alerting. This plan supplies a
  reusable document/evidence substrate; it does not replace that scoring workflow.

## Current source coverage and gaps

| Source | Source-native content | Current repository use | Gap addressed here |
| --- | --- | --- | --- |
| Direct NSF Award Search and annual award JSON | Award, program, organization, dates, and funding metadata | Award validation and classification inputs where a direct NSF adapter is present | No solicitation body or attachment is carried by the award record |
| NSF funding-opportunity pages and PDFs | Full solicitation sections, responsiveness criteria, award limits, proposal rules, and agency updates | Not ingested | Snapshot and parse the authoritative NSF publication linked to an award or opportunity |
| SBIR.gov bulk awards | Award title/abstract, firm, funding, solicitation number/year/close date, and topic code | Versioned download already supports award and supply-chain research; exact link product now implemented | Use full-snapshot identifiers to seed exact award-to-solicitation/topic assertions; never treat award text as solicitation text |
| SBIR.gov Solicitation API | Solicitation title, phase, year, release/open/close/due dates, status, agency URL, topics, topic links, and subtopics | Lossless normalized substrate implemented; endpoint currently unavailable | Retain as a future source-native solicitation-text path, not the initial linkage dependency |
| SAM.gov Opportunities API | Notice metadata, synopsis endpoint, additional-information URL, and direct attachment URLs | Metadata retained; selected synopsis descriptions hydrated | Fetch, version, parse, and classify selected attachments without losing inline descriptions |
| GSA Contract Opportunities archive | Historical notice metadata and frequently rich inline descriptions | Used by the Phase III notice-corpus research path | Reuse inline text and provenance; do not re-fetch attachments when the archive text is sufficient |
| Grants.gov opportunity detail | Synopsis, Assistance Listings, eligibility, funding envelope, attachments, related URLs, changes, and version history | No adapter; context only | Add a bounded opportunity/document adapter, never an award or payment ledger |
| USAspending / FPDS / FABS | Award and transaction descriptions, identifiers, obligations, and agency metadata | Funding and transition evidence | Use identifiers for linkage only; these sources do not substitute for solicitation documents |

Official source contracts:

- [SBIR.gov downloadable award data](https://www.sbir.gov/data-resources)
- [SBIR.gov Solicitation API](https://www.sbir.gov/api/solicitation)
- [NSF funding opportunities](https://www.nsf.gov/funding/opportunities)
- [SAM.gov Opportunities API](https://open.gsa.gov/api/get-opportunities-public-api/)
- [Grants.gov opportunity detail API](https://www.grants.gov/api/common/fetchopportunity)

## Scope

### In scope

- Versioned SBIR.gov bulk award records as exact award-to-solicitation/topic identifier evidence.
- Public federal SBIR/STTR solicitations and topics from SBIR.gov.
- Official NSF solicitation pages and linked documents for NSF SBIR/STTR records.
- SAM.gov solicitation, presolicitation, sources-sought, special-notice, and justification records
  selected by an explicit cohort or research query.
- Grants.gov opportunities selected by exact opportunity number, Assistance Listing, agency,
  program, or a documented cohort query.
- Public attachments referenced by those source records.
- Immutable raw snapshots, document versions, checksums, retrieval outcomes, extracted text,
  section/page provenance, and source URLs.
- Exact and candidate award-to-solicitation assertions kept as different evidence classes.
- A versioned requirement-span classifier evaluated on a frozen, human-labeled benchmark.
- Research-table and graph exports that keep solicitation evidence separate from award and funding
  facts.

### Out of scope

- Grants.gov as evidence that an award or payment occurred.
- Proposal submissions, reviewer comments, or other nonpublic applicant material.
- General crawling outside allowlisted official government hosts and source-provided URLs.
- Email, Slack, or other solicitation-alert delivery.
- Automatic critical-supplier, specific-award-use, or physical-dependency conclusions.
- Bills of materials, Tier 3+ supplier discovery, country-of-origin, or production-capacity claims.
- FOCI analysis.
- DoD-14 or NDIS-8 mapping until an authoritative, citable mapping exists.

## Evidence and grain model

Do not collapse these grains:

1. **Solicitation version** — one source-native solicitation or opportunity revision.
2. **Topic or subtopic** — one nested technical area under a solicitation version.
3. **Document version** — one immutable attachment or authoritative HTML snapshot.
4. **Document section** — one page/section-addressable extracted text segment.
5. **Requirement assertion** — one classified span with its exact source evidence.
6. **Award-link assertion** — one stated relationship between an award and a solicitation, topic,
   notice, or requirement.

Every assertion records its source record, source URL, snapshot path, checksum, retrieval time,
source version, analysis date, matching rule, and confidence class.

### Link classes

| Class | Permitted evidence | Interpretation |
| --- | --- | --- |
| `exact_source_identifier` | Equal normalized solicitation/opportunity number and, when applicable, topic/subtopic code | The award was issued under the identified solicitation/topic |
| `official_source_reference` | An official award, solicitation, or notice explicitly cites the other identifier | The source itself states the relationship |
| `exact_prior_award_reference` | A notice or justification cites an exact prior award/PIID | The document references that award; it does not by itself prove technology use |
| `candidate_program_timing` | Program/Assistance Listing/agency/date/text alignment without an exact identifier | Review candidate only |
| `candidate_text_similarity` | Requirement-to-award text similarity without exact linkage | Topical relevance only |

Name similarity alone cannot create an exact award-to-solicitation link. Candidate links remain out
of verified counts and use visibly different graph edges and UI labels.

## Planned data products

| Product | Grain | Purpose |
| --- | --- | --- |
| `solicitation_versions.parquet` | One source solicitation/opportunity revision | Cross-source registry, dates, status, program, agency, and identifiers |
| `solicitation_topics.parquet` | One topic/subtopic per solicitation version | Preserve the full technical hierarchy and source links |
| `solicitation_document_manifest.parquet` | One document URL/version/retrieval outcome | Attachment inventory, checksum, MIME type, size, and failure reason |
| `solicitation_document_sections.parquet` | One page or section per document version | Searchable text with page, heading, offsets, and parser provenance |
| `solicitation_requirement_evidence.parquet` | One classified evidence span | Requirement type, normalized value, confidence, and exact citation |
| `award_solicitation_link_assertions.parquet` | One award-to-source assertion | Exact and candidate linkage without confidence laundering |
| `solicitation_corpus_quality.json` | One build | Coverage, schema, retrieval, parsing, linkage, deduplication, and classifier gates |

Generated data stays outside version control. Small source-shape fixtures, schemas, thresholds,
classifier labels, and methodology stay in the repository.

## Acquisition and document safety

1. Use the source API or source-provided direct URL; do not discover arbitrary links by crawling.
2. Allowlist government hosts and revalidate every redirect before downloading.
3. Record `retrieved`, `not_found`, `unsupported_type`, `too_large`, `blocked_host`, `parse_failed`,
   and `source_error` outcomes. Never silently drop an attachment.
4. Store raw bytes immutably by content hash. Preserve separate source-version records when the same
   URL changes, and deduplicate identical bytes across sources without discarding either provenance
   path.
5. Apply configured byte, archive-entry, decompression, and page limits. Quarantine malformed or
   suspicious archives rather than opening them recursively.
6. Start with PDF, HTML, plain text, DOCX, CSV, and XLSX. Add other formats only after a measured
   coverage gap.
7. Extract embedded text first. Apply OCR only when a document is otherwise in scope and a recorded
   text-coverage rule identifies it as scanned.
8. Treat all document text as untrusted data. It cannot supply instructions to tools, alter system
   prompts, or trigger network access.

## Requirement classifier

Create a classifier for government requirements rather than reusing an award-capability classifier
as if the two tasks were equivalent.

### Labels

- `technical_topic`
- `component_or_material`
- `process_or_manufacturing_method`
- `platform_or_mission_system`
- `performance_threshold`
- `standard_or_interface`
- `manufacturing_or_sourcing_constraint`
- `readiness_or_commercialization_expectation`
- `deliverable_or_test_requirement`
- `security_data_rights_or_export_constraint`

The classifier may additionally attach a CET label, but CET is secondary to the requirement span.
It must emit:

- the verbatim evidence span;
- document, version, page/section, and character offsets;
- normalized label and value;
- classifier and taxonomy versions;
- confidence and review status; and
- any deterministic rule or model feature needed to reproduce the decision.

It must not emit `critical`, `dependent`, or `used_on_award` as model conclusions.

### Evaluation gate

Freeze a benchmark before selecting or tuning a model:

- at least 100 documents, stratified across available SBIR.gov/NSF, SAM.gov inline, SAM.gov
  attachment, and Grants.gov/agency-document sources;
- at least 300 adjudicated requirement spans;
- no document version in both train and test;
- agency and document-family stratification in reported results; and
- adversarial negatives containing boilerplate, applicant instructions, historical examples, and
  merely mentioned technologies.

Automatic research-product surfacing requires at least 85% precision overall on the held-out set.
Below that threshold, outputs remain explicitly human-review-only. Recall and per-label precision
must still be reported; an aggregate pass cannot hide a failing high-impact label.

## Implementation phases

### Phase 0 — Source and linkage coverage spike

- Use the full SBIR.gov bulk award snapshot and its existing metadata sidecar as the first linkage
  census; capture bounded source-shape fixtures from NSF, SAM.gov, and Grants.gov separately.
- Measure documented-versus-retained field coverage in existing extractors.
- Sample at least 50 records per remaining available source, including records with and without
  attachments.
- Measure exact award-to-solicitation identifiers, topic availability, attachment yield, MIME types,
  duplicate URLs/content, inaccessible links, and version history.
- Reconcile results with the existing Phase III notice-corpus and transition-coverage findings.

**Verify:** publish a manifested coverage report and a go/no-go decision for each adapter. Do not
promote sparse program/timing joins to exact links.

**Progress:** the bulk award linkage adapter is `go` for exact identifier assertions. The
source-native solicitation/document adapters remain separate and have not passed.

### Phase 1 — Complete the SBIR.gov solicitation substrate

- Expand the existing extractor to retain all documented solicitation fields, dates, status,
  agency URL, topic link, and nested subtopics.
- Preserve one solicitation-version table and one topic/subtopic table instead of flattening away
  hierarchy.
- Remove presentation truncation from the source layer; reports may render bounded excerpts.
- Add schema-drift fixtures and coverage metrics.

**Verify:** source fixtures round-trip without field loss; topic/subtopic identifiers are unique at
their declared grain; current weekly-report behavior remains compatible.

### Phase 2 — Shared document acquisition and parsing

- Add one reusable, allowlisted attachment fetcher and immutable manifest contract.
- Reuse source-provided inline text when adequate; fetch an attachment only when it adds a distinct
  document or required section.
- Parse supported documents into page/section-addressable text and preserve extraction metrics.
- Deduplicate by content hash while retaining every source relationship.

**Verify:** every requested document has a terminal outcome; two builds from frozen raw bytes have
identical hashes and extracted sections; unsupported or unsafe files fail closed.

### Phase 3 — NSF and Grants.gov solicitation context

- Join NSF awards to the solicitation and topic identifiers carried in the versioned SBIR.gov bulk
  award baseline.
- Snapshot the official NSF publication/page and linked documents for exact NSF solicitation
  numbers.
- Add a bounded Grants.gov opportunity-detail adapter for selected opportunity numbers and
  Assistance Listings.
- Treat Grants.gov as versioned solicitation context. Where it points to an official NSF document,
  preserve both provenance paths and use the NSF publication as the source-native program text.
- Record broad parent NOFOs and sparse award links as such; do not manufacture award-specific
  relationships.

**Verify:** exact and candidate linkage counts are separate; missing Grants.gov attachments do not
erase an available official-agency document; Grants.gov never contributes an award or payment fact.

### Phase 4 — SAM.gov attachment completion

- Select notices through an explicit cohort, identifier, or bounded research query.
- Preserve already-hydrated descriptions and GSA archive text.
- Fetch `resourceLinks` and `additionalInfoLink` documents only when they add text or document types
  not already present.
- Carry notice type, solicitation number, PIID references, office, NAICS, PSC, dates, and version
  provenance into the document corpus.

**Verify:** report inline-only, attachment-added, duplicate, failed, and unsupported counts by notice
type and year; attachment retrieval cannot alter the existing Phase III precision benchmark.

### Phase 5 — Requirement extraction and evaluation

- Label and adjudicate the frozen benchmark.
- Establish deterministic baselines before evaluating a local statistical or language model.
- Fit or configure the requirement classifier only on the training partition.
- Publish held-out overall and per-label precision, recall, confusion matrix, and error analysis.
- Version the classifier with its benchmark manifest hash and label taxonomy.

**Verify:** the 85% precision gate passes before automatic surfacing; otherwise retain review-only
status and do not tune downstream thresholds around unvalidated output.

### Phase 6 — Research and graph integration

- Add solicitation, topic, document, and requirement nodes only after corpus quality gates pass.
- Use distinct relationships for `ISSUED_UNDER`, `HAS_TOPIC`, `HAS_DOCUMENT`,
  `STATES_REQUIREMENT`, `REFERENCES_AWARD`, and `POSSIBLY_RELEVANT_TO`.
- Add source citations and downloadable evidence to analyst views.
- Compare award-only CET screening with award-plus-requirement screening on a fixed cohort.
- Report coverage gains and changed rankings; do not relabel review candidates as confirmed
  dependencies.

**Verify:** no dangling nodes, no candidate edge rendered as exact, every displayed requirement
resolves to a document span, and award-only results remain reproducible.

### Phase 7 — Orchestration after value is demonstrated

- Add Dagster assets and partitions only for adapters that pass the Phase 0 coverage gate.
- Default schedules to stopped until a complete manual run succeeds.
- Validate freshness, source-schema drift, attachment outcomes, hashes, parser versions, linkage
  classes, and classifier versions before publication.

**Verify:** a frozen end-to-end release reproduces byte-identical manifests and stable row counts;
intentional source changes produce an explicit version delta rather than an overwrite.

## Success criteria

The initial implementation is complete when it can state, with a pinned analysis date:

- the solicitation, topic, subtopic, and document coverage obtained from each source;
- the share of NSF SBIR/STTR awards with exact solicitation and topic links;
- the number and type of documents added beyond inline descriptions;
- the retrieval and parsing failure distribution rather than only successful counts;
- the held-out precision and recall of each requirement label;
- the incremental CET/requirement evidence added beyond award abstracts; and
- the exact number of verified versus candidate award-to-solicitation assertions.

No success criterion depends on producing a critical-supplier or specific-award-use conclusion.

## Principal risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Broad NOFO text creates false firm-level relevance | Keep opportunity grain; require exact identifiers for verified award links |
| Rich text is boilerplate rather than discriminating requirements | Label spans, include boilerplate negatives, and report per-label precision |
| Attachments duplicate inline or agency-hosted content | Hash-deduplicate bytes while preserving all provenance paths |
| Source URLs change or disappear | Immutable snapshots, retrieval timestamps, version records, and terminal failure outcomes |
| Scanned or malformed documents silently lose content | Text-coverage metrics, bounded OCR, parser status, and fail-closed publication gates |
| Similarity is mistaken for dependency or use | Candidate-only edge type, explicit interpretation text, and no criticality/use labels |
| Existing Phase III workflows are destabilized | Additive evidence products; preserve existing scorer inputs and precision benchmarks |

## Recommended first increment

Use the SBIR.gov bulk award export for Phase 0 exact-link coverage and keep Phase 1's normalized
solicitation schema ready for future source-native records. This avoids blocking initial NSF linkage
analysis on the unavailable endpoint while preserving the distinction between award text and
government-authored solicitation text. Use the measured identifier coverage to select bounded NSF,
SAM.gov, and Grants.gov document cohorts before building the requirement classifier.

**Progress:** Phase 1 and both audit paths are implemented. The bulk award linkage adapter has
passed; Phase 0 document-source coverage is not complete.
