# Reproduce the SBA structural comparison

**Prepared for:** SBIR program managers and policy analysts in Treasury, OMB,
JCT, and state economic-development offices

Use Python 3.11 or 3.12 and `uv`. Docker, API keys, and running services
are not required. The source bundle is about 402 MB.

## Run the public check

From a tagged release checkout, run:

```bash
git checkout v0.18.0
make install-core
make reproduce-sba-structural
```

The reproduction command adds the study producer source path for this run. It
does not install or start Dagster or the other workspace packages.

The command performs these checks before it reports success:

1. Retrieve the exact September 17, 2026 SBIR.gov export object version and
   the three official SBA annual-report PDFs.
2. Verify each byte count and SHA-256 against `source-manifest.json`.
3. Verify the export row count, ordered 42-column schema, PDF page counts, and
   three captured-table identities.
4. Rebuild all 632 count cells under `EXPORT_ROW_V1` and
   `AWARD_YEAR_FIELD_V1`.
5. Verify the generated CSV is byte-identical to the frozen count sidecar.
6. Reconcile every value in the 1,264-row separate blinded-role submission.
7. Rebuild the public JSON sidecar and Markdown page and verify both frozen
   hashes byte-for-byte.

The command must fail on a missing source, a changed byte, an unpinned path, a
schema change, a missing or duplicate cell, incorrect difference arithmetic,
an unequal blinded-role validation value, or a rendered-result mismatch.

## Inspect and challenge the claim

Read these files in order:

1. [`study.yaml`](../../studies/sba-annual-report-structural-comparison/study.yaml)
2. [`source-manifest.json`](../../studies/sba-annual-report-structural-comparison/source-manifest.json)
3. [`validation-design-v1.md`](../../studies/sba-annual-report-structural-comparison/validation-design-v1.md)
4. [`count-comparison.csv`](../../studies/sba-annual-report-structural-comparison/results/count-comparison.csv)
5. [`amendments.md`](../../studies/sba-annual-report-structural-comparison/amendments.md)

Report a challenge against the release tag and artifact SHA-256. Do not use a
moving branch as the cited object.

Read the [generated public result](sba-structural-comparison.md) for the bounded
claim, comparison summary, validation meaning, and adjacent non-claims.
