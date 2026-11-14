# Evidence audit — Revision 11

**Reviewer:** `pr788_revision11_evidence_audit`, project evidence-auditor role  
**Date:** 2026-09-22  
**Verdict:** `GO` for retaining `validated` and proceeding to a fresh cold
named-reader review

This verdict does not authorize merge, tag, publication, materialization,
citation, or `citable` promotion.

## Exact public hashes

- JSON: `b87c38ebcc43621d5bb83aaa1102006bc5ab61a8da33e8ed6645eb0b76f87dd2`
- Markdown: `8ab91c64cf60eed4876bf4b7dd3db6c4023c4d50de5c49f30c533b34c741ae02`
- Canonical content:
  `315587761de27092df09cb1c394e86f2ad1f3cdcc7a199341e849108d4e7537f`

## Contract

- Frozen specification: pass. Design SHA-256
  `7373d7e189bf8dce3ec4611064f698571053b3fb397e213e1bf8873424839fa3`,
  population, source identities, producer, and comparison were frozen before
  Packet v5 began.
- SHA enforcement: pass. All manifest references and the release checksum
  inventory verify.
- Blocking checks: pass for the validated artifact. Source, schema, key,
  arithmetic, status, validation, diagnostics, and round-trip mismatches fail
  closed. The citable materialization gate remains closed.
- Declared estimand: pass. The added measures are deterministic summaries of
  the existing frozen signed and absolute cell differences. They do not change
  the population, rules, or mismatch classifications.

## Findings

Independent arithmetic produced 632 cells, published total 20,502, recomputed
total 20,835, signed difference `+333`, absolute difference 869, 208 positive
cells, 148 negative cells, 276 exact cells, 356 unresolved cells, 57
zero-versus-zero cells, 219 exact cells among the 575-cell nonzero union, and
60 recomputed-zero cells.

Frozen evidence is unchanged. Sources, design, population, producer, geography
implementation, the 632-cell comparison, confirmatory artifacts, environment
lock, and reproduction command have no working-tree changes.

Diagnostics provenance is explicit. The renderer verifies diagnostics SHA-256
`bf8c932dd8725f2f3e66309c0318987d4a1eed485e6651d064f2037e9f68dbb8`,
requires `20,836 - 1 = 20,835`, checks counted rows against recomputed totals,
and checks 60 zero-filled cells against the sidecar.

The Run 3 wording is accurate and appropriately limited. The record proves the
malformed byte was noted in the attestation, but not that coordinator
invalidation preceded scoring. Revision 11 discloses that audit hole, leaves
Run 3 nonconfirmatory, and does not rewrite the prospective design.

Retaining the two wheels is justified. They are sealed evaluated components
named by the attestation and seal inventory. The reproduction verifier checks
their exact bytes; the version-only lock is not an equivalent provenance
record.

Public JSON and Markdown reproduce byte-for-byte. No new validation run is
required because no input, count rule, production implementation, frozen cell,
or confirmatory result changed.

## Checks

- 12 study manifests validated.
- 26 targeted renderer and geography tests passed.
- Exact 632-cell and 1,264-operand reproduction passed.
- Public artifact round trip passed.
- Release checksum inventory passed.
- Ruff, epistemic-tier, research-status, and `git diff --check` guards passed.

## Remaining gate

Run a fresh cold named-reader review against the three exact hashes above. Keep
the study validated and non-citable until all separately declared release gates
close.
