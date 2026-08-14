# STTR Partner-Type Classification — Seed-List Provenance

**Tier:** `exploratory`, non-citable. This file records the versioned, date-stamped provenance of
every seed list used by the deterministic partner-type classifier
([`design.md`](design.md#partner-type-classification)). Each list is treated as a **versioned
identity input**: a source, a capture date, and a content hash. Output-changing list updates get a
new version and a new [`amendments.md`](amendments.md) revision — never an edit in place — mirroring
the `sbir_etl.identity` primitives contract.

**Status:** scaffold. The lists below are **not yet captured**; sources and curation protocols are
[open questions O-5, O-6, O-7](open-questions.md). Do not run the classifier until each `version`
and `captured` field is populated and the owner has signed off on the sources.

## Seed lists

| List | Purpose | Proposed source | version | captured | sha256 |
|------|---------|-----------------|---------|----------|--------|
| `ffrdc_master` | `FFRDC` | NSF FFRDC Master List (official) | _pending_ | _pending_ | _pending_ |
| `ipeds_institutions` | `UNIVERSITY`, `COMMUNITY_COLLEGE` | IPEDS institutional directory (Carnegie/sector fields) | _pending_ | _pending_ | _pending_ |
| `research_hospitals` | `RESEARCH_HOSPITAL` | **owner to name** (e.g., AAMC-member / NIH-grantee teaching hospitals) — O-7 | _pending_ | _pending_ | _pending_ |
| `new_model_orgs` | `NEW_MODEL_ORG` | Curated FRO / new-model-org directory — curation protocol O-6 | _pending_ | _pending_ | _pending_ |
| `fiscal_sponsors` | sponsor-name masking detection | Curated known-science-org fiscal-sponsor names — O-6 | _pending_ | _pending_ | _pending_ |
| `nonprofit_registry` | `NONPROFIT_INSTITUTE`, `OTHER_NONPROFIT` | Public nonprofit status (e.g., IRS EO / research-institute directory) | _pending_ | _pending_ | _pending_ |

## Rules

1. **Every entry is dated and hashed.** A list with an empty `version`/`captured`/`sha256` is not
   usable; the classifier fails closed on an uncaptured list rather than silently skipping it.
2. **Matching uses the reused `sbir_etl.identity` org-name normalization** and
   `generic_token_guard`. No bespoke normalization.
3. **Fiscal-sponsor masking is explicit.** Both organization names and known sponsor names are
   matched; a miss on both is recorded as typed absence distinguishing `NO_MATCH` from
   `POSSIBLY_MASKED_BY_SPONSOR`. A masked-by-sponsor RI is `UNRESOLVED`, never silently dropped.
4. **Precedence on overlap** follows [O-5](open-questions.md) (proposed default: `FFRDC >
   RESEARCH_HOSPITAL > NEW_MODEL_ORG > UNIVERSITY > COMMUNITY_COLLEGE > NONPROFIT_INSTITUTE >
   OTHER_NONPROFIT`).
5. **Incompleteness is assumed.** These lists are incomplete by construction; an RI absent from all
   lists is `UNRESOLVED`, not `OTHER_NONPROFIT` by default.
