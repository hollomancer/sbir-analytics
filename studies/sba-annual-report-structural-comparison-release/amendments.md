# SBA Structural Comparison Release Study — Freeze and Amendment Record

This study is the successor product authorized by Revision 4 of
`specs/sba-annual-report-approved-evidence-release/amendments.md`. It carries
the `v0.18.0` result of `studies/sba-annual-report-structural-comparison`
under the citation rule from #792. Nothing is re-analyzed.

## Revision 0 — 2026-09-26 — manifest created and replay at HEAD

**Status:** `validated`. Not approved evidence. Release pending.

The manifest pins the same result artifacts as `v0.18.0` by path and hash:
`results/count-comparison.csv`
`e86ab66905f65adaa7fdb721ced6bcbc7b3991a288ba37156f1efe9b4bed7381`, the
confirmatory validation values, the sealed components, and the predecessor's
supporting reviews. It re-pins six files at their HEAD hashes because they
changed after `v0.18.0`: `producer.py` (rename of `citable` to `approved`, no
count logic change), `uv.lock`, the three study scripts that now take a study
parameter, and the `Makefile` wrapper that forwards the selected study ID.

The count stage ran at HEAD against this manifest with the four pinned
sources. It reproduced `results/count-comparison.csv` byte for byte. On that
basis the manifest records `validated`, restating the `v0.18.0` result of
1,264 of 1,264 operands with interval `[1.0, 1.0]`.

The manifest does not record `approved` and carries no `claim_approval`.

## Revision 1 — 2026-09-27 — governance and reproduction wiring reconciled

Revision 4 now follows Revision 3 and #792: a wording-only successor relies on
the existing validation, a byte-identical replay of the frozen result, and the
registered artifact round trips. It does not create a second evidence-audit or
named-reader gate. The two draft successor review records and their manifest
pins were removed. One final pinned claim-boundary review remains required only
for a future promotion to `approved`.

Release and citation limits now come from the successor renderer profile rather
than `materialization.blockers`. The closed materialization gate names the
actual operational condition: no Dagster asset, schedule, service database, or
other production destination is defined or authorized for this
presentation-only successor. The generated page says "Successor release
pending" and also says that no release is scheduled, while directing citation
only to the unchanged result in `v0.18.0`.

The reproduction guide and generated page require a checkout containing the
successor study and selector-aware `Makefile`. The wrapper is now frozen, a
dry-run test proves that `SBA_STUDY_ID` expands to the Python `--study-id`
argument, and a sentinel-hash test proves that the count stage uses the
supplied study manifest.

Re-frozen bytes:

- `Makefile`:
  `91ab000fbe6a2a173ea8c6db8f7be01a6c706d84080cb4d3f0a112888db8f46a`
- `scripts/data/render_sba_structural_comparison.py`:
  `d638774669356c2f65047c32a0d610ce4b346d18f07d173850da12178c42c593`
- `release/public-result.json`:
  `b905f85492301fdd0f06741126e1fd4132d15e00ebd82c7d11bf0fe08ede657d`
  (content digest
  `232fd6750e9dbc10f658350611165fc10b315cdc67d6736953bc30c822071748`)
- `docs/public/sba-structural-comparison-release.md`:
  `d54684cc9763a49d238b8f6a1f16ac1c6ba3e3aa4b04d29737ce598902758726`

Nothing in the result, estimand, permitted claims, limitations, validation
record, or frozen predecessor packet changed. This revision does not authorize
a tag, `approved`, a `claim_approval` block, or operational materialization.

## Revision 2 — 2026-09-27 — folder orientation and pinned record

This revision adds `README.md` to this folder. It says what the folder holds,
where the result artifacts live, and how to reproduce the page. It carries no
claim beyond the manifest.

This revision also pins `amendments.md` in `frozen_artifacts`. This file is
the register of every governance decision for the study, so its bytes are now
part of the frozen packet. Any later revision must re-pin this file after the
text is final.

No renderer input changed. The sidecar and page are unchanged:
`release/public-result.json`
`b905f85492301fdd0f06741126e1fd4132d15e00ebd82c7d11bf0fe08ede657d` and
`docs/public/sba-structural-comparison-release.md`
`d54684cc9763a49d238b8f6a1f16ac1c6ba3e3aa4b04d29737ce598902758726`. This
revision does not authorize a tag, `approved`, a `claim_approval` block, or
operational materialization.

## Revision 3 — 2026-09-27 — release re-freeze before the 0.20.0 tag

Spec Revision 5 authorizes this re-freeze. The page, the folder `README.md`,
and the release limits now state the binding condition instead of a dated
status, so they stay true after `studies/releases.yaml` binds this study and
CI freezes this folder. The version bump to 0.20.0 changed `uv.lock`, which
this manifest pins, so `uv.lock` was re-pinned in the same revision.

Re-frozen bytes:

- `uv.lock`:
  `10dc596d64d96a067a4ffbd051ac61a5a9c04a98c6334cd38b7e0d46422af642`
- `scripts/data/render_sba_structural_comparison.py`:
  `4870f5ab468fdb12047a9d9a8b70b84cfcd2998717b6ee51140b21fcd805ca14`
- `release/public-result.json`:
  `25921e23a0badd7e231694f0f91b6680d287e2ff01e377394a565e71791d76fe`
  (content digest
  `3a811cbb966d47a161597d5f59bcc276b487153ba8e43d647488546dc6d4f6dd`)
- `docs/public/sba-structural-comparison-release.md`:
  `1eeca99417696d24cf4e6dd9b5dc21011babc2504035790943852000d00c7c63`

Nothing in the result, estimand, permitted claims, limitations, or validation
record changed. This revision does not authorize `approved`, a
`claim_approval` block, or operational materialization. The tag and the
`studies/releases.yaml` binding are separate steps after this revision.

Every status sentence and every hash list in Revisions 0, 1, and 2 records
the folder as it stood at that revision. This revision replaced that wording
and re-pinned those bytes. The list in this revision is the current pinned
state. Read the earlier revisions as dated history, not as the current state.
If no annotated tag binds this study in `studies/releases.yaml`, its release
is pending; cite the unchanged result only from release v0.18.0.
