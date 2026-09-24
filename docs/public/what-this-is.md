# What this repository is

This repository is a research instrument for making and testing narrow claims
about U.S. SBIR/STTR administrative data and possible commercialization
signals. Each public result must have its own sources, estimand, transformation
rules, validation result, limits, and release record.

It is not a general-purpose analytics platform. It is not an official SBA
database. It is not a verified commercialization-outcomes database. A result
that is approved evidence earns trust only for its own declared claim.

The authoritative public unit is a versioned study packet. A packet identifies
the exact source bytes, code, environment, machine-readable result, rendered
result, and reviews used for one claim. DuckDB, Parquet, and content-addressed
files hold governed analytical records. Mutable service state cannot strengthen
a claim.

Use [STATUS.md](../../STATUS.md) to find the current public evidence boundary.
Use [the evidence-status guide](evidence-status.md) to interpret the labels.
Use [the repository map](repository-map.md) to identify each top-level path.
Read the [validated SBA structural comparison](sba-structural-comparison.md) for
the current reader-facing release candidate.
