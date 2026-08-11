---
Type: Steering
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-08-03
Status: active
---

# Data Quality Contract

Data quality means that an artifact is faithful to its declared source, grain, identity rules, and
validation contract. It does not, by itself, make a research interpretation valid or citable.

## Sources of truth

- Threshold values live in `config/base.yaml` and subsystem configuration, not prose.
- Reusable validators live in `sbir_etl/validators/` and `sbir_etl/quality/`.
- Runtime metrics and alerts live in `sbir_etl/utils/monitoring/`.
- Dagster asset checks own materialization gates and observed metadata.
- Study validation and permitted claims live in `studies/<study-id>/study.yaml`.

## Required properties

Every maintained pipeline output should declare:

1. **Source and vintage:** where the input came from and when it was captured.
2. **Grain:** what one row represents.
3. **Identity:** the complete key and normalization profile.
4. **Transformation:** the code/configuration version that produced it.
5. **Checks:** observed counts, failure reasons, and whether a failed check blocks downstream work.

Avoid copying numeric thresholds into documentation. Link to configuration and record the observed
value in the materialization or study output.

## Severity and failure behavior

- **Blocking:** schema loss, ambiguous identity, incomplete key components, corrupted inputs, or a
  failed study/materialization gate. Stop before publishing downstream output.
- **Warning:** a known coverage limitation that still leaves the declared estimand valid. Continue
  only while recording the limitation and affected count.
- **Informational:** descriptive runtime or distribution metadata with no pass/fail consequence.

Graceful degradation is appropriate only when the output contract says the missing information is
optional. It must not silently change the population or estimand.

## Contract-award identity and grain

- A PIID is not necessarily an award key; order PIIDs repeat under different parent IDVs and across
  agencies.
- Prefer `contract_award_unique_key`. Otherwise require a complete compound of awarding agency,
  parent-IDV identifier, and PIID.
- USAspending/FPDS inputs commonly contain modifications. Declare transaction versus award grain
  and use `sbir_etl.utils.award_identity` to collapse rows deliberately.
- Aggregate award-level status before selecting a representative transaction. Filtering first can
  manufacture false uncoded candidates.

## Research-output checks

For reportable figures:

- regenerate every downstream artifact after changing a producer;
- verify that joins use the intended population, not merely compatible column names;
- compute load-bearing figures in code rather than typing them into prose;
- build an independent audit that recomputes figures from frozen inputs;
- treat missing public evidence as a measurement limit rather than a negative outcome.

Promotion beyond exploratory use follows the [epistemic tiers](epistemic-tiers.md) and
[study-contract](../../studies/README.md) requirements.

## Related references

- [Configuration](../configuration.md)
- [Pipeline orchestration](pipeline-orchestration.md)
- [Testing index](../testing/README.md)
- [Study contracts](../../studies/README.md)
