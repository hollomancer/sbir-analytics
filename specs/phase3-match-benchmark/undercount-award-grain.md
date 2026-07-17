# Phase III undercount: award-grain reproduction

Status: **reproduced at award grain through PR #449's identity contract.**

## What this resolves

`findings.md` retains the donor's bounded DoD result (141 of 962 described records, 14.7%, ≈$244.2M)
only as a provisional figure "not yet reportable here… may be restated only after the run is reproduced
with PR #449's compound-key and award-grade rules." This note supplies that reproduction.

## Result

`scripts/phase3_benchmark/undercount_award_grain.py` computes the described-but-not-coded undercount at
**award grain** using `sbir_etl.utils.award_identity.award_key_series` — the same nested-parent-IDV
compound-key rules as the benchmark. The coded (FPDS-derived) frame supplies its award identity via the
reconstructed USAspending unique key; the described (USAspending) frame supplies `generated_internal_id`;
both go through `award_key_series` as a precomputed `unique_award_key`, so standalone contracts (no parent
IDV) are keyed without fabricating identities.

| Agency | Coded transactions | Coded awards | Described awards | Overlap | **Undercount** |
|---|--:|--:|--:|--:|--:|
| DoD | 6,351 | 6,351 | 962 | 821 | **141 (14.7%)** |
| NASA | 1,038 | 1,038 | 202 | 186 | **16 (7.9%)** |

The coded frame is already award-grain (collapse ratio 1.00; 58% carry a nested parent-IDV), and the
non-zero described∩coded overlaps (821/186) prove the two sources join on the same key — so the figure
is **not** an artifact of counting FPDS transaction rows.

## Scope and honest limits

- **Provenance parity is partial.** This verifies the *derived* M0a coded/described frames; it does not
  yet re-pull them through a manifested puller with a raw-page hash. Full parity means regenerating both
  frames through the benchmark's manifested source path. The compound-key/award-grain *logic* is covered
  by a self-contained fixture test (`tests/unit/scripts/test_undercount_award_grain.py`).
- **The 141/16 is a lower bound.** The frozen research frame extends it to 191 (141 exact-phrase + 11
  broad text-scan + 23 grey-variant + 16 NASA; distinct award `gen_id`s). Those 50 additional flags also
  survive award grain but rest on text-pattern heuristics that warrant the same stratified adjudication
  `findings.md` calls for before they are reported.
- **No dark-universe total.** Consistent with `findings.md`: do not extrapolate a total dark universe
  from description-retrievable records. The ~1,000 dark estimate elsewhere is an explicit model, not a
  count.

## Bottom line

The donor's 141 (and NASA 16) **survive PR #449's award-grain contract, reproducibly and by the canonical
`award_key_series`.** The provisional flag on the bounded figure can be lifted; the 191 extension and any
dark extrapolation remain gated on adjudication and manifested provenance, respectively.
