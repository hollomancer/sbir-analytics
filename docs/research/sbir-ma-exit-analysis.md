# SBIR Company M&A Exit Analysis — historical materialization

**Audience:** Analysts studying SBIR-company acquisition signals.
**Evidence status:** retired combined result; no current Form D-dependent count.
**Historical date:** 2026-04-23.

## Result status

The former overall M&A totals, confidence-tier totals, Form D
business-combination count, overlaps, and agency tables are suppressed. The
Form D component was built from unversioned records now identified as
`person-or-zip-v1`. A fuzzy person hit alone could place a company in the
matched cohort, so those values cannot be presented as
`corroborated-person-v2` results.

PR #717 reported local counts of changed business-combination records, but the
underlying gitignored Form D corpus is absent from this checkout. Those counts
are not adopted as replacement findings.

## Historical method

The analysis combined two distinct signal families:

1. Form D filings whose issuer marked a business-combination transaction.
2. SEC EFTS mentions classified from filing type, item code, and nearby text.

The Form D flag is issuer-reported transaction evidence. It does not by itself
show that the candidate SBIR company and issuer are the same legal entity, name
the acquirer, or resolve amendment chains. The historical producer also pooled
confidence signals across all filings attached to a company record and could
pool more than one CIK.

The EFTS classifier has a separate event-confidence meaning; it must not be
used to upgrade a weak Form D entity link. Git history preserves the earlier
exploratory methodology and tables for provenance.

## Rebuild gate

Before restoring a Form D-dependent M&A count:

1. pin the complete Form D and EFTS inputs by hash, size, and row count;
2. require one persisted `corroborated-person-v2` rule version throughout;
3. score or quarantine links at a declared filing/issuer grain, including
   multi-CIK records;
4. collapse amendments and duplicate accessions under a declared SEC key;
5. recompute Form D and EFTS channels separately before merging them; and
6. complete human review of the identity links used for any high-tier claim.

Passing the v2 Boolean rule alone does not make every high-tier M&A record
trustworthy. Until the gate closes, only the existence of the historical
pipeline—not its numerical output—is current documentation.

See the [Form D retirement record](sbir-form-d-fundraising-analysis.md) and
[`studies/form-d-fundraising`](../../studies/form-d-fundraising/study.yaml).
