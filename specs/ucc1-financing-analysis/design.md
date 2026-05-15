# UCC-1 Financing Analysis — Design

## Goal

Pilot a debt-side complement to the Form D equity analysis using free DE + CA
UCC indexes. Output: a matched dataset of SBIR-firm UCC-1 filings (with
UCC-3 amendments and terminations attached) and a research memo answering
(a) "what fraction took venture debt, from whom" and (b) "do UCC-3
terminations corroborate known M&A events."

## Architecture

Standalone analysis scripts, not Dagster assets. The pilot is intentionally
disposable — if results are weak, the code is read once and discarded; if
strong, it gets promoted into the pipeline in a follow-on spec.

### Data Flow

```
Form D high-confidence SBIR cohort  ─┐
                                     ├─► UCC-1 debtor match
DE Division of Corporations UCC      │   (fuzzy name + state)
CA Secretary of State UCC index     ─┘                │
                                                      ▼
                                          UCC-3 amendments + terminations
                                          fetched per matched UCC-1
                                                      ▼
                                          lifecycle reconstruction
                                          (active / terminated / lapsed)
                                                      ▼
                                          secured-party classifier
                                          (lender taxonomy)
                                                      ▼
                                          M&A event corroboration
                                          (UCC-3 termination ±180d of
                                          sbir_ma_events.jsonl event_date)
                                                      ▼
                                          analysis report (markdown)
```

### Data sources (pilot)

| Source | Access | Notes |
|---|---|---|
| Delaware Division of Corporations UCC search | Free web search, paid bulk | DE captures most VC-backed C-corps regardless of HQ |
| California SOS bizfileOnline UCC | Free web search | CA-incorporated and CA-HQ firms |

DE web search is per-debtor lookup; bulk feed costs apply if we exceed the
free-tier rate. Scope the pilot to the ~3,640 Form D high-confidence firms
and respect rate limits.

### Key Components

1. **`UCCExtractor`** — Per-state extractor. Two implementations:
   `DEExtractor`, `CAExtractor`. Each takes a debtor name and returns the
   initial UCC-1 records *plus* any related UCC-3 amendments and
   terminations (state portals expose these via the original filing
   number / lien lookup). Common output schema:
   `{filing_number, parent_filing_number, filing_date, filing_type
   (initial | amendment | continuation | assignment | termination |
   lapse), debtor_name, debtor_address, secured_party_name,
   secured_party_address, collateral_description, source_state}`.
   `parent_filing_number` is null for initial UCC-1 filings; populated
   for UCC-3 records pointing back to their original.

2. **`UCCMatcher`** — Matches state UCC debtors to the SBIR cohort using
   the same fuzzy-name + state approach as the Form D matcher. Reuses
   normalization helpers from `sbir_etl`. Confidence tiers:
   - **High**: exact normalized name match + state match
   - **Medium**: fuzzy ≥0.92 + state match
   - **Low**: fuzzy 0.85–0.92, excluded from headline results

3. **`LifecycleReconstructor`** — Groups records by `parent_filing_number`
   (or `filing_number` for initials) and derives a per-UCC-1 lifecycle:
   - `status` ∈ {active, terminated, lapsed, unknown}
     - `terminated` = any child UCC-3 with `filing_type=termination`
     - `lapsed` = no termination, no continuation, > 5 years since the
       most recent filing (UCC-1s expire after 5 years absent
       continuation under §9-515)
     - `active` = otherwise, with at least one filing in the last 5 years
   - `terminated_on` = earliest termination date, if any
   - `assignment_chain` = ordered list of secured-party changes via
     `filing_type=assignment`
   - `last_event_date` = max filing_date across the chain

4. **`SecuredPartyClassifier`** — Rule-based taxonomy:
   - `venture_debt`: SVB / First Citizens, Hercules Capital, Trinity Capital,
     Western Alliance, Comerica (Tech & Life Sciences), Pacific Western,
     Runway Growth, Horizon Technology Finance, ORIX Venture Finance, etc.
     Maintained as a small JSON lookup; grow from observed names during pilot.
   - `equipment_finance`: Dell Financial, Cisco Systems Capital, leasing cos.
   - `bank_depository`: generic commercial banks (Chase, BoA, Wells, regional).
   - `foreign`: secured-party address country ≠ US.
   - `other` / `unknown`: everything else.

5. **`MAEventCorroborator`** — Joins reconstructed lifecycles to
   `data/sbir_ma_events.jsonl` (high+medium tier). For each SBIR firm with
   both a known M&A event and at least one matched UCC-1, computes:
   - `termination_within_180d`: any UCC-3 termination dated within ±180
     days of `event_date`
   - `days_termination_to_event`: signed delta (negative = termination
     before event, a leading signal)
   - `assignment_within_180d`: same for assignments (debt sold around close)

6. **`AnalysisReporter`** — Computes headline metrics:
   - Match rate by state and confidence tier
   - Fraction of cohort with ≥1 venture-debt UCC-1
   - Top-N venture-debt lenders by SBIR-firm count
   - Lifecycle status distribution (active / terminated / lapsed)
   - M&A corroboration rate (% of known M&A firms with termination ±180d)
     and the leading/lagging delta distribution
   - Stratification by SBIR agency and award vintage
   - Foreign secured-party count (count only, not name list, in the memo)

### Output

- `data/ucc1_pilot_matches.jsonl` — matched filings (initials + UCC-3s)
  with confidence tier and `parent_filing_number` linkage
- `data/ucc1_pilot_lifecycles.jsonl` — per-UCC-1 reconstructed lifecycle
  (one row per initial filing with status, terminated_on, assignment
  chain, last_event_date)
- `data/ucc1_pilot_lender_taxonomy.json` — secured-party classifications
- `docs/research/sbir-ucc1-pilot.md` — analysis memo with the headline
  numbers, M&A corroboration result, and the gate-condition statement

### Manual Validation

50 randomly sampled matches (25 DE, 25 CA) hand-reviewed against the
source state portal. Precision = (true matches / 50). Recorded in the
memo. If precision < 70%, the pilot fails the gate.

## Risks

- **DE per-debtor rate limiting.** Mitigation: throttle aggressively;
  fall back to CA-only if blocked.
- **Name-only matching false positives.** Mitigation: require state match;
  hand-review sample.
- **Lender taxonomy incompleteness.** Mitigation: pilot result is a *lower
  bound* on venture-debt prevalence; documented as such in the memo.
- **Cohort skew.** Form D high-confidence cohort already over-represents
  VC-backed firms — pilot results don't generalize to the full SBIR
  population. Acknowledged in the memo; widening cohort is a follow-on.
- **UCC-3 ↔ UCC-1 linkage gaps.** State portals sometimes return UCC-3s
  without a parent reference if a continuation altered the lien number.
  Mitigation: treat orphan UCC-3s as `unknown_parent` rather than
  dropping; report orphan rate as a quality metric.
- **M&A event-date precision.** `sbir_ma_events.jsonl` event dates derive
  from 8-K/Form D filing dates, which can lead or lag the actual close
  by weeks. ±180d window is intentionally wide; tighter windows
  reported as a sensitivity in the memo.

## What This Does NOT Include

- States other than DE + CA
- IP collateral parsing
- Commercial bulk feed evaluation (LexisNexis, CSC, First Corporate Solutions)
- Neo4j loading
- Dagster asset wiring
- Time-series / lender concentration analysis
- Foreign-acquisition risk *scoring* (only counts the signal)
