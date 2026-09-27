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
