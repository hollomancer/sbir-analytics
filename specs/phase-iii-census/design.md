# Label-free Phase III Census and Negative Controls — Phase 0 Design

**Status:** Phase 0 approved; **criteria frozen**. The target-code provenance, federal
Phase II award-grain, and SBIR.gov source-row-grain amendments below were approved before
any result was materialized. The source layer and prior-grain implementation now live in a
separate prerequisite change. The Phase 1 census is implemented and fixture-verified;
production census materialization is deliberately paused until the Phase 2 negative-control
eligibility problem is resolved, so no census count is quoted before its validation design
can run.
**Design date:** 2026-07-31.
**Approval date:** 2026-08-01.
**Provenance-amendment approval date:** 2026-08-01.
**Prior-grain amendment approval date:** 2026-08-01.
**SBIR.gov source-row-grain amendment approval date:** 2026-08-01.
**Research-question anchors:** B2 (federal-procurement transition), B3 (Phase II → III
latency and coding undercount), and E1 (SBIR/STTR identification) in
[`docs/research-questions.md`](../../docs/research-questions.md).
**Answerability label after Phase 1 implementation:** **[Implementation complete,
materialization paused — source and prior-grain prerequisites are separated; negative-
control eligibility must be resolved before any census count is materialized or quoted]**.

No census, sample count, coverage count, drop-off count, or sensitivity result was
computed while writing this note.

## Decision this note supports

This design is a parallel, label-free path. It does not replace, call, import, calibrate,
or validate the weighted `phase_iii_candidates` scoring path. In particular, it does not
use `_score_pair`, `TransitionScorer`, any weight, any score, any inclusion threshold,
text similarity, an embedding, a classifier, or a learned model.

“Census” means an exhaustive count of records satisfying a pre-registered observable
rule. It does **not** mean that those records have been legally or manually established as
Phase III. The statutory element that the target work “derives from, extends, or
completes” prior SBIR/STTR work is not directly observed in the current structured fields.

## Proposed estimand — one sentence

Among exact-UEI Phase II-award × federal-prime-contract-action pairs observable in the
existing retrospective source universe, estimate the surviving pair count, distinct-firm
count, distinct-contract count, and signed action obligations for post-completion actions
with an exact NAICS-or-PSC lineage proxy and no affirmative FPDS SBIR/STTR phase code,
under every pre-specified time-window × agency-continuity cell; this is an uncoded
follow-on-procurement proxy, not the prevalence of statutory Phase III awards.

The words **post-completion** and **lineage proxy** are deliberate restrictions. They are
the first two approval questions at the end of this note.

## Authorities and findings used

- [15 U.S.C. § 638(e)(4)(C) and (r)](https://uscode.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title15-section638)
  define Phase III as follow-on, non-SBIR/non-STTR-funded work that derives from,
  extends, or completes prior SBIR work. Section 638(r)(1) expressly permits the work
  **during or after** Phase II and with the same agency **or any other agency**; § 638(r)(4)
  authorizes awards “including sole source awards” but does not require sole-source or
  otherwise noncompetitive procurement.
- [GAO-24-106398 [L14]](https://www.gao.gov/assets/d24106398.pdf) describes Phase III as
  commercialization—including further R&D or testing—funded outside the SBIR/STTR
  set-aside, and says agencies may award it without further competition in some
  circumstances. It does not say that completion, same-agency procurement, or
  noncompetition is necessary.
- [NRC 2014 [L2]](https://nap.nationalacademies.org/read/18821/) reports that contracting
  officers do not consistently mark follow-on contracts as Phase III in FPDS and that
  FPDS-based analysis therefore undercounts transitions. This supports an explicitly
  **uncoded-candidate** scope; absence of a code is not affirmative proof of Phase III.
- [NASEM 2026 [L1]](https://www.nationalacademies.org/projects/PGA-STEP-17-08/publication/29329)
  says Phase III rates are not carefully measured and are difficult to quantify, with
  agency mission and research focus affecting observed rates. This supports reporting
  the full sensitivity table and matched controls rather than selecting one headline.

The `[L#]` labels above are the labels already used by the research-question inventory.
This note does not repeat the older solicitation spec's erroneous identification of
GAO-24-107036 as `[L14]`; `[L14]` is GAO-24-106398 in the inventory.

## Inherited pair universe

### Required boundary

The starting universe is the same normalized, nonblank, exact-UEI inner join used by the
retrospective candidate path:

```text
normalize(prior_recipient_uei) == normalize(target_recipient_uei)
```

where normalization is trim + uppercase and null-like values do not match. There is no
DUNS or name fallback, no new entity-resolution pass, and no second independently
implemented join. Every Phase II award for a UEI remains paired with every target
contract action for that UEI; the resulting many-to-many grain is preserved for the
drop-off ladder.

UEI equality is the inherited universe gate rather than a census clause. It implements
the statute's requirement that the Phase III agreement be with the Phase II awardee, but
it will miss acquisitions, successors, and UEI changes. Those misses are outside this
label-free path rather than repaired with fuzzy matching.

### Current-code incompatibility that must be resolved before Phase 1

There is currently no persisted, pre-gate S1 pair table. `pair_filter_s1` creates the join
in memory, removes targets already coded SR3/ST3 (or with a Phase III label), removes all
pairs without an agency match, drops the raw coding fields, and then returns the frame
that `phase_iii_candidates/assets.py` scores. Consequently, its returned frame cannot
produce an honest coded-status or agency drop-off.

The default producer also stores a PIID as `contract_id`, leaves the stable transaction
identifier inside nested metadata, and does not carry `research` or `sbir_phase` through
the `FederalContract` parquet schema. The current Phase II schema also leaves the pair
table's NAICS/PSC fields null on the default path. Treating absent columns as negative
codes or as taxonomy disagreement would silently fabricate the census.

Phase 1 therefore requires an additive shared boundary in `pairing.py`:

1. One UEI-only pair builder performs the existing join once as shared implementation,
   computes a nullable agency-match descriptor without filtering it, and projects the
   raw fields needed below.
2. Existing `pair_filter_s1` delegates to that builder and then applies its existing
   coded-status and agency gates, preserving scoring behavior.
3. The census calls the same builder and applies the frozen clauses itself.
4. The source projection must carry authoritative `target_research`, a stable
   `target_transaction_id`, a stable `target_contract_key` (prefer the USAspending
   generated unique award identifier over bare PIID), and populated NAICS/PSC fields.
   A genuine source `target_sbir_phase` may be carried as supplemental evidence, but it
   is optional and must never be synthesized from `research`. This is field pass-through,
   not a new join.

`phase_iii_candidates/assets.py`, `TransitionScorer`, and
`packages/sbir-ml/sbir_ml/transition/detection/` remain untouched. If the required source
fields cannot be carried through the shared pair boundary reliably, Phase 1 stops; it
does not substitute another data source or silently weaken a clause.

## Criteria review and exact predicates

All string comparisons below use trim + uppercase; blank, `None`, and `NaN` normalize to
null. All dates are parsed without imputation. `census_data_cut_date` is the documented
cutoff of the input snapshot, supplied explicitly and recorded in output metadata; it is
not the wall-clock time at which code happens to run.

| Order | Proposed clause | Justification | Exact field and comparison | Disposition |
|---:|---|---|---|---|
| 1 | The prior Phase II has an observable end date at the data cut. | This defines the mature, date-evaluable cohort for B3's post-completion question. It is **not** a statutory Phase III condition: § 638(r)(1) permits Phase III during Phase II. | `prior_period_of_performance_end` parses to a date and `prior_period_of_performance_end <= census_data_cut_date`. | **Keep only for the narrower post-completion estimand; approval required.** Do not describe a populated date as proof that work actually completed. |
| 2 | The target action occurs after the recorded Phase II end. | This is a conservative temporal ordering rule for the post-completion estimand, not the legal definition. The repo intentionally preserves negative Phase II→III latency because overlapping Phase III can be valid ([latency note](../../docs/phase-transition-latency.md#3-negative-latencies-are-real)). | `target_action_date` parses to a date and `prior_period_of_performance_end < target_action_date <= census_data_cut_date`. | **Keep only for the narrower estimand; approval required.** It excludes legally valid during-Phase-II work. |
| 3 | The target is not affirmatively coded as SBIR/STTR Phase I or II. | Section 638(r)(2) requires non-SBIR/non-STTR funding. A null code is only “not affirmatively coded,” not proof of funding source. | Required `target_research NOT IN {SR1, SR2, ST1, ST2}` and, only when a genuine `target_sbir_phase` source column exists, normalized `target_sbir_phase NOT IN {PHASE I, I, 1, PHASE 1, PHASE II, II, 2, PHASE 2}`. Null values pass; an absent `research` source column fails the asset. | **Add and keep.** The proposed SR3/ST3-only rule did not enforce the statutory non-SBIR funding condition. |
| 4 | The target is not already coded Phase III. | The estimand is the uncoded-candidate/undercount proxy supported by NRC [L2], not the total Phase III universe. Code absence is not Phase III evidence. | Required `target_research NOT IN {SR3, ST3}` and, only when a genuine `target_sbir_phase` source column exists, normalized `target_sbir_phase NOT IN {PHASE III, III, 3, PHASE 3}`. Null values pass; an absent `research` source column fails the asset. | **Keep as a scope restriction.** It is not a substantive Phase III criterion. |
| 5 | At least one exact administrative scope code agrees across the prior and target. | Section 638(e)(4)(C) requires work that derives from, extends, or completes the prior effort. Exact code agreement is a transparent label-free proxy for that otherwise unobserved lineage; it is not proof of derivation. | `(prior_naics_code and target_naics_code are nonnull and normalize(prior_naics_code) == normalize(target_naics_code)) OR (prior_psc_code and target_psc_code are nonnull and normalize(prior_psc_code) == normalize(target_psc_code))`. | **Add, but approval required.** Exact equality can miss legitimate R&D-to-production code changes. No prefix, distance, similarity, or learned rule is allowed. |
| — | Same agency or department. | No cited authority makes agency continuity necessary; § 638(r)(1) expressly permits another agency, and assisted acquisition can separate the awarding vehicle from the customer. | Removed from the core rule. Exact sensitivity comparisons are specified below. | **Cut as a defining criterion; retain only as the required sensitivity dimension.** |
| — | Not full-and-open / target is sole-source or limited. | Section 638(r)(4) authorizes sole-source awards but does not require them. Competitive awards can still be Phase III; “limited” has no independent statutory Phase III status. The existing repo guidance likewise notes that full-and-open awards can represent commercialization ([scoring guide](../../docs/transition/scoring-guide.md#caveats)). | No competition field decides inclusion. `target_competition_type` remains an audit column only. | **Cut.** Retaining it would redefine the estimand as a procurement-method subset, not a Phase III proxy. |

### Proposed cumulative ladder order

If the conditional clauses are approved, the ladder is frozen in this order:

1. all inherited exact-UEI pair rows;
2. prior end date observable at the data cut;
3. target action strictly post-completion;
4. target not affirmatively Phase I/II-coded;
5. target not already Phase III-coded; and
6. exact NAICS-or-PSC lineage proxy.

Agency restrictions are not silently baked into the starting pair frame. The six
sensitivity cells apply them after the full core ladder. Competition never filters.

Each ladder row reports, without prose selecting a headline:

- surviving pair rows;
- distinct normalized recipient UEIs;
- distinct `target_contract_key` values; and
- signed `target_obligated_amount`, deduplicated by `target_transaction_id` before sum.

This lets a reviewer reject any core clause and read the preceding row. Agency-restriction
effects are read from the sensitivity grid, including both requested alternatives.

## Sensitivity grid

The full approved core filter is rerun for all six cells. There is no preferred or
headline cell.

| Time after recorded Phase II end | Same agency/component | Same top-tier department |
|---|---|---|
| No maximum | Cell `none__same_agency` | Cell `none__same_department` |
| At most 5 calendar years | Cell `5y__same_agency` | Cell `5y__same_department` |
| At most 10 calendar years | Cell `10y__same_agency` | Cell `10y__same_department` |

Exact time comparisons, conditional on approval of the strict post-completion clause:

- **none:** no upper bound beyond `target_action_date <= census_data_cut_date`;
- **5 years:** `target_action_date <= prior_period_of_performance_end + 5 calendar years`;
- **10 years:** `target_action_date <= prior_period_of_performance_end + 10 calendar years`.

The anniversary endpoint is inclusive. Calendar-year arithmetic is used rather than a
fixed number of days. The 5- and 10-year values are the pre-authorized sensitivity values
from the handoff; no other window may be added after observing results.

Exact agency comparisons:

- **same top-tier department:** both values are nonnull and
  `normalize(prior_agency) == normalize(target_agency)`;
- **same agency/component:** the top-tier comparison above is true, both sub-tier values
  are nonnull, and
  `normalize(prior_sub_agency) == normalize(target_sub_agency)`.

These predicates do not rely only on `agency_match_level`, whose current value is merely
the finest observed match (`office`, `sub_tier`, or `agency`) and does not verify parent
equality. The output retains `agency_match_level` for audit.

Every cell reports exactly:

- distinct firms (`nunique(normalized prior_recipient_uei)`);
- distinct contracts (`nunique(target_contract_key)`); and
- total obligated dollars (signed sum of unique qualifying target transactions).

Surviving pair rows are also retained as an audit metric. The report is the table; no
summary may name one cell's number.

The sensitivity diagnostic varies one dimension at a time. It reports these seven
adjacent contrasts, with the first cell in each contrast the broader set and the second
the nested restriction:

1. `none__same_agency` → `10y__same_agency`;
2. `10y__same_agency` → `5y__same_agency`;
3. `none__same_department` → `10y__same_department`;
4. `10y__same_department` → `5y__same_department`;
5. `none__same_department` → `none__same_agency`;
6. `10y__same_department` → `10y__same_agency`; and
7. `5y__same_department` → `5y__same_agency`.

The first four are adjacent window effects holding agency continuity fixed. The last
three are agency-continuity effects holding the window fixed. For every contrast, the
diagnostic reports broader and narrower pair, firm, and contract counts; their signed
count deltas and fold changes; and the broader and narrower signed-dollar totals plus the
signed dollar delta. It also reports, for each count metric, the largest adjacent fold
change in the cumulative core-clause ladder.

The diagnostic fails only when an adjacent **window** fold change is greater than 3 for
distinct firms or distinct contracts **and** that same fold change is greater than the
metric's largest adjacent core-clause fold change. Pair-count changes, all agency
contrasts, and all signed-dollar changes are diagnostic only. A zero narrower count with
a nonzero broader count is recorded explicitly as an infinite fold; two zero endpoints
are a onefold no-change comparison. No `1.2` or other secondary cutoff is introduced.
Because non-adjacent cells differ on more than one dimension or skip a nested window,
their arithmetic ratio is never a checkpoint.

The two census parquet tables are persisted before this diagnostic runs. The checkpoint
is a Dagster asset check that reads both persisted tables and emits the complete set of
contrasts; a failed check leaves the audit artifacts available for review rather than
suppressing them.

## Grain and dollar invariants

The source is transaction-grained while `target_id` is generally a PIID, and one target
transaction can pair to several Phase II awards. Therefore:

1. Clause evaluation occurs at the Phase II-award × target-transaction pair grain.
2. A firm or contract survives a step/cell if at least one of its pairs survives.
3. A qualifying target transaction contributes its signed
   `target_obligated_amount` exactly once, regardless of how many prior awards it pairs
   with.
4. Distinct contracts use a source-stable generated award key, not bare PIID. PIID remains
   an audit field.
5. Negative obligations and zero obligations are retained. There is no dollar floor and
   no positive-only inclusion rule.
6. Missing or duplicate transaction keys fail validation rather than being deduplicated
   heuristically by PIID/date/amount.

These rules prevent pair fan-out from multiplying dollars and prevent PIID-level
deduplication from dropping modifications.

## Phase 1 artifact contract

After criteria approval, one additive Dagster asset named `phase_iii_census` will emit
two tables under the existing processed-data convention:

- `data/processed/phase_iii_census_dropoff.parquet` — one row per cumulative ladder
  step, in the frozen order, with all four audit metrics; and
- `data/processed/phase_iii_census_sensitivity.parquet` — exactly the six cells above,
  with distinct firms, distinct contracts, signed obligated dollars, and pair rows.

Asset metadata records both paths, `census_data_cut_date`, the repository-relative path,
revision, and SHA-256 of this exact design note, the path and SHA-256 of the append-only
amendment log, a machine-readable ordered clause list, and any reproducibility seed. The
asset hashes the raw bytes of this note before loading either input and fails closed if the
file is missing or differs from the approved digest compiled into the asset. It performs
the same fail-closed verification for the amendment log. It does not designate a headline
cell or repeat one cell as a summary metric. The asset follows the existing `Output` /
`MetadataValue` pattern without modifying the scoring asset.

The corresponding B2/B3/E1 inventory entries in `docs/research-questions.md` are updated
only after implementation and verification. Even then, the strongest honest label is
“answerable now, moderate confidence — deterministic uncoded-contract proxy and matched-
control discrimination; not validated true Phase III status.”

## Downstream design invariants already frozen by the handoff

- The same pure criteria function receives SBIR and control pair frames; it does not read
  `is_control`, arm labels, weights, or scores.
- A control has no Phase II record by definition, so its common-schema `prior_*` index
  cannot be left null and cannot be manufactured inside the filter. Before Phase 2, the
  study must freeze one arm-blind risk-set construction outside the filter. The proposed
  construction is to copy each matched SBIR firm's Phase II index rows (date, agency,
  NAICS, and PSC) to each of its matched controls, replace only the pair-join UEI with the
  control UEI, and run the same shared UEI pair builder. This preserves calendar time and
  gives both arms identical criteria inputs, but the copied row is explicitly a
  **pseudo-index**, not a claim that the control completed Phase II. It requires approval
  below.
- Control eligibility is evaluated against the complete available SBIR/STTR award
  history. Unreliable SBIR-negative status is a stop, not an assumption.
- Matching is 1–3 controls on primary NAICS, employee-count band, state, first federal
  contract year, and PSC family. Any new band boundary is a later stop-and-ask decision;
  none is introduced here.
- Balance reports every matched covariate's standardized mean difference and flags
  absolute SMD above the pre-authorized `0.1` value. Unresolved key-covariate imbalance
  stops the study.
- Arm results are distributions of criteria-met counts per firm, their overlap
  coefficient, and the ratio of firms clearing the complete criteria set—not arm means.
- The placebo permutes `prior_period_of_performance_end` across firms, preserves the
  marginal distribution, reruns the identical filter, and records its fixed seed. It
  does not change any criterion after comparison.

Detailed matching, balance, and placebo interfaces belong in the post-approval
requirements/design update. They cannot alter the criteria frozen here.

## Non-goals and prohibited drift

- No change to `phase_iii_candidates/assets.py`, `TransitionScorer`, or any file under
  `packages/sbir-ml/sbir_ml/transition/detection/`.
- No import or call of `_score_pair`, any scorer, any weight, or any candidate threshold.
- No float-valued inclusion decision, similarity score, rank, embedding, or classifier.
- No new firm-to-contract join and no DUNS/name fallback.
- No post-result tuning, preferred sensitivity cell, or single-number summary.
- No claim that the criteria establish legal Phase III lineage or identify every Phase III
  agreement.

## Freeze record

The repository owner approved Phase 0 **as written** on 2026-08-01. That approval freezes
all five decisions below:

1. **Narrow temporal estimand:** use the post-completion proxy while stating that
   § 638(r)(1) also permits Phase III during Phase II.
2. **Lineage proxy:** use exact full-code NAICS **or** exact full-code PSC equality.
3. **Agency and competition dispositions:** use agency continuity only as the specified
   sensitivity dimension and remove competition from inclusion.
4. **Shared pair boundary:** use the additive pre-gate builder and field pass-through
   without changing the scoring asset or creating a second join implementation.
5. **Control pseudo-index:** copy each matched SBIR firm's Phase II index rows to its 1–3
   controls while replacing only the UEI consumed by the shared pair builder.

The frozen criteria were committed as `989d9155c60e227ff2f921d3495e251a4246dda3` before
Phase 1 implementation began. No census may be materialized from a source that fails the
field-provenance and key checks above.

The chronological approval and visibility record is maintained in
[`amendments.md`](amendments.md). Existing records in that file are never edited,
removed, or reordered; a later change is appended as a new numbered revision with its
reason and an explicit statement of what result information was visible at approval.
Git history supplies the immutable prior versions. Materialization records and verifies
the current design and amendment-log byte digests, so the freeze is an executable input
contract rather than an unchecked commit label.

### Approved target-code provenance amendment

Before any census materialization, the repository owner approved making USAspending's
authoritative `research` field required and a separate `sbir_phase` field optional. The
[official USAspending data dictionary](https://api.usaspending.gov/api/v2/references/data_dictionary/)
defines `research_code` and maps it to `transaction_fpds.research`, including the complete
`SR1`/`SR2`/`SR3` and `ST1`/`ST2`/`ST3` domains. It does not define a separate
`sbir_phase` source field. The amendment prevents a redundant phase label from being
fabricated from `research`; a genuine supplemental phase field is still checked if another
source actually supplies one. No inclusion code set, ladder clause, sensitivity cell, or
estimand changed.

### Approved Phase II award-grain amendment

A pre-materialization integrity review found that federal Phase II rows were keyed by
bare PIID before `generated_unique_award_id` and that repeated transaction rows were
reduced by input order. That could collapse equal PIIDs from different agencies and make
the recorded completion date depend on archive row order. The repository owner approved
correcting this source grain before any count. This amendment changes neither a census
clause nor the estimand; it makes “Phase II award” deterministic at the already-approved
award × target-transaction pair grain.

Federal-system Phase II rows are frozen to this exact construction:

1. Every Phase II-coded federal transaction must have nonblank
   `generated_unique_award_id` and `transaction_unique_id`; absence is a source error,
   not permission to fall back to PIID or row position.
2. The canonical prior `award_id` is normalized `generated_unique_award_id`. Bare PIID is
   retained separately as `source_award_id` for audit and exact reconciliation only.
3. Transactions for one generated award are ordered by: a valid parsed `action_date`
   after a missing date, then parsed `action_date`, then normalized
   `transaction_unique_id`. The greatest row is the deterministic representative. A
   transaction identifier associated with conflicting source values fails validation.
4. Recipient identifiers/name, agency fields, NAICS, PSC, performance-period start and
   performance-period end come from that representative transaction. In particular,
   `period_of_performance_end` is the latest transaction's recorded *current* end date;
   it is not the maximum historical end date and is not filled from an older action.
5. `award_date` is the earliest valid action date for the generated award, and
   `award_amount` is the signed sum of its Phase II-coded action obligations. The output
   records the representative transaction identifier and number of source transactions.

SBIR.gov rows keep their source `award_id`. For reconciliation, their audit
`source_award_id` is the first nonblank value in the fixed order `contract`,
`agency_tracking_number`, then `award_id`. After federal transactions are collapsed,
SBIR.gov and federal rows may reconcile only on exact normalized `source_award_id`:

- no federal match leaves the SBIR.gov row as its own prior award;
- exactly one federal match preserves the federal generated key and authoritative
  federal dates, fills only missing NAICS/PSC from nonconflicting SBIR.gov values, and
  removes the supplemental duplicate; and
- more than one federal match, or conflicting nonnull supplemental taxonomy for one
  federal award, stops materialization instead of selecting by row order, agency-name
  similarity, or another heuristic.

This upstream correction changes identifiers supplied to every consumer of
`validated_phase_ii_awards`, including the existing retrospective candidate path. That
effect was disclosed before approval. It does not modify the scoring asset, scorer,
weights, thresholds, target filters, or the shared exact-UEI pair builder.

### Approved SBIR.gov source-row-grain amendment

A pre-materialization check of the full SBIR.gov history found that the legacy validated
input removed rows by input order when `award_id + phase` repeated. In the source snapshot,
distinct Phase II records can share that key, including records for different firms and
work. It also found the normalized identifier collision `NAVY38356`: one Phase II record is
for ARGON ENGINEERING ASSOC., INC. and has no UEI, while the other is for ALPHATECH, INC.
and has UEI `KM4XFJ7CJSY8`. Exact-UEI gating makes the Argon record unable to enter the
current census pair universe, but that downstream fact cannot justify silently deleting a
source award: source-grain validation occurs before the join, the record remains relevant
to source completeness and other consumers, and a future corrected UEI could make it
pair-eligible.

The repository owner therefore approved this exact SBIR.gov source-row construction before
any count:

1. Read all 42 SBIR.gov CSV fields as source strings in the CSV's declared header order.
   Collapse rows only when all 42 parsed source-field values are identical. No
   `award_id + phase`, recipient, title, or other partial-key deduplication is permitted.
2. For each retained row, define the base source identifier as the first nonblank value in
   fixed order: `Contract`, then `Agency Tracking Number`. This aligns with the already
   approved `source_award_id` reconciliation order. Blank and null-like values use the
   existing source-key semantics: trim, uppercase, and treat `""`, `<NA>`, `NAN`, `NONE`,
   `NULL`, and `\\N` as null.
3. Partition retained rows by `(normalized base identifier, normalized phase label)`, where
   the phase label uses the existing `I`/`II`/`III` normalization. This is the minimal
   correction to the legacy `[award_id, phase]` grain: normal Phase I/Phase II reuse of one
   source identifier does not by itself trigger a surrogate. If the normalized base is
   nonblank and its base-plus-phase tuple occurs exactly once, canonical `award_id` is the
   original, unmodified base source string.
4. If the normalized base is blank or its base-plus-phase tuple occurs more than once,
   canonical `award_id` is exactly:

   ```text
   SBIRGOV:<MISSING-or-normalized-base>:<source-row-sha256>
   ```

   `source-row-sha256` is the complete 64-lowercase-hex SHA-256 of the UTF-8 encoding of a
   JSON array containing the 42 parsed source-field values in declared CSV header order.
   Serialization uses `ensure_ascii=False` and `separators=(",", ":")`; a parsed null is
   JSON `null`. Values receive no case or whitespace normalization before hashing. The
   digest is never truncated.
5. Retain the original base value separately as `source_award_id` and the digest as
   `source_row_sha256`. A generated canonical identifier is a deterministic source-row
   surrogate, not an inferred award match or entity resolution.
6. The materialization manifest records the ordered 42-column list, its SHA-256, the input
   file SHA-256 and byte size, raw/retained/exact-duplicate counts, blank-base count,
   collision-group and collision-row counts, generated-ID count, output SHA-256, and the
   fingerprint serialization contract. A missing field, duplicate generated canonical ID,
   or manifest/output checksum mismatch stops materialization.
7. The full-history source is materialized at the census-dedicated default path
   `data/processed/phase_iii_census_sbir_awards.parquet`; it does not overwrite the shared
   legacy `enriched_sbir_awards.parquet`. A census run selects this path through the
   existing `SBIR_ETL__PHASE_TRANSITION__SBIR_AWARDS_PATH` override (or another explicitly
   selected v2 artifact satisfying the identical manifest contract). The general Phase II
   asset retains legacy input compatibility outside the census, but the census fails closed
   unless its selected SBIR source and the materialized prior frame have verified v2
   provenance.

The earlier exact reconciliation rule is correspondingly strict at both grains. A shared
normalized `source_award_id` reconciles only when it identifies exactly one collapsed
federal award and exactly one retained SBIR.gov row. Multiplicity on either side stops
materialization with `PhaseIIInputError`; no row may be selected or dropped by order, UEI,
DUNS, recipient name, or another heuristic.

This amendment adds no threshold, score, heuristic match, source join, or learned model.
It changes no census criterion or sensitivity cell. It replaces only the legacy
input-order source-row deletion and makes the complete SBIR.gov input reproducible at its
observable record grain.

### Approved executable-freeze and one-factor-diagnostic amendment

Before any census, drop-off, or sensitivity artifact was materialized, the repository
owner approved replacing the unchecked spec-commit constant with raw-byte SHA-256
verification of this design note and its append-only amendment log. A missing or changed
file now stops materialization before either source is loaded, paired, counted, or
written. The verified paths, digests, and revision are recorded in asset metadata.

The owner also withdrew the original global greater-than-threefold span checkpoint. The
six sensitivity cells are nested by construction, so comparing arbitrary extrema can
conflate both dimensions and make an expected arithmetic relationship look like a
finding. The replacement is the seven adjacent one-factor contrasts specified above.
Only an adjacent window effect on firms or contracts can fail the asset check, and only
when it is both greater than threefold and larger than that metric's largest adjacent
core-clause effect. The artifacts are written before the asset check runs. This amendment
changes no inclusion clause, sensitivity cell, window endpoint, agency predicate,
estimand, or output metric.

After approval, any further criterion change requires a new spec revision and a new
freeze before rerunning. An observed count, control overlap, balance statistic, or
placebo result is never a justification for changing a clause.
