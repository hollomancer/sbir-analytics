# Product 2 — Bypass Leads — Requirements

> **Status:** Spec / design — **DESCOPE recommended per A3**
> ([../phase3-match-benchmark/findings.md](../phase3-match-benchmark/findings.md)). Against true
> same-contracting-office hard negatives, embedding separability is ≈ chance (AUC 0.564) and **no
> better than the lexical baseline**; realistic same-office retrieval is weak (P@1 0.23, ~2× random,
> optimistic upper bound). Recommendation: build **Tier-1 string-evidence-only**; demote the
> embedding (Tier 2) to a weak secondary signal for a review queue; reopen the embedding ranker only
> after M0a enables real-pool precision@k.
> Supports inventory question **B3** (Phase III derivation / bypass detection) in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B3 — which awards/solicitations to entity X plausibly derive from
firm Y's Phase II work (Y ≠ X)? Output is **ranked leads for human review, never violations.**
**Answers for:** OII / oversight staff, SBIR program managers
**Complexity tier:** Inferential (Tier 3)

## Done when

> An analyst can state: "For the well-described contract stratum, Product 2 surfaces the top-[k]
> ranked candidate derivations of a given firm's Phase II work, each with a two-tier confidence and
> a disposition slot; precision@[k] against hard negatives is [X]; every output is a lead, not a
> finding."

## Background

Phase III bypass — a non-developing firm receiving derivative work — leaves no certain public
signal. The A3 benchmark shows text similarity separates derivative from non-derivative pairs only
where FPDS descriptions are substantive (~25% of records), and is worse than chance on boilerplate.
Product 2 is therefore a **narrowly-blocked lead ranker**, not a detector. No ground-truth violation
corpus exists; leads must feed human adjudication whose outcomes return as labels.

## Requirements

### Requirement 1 — Blocking (candidate generation)
#### Acceptance Criteria
1. THE System SHALL build candidate (Phase II abstract → FPDS record) pairs blocked on funding
   office/command, PSC/NAICS adjacency, and time window (reuse `pair_filter_s1`).
2. THE System SHALL **exclude FPDS records whose description is below the length threshold** shown
   hopeless in A3 (~100 chars) — this is a hard gate, not a soft weight.

### Requirement 2 — False-positive kill chain (in order)
#### Acceptance Criteria
1. THE System SHALL run a `resolve_entities` **successor-in-interest** check first — if the awardee
   legitimately *is* the developing firm (novation / ASRC pattern), it is not a lead.
2. THE System SHALL run an **FSRS subaward** check — if the developing firm is X's subcontractor,
   the preference may be satisfied. *(BLOCKED: FSRS data absent repo-wide — see Dependencies; until
   ingested this check is a stub that flags "subaward status unknown," never clears silently.)*
3. THE System SHALL apply a **hot-area discount** from the count of similar Phase IIs in the
   blocking cell (many plausible sources ⇒ weaker attribution).

### Requirement 3 — Two-tier lead confidence
#### Acceptance Criteria
1. THE System SHALL assign **Tier 1** = string-level evidence (product/system name match, explicit
   award reference) and **Tier 2** = ModernBERT cosine + structural score, mirroring the house
   Tier-1-exact / Tier-2-fuzzy grammar.
2. Tier 2 scoring SHALL run **only on well-described candidates** (Req 1.2).

### Requirement 4 — Output + adjudication feedback
#### Acceptance Criteria
1. THE System SHALL emit a ranked leads table with a **nullable `disposition`** field, so human
   adjudication flows back as labels.
2. No field, comment, column, or log SHALL use `violation`/`noncompliance`; outputs are `leads`.

## Dependencies
- A3 benchmark viability call — GATE
- `ModernBertClient`, `resolve_entities`, `pair_filter_s1`, transition scorer `score_text_similarity` — EXISTS
- Successor-in-interest resolution through M&A — NOT STARTED (gap; blocks Req 2.1 completeness)
- FSRS / subaward data — NOT STARTED (blocks Req 2.2)

## Out of scope
- No violation classifier or determination. No subcontract-displacement detection. No training on
  violations. Descope to Tier-1 string-evidence-only if A3 thresholds miss on a realistic pool.
