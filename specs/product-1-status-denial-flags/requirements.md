# Product 1 — Status-Denial Flags — Requirements

> **Status:** Spec / design. **Buildable independent of the A3 benchmark gate** (entity-match
> driven; no text-derivation inference). Largely a **tuning/labeling layer over the existing**
> `phase_iii_retrospective_candidates` asset — not a new pipeline.
> Supports inventory question **B3** (Phase III undercount by agency; GAO-24-106398 [L14]) in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B3 — how large is the FPDS Phase III coding undercount, and which
same-entity follow-on awards lack Phase III designation?
**Answers for:** SBIR program managers, OII / oversight staff
**Complexity tier:** Relational (Tier 2)

## Done when

> An analyst can state: "Across FY[range], [N] contract awards to resolved SBIR firms sit in
> SBIR-lineage funding offices but carry no Phase III (SR3/ST3) designation in FPDS; this
> quantifies the [L14] undercount at [X]% and produces a reviewable flag queue."

## Background

FPDS Element 10Q (`research`, values SR3/ST3) is inconsistently coded; GAO-24-106398 [L14]
documents a material Phase III undercount. The repo already pairs SBIR priors to contracts and
excludes already-coded Phase III via `_is_phase_iii_already_coded` (`pairing.py:49`) — the awards
that *survive* that filter, restricted to the same resolved entity, are exactly status-denial
flags. This product tunes and packages that existing signal; it asserts a **flag for review**,
never a violation.

## Requirements

### Requirement 1 — Same-resolved-entity follow-on without Phase III coding
**User story:** As an oversight analyst, I want follow-on awards to a resolved SBIR firm that lack
Phase III coding, so that I can review probable undercounted Phase III actions.
#### Acceptance Criteria
1. THE System SHALL resolve contract awardees to SBIR firms via `resolve_entities` (UEI→DUNS→CAGE→
   name cascade), including renamed/acquired firms.
2. THE System SHALL retain only awards where the FPDS 10Q code is absent AND the awardee resolves
   to a firm with a prior Phase II, using `_is_phase_iii_already_coded` as the coded/uncoded gate.
3. THE System SHALL NOT label any award a violation; outputs are `flags` for review.

### Requirement 2 — Undercount quantification (benchmark anchor)
#### Acceptance Criteria
1. THE System SHALL report, per agency and FY, the count and dollar value of flags vs. coded
   Phase IIIs, producing the [L14] undercount estimate with data-coverage caveats.

### Requirement 3 — Reviewable output + adjudication feedback
#### Acceptance Criteria
1. THE System SHALL emit `data/derived/product1_status_denial_flags.parquet` + a review queue.
2. THE `PhaseIIICandidate` model SHALL gain a nullable `disposition` field so review outcomes can
   flow back as labels.

## Dependencies
- `phase_iii_retrospective_candidates` asset + `_is_phase_iii_already_coded` — EXISTS (extend)
- `resolve_entities` — EXISTS
- FPDS 10Q coding ingested (M0b, FPDS ATOM) — IN PROGRESS
- Full contract population (M0a) — NOT STARTED (needed for complete coverage)

## Out of scope
- No derivation inference (that is Product 2). No violation determination. No subcontract signal.
