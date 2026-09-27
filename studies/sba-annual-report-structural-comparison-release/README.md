# SBA annual-report structural comparison — release page study

**Prepared for:** SBIR program managers and policy analysts in Treasury, OMB,
JCT, and state economic-development offices

## What this folder is

This study restates one result under the citation rule from #792. The result
is the v0.18.0 structural comparison in
[`../sba-annual-report-structural-comparison/`](../sba-annual-report-structural-comparison/).
Nothing is re-analyzed here.

This folder holds only the manifest, the generated public sidecar, and this
record. The result artifacts, the validation record, and the reviews live in
the sibling folder. `study.yaml` pins them there by path and hash.

[Read the generated public page](../../docs/public/sba-structural-comparison-release.md).

## Status

**Validated. Not approved evidence.** `studies/releases.yaml` says whether an
annotated tag binds this study. If none does, its release is pending. Cite the
unchanged result only from release v0.18.0, never from the page or a moving
branch. After a tag binds this study, cite from that release.

## Reproduce

Use a checkout that contains this folder and the selector-aware `Makefile`: the
release whose tag binds this study, or the moving branch. Then run:

```bash
make install-core
make reproduce-sba-structural SBA_STUDY_ID=sba-annual-report-structural-comparison-release
```

Do not run that selector from a v0.18.0 checkout. That tag does not contain
this study, and its Make target reproduces the predecessor.

## Record

`amendments.md` is the freeze and amendment record for this study. It names
every re-frozen byte and every governance decision.
