---
Type: Research Readout
Owner: research@project
Last-Reviewed: 2026-09-27
Status: draft
---

# STTR research-institution partner-effect feasibility

**Prepared for:** Repository maintainers deciding whether to draft the NSF experiment; not for an agency or external briefing.

> **Exploratory / non-citable Phase 0 readout.** This document reports data
> availability and sample counts. It does not estimate a partner effect, compare
> outcomes, or support a claim that research-institution partners matter. No model
> was run.

## Gate answer: enough partners overall; no sparse-market count

- **320 normalized RI strings have at least 10 STTR Phase I awards; 114 have at
  least 30; and 70 have at least 50.** These are normalized strings, not resolved
  institutions. The Phase I population contains 16,033 awards, of which 15,732
  (98.12%) name an RI.
- **Sparse-tier awards: not present. Sparse-tier RIs with at least 10 awards: not
  present.** The repository has neither a canonical RI-to-CBSA primitive nor a
  CBSA-level Form D market-density measure. Question 2 cannot be preregistered
  from current data.
- For the cross-agency extension, **70 normalized RI strings have at least 10
  Phase I awards in two or more agencies**. This is a feasibility count, not a
  power calculation; alias resolution and rare-outcome counts can still make
  agency splits unusable.
- An authoritative Phase I **grant-versus-contract split is not present**. The
  export's `Contract` column is an award identifier, not an instrument-type
  field; the upstream D4 identifier-shape classifier is exploratory and has
  been validated only on Phase II.

The immediate decision is narrow: Question 1 has enough repeated partner strings
to justify review of a preregistration for the outcomes that are actually
available. Question 2 remains blocked. Question 4 may be scoped, but its power is
not established. Phase 1 should not begin until this readout is reviewed.

## Research-question and tier anchors

This work is `exploratory` and non-citable under the repository's epistemic-tier
contract. It is anchored primarily in **B3** (commercialization and transition
heterogeneity), with **B1/B2** supplying the RI-identity and STTR-relationship
dependencies. **F1/F3** cover Form D and geographic capital-market context;
**A4/F1** cover M&A candidates; and **E3/E5** cover missing fields and source
availability. There is no dedicated partner-variance item in the current A–F
inventory. Adding one is Phase 1 work, not a Phase 0 status change.

No new spec, study manifest, evidence rank, or status-registry entry is created
here. The existing `sttr-spinout-linkage` design remains the upstream identity
dependency. Its Revision 2 freeze records design SHA-256
`5ffb2c28a58d50bc9155e3412f0ec243c6c4c762f971e305b5394564d105f9de`.

## Input and counting contract

| Item | Phase 0 choice |
| --- | --- |
| Public source | SBIR.gov bulk awards CSV |
| Source URL | `https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv` |
| Retrieval recorded by adjacent legacy metadata | 2026-09-07 09:00:18 UTC |
| Analysis SHA-256 | `aed146eab56f370c9f3fe7f562475e3eedfc61cca2eba112c830fac6f73bf38a` |
| Size and physical rows | 394,636,989 bytes; 219,590 rows; 42 ordered source columns |
| Canonical award grain | 219,535 awards after `load_sbir_awards_csv`; 109 source rows across 54 stable keys collapse under `sbir-source-v2` |
| Form D diagnostic input | Local legacy public-SEC-derived `data/form_d_details.jsonl`; SHA-256 `683ce43a955f074320daca5ed366152ca2c47cfd41b03b56ec9a25b6f3fc98ff`; 45,075,563 bytes; 10,742 records |
| Phase I gate population | Canonical awards with `Program = STTR` and `Phase = Phase I` |
| RI key | `scripts.sttr_spinout_linkage.kernel.resolve_identity`, organization kind, default `MATCHING_V1`, with its generic-token guard |
| Firm key for Question 3 | `scripts/data/find_same_work_awards.py::assign_firm_keys` (UEI, unambiguous DUNS bridge, then normalized company + state) |
| Topic proxy | Exact `normalize_topic_code` output; no canonical topic-family ontology exists |
| Fiscal-year proxy | `FiscalShockAggregator.extract_fiscal_year`: proposal award date first, then its source-Award-Year fallback |

The raw RI, PI-email, and proposal-date fields are joined back to the canonical
award selected by `source_row`; the canonical projection intentionally does not
retain those fields. The adjacent metadata file records the URL, hash, retrieval
time, and size, but predates the repository's current full verified-sidecar
schema. Byte-for-byte reproduction therefore requires the retained snapshot
identified by the hash above; the public download URL is mutable.

The RI rule performs deterministic string normalization and a generic-token
guard. It is **not** an RI alias resolver. For example, abbreviated and legal
names can remain separate. There were 301 blank RI values and zero nonblank
names rejected by the guard in the Phase I population. No RI matching rule was
changed after any outcome was inspected.

## a. RI-name field coverage

Yes. The public award export has `RI Name`, and 21,440 of 21,856 canonical STTR
awards (98.10%) populate it.

| Agency | STTR awards | RI populated | Share | Award years with at least one populated RI |
| --- | ---: | ---: | ---: | --- |
| Defense | 11,557 | 11,546 | 99.91% | 1996; 1998–2026 |
| Health and Human Services | 5,442 | 5,042 | 92.65% | 1998–2025 |
| National Science Foundation | 1,663 | 1,659 | 99.76% | 1997–2025 |
| NASA | 1,597 | 1,597 | 100.00% | 1997; 1999–2025 |
| Energy | 1,557 | 1,556 | 99.94% | 1998–2025 |
| Agriculture | 34 | 34 | 100.00% | 2023–2024 |
| Homeland Security | 6 | 6 | 100.00% | 2006–2008 |
| **Total** | **21,856** | **21,440** | **98.10%** | — |

The year column means that at least one populated record exists in the listed
year; it does not mean every award in that year is populated. Within Phase I,
coverage is 15,732 of 16,033 (98.12%). The 301 missing Phase I names are 300 HHS
awards and one NSF award.

## b. Existing STTR linkage and RI-resolution work

Yes: build on [`specs/sttr-spinout-linkage/`](../../specs/sttr-spinout-linkage/).
It already owns the spinout-versus-subcontract design, RI partner-type design,
freeze record, identity kernel, and public seed-list provenance. The reusable
pieces are:

- `scripts/sttr_spinout_linkage/kernel.py::resolve_identity` for guarded
  organization-name normalization;
- `scripts/sttr_spinout_linkage/d1_spine.py` for source-field discovery and D1
  spine patterns; and
- `data/reference/sttr_partner_type_seed_lists/` for IPEDS and FFRDC source
  material.

The existing D1 loader is Phase II-only, so its population filter is not reused
for this Phase I gate. The partner-type classifier, research-hospital seed, D3
scorer, full cascade, and blind/negative-control gates are incomplete. There is
no completed canonical RI alias crosswalk. This readout therefore reports
normalized RI strings and does not duplicate or pretend to complete that work.

The repository lifecycle review classifies that upstream spec as **PARTLY
STALE**: its frozen Revision 2 design and identity substrate remain the correct
dependency, but some requirements/task/status prose still describes the kernel
and seed capture as pending even though the kernel and five of six seed sources
are implemented. Evidence gates remain open, so this is documentation lag—not
authorization to treat the unfinished linkage as validated. This Phase 0 packet
does not revise the frozen upstream spec or its status entry.

## c. RI geography and Form D density

Both requested canonical inputs are **not present**:

1. No canonical primitive places an arbitrary RI in a CBSA. IPEDS HD2024 does
   carry `CBSA`, county, ZIP, and coordinates for higher-education institutions,
   but it covers only RIs that can first be linked to an IPEDS `UNITID`. The
   FFRDC seed carries state only, and other RI types are incomplete.
2. No CBSA-level early-stage Form D density measure exists. The maintained DERA
   control-universe producer retains issuer ZIP at filing grain but does not map
   it to CBSA or compute density. Form D also does not itself establish that an
   issuer is early-stage.

**Provisional proposal — not a canonical primitive:** freeze an RI crosswalk
before outcomes, using exact reviewed links to IPEDS for higher education and
versioned public registries for FFRDCs and remaining RI types. Map public
address ZIP/county to a pinned Census/OMB CBSA delineation and keep unresolved
geography explicit. Then use the official DERA universe with one first live,
non-amendment Form D per CIK, exclude pooled-investment funds and structurally
incompatible industries, map issuer ZIP to CBSA, and compute average annual
distinct first-disclosed Regulation D issuers per 100,000 residents over a
fixed pre-award period. Call this **first-disclosed Regulation D issuer
density**, not early-stage density. Freeze unweighted CBSA terciles before
outcomes; provisionally assign non-CBSA locations density zero/sparse and run a
separate non-CBSA sensitivity.

## d. STTR Phase I awards by normalized RI

| Minimum Phase I awards | Normalized RI strings meeting it |
| --- | ---: |
| 10 | **320** |
| 30 | **114** |
| 50 | **70** |

There are 2,956 distinct populated normalized RI strings. Counts can move in
either direction once a reviewed alias crosswalk merges abbreviations, system
campuses, and legal-name variants. That crosswalk must be frozen before outcomes.

| Rank | Representative source RI name | Phase I awards |
| ---: | --- | ---: |
| 1 | Purdue University | 169 |
| 2 | Georgia Institute of Technology | 162 |
| 3 | University of Washington | 158 |
| 4 | University of Michigan | 140 |
| 5 | Massachusetts Institute of Technology | 139 |
| 6 | Stanford University | 131 |
| 7 | University of Arizona | 128 |
| 8 | North Carolina State University | 121 |
| 9 | The Ohio State University | 116 |
| 10 | University of Florida | 116 |
| 11 | Duke University | 110 |
| 12 | University of California, San Diego | 110 |
| 13 | Northwestern University | 109 |
| 14 | Virginia Tech | 108 |
| 15 | University of Central Florida | 106 |
| 16 | University of Maryland | 102 |
| 17 | Carnegie Mellon University | 99 |
| 18 | Johns Hopkins University | 97 |
| 19 | University of Utah | 97 |
| 20 | University of Southern California | 96 |
| 21 | UNIVERSITY OF MINNESOTA | 94 |
| 22 | Arizona State University | 93 |
| 23 | UNIVERSITY OF PITTSBURGH | 91 |
| 24 | UNIVERSITY OF PENNSYLVANIA | 89 |
| 25 | University of Virginia | 88 |

The representative name is the most frequent source spelling inside each
normalized key, with lexical tie-breaking. Agency-specific counts of normalized
RI strings with at least 10 awards are: Defense 201, HHS 105, Energy 24, NSF 22,
NASA 19, Agriculture 0, and Homeland Security 0.

The bulk table does not contain an authoritative grant-versus-contract field:
`Contract` is the award's PIID/FAIN identifier. The upstream D4 scorer has an
exploratory regex classifier for identifier shapes, but it was empirically
validated on Phase II only. Until its Phase I behavior and unknown bucket are
reviewed and frozen, the Question 4 award-type split is **not present**.

## e. Awards by density tier

| Requested quantity | Result |
| --- | --- |
| STTR Phase I awards in sparse markets | **Not present** |
| Sparse-market normalized RIs with at least 10 awards | **Not present** |

No tier may be assigned until the provisional choices in (c), or a reviewed
replacement, are frozen. Consequently the sparse-tier power limit required for
Question 2 cannot yet be stated.

## f. Outcome linkage available today

“Linkable” below separates a mechanical candidate join from an outcome that is
currently admissible for the future gate model.

| Outcome | Current status | Grain and limitation |
| --- | --- | --- |
| Phase II follow-on | **Available** | `OutcomeMetricsCalculator` implements a five-calendar-year Phase I→II firm-level outcome over exact UEI/DUNS/normalized-name connected components. It pools SBIR and STTR and does not establish that a Phase II descends from a particular Phase I project. |
| Form D | **Not currently admissible** | The local company-record file is mechanically name-linkable, but all 10,742 records were unversioned. Offline rescoring to `corroborated-person-v2` moved 209 records from high to medium (3,700→3,491 high). The required PIF cross-link diagnostic then found 75 review pairs, including 34 distinct high-tier operating-company records; 30 of those high-tier records had signals that may span filings or CIKs. These are review flags, not false-positive labels. Issuer/filing-grain identity and amendment handling remain unresolved, so the retired Form D study does not authorize this as an outcome. |
| M&A via EFTS | **Candidate join only; not an exit outcome** | `data/sec_edgar_scan.jsonl` and the M&A scripts are company-name keyed, but the local enriched artifact is legacy and the required current `data/sbir_ma_direction_refined.jsonl` is absent. Current study gates prohibit treating a mention candidate as a confirmed acquisition or exit. |
| Phase III census | **Unavailable under the requested gate** | `studies/phase-iii-census/study.yaml` is `reproducible`, has no completed `validation_status`, and explicitly withholds headline or statutory Phase III interpretation. No census asset or negative-control gate was changed. |
| Coded-set Phase II→III latency | **Method available; not materialized on this host** | `validated_phase_iii_contracts`, `transformed_phase_ii_iii_pairs`, and `transformed_phase_transition_survival` join Phase II awards by UEI with DUNS fallback. FPDS `SR3`/`ST3` and explicit Phase III coding are a known undercount, especially outside DoD. A Phase I analysis would still need a frozen firm-level propagation rule and observation window. |

Missing or gated evidence is unavailable, never a zero. No outcome was joined to
RI names in this Phase 0 work.

## g. PI affiliation and the Question 6 proxy

The award record has `PI Name`, `PI Title`, `PI Phone`, and `PI Email`. It has no
PI employer or affiliation field and nothing that directly distinguishes an
RI-employed PI from a firm-employed PI.

For STTR Phase I awards, 14,984 of 16,033 (93.46%) have a nonblank PI email, and
2,704 (16.87% of all awards; 18.05% of populated emails) contain an address whose
domain ends in `.edu`. That is a cheap, incomplete proxy. A `.edu` address can
be retained after a move, and a non-`.edu` address does not imply firm
employment. It can support a preregistered sensitivity screen, not a direct
“PI sits at the RI” measure.

## h. Agreement or submission timing

**Not present.** There is no allocation-of-rights agreement execution date or
agreement-submission date. Among Phase I awards:

| Nearby public field | Populated | Share | Why it does not answer Question 5 |
| --- | ---: | ---: | --- |
| `Proposal Receipt Date` | 7,451 | 46.47% | Proposal receipt is not agreement submission. |
| `Date of Notification` | 9,475 | 59.10% | Possible selection-date proxy only. |
| `Proposal Award Date` | 11,767 | 73.39% | Award date is not signed-agreement date. |

Question 5 is not feasible from the public award table.

## i. Firms holding both SBIR and STTR

Using the existing conservative firm-key helper across canonical awards:

- **4,413 firms** hold both SBIR and STTR at the same agency, across 5,061
  firm×agency cells.
- A canonical topic-family field is **not present**. Using exact normalized
  `Topic Code` as a provisional stand-in and the repository's government-FY
  helper, **249 firms** qualify, across 318 firm×agency×FY×topic cells.
- As a sensitivity, using source `Award Year` instead of the FY helper gives
  245 firms and 310 cells.
- Restricting both sides to Phase I gives 4,005 firms at the same agency and 136
  under the government-FY plus exact-topic proxy.

The 249 figure is not a true topic-family count: related codes can remain
separate, while reused codes can group unlike work. Question 3 remains scope
only; no SBIR-versus-STTR outcome comparison was run.

## Question-by-question Phase 0 disposition

| Question | Phase 0 disposition |
| --- | --- |
| 1. Partner variance | Overall repetition is adequate for preregistration review; available outcomes and single-award firms still constrain the model. No estimate run. |
| 2. Density interaction | **Blocked:** density tiers and sparse counts are not present. |
| 3. SBIR vs STTR | **Scoped only:** 4,413 same-agency firms; 249 under the provisional FY/exact-topic proxy. |
| 4. Cross-agency stability | **Mixed:** the agency split is conditionally scopeable because 70 normalized RI strings meet the ≥10 threshold in at least two agencies; an authoritative Phase I grant-versus-contract split is not present. Both depend on Question 1 and outcome event counts. |
| 5. Partner speed | **Not feasible:** agreement timing is absent. |
| 6. Partner mode | **Partial proxy only:** `.edu` email exists for 2,704 awards; no employer/affiliation field. |

## Reproduction map

The cleared exploratory notebook
[`b3_sttr_partner_effect_feasibility.ipynb`](../../notebooks/explorations/b3_sttr_partner_effect_feasibility.ipynb)
contains the award-field, RI-count, date/email, and mixed-program queries. Run it
against the exact snapshot:

```bash
SBIR_AWARDS_CSV=/Volumes/SSDmini/sbir-analytics/data/raw/sbir/award_data.csv \
  jupyter nbconvert --execute \
  notebooks/explorations/b3_sttr_partner_effect_feasibility.ipynb \
  --to notebook --output /tmp/b3_sttr_partner_effect_feasibility.executed.ipynb
```

The Form D gate diagnostics were run offline, without changing the source file:

```bash
python scripts/data/rescore_form_d_details.py \
  --input data/form_d_details.jsonl \
  --output /private/tmp/sttr-form-d-details-v2.jsonl

python scripts/archive/data/audit_form_d_pif_cross_links.py \
  --form-d-path /private/tmp/sttr-form-d-details-v2.jsonl \
  --output-json /private/tmp/sttr-form-d-pif-cross-links.json \
  --output-md /private/tmp/sttr-form-d-pif-cross-links.md
```

Repository-availability checks used `rg -n -i 'CBSA|core.based|Form D.*density'`
and file inspection of these named contracts:

- `sbir_etl/extractors/sbir_award_export.py` — exact 42-field schema;
- `sbir_etl/extractors/sbir_public_awards.py::load_sbir_awards_csv` — canonical
  award collapse;
- `scripts/sttr_spinout_linkage/kernel.py::resolve_identity` — RI string key;
- `scripts/sttr_spinout_linkage/d4_scorer.py::classify_instrument_type` —
  exploratory Phase II-only validation for the provisional instrument proxy;
- `scripts/data/find_same_work_awards.py::{assign_firm_keys,normalize_topic_code}`;
- `sbir_etl/transformers/fiscal/shocks.py::FiscalShockAggregator.extract_fiscal_year`;
- `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/outcomes.py`;
- `docs/research/form-d-data-dictionary.md` and
  `scripts/archive/data/audit_form_d_pif_cross_links.py`;
- `docs/data/ma-events-refresh.md` and
  `studies/sbir-ma-dated-signal-study/study.yaml`;
- `studies/phase-iii-census/study.yaml` and
  `docs/phase-transition-latency.md`.

## Stop condition

Phase 0 ends here. No gate model, density interaction, agency split, placebo, or
SBIR-versus-STTR outcome contrast was estimated. A Phase 1 spec and its freeze
mechanism should be drafted only after review of this readout.
