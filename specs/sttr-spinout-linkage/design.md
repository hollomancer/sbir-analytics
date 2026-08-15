# STTR Spinout–Subcontract Linkage and Partner-Type Classification — Phase 0 Design

**Status:** **FROZEN as Revision 1** (see [`amendments.md`](amendments.md)). All open questions
in [`open-questions.md`](open-questions.md) are resolved. This note describes the intended method;
freezing the design does **not by itself** authorize implementation, materialization, a headline
cell, or any citable claim — Phase 1 (`tasks.md`) is now unblocked to *begin*, but every task
within it (seed-list capture, the kernel, the cascade run, the negative-control and adjudication
gates) still has to complete before any result exists, and the tier stays `exploratory`
/ non-citable throughout.

**Target epistemic tier:** `exploratory` (declared in [`requirements.md`](requirements.md); non-citable).

**Design date:** 2026-08-14.

**Research-question anchors:** dedicated **B2** (STTR spinout vs. subcontract relationship)
and **B1** (STTR research-institution partner types); supporting dimensions A2 (subaward
relationship) and C2 (patent–award linkage) for RQ1; F1 (Form D fundraising, M&A exit rate),
F3 (leverage ratio, private-capital-baseline outcomes), A4 (M&A effect on transition
pathways), B3 (Phase II→III latency) for the RQ2 design. See
[Anchor verification](#anchor-verification-and-a-correction-to-the-brief).

**Answerability label after Phase 1 implementation:** **[Deterministic public-data
classification of STTR SBC↔RI relationships and RI partner types, emitted as `CANDIDATE`
assertions with typed per-dimension absence. Report only the labeled counts, the incidence
tables, and per-tier adjudication precision/recall — do not interpret any `SPINOUT` rate as a
measured spinout prevalence, and do not mark any research question answerable, until the
negative-control and blind-adjudication gates below pass. Non-citable (`citable: false`) at all
times in this tier.]**

---

## Decision this note supports

Whether, and exactly how, to build a deterministic, public-data classifier that splits every
STTR award's small-business (SBC) ↔ research-institution (RI) relationship into `SPINOUT_T1`,
`SPINOUT_T2`, `SUBCONTRACT`, or `INDETERMINATE` (RQ1), plus a deterministic RI partner-type
classifier with a novel-partner incidence readout; and whether the matched outcome comparison
(RQ2) ships here or as its own spec. The spinout-vs-subcontract split has, to our knowledge,
never been measured anywhere.

## Proposed estimand — one sentence (RQ1)

Among STTR awards observable on the frozen SBIR.gov award spine, estimate the count and share of
awards whose SBC↔RI relationship is classifiable from public evidence as a founding-or-licensing
**spinout** (`SPINOUT_T1` exact / `SPINOUT_T2` corroborated-fuzzy) versus an arm's-length
**subcontract** (`SUBCONTRACT`, dimensions present and negative), with the residual reported as
`INDETERMINATE`; this is a **public-evidence classifiability rate under a frozen deterministic
cascade**, not the true prevalence of spinouts, because the clean signal — the PI's employer
election and the allocation-of-rights agreement — lives in non-public agency award files (see
[the documented gap](#coverage-and-the-documented-gap)).

The words **public-evidence** and **classifiability** are deliberate restrictions. A
`SUBCONTRACT` label means the spinout-bearing dimensions were measured and negative, not merely
absent; an `INDETERMINATE` label means typed absence dominated. Neither the numerator nor the
denominator is a statutory or economic measurement of spinout activity.

## Authorities and findings used

The `[L#]` labels are the literature-map labels already used by
[`docs/research-questions.md`](../../docs/research-questions.md).

- [NASEM 2016 [L7]](../../docs/research-questions.md) assessed the STTR program specifically; it
  is the only STTR-specific NASEM anchor and frames the SBC↔RI partnership as the defining STTR
  feature. Supports treating the relationship as the unit of analysis.
- [Fini, Perkmann, Kenney & Maki 2022 [L36]](../../docs/research-questions.md) study SBIR awards
  in the University of California system and are the most-cited recent SBIR-commercialization
  spinout study. Supports the `SPINOUT` construct and the person/IP-link evidence model; does
  not supply a public-data classifier.
- [Swann 2026 [L38]](../../docs/research-questions.md) relates firm-level SBIR reliance to
  spin-off generation and patenting. Supports the spinout-vs-non-spinout distinction as
  measurable in principle.
- [Guerrero, Link & van Hasselt 2023 [L37]](../../docs/research-questions.md) and
  [Audretsch, Link & van Hasselt 2019 [L39]](../../docs/research-questions.md) characterize
  federally funded technology transfer and university knowledge spillovers into SBIR output.
- [Link & Scott 2010/2012 [L12]](../../docs/research-questions.md) and
  [Lerner 1999 [L10]](../../docs/research-questions.md) anchor the RQ2 commercialization and
  follow-on-capital outcomes.
- [Rovito, Kamp & Etemadi 2025 [L47]](../../docs/research-questions.md) find Phase III receipt
  only weakly predictive of commercialization success — a required honesty input for RQ2.

**Bayh-Dole statutory anchor:** [35 U.S.C. §§ 200–212 [L50]](../../docs/research-questions.md)
([O-8](open-questions.md), resolved). This is the literature citation only — it does not supply a
public government-interest or RI→SBC license data source ([O-12](open-questions.md)). Do **not**
take `[L49]` (conditionally reserved for an unverified Jones & Fearon deposit).

---

## Evidence dimensions

Each dimension is scored **independently** and carries a typed per-dimension status. The status
enum mirrors the graph-governance `DimensionStatus`
([ADR-005](../../docs/architecture/neo4j-epistemic-assertions-plan.md)):
`MEASURED` (bounded finite score; zero is a measured no-signal), `NOT_MEASURABLE`,
`NOT_APPLICABLE`, `NOT_EVALUATED`, `EVALUATION_FAILED`. A `NOT_MEASURABLE` status carries a
`signal_absent_reason` code (proposed `StrEnum`, modeled on `sbir_etl.identity.RecoveryStatus`;
see [O-0](open-questions.md)). **Missing or null data never stands in for one of these states.**

| Dim | Name | Sources | Positive signal | Typed absence encodes |
|-----|------|---------|-----------------|-----------------------|
| **D1** | Award spine | SBIR.gov award data, `program = STTR` | SBC, RI, PI, agency, FY, abstract present (the join spine) | Missing RI/PI blocks scoring downstream; row is `INDETERMINATE` if D1 incomplete |
| **D2** | Person trail | OpenAlex / PubMed authorship, ORCID | PI and founders (founders = D4 Form-D-derived officer/director names only, no separate discovery pipeline — [O-1](open-questions.md), resolved) matched to RI-affiliated authorship within ±5 years of award ([O-2](open-questions.md), resolved) | No RI-affiliated authorship found *after search* vs. person unresolvable (`generic_token_guard` fail) vs. source not queried |
| **D3** | IP trail | USPTO assignment data (local, confirmed — patent-assignment sub-signal only); **no confirmed public source for Bayh-Dole government-interest statements or a structured RI→SBC license record** ([O-12](open-questions.md)) | Patent assigned to the RI naming an SBC principal as inventor; **recorded license** RI→SBC | License **absence** → `NOT_MEASURABLE` (`LICENSE_RECORDS_SPARSE`), **never** `SUBCONTRACT` evidence |
| **D4** | Money / paper trail | USASpending subawards; Form D officers/directors (existing pipeline) | RI subaward share on grant-based STTRs (a positive **subcontract** marker); Form D officer/director matched to RI-affiliated name (a positive **spinout** marker) | No subaward record vs. non-grant instrument (`NOT_APPLICABLE`) vs. Form D absent |
| **D5** | Text trail | Deterministic phrase lexicon over award abstracts and firm text | "spun out of", "licensed from", "founded by Professor …" ([O-4](open-questions.md) fixes the v1 lexicon) | No phrase matched vs. no firm text available |

Discipline notes carried from the brief:
- **D3 licenses are asymmetric evidence.** A recorded license is positive spinout evidence; its
  absence proves nothing and is encoded as typed absence, never as subcontract evidence.
- **The `recorded_license_RI_to_SBC` sub-signal has no confirmed public or paid data source** —
  checked twice ([O-12](open-questions.md), resolved). iEdison is statutorily confidential, not
  merely account-gated; PatentsView/USPTO's `government_interest` extraction and the local USPTO
  `convey_text` `"confirmatory license"` proxy both capture *federal-funding nexus*
  (contractor-to-government), not an RI→SBC license; AUTM's STATT (paid, aggregate-only) and
  TransACT (paid, explicitly de-identified) don't help at any price. If this sub-signal ships in v1,
  source it from the sharper `"confirmatory license"` search over `convey_text` (not generic
  "license" wording) plus, optionally, a corroborating SEC EDGAR full-text-search pass over the
  small subset of STTR firms that later became SEC filers — both weak, unvalidated, population-
  partial proxies, never presented as a Bayh-Dole compliance record.
- **`generic_token_guard` is mandatory on D2 person names** and on all organization-name matching
  (partner type). A name dominated by generic tokens cannot produce an accepted match.
- **D4 has two directions.** The RI subaward share is a *subcontract* marker; a Form
  D officer/director who is RI-affiliated is a *spinout* marker. They are scored separately.

---

## Classification cascade (RQ1)

All string comparisons use the reused `sbir_etl.identity` normalization (a named
`CompanyNameProfile`; person-name normalization is net-new, [O-0](open-questions.md), resolved);
blank, `None`, and `NaN` normalize to null; dates are parsed without imputation. The cascade is
evaluated **in order**; the first matching rule assigns the label. The exact-vs-fuzzy **method** is
frozen by [O-3](open-questions.md) (`company_name_similarity` under `CompanyNameMetric.JARO_WINKLER`
gated by `generic_token_guard`); the **numeric cutoff** is explicitly deferred to a post-task-1.4
amendment, not a Revision 1 blocker — `SPINOUT_T2` scoring cannot run until that amendment lands.

| Order | Label | Exact condition (frozen predicate; O-3 numeric cutoff still deferred) |
|-------|-------|------------------------------------------------------------------|
| 0 | `INDETERMINATE` | `D1` incomplete: RI or PI absent on the spine → cannot classify. |
| 1 | `SPINOUT_T1` | `D2.status == MEASURED and D2.exact_person_ri_affiliation` **OR** `D3.status == MEASURED and (D3.patent_assigned_to_RI_with_SBC_inventor or D3.recorded_license_RI_to_SBC)`. One **exact** person or IP link with affiliation evidence. |
| 2 | `SPINOUT_T2` | A **fuzzy** positive in one dimension (`D2.fuzzy_person` above the similarity cutoff and `generic_token_guard` passes, **or** `D5.spinout_phrase`) **AND** independent corroboration from a **second, distinct** dimension (`D3`, `D4.form_d_officer_ri_affiliated`, or `D5` — excluding whichever dimension supplied the primary fuzzy positive). Two independent weak signals from different dimensions; a single `D5.spinout_phrase` cannot corroborate itself. |
| 3 | `SUBCONTRACT` | The spinout-bearing dimensions are **present and negative**: `D4.ri_subaward_share.status == MEASURED and D4.ri_subaward_share > 0` (a positive subcontract marker) **AND** `D2.status == MEASURED and not D2.any_person_link` **AND** `D3.status == MEASURED and not D3.any_ip_link` **AND** `D5.status == MEASURED and not D5.spinout_phrase`. Measured-negative, not merely absent. |
| 4 | `INDETERMINATE` | Otherwise — typed absence dominates (any decisive dimension is `NOT_MEASURABLE` / `NOT_EVALUATED` / `EVALUATION_FAILED`). |

Rules for the cascade, frozen once the owner approves:
- **Absence never advances a label.** Order 3 requires `MEASURED` status on `D2`, `D3`, `D5` and
  a positive `D4` subaward share. If any of those is `NOT_MEASURABLE`, the row falls through to
  Order 4 `INDETERMINATE`. This is what "dimensions present and negative — not merely absent" means.
- **License absence cannot create a `SUBCONTRACT`.** Because `D3` license absence is
  `NOT_MEASURABLE`, it never satisfies the Order-3 `D3.status == MEASURED` clause on its own; the
  patent-assignment sub-signal can, when USPTO assignment coverage is real for that RI.
- **No score, prefix, distance, or learned rule** decides a label in v1. Fuzzy matching appears
  only as a bounded `company_name_similarity` cutoff at Order 2, gated behind `generic_token_guard`.

## Partner-type classification

A second, independent deterministic classifier over the RI on the D1 spine. House-census style,
list-based, **no ML**. Reuses `sbir_etl.identity` for organization-name matching and
`generic_token_guard` for the guard.

**Vocabulary:** `UNIVERSITY`, `FFRDC`, `RESEARCH_HOSPITAL`, `NONPROFIT_INSTITUTE`,
`NEW_MODEL_ORG` (focused research organizations and similar), `COMMUNITY_COLLEGE`,
`OTHER_NONPROFIT`, `UNRESOLVED`.

**Seed lists** (each versioned, date-stamped, with sources recorded in
[`seed-list-provenance.md`](seed-list-provenance.md)):
- the official **FFRDC Master List** (NSF);
- a curated **FRO / new-model-org** list — seeded from Convergent Research's public FRO portfolio
  plus known independents, verified at capture, incomplete-by-construction ([O-6](open-questions.md)
  **resolved**: curation protocol, not a source pick);
- **IPEDS** for community colleges and the university universe;
- a **research-hospital** list — **NIH RePORTER** hospital-class grantees scoped to non-university
  institutions, with **AAMC COTH** as a coverage cross-check ([O-7](open-questions.md) **resolved**).

**Fiscal-sponsor masking.** New-model orgs operating under a fiscal sponsor may appear in award
data under the sponsor's name. The classifier matches both org names and known sponsor names, and
the typed absence **distinguishes `NO_MATCH` from `POSSIBLY_MASKED_BY_SPONSOR`**. Sponsor-name
coverage is [O-6](open-questions.md).

**Precedence when lists overlap** (e.g., a university-administered FFRDC). Proposed default,
revised by the [O-7](open-questions.md) resolution and pending final ordering confirmation
([O-5](open-questions.md)): **`FFRDC` > `NEW_MODEL_ORG` > `UNIVERSITY` > `RESEARCH_HOSPITAL` >
`COMMUNITY_COLLEGE` > `NONPROFIT_INSTITUTE` > `OTHER_NONPROFIT`**. Rationale: the most specific,
list-authoritative status (FFRDC by federal master list) wins over the broadest (a nonprofit tax
status); a university-administered FFRDC is reported as an FFRDC because that is its
funding-instrument identity in award data; and `UNIVERSITY > RESEARCH_HOSPITAL` keeps
university-owned academic medical centers labeled `UNIVERSITY`, with the hospital list built to
exclude them so the overlap rarely arises.

**Headline readout:** *Has a non-university, non-FFRDC nonprofit (research hospital, independent
institute, or new-model org) ever served as an STTR partner?* Report incidence by
`category × agency × fiscal_year` (table shape in [`coverage-memo.md`](coverage-memo.md)). Either
result — presence or a clean zero — is reportable once gates pass.

---

## Graph governance

All linkage and partner-type outputs are emitted **only** as `CANDIDATE` assertions per
[ADR-005](../../docs/architecture/neo4j-epistemic-assertions-plan.md): `claim_status = CANDIDATE`,
`support_class = C`, `permitted_use = INVESTIGATIVE_ONLY`. Each per-dimension score carries a
`DimensionStatus`. **Parquet is authoritative**; Neo4j is a disposable investigative projection.
**No new causal edge type** is introduced — the relationship label is a property of a candidate
assertion, not a `SPUN_OUT_OF` edge. `ACCEPTED` / `REJECTED` claim statuses remain reserved and
forbidden to any producer in this spec.

---

## Validation and gates

Mirrors the negative-control gate pattern of [`specs/phase-iii-census/`](../phase-iii-census/design.md).

**Negative controls (must pass before any citable status is contemplated):**
1. **Random-RI pairing.** SBIR-only firms paired with a randomly assigned RI should classify
   overwhelmingly `SUBCONTRACT` or `INDETERMINATE`; a material `SPINOUT` rate on random pairs is a
   false-positive alarm and stops the study.
2. **Permuted PI names.** Permuting PI names across awards (fixed recorded seed) should collapse
   the D2 person-link rate to noise; residual `SPINOUT_T1` from D2 on permuted names indicates the
   `generic_token_guard` or the affiliation join is leaking.
3. **Arm-blindness.** The classifier is a pure function of the evidence dimensions; it does not
   read the control flag, the arm label, or any outcome.

**Adjudication sample.** A **150–200 award** blind-adjudication sample for calibration, drawn
**NSF and NIH cohorts first, DoD last** (DoD abstract emptiness makes D5 weakest there — consistent
with the repository's Phase III DoD description findings). Report **precision/recall by tier** with
an **error taxonomy** (false-spinout from co-authorship-without-founding, false-subcontract from
license-record sparsity, etc.).

**Release gate.** Citable status is **blocked** until the negative controls pass and the
adjudication precision/recall is reviewed and signed off. Until then every artifact is
`citable: false`. Promotion out of `exploratory` is explicit work under
[`docs/steering/epistemic-tiers.md`](../../docs/steering/epistemic-tiers.md) (frozen spec + SHA
enforcement + blocking asset checks + declared estimand), not a consequence of the numbers looking
good.

**Freeze mechanics — executed as Revision 1.** What Revision 1 actually freezes: the cascade
structure and ordering (Order 0–4), the exact-vs-fuzzy **method** (not the O-3 numeric cutoff,
explicitly deferred to a post-task-1.4 amendment), the evidence-dimension sourcing including the
O-12 D3 findings, and the partner-type precedence order. What it does **not** freeze, because these
are structurally Phase 1 deliverables, not Phase 0 decisions: the D5 lexicon's actual phrase list
(O-4 — drafted and frozen at task 1.3), and the seed lists' actual captured versions/hashes
(task 1.1 — `seed-list-provenance.md` stays `_pending_` until then). See
[`amendments.md`](amendments.md) Revision 1 for the frozen raw-byte SHA-256 of this file. A future
materializing asset must verify that hash before running and fail closed on mismatch; it must also
verify each seed list's own hash from `seed-list-provenance.md` once task 1.1 populates them.

---

## Coverage and the documented gap

Per-dimension, per-agency expected-coverage estimates are maintained in
[`coverage-memo.md`](coverage-memo.md). Summary: D1 (spine) near-complete; D2 (person trail)
strongest for NIH/NSF (rich OpenAlex/PubMed authorship, ORCID), weakest for DoD; D3 (IP) uneven —
USPTO assignment coverage is real but license records are sparse; D4 (subaward) strong for
grant-based STTRs (NIH/NSF), `NOT_APPLICABLE` for contract-instrument STTRs (much of DoD); D5 (text)
tracks abstract richness and is weakest for DoD.

**Where the clean answer actually lives — a documented data gap, not a data source.** The
unambiguous spinout/subcontract signal is the **PI's employer election** (does the PI remain an
RI employee, or is the PI now an SBC employee?) and the **allocation-of-rights agreement** between
the SBC and the RI. Both live in **non-public agency award files**, not in any public dataset this
spec can read. Every public dimension here is a proxy for that election. This section is written
precisely because it supports a **separate policy argument**: the cheapest path to a clean national
measurement is not more inference — it is a one-field disclosure at submission (see the
[Appendix](#appendix--one-field-prospective-fix)). We do not attempt to reconstruct these files;
we mark their absence as the binding constraint.

---

## RQ2 — matched outcome comparison (design only)

**This section is a design. It is not run in this spec.** Whether it ships here or as its own spec
is [open question O-9](open-questions.md).

**Question.** Do spinout-STTRs transition differently from subcontract-STTRs on (a) Phase II→III
latency, (b) Form D follow-on capital, and (c) M&A detection?

**Design.** Matched comparison on **agency × award year × topic-embedding similarity**. The
treatment axis is the RQ1 label (`SPINOUT_{T1,T2}` vs. `SUBCONTRACT`); `INDETERMINATE` awards are
excluded from the matched set and reported separately. Embedding choice for the topic-similarity
key is [O-10](open-questions.md). Outcomes reuse existing pipelines:
- **Transition latency** — Phase II→III latency (anchor B3), right-censored; report
  Kaplan–Meier medians, never naive means over completed transitions only.
- **Form D follow-on** — the existing SEC EDGAR / Form D pipeline (anchors F1, F3).
- **M&A** — the existing EFTS-mention M&A detector (anchors F1, A4).

**Honesty clauses (required, stated before any result):**
1. **Spinout selection into long-horizon deep tech.** Spinouts may self-select into longer-fuse,
   capital-intensive technologies; a latency or capital difference may reflect technology mix, not
   the spinout relationship.
2. **Right-tail blindness of registry outcomes.** Form D and FPDS miss the outcomes that matter
   most (private acquisitions structured off-registry, non-dilutive success); the comparison is
   blind to the right tail.
3. **License-record absence.** D3 license sparsity means the spinout arm is under-identified;
   misclassified spinouts sitting in the subcontract arm bias the contrast toward zero.
4. **Coded-set upper-bound caveat.** State explicitly whether any positives set (e.g.,
   `SPINOUT_T1`) carries a coded-set upper bound — the measured rate is a floor on true spinouts
   and a ceiling on what public data can confirm.

**Format.** A pre-registered analysis plan: matching keys, caliper, outcome definitions,
estimator, primary vs. secondary contrasts, and stopping/adjudication rules fixed **before** the
RQ1 labels are joined to outcomes.

---

## Non-goals and prohibited drift

- No ML classifier for linkage or partner type in v1 (lexicon- and list-first; ML is flagged
  future work).
- No causal edge types; no `SPUN_OUT_OF` / `RESULTED_IN` relationship.
- No promotion of any count to a citable tier; no research question marked answerable on this work.
- No reconstruction of, or dependence on, non-public agency award files.
- Running RQ2. This spec designs it only.

---

## Anchor verification and a correction to the brief

The task brief specified a "B2/B3 + C2 cross-read." Verified against
[`docs/research-questions.md`](../../docs/research-questions.md):
- **B2, B3, C2 all exist** (as area+tier headings). **B2/B3 is a well-established anchor pair**
  across `phase-iii-census`, `dark-majority-resolution`, and others.
- **The existing B2 questions are about award-to-contract transition, not STTR
  relationship type.** Stretching those entries would make the inventory lie about
  what this spec answers. This spec therefore adds two dedicated inventory
  questions: **B2 STTR spinout vs. subcontract relationship** (RQ1) and **B1 STTR
  research-institution partner types** (the partner-type readout).
- **C2 is patent–award linkage**, which legitimately covers the **D3 IP trail** — so C2 is retained
  as a supporting RQ1 dimension, not as the primary question.
- **Capital and M&A live in Section F, not C.** The RQ2 outcomes (Form D, leverage, M&A) anchor to
  **F1 / F3 / A4**, not C2. The closest existing matched-comparison precedent,
  [`agency-private-capital-comparison`](../agency-private-capital-comparison/requirements.md),
  anchors **F3 / B2 / B3** — which this spec follows for RQ2. **A2** (SBIR-to-prime
  supply network / subaward relationship) is the better fit for the subcontract-relationship
  framing and is retained as a supporting dimension.

The CI anchor check (`scripts/ci/check_removed_src_references.py::scan_spec_question_anchors`)
validates that the anchor line exists and is non-placeholder; it does not resolve the IDs. The IDs
above are chosen to be substantively correct, not merely CI-passing.

---

## External citation line (for a policy one-pager)

> **SBIR/STTR spinout–subcontract linkage (live exploratory measurement).** This repository is
> developing the first public-data classification of STTR awards by whether the small business was
> *spun out of* its research-institution partner (founded by, or licensing core technology from,
> the institution) versus *subcontracting* to an arm's-length institution, alongside a
> deterministic classification of each research-institution partner's type — including whether any
> non-university, non-FFRDC nonprofit has ever served as an STTR partner. Results are produced as
> investigative candidate assertions with typed evidence-by-dimension, are calibrated against a
> blind adjudication sample, and are **exploratory-tier and non-citable** until negative-control
> and adjudication gates pass; the numbers below are provisional and must not be cited as
> measured prevalences. The cleanest measurement would come not from more inference but from a
> single disclosure field at SBIR.gov submission (see appendix).

Per the partner-type addendum, the incidence finding folds into this template: once gates pass,
append "*Of [N] STTR awards, [k] name a non-university, non-FFRDC nonprofit as the research
partner ([category breakdown]).*"

---

## Appendix — one-field prospective fix

The entire inference apparatus in this spec exists to reconstruct a fact the awardee already knows
at submission. A durable national measurement would follow from adding, to the SBIR.gov submission
form, a single structured disclosure: a **licensee/spinout flag** ("Was the applicant small
business founded by, or does it license core technology from, the named research institution?
yes/no") and the **PI-employer election** ("Is the principal investigator primarily employed by
the small business or by the research institution for the period of performance?"). Two
machine-readable fields, collected at the source, would convert the RQ1 estimand from a public-data
classifiability rate into a direct measurement — and would make the negative-control and
adjudication scaffolding in this spec a validation harness rather than the primary instrument. This
appendix is text only; it prescribes no implementation here.
