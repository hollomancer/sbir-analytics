# SBIR UCC-1 Pilot — historical v1 cohort

**Audience:** Analysts evaluating public UCC data coverage.
**Evidence status:** retired cohort-dependent pilot; no current rate or count.
**Historical date:** 2026-05-16.

## Result status

The pilot selected firms from the unversioned Form D high-tier cohort now
identified as `person-or-zip-v1`. Its cohort sizes, sampled-firm counts,
coverage percentages, extrapolations, and firm-level Form D dollar comparisons
are suppressed. They must not be attributed to `corroborated-person-v2`.

The historical source-access observations remain useful: Delaware did not
offer the comprehensive free public debtor search the pilot required, while
California's public portal exposed searchable filing and lifecycle details.
Jurisdiction-of-organization remained a major coverage constraint because a
California operating address does not imply that the relevant UCC filing is in
California. These operational observations do not establish a population
financing rate.

## Historical computation path

The pilot used `sbir_etl/ucc/` to export a Form D-selected SBIR cohort, query
the California registry, reconstruct filing lifecycles, and match debtor names
and addresses. Git history preserves the earlier probe log and exploratory
tables for provenance.

The cohort export now requires a persisted current Form D tier-rule version.
That safeguard prevents an unversioned v1 file from silently producing a cohort;
it does not reopen this pilot's evidence gate.

## Rebuild condition

A replacement result requires:

1. a pinned, complete `corroborated-person-v2` Form D materialization;
2. quarantine or resolution of cross-filing and multi-CIK confidence records;
3. a pinned cohort export carrying the rule version;
4. a declared state/jurisdiction sampling frame and coverage denominator;
5. deduplicated UCC lifecycle records with human-reviewed debtor matches; and
6. new source and output hashes before any count, rate, or extrapolation is
   restored.

See the [Form D retirement record](sbir-form-d-fundraising-analysis.md) and the
[capital-pathway retirement](sbir-pathway-cohorts.md).
