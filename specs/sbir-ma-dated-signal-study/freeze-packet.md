# SBIR M&A Dated Signal Study — Freeze Packet (Draft)

> **Status:** Decision-ready draft; **not frozen and not an authorization**.
> It neither supersedes Amendment 1 nor authorizes a source acquisition, a
> date-field scan, identity resolution, candidate creation, aggregation,
> materialization, or a claim. It exists so the owner can approve or reject a
> bounded contract without reconstructing the lost April analysis.

## Proposed narrow question and estimand

**Question.** In a reviewed SBIR firm frame observed through the planned cutoff
of `2026-08-29T23:59:59Z`, what is the count of reviewed candidate firms with
at least one retained, source-observed ownership-change signal from the approved
source slate?

**Estimand.** The unit is one *reviewed candidate SBIR firm identity*, not an
award row, a normalized name string, an SEC filing, a deal, or a transaction.
The sole proposed quantity is the count of such identities with at least one
retained signal. It is an observed-signal count, not an acquisition count,
exit count, exit rate, prevalence, hazard, time-to-exit, or estimate of the
unobserved private-firm population. No denominator or share is authorized in
this draft.

The signal date is the source-record date retained with the signal: a Form D
filing date or an EDGAR filing date. It is never silently substituted for an
announcement, agreement, closing, or acquisition date.

## Proposed source slate and purpose

| Role | Proposed source and bounded use | Required pre-freeze proof |
|---|---|---|
| Firm-frame spine | Official SBIR.gov bulk `award_data.csv`, retrieved privately under Amendment 1. Candidate eligibility would require a nonblank `Company` and a valid `Proposal Award Date` on or before the planned cutoff. The raw row, `UEI`, `Duns`, `Agency Tracking Number`, and `Contract` are retained as identity evidence; none alone is assumed complete. | Evaluate record-level coverage using `Proposal Award Date`; record eligible/excluded row diagnostics; complete source/privacy/license/release review. The currently captured HTTP `Last-Modified` date is insufficient. |
| First ownership-change signal | SEC Form D records whose source record identifies a business-combination offering. Retain the filing identifier, filer/entity identifiers where supplied, filing date, and the exact predicate that produced the signal. | Approve the source-specific access, retention, privacy, and release scope; pin the exact acquisition method, retrieval time, source-version metadata, hash, size, schema, and row count. |
| Second ownership-change signal | SEC EDGAR/EFTS full-text filings: `8-K`, `10-K`, `DEFM14A`, `PREM14A`, `SC TO-T`, and `SC 14D9`. A retained signal requires the query, filing accession, form, filer/CIK, filing date, matched text locator, source URL, and a directional disposition (`target`, `not_target`, `comparator`, or `ambiguous`). | Approve access/rate-limit handling and terms; freeze the exact query, form set, retrieval interval, text-extraction and direction rules, input manifest, and review protocol. A mention alone is not an acquisition. |

No archived April input, existing local award file, alternate bulk snapshot, web-search result,
or local-source substitution may enter this study. A source that cannot demonstrate the planned
cutoff or its specified coverage fails the contract; it is not replaced by a nearby vintage.

## Proposed identity, retention, and exclusion rules

1. Preserve every raw firm-frame alias and source identifier privately. `UEI` and `Duns` are
   exact evidence when present; `Agency Tracking Number` and `Contract` are award-row anchors,
   not universal firm identifiers.
2. Normalized company names may propose a candidate linkage only. They cannot merge firms,
   establish an acquisition target, or resolve a candidate without documented rationale.
3. One candidate firm may retain many award rows and many signals. Separate signals are never
   collapsed into one deal unless a reviewer records the evidence and rationale; the proposed
   estimand needs only an at-least-one retained signal per reviewed candidate.
4. Keep a private candidate-level audit table and exclusion ledger. Required fields are source
   IDs and URLs, source-observed dates, aliases, match rationale, signal predicate/disposition,
   duplicate rationale, exclusions, and uncertainty.
5. Do not put raw rows, contact information, row-level audit tables, text excerpts, or PII in
   Git, Git LFS, release assets, or a public dataset. Any later public artifact needs an explicit
   field-level release decision.

## Privacy, license, and release-scope review record

The owner/reviewer must complete this table for every source before the contract is frozen.
This draft records no legal conclusion and grants no redistribution right.

| Source | Access / terms reviewed | Private retention allowed | Derived private audit allowed | Public aggregate allowed | Public row-level release allowed | Reviewer and decision date |
|---|---|---|---|---|---|---|
| SBIR.gov award CSV | _pending_ | _pending_ | _pending_ | _pending_ | **no, unless separately approved** | _pending_ |
| SEC Form D | _pending_ | _pending_ | _pending_ | _pending_ | **no, unless separately approved** | _pending_ |
| SEC EDGAR/EFTS | _pending_ | _pending_ | _pending_ | _pending_ | **no, unless separately approved** | _pending_ |

The SBIR source includes contact and address fields. A later implementation must use an
allowlisted working schema and must not propagate contact, phone, email, address, or free-text
award fields into the candidate audit or any release unless the review explicitly permits it.

## Freeze checklist

The owner may label this contract **FROZEN** only when all of the following are recorded in a
new, reviewed amendment:

1. The SBIR record-level cutoff check passes or the study remains unmaterialized.
2. Each source has a completed privacy/license/release-scope decision above.
3. Each approved input has a private manifest with URL/method, retrieval time, version metadata,
   SHA-256, byte size, row count, schema, destination, and operator.
4. The Form D predicate and EDGAR/EFTS query, form set, direction rules, and duplicate policy are
   versioned and hashed.
5. The candidate-identity review procedure and audit/exclusion schemas are fixed.
6. The exact estimand and its non-claims above are approved, and the study remains
   `exploratory`, `citable: false`, with `materialization.allowed: false`.

Even after a freeze, a separate authorization is required for each acquisition and for any
analysis. An external numerical claim still requires the evidence-tier promotion and blinded
human adjudication in the study design.
