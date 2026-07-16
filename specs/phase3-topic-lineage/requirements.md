# Phase III Topic-Lineage Recovery — Requirements

> **Status:** **NO-GO — spike ran, signal is empty (see Spike result below).** A same-firm
> structural-lineage attempt to recover uncoded Phase IIIs from the "dark" pool that text-semantic
> methods provably cannot enumerate.
> Supports inventory question **B3** (Phase III undercount by agency; GAO-24-106398 [L14]) in
> [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B3 — can a firm's *own* SBIR lineage keys (topic code, prior contract
PIID, solicitation number), cited in a later contract, recover uncoded Phase IIIs that carry neither
the SR3/ST3 code nor a "SBIR PHASE III" description?
**Answers for:** SBIR program managers, OII / oversight staff
**Complexity tier:** Relational → Inferential (Tier 2–3)

## Done when

> An analyst can state: "Beyond the 168 text-evidenced flags, same-firm topic-lineage matching
> recovers **[N] additional confirmed uncoded Phase III (~$[X]M)** — contracts that cite the firm's
> own SBIR topic / prior PIID / solicitation — moving them from the modeled-dark estimate into the
> verified column, with precision [P]% on spot-check."

## Background
The DoD+NASA Phase III undercount is ~168 text-evidenced flags plus a modeled ~1,073 "dark" residual
that is **text-semantically unenumerable** — the Product-2 benchmark showed abstract↔description
similarity is near-chance (AUC 0.56), the FPDS competition field is null, and a full-universe scan for
"SBIR PHASE III" added only +11. **Not yet tried:** the exact structural lineage a firm leaves when it
cites its *own* prior SBIR work — topic codes (`AF05-123`), prior SBIR PIIDs, or solicitation numbers —
in a later, uncoded contract. This is exact-match evidence, categorically different from fuzzy text,
and is the "Tier-1 string-evidence" path A3 recommended when it descoped the embedding ranker.

## Requirements

### Requirement 1 — Signal-availability gate (spike, go/no-go)
**User story:** As a pipeline engineer, I want the prevalence of structural lineage references in the
dark pool measured first, so we don't build a matcher for a signal that isn't there.
#### Acceptance Criteria
1. THE spike SHALL measure, over the ~90k "neither" (uncoded, non-self-describing) contracts, the
   share whose description contains (a) an SBIR topic-code pattern, (b) a plausible prior-SBIR-PIID
   reference, and (c) whether FPDS `solicitationID` is populated (sampled from FPDS ATOM).
2. IF structural references are effectively absent (~0%), THE effort SHALL STOP and report — the dark
   layer is confirmed unrecoverable by this signal too.

### Requirement 2 — Firm lineage keys
1. THE System SHALL build, per SBIR firm (resolved identity), the set of {topic codes, SBIR award
   PIIDs, solicitation numbers} from its Phase I/II awards in `award_data.csv`.

### Requirement 3 — Tier-1 exact matcher
1. THE System SHALL flag a firm's later DoD/NASA contract when its description or `solicitationID`
   contains one of **that same firm's** lineage keys → candidate uncoded Phase III.
2. Matches SHALL be exact/normalized string matches, not embedding similarity (Tier 3 is a
   tiebreaker only, never standalone).

### Requirement 4 — Validation + fold-in
1. THE System SHALL spot-check candidates against FPDS (genuinely Phase III? uncoded? sole-source?)
   and add confirmed matches as a new `topic_lineage` layer of the frozen undercount frame.

### Requirement 5 — Language discipline
1. Outputs are `candidates` / `flags` for review — never `violation` / `noncompliance`.

## Dependencies
- `award_data.csv` topic/solicitation/PIID fields — EXISTS (Topic Code, Solicitation Number, Contract)
- Recipient contract universe (95k, pulled) + coded/described sets — EXISTS
- Entity resolution (`resolve_entities`) — EXISTS
- ModernBERT (Tier 3 tiebreaker only) — EXISTS

## Out of scope
- **Cross-firm** bypass detection (that is Product 2). This is *same-firm* undercount recovery.
- Fuzzy abstract-to-description similarity as a primary signal (benchmarked near-chance).
- Any claim that a match is a violation — candidates feed human review.


## Spike result — NO-GO (Req 1 failed)
Ran the availability spike on the 90,792-contract dark pool:
- **Topic codes present but point the wrong way.** 3.1% of dark descriptions carry an SBIR topic
  code — but **77%+ explicitly say Phase I/II**, and the residual is unlabeled Phase I/II SBIR
  *research awards*, not Phase III follow-ons.
- **Same-firm temporal lineage is empty.** 2,672 dark contracts cite the recipient firm's **own**
  topic code — but **0** are ≥2 years after the firm's Phase II under that topic (regardless of
  phase text). They are the SBIR award contracts themselves (same year), not later Phase III.
- **Prior-PIID references: 0.2%** — also dead.

**Why:** the topic code in an FPDS description is an artifact of the SBIR *research award* (Phase I/II),
not a provenance tag on the Phase III descendant. Phase III follow-on contracts do not carry the
originating topic code, so there is no lineage bridge to recover them from FPDS text.

**Conclusion:** topic/PIID lineage recovers **0** uncoded Phase IIIs — the 7th ruled-out signal. It
confirms (does not overturn) the [dark-undercount-analysis](../product-1-status-denial-flags/dark-undercount-analysis.md)
finding that the dark layer is unenumerable from public data. **Recommend parking this PR** as a
documented negative result. Do not build Tiers 1–3.
