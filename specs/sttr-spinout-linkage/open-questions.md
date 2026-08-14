# STTR Spinout–Subcontract Linkage — Open Questions

Decisions reserved for the repository owner. **The classification criteria in
[`design.md`](design.md) cannot be frozen, and no implementation is authorized, until these are
resolved.** Each is stated as a decision with a proposed default; the default is a recommendation,
not a resolution. When the owner decides, record the resolution as a numbered revision in
[`amendments.md`](amendments.md) and only then freeze.

Nothing here is resolved unilaterally. This file exists precisely to keep these open.

---

## O-0 — The `nih-commercialization-linkage` kernel does not exist

**Finding.** The brief instructs reuse of a `nih-commercialization-linkage` kernel exposing
`resolve_identity`, `classify_linkage`, `generic_token_guard`, and `signal_absent_reason`, and to
"extend the cascade, do not re-implement it." **None of these functions, and no such spec or
module, exist in the repository** (verified by repo-wide search). The real reusable substrate is:
- `sbir_etl.identity` (primitives tier): `normalize_company_name`, `company_name_similarity`,
  versioned `CompanyNameProfile` / `CompanyNameMetric`, and `RecoveryStatus` (the typed-absence
  `StrEnum` template) — org-name only; **no person-name primitive exists**.
- The graph-governance `DimensionStatus` enum and `CANDIDATE` assertion contract (ADR-005).

**Decision:** (a) build the four kernel functions as **new `exploratory`-tier code in this spec**,
grounded in the primitives above (`signal_absent_reason` modeled on `RecoveryStatus`;
`generic_token_guard` built from the existing `SUFFIX_TOKENS` generic-token stripping; person-name
normalization net-new); **or** (b) split the kernel into its own upstream spec (possibly a
`primitives`-tier promotion) that this spec then consumes.
**Proposed default:** (a) — build here at exploratory tier; promote to a shared primitive later if
a second consumer appears. Do not block RQ1 on a primitive-promotion project.

## O-1 — Are founders in scope for D2, or only the PI?

The person trail (D2) can match the PI alone, or the PI plus named founders/officers. Founders
widen recall (many spinouts are founded by a non-PI academic) but raise false-positive risk and
data-sourcing cost.
**Proposed default:** PI in v1; founders as a labeled extension after the adjudication sample shows
the PI-only recall floor.

## O-2 — The ±N-year authorship window for D2

How many years around the award date may an RI-affiliated authorship record fall and still count?
**Proposed default:** ±3 years. Report ±1 / ±2 / ±3 / ±5 sensitivity in the review artifact.

## O-3 — Tier thresholds (what is "exact" vs. "fuzzy")

The `company_name_similarity` cutoff separating `SPINOUT_T1` (exact) from `SPINOUT_T2` (fuzzy), and
the corroboration rule for T2 (which dimension pairs count as "independent").
**Proposed default:** exact = normalized-equality or verified identifier match (ORCID, exact
UEI↔RI); fuzzy = `company_name_similarity ≥ [cutoff]` under `CompanyNameMetric.JARO_WINKLER` with
`generic_token_guard` passing. Cutoff to be set from the adjudication sample, not guessed.

## O-4 — The v1 phrase lexicon (D5)

The exact deterministic phrase list ("spun out of", "licensed from", "founded by Professor …", and
variants) and whether it ships in v1 at all.
**Proposed default:** ship a small, frozen, hand-curated lexicon in v1; an ML text classifier is
future work, not v1. The lexicon version is part of the freeze.

## O-5 — Partner-type precedence order

When seed lists overlap (e.g., a university-administered FFRDC), which label wins?
**Proposed default (revised by O-7):** `FFRDC > NEW_MODEL_ORG > UNIVERSITY > RESEARCH_HOSPITAL >
COMMUNITY_COLLEGE > NONPROFIT_INSTITUTE > OTHER_NONPROFIT`. The `UNIVERSITY > RESEARCH_HOSPITAL`
direction is **fixed by the O-7 resolution** (university-owned academic medical centers stay
`UNIVERSITY`; the hospital list is built to exclude them, so the two rarely overlap in practice).
FFRDC (federal master list) remains most authoritative. **Still open:** owner confirmation of the
full ordering.

## O-6 — FRO / new-model-org list curation and fiscal-sponsor coverage

The curation protocol for the new-model-org (focused research organization and similar) seed list,
and the coverage of the known-fiscal-sponsor name list used to detect `POSSIBLY_MASKED_BY_SPONSOR`.
**Proposed default:** seed from public FRO directories and known science-org fiscal sponsors, each
entry date-stamped with a source URL in [`seed-list-provenance.md`](seed-list-provenance.md);
treat the list as versioned and incomplete-by-construction.

**RESOLVED (2026-08-14):** No government master list for new-model orgs exists, so this is a
**curation protocol, not a source pick.** `NEW_MODEL_ORG` seed = Convergent Research's public FRO
portfolio plus known independents (Arc Institute, Arcadia Science, Astera Institute, Speculative
Technologies, and similar), each entry date-stamped with a source URL and **verified at capture**,
treated as incomplete-by-construction. The **fiscal-sponsor list is the load-bearing piece for the
`NEW_MODEL_ORG` vs. `OTHER_NONPROFIT` breakdown** (it is what distinguishes a confirmed new-model
org from one masked behind a sponsor's name): seed = science-specific sponsors (Convergent Research,
Astera) plus generic 501(c)(3) fiscal sponsors used by science orgs (Players Philanthropy Fund,
Hopewell Fund, Social Finance, Research Corporation for Science Advancement — verify each at
capture). Scope note: this list only distinguishes `NEW_MODEL_ORG` from `OTHER_NONPROFIT`; the
headline "non-university, non-FFRDC nonprofit" detection does **not** depend on it — a
sponsor-masked FRO still classifies as a nonprofit and counts toward the headline sum regardless of
whether its sponsor is on this list. Sources recorded in
[`seed-list-provenance.md`](seed-list-provenance.md); data capture remains pending.

## O-7 — Research-hospital list source

Which authoritative list defines `RESEARCH_HOSPITAL` (e.g., a teaching-hospital / AAMC-member set,
or an NIH-grantee hospital set)?
**Proposed default:** owner to name the authoritative source; record its version and date in the
provenance file.

**RESOLVED (2026-08-14):** `RESEARCH_HOSPITAL` is defined **narrowly** as a freestanding nonprofit
research hospital that is **not** the degree-granting university. Spine source = **NIH RePORTER
hospital-class grantees** (public, downloadable, versioned, research-active by construction), scoped
to non-university institutions, with **AAMC COTH** as a coverage cross-check. Precedence is set
`UNIVERSITY > RESEARCH_HOSPITAL` (university-owned academic medical centers stay `UNIVERSITY`), and
the hospital list is **built to exclude university-owned AMCs** so no overlap needs arbitration.
This resolution fixes the precedence direction in [O-5](#o-5--partner-type-precedence-order).
Sources recorded in [`seed-list-provenance.md`](seed-list-provenance.md); data capture remains pending.

## O-8 — Bayh-Dole / licensing literature anchor

The literature map has no Bayh-Dole or licensing citation. D3 relies on Bayh-Dole
government-interest statements.
**Proposed default:** add a statutory Bayh-Dole anchor (35 U.S.C. §§ 200–212) and, if desired, a
licensing citation, as a new `[L#]`. Do **not** take `[L49]`: that slot is conditionally
reserved for an unverified Jones & Fearon deposit (see the literature-map audit note in
[`docs/research-questions.md`](../../docs/research-questions.md)). The next unreserved slot
is `[L50]`. Do not cite Bayh-Dole informally until the anchor is added.

## O-9 — Does RQ2 ship in this spec or its own?

The matched outcome comparison (design in [`design.md`](design.md#rq2--matched-outcome-comparison-design-only))
is design-only here. It can stay as a design section, or graduate to its own spec once RQ1 labels
exist and are validated.
**Proposed default:** keep RQ2 as a design section here; spin it into its own spec at
implementation time, so this spec stays scoped to classification.

## O-10 — Embedding choice for RQ2 topic-similarity matching

Which embedding produces the topic-similarity matching key (e.g., the repository's
ModernBERT-Embed used elsewhere, or another).
**Proposed default:** reuse the existing ModernBERT-Embed path used by the analysis layer, for
consistency with prior transition work; decide at RQ2 implementation, not now.

## O-11 — Partner-type: this spec or its own primitive?

Partner-type classification shares the D1 spine with RQ1 but is conceptually independent.
**Proposed default (from the addendum):** ship it in this spec — it shares the spine. Promote to
its own primitive only if a second consumer appears.

## O-12 — Bayh-Dole government-interest statement data source

**The gap.** The [D3 evidence-dimension row](design.md#evidence-dimensions) names "Bayh-Dole
government-interest statements" as a source, and the [Order-1 cascade
rule](design.md#classification-cascade-rq1) treats a **recorded license from the RI to the SBC**
(`D3.recorded_license_RI_to_SBC`) as `SPINOUT_T1` evidence — but **no source for that data was ever
named**, in `design.md`, `coverage-memo.md`, or anywhere else in the spec. This is distinct from
[O-8](#o-8--bayh-dole--licensing-literature-anchor), which is only about adding a **statutory
citation** to the literature map; O-8 does not address where the government-interest-statement
*data* would come from. This question is research/sourcing only — no ingestion, fetch, or parsing
is authorized here or before the Revision 1 freeze.

**Candidate sources researched (2026-08-14):**

- **NIH/interagency iEdison (now NIST-operated, transferred from NIH August 2022).** The system of
  record for Bayh-Dole subject-invention and utilization-report filings, used across NIH, NSF, DoD,
  DOE, and ~30 other agencies. **Not obtainable even in principle, not merely account-gated.** Three
  independent barriers stack:
  1. **Statutory confidentiality.** The Bayh-Dole Act authorizes agencies to withhold
     invention-disclosure data from the public, and utilization/licensing-effort information is
     treated as commercial and financial information that is privileged, confidential, and not
     subject to disclosure — this is a FOIA-exemption-grade bar, not just a login wall. A FOIA
     request for licensee-level data would predictably be denied on this basis; see the SBIR/STTR
     data-rights briefing on this point
     ([Patent and Data Rights under SBIR/STTR Awards](https://www.orau.gov/2018SBIRPhase2/presentations/Mike_Dobbs_SBIR-STTR_Phase_I_PI_Meeting_Dec_2018.pdf)).
  2. **Account access is organization-scoped, not query access.** Web access requires an
     organization-level iEdison account with login.gov authentication
     ([NIST iEdison FAQ](https://www.nist.gov/iedison/iedison-frequently-asked-questions-faqs)); an
     authenticated user sees their own organization's filings, not a cross-agency corpus.
  3. **The API is a system-to-system filer interface, not a research read endpoint.** The
     [iEdison API](https://www.nist.gov/iedison/iedison-api) requires a system account and a
     NIST-issued PKI client certificate
     ([Setting up your API Account](https://www.nist.gov/iedison/setting-your-api-account)) — built
     for an institution's own grants-management system to submit/query *its own* reports, not for
     third-party bulk read access.

  **Verdict: Not obtainable — a statutory and architectural dead end, not a temporary access
  friction.** Even with credentials, there is no path from one organization's account to the
  government-wide STTR population this cascade needs. A recent GAO report on iEdison data,
  [GAO-26-107971](https://files.gao.gov/reports/GAO-26-107971/index.html) ("Funding Recipients Keep
  Most Federally Funded Inventions, but Some Cited Reporting Challenges"), analyzes FY2020–2024
  iEdison filings across 30 agencies but publishes only **aggregate narrative statistics** (e.g.,
  ~56% title-retention rate) — no individual-invention or license-level microdata release, and it
  does not name a licensee, so it would not help even if released.
- **PatentsView / USPTO Open Data Portal `government_interest` extraction.** PatentsView runs an
  NER pipeline over the "GOVERNMENT INTERESTS" clause in granted-patent front matter, resolving
  matches against a list of 300+ U.S. government organizations
  ([extraction-process methodology](https://patentsview.org/government-interest/extraction-process);
  [pv-government-interest](https://github.com/PatentsView/pv-government-interest)). This is
  **public, bulk-downloadable, patent-level** structured data — the cleanest-sounding candidate.
  **But it captures the wrong thing for D3's stated use**: the extracted fields are the **funding
  agency and contract/grant award number** named in the clause (e.g., "awarded by NIH, grant
  R01..."), not a license grantee. It confirms federal funding nexus, not an RI→SBC license.
  PatentsView migrated into the USPTO Open Data Portal (`data.uspto.gov`) on March 20, 2026, and its
  standalone search API was shut down
  ([USPTO transition notice](https://www.uspto.gov/subscription-center/2026/patentsview-migrating-uspto-open-data-portal-march-20)).
  As of this writing, ODP bulk/API access remains free but now requires a registered USPTO.gov
  account with MFA (required starting June 18, 2026, with additional profile fields required
  starting August 18, 2026 per ODP onboarding notices) — free registration, not open-anonymous, and
  a tightening requirement worth re-checking before any future capture. **Verdict: Feasible with
  work, but answers the wrong question** — usable for confirming federal-funding nexus, not license
  evidence.
- **USPTO assignment bulk data already in `data/raw/uspto/assignments/`.** Directly inspected the
  local files (not fetched new data). `assignment_conveyance.csv.zip` classifies every recorded
  conveyance into one of 10 categories (`assignment`, `namechg`, `correct`, `govern`, `security`,
  `merger`, `release`, `other`, `missing`, `employee` — counted directly from the local file,
  10.5M rows total); **`license` is not one of them.** USPTO's own conveyance-type list separately
  documents `Government Interest Agreement` and `Confirmatory License` as distinct filing types, but
  neither surfaces as a queryable category in this bulk product — `govern` (111,537 rows locally) is
  the closest analog and is a title/rights recordation, not a license grant. However, the free-text
  `convey_text` field in `assignment.csv.zip` **does** contain literal "LICENSE" wording on a
  meaningful minority of records (≈0.5% of a 2M-row sample, i.e. tens of thousands of records
  repo-wide), joinable to `assignor.csv.zip` / `assignee.csv.zip` by `rf_id` to recover the naming
  parties. **Verdict: Feasible now, as a weak proxy only** — a `convey_text` free-text search for
  license wording, cross-checked against RI/SBC names on the award spine, is the only concrete,
  already-in-repo path to any license-adjacent signal. It is not a Bayh-Dole government-interest
  statement, is unvalidated (recorded licenses are optional and most private license agreements are
  never filed with USPTO at all — recordation is voluntary, not required), and will systematically
  undercount.
- **DOE VIPS (national-lab IP licensing database) and NASA e-NTR / NTRS.** DOE's [Visual
  Intellectual Property Search](https://www.energy.gov/technologycommercialization/articles/doe-unveils-public-database-featuring-intellectual-property)
  lists national-lab patents/software available for licensing (public), and NASA's e-NTR
  (`invention.nasa.gov`) tracks New Technology Reports internally. Neither is a general-purpose
  Bayh-Dole license registry: DOE VIPS shows licensing *availability* from federal labs, not
  confirmed *executed* licenses to named third parties, and it is scoped to DOE national labs — not
  the university/RI population that dominates STTR partners. NASA's system is internal, not public.
  **Verdict: Not applicable** to the general D3 case; noted for completeness only.

**Recommended default.** No public source directly supplies "a recorded license from the RI to the
SBC" as declared. Treat this as a **structural limitation of D3, not a temporary sourcing gap**:
(a) drop "Bayh-Dole government-interest statements" from D3's declared sources (done — see the
`design.md` amendment accompanying this entry) since no accessible source of that name exists; (b)
keep `D3.patent_assigned_to_RI_with_SBC_inventor` as the real, confirmed-available D3 signal
(USPTO assignment data, already local); (c) if `D3.recorded_license_RI_to_SBC` ships at all in v1,
source it only from the `convey_text` free-text proxy above, labeled explicitly as low-recall and
unvalidated, never presented as a Bayh-Dole compliance record. This **corroborates and sharpens**
`coverage-memo.md`'s existing D3 row ("license records are sparse everywhere"): the records are not
merely sparse, they are close to **structurally unobservable** from any public Bayh-Dole compliance
channel — the sparsity is a source-availability ceiling, not a coverage artifact that more querying
would fix.
