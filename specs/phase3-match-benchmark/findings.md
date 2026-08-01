# Phase III benchmark: findings and decision record

Status: **provisional; rerun required on award-grade identities**.

## What survives from the donor research

The donor work established a useful scope decision: text similarity alone is
not strong enough to support a standalone “bypass lead” product. Structural
signals—firm identity, acquisition office, time ordering, competition type,
and explicit Phase III language—must remain primary. This successor preserves
that decision while replacing the donor's untested scripts with a fixture-tested
baseline that can be rerun.

The donor also reported a bounded DoD description-retrievable lower bound of
141 candidates among 962 scoped records (14.7%), representing approximately
$244.2 million. Those figures are **not yet reportable results here**: the donor
parser did not reliably extract nested parent-IDV identity and evaluated FPDS
transaction rows. They may be restated only after the run is reproduced with
PR #449's compound-key and award-grain rules and its provenance manifest is
retained.

## Product decisions

- **Status/denial flags (Product 1):** continue as a bounded review queue once
  its denominator is reproduced at award grain. Do not extrapolate a total
  dark universe from description-retrievable records.
- **Bypass leads (Product 2):** descope similarity as a standalone product.
  Similarity may remain one feature inside a structurally gated candidate
  score after benchmark precision is measured.
- **Recompete watchlist (Product 4):** defer. It requires option periods,
  solicitation/recompete events, and longitudinal award state that this
  bounded Element 10Q pull does not provide.

## Evidence still needed

1. Reproduce the bounded pull with a committed manifest and award-grade key.
2. Manually adjudicate a stratified P1/N1 sample to estimate proxy-label noise.
3. Report lexical results before adding embeddings, then test incremental lift.
4. Define completeness and refresh semantics through the #442 source adapter
   before any continuous or user-facing product is built.

No claim from the donor's later dark-layer, NASA, freeze/sample, or positive-
control experiments is carried into this successor; those paths lacked a
committed fixture/provenance contract or conflicted with the bounded result.
