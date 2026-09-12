# NASA, Air Force, and DOE SBIR/STTR commercialization outcomes

**Audience:** policy staff and program officers; exploratory / non-citable.

**Status:** Results withheld pending regeneration from pinned inputs

**Observation cutoff:** 2024-12-31

**Primary window:** Five years after a firm's first Phase II award from the agency

**Channels:** Non-Phase-I/II federal prime contracts, SEC Form D offerings, and public-record M&A

## Current result status

This page intentionally reports no scorecard, rates, counts, dollar totals, confidence intervals,
agency comparisons, horizon comparisons, or rankings. The previously tracked results were generated
before the current Form D ambiguity quarantine and canonical firm-roster policy. They also depended
on Form D and M&A files whose exact producing snapshots are not pinned by a committed run manifest.
The old values therefore cannot be reconciled to the current generator and have been withdrawn.

The generator remains useful for exploratory work, but a fresh local run is not enough to restore
claims here. Results should stay suppressed until every input is frozen by hash and coverage date,
the current code is recorded by Git commit, and channel-level and firm-level outputs reconcile to
those inputs.

## Question and estimand

The analysis asks how often firms in NASA, Air Force, and DOE SBIR/STTR Phase II cohorts have an
observed signal in each of three public-data channels after their first Phase II award from that
agency. The channels are kept separate:

- Subsequent federal prime-contract activity measures later federal-market participation. It does
  not establish technical lineage from the Phase II project.
- Form D amount sold measures disclosed Regulation D financing that can be linked to the roster.
- M&A measures candidate transactions present in the supplied public-record event file.

A missing signal means only that no qualifying match was found in the supplied channel data. It is
not evidence that a firm did not commercialize.

## Cohort and identity rules

- The cohort includes SBIR and STTR firms first receiving an in-scope agency Phase II on or after
  the Form D observation start in 2009. NASA covers the full agency, Air Force is selected from the
  DoD branch field, and DOE includes ARPA-E.
- A firm may belong to more than one agency cohort. Each agency clock begins at that firm's first
  Phase II award from the agency.
- Award identities use the shared `CanonicalMergePolicy.PRELOAD_V1` primitive. UEI is the primary
  key, DUNS is the fallback, and the policy's existing normalized-name behavior applies only after
  identifier matching. Records with the same normalized name but incompatible UEI/DUNS identities
  remain distinct.
- External event linkage tries UEI, then DUNS, then an existing normalized-name alias. An alias is
  admitted only when it resolves to one canonical firm across the complete retained award roster;
  conflicts are not resolved by choosing a cohort member.

## Channel measurement rules

Federal contract evidence comes from USAspending `Contracts_Full` archive extracts. Phase I and II
actions are removed using research codes and normalized PIIDs; a coded Phase III action on the same
vehicle remains eligible. Signed transaction obligations are netted per firm, and a non-positive
firm total does not count as a signal. Same-agency dollars use the same per-firm netting rule and
cannot exceed the firm's total positive net obligations.

Form D uses reported amount sold, excludes incompatible industry groups, and collapses amendments
by CIK, first-sale date, and security type. An accession or CIK linked to more than one canonical
firm is quarantined from every candidate firm. High-confidence links are primary and high-plus-medium
links are a sensitivity analysis.

M&A rows are deduplicated public-record matches. High-confidence links are primary and
high-plus-medium links are a sensitivity analysis.

Neither Form D nor M&A is a one-sided bound. Incomplete public coverage can omit real events, while
identity and event-classification errors can add false matches. Because those errors act in opposite
directions, the net bias is unknown.

## Interpretation limits

This is a descriptive portfolio comparison, not a causal evaluation of agency performance.
Agencies select different technologies, missions, firm types, and award vintages. The analysis does
not trace technical lineage from a Phase II project to a later procurement, financing, or
acquisition. It does not measure commercial revenue, private-contract revenue, survival, or the
full universe of private-capital and acquisition activity.

Contract linkage can use UEI or DUNS, whereas the supplied SEC and M&A artifacts are generally
name-keyed. The latter channels therefore carry greater identity uncertainty. Any regenerated
output remains exploratory and non-citable unless it is separately promoted under the repository's
evidence-tier contract.

## Requirements before results can be restored

Before adding numerical findings back to this page, a regeneration must:

1. Pin every award, contract, Form D, and M&A input by path, byte size, SHA-256, source coverage,
   and as-of date.
2. Record the generator Git commit, cutoff, horizons, identity policy, and random seed.
3. Run the current identity, PIID-exclusion, contract-netting, Form D amendment, and ambiguity
   quarantine logic.
4. Reconcile retained input rows, unique firms, excluded rows, event dollars, and every published
   numerator and denominator to the generated audit artifacts.
5. Review the generated policy memo and companion CSVs together; do not copy values from an older
   run or from an unpinned local data volume.

## Generator and artifacts

The canonical exploratory generator is
[`scripts/data/three_agency_commercialization_outcomes.py`](../../scripts/data/three_agency_commercialization_outcomes.py),
with archive extraction in
[`scripts/data/extract_three_agency_contracts.py`](../../scripts/data/extract_three_agency_contracts.py).
The thin exploration notebook is
[`notebooks/explorations/b2_three_agency_commercialization_outcomes.ipynb`](../../notebooks/explorations/b2_three_agency_commercialization_outcomes.ipynb).

Generated CSVs, the generated policy memo, and the run manifest live under
`data/reports/three_agency_commercialization/` in the data volume. They are not committed evidence.
Related source-method notes are the [Form D data dictionary](form-d-data-dictionary.md),
[Form D fundraising analysis](sbir-form-d-fundraising-analysis.md), and
[M&A exit analysis](sbir-ma-exit-analysis.md).
