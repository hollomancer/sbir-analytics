# Phase III census — permutation-separation validation design (R16)

**Study:** `phase-iii-census`
**Design revision:** `phase-0-r16` (see `specs/phase-iii-census/amendments.md`, Revision 16)
**Status of this document:** frozen at merge; its SHA-256 is pinned in `study.yaml` and any
change is a new numbered revision, never an edit.

## 1. What this design tests, and what it does not

R15 ran one fixed-seed cross-firm completion-date derangement and recorded direction: the actual
census frame exceeded its placebo at the final cumulative clause on every metric. One draw gives a
sign, not a magnitude, and the frozen R15 contract expressly attached no inferential test to it.

This design runs the **same frozen placebo family** over a preregistered seed list and asks one
question: *how often does the actual frame exceed a placebo frame at the final cumulative clause?*
A high exceedance share means the temporal link in the frozen criteria is doing work that a
cross-firm reassignment of completion dates does not reproduce.

It does **not** test whether the frozen proxy identifies statutory Phase III awards. No label set
exists, and the existing limitation stands: an uncoded lineage proxy is not proof of a statutory
Phase III award. A `validated` rank reached under this design means *separation from the frozen
placebo family*, and the permitted claim recorded at promotion must say exactly that.

## 2. Placebo family (unchanged from R15)

Unit: normalized nonblank `prior_award_id`, each mapped to one firm and one completion-date value
(nulls included). Assignment: with a NumPy seed, randomly order firms, randomly order awards within
firms, concatenate, and cyclically shift the donor sequence by the largest single-firm award count.
Stop conditions, multiset preservation, fan-back rules, the null-safe `date_value_changed`
indicator and the mapping digest are as in R15. The family is a randomized cyclic group
derangement; it is **not** a uniform draw over all derangements, and the empirical null below is a
null over this family only.

## 3. Seeds

- Confirmatory seeds: `20260802 + i` for `i = 0 … 499` (N = 500), run in that order.
- The R15 seed `20260801` is **excluded** from the confirmatory sample because its result was
  visible when this design was written. It runs first, separately, as the equivalence
  precondition in §6.
- Seeds are distinct integers fed to `numpy.random.default_rng`, which hashes them through
  `SeedSequence`; consecutive integers give independent streams.

## 4. Statistic

For each seed, build the placebo frame and take the **final cumulative clause**
(`exact_naics_or_psc_lineage`) metrics using the frozen predicates, plus the six frozen
time-window × agency-continuity cells.

**Primary:** `surviving_pairs` at the final clause. A draw is an *exceedance* if
`actual > placebo` strictly; a tie is not an exceedance and is counted separately.

Numerator = exceedances; denominator = N = 500. Interval: Wilson score, 95%.

**Secondary (reported, no threshold):** `distinct_firms` and `distinct_contracts` at the final
clause, and `surviving_pairs`, `distinct_firms`, `distinct_contracts` in each of the six cells,
each with its own exceedance share and Wilson interval. `total_obligated_dollars` is descriptive
only because dollar totals are signed.

Why the final clause only: the R15 record shows the placebo frame carrying **more** distinct
contracts than the actual frame at three intermediate stages (0.896×, 0.886×, 0.879×) while the
actual exceeds at the final clause. A statistic defined over every stage would therefore be known
in advance to fail on a metric the criteria do not target. The estimand is the full-criteria
census, and the final clause is where it lives.

## 5. Decision rule

`threshold_basis: proportion`, `threshold_value: 0.95`.

**Threshold met** if and only if the Wilson 95% **lower bound** on the primary exceedance share
is ≥ 0.95. The point estimate is not the criterion. With N = 500 this tolerates at most 15
non-exceedances (485/500 → lower bound 0.9511); 480/500 has a point estimate of 0.96 and fails
(lower bound 0.9390).

Derivation: 0.95 is the conventional one-sided level for "the actual value sits in the upper tail
of the null"; it was fixed here without reference to any observed draw beyond the single R15 sign.
Requiring the lower bound rather than the point estimate is the same choice the repository made in
#726: a `validated` result carries its uncertainty, and the floor is cleared by the interval, not
by the estimate.

A miss is a result. Under #726, a design that ran as written and missed its threshold is recorded
with `threshold_met: false` and the study may hold `validated`; `citable` needs the threshold met.

## 6. Equivalence precondition

The per-draw path evaluates the three date-independent clauses once and the two date-dependent
clauses per draw, then applies the frozen final-stage summary and six-cell builder. Because every
core clause is a row-wise predicate, this is the same intersection `build_census_tables` computes;
fixture tests assert equality with the shared builder for several seeds.

Before any confirmatory seed runs, seed `20260801` is run through this path and must reproduce the
recorded R15 values exactly: placebo final clause 546,242 pairs / 1,985 firms / 21,357 contracts /
$46,386,904,542.06; actual final clause 727,292 / 2,369 / 28,665 / $55,080,851,466.46; assignment
mapping digest `c1c97a9c7f1c81105a17dc21888afb7493311605405272672608d950c9250119`. A mismatch stops
the run with no confirmatory draw taken, and the mismatch is itself recorded.

## 7. Execution

- Entry point: `scripts/data/build_phase_iii_placebo_permutation.py::run`, gated on a separate
  repository-owner approval of the R16 run (`owner_approved=True` asserts it; it does not grant it).
- Freeze verification precedes any input read; Phase 1 source provenance is verified as in R15.
- The draw count is fixed at 500 by the design and the runner refuses any other value.
- The run may be executed in resumable batches over the fixed seed list. A partial draw store is
  not a result: no exceedance table or manifest is written until every preregistered seed is
  present, and a store containing a seed outside the list is refused.
- Outputs: actual final-stage row and cells; per-seed final-stage rows, cells and mapping digests;
  the exceedance table; a JSON manifest carrying the freeze record, input digests, precondition
  record, and the primary result (numerator, denominator, ties, interval, rule, `threshold_met`).
- Runtime is unmeasured. Each draw evaluates two date predicates over the full pair frame and the
  six cells over the full-criteria survivors; the run is expected to take hours, not minutes.

## 8. What is fixed and what may not change after the run starts

Fixed by this document: the family, the seed list, N, the primary metric and stage, the exceedance
definition, the interval method, the threshold and its rule, the precondition values, and the
outputs. Any change to any of these after a confirmatory seed has run is post-hoc and may only be
reported under `post_hoc_analyses`, never marked confirmatory.

## 9. Visibility at freeze

The R15 single-draw result was visible in full — every stage, every cell, every metric, including
the intermediate-stage contract inversions — when this design was written. No R16 draw had been
taken, and the R15 seed is excluded from the confirmatory sample for that reason.
