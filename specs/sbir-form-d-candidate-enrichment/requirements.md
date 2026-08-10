# SBIR ↔ Form D Candidate Enrichment — Requirements

- Research questions: F1, F2, F3
**Target epistemic tier:** `pipelines`
- Status: active
- Out of scope: legal-entity decisions; confidence tiers; people, affiliates, acquisitions, and
  successors; offering amounts; control exclusion; matching; outcomes; rates

## Purpose

The atomic crosswalk preserves exact-name awardee–CIK candidates but does not expose a bounded
near-name review universe or comparable contact evidence. This phase preserves every exact pair,
adds only three frozen fuzzy-name routes, and appends traceable address and phone corroborators. It
produces candidates for a separate blinded validation phase and does not accept identity.

## Requirements

### 1. Pinned prerequisites

1.1. The producer SHALL require external SHA-256 pins for both the Phase 1 crosswalk runtime
manifest and its upstream Form D control-universe runtime manifest. It SHALL validate the pinned
ledger, exact-edge, broad-issuer, and SBIR award products by safe path, hash, bytes, rows, schema,
and closed downstream gates before publication.

1.2. The Phase 1 exact-edge set SHALL be immutable input evidence. Every exact
`(sbir_firm_id, form_d_cik)` pair, stable edge ID, and source provenance SHALL occur in the enriched
product; no new exact pair may appear and no exact pair may disappear.

### 2. Frozen candidate routes

2.1. Fuzzy routes SHALL compare unequal names under
`CompanyNameProfile.ORGANIZATION_KEY_V1`, require at least six alphanumeric characters on each
side, and use RapidFuzz `3.14.3` ratio similarity with inclusive thresholds. The producer SHALL
fail closed if that exact backend version is unavailable; it SHALL NOT fall back to a different
similarity implementation.

2.2. The only fuzzy routes SHALL be:

- `strong_name`: equal two-alphanumeric-character prefix and ratio at least `0.95`;
- `state_supported`: equal prefix, at least one equal state under
  `USJurisdictionProfile.STRICT_V1`, and ratio at least `0.85`; and
- `zip_supported`: at least one equal strict ZIP5 and ratio at least `0.80`, without a prefix
  requirement.

There SHALL be no fallback, top-k limit, phonetic route, person route, best-first shortcut, or
threshold tuning after materialization.

2.3. Missing or malformed prefix, state, or ZIP evidence SHALL fail that route closed. State and
ZIP are retrieval predicates only; neither is an identity decision or confidence label.

### 3. Atomic evidence

3.1. Output SHALL contain exactly one row per `(sbir_firm_id, form_d_cik)`. Evidence from one CIK
SHALL never be pooled onto another CIK. Shared names across firms and shared names across CIKs
SHALL retain every implied atomic pair.

3.2. Each candidate SHALL retain the stable Phase 1 edge ID contract, SBIR component and
quarantine status, qualifying route set, deterministic best evidence for every qualifying route,
overall best name evidence with ratio, token-sort, and token-set scores, SBIR source-record
lineage, and Form D alias/accession lineage. State- and ZIP-supported route witnesses SHALL name
the shared value and its supporting source records and accessions.

3.3. Exact normalized street line 1, city, strict state, strict ZIP5, and normalized ten-digit U.S.
phone intersections MAY enrich an already name-routed pair. Street, city, and phone SHALL never
originate a candidate. Every contact value SHALL identify the supporting SBIR source records and
Form D accessions.

3.4. The product SHALL contain no people, email, website, award value, Form D offering or sale
amount, confidence label, or preferred CIK.

### 4. Decision and publication contract

4.1. Every row SHALL remain `candidate_unreviewed`, set `same_legal_entity` to unknown, and keep
identity acceptance, exclusion, covariate, matching, and rate eligibility false. Exclusion recall
SHALL remain unknown.

4.2. The JSONL SHALL be canonically ordered and content-addressed. A deterministic manifest SHALL
pin inputs, rules, normalizers, producer bytes and commit, outputs, counts, and invariants without
timestamps.

4.3. The complete release SHALL publish by an atomic sibling-directory exchange when replacing an
existing release; first publication SHALL use one atomic rename. The producer SHALL fail closed
when the platform cannot provide the exchange primitive, leave the prior release intact when the
exchange fails, reject output directories containing any pinned input, and require a full
lowercase 40-character `--code-version`.

4.4. Identical inputs and producer bytes SHALL yield byte-identical release directories.

## Acceptance criteria

- Inclusive `.95`, `.85`, and `.80` boundaries produce the declared routes only.
- Short names can survive as preserved exact pairs but cannot create fuzzy pairs.
- Contact-only agreement produces no candidate.
- One shared name across multiple SBIR firms or CIKs preserves every atomic pair.
- Every Phase 1 exact pair and its nested provenance is preserved exactly.
- Every emitted route has a deterministic traceable witness, and backend drift fails closed.
- Input drift, malformed lineage, cross-CIK evidence, and publication failure fail closed.
- A second full-corpus build is byte-identical and every downstream gate remains closed.

## Non-claims

This product does not identify a legal entity, measure precision or recall, define a control,
attach private-capital amounts, or support an outcome or rate. Those claims require the separately
reviewed adjudication and sensitivity phases.
