# Named-reader review 6 — Revision 11 public packet

**Reviewer:** `pr788_revision11_named_reader`, project named-reader-reviewer role  
**Date:** 2026-09-22  
**Reviewed commit:** `a18a568c3da2badd5e34d9be37e5ac4a1d831095`  
**Verdict:** `BRIEF`; no remediation

This verdict does not authorize merge, tag, publication, materialization,
citation, or `citable` promotion.

## Declared reader

- Header: SBIR program managers and policy analysts in Treasury, OMB, JCT,
  and state economic-development offices.
- Inventory slot: **Start here** for both SBIR program managers and
  fiscal-policy/state economic-development analysts.
- Question ID: D1 — Award totals.

## Quotable sentence

> Recomputed minus published counts sum to +333, while absolute cell
> differences sum to 869.

The sentence is licensed by `permitted_claims` and the reader-facing page only
as part of a validated, non-citable packet. It is not a released finding.

## Over-read

A reader may hear that SBA omitted 333 unique awards, that 869 awards are
wrong, or that one source is authoritative. They may also hear that
1,264/1,264 and `[1.0, 1.0]` prove source agreement or constitute third-party
replication.

The packet blocks those readings. The result paragraph immediately says the
summaries are not an omitted-award estimate, source-correctness verdict, or
causal explanation. The first screen says `Validated, not citable` and
prohibits quoting the result as released.

The new disclosures are understandable and non-misleading:

- Signed difference is defined as recomputed minus published.
- Absolute difference is explained as removing signs before summing, so
  positive and negative cells cannot cancel.
- The page reports 208 positive and 148 negative cells.
- It separates 57 zero-versus-zero cells from 219 exact cells among the
  575-cell nonzero union.
- It says one parsed row is not necessarily one unique award.
- The `20,836 - 1 = 20,835` row diagnostic and 60 zero-filled groups are fixed
  source-vintage diagnostics, not tolerances.
- Validation is limited to capture and transformation fidelity and cannot
  detect a rule error shared by both implementations.
- Independence is internal blinded-role separation, not unaffiliated
  replication.

## Decision

The reader can inspect, reproduce, or challenge the 632 current-vintage cell
comparisons and identify cells needing reconciliation.

The reader cannot cite a released finding; choose the correct source; infer
omitted or extra unique awards; claim publication-era or official-report
equivalence; compare dollars; infer commercialization, program effects, or
economic return; or transfer validation to other repository outputs.

## Verification

- JSON SHA-256:
  `b87c38ebcc43621d5bb83aaa1102006bc5ab61a8da33e8ed6645eb0b76f87dd2`
- Markdown SHA-256:
  `8ab91c64cf60eed4876bf4b7dd3db6c4023c4d50de5c49f30c533b34c741ae02`
- Canonical-content SHA-256:
  `315587761de27092df09cb1c394e86f2ad1f3cdcc7a199341e849108d4e7537f`
- Every release-checksum entry passed.
- Independent CSV and JSON arithmetic reproduced every disclosed total.
- Isolated and in-memory rebuilds reproduced the JSON and Markdown
  byte-for-byte.
- No `v0.18.0` tag exists, consistent with the open release gates.
- The role did not run the download-based replay because its instructions
  prohibit downloads. It completed the local public-artifact rebuild.
- The reviewer made no edits.

## Required remediation

None.
