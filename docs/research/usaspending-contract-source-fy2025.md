---
Type: Research Report
Owner: research@project
Last-Reviewed: 2026-08-09
Status: draft
---

# USAspending closed-FY2025 contract source bundle

> **Source-contract proof only.** This audit does not identify SBIR firms,
> materialize contract actions, classify follow-on awards, establish historical
> coverage, or estimate an outcome rate.

## Result

One official, all-agency, closed-FY2025 USAspending
`All_Contracts_Full` archive was content-pinned and accepted by the fail-closed
prime-contract source contract. The archive was updated upstream on 2026-08-06
and was evaluated with an explicit 2026-08-09 source snapshot date.

| Source fact | Verified value |
| --- | ---: |
| Closed fiscal years | FY2025 only |
| ZIP members | 7 flat CSV files |
| Compressed archive bytes | 1,975,007,443 |
| Uncompressed member bytes | 14,274,207,079 |
| Ordered columns per member | 297 |
| Archive SHA-256 | `69e90f438b61de135a79f30ea3d35f1dfd5a0225b6e68d2a4fa523283174fcbb` |

All seven members have the same ordered header. The verified schema contains
the transaction- and award-native identifiers, action and performance dates,
federal action obligation, UEI and DUNS recipient identifiers, award/IDV flags,
and award, IDV, and action type codes required by the contract.

The [tracked bundle manifest](usaspending-contract-source-fy2025.manifest.json)
pins the official archive URL and filename, upstream update date, archive byte
count and SHA-256, and each member's name, uncompressed byte count, CRC-32, and
complete ordered header. The source release ID is derived from those verified
facts rather than assigned manually:
`f727f7041869106b3c60039dbd8ccc2cc0c8e50884cb2820e3a36d6aa84cb408`.
Two real builds produced the same 94,016-byte manifest; its SHA-256 is
`2dc362cb16c398f2d81de346fd4df8531130bedc58231ec72c583961297b10a1`.

## Boundary of the proof

FY2025 was the latest closed federal fiscal year on the snapshot date. The
locally available FY2026 archive remains an open-year partial snapshot and was
not admitted. One fiscal year is enough to test real archive packaging and
schema compatibility; it is not enough for a five-year follow-up window or a
longitudinal procurement study.

The builder reads the ZIP central directory and each CSV header but does not
scan the 14.27 GB of uncompressed action rows. Row-level action-date,
fiscal-year, identifier, and obligation validation belongs to a later streaming
materialization. In particular, this proof does not establish that a firm has
no contract action or that an observed action is a new award or an SBIR
transition.

## Gate decision

This closes only the real-package compatibility prerequisite for the
USAspending source adapter. Every analytical gate remains open:

| Gate | Status |
| --- | --- |
| `events_materialized` | `false` |
| `firm_identity_linkage_ready` | `false` |
| `historical_coverage_ready` | `false` |
| `transition_classification_ready` | `false` |
| `denominator_ready` | `false` |
| `rate_ready` | `false` |
| `ready_for_matching` | `false` |

Reproduce against the separately staged official archive:

```bash
uv run python scripts/data/build_usaspending_contract_source_bundle.py \
  --archive-dir /Volumes/SSDmini/sbir-analytics/data/raw/usaspending/award_archive \
  --fiscal-year 2025 \
  --source-snapshot-date 2026-08-09 \
  --output docs/research/usaspending-contract-source-fy2025.manifest.json
```
