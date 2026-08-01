# Independent Phase III Transition Ground-Truth Set — Tasks

> Sequenced so the cheap, high-signal work (source catalog + a 10-case pilot)
> comes before the full collection. Stop and re-scope after the pilot if
> resolution or coverage is worse than expected.

## T1 — Source catalog (NASA + DoD)
Catalog the program-office Phase III transition sources: URLs, record shape,
whether they name the prior award / transition contract, and rough volume.
- NASA: `sbir.nasa.gov` success stories; TechPort (check for a prior in-repo puller).
- DoD: DoD SBIR/STTR success stories + component highlights (Navy/Army/Air Force), DSIP.
→ verify: a `sources.md` listing ≥ 2 agencies with per-source record shape and an
  estimate of how often the contract identifiers are actually present.

## T2 — Extraction schema + intake sheet
Freeze the per-case schema (firm, prior award ids, transition contract/program,
agency, year, source URL, evidence snippet, provenance, stratum) as a CSV/JSON
intake format with a one-page filling guide.
→ verify: schema file + guide committed; a reviewer can fill one row unambiguously.

## T3 — Pilot: 10 cases end-to-end
Curate 10 cases (5 NASA, 5 DoD) through the full pipeline: extract → resolve
identifiers → assemble candidate pool → tag provenance/stratum.
→ verify: resolution rate and coverage recorded; ≥ 6 of 10 scorable, or re-scope.

## T4 — Full collection (≥ 60, stratified)
Collect to ≥ 60 resolved cases, deliberately mixing `marquee`/`clean` with
`hard`-to-trace (known from non-marketing evidence). Log every unresolved /
coverage-gap case with a reason.
→ verify: ≥ 60 scorable; both strata represented (≥ 20 each); provenance tagged.

## T5 — Identifier resolution utilities
Scripts to resolve firm→UEI (`award_data.csv`) and transition→contract#
(USAspending/FPDS), reusing #467 recovery where possible. Unit-tested on fixtures.
→ verify: fixture tests pass; unresolved cases surface a clear reason, not a crash.

## T6 — Retrieval test + scoring
For each resolved case, build the candidate pool from the recovered corpus and
score the frozen ranker (`fusion_scoring`): precision@1/@3, MRR, bootstrap CIs,
split by stratum and provenance. Reuse the #467 audit/scoring plumbing.
→ verify: results table committed to the spec dir; independent-only number stated;
  compared to proxy 0.68@1.

## T7 — Decision memo
Write the go/no-go: does the externally-grounded precision justify letting fusion
*order* the packet (vs. deadline-primary)? State the number it rests on, the
strata behind it, and what's still unvalidated (forward-opportunity use, gate).
→ verify: memo committed; a clear recommendation, not a hedge.

## Deferred (documented, not this PR)
- Forward-opportunity validation (open-solicitation distribution transfer).
- Verified decoys for a routing/threshold gate.
- NIH/NSF/DOE agencies.
