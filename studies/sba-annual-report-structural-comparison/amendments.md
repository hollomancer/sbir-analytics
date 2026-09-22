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

## Revision 2 — 2026-09-21 — release-version correction and re-freeze

**Status:** Approved for a new first sealed independent extraction.

Revision 2 changes only the synchronized release version from `0.17.0` to
`0.18.0` and the resulting `uv.lock` bytes. The dependency set, design,
population, source identities, producer, production sidecar, claim, and
non-claims do not change. A clean regeneration produced the same 632-cell
sidecar with SHA-256
`e86ab66905f65adaa7fdb721ced6bcbc7b3991a288ba37156f1efe9b4bed7381`.

- Approver: Conrad Hollomon, repository owner, through the instruction to
  execute this bounded release plan.
- Approval time: `2026-09-21T22:28:59Z`.
- Git anchor: `7f712c011499fc444f9f8529143c6734ad5b9c58`.
- Coordinator: `/root (Codex primary agent)`.
- Independent extractor: `/root/sba_blind_extractor_2`.
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
  `b9f214496158828da145a19db9c7d5cb4fc52765eeacb9a394312a2b6cf34893`.
- Reproduction command SHA-256:
  `a8d2aa68e40e5748c241795599bf7c432abb013cfe7c26a020c5fbc29c6be538`.
- Blind packet manifest SHA-256:
  `fe77b3de60ae983624be3428d769b0fb3702b3989c5aeedd4af5f8980e6c2c8f`.
- Superseded packet manifest SHA-256:
  `68911d57fcb308794813d4ce1b10811ee333661ba799191f3a76068acf5b88e8`.
- Prior results visible at approval: the Revision 0 list above. Run 1 had no
  submission and no validation score.

The Revision 1 permitted claim and adjacent non-claims remain unchanged. The
new extractor receives only Packet v2. Any further frozen-artifact change
invalidates this run.

### Run 2 aborted at the PDF parsing gate

Run 2 used Packet v2 from `2026-09-21T22:37:50Z` through
`2026-09-21T22:37:55Z`. All packet, source, durable-URI, page-count, export
schema, and population preflight checks passed. The independent implementation
then classified an unlabeled numeric line on PDF page 53 as a possible table
row and aborted because it was not a mapped jurisdiction.

No validation-values file was written. The run has no score. The extractor
attested that it saw no prohibited material. The sealed implementation,
requirements, mapping, and abort attestation are preserved under
`validation/run-2/`.

This failure exposes a parsing ambiguity, not a count disagreement. A new run
must use a new extractor. It must distinguish mapped jurisdiction rows from
other numeric lines using the PDF's own table structure. It must still abort on
an unreadable or unmapped printed jurisdiction row, and it must still prove the
53, 53, and 52 row counts independently. No threshold, source, production
value, or completeness rule changes.

## Revision 3 — 2026-09-21 — PDF row-geometry clarification and re-freeze

**Status:** Approved for a new first sealed independent extraction.

Revision 3 adds the Run 2 parsing clarification to the independent extraction
instructions. A jurisdiction row is identified from its printed mapped label
and the table's count-column geometry. A numeric continuation, header, footer,
or total is not a jurisdiction row solely because it has the same number of
numeric tokens. The extractor must abort if an unlabeled line could be an
unreadable jurisdiction row.

This clarification does not change the 1,264-unit population, source bytes,
production logic, production sidecar, threshold, claim, or non-claims. The
production sidecar regenerated byte-for-byte with its existing SHA-256.

- Approver: Conrad Hollomon, repository owner, through the instruction to
  execute this bounded release plan.
- Approval time: `2026-09-21T22:40:05Z`.
- Git anchor: `b5ae2ddc01441e2e86cfc8e23237ae76ec563869`.
- Coordinator: `/root (Codex primary agent)`.
- Independent extractor: `/root/sba_blind_extractor_3`.
- Design SHA-256:
  `7373d7e189bf8dce3ec4611064f698571053b3fb397e213e1bf8873424839fa3`.
- Population SHA-256:
  `48dfdf1ea70e9a74378c21a3a661795540ebd6450c77365ebdad76c6569b68c1`.
- Source manifest SHA-256:
  `be8adfce554b2811cb612428bebab314f061b2a808b9cc957ad0311797388db3`.
- Production implementation SHA-256:
  `dff20751bec1424419ad8ed2406e082f8a6fca3eac8850c5d388e756ac24b56c`.
- Production sidecar SHA-256:
  `e86ab66905f65adaa7fdb721ced6bcbc7b3991a288ba37156f1efe9b4bed7381`.
- Environment lock SHA-256:
  `b9f214496158828da145a19db9c7d5cb4fc52765eeacb9a394312a2b6cf34893`.
- Reproduction command SHA-256:
  `a8d2aa68e40e5748c241795599bf7c432abb013cfe7c26a020c5fbc29c6be538`.
- Blind packet manifest SHA-256:
  `79eaa57a4834b5056c1e4ddd5522dbdb2ee26bc57fcef1a5944dd5ae37511e67`.
- Superseded Packet v2 SHA-256:
  `fe77b3de60ae983624be3428d769b0fb3702b3989c5aeedd4af5f8980e6c2c8f`.
- Prior results visible at approval: the Revision 0 list above. Runs 1 and 2
  were invalid and produced no validation score or filled submission.

The Revision 1 permitted claim and adjacent non-claims remain unchanged. The
new extractor receives only Packet v3. Any further frozen-artifact change
invalidates this run.

### Run 3 matched all values but is not confirmatory

Run 3 produced a sealed first submission with 1,264 observed values and no
missing values. It independently found 53, 53, and 52 jurisdiction rows and
632 printed count cells. It parsed 219,590 export rows and dropped one retained
row with blank `State`. The sealed submission SHA-256 is
`3f2d9aee873a2c828194cce562b944c617794983fc96d89deea6c2cfd006ef18`.

After sealing, the production reconciliation found 1,264 exact agreements out
of 1,264. The point interval is `[1.0, 1.0]` under the declared complete-
population method.

The run is invalid for promotion. Packet v3's checksummed manifest begins with
an accidental `+` byte and is not valid JSON. The extractor recorded that it
stripped this byte in memory before it decoded the manifest. The bytes matched
the prospective packet hash, but the packet did not satisfy its own manifest
format. This is a packet-integrity failure under the frozen abort rules.

The unchanged submission, independent implementation, mapping, attestation,
and non-confirmatory reconciliation are preserved under `validation/run-3/`.
The 1,264/1,264 result is diagnostic only. It does not set
`validation_result`, open materialization, or authorize the public claim.

## Revision 4 — 2026-09-21 — valid-JSON packet correction and re-freeze

**Status:** Approved for a new first valid sealed independent extraction.

Revision 4 removes the accidental leading `+` byte from the packet manifest.
The coordinator verified Packet v4 with Python's JSON parser before freezing
it. The source bytes, design, population, environment, production producer,
production sidecar, threshold, claim, and non-claims do not change.

- Approver: Conrad Hollomon, repository owner, through the instruction to
  execute this bounded release plan.
- Approval time: `2026-09-21T22:50:51Z`.
- Git anchor: `1b7760daf5b4980b57c07d73bf1f8ca2b2227f64`.
- Coordinator: `/root (Codex primary agent)`.
- Independent extractor: `/root/sba_blind_extractor_4`.
- Design SHA-256:
  `7373d7e189bf8dce3ec4611064f698571053b3fb397e213e1bf8873424839fa3`.
- Population SHA-256:
  `48dfdf1ea70e9a74378c21a3a661795540ebd6450c77365ebdad76c6569b68c1`.
- Source manifest SHA-256:
  `be8adfce554b2811cb612428bebab314f061b2a808b9cc957ad0311797388db3`.
- Production implementation SHA-256:
  `dff20751bec1424419ad8ed2406e082f8a6fca3eac8850c5d388e756ac24b56c`.
- Production sidecar SHA-256:
  `e86ab66905f65adaa7fdb721ced6bcbc7b3991a288ba37156f1efe9b4bed7381`.
- Environment lock SHA-256:
  `b9f214496158828da145a19db9c7d5cb4fc52765eeacb9a394312a2b6cf34893`.
- Reproduction command SHA-256:
  `a8d2aa68e40e5748c241795599bf7c432abb013cfe7c26a020c5fbc29c6be538`.
- Blind packet manifest SHA-256:
  `7ed7733028bd0a56a76ca966d25f65a2b3954324a7a193de4e61b72155aef76d`.
- Superseded malformed Packet v3 SHA-256:
  `79eaa57a4834b5056c1e4ddd5522dbdb2ee26bc57fcef1a5944dd5ae37511e67`.
- Prior results visible at approval: the Revision 0 list above. Runs 1 and 2
  had no score. Run 3 matched 1,264/1,264 but is non-confirmatory because its
  packet manifest was malformed.

The Revision 1 permitted claim and adjacent non-claims remain unchanged. The
new extractor receives only Packet v4. Any further frozen-artifact change
invalidates this run.

### Run 4 aborted at the source-identity gate

Run 4 stopped before the extractor read the design or source content. Packet
v4 was valid JSON, but its declared FY2022 PDF digest contained 63 characters.
It omitted one `f` from the 64-character source-manifest digest. Six of seven
declared file identities passed before this check failed.

No extraction started. No submission was created. The run has no score. The
extractor attested that it saw no prohibited material. The abort attestation is
preserved at `validation/run-4-abort-attestation.json`. Its SHA-256 is
`8c140d798d8fc666ba02563734163d48774534bf1a78b829374028982eab29c6`.

This is a packet-construction failure. It does not change the design,
population, source bytes, production values, threshold, claim, or non-claims.

## Revision 5 — 2026-09-21 — source identity correction and re-freeze

**Status:** Approved for a new first valid sealed independent extraction.

Revision 5 restores the omitted `f` in the declared FY2022 PDF digest. The
coordinator parsed Packet v5 and verified all seven declared files before this
freeze. Every declared digest has 64 lowercase hexadecimal characters. The
four source identities also match the authoritative source manifest.

The source bytes, design, population, environment, production producer,
production sidecar, threshold, claim, and non-claims do not change.

- Approver: Conrad Hollomon, repository owner, through the instruction to
  execute this bounded release plan.
- Approval time: `2026-09-21T22:55:30Z`.
- Git anchor: `91f208481c0328c3d80171956579dfe8200c6ffb`.
- Coordinator: `/root (Codex primary agent)`.
- Independent extractor: `/root/sba_blind_extractor_5`.
- Design SHA-256:
  `7373d7e189bf8dce3ec4611064f698571053b3fb397e213e1bf8873424839fa3`.
- Population SHA-256:
  `48dfdf1ea70e9a74378c21a3a661795540ebd6450c77365ebdad76c6569b68c1`.
- Source manifest SHA-256:
  `be8adfce554b2811cb612428bebab314f061b2a808b9cc957ad0311797388db3`.
- Production implementation SHA-256:
  `dff20751bec1424419ad8ed2406e082f8a6fca3eac8850c5d388e756ac24b56c`.
- Production sidecar SHA-256:
  `e86ab66905f65adaa7fdb721ced6bcbc7b3991a288ba37156f1efe9b4bed7381`.
- Environment lock SHA-256:
  `b9f214496158828da145a19db9c7d5cb4fc52765eeacb9a394312a2b6cf34893`.
- Reproduction command SHA-256:
  `a8d2aa68e40e5748c241795599bf7c432abb013cfe7c26a020c5fbc29c6be538`.
- Blind packet manifest SHA-256:
  `51033aca620e71f71fc18d6ae398d27fe238fbf7c7d6cda4e748ba7db3299314`.
- Superseded Packet v4 SHA-256:
  `7ed7733028bd0a56a76ca966d25f65a2b3954324a7a193de4e61b72155aef76d`.
- Prior results visible at approval: the Revision 0 list above. Runs 1 and 2
  had no score. Run 3 matched 1,264/1,264 but is non-confirmatory because its
  packet manifest was malformed. Run 4 stopped before extraction and has no
  score.

The Revision 1 permitted claim and adjacent non-claims remain unchanged. The
new extractor receives only Packet v5. Any further frozen-artifact change
invalidates this run.

## Revision 6 — 2026-09-21 — confirmatory result and validated promotion

**Status:** Authorized for `validated` only. Citation remains prohibited.

Packet v5 and all evaluated artifacts were frozen at commit `c4874c00` before
Run 5 started. The first complete extraction ran from `2026-09-21T23:01:28Z`
through `2026-09-21T23:01:38Z`. The sealed result artifacts first appear at
commit `56acfb0f` after coordinator reconciliation.

The extractor submitted 1,264 unique observed operands and no missing
operands. Coordinator reconciliation found 1,264 exact agreements out of
1,264. The complete-population point interval is `[1.0, 1.0]`. The interval
method is `exact complete-population point interval; no sampling`. The frozen
threshold was met.

Before the first complete extraction, the independent implementation located a
table title in both the table of contents and the printed table. It stopped
before a submission file, diagnostic file, extracted value, or diagnostic
count existed. The extractor then required the full count-column header with
the title. That correction implemented the frozen title-plus-count-column-
geometry rule. It did not change the design. The corrected implementation was
sealed before unblinding, and its first complete submission was not repaired or
rerun.

Runs 1, 2, and 4 produced no validation score. Run 3 matched 1,264 of 1,264
operands but remains nonconfirmatory because its packet manifest was not valid
JSON. None of those runs supports promotion.

The post-result evidence audit verified the freeze chronology, all sealed
component hashes, source identities, independent extraction, and claim
boundary. It authorized `evidence_status: validated` with
`threshold_met: true`. It did not authorize `citable`, materialization, merge,
publication, or release. The audit record is
`reviews/post-result-evidence-audit.md`.

The validated result supports source-capture and transformation fidelity only.
It does not establish agreement between the two upstream sources. The 632-cell
sidecar contains 276 exact comparisons and 356 unresolved differences. The
Revision 1 permitted claim and all adjacent non-claims remain in force, with
the added shared-mode-rule-error limitation.

## Revision 7 — 2026-09-21 — first named-reader remediation

**Status:** Validated and non-citable. A second named-reader review is required.

The first cold named-reader review returned `MISLABELED`. The packet lacked a
declared reader, did not link its generated result, and exposed premature
citation metadata. It also used "independent" without stating that independence
was between blinded roles and separate implementations inside this repository.

The reviewer selected the 276 exact and 356 unresolved comparison summary as
the sentence most likely to be quoted. The study now lists that summary and the
aggregate `+333` signed difference in `permitted_claims`. The claim states that
`+333` is not an omitted-award estimate, source-correctness verdict, or causal
explanation. These values are mechanical summaries of the already frozen
632-cell sidecar; they do not change the estimand, threshold, validation result,
or mismatch classifications.

The public packet now declares its readers, links the generated result, uses the
canonical `Validated, not citable` label, qualifies the blinded-role boundary,
includes fresh-checkout setup, explains the two digests, and defers citation
metadata until an immutable tag exists. The result page is now
`docs/public/sba-structural-comparison.md`.

A supplemental evidence audit independently recomputed the 276/356/+333
summary and approved it as a mechanical summary within the validated estimand.
It required no new validation and authorized a second cold named-reader review.

## Revision 8 — 2026-09-21 — named-reader gate completed

**Status:** Validated and non-citable. The named-reader comprehension gate passed.

The second cold review found only one inventory-routing defect: D1 did not
appear under **Start here** for the readers declared by the packet. The human-
authorized release work now routes D1 to SBIR program managers and to Treasury,
OMB, JCT, and state economic-development analysts. The inventory labels the
study `Validated, not citable` and blocks source-equivalence and economic-return
over-reads.

A fresh third review began at the root README. It returned `BRIEF`. The reader
correctly stated the source vintage, row-count grain, 632-cell coverage,
1,264-operand fidelity meaning, 276 exact and 356 unresolved cells, `+333`
signed aggregate, and all adjacent non-claims without oral context. The review
did not authorize citation, materialization, merge, release, or tagging.

## Revision 9 — 2026-09-21 — shared jurisdiction profile migration

**Status:** Evidence audit passed with required provenance-only remediation.

The repository identity guard found the exact jurisdiction map embedded in the
validated producer. The producer now calls the versioned
`SBA_ANNUAL_REPORT_TABLE_V1` profile in `sbir_etl.identity.geography`. That
profile preserves the exact 53 printed names and codes used by the validated
implementation, including Marshall Islands and excluding four territories not
present in the frozen comparison tables.

The current producer SHA-256 is
`bff52a594e4d77a2094c584e59365d4fd8be7dc381f2029246927fdebec5445a`.
The shared geography primitive SHA-256 is
`b2961c8f77086d3fb33e5f3e8fdce22a56da60004883d274c8431c1fcae00280`.
The previous validated producer remains identified in Revisions 1 through 6 as
`dff20751bec1424419ad8ed2406e082f8a6fca3eac8850c5d388e756ac24b56c`.

Acceptance requires byte identity with the frozen 632-cell sidecar, exact
reconciliation against all 1,264 confirmatory operands, the identity boundary,
focused primitive and producer tests, and an evidence-auditor decision. A
failure keeps the previous producer authoritative and blocks release.

The evidence audit verified all acceptance conditions and found no change to
the estimand, population, threshold, numerical result, claim, or non-claim. It
authorized the existing `validated` result to remain in force without a new
prospective validation run. It required regenerated public artifacts because
their producer-provenance field changes, followed by a clean replay and a fresh
cold named-reader review of those exact bytes.

The regenerated public JSON has SHA-256
`31c079dbbc6e1e3d635fd504a7ce28f0add511d1a7e7490e1e9c4d2205c9adc0`.
The regenerated Markdown has SHA-256
`140962e490df125d618a808e8871c34c339375bc4c633fc91d59c1e168c2055c`.
The clean reproduction command passed. A fresh cold named-reader review of
those exact bytes returned `BRIEF` with no remediation.

## Revision 10 — 2026-09-22 — minimal public setup and release-state correction

**Status:** Validated and non-citable. The result and validation are unchanged.

The completion audit found that the public page still instructed readers to run
the full workspace install. The release path now uses `make install-core` and
adds only the study producer source directory while it runs. An isolated locked
environment reproduced all 632 cells and 1,264 validation operands without
Dagster, Neo4j, `sbir_graph`, or `sbir_ml` installed.

The materialization blocker no longer lists the completed named-reader gate as
pending. It now lists only owner approval, the immutable version 0.18.0 tag,
tag-bound citation metadata, and a citable-promotion evidence audit.

These changes do not alter the estimand, source bytes, row grain, year basis,
jurisdiction profile, comparison cells, validation design, validation result,
claim, or non-claims. The renderer SHA-256 is
`d666b51fe4e18256c0359fccd88d1fcad9a610699861ab5a4d970b2ad2de7572`.
The regenerated public JSON SHA-256 is
`a0b81cc9d700de5fae4cfa1857a13fc593ba47223362968d55a0b071f1516e85`.
The regenerated Markdown SHA-256 is
`9f643c041a3a8747927c5565a7be5a0a3621d3d63ff30858f2ba614b6726c742`.
The canonical content SHA-256 is
`9a1e9d6081fa0aaae554727cde589cdc47a86a09f0988fa8b2bc887aea01ed49`.

The release-readiness evidence audit returned `GO`. It retained the validated
status without a new prospective run and authorized a fresh cold-reader review
of the exact revised public hashes. It did not authorize merge, tag,
publication, materialization, citation, or citable promotion.

The fresh cold named-reader review returned `BRIEF` on those exact hashes. The
reader reconstructed the claim, limits, minimal setup, and remaining gates
without oral context. No remediation remains. The verdict did not authorize
merge, tag, publication, materialization, citation, or citable promotion.

## Revision 11 — 2026-09-22 — disagreement disclosure and procedure hardening

**Status:** Validated and non-citable. The 632 cells and validation result are
unchanged. The amended claim-facing bytes require a fresh evidence audit and
cold named-reader review before release.

The owner review found that reporting only the signed aggregate understated
the cell-level disagreement because positive and negative differences cancel.
The unchanged frozen comparison has these descriptive summaries:

- 276 exact cells and 356 unresolved cells;
- a signed recomputed-minus-published sum of `+333`;
- an absolute cell-difference sum of `869`;
- 208 positive and 148 negative differences;
- 57 zero-versus-zero cells among the 276 exact cells; and
- 219 exact cells among the 575 cells where either value is nonzero.

The public result now reports those measures together. They are mechanical
summaries of the existing signed and absolute differences in the frozen
632-cell estimand. They do not estimate missing or extra unique awards, decide
which source is correct, classify a cause, or change a mismatch status.

The public result also discloses frozen row-handling diagnostics. Of 20,836
export rows retained for FY2020-FY2022 before jurisdiction handling, one had a
blank `State` and was excluded under the declared rule. The remaining 20,835
rows were counted. Sixty eligible jurisdiction/program/phase groups had no
retained row and received a recomputed count of zero. These values are fixed
diagnostics for this source vintage, not tolerances.

The study-only jurisdiction profile accepts 53 exact, case-sensitive,
untrimmed full names. It does not accept codes, aliases, lowercase variants, or
whitespace variants. The producer excludes and counts blank `State` rows, then
blocks every other unmapped nonblank value. `Marshall Islands` maps to `MH`
only in this study profile. `MH` is not added to the general canonical
jurisdiction set, and the study profile must not be reused as a general U.S.
jurisdiction normalizer.

### Run 3 retrospective limitation

The Run 3 attestation records the malformed packet's leading `+` byte and an
extractor finish time of `2026-09-21T22:49:03Z`. The reconciliation has no
timestamp and contains both the 1,264/1,264 numerical score and the invalidity
decision. The attestation, submission, and reconciliation first entered Git
together at commit `1b7760d`. The record therefore does not establish that the
coordinator formally declared the run invalid before computing or observing
its score.

The malformed byte existed in the prospectively frozen Packet v3, and the
extractor recorded it before handoff. Run 3 and its nonconfirmatory score were
disclosed before later packet freezes. Run 5 then independently matched all
1,264 operands. The record shows no observed score-shopping, but the procedure
had an audit hole. Run 3 remains nonconfirmatory and no public claim relies on
it.

For every future evaluated run, packet-gate invalidity must be declared and
sealed from gate evidence before reconciliation. An invalid run must receive
no numerator, threshold result, or reconciliation artifact. Any future
evaluated run must freeze this rule in a new prospective design version; this
revision does not rewrite `validation-design-v1.md` after its result.

The two confirmatory dependency wheels remain in the packet. They are exact
sealed components named by the attestation and seal inventory, and the replay
verifier requires their bytes. The version-only `requirements.lock` is not a
substitute for those evaluated artifacts. They are not installed by the normal
reproduction path.
