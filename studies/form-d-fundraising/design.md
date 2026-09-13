# Form D fundraising leverage — Revision 1 frozen design

**Lifecycle status:** retired pending a complete v2 rebuild.
**Tier rule:** `corroborated-person-v2`.
**Current numerical result:** none.

This revision replaces the historical 2026-04-23 design for purposes of any new
materialization. The historical result used `person-or-zip-v1`; it is not a result under
this design and is not authorized for citation. The retirement and visible-result record
is in [`amendments.md`](amendments.md).

## Intended estimand

Among SBIR/STTR awardees in calendar years 2009–2024, estimate two descriptive ratios from
SEC Form D `totalAmountSold` after year and excluded-industry filters:

1. **Program-level ratio.** Form D dollars from matched firms divided by all SBIR.gov award
   dollars in the window.
2. **Per-matched-firm ratio.** Form D dollars from matched firms with an in-window SBIR award
   divided by SBIR.gov dollars for that same subset.

Each ratio would be reported for high and high-plus-medium match tiers with a firm-level
percentile bootstrap using 1,000 iterations and seed 42. The bootstrap covers firm resampling
only. It does not cover identity error, Form D reporting error, or missing private capital.

Neither ratio is a lower bound: false-positive identity links and filing aggregation can move
the numerator upward, while missed or non-Form-D capital can move it downward. The ratios are
not NASEM's federal-contract follow-on leverage.

## Named tier rules

- `person-or-zip-v1` is the retired historical rule: a person score of at least 0.7 or an exact
  ZIP match reached high.
- `corroborated-person-v2` is the current rule: exact ZIP reaches high; a person score of at
  least 0.7 reaches high only with an exact ZIP or state overlap; person alone reaches medium.

Every `match_confidence` object must persist `rule_version`. Unversioned, mixed-version, or
unsupported inputs fail before analysis. `scripts/data/rescore_form_d_details.py` can apply a
named rule deterministically from stored person, address, and state scores without network
access. Its atomic rewrite is a tier migration, not a new identity validation.

## Filing and issuer boundary

The legacy detail producer pooled persons, states, ZIPs, dates, and incorporation evidence across
all filings attached to a company record before assigning one tier. Those filings can span more
than one CIK. Consequently, a v2 person-plus-state result can combine signals observed in
different filings or issuers. A shared CIK between a PIF-side and operating-side record can also
indicate record aggregation or an unresolved entity relationship; it is not automatic
corroboration.

Migrated records expose `match_confidence_scope`, including whether their signals may span
filings or CIKs. No high tier is described as trustworthy solely because it satisfies the
record-level v2 Boolean rule.

## Closed materialization gate

The study may be reactivated only after all of the following are recorded:

1. Pin the complete Form D-detail and SBIR input bytes by SHA-256, size, and row count.
2. Rescore the complete Form D corpus to `corroborated-person-v2`; prove exact input/output row
   coverage and one rule version across every output record.
3. Rebuild confidence at a declared filing/issuer grain, or quarantine and quantify every record
   whose corroborating signals may span filings or CIKs.
4. Resolve offering/amendment-chain aggregation at a declared SEC identifier grain so a filing is
   not counted twice or attributed to multiple SBIR firms without quarantine.
5. Run a realistic person-collision review and a version-2 PIF/CIK cross-link audit. These are
   identity diagnostics, not validation by themselves.
6. Recompute every ratio, interval, agency decomposition, pathway cohort, and dependent report
   from the same pinned v2 materialization. Record output hashes and refreeze this contract before
   restoring any number.

Until those gates pass, `bootstrap_form_d_leverage_ci.py` refuses materialization and all former
headline, agency, confidence-tier, and PIF-exposure numbers remain suppressed.

## What would make the estimate wrong

- Treating non-detection as zero private capital.
- Treating `totalOfferingAmount` as capital sold.
- Mixing the two denominators.
- Treating a record-level person/state conjunction as proof of same-filing identity.
- Combining multiple issuer CIKs or amendment restatements as independent capital flows.
- Calling a high tier validated without a human identity review.
