---
Type: Research Report
Owner: research@project
Last-Reviewed: 2026-08-09
Status: draft
---

# Form D control-identity universe audit

> **Exploratory and non-citable.** This artifact audits a reproducible identity
> staging set. It is not a validated non-SBIR control cohort, does not perform
> matching, and reports no treated-versus-control outcome.

## Materialization result

The maintained producer successfully parsed every official SEC DERA quarterly
Form D bulk archive from **2009Q1 through 2024Q4**. It retained 673,656 live D or
D/A filings with a primary issuer and recoverable identity, representing
311,809 unique issuer CIKs.

Exact equality after applying the frozen
`CompanyNameProfile.ORGANIZATION_KEY_V1` normalizer linked 4,423 historical
SBIR-name keys to 4,465 issuer CIKs. All 4,465 CIKs were conservatively excluded,
including ambiguous names that mapped to multiple CIKs. The remaining 307,344
issuer identities are provisional controls only in the narrow sense that they
were **not exact-name-matched to the observed SBIR award history**.

| Audit measure | Value |
| --- | ---: |
| SEC quarters present and validated | 64 / 64 |
| Live D or D/A submissions with primary issuers | 673,679 |
| Filings retained after identity validation | 673,656 |
| Unique Form D issuer CIKs | 311,809 |
| Historical SBIR award rows | 219,500 |
| Unique normalized SBIR company-name keys | 34,287 |
| Exact-matched normalized names | 4,423 |
| Candidate-excluded issuer CIKs | 4,465 |
| Exact-name keys mapping to multiple CIKs | 89 |
| Provisional retained issuer CIKs | 307,344 |

Twenty-three selected filings had issuer names that produced no usable identity
key and were omitted. No quarter, required table, required header, or accession
join was missing. A second cache-only build produced byte-identical hashes for
all three JSONL products.

## What the exclusion does and does not establish

The exclusion is intentionally asymmetric: any exact historical-name collision
removes every associated CIK, even when one name maps to multiple issuers. That
choice favors avoiding known contamination over maximizing the control pool.

It does not establish complete SBIR exclusion. Aliases absent from both source
histories, spelling changes, renames, acquisitions, and other entity lineage can
leave SBIR-exposed firms unmatched. The machine-readable manifest therefore
states:

- `complete_sbir_exclusion=false`;
- `exclusion_recall="unknown"`;
- `identity_only=true`;
- `covariates_ready=false`; and
- `ready_for_matching=false`.

The SEC source reports SIC and its own Form D industry group, not NAICS. Neither
field was relabeled or inferred as NAICS-2. The current Phase 2 matched asset must
not consume these staging products.

## Products and provenance

The full [tracked research manifest](agency-private-capital-form-d-control-universe.manifest.json)
pins the catalog snapshot, all 64 resolved archive URLs and SHA-256 hashes,
required table headers and row counts, the producer commit, the full SBIR award
input, output hashes, and invariant results.

| Product | Rows | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Broad issuer identity universe | 311,809 | 725,072,925 | `28bb167e0281bca00652444600b6635c4c0b60b0103817715df34a98f67e3fe5` |
| Candidate SBIR-CIK exclusion evidence | 4,465 | 2,276,095 | `94cb5bc0eae682675f6e0015cc2c21b48411aba6429b6ef5e4cccfe769af38d3` |
| Provisional retained control identities | 307,344 | 710,168,771 | `aaffebbda1ef3d2b1fe04e211b6973a027181d6840b03c12d4329a1649f31c75` |

The source archive set contains 174,385,952 bytes. Its catalog snapshot hashes
to `e6cbafae178d4c6316f1752436b6d53edf3c268c3fe6f0ab75791e2e12de054c`.
The full-history SBIR award input contains 219,500 rows and hashes to
`73d646fc6883ed93b36d19518b0d9442a9ebae94c5b49ad5a7fcd6d3c2b872dd`.
The large JSONL products and source cache remain gitignored; their hashes and
the complete source ledger are tracked.

Reproduce from a checkout with the SBIR award snapshot available and an
SEC-compliant contact string:

```bash
SBIR_SEC_USER_AGENT="SBIR-Analytics/1.0 contact@example.org" \
  uv run python scripts/data/build_form_d_control_universe.py \
  --awards-csv data/raw/sbir/award_data.csv
```

## Gate decision

This run closes the missing broad-source and deterministic-materialization
prerequisites, but **task 2.2 remains open**. Before the controls become eligible
for matching, a follow-on must union higher-recall authoritative CIK and alias
evidence, validate that exclusion boundary, and establish a defensible
SIC-to-NAICS-2 strategy. Symmetric federal-contract, patent, and M&A event
coverage remains a separate gate.
