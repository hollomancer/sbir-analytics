# UCC-1 Financing Analysis — Design

## Goal

Pilot a debt-side complement to the Form D equity analysis using free DE + CA
UCC indexes. Output: a matched dataset of SBIR-firm UCC-1 filings and a
research memo answering "what fraction took venture debt, from whom."

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
                                          matched filings (JSONL)
                                                      ▼
                                          secured-party classifier
                                          (lender taxonomy)
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
   `DEExtractor`, `CAExtractor`. Each takes a debtor name and returns a list
   of normalized filing records. Common output schema:
   `{filing_number, filing_date, debtor_name, debtor_address,
   secured_party_name, secured_party_address, collateral_description,
   filing_status, source_state}`.

2. **`UCCMatcher`** — Matches state UCC debtors to the SBIR cohort using
   the same fuzzy-name + state approach as the Form D matcher. Reuses
   normalization helpers from `sbir_etl`. Confidence tiers:
   - **High**: exact normalized name match + state match
   - **Medium**: fuzzy ≥0.92 + state match
   - **Low**: fuzzy 0.85–0.92, excluded from headline results

3. **`SecuredPartyClassifier`** — Rule-based taxonomy:
   - `venture_debt`: SVB / First Citizens, Hercules Capital, Trinity Capital,
     Western Alliance, Comerica (Tech & Life Sciences), Pacific Western,
     Runway Growth, Horizon Technology Finance, ORIX Venture Finance, etc.
     Maintained as a small JSON lookup; grow from observed names during pilot.
   - `equipment_finance`: Dell Financial, Cisco Systems Capital, leasing cos.
   - `bank_depository`: generic commercial banks (Chase, BoA, Wells, regional).
   - `foreign`: secured-party address country ≠ US.
   - `other` / `unknown`: everything else.

4. **`AnalysisReporter`** — Computes headline metrics:
   - Match rate by state and confidence tier
   - Fraction of cohort with ≥1 venture-debt UCC-1
   - Top-N venture-debt lenders by SBIR-firm count
   - Stratification by SBIR agency and award vintage
   - Foreign secured-party count (count only, not name list, in the memo)

### Output

- `data/ucc1_pilot_matches.jsonl` — matched filings with confidence tier
- `data/ucc1_pilot_lender_taxonomy.json` — secured-party classifications
- `docs/research/sbir-ucc1-pilot.md` — analysis memo with the headline
  numbers and the gate-condition statement

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

## What This Does NOT Include

- States other than DE + CA
- UCC-3 amendments / terminations / lifecycle
- IP collateral parsing
- Commercial bulk feed evaluation (LexisNexis, CSC, First Corporate Solutions)
- Neo4j loading
- Dagster asset wiring
- Time-series / lender concentration analysis
- Foreign-acquisition risk *scoring* (only counts the signal)
