# STTR Partner-Type Classification — Seed-List Provenance

**Tier:** `exploratory`, non-citable. This file records the versioned, date-stamped provenance of
every seed list used by the deterministic partner-type classifier
([`design.md`](design.md#partner-type-classification)). Each list is treated as a **versioned
identity input**: a source, a capture date, and a content hash. Output-changing list updates get a
new version and a new [`amendments.md`](amendments.md) revision — never an edit in place — mirroring
the `sbir_etl.identity` primitives contract.

**Status:** O-5 (precedence order), O-6 (new-model orgs / fiscal sponsors), and O-7 (research
hospitals) are RESOLVED (see [`open-questions.md`](open-questions.md)). Task 1.1 data capture is
**mostly complete**: 5 of 6 lists below have a real `version`/`captured`/`sha256`. `research_hospitals`
is honestly left `_pending_` — see [Capture notes](#capture-notes) for why and what a follow-up needs.
Do not run the classifier until every `version` and `captured` field is populated; a partially
captured provenance table blocks classifier implementation (task 1.3) on the still-pending row, per
the fail-closed rule below.

## Seed lists

| List | Purpose | Proposed source | version | captured | sha256 |
|------|---------|-----------------|---------|----------|--------|
| `ffrdc_master` | `FFRDC` | NSF FFRDC Master List (official) | `2026-08-14` | `2026-08-14` | `29ae0e3ebb4a7ccb8453b95c17ccb1b9210e906600cb3d8af066374c9118195f` (raw `ffrdc-2026.xlsx`); `59e9acaa68ca54811381a7f9813055498e179ce1a05f31826b0d85a1f92b9c94` (derived `ffrdc_master.csv`) |
| `ipeds_institutions` | `UNIVERSITY`, `COMMUNITY_COLLEGE` | IPEDS institutional directory (Carnegie/sector fields) | `2026-08-14` (IPEDS HD2024, Fall 2024 collection) | `2026-08-14` | `d7b20e136fd971d7dce8ad6ec9b7002f0f281f133959f2c3a6c089a5a4610fe5` (`HD2024.csv`) |
| `research_hospitals` | `RESEARCH_HOSPITAL` | **NIH RePORTER** hospital-class grantees, non-university scope, + **AAMC COTH** cross-check (O-7 resolved) | _pending_ | _pending_ | _pending_ |
| `new_model_orgs` | `NEW_MODEL_ORG` | Curated: **Convergent Research** FRO portfolio + known independents (Arc, Arcadia, Astera, Speculative Technologies, …), verified at capture (O-6 resolved) | `2026-08-14` | `2026-08-14` | `81c44c7deaae34bb820bb22c313525cf579ac2c2a9539a1912259f4f2c7ffe51` (`new_model_orgs.json`) |
| `fiscal_sponsors` | sponsor-name masking → `POSSIBLY_MASKED_BY_SPONSOR` | **Convergent Research, Astera** + generic 501(c)(3) sponsors (Players Philanthropy Fund, Hopewell Fund, Social Finance, RCSA), verified at capture (O-6 resolved) | `2026-08-14` | `2026-08-14` | `4de2d9c70c7cda999c664fdcb5ad131ca5f00f52444e7781af3f14957fee3a82` (`fiscal_sponsors.json`) |
| `nonprofit_registry` | `NONPROFIT_INSTITUTE`, `OTHER_NONPROFIT` | IRS Exempt Organizations Business Master File Extract (EO BMF), all 4 regional extracts | `2026-08-14` | `2026-08-14` | `674c26b2a57bb7317d71a54ce65be0d6913e5027a0d6294435059037ad2f6d75` (`eo_bmf.manifest.json`; per-file hashes of the 4 raw regional extracts inside) |

Captured files live under
[`data/reference/sttr_partner_type_seed_lists/`](../../data/reference/sttr_partner_type_seed_lists/),
one subdirectory per list.

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

## Capture notes

Task 1.1 (data capture) status per list, as of 2026-08-14. All captured files live under
[`data/reference/sttr_partner_type_seed_lists/<list_name>/`](../../data/reference/sttr_partner_type_seed_lists/).

### `ffrdc_master` — captured

Source: NSF National Center for Science and Engineering Statistics, Master Government List of
FFRDCs, February 2026 edition —
[`https://ncses.nsf.gov/879/assets/0/files/ffrdc-2026.xlsx`](https://ncses.nsf.gov/879/assets/0/files/ffrdc-2026.xlsx).
Retrieved as-is (`ffrdc-2026.xlsx`, 42 active FFRDCs, 4 sheets including a `Historical`
decertified/renamed tab); a derived `ffrdc_master.csv` (name, agency, sub-agency, administering
organization, admin type, state, activity type) is also committed for convenience. Both files and
both hashes are recorded in the table above.

### `ipeds_institutions` — captured

Source: NCES IPEDS Data Center, `HD2024` Institutional Characteristics file (Fall 2024 collection)
— [`https://nces.ed.gov/ipeds/datacenter/data/HD2024.zip`](https://nces.ed.gov/ipeds/datacenter/data/HD2024.zip).
Downloaded and unzipped in full (6,072 postsecondary institutions, all fields including `SECTOR`,
`ICLEVEL`, `CONTROL`, and the Carnegie Classification fields `C21BASIC`/`CARNEGIEIC`/`CARNEGIERSCH`
needed to distinguish `UNIVERSITY` from `COMMUNITY_COLLEGE` at classifier-build time). Committed as
`HD2024.csv`; the zip is not retained (its sha256 is `d98425c123d7c0e872aec6e83960dfb501884818bf17385c340790f3d1f28345`
for reproducibility, should a future capture need to diff against the original archive).

### `new_model_orgs` and `fiscal_sponsors` — captured (curated allowlists)

Both curated per the O-6 resolution. Each entry in `new_model_orgs.json` / `fiscal_sponsors.json`
carries its own `source_url` and `verified_at` date, plus a `verification_note` documenting exactly
what was confirmed. Two caveats surfaced during verification and are recorded inline rather than
silently resolved (O-6 named these entries; this capture task does not re-litigate a frozen
resolution, but does not hide what verification found either):

- **Arcadia Science** (`new_model_orgs`): multiple independent public sources (Crunchbase, PitchBook,
  a founder's own account) describe it as a **for-profit** institute, not a 501(c)(3) nonprofit —
  unlike every other entry on the list. It is a real, genuine "new research model" organization
  matching the O-6 description, but its for-profit structure does not fit the nonprofit-institution
  framing used elsewhere in the RI partner-type vocabulary. Flagged for the spec owner before this
  entry drives a `NEW_MODEL_ORG` label on a live award.
- **Social Finance** and **Research Corporation for Science Advancement** (`fiscal_sponsors`): both
  confirmed as real 501(c)(3) organizations, but no public source was found at capture documenting
  either one specifically acting as a fiscal sponsor for a science/research project (RCSA's public
  profile is a grant-making foundation; Social Finance's is impact investing / outcomes funds — fiscal
  sponsorship is not the activity either is publicly known for, unlike Players Philanthropy Fund and
  Hopewell Fund, whose fiscal-sponsor role is directly confirmed). Flagged for the spec owner to
  confirm directly before either entry is relied on to detect `POSSIBLY_MASKED_BY_SPONSOR`.

### `nonprofit_registry` — captured (hash-anchored, not committed in full)

Source: IRS Exempt Organizations Business Master File Extract (EO BMF), all 4 regional CSV
extracts — `https://www.irs.gov/pub/irs-soi/eo{1,2,3,4}.csv` (IRS publishes a refreshed extract
monthly, second Tuesday). Downloaded in full: 1,957,340 total data rows, ~336 MB combined. This
repository is not Git-LFS-enabled (largest previously tracked file was under 1 MB), so — following
the existing precedent in
[`docs/research/agency-private-capital-phase1-nsf.manifest.json`](../../docs/research/agency-private-capital-phase1-nsf.manifest.json)
for the 394 MB `award_data.csv` — the raw extracts are **not** checked into git. Each file's exact
source URL, retrieval date, byte size, row count, and sha256 is instead recorded in the committed
[`eo_bmf.manifest.json`](../../data/reference/sttr_partner_type_seed_lists/nonprofit_registry/eo_bmf.manifest.json);
that manifest's own sha256 is the value in the table above. A future classifier build (task 1.3)
must re-download each file by URL and verify its sha256 against the manifest before use; a hash
mismatch means the IRS has republished the extract and this row's version must be superseded, not
silently trusted.

### `research_hospitals` — left `_pending_`

O-7 names two sources: **NIH RePORTER** hospital-class grantees (spine) and **AAMC COTH** (coverage
cross-check). Both were investigated and both are currently blocked for reasons that would produce a
wrong list if worked around rather than fixed, so this row is left honestly `_pending_` instead of
being filled with a fabricated or silently-scoped-down capture:

1. **NIH RePORTER's `org_types` filter does not isolate hospital-class organizations.** Querying the
   public v2 Project API (`POST https://api.reporter.nih.gov/v2/projects/search`,
   `criteria.org_types: ["HOSPITAL"]`) returns project records whose organization is frequently a
   **university** (e.g. University of Southern California, University of Illinois at Chicago) mixed
   in with genuine freestanding hospitals (e.g. Dana-Farber Cancer Institute). The filter appears to
   match at some sub-organization/performance-site level within multi-component grants rather than
   guaranteeing the primary awardee organization itself is hospital-typed. Naively aggregating unique
   organizations from this filter would misclassify universities as `RESEARCH_HOSPITAL`, which is
   exactly the failure mode O-7's `UNIVERSITY > RESEARCH_HOSPITAL` precedence and "exclude
   university-owned AMCs" construction rule exist to prevent. There is no separate NIH-published bulk
   file of *organizations* (only per-project records), so a clean org-level "is this a hospital"
   field was not found via the public API.
2. **AAMC COTH no longer exists.** The Council of Teaching Hospitals (COTH) was dissolved on
   2024-07-01 and succeeded by the Council of Academic Health System Executives (CAHSE, ~400
   members). No public, unauthenticated bulk directory of CAHSE members was found; the AAMC's member
   directory requires an AAMC-affiliated login ("My Engagement"). O-7's named cross-check source is
   therefore not currently capturable as a public downloadable list.

**What a follow-up needs:** either (a) NIH's Institution Profile File (IPF) system is confirmed to
expose an org-level type/classification field via a different endpoint or a bulk IPF export (the
public Project API does not appear to), enabling a clean aggregate-and-dedupe over NIH RePORTER data
with a real hospital-vs-university distinction; or (b) direct outreach to AAMC for CAHSE member-list
access (or a different public teaching-hospital directory, e.g. a state-level or CMS-published
teaching-hospital list) to replace the now-defunct COTH cross-check named in O-7. Either path is
outside the scope of this data-capture task and needs owner input before proceeding — this is a
capture blocker, not a classifier-design question, so it does not require reopening the frozen O-7
resolution, only executing it against a source that still exists.
