# SBIR M&A Dated Signal Study — Amendment Log

This is the append-only authorization record for the prospective study design.
It records scope decisions before any retrieval. It does not freeze an
estimand, establish redistribution rights, or authorize analysis,
materialization, a numerical result, or a public release.

## Amendment 1 — private first-source acquisition authorization

- **Operator authorization:** 2026-08-29. The operator authorized a private,
  raw-source acquisition for this new dated study, beginning with the official
  SBIR.gov bulk award CSV. This authorization applies only to the retrieval
  described below.
- **First permitted source:** SBIR.gov bulk `award_data.csv`,
  `https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv`. Retrieve it
  once, without substituting an existing local awards file or an archived
  April input. It is the prospective firm-frame source, not a reproduction
  source for the unrecoverable April analysis.
- **Planned later sources:** SEC Form D records and SEC EDGAR/EFTS records are
  prospective signal sources only. They are not authorized by this amendment;
  each needs its own source-specific authorization before retrieval.
- **Storage and handling:** Keep retrieved raw bytes and all derived private
  handling artifacts under the ignored local root
  `data/studies/sbir_ma_dated_signal_study/2026-08-29/`. Do not add raw bytes,
  row-level extracts, or PII to Git, Git LFS, release assets, or a public
  dataset. Public availability of a source does not itself establish a right or
  an appropriate basis to redistribute a copied extract. Any public artifact
  remains blocked pending a #676-style privacy, license, and release-scope
  review.
- **Required retrieval record:** Before any later use, write a private
  manifest for the SBIR.gov retrieval containing the source URL, retrieval
  timestamp in UTC, HTTP/source version information when supplied, SHA-256,
  byte size, CSV row count, declared header order/schema, destination path,
  and the operator or command responsible. The record must distinguish source
  retrieval time from source-record dates.
- **Cutoff check:** The retrieval record must explicitly evaluate coverage
  through the planned cutoff, 2026-08-29 23:59:59 UTC. It must state which
  source field and interpretation supports that check, or record the check as
  failed/unavailable. A failed or unavailable cutoff check blocks firm-frame
  freezing and all later materialization; it does not permit silently changing
  the cutoff or mixing source vintages.
- **Still prohibited:** No SEC retrieval, identity resolution, candidate-event
  creation, counting, aggregation, numerical interpretation, notebook
  execution, materialization, or claim is authorized. The study remains
  exploratory and non-citable.
- **Visibility at authorization:** No new dated-study source has been acquired
  or analyzed, and no new dated-study numerical result was visible when this
  authorization was recorded.

## Amendment 2 — private cutoff and source-handling review authorization

- **Operator authorization:** 2026-08-30. The operator directed completion of
  the remaining pre-freeze work using the previous M&A implementation and
  decisions where they remain defensible. This amendment is limited to the
  private checks and documentation below.
- **Permitted private check:** Parse the already retrieved SBIR.gov
  `award_data.csv` only to audit the `Proposal Award Date` field's schema,
  date validity, minimum/maximum values, and coverage against
  `2026-08-29T23:59:59Z`. Record aggregate diagnostics only; do not emit
  source rows, contact data, company names, or a firm frame.
- **Permitted documentation:** Review official SBIR.gov and SEC public
  documentation to record operational access, privacy, and release-scope
  constraints for the proposed source slate. This is a technical handling
  review, not legal advice or a finding that redistribution is permitted.
- **Method reuse boundary:** The historical Form D business-combination
  predicate and EDGAR/EFTS filing-form/directional-review pattern may be
  described as proposed method inputs. The historical JSONL, refinement
  artifacts, tier totals, source snapshot, and April results remain excluded
  and may not be reused or reconstructed.
- **Still prohibited:** No SEC/Form D/EDGAR acquisition; firm identity
  resolution; candidate-event creation; signal counting; aggregation;
  notebook execution; materialization; external claim; public artifact; or
  numerical analysis beyond the aggregate cutoff/schema diagnostic above.
- **Decision effect:** A failed or unavailable cutoff check is recorded as a
  hard stop for contract freeze and materialization. It does not permit moving
  the cutoff or substituting another source vintage.

## Amendment 3 — private fresh-snapshot attempt at the fixed cutoff

- **Operator authorization:** 2026-08-30. The operator directed a single fresh
  retrieval attempt while retaining the fixed planned cutoff of
  `2026-08-29T23:59:59Z`.
- **Permitted source and retrieval:** Retrieve the official SBIR.gov bulk
  `award_data.csv` once from the Amendment 1 URL, requesting a fresh response,
  into the ignored local root
  `data/studies/sbir_ma_dated_signal_study/2026-08-30/`. Retain raw bytes and
  response headers only; do not replace or modify the Amendment 1 source.
- **Required evaluation:** Write a separate private provenance manifest and
  perform the same aggregate `Proposal Award Date` cutoff/schema audit
  authorized by Amendment 2. The candidate is usable only if its response
  provenance and record-date audit establish a coherent frame through the fixed
  cutoff.
- **Failure behavior:** A stale, temporally inconsistent, unavailable, or
  otherwise inadequate candidate remains a recorded failed retrieval. It does
  not authorize cutoff movement, source mixing, SEC acquisition, identity work,
  event creation, aggregation, materialization, or a claim.

## Amendment 4 — accept a retrieval-defined private firm-frame selection

- **Operator authorization:** 2026-08-30. The operator directed the study to
  work with the exact official bulk object already retrieved rather than change
  the fixed August 29 date.
- **Accepted input:** The private object with SHA-256
  `efdf7ca5a398703002ebb33345275b0f68e50af3c5db361d48a2456266a23628`,
  retrieved on 2026-08-30 and recorded in the Amendment 1 manifest, is accepted
  as the **retrieval-defined source cut** for this exploratory study.
- **Fixed selection rule:** `2026-08-29T23:59:59Z` is the inclusive selection
  boundary for a source row's `Proposal Award Date`, not a claim that the bulk
  file completely reflects SBIR.gov as of that time. A candidate frame row must
  also have a nonblank `Company`. Amendment 2's aggregate diagnostic may be
  extended only to record aggregate selected/excluded counts and identifier
  availability; raw rows and names remain private.
- **Interpretation boundary:** The selected rows are a reproducible subset of
  one pinned provider object. They are not a complete as-of firm universe, a
  denominator for prevalence or exit rates, or evidence that an absent firm had
  no award or outcome.
- **Still prohibited:** No SEC acquisition; identity resolution; candidate-event
  creation; signal count; aggregation; materialization; external claim; or
  public artifact. The privacy/license/release-scope decisions and each SEC
  source authorization remain separate gates.

## Amendment 5 — private SEC Form D index acquisition

- **Operator authorization:** 2026-08-30. The operator authorized the first
  private-only outcome-source acquisition: SEC EDGAR quarterly `form.idx`
  records for Form D and Form D/A filings.
- **Permitted retrieval:** Retrieve the official SEC quarterly index files from
  2009 Q1 through 2026 Q3 into the ignored study root. Retain raw bytes and a
  private per-file provenance manifest (URL, retrieval time, status/header
  metadata, SHA-256, and byte size). The index is the source acquisition; no
  filing XML is authorized by this amendment.
- **Selection boundary:** Later candidate work may use only index entries with
  `date_filed <= 2026-08-29`. The source period beginning in 2009 is a known
  coverage limit, not evidence of no earlier filing or no outcome.
- **Reuse boundary:** The archived Form D index parser may guide the Form D/D-A
  record identification and source layout. Its fuzzy matching, confidence tiers,
  PI/ZIP scoring, and existing artifacts are not inputs to this study.
- **Handling:** Keep all raw index bytes, candidate links, and later filing
  details private and out of Git, Git LFS, release assets, and public datasets.
  This operational authorization does not determine redistribution rights.
- **Still prohibited:** SBIR-to-Form-D identity resolution; XML retrieval;
  business-combination predicate evaluation; candidate-event creation; counts;
  aggregation; EDGAR/EFTS search; materialization; external claim; and public
  artifact remain unauthorized.

## Amendment 6 — private Form D candidate ledger and XML retrieval

- **Operator authorization:** 2026-08-30. The operator authorized private-only
  SBIR↔Form D candidate linkage and XML retrieval for the already pinned source
  cuts.
- **Candidate rule:** Generate candidates only when an eligible SBIR source-row
  alias and a Form D filer have the same
  `CompanyNameProfile.FORM_D_JOIN_V1` key. Retain the raw aliases, award-row
  identifiers, Form D filer name, CIK, filing date, form type, accession, and
  the exact-key rationale in a private ledger. This is candidate generation,
  not firm identity resolution; zero candidates or an unmatched source row are
  not negative evidence.
- **XML retrieval:** Retrieve only the Form D primary XML for ledger candidates,
  using the accession and CIK from the pinned index source with identified,
  rate-limited SEC access. Preserve raw XML and per-file retrieval provenance
  privately. Failed or missing XML is recorded as unavailable, not excluded or
  inferred.
- **Still prohibited:** Evaluating a business-combination predicate, assigning
  confidence tiers, declaring an M&A signal or event, aggregating candidates,
  EDGAR/EFTS search, materialization, external claim, and public artifact remain
  unauthorized.
