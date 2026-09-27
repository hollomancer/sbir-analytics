# SBA Structural Comparison Release Study — Freeze and Amendment Record

This study is the successor product authorized by Revision 4 of
`specs/sba-annual-report-approved-evidence-release/amendments.md`. It carries
the `v0.18.0` result of `studies/sba-annual-report-structural-comparison`
under the citation rule from #792. Nothing is re-analysed.

## Revision 0 — 2026-09-26 — manifest created and replay at HEAD

**Status:** `validated`. Not approved evidence. Release pending.

The manifest pins the same result artifacts as `v0.18.0` by path and hash:
`results/count-comparison.csv`
`e86ab66905f65adaa7fdb721ced6bcbc7b3991a288ba37156f1efe9b4bed7381`, the
confirmatory validation values, the sealed components, and the reviews. It
re-pins five files at their HEAD hashes because they changed after `v0.18.0`:
`producer.py` (rename of `citable` to `approved`, no count logic change),
`uv.lock`, and the three study scripts that now take a study parameter.

The count stage ran at HEAD against this manifest with the four pinned
sources. It reproduced `results/count-comparison.csv` byte for byte. On that
basis the manifest records `validated`, restating the `v0.18.0` result of
1,264 of 1,264 operands with interval `[1.0, 1.0]`.

The manifest does not record `approved` and carries no `claim_approval`.

## Revision 1 — 2026-09-26 — presentation re-freeze and exact-byte reviews recorded

After Revision 0, the page wording changed twice. Both changes were made in
the renderer profile only. Nothing in the result, the estimand, the permitted
claims, the limitations, or the validation record changed.

1. The status paragraph now states the citation status under the #792 rule
   plainly. The first blocker was reworded to match.
2. A cold named-reader review of the page then returned `OVERCLAIMS`: the
   reproduce lead-in said "in a tagged release checkout", but no tag contains
   this study, and the `SBA_STUDY_ID` selector is ignored at `v0.18.0`. The
   renderer profile gained a `reproduction_lines` field that states this. The
   badge became "Validated; cite from release v0.18.0, not this page". The
   heading became "Release status and limits".

Re-frozen bytes at commit `7bc22b9dcd46da5a116746ff66c047aac90dbd46`:
`scripts/data/render_sba_structural_comparison.py`
`df6f65410e761b9f60b092abc599965b80a3ab68b5460f0c59fff729581ef142`,
`release/public-result.json`
`46aed9913753ad3059dbf0fb6b77f3241721af9c57ba5b7f00e63cafeed83003`
(content digest
`7ccf34ee0ab5e96d4f533c1711552b1e0425665f6eacb57e84f1b08798aaa473`),
and `docs/public/sba-structural-comparison-release.md`
`09b5b1f0617067028cfba228f7f0aa2ddebe0d6ed5e33fe2c7cd3bc9c756de7d`.
The audited manifest was
`ff48975e20bee5473dd6f77859734df997c836bc43505a8d71ce5c2795a0cd4d`. The only
later change to the manifest is the two review pins added by this revision.

The evidence audit of those exact bytes is recorded in
`reviews/successor-evidence-audit.md`. Every contract check passed. The
auditor reproduced the count stage byte for byte and verified that no replay
input changed afterwards. The audit's only `BLOCK` was that this record did
not yet exist.

The cold named-reader review of the exact page bytes is recorded in
`reviews/named-reader-review-1.md`. It returned `BRIEF` with no remediation.

With both records pinned, the page's statement that the result may be cited
as a validated result from release `v0.18.0` is licensed under Revision 4
rule 4. No release binds this study yet. Neither review authorizes a tag,
`approved`, a `claim_approval` block, or a Start-here edit.
