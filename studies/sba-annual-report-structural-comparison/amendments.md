# SBA Structural Comparison — Freeze and Amendment Record

## Revision 0 — 2026-09-21 — candidate design created

**Status:** Candidate only. This revision does not authorize an evaluated run.

The blank population and prospective fidelity design were committed together at
Git commit `72695b18853b82a5efe66350ad9f416a9eea18f1`. No filled independent
extraction or validation result existed at that commit.

The candidate population contains 1,264 unique operands. It contains 632
`published_count` operands and 632 `recomputed_count` operands. The base keys
contain 53 jurisdictions for FY2020, 53 for FY2021, and 52 for FY2022. Each
jurisdiction has four program-phase cells.

The following results were visible before this candidate existed. They are
post-hoc context. They do not set a validation threshold:

- The historical exploratory comparison reported FY2020 `+179` counts
  (`+2.51%`).
- It reported FY2021 `+98` counts (`+1.44%`).
- It reported FY2022 `+56` counts (`+0.85%`).
- It reported 632 cell comparisons and a post-hoc tolerance-band verdict.
- It assigned 534 cells to `revised_upstream` without cell-specific evidence.
- It used dollar differences in some count-cell classifications.
- An eight-year extension showed that the three-year band was not a safe
  general rule and excluded FY2014 for an unresolved basis.

None of those verdicts or classifications is permitted in the citable product.

## Pre-run evidence audit — 2026-09-21

**Auditor:** Dalton, evidence-auditor role

**Verdict:** Go with required changes.

The auditor accepted the complete-population fidelity target and rejected an
evaluated run from the candidate unchanged. The required changes were:

1. Add durable exact-byte acquisition and a frozen source manifest.
2. Separate this product from the blocked historical reproduction study.
3. Freeze the final count-only producer and sidecar before extraction.
4. Remove post-hoc bands and unsupported causal classifications.
5. Name all 632 printed count cells as the estimand.
6. Make blinding operational with named, separate roles.
7. Define the submission schema, abort rules, and point interval.
8. Add fail-closed evidence gates and arithmetic checks.
9. Record formal approval and final hashes before extraction.

`validation-design-v1.md` was revised to include these requirements. The
`source-manifest.json` now names clean, exact-byte acquisition routes for all
four source files. The evaluated run remains prohibited until Revision 1 is
complete.

## Revision 1 — 2026-09-21 — formal pre-run freeze

**Status:** Approved for the first sealed independent extraction.

- Approver: Conrad Hollomon, repository owner, through the instruction to
  execute this bounded release plan.
- Approval time: `2026-09-21T22:21:33Z`.
- Git anchor: `d4f9d1975e61e8f2c5d8aea0739666041f394eb7`.
- Coordinator: `/root (Codex primary agent)`.
- Independent extractor: `/root/sba_blind_extractor`.
- Design SHA-256:
  `02e0fadd1f623096d20105fb4af47bba0b9c1c98d0c9ca10123da40907ec2da2`.
- Population SHA-256:
  `48dfdf1ea70e9a74378c21a3a661795540ebd6450c77365ebdad76c6569b68c1`.
- Source manifest SHA-256:
  `be8adfce554b2811cb612428bebab314f061b2a808b9cc957ad0311797388db3`.
- Production implementation SHA-256:
  `dff20751bec1424419ad8ed2406e082f8a6fca3eac8850c5d388e756ac24b56c`.
- Production sidecar SHA-256:
  `e86ab66905f65adaa7fdb721ced6bcbc7b3991a288ba37156f1efe9b4bed7381`.
- Environment lock SHA-256:
  `25a5a34ae5a3ee427d8a59c729065037a91c37797329e03dc9c7c76164a4b0b8`.
- Reproduction command SHA-256:
  `a8d2aa68e40e5748c241795599bf7c432abb013cfe7c26a020c5fbc29c6be538`.
- Blind packet manifest SHA-256:
  `68911d57fcb308794813d4ce1b10811ee333661ba799191f3a76068acf5b88e8`.
- Prior results visible at approval: the Revision 0 list above.

The permitted claim after a confirmatory pass is:

> For all 632 award-count cells printed in FY2020 Table 18, FY2021 Table 18,
> and FY2022 Table 20, this study reports the differences between those
> published counts and counts computed from the pinned September 17, 2026
> SBIR.gov export under declared row, year, program, phase, and jurisdiction
> rules. An independent full-population extraction reproduced all 1,264 count
> operands used to calculate those differences.

Every public rendering must state these adjacent non-claims:

- This study does not reproduce the unavailable publication-era SBIR.gov export.
- It does not certify SBIR.gov or SBA annual reports as complete or correct.
- It does not claim official-report equivalence.
- It does not compare or validate award-dollar totals.
- It does not measure commercialization, program effects, or economic return.
- It does not validate M&A, private-capital, or other repository outputs.

Do not change the design, population, source identities, producer, sidecar,
environment lock, packet, claim, or non-claims during the evaluated run. A
change invalidates the run and requires a new approved freeze.

### Run 1 invalidated before evaluation

The coordinator stopped Run 1 at `2026-09-21T22:27:42Z`. No validation-values
file existed. No first submission was sealed. The extractor attested that no
prohibited material was seen.

The coordinator found that the release still declared version `0.17.0`. The
new public evidence capability requires the minor release `0.18.0`. Updating
the synchronized package versions changes `uv.lock`, so it invalidates the
Revision 1 environment freeze even though the dependency set and production
sidecar do not change.

The abort attestation is preserved at
`validation/run-1-abort-attestation.json`. Its SHA-256 is
`40f21ec26368db1382fa77e88ca3b6151bad1e7697688c2c656c5f5828c85b0f`.
This invalid run has no validation score and cannot support promotion.
