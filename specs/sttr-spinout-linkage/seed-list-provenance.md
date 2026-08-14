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
| `research_hospitals` | `RESEARCH_HOSPITAL` | **NIH RePORTER** hospital-class grantees, non-university scope, + **AAMC COTH** cross-check (O-7 resolved) | _pending_ | _pending_ | _pending_ |
| `new_model_orgs` | `NEW_MODEL_ORG` | Curated: **Convergent Research** FRO portfolio + known independents (Arc, Arcadia, Astera, Speculative Technologies, …), verified at capture (O-6 resolved) | _pending_ | _pending_ | _pending_ |
| `fiscal_sponsors` | sponsor-name masking → `POSSIBLY_MASKED_BY_SPONSOR` | **Convergent Research, Astera** + generic 501(c)(3) sponsors (Players Philanthropy Fund, Hopewell Fund, Social Finance, RCSA), verified at capture (O-6 resolved) | _pending_ | _pending_ | _pending_ |
| `nonprofit_registry` | `NONPROFIT_INSTITUTE`, `OTHER_NONPROFIT` | Public nonprofit status (e.g., IRS EO / research-institute directory) | _pending_ | _pending_ | _pending_ |

## Rules

1. **Every entry is dated and hashed.** A list with an empty `version`/`captured`/`sha256` is not
   usable; the classifier fails closed on an uncaptured list rather than silently skipping it.
2. **Matching uses the reused `sbir_etl.identity` org-name normalization** and
   `generic_token_guard`. No bespoke normalization.
3. **Fiscal-sponsor masking is explicit.** Both organization names and known sponsor names are
   matched; a miss on both is recorded as typed absence distinguishing `NO_MATCH` from
   `POSSIBLY_MASKED_BY_SPONSOR`. A masked-by-sponsor RI is `UNRESOLVED`, never silently dropped.
4. **Precedence on overlap** follows [O-5](open-questions.md) (revised by O-7: `FFRDC >
   NEW_MODEL_ORG > UNIVERSITY > RESEARCH_HOSPITAL > COMMUNITY_COLLEGE > NONPROFIT_INSTITUTE >
   OTHER_NONPROFIT`; `UNIVERSITY > RESEARCH_HOSPITAL` fixed by O-7).
5. **Incompleteness is assumed.** These lists are incomplete by construction; an RI absent from all
   lists is `UNRESOLVED`, not `OTHER_NONPROFIT` by default.

## How `NEW_MODEL_ORG` is determined

`NEW_MODEL_ORG` has **no registry or legal definition** (unlike `FFRDC`, `UNIVERSITY`,
`COMMUNITY_COLLEGE`). No dataset field says "I am a focused research organization," so the label
**cannot** be derived by a rule over award data — it is an **allowlist match only**:

- **Path A — direct list match (the only path that yields the label).** The RI name on the award
  spine is normalized (`sbir_etl.identity` org normalization + `generic_token_guard`) and matched
  against the dated `new_model_orgs` list. A match → `NEW_MODEL_ORG`. No fuzzy "new-model-ness"
  heuristic (e.g., "nonprofit + founded post-2015 + single research mission") is used; that would be
  the kind of inference this deterministic classifier forbids in v1.
- **Path B — fiscal-sponsor match (does NOT yield `NEW_MODEL_ORG`).** If the RI name matches a
  `fiscal_sponsors` entry, the true research org is masked and unknown. The classifier records
  `UNRESOLVED` with typed absence `POSSIBLY_MASKED_BY_SPONSOR` — it does **not** manufacture a
  `NEW_MODEL_ORG` label it cannot confirm.

Consequences to report honestly: (a) the label is **high-precision, low-recall by design** — an FRO
absent from the capture-dated list classifies as `OTHER_NONPROFIT`, not `NEW_MODEL_ORG`; (b) because
FROs are young and most likely to appear (if at all) under a sponsor's EIN, the **`POSSIBLY_MASKED_BY_SPONSOR`
count is expected to carry more signal than the confirmed `NEW_MODEL_ORG` count**, and both are
reported for the headline readout, with masked candidates flagged for manual follow-up rather than
auto-labeled.
