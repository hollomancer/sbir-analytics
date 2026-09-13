# SBIR Capital-Pathway Cohorts — historical v1 materialization

**Audience:** Analysts working on capital-event sequences.
**Evidence status:** retired numerical cohort; not current and not citable.
**Historical date:** 2026-06-23.
**Historical PR:** #356.

## Result status

The former cohort counts, event totals, pathway frequencies, agency composition, and timing tables
are suppressed. The cohort was selected from `form_d_details.jsonl` under
`person-or-zip-v1`, including records for which a fuzzy person-name hit alone reached high. The
current `corroborated-person-v2` rule changes membership, and no complete replacement input or
capital-event materialization is pinned in the repository.

The historical artifact also inherited company-level pooling of confidence signals across Form D
filings and potentially across CIKs. A high tier did not prove that its corroborating signals came
from one filing or issuer.

## Historical computation path

The sequence fields were produced by `sbir_etl/capital_events/summarize.py` from local Form D,
SBIR, M&A, and contract artifacts. Git history preserves the earlier tables for provenance; they
must not be presented as v2 results.

## Rebuild condition

Rebuild only after the `form-d-fundraising` study's closed gate reopens. The replacement must:

1. use one pinned `corroborated-person-v2` Form D materialization;
2. reject unversioned or mixed-tier records;
3. quarantine unresolved cross-filing, multi-CIK, and duplicate-accession attribution;
4. rebuild the capital-event table and every pathway summary from that exact input; and
5. record source and output hashes before restoring any cohort count.

See the [Form D retirement and rebuild record](sbir-form-d-fundraising-analysis.md).
