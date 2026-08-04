# Solicitation source coverage spike status

**Analysis date:** 2026-08-04

**Evidence status:** Implementation and source-availability status; not a research dataset

## Adapter decisions

| Adapter | Decision | Evidence available in this increment | Blocking evidence |
| --- | --- | --- | --- |
| SBIR.gov solicitations | `no_go` | Official 25-field contract; documentation-derived round-trip fixture; manifested audit command | Official API reports maintenance; a bounded endpoint probe returned HTTP 403; no manifested live sample of at least 50 records |
| NSF funding opportunities | `no_go` | Source contract and intended exact-identifier role documented in the plan | No manifested page/document sample or award-link yield measurement |
| SAM.gov opportunities/documents | `no_go` | Existing metadata, description, and URL retention paths identified | No manifested attachment cohort measuring added text, MIME type, duplicates, or failures |
| Grants.gov opportunity detail | `no_go` | Source contract and context-only evidence boundary documented | No bounded adapter or manifested opportunity/version/attachment sample |

No adapter is approved for scheduled research materialization from this status report. These are
coverage-gate decisions, not judgments about source authority or eventual value.

The SBIR.gov availability probe requested one JSON record from the documented endpoint on the
analysis date. It received `403 application/json` with `{"message":"Forbidden"}`. The response is
an availability result only; it is not a source-shape sample and is not attributed to a particular
cause beyond the separate maintenance notice on the official documentation page.

## SBIR.gov audit contract now available

The new audit command consumes an immutable captured JSON response and writes a machine-checkable
manifest outside version control:

```bash
python scripts/data/audit_sbir_solicitation_source_coverage.py \
  --input /path/to/captured-solicitations.json \
  --output /path/to/sbir-solicitation-coverage.json \
  --source-url 'https://api.www.sbir.gov/public/api/solicitations?rows=50' \
  --analysis-date 2026-08-04
```

The adapter can return `go` only when the capture:

- contains at least 50 records;
- exercises every documented solicitation, topic, and subtopic field;
- retains all 25 documented fields through normalized columns or hierarchy links;
- contains no unmapped source fields or malformed nested values; and
- produces unique solicitation-version and topic/subtopic identifiers.

The report also records duplicate source records and the yield of agency/topic source links. The
documentation-derived fixture intentionally returns `no_go` because one synthetic record cannot
satisfy the live-sample gate.

## Next evidence collection

1. Re-run the SBIR.gov capture after the maintenance notice is removed, retain the raw response and
   exact request URL outside version control, and publish the generated manifest with the research
   release.
2. Build equivalent bounded manifests for official NSF publication pages, existing SAM.gov
   opportunity URLs, and selected Grants.gov opportunity details.
3. Reconcile SAM.gov attachment-added text with the existing GSA archive corpus before authorizing
   attachment downloads.

Candidate program/timing or text-similarity joins remain excluded from exact award-to-solicitation
counts. This status does not support critical-supplier, specific-award-use, or physical-dependency
claims.
