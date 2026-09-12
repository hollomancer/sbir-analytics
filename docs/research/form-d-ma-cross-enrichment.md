# Form D and M&A-candidate cross-enrichment

**Status:** Exploratory — non-citable

**Test case:** [NASA, Air Force, and DOE commercialization outcomes](nasa-air-force-doe-commercialization-outcomes.md)

## Purpose

Form D and public-record M&A candidates can describe the same corporate event,
but they add different information. Form D can contribute a target CIK, filing
accession, exempt securities sold, address, and related persons. EFTS-derived
evidence can contribute a possible acquirer and an acquisition or subsidiary
context. Combining the sources can improve event review and identity
persistence. Treating a Form-D-derived candidate as independent confirmation
would inflate channel overlap.

Every output relationship has
`candidate_status=unvalidated_public_record_candidate` and
`legal_event_validated=false`. A high confidence label describes the strength
of the source-pattern match. It does not mean that researchers verified the
target identity, closing status, transaction terms, or legal exit.

The cross-enrichment layer leaves both raw source files unchanged. It writes:

- `enriched_ma_events.jsonl`, preserving every M&A-candidate row and adding source-aware
  cross-enrichment metadata;
- `corporate_relationships.jsonl`, one reviewable candidate target-to-acquirer
  or business-combination relationship per source row; and
- `form_d_ma_crosswalk.jsonl`, accession-level Form D links, including
  unlinked business-combination filings.

Acquirers are emitted as `candidate_acquired_by` relationships with
`auto_merge: false`. A source mention does not prove that an acquisition closed.
Even a verified acquisition would not make the target and acquirer
interchangeable identities or prove that later acquirer contracts descend from
the target's SBIR work.

## Provenance rule

The M&A-candidate file is a composite product, not an independent evidence source. Source
counts are based on the underlying Form D, EFTS, press, or discovery evidence.
When an M&A record originated from a Form D business-combination filing, that
same filing is labeled `originating_evidence` and receives no additional
confidence credit. A separately detected EFTS event linked to a Form D filing
is independent corroboration.

This distinction produces two measures:

- **M&A candidate observed:** any retained high- or medium-confidence public-record signal,
  including Form-D-only business combinations; and
- **M&A candidate independent of Form D:** a signal supported by EFTS, press, or
  discovery evidence beyond the Form D filing.

The first is a candidate-detection rate, not an exit rate. The second is used
when counting independent observed pathways. Neither establishes a completed
legal transaction.

## Amount-sold interpretation

Form D `total_amount_sold` measures exempt securities sold in the reported
offering. When Item 10 marks the offering as connected to a business
combination, this study labels the measure **business-combination-associated
exempt securities sold**. It can describe acquisition financing, securities
issued as consideration, recapitalization, or another offering connected to
the combination. It is not purchase price, seller proceeds, equity value, or
enterprise value. See the SEC's [Form D and Item 10
language](https://www.sec.gov/about/forms/formd.pdf).

The relationship metadata makes this limit machine-readable with
`form_d_amount_sold_is_deal_value=false`, `deal_terms_captured=false`, and
`enterprise_value_observed=false`. The pipeline continues to collapse Form D
amendments so cumulative offering amounts are not summed repeatedly.

## Initial materialization

Using the current `form_d_details.jsonl` and `enriched_sbir_ma_events.jsonl`:

| Diagnostic | Count |
| --- | ---: |
| M&A-candidate source rows annotated | 5,252 |
| Distinct target/date/acquirer relationship clusters | 5,239 |
| Relationships containing Form D evidence | 598 |
| Relationships containing EFTS evidence | 4,821 |
| Relationships containing press-wire evidence | 13 |
| Relationships containing both Form D and EFTS evidence | 180 |
| Relationships with multiple source classes | 189 |
| Form-D-only M&A-candidate relationships | 417 |
| Linked Form D business-combination accessions | 694 |
| Unlinked Form D business-combination accessions | 116 |
| Links adding independent Form D corroboration to EFTS evidence | 10 |
| Acquirer identities automatically merged into targets | 0 |

The accession count exceeds the relationship count because a company can have
multiple business-combination filings associated with one composite M&A row.
Originating Form D filings are identified from `form_d_detail` accession or
filing date, not from proximity to a possibly overwritten composite
`event_date`. The 366-day window is used only for additional matches on rows
that do not already have Form D evidence. It is a candidate clustering rule,
not proof that two records describe the same legal event. Only high-tier Form D
matches are ingested.

## Three-agency test case

The headline five-year candidate-detection counts from the prior analysis do
not change: five NASA firms, five Air Force firms, and nine DOE firms have a
high-confidence public-record candidate. The new provenance field shows that
only three, three, and four of those respective candidates have evidence
independent of Form D. The channel-overlap table no longer describes a reused
Form D filing as a second, independent pathway.

| Agency | High-confidence M&A candidates observed | Independent of Form D |
| --- | ---: | ---: |
| NASA | 5 | 3 |
| Air Force | 5 | 3 |
| DOE | 9 | 4 |

With independent pathways used for overlap, the shares with no independently
observed signal across contracts, Form D amount sold, and M&A candidates are 32.4% for
NASA, 31.5% for Air Force, and 59.8% for DOE. This is an overlap-accounting
correction, not a revision to the channel-specific headline rates.

## Transaction-terms audit

A 2026-09-09 review traced the 19 five-year high-confidence candidates to the
retained source summaries. None contains explicit purchase price, cash or stock
consideration, earn-outs, assumed debt, or enterprise value. Ten candidates
name a possible acquirer. Twelve contain Form D amount sold, but those amounts
are offering measures and not deal values.

For those 12 candidates, amount sold totals $412.3 million. The median is $3.44
million and the range is $45,000 to $344.8 million. One $344.8 million filing
accounts for 83.6% of the total; the three largest account for 94.7%. The mean
and agency totals are therefore not representative of a typical firm.

Source spot checks also found candidate-quality problems that aggregate signal
labels do not reveal:

- A [Horizon Technology Finance
  filing](https://www.sec.gov/Archives/edgar/data/1487428/000143774926006636/hrzn20251231_10k.htm)
  describes Slingshot Aerospace as a portfolio investment with a
  preferred-stock warrant, not as an acquired company.
- An [OSI Systems subsidiary
  exhibit](https://www.sec.gov/Archives/edgar/data/1039065/000104746917005596/a2232548zex-21_1.htm)
  lists DXRay but does not supply the acquisition date or terms retained by
  this study.
- A [Global Technologies
  filing](https://www.sec.gov/Archives/edgar/data/1308841/000110801711000405/ex991.htm)
  discusses a potential Technology Applications transaction and does not
  establish that it closed.

These checks are diagnostic, not a complete adjudication of all 19 candidates.
Until each candidate has a source accession, target-specific excerpt, verified
identity, closing status, and terms review, the study must not call the counts
validated exits.

## Implementation

The pure cross-enrichment logic is in
[`sbir_etl/capital_events/cross_enrichment.py`](../../sbir_etl/capital_events/cross_enrichment.py).
The materialization command is
[`scripts/data/build_form_d_ma_cross_enrichment.py`](../../scripts/data/build_form_d_ma_cross_enrichment.py).
The three-agency generator consumes the enriched M&A JSONL through its existing
`--ma` argument and reports both observed and independent signal counts. The
shared M&A capital-event builder also preserves the `cross_enrichment` object in
event metadata so downstream timeline products do not discard provenance.

## Remaining work

This first slice creates the safe relationship layer. Subsequent work should:

1. incorporate verified press/discovery records as additional evidence classes;
2. resolve acquirer identifiers such as CIK and UEI, not just names;
3. create time-bounded predecessor and successor assertions after review;
4. test post-acquisition contract continuation using those reviewed assertions;
5. retain filing accession numbers and target-specific source excerpts;
6. validate closing status and capture cash, stock, earn-out, assumed-debt,
   purchase-price, and enterprise-value fields when disclosed; and
7. hand-label linked and unlinked business-combination samples to estimate
   precision before any evidence-status promotion.
