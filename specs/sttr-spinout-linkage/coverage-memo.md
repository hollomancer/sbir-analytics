# STTR Spinout–Subcontract Linkage — Coverage and Feasibility Memo

**Tier:** `exploratory`, non-citable. This memo estimates *expected* public-data coverage per
evidence dimension per agency **before any run**. The numbers are qualitative feasibility
judgments (High / Medium / Low / Not-applicable), not measurements. They set the prior for where
`INDETERMINATE` will concentrate and which cohorts the adjudication sample must cover first.

## Expected coverage by dimension × agency

Coverage = the probability that the dimension is `MEASURED` (not `NOT_MEASURABLE` / `NOT_APPLICABLE`)
for a typical STTR award at that agency.

| Dimension | NIH | NSF | DoD | DoE / other | Basis |
|-----------|-----|-----|-----|-------------|-------|
| **D1** Award spine | High | High | High | High | SBIR.gov carries SBC, RI, PI, agency, FY, abstract for STTR rows. |
| **D2** Person trail (OpenAlex/PubMed/ORCID) | High | High | **Low** | Medium | Biomedical/academic authorship is densely indexed; DoD PIs are under-indexed and abstracts are terse. |
| **D3** IP trail (USPTO assignment; Bayh-Dole) | Medium | Medium | Medium | Medium | Patent assignment coverage is real but uneven; **license records are sparse everywhere** (encoded as typed absence, never subcontract evidence). |
| **D4** Money trail (USASpending subaward; Form D) | High (grant) | High (grant) | **N/A→Low** (contract) | Mixed | STTR at NIH/NSF is grant-instrument (subaward share observable); much of DoD STTR is contract-instrument, so the RI subaward share is `NOT_APPLICABLE`. Form D officer/director match is instrument-independent but low base rate. |
| **D5** Text trail (phrase lexicon) | Medium | Medium | **Low** | Medium | Tracks abstract richness. Consistent with the repository's finding that DoD descriptions are frequently near-empty. |

## Implications

- **`INDETERMINATE` will concentrate in DoD**, where D2 and D5 are weakest and D4's subaward share
  is often `NOT_APPLICABLE`. This is why the adjudication sample is drawn **NSF and NIH first, DoD
  last** — the DoD cohort tests the classifier where public evidence is thinnest, and its error
  taxonomy will differ.
- **`SUBCONTRACT` is only reachable where D4 has a positive, measured subaward share** and D2/D3/D5
  are measured-negative — i.e., predominantly grant-instrument STTRs. Contract-instrument STTRs with
  no subaward record fall to `INDETERMINATE`, not `SUBCONTRACT`, by construction.
- **License sparsity is systemic, not agency-specific.** D3 will identify spinouts primarily through
  patent assignment (RI assignee + SBC-principal inventor), not through recorded licenses.

## Partner-type incidence readout — table shape

Once gates pass, the partner-type classifier emits this table (counts only; non-citable until then):

| category | agency | fiscal_year | award_count | distinct_RI_count |
|----------|--------|-------------|-------------|-------------------|
| `UNIVERSITY` | … | … | … | … |
| `FFRDC` | … | … | … | … |
| `RESEARCH_HOSPITAL` | … | … | … | … |
| `NONPROFIT_INSTITUTE` | … | … | … | … |
| `NEW_MODEL_ORG` | … | … | … | … |
| `COMMUNITY_COLLEGE` | … | … | … | … |
| `OTHER_NONPROFIT` | … | … | … | … |
| `UNRESOLVED` (`NO_MATCH` / `POSSIBLY_MASKED_BY_SPONSOR`) | … | … | … | … |

Headline: the sum of `RESEARCH_HOSPITAL + NONPROFIT_INSTITUTE + NEW_MODEL_ORG + OTHER_NONPROFIT`
answers "has a non-university, non-FFRDC nonprofit ever served as an STTR partner?" — either the
presence with a breakdown, or a clean zero. Both are reportable.

## Feasibility verdict

RQ1 and the partner-type readout are **feasible as an exploratory classifiability measurement**
with the coverage above; the binding constraint is not compute but the fact that the decisive
signal (PI employer election, allocation-of-rights agreement) is non-public
([see the documented gap](design.md#coverage-and-the-documented-gap)). RQ2 is feasible **as a
design**; running it is out of scope here and gated on validated RQ1 labels.
