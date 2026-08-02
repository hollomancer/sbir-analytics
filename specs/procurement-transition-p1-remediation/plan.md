# Procurement transition P1 remediation plan

## Objective

Make the monthly procurement packet safe to use as a human review queue. A displayed path must
identify one SBIR/STTR award, preserve the public evidence behind that identity, and never turn
missing state or an unvalidated ranking model into a plausible-looking acquisition recommendation.

The work is split into small pull requests because the source-matching repair will greatly expand
the candidate universe. Cold-start safeguards must land before that expansion.

## Phase 1 — award identity and path attribution (this PR)

- Separate stable award identity (`award_key`) from public identifiers and mutable row content.
- Build that identity from the full stable source compound; neither tracking nor contract number
  is unique by itself. Canonicalize multiple published editions of the same stable award.
- Carry `prior_award_key` through pairing, candidate IDs, evidence, and report joins.
- Use the same key for descriptive enrichment; skip ambiguous legacy enrichment instead of
  assigning one award's technical fields to another.
- Version the identity contract and fail closed on pre-migration normalized snapshots; raw award
  snapshots must be re-normalized during rollout.
- Preserve legacy candidate files only when their public award ID identifies exactly one award;
  fail closed on ambiguity.
- Render each awardee-to-procurement path from the award that produced that candidate, not the
  awardee group's first award.

Acceptance gates:

1. Awards sharing an Agency Tracking Number or contract number remain distinct through pairing
   and reporting when their stable source lineage differs.
2. Editing title, abstract, amount, or recorded end date changes `row_hash`, not `award_key`.
3. Multiple source editions of the same stable award become one canonical award with an auditable
   edition count.
4. Candidate IDs differ for distinct award keys even when their public identifiers are equal.
5. A legacy ambiguous `prior_award_id` raises a clear error instead of creating a many-to-many join.
6. Every rendered **Built on** statement comes from the candidate's associated award.
7. A pre-migration normalized snapshot cannot silently make the full history appear newly observed.

## Phase 2 — cold-start and historical execution safety

This phase must precede source normalization.

- Add an explicit bootstrap mode; a missing prior snapshot must not mark the full SBIR history as
  newly observed.
- Fail closed when a scheduled incremental run unexpectedly loses its baseline.
- Put bounded row/pair budgets and coverage metrics ahead of company enrichment and code joins.
- Define backfill semantics around versioned input snapshots and an explicit `as_of` date rather
  than today's active/deadline state.

Acceptance gate: a cache miss produces either a bounded bootstrap cohort or an actionable failure,
never an all-history monthly packet.

## Phase 3 — source normalization and enrichment provenance

- Introduce canonical organization identifiers/aliases for SBIR.gov and SAM.gov agency, branch,
  sub-tier, and office values; retain raw source values beside them.
- Replace the top-100 company workaround with measured coverage and a bounded fallback strategy.
- Stop assigning the first sorted company-wide NAICS code to every award. Treat company-level
  codes as separately sourced screening evidence, never as award-record facts.
- Require independent technical evidence for common-code follow-on matches and report coverage by
  source/gate.

Acceptance gate: realistic `Department of Defense` / `DEPT OF DEFENSE` records with matching
technical text survive hydration and pairing without fabricating award-level NAICS evidence.

## Phase 4 — ranking decision and auditability

- Restore deadline-primary packet order until an opportunity-to-firm model has fitted weights and
  forward, notice-grained validation.
- Treat the current fusion model as advisory research output, not a silent packet orderer.
- Populate every served feature, make missing values neutral, and persist score, model/version,
  ranking orientation, and fallback state in the master ledger and manifest.
- Reconcile the packet implementation with the PR 481/484 findings and the 85% hand-audit gate.

Acceptance gate: the same packet has a reproducible order, a visible fallback, and an audit record
that identifies the model and evidence used; unvalidated scores cannot reorder or drop leads.

## Release order

1. Phase 1: identity and attribution.
2. Phase 2: bootstrap and execution bounds.
3. Phase 3: normalization and provenance-aware matching.
4. Phase 4: ranking orientation and production validation.

Each phase should ship with a focused regression fixture derived from the failure that motivated it
and should not weaken the representative-distribution precision gate.
