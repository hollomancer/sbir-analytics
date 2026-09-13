# DoD Form D leverage — historical v1 analysis

**Audience:** Defense industrial-base and SBIR program analysts.
**Evidence status:** retired numerical analysis; not current and not citable.
**Historical date:** 2026-06-21.
**Dependency:** [retired Form D fundraising study](sbir-form-d-fundraising-analysis.md).

## Result status

The former DoD aggregate, branch, time-series, per-firm, acquirer-type, and Form D-versus-FPDS
numbers are suppressed. They were computed from the same local `person-or-zip-v1` match corpus as
the retired fundraising study. No complete `corroborated-person-v2` rebuild is pinned in the
repository, so the old branch comparisons cannot be treated as current or carried into a demo.

Git history preserves the historical tables. Their earlier statistical intervals covered firm
resampling only; they did not cover identity-rule error, cross-filing signal aggregation,
multi-CIK attribution, or Form D amount reporting. They therefore do not establish that any branch
difference is trustworthy.

## Historical computation paths

- [`dod_form_d_leverage_decomposition.py`](../../scripts/archive/data/dod_form_d_leverage_decomposition.py)
- [`dod_form_d_followups.py`](../../scripts/archive/data/dod_form_d_followups.py)
- [`dod_fpds_substitution_test.py`](../../scripts/archive/data/dod_fpds_substitution_test.py)

These scripts remain for provenance. They consume `data/form_d_details.jsonl` and should not be
used to publish a result from an unversioned or mixed-version file.

## Rebuild condition

Recompute this analysis only after the parent study reopens its materialization gate. The DoD run
must use the exact same pinned v2 Form D materialization as the program-wide result, enforce one
`match_confidence.rule_version`, quarantine unresolved cross-filing/multi-CIK records, and record
the input and output hashes. Any branch interpretation then needs its own sample-size and identity
review; a high match tier alone is not a validation label.
