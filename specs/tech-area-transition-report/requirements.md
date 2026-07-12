# Tech-Area Transition Report — Requirements

> **Status:** In progress (v1 cohort parameterization)
> Anchors inventory questions **B** (commercialization / Phase II→III pathways) and
> **C1** (cross-agency CET portfolio) in [docs/research-questions.md](../../docs/research-questions.md).
> Coordinates with [dark-majority-resolution](../dark-majority-resolution/requirements.md)
> (that spec owns deficiency *treatments*; this one owns parameterized *cohort → signal → report skeleton*).

**Research question anchor:** B — technology-area Phase II→III commercialization pathways;
C1 — CET-area portfolio composition
**Answers for:** SBIR program managers, OSTP / NSET-style technology-area audiences, policy analysts
**Complexity tier:** Descriptive → Relational

---

## Done when

> An analyst can run `uv run python scripts/data/build_tech_area_cohort.py --area <cet_id>`
> for any configured technology area and obtain: (1) a Method-A keyword Phase II cohort CSV,
> (2) Method-A ∩ CET-taxonomy overlap (containment + Jaccard), (3) a transition-channel
> summary table when shared signal artifacts are present, and (4) a short methodology stub.
> Running `--area quantum_information_science` and `--area hypersonics` produces non-empty
> cohorts; a quantum false-positive spot-check confirms `negative_keywords` (quantum dot /
> quantum well / etc.) are applied.

---

## Background

PR #428 demonstrated a reusable *pattern* for technology-area commercialization reporting on
nanotechnology, but the implementation hardwires nanotech (`KEYWORD_PATTERNS`, B82 CPC,
NNI Table 5, `nano_*` paths). The dark-majority-resolution spec already asserts the pattern
is technology-agnostic; that claim is unverified. Parameterizing cohort definition — and
proving it on quantum (high contamination risk) and hypersonics (sparse / keyword-quality
risk) — is the cheapest way to stop the pattern calcifying as a nanotech one-off.

---

## Glossary

- **`cet_id`** — canonical area key from `config/cet/taxonomy.yaml` (e.g.
  `quantum_information_science`). Report paths and configs use this; no parallel ID namespace.
- **Method A** — keyword/regex cohort over award title + abstract (primary definition).
- **Method B** — CET-taxonomy keyword cohort for the same `cet_id` (triangulation, not primary).
- **Method C** — USPTO CPC-class cohort (optional; empty when no prefixes configured).
- **Keyword pack** — optional richer Method-A regex list that overrides thin taxonomy keywords.

---

## Requirements

### Requirement 1 — Area config keyed by `cet_id`

**User story:** As a policy analyst, I want each technology area defined in one YAML file
keyed by `cet_id`, so that adding a new area does not require editing pipeline scripts.

#### Acceptance Criteria

1. WHEN an area YAML exists under `config/transition_reports/<area_id>.yaml`, THE System SHALL
   load Method-A patterns, optional negatives, optional CPC prefixes, and report metadata from it.
2. WHEN `keyword_pack` is absent and `cet_id` is set, THE System SHALL fall back to
   `taxonomy.yaml` keywords for that `cet_id`, applying `negative_keywords` from taxonomy
   and/or the area YAML.
3. WHEN optional fields (`cpc_prefixes`, `external_reference`, `sector_registries`, `cet_id`)
   are absent, THE System SHALL proceed with those methods empty — not error.
4. WHEN `area_id` equals a taxonomy `cet_id`, Method B SHALL default to that area's taxonomy
   keywords. Nanotechnology is the documented exception (`cet_id: null` + `method_b_terms`).

### Requirement 2 — Parameterized cohort build

**User story:** As an SBIR program manager, I want a single CLI that builds a Phase II cohort
for any configured area, so that I can compare pathway visibility across CET areas without
nanotech-specific scripts.

#### Acceptance Criteria

1. WHEN invoked with `--area <area_id>`, THE System SHALL write outputs under
   `data/reports/<area_id>/` (keyword cohort CSV at minimum).
2. THE System SHALL report Method-A size, Method-B (taxonomy) size, and Method-A ∩ Method-B
   containment and Jaccard on unique award IDs.
3. WHEN shared signal artifacts exist (prospect digest, Form D high-conf, M&A enrichment),
   THE System SHALL enrich the keyword cohort and print the channel table
   (FPDS P3, any federal obligation, M&A, Form D, union) with the same caveats as the nano
   pipeline (union ≠ transition rate).
4. WHEN those artifacts are missing, THE System SHALL still emit the cohort and overlap
   stats, and SHALL state which signal inputs were absent (no silent zero-rate methodology).

### Requirement 3 — Quantum and hypersonics validation

**User story:** As a pipeline engineer, I want quantum and hypersonics to run through the
same path as nanotech’s Method A, so that we know the pattern generalizes before wiring
more dark-majority workstreams to nano-only paths.

#### Acceptance Criteria

1. WHEN built for `quantum_information_science`, THE Method-A cohort SHALL be non-empty.
2. WHEN a random sample of ≥15 quantum Method-A awards is inspected, awards whose *only*
   quantum-adjacent hit is a negative term (quantum dot / well / mechanics / chemistry /
   field theory) SHALL NOT appear in the cohort.
3. WHEN built for `hypersonics`, THE Method-A cohort SHALL be non-empty, and the keyword pack
   SHALL NOT use bare `supersonic` as a positive match (too broad; taxonomy keeps it for
   CET Method B only).
4. Results (sizes, overlap, channel rates if available, spot-check notes) SHALL be recorded
   in `specs/tech-area-transition-report/validation.md`.

### Requirement 4 — Boundary with dark-majority-resolution

**User story:** As a maintainer, I want a clear ownership line between this spec and
dark-majority-resolution, so that parameterization work is not duplicated.

#### Acceptance Criteria

1. THIS spec SHALL own: area config, Method A/B(/C) cohort construction, shared-signal
   enrichment for the report skeleton, methodology stub, validation on new areas.
2. `dark-majority-resolution` SHALL own: WS1–WS6 deficiency treatments, survey design,
   capture-recapture bounds on dark populations.
3. Downstream dark-majority scripts MAY later accept `--area <cet_id>`; that migration is
   OUT of scope for this spec’s v1.

---

## Explicitly out of scope (v1)

- API-only rebuild of SBIR / EDGAR / Form D / USPTO bulk inputs
- Full findings-narrative generation (§5D/§5E-style prose)
- Dagster asset wiring
- Dark-majority WS1–WS6 for every area
- NNI-equivalent external reconciliation for quantum / hypersonics
- Method C as a gate for test areas (may be empty)
- Renaming or deleting the existing `nano_*` scripts (they remain the nanotech reference
  implementation until a follow-up migrates them onto this path)

---

## Dependencies

- `config/cet/taxonomy.yaml` (`cet_id`, keywords, negative_keywords) — EXISTS
- PR #428 nanotech pipeline (`build_nano_cohort.py` signal enrichment helpers) — IN PROGRESS
- Shared artifacts: `award_data.csv`, optional digest / Form D / M&A JSONL — EXISTS in prod;
  local runs may lack signal files
- `dark-majority-resolution` — parallel; boundary only — IN PROGRESS
