# SBIR M&A Dated Signal Study — Tasks

> **Status:** The pre-run protocol is complete. Amendment 1 authorizes only a
> private first retrieval of the official SBIR.gov award CSV; analysis and
> materialization remain unauthorized.

## T0. Establish the new-study boundary

- [x] Record the 2026-08-29 UTC planned as-of cutoff.
  - Verify: requirements, design, notebook, and study manifest agree.
- [x] Exclude the unrecoverable April 2026 analysis as an input, benchmark, or
  reproduction target.
  - Verify: no historical count or denominator appears as a planned input.
- [x] Declare `exploratory` tier, non-citability, and a closed materialization
  gate.
  - Verify: manifest validation passes with a named blocker.

## T1. Prepare, but do not execute, the evidence runway

- [x] Define the conditional source, cutoff, identity, audit, and validation
  protocol.
  - Verify: the design requires source provenance and candidate-level review
  before aggregation.
- [x] State the evidence-tier requirements for an external numerical claim.
  - Verify: frozen protocol, SHA enforcement, blocking checks, declared
  estimand, and human review are all named.
- [x] Add a cleared exploratory notebook and backlog entry.
  - Verify: notebook has no outputs, no source paths, and no executable
  analysis.

## T2. Human authorization and execution gates — partially complete

- [x] Approve the first private source acquisition and its restricted handling
  boundary.
  - Verify: Amendment 1 names the SBIR.gov source, local ignored storage,
    required provenance, cutoff check, and the no-Git/LFS/public-release rule
    before network activity.
- [x] Prepare a decision-ready source/estimand freeze packet without changing
  any acquisition or materialization authority.
  - Verify: `freeze-packet.md` fixes the proposed observed-signal quantity,
    source slate, identity/audit policy, and the specific evidence needed for a
    later owner decision; it remains explicitly not frozen.
- [x] Run the separately authorized private SBIR.gov cutoff/schema audit.
  - Verify: 112,951 parseable `Proposal Award Date` values span 1905-07-01 to
    2026-12-20; two fall after the 2026-08-29 cutoff, while the HTTP snapshot
    is dated 2026-08-01. The cutoff check fails; no firm frame is frozen.
- [x] Document the official source-handling constraints and prior-method reuse
  boundary.
  - Verify: `source-handling-review.md` limits reuse to candidate-signal
    predicates and directional review; it excludes the unrecoverable historical
    input, hybrid dates, confidence tiers, and exact-name event merge.
- [ ] Complete source-specific privacy/license/release-scope review before any
  public artifact or later source acquisition.
  - Verify: a later reviewed amendment records the review disposition and
  permitted handling for each source.
- [ ] Freeze the prospective firm frame, signal-source manifest, identity
  policy, date policy, and descriptive estimand.
  - Verify: hashes, sizes, counts, schemas, and cutoff coverage are recorded.
- [ ] Independently adjudicate the claim-bearing population or a prespecified
  blinded sample, and resolve disagreements.
  - Verify: reviewer records and an error/reconciliation report are retained.

## T3. Separate future promotion — blocked

- [ ] Implement and test a canonical materialization only after T2.
  - Verify: blocking asset checks fail closed for source, cutoff, schema,
  provenance, and reconciliation violations.
- [ ] Submit the result for evidence-auditor and independent human review.
  - Verify: manifest status and permitted claims are updated only after the
  evidence contract is satisfied.

## Out of scope

Discovery, LLM extraction, April-result reproduction, vintage/survival work,
comparators, agency causal claims, live Dagster materialization, and public
release are not tasks in this study.
