# Phase III Negative Controls and Placebo — Design

> **Status (2026-08-02):** Approved bounded foundation; empirical study and release gate
> remain blocked. The repository owner approved the decisions recorded below before any
> census, negative-control, or placebo result had been computed or seen.

This is a post-Phase-0 companion to the frozen
[`phase-iii-census`](../phase-iii-census/design.md) design. It does not amend that design,
its amendments, or its frozen constants. It adds only the data-independent control audit,
name stress flag, and one placebo permutation needed before a future matched-control
materialization can be approved.

## Approved decisions

The following decisions were approved on **2026-08-02 with no result visibility**:

1. Retained controls are labeled **“no observed exact-identifier SBIR/STTR match,”** not
   certified SBIR-negative.
2. The core eligibility exclusion is exact strict-normalized UEI/DUNS against the
   complete available SBIR/STTR history.
3. An exact normalized-name match to an identifier-free award recipient is only a
   worst-case stress-set/reporting flag. It is neither an upper bound nor an
   inclusion/exclusion rule, and exact names do not bound aliases.
4. Employee count is omitted, without a proxy or new bands. The limitation must be
   prominent in eventual methods and results.
5. The single placebo uses seed `20260801`. It shuffles
   `prior_period_of_performance_end` once at unique prior-award grain and propagates the
   assigned date to all fan-out pair rows for that award.
6. Every remaining methodological choice is an explicit question to resolve before the
   corresponding implementation or materialization. No result may answer a design
   question retrospectively.

## Bounded architecture

The implemented layer is deliberately pure and additive:

```text
canonical candidate rows + complete available SBIR/STTR history
                    |
                    +--> exact UEI/DUNS audit --> retained-label + exclusion reasons
                    |
                    +--> identifier-free exact-name reporting flag

existing exact-UEI pair frame
                    |
                    +--> fixed award-grain date permutation
                    |
                    +--> existing frozen census helpers (unchanged)
```

There is no source reader, matcher, Dagster asset, artifact writer, config object, or
generic study framework here. Those boundaries would force answers to unresolved
questions.

### Pure interfaces

`audit_exact_identifier_eligibility(candidate_entities, complete_award_history)` expects
an already-canonical candidate frame with `entity_id`, `uei`, and `duns`, plus a complete
available SBIR/STTR history frame with `uei` and `duns`. It preserves candidate columns
and appends:

- strict normalized identifiers;
- exact UEI and DUNS match booleans;
- a deterministic semicolon-separated exclusion reason containing every applicable
  match reason;
- `passes_exact_identifier_screen`; and
- the approved control label only for rows that pass.

Candidate `entity_id` is an interface key, not a decision about which registered-entity
population supplies candidates. It must be unique and nonblank so every exclusion is
auditable. A nonempty candidate frame with an empty history fails closed. The helper does
not assert that the caller supplied complete history; provenance verification belongs to
the future materialization.

`flag_identifier_free_name_stress_set(audit, complete_award_history)` expects an
`entity_name` in the audit and a `company_name` in history. Award rows enter the reference
set only when both strict identifier normalizers return no usable identifier. The helper
uses the existing `normalize_company_name` function and exact nonblank equality. It
appends a reporting flag and does not change the eligibility fields.

`permute_prior_end_dates(pairs)` has no seed argument: exposing one would invite repeated
runs and favorable selection. It validates the prior-award/date relationship, sorts the
unique normalized prior-award keys to make the mapping independent of pair-row order,
uses the fixed seed once, maps donor dates at award grain, and propagates the result back
to the original rows. It verifies the award-grain date multiset and fan-out invariant
before returning.

`build_placebo_census_tables(pairs, data_cut_date)` is intentionally a thin composition:
it permutes the one approved field exactly once, then passes that same in-memory frame to
the existing `build_dropoff_ladder` and `build_sensitivity_grid`. It returns both tables,
has no arm parameter, and has no alternative criterion path.

Future control construction must likewise call the existing
`phase_iii_candidates.pairing.build_uei_pairs` for pseudo-index rows, then the existing
`phase_iii_census.criteria` helpers. This spec does not copy either implementation.

## Exact identifier and name semantics

- UEIs are exact only after the repository's strict 12-character alphanumeric
  normalization.
- DUNS values are exact only after the repository's strict nine-digit normalization.
- A missing or malformed identifier is unusable exact-linkage evidence. It does not
  become evidence of nonparticipation.
- Both exact reasons are retained when both identifiers match, even if they point to
  different history rows.
- Company names use the repository's existing punctuation, whitespace, Unicode, and
  suffix normalization. No fuzzy score, alias list, DBA expansion, substring rule, or
  crosswalk is used.
- The name stress flag can miss true identity relationships and can flag unrelated firms.
  Its size is therefore not a contamination rate or upper bound.

## Employee count is deliberately absent

Employee count is not deferred inside the matcher and is not replaced. GSA's official
[Entity Management API documentation](https://open.gsa.gov/api/entity-api/) classifies
`assertions.sizeMetrics.averageNumberOfEmployees` as FOUO, while public entity data
includes fields such as UEI, name, NAICS, and PSC. GSA separately describes the
[public entity extracts](https://open.gsa.gov/api/sam-entity-extracts-api/) as the
unclassified public tier and requires FOUO permissions for FOUO extracts.

Consequently the public-input study omits employee count. Firm size can be associated
with both SBIR/STTR participation and procurement outcomes, so residual size imbalance is
a major known limitation. Every eventual methods and results artifact must say this
prominently. Revenue, small-business flags, award volume, or any other size proxy would
be a new design choice and is prohibited here.

## Arm blindness and inherited criteria

The census filter sees only pair fields. It cannot accept or inspect an arm label. SBIR
pairs, future control pseudo-index pairs, and placebo pairs all run through the same
frozen core clauses. The only placebo mutation is the pre-registered prior end date.

The implementation does not import or call a scorer, weights, thresholds, similarity,
embeddings, or ML. It does not modify `phase_iii_candidates/assets.py`,
`TransitionScorer`, or anything under `packages/sbir-ml/sbir_ml/transition/detection/`.

## Questions to resolve before any empirical implementation

Every item below is intentionally unanswered. The answer must be approved and recorded
before its code is written and before any result is viewed.

1. **SAM acquisition and provenance:** Which dated SAM public snapshot will be acquired,
   by which API/extract route, and which URL, file name, checksum, extract layout,
   registration-status scope, generation date, and acquisition timestamp must its
   manifest bind?
2. **Registered-entity candidate frame:** Which public SAM entities enter the candidate
   frame—active only, active plus recently expired, all-awards registrations, procurement
   registrations, domestic entities, firms with a federal-contract history, or another
   pre-declared population—and how are duplicate or successor registrations handled?
3. **SBIR/STTR history provenance:** Which exact full-history snapshot and manifest define
   “complete available history,” and which program/phase fields establish that every
   supplied row is in SBIR or STTR scope?
4. **Canonical candidate name:** Does the staged `entity_name` use legal business name
   only, DBA only, or a separately reported flag for each? How are missing names handled
   without turning alias expansion into an inclusion rule?
5. **Primary NAICS and state:** Which snapshot fields and missing-value rules define
   primary NAICS and state, and is state physical address or incorporation state?
6. **First federal contract year:** Which contract corpus, transaction/award grain,
   identifier resolution, date field, and observation-window rule derive first-contract
   year?
7. **PSC family:** Which authoritative taxonomy/version and deterministic mapping derive
   PSC family, which contract history supplies a firm's PSCs, and how are multiple or
   missing families handled?
8. **Matching algorithm:** Are covariates exact strata, distance terms, calipers, or a
   staged combination; what happens when fewer than the target one-to-three controls are
   available?
9. **Control reuse and tie-breaking:** May a control be reused across treated firms or
   pseudo-index assignments, what reuse cap applies, and what deterministic ordering or
   random seed breaks otherwise equal matches?
10. **Multiple identifiers and organizations:** How are multiple UEIs/DUNS, corporate
    parents, acquisitions, successor entities, and identifier changes represented without
    introducing an unapproved identity method?
11. **Categorical and temporal SMD encoding:** Are NAICS, PSC family, and state expanded as
    indicator variables; is first-contract year continuous, categorical, or binned; how
    are pooled variance, zero-variance cells, missingness, and weighting handled?
12. **Key-covariate review:** Which encoded balance rows are “key” for the absolute `0.1`
    stop rule, and what action follows a failure without post-result rematching?
13. **Per-firm distribution grain:** Is a firm keyed by staged entity ID or UEI; how are
    multiple real Phase II indices, copied pseudo-indices, reused controls, and multiple
    target transactions collapsed into criteria-met counts?
14. **Control pseudo-index artifact:** What exact mapping schema binds each control to its
    matched SBIR firm and copied prior-award row, and how are provenance and one-to-many
    fan-out verified before `build_uei_pairs`?
15. **Output contracts:** What artifact paths, schemas, manifests, hashes, data-cut
    bindings, and review metadata are required for eligibility, matches, balance,
    per-firm distributions, stress-set reporting, and placebo outputs?
16. **Release evidence:** Which concrete artifact checks and reviewer sign-off replace the
    sentinel once—and only once—the negative-control and placebo evidence exists?

## Release discipline

The release sentinel remains deliberately failing. Green fixture tests prove only that
the approved pure mechanics behave as specified. They do not establish source
provenance, match quality, balance, or an empirical result, and they cannot close the
gate. This branch must not compute, materialize, or quote real census, control, or placebo
results.
