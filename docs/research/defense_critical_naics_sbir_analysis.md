# SBIR entities in SBA's defense-critical NAICS codes

**Status:** exploratory and non-citable

**Analysis date:** September 10, 2026

**SBIR input archive date:** September 7, 2026 (not a source-declared data-through date)

**SAM public monthly extract:** September 7, 2026

**Procurement observation window:** October 1, 2008–July 3, 2026

**Unit:** exact-UEI SBIR entity
**Research questions:** A1, A2/B2, B3, D1, and E2/E3 in
[`docs/research-questions.md`](../research-questions.md)

This analysis identifies exact-UEI SBIR recipients that currently declare or have procured work
in the ten six-digit NAICS codes named in SBA's September 10 announcement. It separately screens
for positive target-coded transactions after an earliest usable recorded Phase II end, qualifying
target-origin awards after a clean pre-index period, and literal first-observed target entry. It is
a public-data screening analysis, not a causal estimate of SBIR commercialization, evidence that
a Phase II was completed, or an eligibility determination for the 8(a) program.

## Executive readout

- The high-precision identity cohort contains **17,168 exact-UEI SBIR entities**. It does not cover
  SBIR recipients that lack a usable UEI or whose identities changed without a preserved UEI.
- In the public SAM extract, **1,471 entities (8.57%)** have an active registration listing at
  least one target code; **375 (2.18%)** list a target code as primary. Among the 11,396 exact-UEI
  SBIR entities found in active public SAM records, the corresponding shares are **12.91%** and
  **3.29%**. These are lower bounds on SAM registrations because the public extract excludes
  entities that opt out of public display.
- **1,266 entities (7.37%)** have at least one observed, non-IDV federal prime-contract action
  coded to a target NAICS during the procurement window. **1,247** have a positive target-coded
  obligation. Across the full archive, **690** meet the sustained definition: at least two distinct
  qualifying target-origin awards whose target-coded transactions span at least two fiscal years.
- The union of public active-registration and procurement evidence is **2,026 entities (11.80%)**:
  760 registration-only, 555 procurement-only, and 711 observed in both channels. Registration and
  procurement answer different questions and should not be collapsed into a single claim that a
  company “operates in” a sector.
- Of **10,601 exact-UEI entities with a recorded Phase II award**, **9,026** have an earliest usable
  recorded Phase II end date. That date is an analytical anchor, not proof that the work was
  completed. **710** anchored entities have a later positive target-coded transaction on an award
  not classified as Phase I or II. This broad observable can be a modification to an existing
  award.
- The **clean-pre-index qualifying target-origin-award cohort** contains **205 entities**. It
  requires the Phase II anchor to fall at least three years after archive coverage begins, no
  target-coded action before or on that anchor, and a later qualifying target-origin award. The
  **literal-first-observed target
  entry cohort** contains **203** of those entities; it additionally requires the qualifying award
  date to equal the entity's first target-coded action date in the archive. Median lags are **2.74
  years** and **2.60 years**, respectively.
- First-date award-size sensitivity is material. At minimum lifetime gross-positive target
  obligations of $0, $1,000, $10,000, $100,000, and $1 million, the clean cohort counts are
  **205 / 203 / 119 / 68 / 27**; the literal counts are **203 / 201 / 117 / 67 / 27**. The test uses
  the largest individual qualifying award on the first date, not the sum of awards on that date.
- **68 of 205 clean-cohort entities (33.2%)** and **67 of 203 literal-entry entities (33.0%)** meet
  the sustained test. These are full-window descriptive shares with unequal entity-specific
  follow-up, not fixed-horizon rates.
- A formal identity-review workstream flags **106 of the 1,266 procurement-observed entities** at
  name-pair similarity below 0.90. Their flagged identity pairs carry **$28.233 billion**, or
  **56.9%**, of all gross-positive target obligations. The priority tranche contains **14 of 106**
  candidates—the top ten by flagged dollars plus all four clean-cohort candidates—and covers
  **96.9%** of flagged dollars. All 14 have supported corporate histories, but none has evidence
  establishing federal contract novation; the other 92 candidates remain unreviewed.
- Of the 1,471 public active target-code registrants, **11** carry an A6/8(a) history token. **Nine**
  have a recorded exit date on or after the SAM source date and are treated as current; the other
  **two histories are expired**. The remaining **1,462** without a current indicator form a broad,
  public-extract outreach pool—not a complete count of registrants or eligible applicants.

## What SBA announced

SBA [News Release 26-90](https://legacy.sba.gov/article/2026/09/10/sba-issues-guidance-prioritize-defense-critical-firms-new-8a-program-rules-take-effect)
says that, “moving forward,” SBA will prioritize the review and processing of 8(a) applications
from small businesses operating in ten defense-critical NAICS codes. The September 10 release does
not specify a separate effective date for that processing priority, define “operating in,” state a
duration or sunset, or set out an SBIR-specific pathway. It announces an application-processing
priority, not automatic 8(a) eligibility or a target-code contract-award preference.

The ten-code processing priority appears in the news release, not in the related
[final rule](https://www.govinfo.gov/content/pkg/FR-2026-08-11/pdf/2026-16370.pdf).
The rule became effective September 10, 2026 and revises how individually owned applicants
establish social disadvantage. It does not contain the NAICS list or create a distinct SBIR
pathway. The release also says SBA restored the pre-existing potential-for-success review. Under
the rule's transition process, pending individually owned applicants receive 45 calendar days to
update and resubmit returned applications; that process is distinct from the ten-code processing
priority.

## The ten target codes

| NAICS | SBA-listed industry |
|---|---|
| 332992 | Small Arms Ammunition Manufacturing |
| 332993 | Ammunition (except Small Arms) Manufacturing |
| 336414 | Guided Missile and Space Vehicle Manufacturing |
| 336413 | Other Aircraft Parts and Auxiliary Equipment Manufacturing |
| 334511 | Search, Detection, Navigation, Guidance, Aeronautical, and Nautical System and Instrument Manufacturing |
| 334419 | Other Electronic Component Manufacturing |
| 331110 | Iron and Steel Mills and Ferroalloy Manufacturing |
| 332710 | Machine Shops |
| 332999 | All Other Miscellaneous Fabricated Metal Product Manufacturing |
| 336611 | Ship Building and Repairing |

The release does not state a NAICS vintage. The codes and titles match the 2022 NAICS structure,
so the headline analysis uses exact six-digit equality. No inferred, topic-derived, agency-default,
or parent-prefix NAICS values are admitted.

## Findings by code

Entity counts are non-additive because one UEI can appear in several codes. Dollar totals are
historical gross-positive obligations on target-coded actions, not company revenue, physical
capacity, market size, or value caused by SBIR.

| NAICS | Public active SAM: any | Public active SAM: primary | Any target prime action | Clean qualifying origin | Literal first-observed entry | Gross-positive obligations | Historical cohort HHI |
|---|---:|---:|---:|---:|---:|---:|---:|
| 332992 | 21 | 2 | 15 | 1 | 1 | $2.8M | 3,219 |
| 332993 | 118 | 3 | 167 | 40 | 40 | $2.49B | 2,116 |
| 336414 | 211 | 59 | 51 | 7 | 7 | $1.24B | 1,428 |
| 336413 | 407 | 53 | 408 | 46 | 46 | $16.58B | 2,195 |
| 334511 | 707 | 173 | 595 | 79 | 77 | $24.20B | 1,407 |
| 334419 | 327 | 51 | 424 | 20 | 20 | $3.20B | 4,349 |
| 331110 | 5 | 2 | 21 | 0 | 0 | $1.3M | 2,006 |
| 332710 | 144 | 12 | 118 | 6 | 6 | $146.2M | 1,273 |
| 332999 | 173 | 15 | 180 | 4 | 4 | $242.9M | 485 |
| 336611 | 114 | 5 | 106 | 2 | 2 | $1.54B | 1,599 |

The largest observed footprints are in navigation/guidance instruments (334511), aircraft parts
(336413), and electronic components (334419). Together they account for 145 of the 205 clean
qualifying-origin entities and 143 of the 203 literal first-observed entries. Iron and steel
(331110) and small-arms ammunition (332992) have very thin SBIR-linked footprints in this
exact-UEI view.

The HHI column is calculated from each matched SBIR entity's accumulated gross-positive
target-coded obligations over the full historical procurement window within each code. It is not
an industry HHI, a federal-market HHI, or a measure of present-day supplier concentration. The
electronic-components cohort (334419) is especially concentrated in this historical matched-cohort
measure: its leading entity accounts for 64.1% of observed dollars and the top four account for
86.0%. That is an identity and concentration review flag, not evidence of a current
physical bottleneck.

## Transition timing

Three transition lenses are reported because they support different statements:

1. **Positive post-anchor transaction not classified as Phase I/II** is the first target-coded
   transaction with a positive obligation strictly after the entity's earliest usable recorded
   Phase II end, on an award-code record that is neither linked to a known SBIR award nor otherwise
   classified as Phase I/II and that has positive lifetime gross-positive target obligations. It
   can be a modification to an existing award and does not require the target code on the award's
   first observed action.
2. **Clean-pre-index qualifying target-origin award** requires the Phase II anchor to be at least
   three years after archive coverage begins, no observed target-coded action before or on that
   anchor, and a qualifying award whose observed first action is strictly later. A qualifying
   target-origin award has an observed base transaction, is not left-censored, carries the target
   NAICS on its first observed action, is not linked to or classified as Phase I/II, and has
   positive lifetime gross-positive target obligations.
3. **Literal first-observed target entry** adds that the first qualifying target-origin award date
   must equal the entity's first target-coded action date anywhere in the archive. Two clean-cohort
   entities have an earlier post-anchor target action, so they qualify under lens 2 but not lens 3.

“Earliest usable recorded Phase II end” is the minimum plausible recorded end date across an
entity's Phase II rows. Only 9,026 of 10,601 exact-UEI Phase II entities have such an anchor. It is
not a verified completion date. A target action on the anchor date is treated as ambiguous, not
post-index; one entity falls on that boundary.

Fixed-horizon rates use only entities with complete follow-up through July 3, 2026. The broad
transaction risk set also requires the anchor to fall within archive coverage. The clean and
literal risk sets additionally require three years of pre-index coverage and no target action
before or on the anchor. Every horizon has a different risk set; the percentages are not one
cohort's cumulative path.

| Horizon after earliest usable recorded Phase II end | Positive post-anchor transaction | Clean qualifying origin | Literal first-observed entry |
|---|---:|---:|---:|
| 1 year | 152 / 7,028 = 2.16% | 41 / 6,210 = 0.66% | 41 / 6,210 = 0.66% |
| 3 years | 228 / 5,684 = 4.01% | 89 / 4,914 = 1.81% | 88 / 4,914 = 1.79% |
| 5 years | 223 / 4,078 = 5.47% | 93 / 3,365 = 2.76% | 92 / 3,365 = 2.73% |
| 10 years | 165 / 1,524 = 10.83% | 49 / 891 = 5.50% | 48 / 891 = 5.39% |

The denominator contraction matters. Recent Phase II recipients are right-censored rather than
treated as failures, while early recipients without three years of archive coverage cannot enter
the clean or literal risk set.

## First-date award-size sensitivity

The threshold is not the obligation on the first transaction. For every qualifying award whose
observed first action falls on the entity's first qualifying date, the analysis sums that award's
gross-positive target obligations over its observed lifetime through July 3, 2026. If several
qualifying awards share the date, the threshold is applied to the largest individual award; their
amounts are not combined.

| Minimum lifetime gross-positive obligations on largest first-date award | Clean qualifying origin | Literal first-observed entry |
|---|---:|---:|
| $0 | 205 | 203 |
| $1,000 | 203 | 201 |
| $10,000 | 119 | 117 |
| $100,000 | 68 | 67 |
| $1 million | 27 | 27 |

These are sensitivity screens, not value created by SBIR. Gross-positive amounts sum positive
transactions and do not net later deobligations; signed totals are retained separately in the
evidence ledger.

## Illustrative sustained clean-pre-index entities

For this report, **sustained target procurement** means at least two distinct qualifying
target-origin prime awards and target-coded transactions across those qualifying award-code
records in at least two fiscal years. It does not require continuous activity, positive net
obligations, or a statutory Phase III marker. The definition yields 68 clean-cohort entities and
67 literal-entry entities. Because entities enter on different dates, each has a different amount
of follow-up through July 3, 2026; use the fixed-horizon table for time-comparable rates.

The examples below are the leading members of the 68-entity clean sustained cohort, ordered by all
observed gross-positive target obligations. The total is not the value of the first target-origin
award and is not a causal SBIR contribution.

| SBIR recipient label | UEI | First qualifying target-origin award | Code | Lag after recorded Phase II end | All observed gross-positive target obligations |
|---|---|---:|---:|---:|---:|
| Anduril Industries | KC3CH2MSK7Q3 | 2022-01-19 | 334511 | 1.20 years | $1.043B |
| Fairwinds Technologies | R3G6PWHQRAY5 | 2022-07-08 | 334511 | 1.18 years | $448.7M |
| Integrated Solutions for Systems | MPPUC2JZXND3 | 2015-09-10 | 332993 | 0.36 years | $182.0M |
| TRX Systems | ZFC8EAVYL8W2 | 2023-03-24 | 334511 | 9.69 years | $152.4M |
| Lunar Outpost | XYW2GGS9BKK5 | 2024-09-27 | 336414 | 3.56 years | $67.5M |
| Azure Summit Technology | P1LMDHFJSYH7 | 2016-12-23 | 334511 | 4.58 years | $67.0M |
| Magee Technologies | NUFGPBWG4ZK1 | 2024-08-15 | 336413 | 1.88 years | $38.1M |
| MAST Technologies | HJFAW5KCG7N7 | 2019-09-23 | 334511 | 6.41 years | $32.0M |
| Parry Labs | H7NNDQJ1NFP4 | 2023-07-31 | 336413 | 3.29 years | $27.0M |
| Intellisense Systems | C4Y5CNN55L37 | 2019-02-01 | 334511 | 2.96 years | $20.8M |

Some first-date awards are small even when accumulated totals are large. Outreach or case-study
selection should use the first-date maximum-award amount and repeat-activity fields in the evidence
ledger rather than ranking only on cumulative dollars.

## Acquisition, novation, and successor-identity workstream

This analysis treats identity review as a named study workstream rather than resolving low name
continuity implicitly. Exact UEI matching establishes that the SBIR and procurement records carry
the same identifier; it does not establish that the original small business, its assets, or its
federal contracts remained with the same legal or operating entity over time.

### Review queue and coverage

The generated review queue has **identity-pair grain**: one row per exact UEI, SBIR display name,
and observed contract-recipient name. Its stable review key is
`(firm_uei, sbir_name_key, contract_name_key)`, where the two name keys use the project's
`organization-key-v1` normalization. A pair enters the queue when normalized token-set similarity
is below **0.90**, or when a usable name is missing. All 106 rows in this data cut are below 0.90;
none was triggered by a missing name. The score is a review trigger, not evidence of acquisition,
novation, successor status, or a false UEI match.

The queue contains **106 rows and 106 entities**, out of 1,266 procurement-observed entities. The
flagged pairs account for **$28.233 billion (56.9%)** of the $49.658 billion in gross-positive
target obligations. Large pairs include Photon Research Associates/Raytheon, Oasys Technology/BAE
Systems, Progeny Systems/General Dynamics Mission Systems, and Cyrano Sciences/Smiths Detection.

The initial priority tranche is the union of the **top ten candidate entities by flagged
gross-positive dollars** and **all four low-continuity entities in the 205-entity clean cohort**.
Those groups do not overlap in this cut, producing 14 reviewed pairs. They cover **96.9% of flagged
dollars**, but the dollar- and cohort-targeted selection is not a representative sample.

The tracked crosswalk documents a supported acquisition, merger, or name-change history for every
one of the 14 priority pairs. It does **not** establish federal contract novation for any of them:
all 14 carry `contract_relationship = not_established`. The current attribution treatments are 11
`temporal_split_required`, one `same_entity_continuity`, and two
`unresolved_exclude_from_original_firm_claims`. The remaining **92 candidates are unreviewed**.
An absent crosswalk row means only that review has not been completed; it is not negative evidence
of an acquisition, name change, novation, or continuity.

The clean cohort is less exposed but not exempt: **201 of 205** entities meet the 0.90 continuity
threshold, while the other four are included in the reviewed priority tranche.

### Corporate event versus federal contract novation

A corporate event and a federal contract novation are different facts. An acquisition release,
SEC filing, state corporate record, or documented legal name change can support corporate history,
but it does not by itself show which federal contracts transferred or that the Government
recognized a successor in interest.

[FAR 42.1204](https://www.acquisition.gov/far/42.1204) permits the Government, when in its
interest, to recognize a third party as successor to a contract when the relevant assets transfer;
it also says a novation is unnecessary for a stock purchase when the contracting party does not
legally change and remains in control of the performing assets. More broadly,
[FAR subpart 42.12](https://www.acquisition.gov/far/subpart-42.12) provides the contracting-officer
process for recognizing successors, executing novation agreements, and handling change-of-name
agreements. Accordingly, corporate-event evidence proves neither that novation occurred nor that
novation was required. This study treats novation or a federal change-of-name relationship as
established only with contract-specific Government evidence, such as an executed agreement,
an SF 30 incorporating the agreement, or an equivalent contracting-office record.

### Evidence and attribution rules

- Preserve the raw observation first: dollars and actions remain valid as exact-UEI procurement
  records even when corporate attribution is unresolved.
- Review the full identity-pair key, not the UEI or a company-name fragment alone. Record the
  corporate relation, event date and date basis, same-entity assessment, confidence, sources, and
  reviewer notes. Low similarity alone never supplies a relation.
- Keep `corporate_relation` separate from `contract_relationship`. Corporate sources can support
  the former; only contract-specific Government evidence can confirm novation or a federal
  change-of-name agreement.
- Apply attribution treatments consistently:

  | Treatment | Current rows | Permitted use |
  |---|---:|---|
  | `temporal_split_required` | 11 | Split actions at the supported corporate-event date and label pre- and post-event identity explicitly before making firm-specific claims. If an exact event date is unresolved, defer the split and the claim. |
  | `same_entity_continuity` | 1 | Aggregate as one entity only with documented same-entity continuity, while retaining the former/current names and corporate-event provenance; do not describe this as confirmed novation. |
  | `unresolved_exclude_from_original_firm_claims` | 2 | Keep UEI-level observations, but exclude the pair from original-SBIR-firm, successor, or acquirer attribution until legal and contract continuity is resolved. |
  | Unreviewed | 92 | Retain in the review queue and UEI-level totals; do not default missing review to either continuity or acquisition, and omit from claims that require resolved identity. |

### Scope boundaries

This workstream does not search for successors or acquirers that use a different UEI. It therefore
cannot discover cross-UEI transfers, new parent identifiers, or all post-acquisition activity. The
queue can also miss an acquisition that preserves a similar name and can flag an ordinary rebrand
or harmless naming difference. Because selection begins with a name-similarity trigger and the
reviewed tranche intentionally emphasizes dollars and clean-cohort cases, neither 106/1,266 nor the
14 reviewed histories is an acquisition-rate estimate. The workstream supports case-level
attribution decisions only; it does not estimate acquisition prevalence or causality.

## How to use the results

For near-term SBA or ecosystem outreach, begin with the **1,462 public active-SAM target-code
registrants without a current A6 indicator**, then apply current size, ownership, socioeconomic,
and eligibility screens. Treat this as a lower-bound public-extract pool because opt-out entities
are absent. Use primary-code registrants as the narrowest declared-industry pool and any-code
registrants as the broader declared-capability pool.

For case studies of literal first-observed target entry, begin with the 203-entity literal cohort;
for the broader clean-pre-index target-origin lens, begin with 205. The sustained subsets are 67
and 68, respectively. Stratify by code, first-date award threshold, latency, agency, follow-up, and
name continuity. Apply the identity crosswalk's attribution treatment before naming an original
SBIR firm, successor, or acquirer; an exact-UEI total alone does not authorize that attribution.
For supplier-base screening, review both thin entity counts and high historical within-cohort
concentration, but validate current capacity, financial health, sole-source dependence, ownership,
and contract continuity from additional sources.

## Method and limitations

- The SBIR input is an official award CSV archived locally on September 7, 2026. That archive date
  is not a source-declared data-through date. The canonical loader collapses 219,590 source rows to
  219,535 versioned award records; validation retains 219,494. Of those, 152,801 rows have valid
  UEIs, yielding 17,168 exact-UEI entities. Results do not represent recipients without usable
  UEIs. Among 10,601 exact-UEI Phase II entities, 9,026 have an earliest plausible recorded end
  date; that field is not evidence of completion.
- SAM evidence comes from the September 7 Public V2 monthly extract. Public records exclude
  registrants that opted out of public display, so registration and A6 counts are lower bounds.
  The file includes current and recently expired records; headline counts retain only status `A`.
  A secondary NAICS is a declaration, not proof of sales, capacity, or historic operation.
- The SAM parser treated NUL characters as quote delimiters for 305 records whose free text
  contained literal pipes. It reconciled the BOF-declared and observed count of 895,359 data rows,
  required 142 parsed fields and an end marker on every data row, and required the EOF record to
  match the BOF record. These are parse and structural checks, not independent validation of SAM
  declarations or certification status.
- Procurement comes from a derived ledger built from frozen USAspending award-transaction
  archives. It contains exact-UEI prime contract transactions; IDV rows are excluded, transaction
  identifiers are unique, and award grouping remains scoped to UEI. Signed obligations retain
  deobligations, while gross-positive totals sum only positive actions. A contract NAICS describes
  the acquisition, not the recipient's corporate primary industry.
- Target-origin status requires an observed base transaction, no archive-boundary left censoring,
  and a target NAICS on the award's first observed action. It therefore excludes later target-code
  reclassification of an existing award. “First observed” remains bounded by the FY2009 archive;
  private, subcontract, classified, and older activity are not visible.
- Phase I/II exclusions use known SBIR award identifiers, structured research fields where
  present, and text patterns. The complement means “not classified as Phase I/II,” not commercial
  work. **91 entities** with positive target obligations have a structured or text Phase III
  marker. Because the source field is incomplete, neither the 710-event screen nor either entry
  cohort is a statutory Phase III determination.
- The observed transition is not proof of industry change and cannot establish that SBIR caused
  later procurement. Private sales, subawards, classified work, SAM history, mergers, novations,
  and activity before FY2009 are incompletely observed or absent.
- Identity review is pair-specific and incomplete. The 0.90 threshold identifies work for review;
  it is not a classifier of acquisitions or successors. Ninety-two candidate pairs remain
  unreviewed, and the workflow does not search beyond the matched UEI. Corporate-event evidence
  does not establish contract novation, while missing evidence is unreviewed rather than negative.
- Code-specific entity counts overlap. Historical concentration is limited to accumulated
  matched-SBIR-cohort obligations and is not a current market estimate. Public current-A6
  indicators are descriptive source fields, not authoritative certification adjudications.
- This is an `exploratory` artifact. A citable release would require a frozen study specification,
  complete input/output SHA enforcement, blocking validation checks, a declared estimand, a
  complete contract-grounded identity/attribution review for claims in scope, and a tracked builder
  that recreates the derived historical transaction ledger from the frozen raw USAspending
  archives.

## Reproducibility artifacts

The report generator is
[`scripts/data/defense_critical_naics_sbir.py`](../../scripts/data/defense_critical_naics_sbir.py).
Given the pinned SBIR and SAM inputs and the derived target-transaction ledger, it repeatably
rebuilds the report tables. It does **not** yet provide the raw-to-ledger build step; the archive
source manifest records raw-file provenance, but promotion still requires a tracked, repeatable
raw-ledger builder. The companion notebook is
[`notebooks/explorations/a_defense_critical_naics_sbir.ipynb`](../../notebooks/explorations/a_defense_critical_naics_sbir.ipynb).
Generated artifacts live under `data/reports/defense_critical_naics/`:

- `manifest.json` and `summary.json` — source hashes, cohort audit, definitions, and headline counts
- `archive_source/target_contract_transactions_fy2009_fy2026.manifest.json` — derived-ledger and
  raw-archive provenance
- `firm_evidence.csv` — one row per exact-UEI SBIR entity
- `sam_evidence.csv` — registration-level target evidence
- `contract_evidence.csv` — UEI × award × code evidence
- `identity_review_candidates.csv` — generated identity-pair review queue, priorities, dollar
  exposure, and merged review state
- `transitioners.csv` — clean-pre-index qualifying target-origin cohort
- `literal_first_entry_transitioners.csv` — literal first-observed target-entry cohort
- `sustained_transitioners.csv` — sustained clean-pre-index cohort
- `by_code.csv`, `horizons.csv`, and `transition_threshold_sensitivity.csv` — reported tables

The tracked review input is:

- [`data/reference/defense_critical_naics_identity_crosswalk.csv`](../../data/reference/defense_critical_naics_identity_crosswalk.csv)
  — tracked, evidence-linked identity review annotations keyed to the generated queue

Public-source documentation: [SAM entity extracts](https://open.gsa.gov/api/sam-entity-extracts-api/),
[2022 NAICS](https://www.census.gov/naics/), and the
[USAspending data dictionary](https://api.usaspending.gov/api/v2/references/data_dictionary/).
