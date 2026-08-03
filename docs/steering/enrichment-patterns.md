---
Type: Steering
Owner: engineering@project
Last-Reviewed: 2026-08-03
Status: active
---

# Enrichment Patterns

Enrichment adds source-backed fields to an existing record. It must preserve the original value,
the source and vintage, the matching method, and enough evidence to audit why the new value was
accepted.

## Required flow

```text
validate source record
        │
        ▼
resolve canonical identity ──▶ query or join source ──▶ normalize candidate
        │                                                │
        └──────────────────────▶ score and retain evidence
                                                         │
                                                         ▼
                                              apply source-specific gate
```

The order and thresholds are source-specific. SAM.gov UEI recovery, USAspending contract linkage,
NAICS inference, SEC/Form D matching, and patent assignment matching do not share a universal
nine-step hierarchy.

## Identity boundary

Company-name normalization and similarity live in `sbir_etl/identity/`. An enricher selects an
explicit versioned `CompanyNameProfile`; it must not introduce a parallel RapidFuzz scorer or
unnamed normalization routine. Prefer stable identifiers such as UEI, CAGE, accession number,
patent identifier, or complete award key before fuzzy names.

See the [company identity contract](company-identity.md).

## Confidence

A confidence value is meaningful only with its method and calibration population. A `0.9` exact
identifier match is not interchangeable with a `0.9` model probability or fuzzy-name score.

Store at least:

- normalized and raw source identity;
- method/profile name and version;
- score and applicable threshold;
- source record identifier and vintage;
- ambiguity or competing candidates;
- whether the field is observed, derived, or imputed.

Downstream consumers should gate on the named method/profile contract, not a context-free global
confidence band.

## Source-specific strategy

Use the narrowest reliable path for each source:

1. deterministic source identifiers;
2. authoritative crosswalks with provenance;
3. exact normalized identity under a declared profile;
4. fuzzy or model-based candidates with ambiguity handling;
5. unresolved rather than an unsafe forced match.

Cache external responses only when the cache key includes the request identity and the response
retains retrieval time/source version. Rate limits and unavailable APIs should produce explicit
partial coverage, not silent empty matches.

## Orchestration boundary

Reusable retrieval and matching logic belongs in `sbir_etl`; Dagster assets own dependencies,
materialization metadata, retries, and asset checks. Enrichers should remain usable outside Dagster
and should not read configuration files directly—use `sbir_etl.config.loader.get_config()` or
injected settings.

## Verification

Test exact, fuzzy, ambiguous, missing, stale-cache, and source-failure cases. Report coverage by
method and source vintage. When enrichment affects transition scoring or reportable findings, run
the subsystem benchmark and follow the [data-quality](data-quality.md) and
[epistemic-tier](epistemic-tiers.md) contracts.

Current keys and thresholds are owned by [configuration](../configuration.md), not this guide.
