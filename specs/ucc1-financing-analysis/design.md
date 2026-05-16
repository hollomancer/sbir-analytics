# UCC-1 Financing Analysis — Design

## Goal

CA-only pilot of a debt-side complement to the Form D equity analysis.
Output: a matched dataset of UCC-1 filings (with UCC-3 amendments and
terminations attached) for the CA-organized subset of the SBIR cohort, and
a research memo answering (a) "what fraction of CA-organized cohort firms
took secured debt and from whom" and (b) "do UCC-3 terminations
corroborate known M&A events for those firms."

See [docs/research/sbir-ucc1-pilot.md](../../docs/research/sbir-ucc1-pilot.md)
for the Phase 0 findings that drove the CA-only narrowing.

## Architecture

Standalone analysis scripts, not Dagster assets. The pilot is intentionally
disposable — if results are weak, the code is read once and discarded; if
strong, it gets promoted into the pipeline in a follow-on spec.

### Data Flow

```
Form D high-confidence SBIR cohort (export step) ─┐
                                                  │
CA SOS Business Search → CA-organized filter      │
                                                  ▼
                                          CA-organized cohort
                                                  │
CA bizfileOnline UCC search                       │
       │                                          │
       ▼                                          ▼
  UCC-1 + UCC-3 records  ───────────►  debtor-side match
       (per-debtor scrape)                        │
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
                                          analysis memo
                                          (docs/research/sbir-ucc1-pilot.md
                                          — already started; pilot run
                                          appends headline metrics)
```

### Data sources

| Source | Access | Notes |
|---|---|---|
| CA SOS bizfileOnline Business Search | Free | Used to filter cohort to CA-organized entities (`bizfileonline.sos.ca.gov/search/business`) |
| CA SOS bizfileOnline UCC Search | Free | Per-debtor lookup; supports Advanced filters (File Type, Status, Date ranges); History modal exposes full UCC-3 lifecycle; PDF endpoint `/api/report/GetImageByNum/<token>` returns filing images |

Per Phase 0: no CAPTCHA observed; CA portal supports the full lifecycle
view via its History modal. The portal's free-text search matches against
both debtor and secured-party fields — role filtering is done client-side
in `UCCMatcher`.

### Key Components

1. **`CohortStateFilter`** — Reads the Form D high-confidence cohort export
   (`data/form_d_high_conf_cohort.jsonl`, produced by a one-shot export
   script). For each firm, queries CA SOS Business Search to determine
   whether the firm is registered as a CA-organized entity (i.e., state of
   organization = CA, not "foreign" / DE-organized doing business in CA).
   Emits `data/ucc1_pilot_ca_org_cohort.jsonl` — the narrowed pilot
   population.

2. **`CAUCCExtractor`** — Per-debtor scraper against CA bizfileOnline UCC
   search. For each firm in the CA-organized cohort:
   - Submits search with Advanced filter `File Type = Financing Statement`
     to exclude tax/judgment liens
   - For each result, expands the detail panel and opens the History modal
   - Captures all related filings (initial + UCC-3 amendments,
     continuations, assignments, terminations) with file numbers and
     dates
   - Output schema:
     `{filing_number, parent_filing_number, filing_date, filing_type
     (initial | amendment | continuation | assignment | termination |
     lapse), debtor_name, debtor_address, secured_party_name,
     secured_party_address, status (Active | Lapsed | per-portal),
     lapse_date, source = "CA"}`
   - Respects rate limits; resumable via checkpoint file

3. **`UCCMatcher`** — Matches CA UCC debtors to the CA-organized cohort
   using name normalization compatible with `sbir_etl` helpers. Filters to
   debtor-side matches only (drops rows where the search hit was on the
   secured-party field). Confidence tiers:
   - **High**: exact normalized name match
   - **Medium**: fuzzy ≥0.92
   - **Low**: fuzzy 0.85–0.92, excluded from headline results

4. **`LifecycleReconstructor`** — Groups records by `parent_filing_number`
   (or `filing_number` for initials) and derives a per-UCC-1 lifecycle:
   - `status` ∈ {active, terminated, lapsed, unknown}
     - `terminated` = any child UCC-3 with `filing_type=termination`
     - `lapsed` = no termination, no continuation, > 5 years since the
       most recent filing (UCC-1s expire after 5 years absent
       continuation under §9-515; CA portal also reports its own
       `Lapsed` status — reconcile with computed value)
     - `active` = otherwise, with at least one filing in the last 5 years
   - `terminated_on` = earliest termination date, if any
   - `assignment_chain` = ordered list of secured-party changes via
     `filing_type=assignment`
   - `last_event_date` = max filing_date across the chain

5. **`SecuredPartyClassifier`** — Rule-based taxonomy:
   - `venture_debt`: SVB / First Citizens, Hercules Capital, Trinity
     Capital, Western Alliance, Comerica (Tech & Life Sciences), Pacific
     Western, Runway Growth, Horizon Technology Finance, ORIX Venture
     Finance, etc. Maintained as a small JSON lookup; grow from observed
     names during pilot.
   - `equipment_finance`: Dell Financial, Cisco Systems Capital, leasing
     cos.
   - `bank_depository`: generic commercial banks (Chase, BoA, Wells,
     regional).
   - `tax_authority`: Employment Development Department (CA EDD),
     Franchise Tax Board, IRS, etc. — expected to dominate CA portal
     results given the § 9-307 venture-debt diversion to DE.
   - `foreign`: secured-party address country ≠ US.
   - `other` / `unknown`: everything else.

6. **`MAEventCorroborator`** — Joins reconstructed lifecycles to
   `data/sbir_ma_events.jsonl` (filter `confidence ∈ {high, medium}` — note
   the field is `confidence`, not `tier`). For each cohort firm with both
   a known M&A event and at least one matched UCC-1, computes:
   - `termination_within_180d`: any UCC-3 termination dated within ±180
     days of `event_date`
   - `days_termination_to_event`: signed delta (negative = termination
     before event, a leading signal)
   - `assignment_within_180d`: same for assignments (debt sold around
     close)

7. **`AnalysisReporter`** — Computes headline metrics:
   - CA-organized subset size vs full Form D cohort size (the headline
     coverage gap)
   - Match rate by confidence tier
   - Fraction of CA-organized cohort with ≥1 Financing Statement UCC-1
     (i.e., excluding tax/judgment liens)
   - Top-N secured parties by SBIR-firm count, broken out by classifier
     category
   - Lifecycle status distribution (active / terminated / lapsed)
   - M&A corroboration rate (% of known M&A firms with termination
     ±180d) and the leading/lagging delta distribution
   - Stratification by SBIR agency and award vintage
   - Foreign secured-party count (count only, not name list, in the memo)

### Output

- `data/form_d_high_conf_cohort.jsonl` — exported Form D high-confidence
  cohort (prerequisite; produced by a one-shot export script)
- `data/ucc1_pilot_ca_org_cohort.jsonl` — CA-organized subset of the
  cohort (post-`CohortStateFilter`)
- `data/ucc1_pilot_matches.jsonl` — matched filings (initials + UCC-3s)
  with confidence tier and `parent_filing_number` linkage
- `data/ucc1_pilot_lifecycles.jsonl` — per-UCC-1 reconstructed lifecycle
  (one row per initial filing with status, terminated_on, assignment
  chain, last_event_date)
- `data/ucc1_pilot_lender_taxonomy.json` — secured-party classifications
- `docs/research/sbir-ucc1-pilot.md` — Phase 0 findings (already written);
  pilot run appends headline metrics and the gate-condition statement

### Cross-worktree data access

`data/sbir_ma_events.jsonl`, `data/form_d_details.jsonl`, and `data/`
generally are gitignored and live only in the main repo at
`/Users/hollomancer/projects/sbir-analytics/data/`. Scripts run from this
worktree read those files via an env var (`SBIR_DATA_DIR`, defaulting to
the main-repo absolute path). New pilot artifacts are written to the
worktree's own `data/` directory.

### Manual Validation

50 randomly sampled matches hand-reviewed against bizfileOnline. Precision
= (true matches / 50). Recorded in the memo. If precision < 70%, the
pilot fails the gate.

## Risks

- **§ 9-307 cohort-shrinkage risk.** The CA-organized subset is expected
  to be <10% of the full Form D cohort. If the subset is smaller than ~50
  firms, statistical conclusions degrade. Mitigation: report subset size
  upfront and gate continuation on whether N is large enough to be
  meaningful.
- **CA SOS state-of-organization data quality.** Some firms appear in CA
  SOS as "foreign" entities (registered to do business in CA but organized
  elsewhere). Filter must exclude those — they're the DE-incorporated
  population we already know is invisible to CA UCC.
- **CA portal rate limiting.** Not observed in Phase 0 at ~10 queries /
  25 minutes, but unknown at the ~few-hundred-query scale needed for the
  CA-organized cohort. Mitigation: throttle conservatively (≤1 req/sec);
  resumable checkpoint.
- **Name-only matching false positives.** Mitigation: hand-review sample;
  the CA-organized narrowing already provides a strong implicit filter.
- **Lender taxonomy incompleteness.** Mitigation: pilot result is a
  *lower bound* on secured-party concentrations; documented as such in
  the memo. Tax-authority and bank classifications are expected to
  dominate (per § 9-307 bias).
- **UCC-3 ↔ UCC-1 linkage gaps.** CA portal exposes lifecycle via its
  History modal which appears to handle parent linkage consistently, but
  edge cases (continuation altering lien number) may produce orphan
  UCC-3s. Mitigation: treat orphan UCC-3s as `unknown_parent` rather than
  dropping; report orphan rate as a quality metric.
- **M&A event-date precision.** `sbir_ma_events.jsonl` event dates derive
  from 8-K/Form D filing dates, which can lead or lag the actual close
  by weeks. ±180d window is intentionally wide; tighter windows reported
  as a sensitivity in the memo.

## What This Does NOT Include

- DE coverage (no free public search; out of pilot scope until
  commercial bulk evaluated separately)
- States other than CA
- IP collateral parsing
- Commercial bulk feed evaluation (LexisNexis, CSC, First Corporate
  Solutions, Cogency)
- Neo4j loading
- Dagster asset wiring
- Time-series / lender concentration analysis
- Foreign-acquisition risk *scoring* (only counts the signal)
- BDC Schedule of Investments harvesting (separate-spec candidate per
  Phase 0 memo)
