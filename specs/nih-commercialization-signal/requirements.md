# Requirements — NIH Commercialization-Signal Enrichment Source

> **Status:** Not yet started. Companion to
> [`specs/nih-reporter-enrichment/`](../nih-reporter-enrichment/requirements.md):
> RePORTER supplies the NIH grant spine (R43/R44/R41/R42 project numbers); this
> spec consumes that spine to attach an **external commercialization / transition
> signal** — a registered clinical trial or a grant-linked publication — to each
> NIH SBIR firm. Registered as a fourth source partition in
> [`specs/iterative_api_enrichment/`](../iterative_api_enrichment/requirements.md)
> alongside `usaspending` (live), `sam_gov`, and `nih_reporter`.
> Anchors inventory questions **B2 / B3** (commercialization & transition) and
> cross-reads **C2** (knowledge generation) in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B2/B3 — external, FPDS-independent commercialization signal for NIH SBIR firms (see L14-undercount note below); C2 cross-read for publication output
**Answers for:** SBA oversight, NIH SBIR program managers, commercialization analysts, pipeline engineers
**Complexity tier:** Relational → Inferential (signal detection + linkage-confidence inference)

---

## Motivation — why this is not the FPDS Phase III signal

The inventory's transition questions (B2/B3) and the Phase III universe both lean
on FPDS/USAspending contract coding to detect commercialization. That coding is
**structurally incomplete**: GAO-24-106398 [L14] and NASEM [L1][L3] document that
Phase III activity is undercounted, and the repo's own inventory flags this
(`docs/research-questions.md`, B3: *"How much undercount exists in Phase III
coding by agency?"*). For **NIH** firms specifically — drug, device, diagnostic,
and biologic developers — the meaningful transition is rarely a federal
follow-on contract at all; it is **a product entering human trials or generating
peer-reviewed evidence**.

ClinicalTrials.gov and PubMed/PMC are therefore an *external, independent*
readout of NIH SBIR commercialization that does not depend on FPDS Phase III
coding. A validation pass over a 380-firm stratified sample of the 12,223-firm
NIH SBIR universe confirmed the signal is real and cohort-discriminating:

| Signal | Phase II-reaching firms | Phase I-only firms |
|---|---|---|
| ≥1 registered ClinicalTrials.gov trial | **16.9 %** | 6.7 % |
| Trial reaches Phase 2+ | 6.5 % | 4.2 % |
| ≥1 affiliation-matched PubMed paper | **35.8 %** | 22.5 % |
| ≥1 paper via PI-author + affiliation (higher precision) | 23.8 % | 12.5 % |

The ~2.5× (trials) and ~1.6× (publications) enrichment in the Phase II-reaching
cohort is the behaviour a genuine commercialization signal should show. Exemplar
exact matches from a targeted lookup (sponsor field verified via trial details,
distinct from the 380-firm sample): **Delpor** DLP-114 risperidone implant (NIH
Phase II → NCT04418466), **SIGA Technologies** TPOXX/tecovirimat (→ Phase 3
NCT04971109, FDA-approved), **Phoenix Nest** MPS III programs (→
NCT05648851/NCT05825131).

---

## Done when

> A pipeline engineer can state: "For every NIH SBIR firm in
> `data/derived/nih_sbir_firm_universe.parquet`, the
> `NIHCommercializationSignalEnricher` attaches registered ClinicalTrials.gov
> trials and grant-linked PubMed/PMC publications, tagged with a two-tier linkage
> confidence (Tier 1 = NIH project number exact; Tier 2 = firm/PI fuzzy). Results
> land in `data/derived/nih_commercialization_signal.parquet` and the source is
> wired as the `nih_commercialization` partition in
> `data/state/enrichment_refresh_state.json`. The `ClinicalTrialsAPIClient` and
> `PubMedAPIClient` share the retry/backoff/raw-cache semantics of
> `SAMGovAPIClient` and `EdgarAPIClient`."

---

## Introduction

NIH is the second-largest SBIR funder (~49.8K HHS SBIR/STTR awards; ~37K under
the NIH branch; 12,223 distinct firms; $23.8B captured in the local award
spine). Its portfolio is dominated by therapeutics and medical devices, whose
commercialization path runs through **clinical trials** and **peer-reviewed
publication**, not federal procurement. Two public data sources capture that path:

- **ClinicalTrials.gov** (v2 API) — every US drug/biologic/device trial and most
  others, keyed by NCT ID, carrying sponsor, collaborator, phase, status, and
  (in `OrgStudyId` / funding metadata) sometimes the originating grant number.
- **PubMed / PMC** (NCBI E-utilities) — biomedical literature with author
  affiliations and, for PMC full text, structured **grant-funding metadata** that
  can carry the NIH project number.

This enricher links each NIH SBIR firm to both, producing a per-firm
commercialization-signal record. It depends on the `nih_reporter` partition
(companion spec) for the canonical R43/R44/R41/R42 **project numbers** that make
the high-precision Tier-1 linkage possible.

---

## Glossary

- **Commercialization signal**: A registered clinical trial or a grant-linked
  publication attributable to an NIH SBIR firm — an external, FPDS-independent
  readout of transition.
- **NCT ID**: ClinicalTrials.gov trial identifier (`NCT` + 8 digits).
- **PMID / PMCID**: PubMed / PubMed Central article identifiers; a PMCID implies
  full text (and structured grant metadata) is available.
- **NIH project number**: R43/R44 (SBIR Phase I/II), R41/R42 (STTR Phase I/II)
  activity-coded grant number from RePORTER; the Tier-1 join key.
- **Tier 1 (exact) linkage**: Match via NIH project number carried in a trial's
  funding field or a publication's grant metadata. Precision ~0.98.
- **Tier 2 (fuzzy) linkage**: Match via distinctive firm name (CT.gov sponsor /
  collaborator) or PI surname + affiliation (PubMed). Precision ~0.78
  (~0.61 for strict exact-name-only), recovers renamed / acquired / academic-led
  cases that Tier 1 misses.
- **False-negative modes**: corporate renaming, acquisition (sponsor = acquirer),
  academic/hospital-as-sponsor, device products absent from CT.gov, pre-trial
  lag, and generic-name ambiguity — see Requirement 4.
- **iterative_enrichment_refresh_job**: Dagster job (see
  `specs/iterative_api_enrichment/`) that refreshes each source partition on a
  rolling schedule under a freshness SLA.

---

## User Stories

**As an NIH SBIR program manager,** I want each firm tagged with whether its
funded work reached a registered clinical trial and at what phase, so that I can
measure transition without relying on the incomplete FPDS Phase III coding.

**As a commercialization analyst,** I want the trial/publication signal tagged
with a linkage confidence tier, so that I can separate high-precision
grant-number matches from fuzzy name matches when reporting transition rates.

**As a pipeline engineer,** I want the ClinicalTrials.gov and PubMed sources
refreshed on the same nightly schedule as USAspending and NIH RePORTER, so that
newly registered trials and publications surface within the 7-day freshness SLA.

---

## Requirements

### Requirement 1 — ClinicalTrials.gov API client

#### Acceptance Criteria

1. THE `ClinicalTrialsAPIClient` SHALL query the ClinicalTrials.gov v2 API
   (`https://clinicaltrials.gov/api/v2/studies`) by sponsor/collaborator name and
   by grant/`OrgStudyId` funding field.
2. THE client SHALL implement the same retry and exponential backoff semantics as
   `SAMGovAPIClient` / `EdgarAPIClient` (3 retries, 2s/4s/8s backoff) and respect
   ClinicalTrials.gov rate guidance.
3. THE client SHALL paginate via `pageToken` / `nextPageToken` and handle the
   total-count envelope so no trial near a page boundary is missed.
4. THE client SHALL cache raw responses under `data/raw/clinicaltrials/` before
   normalization, following the existing raw-cache pattern.

### Requirement 2 — PubMed / PMC API client

#### Acceptance Criteria

1. THE `PubMedAPIClient` SHALL query NCBI E-utilities (`esearch`/`esummary`/`efetch`)
   over three linkage paths: (a) firm name as `[Affiliation]`, (b) PI surname
   `[Author]` scoped by firm `[Affiliation]`, and (c) NIH project number as a
   `[Grant Number]` / grant-metadata match.
2. THE client SHALL convert PMIDs to PMCIDs (`elink`/idconv) to record full-text
   availability, and SHALL send a contact email in the request per NCBI E-utilities
   fair-access policy, sourced the same way as `EdgarAPIClient`'s User-Agent email.
3. THE client SHALL implement the retry/backoff and raw-cache semantics of the
   other API clients, caching under `data/raw/pubmed/`.
4. THE client SHALL respect the NCBI rate limit (3 req/s without an API key,
   10 req/s with one) via the shared rate limiter.

### Requirement 3 — Two-tier linkage & signal normalization

#### Acceptance Criteria

1. WHEN an NIH project number from the `nih_reporter` partition is present in a
   trial's funding field or a publication's grant metadata, THE System SHALL
   record the linkage as **Tier 1 (exact)** with confidence ~0.98.
2. WHEN no project-number match exists, THE System SHALL attempt **Tier 2 (fuzzy)**
   linkage via distinctive firm name (CT.gov sponsor or collaborator) or PI
   surname + affiliation (PubMed), and SHALL record the tier and the matched field.
3. THE System SHALL suppress a Tier-2 name match when the firm name is
   non-distinctive (generic-token guard) unless a project-number or PI
   corroboration is also present, to hold Tier-2 precision at the validated ~0.78.
4. THE System SHALL normalize records to include: `firm_id`, `firm_name_display`,
   `uei`, `nct_ids`, `trial_max_phase`, `trial_status_mix`, `pmids`,
   `pmcid_count`, `linkage_tier`, `linkage_field`, `signal_first_seen`,
   `last_refreshed_at`.
5. THE System SHALL persist normalized records to
   `data/derived/nih_commercialization_signal.parquet` with a
   `source = "nih_commercialization"` tag, keyed on `firm_id`.
6. WHEN a firm already has a record, THE System SHALL overwrite it and update
   `last_refreshed_at`, preserving the earliest `signal_first_seen`.

### Requirement 4 — False-negative accounting

#### Acceptance Criteria

1. THE System SHALL resolve firm identity through the UEI/DUNS cascade **before**
   name matching, so corporate renaming (e.g. Advantagene → Candel) and
   acquisition (e.g. Achillion → Alexion, where the trial sponsor is the acquirer)
   do not read as absent signal.
2. THE System SHALL search the trial **collaborator** field in addition to
   sponsor, so academic/hospital-led trials of a firm's product (e.g. Osel's
   LACTIN-V sponsored by University of Washington) are captured.
3. THE System SHALL record a `signal_absent_reason` for firms with no match, drawn
   from the catalogued modes (no-trial-device, pre-trial-lag, generic-name-ambiguity),
   so downstream analytics can distinguish true absence from linkage failure.
4. THE System SHALL treat absence conservatively: a firm with no detected signal
   is reported as *not-yet-observed*, never as *failed to commercialize*, because
   device/diagnostic products (510(k)/IVD) frequently never register on CT.gov.

### Requirement 5 — Iterative enrichment wiring

#### Acceptance Criteria

1. THE System SHALL register a `nih_commercialization` source partition in
   `data/state/enrichment_refresh_state.json`, tracking `last_attempt_at`,
   `last_success_at`, and `staleness_window_days` (default: 7), consistent with
   the other partitions.
2. THE System SHALL be invocable via the targeted-refresh CLI:
   `poetry run refresh_enrichment --source nih_commercialization --window <start>:<end>`.
3. WHEN the `nih_commercialization` source exceeds its staleness window, THE
   System SHALL emit a Dagster asset-check warning consistent with the E3 SLA
   monitoring requirement in `specs/iterative_api_enrichment/`.
4. THE System SHALL declare a dependency on the `nih_reporter` partition so that
   project-number-based Tier-1 linkage runs against current RePORTER data.

---

## Validation evidence (2026-07-01 sample pass)

- Universe: 12,223 distinct NIH SBIR firms (`data/derived/nih_sbir_firm_universe.parquet`);
  5,789 reach Phase II.
- Sample: 380 firms (260 Phase II-reaching, 120 Phase I-only), stratified.
- ClinicalTrials.gov (sponsor path): 44/260 Phase II firms (16.9 %) with ≥1 trial
  vs 8/120 (6.7 %) Phase I-only.
- PubMed: 93/260 (35.8 %) affiliation-matched vs 27/120 (22.5 %); 64 % of sampled
  matched papers carry PMC full text.
- Precision audit (18 matched firms): 78 % true attributions (61 % strict
  exact-sponsor-name), false positives driven by generic firm names and CRO roles.
- Two-tier rubric and false-negative modes: see
  `docs/research/` linkage-audit artifacts and Requirement 4.
