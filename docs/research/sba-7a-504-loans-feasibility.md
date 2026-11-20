# SBA 7(a) and 504 loan files: feasibility for an SBIR/STTR debt readout

**Evidence status:** exploratory. Not citable. Evaluation only; no pipeline or Dagster asset.
**Research question:** B3-adjacent (non-SBIR financing of SBIR/STTR awardees).
**Code:** `scripts/research/sba_loans_feasibility.py`. Generated files:
`data/derived/sba_loans_feasibility/` (git-ignored). Firm-level matches and review samples:
`data/internal/sba_loans_feasibility/` (git-ignored).
**Source:** SBA 7(a) and 504 FOIA files, as of 2026-09-30, downloaded 2026-11-19 from
`data.sba.gov/dataset/7a-504-foia` (six CSVs and a data dictionary; SHA-256 values in
`data/raw/sba_foia/asof_260930/SHA256SUMS`).

Claim tags: **[measured]** computed from the files; **[inferred]** a reading of measured
results; **[unverified]** stated but not checked.

## Rules fixed before task 5

These rules were written into this memo before the match stage ran, and before any descriptive
cut. Task 5 was never run, because the stop rule applied. Any later change is recorded under
"Amendments" with its reason.

**Match rules** (awardee firms and placebo firms are matched the same way):
- **R1, name plus state.** The borrower name matches the firm name under the existing Form D
  matcher (`match_form_d_to_sbir`: exact normalized name, else the first block candidate at
  `token_set_ratio` ≥ 85), and the borrower state equals the firm's state. R1 is reported in
  two parts, R1-exact and R1-fuzzy. Neither is chosen as final.
- **R2, name plus ZIP or street.** R1 holds, and the borrower's 5-digit ZIP equals one of the
  firm's ZIPs, or the borrower's street key (house number plus first street word) equals one
  of the firm's street keys.
- **Awardee set:** SBIR/STTR concerns (UEI, then DUNS, then exact name) with any Phase I or
  Phase II award in FY2015–FY2024. Each concern's names, states, ZIPs, and streets come from
  all of its SBIR.gov records.
- **Placebo set:** non-SBIR small-business recipients of Federal prime contracts with action
  dates in FY2024 (USAspending). The set excludes any SBIR/STTR UEI and any name-and-state
  match to an SBIR/STTR awardee. One placebo firm is drawn per awardee firm from the same
  state × 2-digit NAICS stratum, falling back to the same state. Seed 20261119.
- **Stop rule:** if the awardee firm match rate does not clearly exceed the placebo rate under
  a rule, that rule cannot support the readout.

**Reading rule** (applies to the timing cut in task 5):
- Loans clustered **after** a firm's first non-SBIR contract support the reading that debt
  follows maturity.
- Loans clustered **before** it do not show that debt causes maturity. They only keep that
  reading alive.
- If the awardee match rate does not clearly exceed the placebo rate, stop and say the source
  cannot support the readout.

## 1. Verdict

*Superseded in part: amendment A1 withdrew the stop rule behind this verdict. See "Extension results" at the end.*

**Not usable** for the readout as specified. Under every match rule, SBIR/STTR awardees match
SBA 7(a) and 504 borrowers **less** often than a placebo of non-SBIR small Federal contractors.
Under the high-precision rule R2 (name plus ZIP or street), 3.96% of 14,724 awardee concerns
match, against 9.34% of 14,090 placebo firms **[measured]**. So the source cannot separate an
awardee debt pattern from the base rate, and under the fixed stop rule the descriptive cut
(task 5) was not run **[measured]**. The files still work as a firm-level "publicly observed SBA
loan" flag with high-precision matching (R1-exact or R2) **[inferred]**.

## 2. Field inventory

Six files, 2,207,426 loans: 7(a) 1,976,761 (FY1991–FY2026) and 504 230,665 (FY1991–FY2026)
**[measured]**. Fill rate is the percent of rows with a non-blank value. "—" means the field is
not in that program's files. A zero counts as filled, so `GrossChargeOffAmount` and
`JobsSupported` show 100% even though most loans have no charge-off (see `ChargeOffDate`). Full
table: `data/derived/sba_loans_feasibility/field_inventory.csv`.

| Field | Meaning | 7(a) 91–99 | 7(a) 00–09 | 7(a) 10–19 | 7(a) 20– | 504 91–09 | 504 10– |
|---|---|---|---|---|---|---|---|
| `ApprovalDate` | Date the loan was approved | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `ApprovalFY` | Fiscal year the loan was approved | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `AsOfDate` | Date when the data was recorded | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `BorrCity` | Borrower city | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `BorrName` | Borrower name | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `BorrState` | Borrower state | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `BorrStreet` | Borrower street address | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `BorrZip` | Borrower zip code | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `BusinessAge` | Categorical description of the age of the business | 100.0 | 100.0 | 99.7 | 100.0 | 100.0 | 99.6 |
| `BusinessType` | Borrower Business Type - Individual, Partnership, or Corporation | 98.8 | 99.9 | 100.0 | 100.0 | 99.4 | 100.0 |
| `CDC_City` | CDC city | — | — | — | — | 100.0 | 100.0 |
| `CDC_Name` | Name of CDC that the loan is currently assigned to | — | — | — | — | 100.0 | 100.0 |
| `CDC_State` | CDC state | — | — | — | — | 100.0 | 100.0 |
| `CDC_Street` | CDC street address | — | — | — | — | 100.0 | 100.0 |
| `CDC_Zip` | CDC zip code | — | — | — | — | 100.0 | 100.0 |
| `ChargeOffDate` | Date SBA charged off loan (if applicable) | 10.5 | 20.9 | 6.3 | 2.0 | 9.8 | 0.8 |
| `CollateralInd` | An indicator whether the SBA lender reported that the loan was backed … | 94.5 | 100.0 | 100.0 | 100.0 | 98.7 | 100.0 |
| `CongressionalDistrict` | Congressional district where project occurs | 99.7 | 99.7 | 100.0 | 100.0 | 99.4 | 100.0 |
| `FirstDisbursementDate` | Date of first loan disbursement (if available) | 87.0 | 87.9 | 87.7 | 81.6 | 83.9 | 80.6 |
| `FranchiseCode` | Franchise Code | 6.4 | 5.7 | 8.7 | 12.1 | 8.0 | 9.8 |
| `FranchiseName` | Franchise Name (if applicable) | 6.4 | 5.7 | 8.7 | 12.0 | 8.0 | 9.8 |
| `GrossApproval` | SBA/CDC loan amount | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `GrossChargeOffAmount` | Total SBA/CDC loan balance charged off | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `JobsSupported` | Total Jobs Created + Jobs Retained as reported by lender on SBA Loan A… | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `LoanStatus` | Current status: CANCLD, CHGOFF, PIF, EXEMPT (withheld), COMMIT / NOT FUNDED (undisbursed); 504 also CLOSED | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `LocationID` | SBA's unique lender ID code | 99.3 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `NaicsCode` | North American Industry Classification System (NAICS) code | 45.4 | 97.1 | 100.0 | 100.0 | 80.7 | 99.6 |
| `NaicsDescription` | North American Industry Classification System (NAICS) description | 45.4 | 97.1 | 100.0 | 100.0 | 80.7 | 99.6 |
| `PaidInFullDate` | Date loan was paid in full (if applicable) | 76.0 | 66.7 | 72.9 | 18.5 | 70.7 | 31.3 |
| `ProcessingMethod` | Specific processing method loan was approved under. | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `Program` | Indicator of whether loan was approved under SBA's 7(a) or 504 loan pr… | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `ProjectCounty` | County where project occurs | 99.9 | 99.9 | 100.0 | 100.0 | 100.0 | 100.0 |
| `ProjectState` | State where project occurs | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `SBADistrictOffice` | SBA district office | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `TermInMonths` | Length of loan term | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| `ThirdPartyDollars` | Third party loan amount | — | — | — | — | 91.4 | 99.6 |
| `ThirdPartyLender_City` | Third party lender city | — | — | — | — | 86.0 | 99.9 |
| `ThirdPartyLender_Name` | Name of third party lender | — | — | — | — | 91.5 | 99.9 |
| `ThirdPartyLender_State` | Third party lender state | — | — | — | — | 85.9 | 99.8 |
| `BankCity` | Bank city | 99.3 | 100.0 | 100.0 | 100.0 | — | — |
| `BankFDICNumber` | The Federal Depository Insurance Corporation certificate ID of the len… | 86.8 | 89.8 | 92.8 | 89.4 | — | — |
| `BankNCUANumber` | The National Credit Union Association charter number of the lender | 0.3 | 1.5 | 3.2 | 2.9 | — | — |
| `BankName` | Name of the bank that the loan is currently assigned to | 99.3 | 100.0 | 100.0 | 100.0 | — | — |
| `BankState` | Bank state | 99.3 | 100.0 | 100.0 | 100.0 | — | — |
| `BankStreet` | Bank street address | 99.3 | 100.0 | 100.0 | 100.0 | — | — |
| `BankZip` | Bank zip code | 99.3 | 100.0 | 100.0 | 100.0 | — | — |
| `FixedorVariableInterestInd` | Fixed/variable interest rate indicator | 0.0 | 5.3 | 100.0 | 100.0 | — | — |
| `InitialInterestRate` | Initial interest rate - total interest rate (base rate plus spread) at… | 0.0 | 5.3 | 100.0 | 100.0 | — | — |
| `RevolverStatus` | Indicator of whether a loan is a term loan or revolving line of credit… | 100.0 | 100.0 | 100.0 | 100.0 | — | — |
| `SBAGuaranteedApproval` | Amount of SBA's loan guaranty | 100.0 | 100.0 | 100.0 | 100.0 | — | — |
| `SoldSecMrktInd` | An indicator if the loan was sold on the secondary market. This is a s… | 30.4 | 20.5 | 23.5 | 30.1 | — | — |

**Checks against the prompt:**
- **(a) No UEI or DUNS: confirmed [measured].** No column in any of the six files names a UEI
  or DUNS, and the dictionary defines none. The only borrower identifiers are name, street,
  city, state, and ZIP.
- **(b) Amounts are approvals, not disbursed or outstanding balances: confirmed [measured].**
  The amount fields are `GrossApproval` and `SBAGuaranteedApproval` (7(a)), and `GrossApproval`
  plus `ThirdPartyDollars` (504). There is a `FirstDisbursementDate`, but no disbursed or
  outstanding amount. The only balance-like field is `GrossChargeOffAmount`, the balance
  charged off.
- **(c) Status, charge-off, and paid-in-full fields [measured].** `LoanStatus`,
  `PaidInFullDate`, `ChargeOffDate`, and `GrossChargeOffAmount` have values from the first
  approval year of every file (FY1991 for the oldest files). But `EXEMPT` withholds the status
  of every disbursed loan that is not cancelled, paid in full, or charged off (FOIA Exemption
  4). `EXEMPT` covers 246,422 of 403,644 7(a) loans approved since FY2020 (61%) and 58,081 of
  119,599 504 loans approved since FY2010 (49%). So the status of an active loan cannot be
  seen.
- **Excluded programs [measured]:** no PPP, EIDL, RRF, or microloan processing method appears in
  any file. Those programs are published separately, so no rows had to be dropped.

## 3. Match counts, false positives, and placebo

**Populations [measured].**
- **Awardees:** 14,724 SBIR/STTR concerns with a Phase I or Phase II award in FY2015–FY2024,
  keyed by UEI, then DUNS, then exact name.
- **Placebo pool:** 27,109 non-SBIR small-business recipients of FY2024 Federal prime
  contracts (USAspending, 522,913 award rows, pulled 2026-11-19).
- **Placebo sample:** 14,090 firms drawn, against 14,724 requested. 634 strata could not be
  filled, and 7,639 draws used the same-state fallback, because only 8,070 awardees have a
  NAICS code in the November 2026 SAM.gov extract. **The industry mix is only partly matched.**

**Firm match rates by rule** (firms with at least one matched loan ÷ firms in the set):

| Rule | Awardee firms | Awardee loans | Placebo firms | Placebo loans |
|---|---|---|---|---|
| R1-exact (exact normalized name + state) | 819 / 14,724 = 5.56% | 1,331 | 1,707 / 14,090 = 12.11% | 2,896 |
| R1-fuzzy (fuzzy name ≥ 85 + state) | 894 / 14,724 = 6.07% | 1,117 | 1,764 / 14,090 = 12.52% | 2,159 |
| R1, either part | 1,713 / 14,724 = 11.63% | 2,433 | 3,471 / 14,090 = 24.63% | 5,033 |
| R2 (R1 + ZIP or street) | 583 / 14,724 = 3.96% | 859 | 1,316 / 14,090 = 9.34% | 2,040 |

All counts **[measured]**. By program:
- **Under R2:** 7(a) matches 473 awardee firms (3.21%) against 1,021 placebo firms (7.25%). 504
  matches 133 awardee firms (0.90%) against 364 placebo firms (2.58%).
- **Under R1-exact:** 7(a) matches 702 (4.77%) against 1,401 (9.94%). 504 matches 168 (1.14%)
  against 422 (3.00%).

**False-positive check.**
- **Form D diagnostic [measured].** `compute_form_d_confidence` and its tier rule
  (`corroborated-person-v2`) ran on every match. Its main discriminator, the PI-to-officer
  name match, cannot run: loan records carry no person names. With state equal by
  construction, the tier reduces to ZIP agreement. A ZIP match is "high", anything else
  "medium", and none is "low". The diagnostic adds no information beyond rule R2 here.
- **Hand review [inferred].** I reviewed a random sample of 100 awardee matches per rule (seed
  20261119). One reviewer read both records side by side; this is not blind adjudication.

  | Rule | Likely same firm | Unclear | Likely different |
  |---|---|---|---|
  | R1-exact | 96 | 4 | 0 |
  | R1-fuzzy | 5 | 5 | 90 |
  | R2 | 100 | 0 | 0 |

  A 20-row spot check of placebo R2 matches found 19 likely the same firm **[inferred]**. So
  precision is high on both sides under R2. The placebo gap is not an artifact of placebo
  false positives.
- **Matcher weakness [measured].** The reused matcher uses `token_set_ratio`, which scores 100
  when one name's words are a subset of the other's ("Acme Technologies" against "Acme
  Technologies Pizza"). It also keeps the first candidate at 85 or above, not the best one.
  This drives the R1-fuzzy false positives.

**Placebo verdict.** The awardee rate does not exceed the placebo rate under any rule. Under
the high-precision rules it is less than half: 5.56% against 12.11% (R1-exact) and 3.96%
against 9.34% (R2) **[measured]**. The stop rule applies.

## 4. Provisional descriptive tables

**Not produced.** The stop rule in "Rules fixed before task 5" applied after task 4, so task 5
was not run **[measured]**. The cuts not run are:
- share of awardee firms with any loan by awarding agency and by first-award cohort;
- 7(a) and 504 separately;
- loan timing against the first Phase II and the first non-SBIR contract.

The reading rule was not applied.

## 5. Limits and threats

**What the file cannot see:**
- ordinary bank credit outside the 7(a) and 504 guaranty;
- unsecured credit and credit cards;
- outstanding balances, since only approvals and charged-off balances are published;
- loan purpose, since the files carry no use-of-proceeds field;
- the status of active loans (`EXEMPT`).

**No match means "not publicly observed in these files", never zero debt.**

**Threats to the comparison:**
- **Placebo industry mix [measured].** It is only partly matched: 7,639 of 14,090 draws used
  the state-only fallback. SBA lending leans toward services, construction, and retail, so a
  state-matched placebo likely overstates the base rate for R&D firms **[inferred]**. This
  could narrow the gap. Closing it would take more than a doubling of the awardee rate
  **[inferred]**.
- **Different populations [inferred].** The placebo is active FY2024 contractors. Awardees are
  any concern active FY2015–FY2024, and some are now inactive, which lowers their chance of a
  recent loan.
- **Name matching only [measured].** Without a UEI or DUNS, every match is a name match. R1-fuzzy
  is mostly wrong (90 of 100 reviewed), and even an exact name in the same state can name a
  different firm.
- **Address drift [inferred].** The loan address is the address at approval. Awardee ZIPs and
  streets come from SBIR.gov records across years, so R2 can miss firms that moved.
- **Single reviewer [unverified].** The precision figures come from one reviewer's reading. They
  have not been through blind adjudication.

This result does **not** show that SBIR/STTR awardees use less SBA-guaranteed credit than
comparable firms. It shows only that this file and these rules cannot separate them from a
rough base rate **[inferred]**.

## 6. Recommendation

**Neither**, for an agency-level readout of government-guaranteed debt among awardees. 7(a) and
504 each fall below the placebo on their own under R2 and R1-exact **[measured]**. 504 alone is
also the thinner source: 133 awardee firms under R2.

A narrower use stays open: a firm-level "publicly observed SBA loan" flag, with R2 or
R1-exact matching, inside a firm profile or an audit. That use needs no comparison with a base
rate **[inferred]**.

## 7. What a spec would need to freeze

1. The source vintage: the `asof` date and the SHA-256 of all six files.
2. The awardee population and its window, and the concern key.
3. The match rules, with R1-fuzzy dropped or replaced by a best-candidate matcher. The
   threshold must be calibrated against labeled pairs, and adversarial tests must cover subset
   names.
4. A placebo with a real industry match: NAICS for every awardee, a published fallback rule,
   and an active-firm filter applied to both sides.
5. A blind, two-reviewer adjudication protocol, with a target precision for each rule.
6. The reading rule and stop rule above, unchanged.
7. Coverage language: "not publicly observed" and the `EXEMPT` status.
8. Exclusion of PPP, RRF, EIDL, and microloans, kept even though the current files hold none,
   in case a future vintage adds them.

## Amendments

### A1 — 2026-11-19, stop rule withdrawn (directed by the study owner)

The stop rule in "Rules fixed before task 5" required the awardee match rate to exceed the
placebo rate. **That rule was wrong.** The placebo is a set of real firms, so its match rate
measures real borrowing, not match noise. A lower awardee rate therefore does not show that the
source cannot measure awardees. It is a gap that needs explaining. The question is now:
awardees matched SBA 7(a)/504 borrowers at under half the placebo rate. Is that gap explained by
composition, by differential match recall, or by neither? The rules in "Extension" below
replace the stop rule. The original verdict, sections 1–7, stays as the record of the first run.

**Seen at the time:** all first-run figures above.

### A2 — 2026-11-19, the first-run placebo came from a truncated download

While preparing the extension, I found that the first run's placebo pool came from a USAspending
award-summary file truncated at **500,000 of 522,913 rows** **[measured]**. The request hit the
download row limit. In the rows that arrived, GSA schedule BPA calls make up 373,260 of 500,000,
so Defense contractors are under-represented: only 10 of the 30 >25-Phase-II subject concerns
appear **[measured]**. The first-run placebo rates (for example R2 9.34%) therefore rest on a
GSA-weighted pool **[inferred]**. The extension uses a complete FY2024 pull, made in four
quarterly requests, each under the limit.

**Seen at the time:** first-run figures only. No extension figure had been computed.

### A3 — 2026-11-20, placebo source and size proxy, before task 3

**Change.** The quarterly award-summary pull was also capped. Each quarter's prime file holds
exactly 500,000 rows, so FY2024 small-business contract awards run into the millions
**[measured]**. The pool and size proxy now come from USAspending's recipient aggregate
(`/api/v2/search/spending_by_category/recipient/`: contracts A–D, recipient type small business,
FY2024 action dates), pulled one recipient state at a time with full pagination:
- **Placebo pool:** recipients from that aggregate, with the same exclusions as below.
- **Size proxy:** each recipient's **FY2024 obligated amount** on small-business contracts from
  that endpoint, for both groups. It replaces "sum of `total_obligated_amount` on FY2024-active
  awards". The bands are unchanged.
- **Placebo name variants (task 4):** the single USAspending recipient name. The award-time
  addresses are no longer available for placebo firms, so placebo address variants come from
  SAM.gov only (physical and mailing).

**Also fixed.** The tracked script no longer imports `scripts/archive`, which the repository
hygiene guard forbids in operational files. The first run's match stage, including R1-fuzzy, is
not in the published script. Its figures stay in this memo for the record, but they cannot be
reproduced from this repository.

**Seen at the time:** no extension figure. Only the row counts of the capped files.

### A4 — 2026-11-20, placebo source replaced again, before task 3

**Change.** A3's recipient-aggregate pull ran at about 2.7 minutes per page and was stopped by
the time limit after 4 of 56 states. An on-demand bulk transaction download then failed on
USAspending's side ("An error occurred", after 5,988 seconds) **[measured]**. The pool and size
proxy now come from the pre-built archive `FY2024_All_Contracts_Full_20261106.zip`
(`files.usaspending.gov/award_data_archive`, SHA-256 recorded with the file):
- **Placebo pool:** UEIs with at least one FY2024 contract transaction whose
  `contracting_officers_determination_of_business_size` is SMALL BUSINESS, with the same
  exclusions.
- **Size proxy:** the sum of `federal_action_obligation` on those transactions, for both groups.
  The bands are unchanged.
- **Placebo variants (task 4):** every recipient name (cleaned and raw) and address on those
  transactions, plus SAM.gov. This restores the award-time address variants that A3 had lost.

**Seen at the time:** no extension figure.

## Extension — composition or recall? (rules frozen before task 3)

Written and committed before any extension match was run. Any change after task 3 starts is
recorded as a further amendment.

**Populations.**
- **Awardees:** the 8,070 active awardee concerns (any Phase I or II award in FY2015–FY2024)
  that have a primary NAICS in the SAM.gov Public V2 extract of 2026-11-01.
- **Placebo pool (as amended by A4):** non-SBIR recipients of FY2024 Federal prime contract
  transactions marked SMALL BUSINESS, from the FY2024 contracts archive, with a SAM.gov record. The pool
  excludes any UEI belonging to an SBIR/STTR concern, and any firm whose normalized name and
  state match an SBIR/STTR awardee.

**Matching proxies (proposed and frozen).**
- **NAICS:** SAM.gov primary NAICS for both groups, at 4 digits, falling back to 3 digits. How
  often the fallback is used is reported.
- **Firm-age band:** SAM.gov `ENTITY START DATE` (zero-based position 24), in years before
  2024-10-01: under 5, 5–9, 10–19, 20 or more. *Limits:* self-reported. It may record a
  reorganization or re-registration date rather than the founding date. It is filled for all
  8,070 awardees and every pool firm found in SAM.gov.
- **Size proxy:** the sum of `total_obligated_amount` on the firm's small-business prime
  contracts with an action in FY2024. Bands: under $250k, $250k–under $1M, $1M–under $5M, $5M or
  more. *Limits:* it measures Federal contract volume, not revenue or employees, since SAM.gov
  publishes neither. An awardee's volume includes its SBIR contracts, and grant-only awardees
  (for example most NIH and NSF firms) have no value.
- **Matching:** 1:1 without replacement, in random order (seed 20261120), within exact strata of
  state × NAICS-4 × age band × size band. If no unused pool firm is left, the match falls back to
  NAICS-3 within the same state, age, and size. If none is found, the awardee is unmatched.
- **Primary analysis:** awardees with a size value, matched on all four dimensions. The reading
  rule applies here.
- **Secondary analysis (reported, not used for the reading rule):** all 8,070 awardees, matched
  on state × NAICS × age only.

**Exposure window (both groups).** A loan counts only if its approval date is on or after the
firm's SAM.gov entity start date and on or before 2026-09-30, the file's as-of date. A firm with
a blank start date is excluded from both groups.

**Match rules.** These use the canonical `sbir_etl.identity.normalize_company_name` with profile
`RECIPIENT_V1`, and `normalize_us_jurisdiction`. R1-fuzzy is dropped.
- **R1-exact:** the normalized borrower name equals a firm name, and the states are equal.
- **R2:** R1-exact, plus an equal 5-digit ZIP or an equal street key (house number plus first
  street word).
- **Baseline names and addresses (task 3, the same source for both groups):** the SAM.gov legal
  business name and the SAM.gov physical address.
- **Recall control A (task 4):** adds every public variant, namely the SAM.gov DBA name and the
  SAM.gov mailing address. For awardees it also adds every SBIR.gov name and address from any
  year. For placebo firms it adds every USAspending recipient name (cleaned and raw) and address
  on their FY2024 award rows. The two groups have different numbers of source records, so any
  recall gain is reported for each group.
- **Recall control B (task 5):** the same rules (baseline and with variants) applied to the
  public PPP loan-level file (as of 2024-09-30), restricted to firms with an entity start date on
  or before 2020-12-31. It checks name-and-address recall only. It is not a finding about
  borrowing.

**Statistics.** A firm counts as matched if it has at least one counted loan.
- **Loan-match ratio:** the awardee rate divided by the placebo rate.
- **Interval:** a 95% percentile bootstrap that resamples matched pairs 1,000 times (seed
  20261120). It is reported by rule and by program (7(a), 504, either).
- **Recall ratio:** the same ratio on PPP (control B), and the rise from baseline to variants
  (control A).
- **Recall-adjusted ratio:** the loan-match ratio divided by the PPP recall ratio, with a paired
  bootstrap.

**Reading rule** (applied to the primary analysis, R2, either program):
- If the loan-match ratio's 95% interval includes 1 after matching, composition explains the
  gap. Stop there.
- If the recall-adjusted ratio's 95% interval includes 1, or task 4 brings the two groups' match
  rates within each other's intervals, recall explains the gap. Stop there.
- If the gap survives both, report: "awardees are less often publicly observed in SBA-guaranteed
  lending than matched contractors." Make no claim about why. Only then run the agency cut (task
  7), suppressing any agency cell under 30 firms.

**Fixed reporting rules:**
- No match means "not publicly observed", never zero.
- No balances, leverage, or causal estimates.
- No repayment outcomes, because `EXEMPT` hides the status of most recent 7(a) loans.
- Claim tags and denominators on every figure.

## Extension results

All counts **[measured]** unless tagged otherwise. A pair is one awardee and its matched
placebo firm. "Matched" means the firm has at least one SBA loan in its exposure window under
the rule: **matched means publicly observed in these files. No match means "not publicly
observed", never zero.**

### Reading-rule outcome

**On the primary analysis (R2, 7(a) or 504, baseline names), the awardee-to-placebo ratio is
1.028 [0.856, 1.249]. The interval includes 1, so under the frozen reading rule composition
explains the gap, and the analysis stops there. The agency cut (task 7) was not run.**

The result is **not robust** to the name-and-address set. With every public variant (recall
control A), the R2 ratio is 0.83 [0.695, 0.987] **[measured]**, because the placebo firms'
award-time names and addresses add more matches than the awardees' do.

### Populations and matching

- **Placebo source (A4):** 78,717 UEIs with FY2024 small-business contract transactions. Of
  13,619 active awardee UEIs, 4,143 appear there.
- **Pool:** 62,482 firms after SAM.gov lookup and the exclusions. 194 were excluded because
  their SAM.gov legal name and state match an SBIR/STTR awardee.
- **Awardees:** 8,070 have a SAM.gov NAICS and start date. 3,217 of them have a size value (FY2024
  small-business contract obligations).
- **Primary (state × NAICS-4 × age × size):** 2,618 pairs from 3,217 eligible awardees; 599 were
  unmatched. 1,053 of the 2,618 pairs used the NAICS-3 fallback (40.2%).
- **Secondary (state × NAICS-4 × age):** 7,123 pairs from 8,070 awardees; 947 unmatched. 2,919
  of 7,123 used the NAICS-3 fallback (41.0%).
- **Exposure window:** a loan counts only if approved on or after the firm's SAM.gov entity
  start date and on or before 2026-09-30.
- **Normalizer switch:** 0 of the 1,784,931 distinct SBA borrower names normalize differently
  under `RECIPIENT_V1` than under the first run's normalizer. The switch changes no match.

### Task 3 — matched rates, baseline names and addresses

Primary (size-matched):

| Rule | Program | Awardees matched / pairs | Placebo matched / pairs | Ratio [95% CI] |
|---|---|---|---|---|
| R1-exact | 7(a) or 504 | 307 / 2,618 = 11.73% | 304 / 2,618 = 11.61% | 1.01 [0.875, 1.165] |
| R1-exact | 7(a) | 260 / 2,618 = 9.93% | 267 / 2,618 = 10.2% | 0.974 [0.828, 1.142] |
| R1-exact | 504 | 66 / 2,618 = 2.52% | 55 / 2,618 = 2.1% | 1.2 [0.833, 1.744] |
| R2 | 7(a) or 504 | 184 / 2,618 = 7.03% | 179 / 2,618 = 6.84% | 1.028 [0.856, 1.249] |
| R2 | 7(a) | 138 / 2,618 = 5.27% | 145 / 2,618 = 5.54% | 0.952 [0.753, 1.197] |
| R2 | 504 | 55 / 2,618 = 2.1% | 43 / 2,618 = 1.64% | 1.279 [0.873, 1.919] |

Secondary (not size-matched, all 8,070 awardees; reported, not used for the reading rule):

| Rule | Program | Awardees matched / pairs | Placebo matched / pairs | Ratio [95% CI] |
|---|---|---|---|---|
| R1-exact | 7(a) or 504 | 569 / 7,123 = 7.99% | 738 / 7,123 = 10.36% | 0.771 [0.695, 0.854] |
| R1-exact | 7(a) | 483 / 7,123 = 6.78% | 641 / 7,123 = 9.0% | 0.754 [0.67, 0.839] |
| R1-exact | 504 | 125 / 7,123 = 1.75% | 135 / 7,123 = 1.9% | 0.926 [0.736, 1.172] |
| R2 | 7(a) or 504 | 364 / 7,123 = 5.11% | 452 / 7,123 = 6.35% | 0.805 [0.71, 0.921] |
| R2 | 7(a) | 287 / 7,123 = 4.03% | 368 / 7,123 = 5.17% | 0.78 [0.665, 0.901] |
| R2 | 504 | 99 / 7,123 = 1.39% | 97 / 7,123 = 1.36% | 1.021 [0.774, 1.329] |

Without the size match the gap remains (R2, either program: 0.805 [0.71, 0.921]). The primary
set covers only awardees with FY2024 small-business contract activity (3,217 of 8,070). So the
composition reading applies to contract-active awardees. It is not shown for grant-only
awardees **[inferred]**.

### Task 4 — recall control A: every public name and address variant

Primary, with variants:

| Rule | Program | Awardees matched / pairs | Placebo matched / pairs | Ratio [95% CI] |
|---|---|---|---|---|
| R1-exact | 7(a) or 504 | 317 / 2,618 = 12.11% | 342 / 2,618 = 13.06% | 0.927 [0.807, 1.05] |
| R1-exact | 7(a) | 269 / 2,618 = 10.28% | 302 / 2,618 = 11.54% | 0.891 [0.759, 1.046] |
| R1-exact | 504 | 69 / 2,618 = 2.64% | 63 / 2,618 = 2.41% | 1.095 [0.787, 1.536] |
| R2 | 7(a) or 504 | 210 / 2,618 = 8.02% | 253 / 2,618 = 9.66% | 0.83 [0.695, 0.987] |
| R2 | 7(a) | 163 / 2,618 = 6.23% | 217 / 2,618 = 8.29% | 0.751 [0.616, 0.921] |
| R2 | 504 | 57 / 2,618 = 2.18% | 53 / 2,618 = 2.02% | 1.075 [0.73, 1.568] |

Gain from baseline to variants (R2, either program):
- **Awardees:** 184 → 210 (+26; 7.03% → 8.02%).
- **Placebo:** 179 → 253 (+74; 6.84% → 9.66%).

The variant sets are not symmetric. Awardees add the SAM.gov DBA name, the SAM.gov mailing
address, and the SBIR.gov name and address. Placebo firms add FY2024 transaction names and
addresses. Recent award-time addresses appear to recover more loans **[inferred]**.

*Correction (A5).* An earlier version of this paragraph said awardees add "SBIR.gov names and
addresses from every year". That is wrong. The SBIR.gov export carries one name and one address
per firm on every award: 1 of 34,475 concern keys has more than one company name, and 2 have more
than one ZIP **[measured]**. So the awardee variants had no award-time history. This makes the
asymmetry larger, not smaller.

### Task 5 — recall control B: PPP (name-and-address recall only, not a finding about borrowing)

These are the primary pairs where both firms have an entity start date on or before
2020-12-31 (2,245 pairs).

Baseline:

| Rule | Awardees matched / pairs | Placebo matched / pairs | Ratio [95% CI] |
|---|---|---|---|
| R1-exact | 1,314 / 2,245 = 58.53% | 1,104 / 2,245 = 49.18% | 1.19 [1.128, 1.259] |
| R2 | 916 / 2,245 = 40.8% | 802 / 2,245 = 35.72% | 1.142 [1.063, 1.225] |

With variants:

| Rule | Awardees matched / pairs | Placebo matched / pairs | Ratio [95% CI] |
|---|---|---|---|
| R1-exact | 1,375 / 2,245 = 61.25% | 1,210 / 2,245 = 53.9% | 1.136 [1.082, 1.198] |
| R2 | 1,097 / 2,245 = 48.86% | 1,081 / 2,245 = 48.15% | 1.015 [0.957, 1.074] |

Awardees match PPP at least as often as matched placebo firms, so the name-and-address method
does not under-recall awardees **[inferred]**.

Recall-adjusted ratio (SBA ratio ÷ PPP ratio, same 2,245 pairs, paired bootstrap):
- **Baseline:** R1-exact 0.835 [0.718, 0.974]; R2 0.881 [0.714, 1.084].
- **Variants:** R1-exact 0.801 [0.691, 0.929]; R2 0.802 [0.672, 0.966].

### Task 6 — blind hand review

50 matches were sampled per group per rule from the primary baseline run, shuffled, with the
group hidden. A loan can appear in both rule samples, because R2 is a subset of R1-exact. The reviewer was the analysis agent that
built the matcher, so the review is single-reader and not adjudicated **[unverified]**.

| Group | Rule | Likely same | Unclear | Likely different |
|---|---|---|---|---|
| Awardee | R1-exact | 49 / 50 | 1 | 0 |
| Awardee | R2 | 50 / 50 | 0 | 0 |
| Placebo | R1-exact | 47 / 50 | 3 | 0 |
| Placebo | R2 | 50 / 50 | 0 | 0 |

The unclear rows are short or generic names with a different ZIP. Precision does not differ
between the groups enough to explain a gap **[inferred]**.

### Limits

- **Primary coverage.** The primary analysis covers 2,618 contract-active awardees, not all
  awardees. Grant-only firms have no size value.
- **Proxies.** The size proxy is Federal contract volume, not revenue. The age proxy is the
  self-reported SAM.gov start date. 40% of pairs used the NAICS-3 fallback.
- **Variant sets differ by source**, and the composition reading does not hold under R2 with
  variants (0.83 [0.695, 0.987]).
- **Not seen at all:** ordinary bank credit, unsecured credit, balances, loan purpose, and active
  loan status (`EXEMPT`). No repayment outcome was used.
- **PPP checks recall only.** PPP take-up reflects 2020–2021 conditions and is not evidence about
  7(a) or 504 borrowing.
- **The hand review is unverified.** The analysis agent labeled it; no second reader checked it.
- **Run note.** The first extension run stopped on a text-encoding error while reading the PPP
  files, before it wrote any result. The PPP files are now read as Latin-1. No rule changed.


## Amendment A5 — 2026-11-21, all awardees by agency and instrument (new, post hoc question)

**Why.** The matched-placebo run (A3, A4, "Extension results") needed FY2024 contract activity
for its size proxy, and its placebo came from a contracts archive. So it excluded grant-only
awardees and did not match on awarding agency **[measured]**. This section asks a new question
that the earlier results suggested. It is **post hoc**. It has no placebo group, and it says
nothing about whether awardees borrow more or less than other firms.

**Question.** Among all SBIR/STTR awardees, from every agency and under both grants and
contracts, how many are publicly observed with an SBA 7(a) loan? How does that rate differ by
awarding agency and by award instrument?

### A5 frozen rules (recorded before task 4)

**Population.** Every concern key with a Phase I or Phase II award in the SBIR.gov export of
2026-09-17, after the same de-duplication as before (agency + award ID + phase). No year, NAICS,
size, or contract-activity filter. Concern key: UEI, else DUNS, else exact company name.

**Instrument (task 1).** SBIR.gov has no instrument field. The instrument comes from the award
ID in the `Contract` column, in this order:
1. **Agency ID rules:**
   - NIH activity code: R41–R44 and SB1 are grant, U41–U44 cooperative agreement, N43/N44
     contract.
   - HHS contract prefixes: HHSN, 75N, 75D, 75F, 75A.
   - DOE: DE-AR (ARPA-E) cooperative agreement; DE-FG, DE-SC, DE-EE, DE-NE, DE-FE grant; DE-AC
     contract.
   - NSF: a 6- to 8-digit number is a grant.
   - USDA: an NIFA number with program code 33610 is a grant.
   - DOC: NIST 70NANB..H is a cooperative agreement; NOAA NA..OAR-style is a grant.
   - ED: H133, R305, R324, H327, H180 are grants. EDIES..C.. and ED-..-PO/CO-.. are contracts
     (added after the check below: 11 of 11 such sampled IDs that USAspending found were
     contracts; no match had run).
2. **Position-9 rule:** a federal award ID of the form six-character office code + two-digit
   fiscal year + one instrument character. A letter A, C, D, F, G, M, P, or V is a contract.
   When the office code holds a letter, a digit 1 is a grant, 2 a cooperative agreement, and 3
   or 9 an other transaction.
3. **Agency default (inferred):** for agencies whose ID-classified awards are at least 97% one
   instrument (USDA, DOE, NSF: grant; DoD, DOT, EPA, NASA: contract), an award that no rule
   classifies, including a blank ID, takes that instrument.
4. Anything else is **unclassified**. This affects HHS, DOC, ED, DHS, DOI, and NRC.

**Firm classification (task 2), all three kept.**
- **(a) Agency of first award:** the agency on the firm's earliest award, by award date (else
  the start of its fiscal year), then file order.
- **(b) Every awarding agency.** A firm counts in each agency that awarded it.
- **(c) Instrument mix:**
  - grant-only, contract-only, or both, counting grants and cooperative agreements together as
    grants;
  - other transactions and unclassified awards are left out of the mix;
  - a firm with no classified grant or contract award is "unclassified" and shown as its own
    group.

**Outcome.** A firm is publicly observed with a 7(a) loan when at least one 7(a) row in the SBA
FOIA files (FY1991 to 2026-09-30) matches it under the rule. There is no exposure window: a loan
before the first award counts and is reported in task 6. 504 is reported in a separate column.
- **R1-exact:** the normalized name (`RECIPIENT_V1`) and the state are equal.
- **R2 (primary):** R1-exact plus an equal 5-digit ZIP or street key.
- **Baseline (primary):** the firm's most frequent SBIR.gov name, with the state, ZIP, and street
  of its most recent award.
- **Variants (task 4, second run):** every SBIR.gov name, state, ZIP, and street of the firm.

**Cells.**
- A cell of 30 firms or more shows the count, the denominator, the rate, and a Wilson 95%
  interval.
- A cell of fewer than 30 firms shows the count and the denominator only, marked "too few to
  rate".
- No agency is pooled or dropped.

**Timing (task 6).** The first R2 baseline 7(a) approval of each matched firm is placed in one
of these mutually exclusive groups:
- before the first award;
- after the first award, and the firm has no Phase II;
- between the first award and the first Phase II;
- after the first Phase II.

"After the last award" is reported as a separate, overlapping count.

**Exposure (task 7).**
- Rates by first-award cohort (5-year bands).
- Loans within 5 and 10 years of the first award, only for firms first awarded in FY1991 or
  later with the full window before 2026-09-30.
- The mix rates within each cohort.

**Standardization (task 8).**
- **Method:** indirect standardization. Observed matches ÷ expected matches, where expected
  uses the all-firm rate in each stratum of state × first-award cohort × award-count band (1,
  2–3, 4–9, 10–24, 25+), times the all-firm rate.
- **Intervals:** a firm bootstrap of 1,000 resamples, seed 20261120.
- **Scope:** groups of 30 firms or more only.
- **Ratio:** grant-only ÷ contract-only, with a bootstrap interval, compared at three levels:
  raw, cohort only, and full strata.
- **NAICS side analysis:** adds the SAM.gov NAICS-2 stratum for the firms that have a SAM.gov
  record.
- No proxy that needs contract activity is used.

**Recall (task 9).**
- **Award-count bands:** the R2 7(a) rate by award-count band, baseline against variants.
- **Variants ratio:** the grant-only ÷ contract-only standardized ratio under variants.
- **PPP control:**
  - population: firms with an award in FY2016–FY2020;
  - the PPP R2 baseline rate by mix and by first agency;
  - the standardized grant-only ÷ contract-only PPP ratio, beside the same ratio for 7(a) in
    the same firms.

**Review file (task 10).** Up to 30 R2 baseline 7(a) matches per mix group, shuffled, with the
group hidden. I do not label it.

### A5 task 1 — instrument classification, fill rates, and check (before task 4)

**Source field [measured].**
- SBIR.gov has no instrument field.
- The `Contract` column (the award ID) is filled on 164,736 of 216,850 de-duplicated Phase I/II
  awards (75.97%).
- Most blanks are on old awards. Of the 52,135 blank IDs under the first rule draft, 46,781
  were on awards from FY1999 or earlier.

| Instrument | By ID rule | By agency default **[inferred]** | Unclassified | All |
|---|---|---|---|---|
| Contract | 87,782 | 43,226 | — | 131,008 |
| Grant | 59,678 | 8,961 | — | 68,639 |
| Cooperative agreement | 757 | — | — | 757 |
| Other transaction | 372 | — | — | 372 |
| Unclassified: blank ID | — | — | 14,575 | 14,575 |
| Unclassified: no rule fits | — | — | 1,499 | 1,499 |
| **All** | **148,589 (68.52%)** | **52,187 (24.07%)** | **16,074 (7.41%)** | **216,850** |

Unclassified awards are in HHS (13,632: 12,897 blank, 735 no rule), ED (850), DOC (903), DHS
(506), NRC (168), and DOI (15). The agency defaults carry most NASA awards (15,129 of 19,132),
because older NASA IDs (`NNX..C..`, `NAS..`) do not fit the position-9 rule.

**Check against USAspending [measured].**
- **Sample:** up to 12 IDs per agency × classification source, from FY2009–FY2024 awards with
  a non-blank ID: 464 IDs. USAspending award search starts at FY2008.
- **Lookup:** each ID, stripped of punctuation, was looked up as a contract and as a grant or
  cooperative agreement. For NIH, the core activity-code number was tried if the full ID was not
  found.
- **Result:** of the 254 sampled classified IDs that USAspending found, **254 agree** on grant
  side or contract side, and **0 disagree**.
  - ID-rule contracts: 138 of 138 found agree.
  - ID-rule grants and cooperative agreements: 93 of 93 found agree.
  - Agency-default contracts: 23 of 23 found agree.
- **Subtype:** grant against cooperative agreement differs in 6 found IDs: 4 ARPA-E IDs are grants
  in USAspending, and 2 NSF FY2023–FY2024 IDs are cooperative agreements. The instrument mix
  counts both as grants, so this does not change any firm's mix.
- **Not found:** 188 sampled IDs, including:
  - all 13 other transactions (OTs are not in USAspending);
  - all 24 agency-default grants (DOE and USDA unclassified formats);
  - 12 DoD agency-default contracts;
  - 12 NIH N43/N44 contracts;
  - 12 NIH SB1 grants.

  These classifications stay unverified **[unverified]**.
- **Unclassified IDs that USAspending found:** 11 HHS IDs are assistance and 11 ED IDs are
  contracts. The ED IDs led to one rule added before task 4 (EDIES..C.., ED-..-PO/CO-..). The
  HHS IDs stay unclassified, because their formats are mixed.
- **Files:** sample and results are in `data/derived/sba_loans_feasibility/a5_instrument_check*.csv`
  (git-ignored).

### A5 task 2–3 — population and firm counts before any match

**Population [measured].**
- 34,408 concern keys have a Phase I or II award in any year.
- The earlier analysis used 14,724 keys. Those are exactly the keys with a Phase I/II award in
  FY2015–FY2024, and all 14,724 are in the 34,408. The other 19,684 keys have no Phase I/II
  award in FY2015–FY2024.
- Key splitting is small. 8 of 10,697 name-keyed firms and 3 of 6,543 DUNS-keyed firms share a
  baseline name and state with a UEI-keyed firm.
- 7,654 firms have awards from more than one agency. 323 firms have at least one other
  transaction.

**Firms by agency of first award × instrument mix [measured; mix partly inferred through agency
defaults]:**

| First agency | Both | Contract-only | Grant-only | Unclassified | All |
|---|---|---|---|---|---|
| DHS | 24 | 114 | 19 | 38 | 195 |
| DOC | 52 | 100 | 91 | 108 | 351 |
| DOE | 502 | 0 | 1,447 | 0 | 1,949 |
| DOI | 0 | 3 | 0 | 11 | 14 |
| DOT | 36 | 265 | 0 | 0 | 301 |
| DoD | 1,644 | 10,049 | 2 | 27 | 11,722 |
| ED | 33 | 131 | 75 | 214 | 453 |
| EPA | 96 | 270 | 0 | 0 | 366 |
| HHS | 928 | 403 | 7,301 | 2,017 | 10,649 |
| NASA | 339 | 1,368 | 0 | 0 | 1,707 |
| NRC | 10 | 6 | 5 | 28 | 49 |
| NSF | 915 | 0 | 4,444 | 0 | 5,359 |
| USDA | 97 | 0 | 1,196 | 0 | 1,293 |
| **All** | **4,676** | **12,709** | **14,580** | **2,443** | **34,408** |

**Firms by every awarding agency × mix** (a firm counts once in each agency; 46,910
firm-agency rows):

| Agency | Both | Contract-only | Grant-only | Unclassified | All |
|---|---|---|---|---|---|
| DHS | 251 | 214 | 29 | 38 | 532 |
| DOC | 454 | 198 | 164 | 110 | 926 |
| DOE | 1,798 | 0 | 1,710 | 0 | 3,508 |
| DOI | 1 | 3 | 0 | 11 | 15 |
| DOT | 243 | 372 | 0 | 0 | 615 |
| DoD | 3,626 | 10,687 | 8 | 27 | 14,348 |
| ED | 150 | 158 | 121 | 223 | 652 |
| EPA | 420 | 316 | 0 | 0 | 736 |
| HHS | 1,893 | 530 | 7,887 | 2,031 | 12,341 |
| NASA | 1,585 | 2,089 | 0 | 0 | 3,674 |
| NRC | 32 | 17 | 9 | 28 | 86 |
| NSF | 2,498 | 0 | 5,042 | 0 | 7,540 |
| USDA | 479 | 0 | 1,458 | 0 | 1,937 |

**What this table implies [inferred].** Agency and instrument are nearly the same variable:
- Grant-only firms come almost entirely from HHS, NSF, DOE, and USDA (14,388 of 14,580).
- Contract-only firms come mostly from DoD and NASA (11,417 of 12,709).

So a grant-versus-contract comparison is mostly an HHS/NSF-versus-DoD/NASA comparison. The
standardization in task 8 does not remove that, because no stratum separates agency from
instrument.

### A5 reading rule (recorded before task 4)

- Raw agency differences are descriptive only.
- A grant-versus-contract difference counts only when both of these hold:
  - the grant-only ÷ contract-only ratio's interval excludes 1 after full standardization
    (task 8);
  - it is not explained by recall (task 9). Recall explains it when either of these is true:
    - the variants ratio's interval includes 1;
    - the PPP ratio is in the same direction with an interval that overlaps the 7(a) ratio's
      interval in the same firms.
- If the raw ratio's interval excludes 1 but the cohort-only standardized ratio's interval
  includes 1, exposure time explains the difference.
- A small cell is evidence about the source's reach, not about that agency's firms.
- No claim about why firms borrow.

## A5 results — all awardees by agency and instrument

Counts are **[measured]** unless tagged. "Matched" means publicly observed with at least one
7(a) loan in the SBA FOIA files. **No match means "not publicly observed", never zero.**
Amounts are not used. Loan status and repayment fields are not used.

### Reading-rule outcome

**Grant-only awardees are publicly observed with a 7(a) loan at about half the rate of
contract-only awardees: 239 / 14,580 (1.64%) against 437 / 12,709 (3.44%). The ratio holds after
standardization on state, first-award cohort, and award count (0.511 [0.44, 0.589]),
within cohort (0.464 [0.393, 0.54]), and against the PPP
recall control. So it counts under the frozen rule. Because instrument and awarding agency are
nearly the same variable here, it is equally an HHS/NSF-versus-DoD/NASA difference, and nothing
here says why.**

**Where the grant-only gap sits [measured].** Not every grant agency is low:
- Grant-only firms first awarded by DOE match at 48 / 1,447 (3.32%), and by USDA at 36 / 1,196
  (3.01%).
- DoD contract-only firms match at 363 / 10,049 (3.61%).
- The low grant-only rate comes from HHS (95 / 7,301, 1.30%) and NSF (53 / 4,444, 1.19%).

So "grant versus contract" is better read as "HHS and NSF awardees against the rest"
**[inferred]**.

### Task 4 — all firms, both runs

| Measure | Baseline | Variants |
|---|---|---|
| 7(a), R2 (primary) | 898 / 34,408 · 2.61% · 2.45–2.78 | 898 / 34,408 · 2.61% · 2.45–2.78 |
| 7(a), R1-exact | 1,453 / 34,408 · 4.22% · 4.02–4.44 | 1,453 / 34,408 · 4.22% · 4.02–4.44 |
| 504, R2 | 237 / 34,408 · 0.69% · 0.61–0.78 | 237 / 34,408 · 0.69% · 0.61–0.78 |
| 504, R1-exact | 354 / 34,408 · 1.03% · 0.93–1.14 | 354 / 34,408 · 1.03% · 0.93–1.14 |

**The variant run equals the baseline run in every cell.** The SBIR.gov export carries one name
and one address per firm on all of its awards. Only 1 of 34,475 raw concern keys has more than
one company name, and 2 have more than one ZIP. So "every SBIR.gov variant" adds nothing. The
address is the firm's current or last-recorded profile, not an award-time address. A firm that
moved before or after its loan cannot match under R2 **[inferred]**.

**Earlier population.** The 14,724 firms of the first run match at 440 / 14,724 (2.99%) here.
The other 19,684 firms match at 458 / 19,684 (2.33%). This run uses one SBIR.gov address and no
exposure window. The earlier runs used other address sets and windows, so the figures are not
comparable one to one.

### Task 5 — by agency of first award

| agency_first | 7(a) R2 matched / firms | Rate | Wilson 95% | 7(a) R1-exact | 504 R2 |
|---|---|---|---|---|---|
| DHS | 6 / 195 | 3.08% | 1.42–6.55 | 17 | 4 |
| DOC | 15 / 351 | 4.27% | 2.61–6.93 | 18 | 1 |
| DOE | 78 / 1,949 | 4.00% | 3.22–4.97 | 116 | 23 |
| DOI | 1 / 14 | too few to rate | — | 1 | 0 |
| DOT | 9 / 301 | 2.99% | 1.58–5.58 | 12 | 0 |
| DoD | 445 / 11,722 | 3.80% | 3.47–4.16 | 708 | 117 |
| ED | 6 / 453 | 1.32% | 0.61–2.86 | 13 | 1 |
| EPA | 9 / 366 | 2.46% | 1.30–4.61 | 17 | 3 |
| HHS | 154 / 10,649 | 1.45% | 1.24–1.69 | 260 | 35 |
| NASA | 54 / 1,707 | 3.16% | 2.43–4.10 | 98 | 17 |
| NRC | 1 / 49 | 2.04% | 0.36–10.69 | 1 | 0 |
| NSF | 80 / 5,359 | 1.49% | 1.20–1.85 | 125 | 21 |
| USDA | 40 / 1,293 | 3.09% | 2.28–4.19 | 67 | 15 |

### Task 5 — by instrument mix

| mix | 7(a) R2 matched / firms | Rate | Wilson 95% | 7(a) R1-exact | 504 R2 |
|---|---|---|---|---|---|
| both | 195 / 4,676 | 4.17% | 3.63–4.78 | 308 | 74 |
| contract-only | 437 / 12,709 | 3.44% | 3.14–3.77 | 705 | 103 |
| grant-only | 239 / 14,580 | 1.64% | 1.45–1.86 | 389 | 52 |
| unclassified | 27 / 2,443 | 1.11% | 0.76–1.60 | 51 | 8 |

### Task 5 — by every awarding agency

A firm counts once in each agency that awarded it, so the rows overlap.

| agencies | Matched / firms | Rate | Wilson 95% |
|---|---|---|---|
| DHS | 26 / 532 | 4.89% | 3.36–7.06 |
| DOC | 46 / 926 | 4.97% | 3.74–6.56 |
| DOE | 152 / 3,508 | 4.33% | 3.71–5.06 |
| DOI | 1 / 15 | too few to rate | — |
| DOT | 26 / 615 | 4.23% | 2.90–6.12 |
| DoD | 553 / 14,348 | 3.85% | 3.55–4.18 |
| ED | 16 / 652 | 2.45% | 1.52–3.95 |
| EPA | 22 / 736 | 2.99% | 1.98–4.48 |
| HHS | 212 / 12,341 | 1.72% | 1.50–1.96 |
| NASA | 158 / 3,674 | 4.30% | 3.69–5.01 |
| NRC | 5 / 86 | 5.81% | 2.51–12.90 |
| NSF | 156 / 7,540 | 2.07% | 1.77–2.42 |
| USDA | 65 / 1,937 | 3.36% | 2.64–4.25 |

### Task 5 — agency of first award × instrument mix (every cell)

| agency_first | mix | 7(a) R2 matched / firms | Rate | Wilson 95% | 7(a) R1-exact | 504 R2 |
|---|---|---|---|---|---|---|
| DHS | both | 0 / 24 | too few to rate | — | 2 | 1 |
| DHS | contract-only | 5 / 114 | 4.39% | 1.89–9.86 | 12 | 2 |
| DHS | grant-only | 1 / 19 | too few to rate | — | 1 | 0 |
| DHS | unclassified | 0 / 38 | 0.00% | 0.00–9.18 | 2 | 1 |
| DOC | both | 4 / 52 | 7.69% | 3.03–18.17 | 4 | 0 |
| DOC | contract-only | 5 / 100 | 5.00% | 2.15–11.18 | 8 | 1 |
| DOC | grant-only | 4 / 91 | 4.40% | 1.72–10.76 | 4 | 0 |
| DOC | unclassified | 2 / 108 | 1.85% | 0.51–6.50 | 2 | 0 |
| DOE | both | 30 / 502 | 5.98% | 4.22–8.40 | 41 | 14 |
| DOE | grant-only | 48 / 1,447 | 3.32% | 2.51–4.37 | 75 | 9 |
| DOI | contract-only | 1 / 3 | too few to rate | — | 1 | 0 |
| DOI | unclassified | 0 / 11 | too few to rate | — | 0 | 0 |
| DOT | both | 1 / 36 | 2.78% | 0.49–14.17 | 2 | 0 |
| DOT | contract-only | 8 / 265 | 3.02% | 1.54–5.84 | 10 | 0 |
| DoD | both | 80 / 1,644 | 4.87% | 3.93–6.02 | 132 | 34 |
| DoD | contract-only | 363 / 10,049 | 3.61% | 3.26–4.00 | 574 | 83 |
| DoD | grant-only | 1 / 2 | too few to rate | — | 1 | 0 |
| DoD | unclassified | 1 / 27 | too few to rate | — | 1 | 0 |
| ED | both | 1 / 33 | 3.03% | 0.54–15.32 | 3 | 0 |
| ED | contract-only | 2 / 131 | 1.53% | 0.42–5.40 | 5 | 1 |
| ED | grant-only | 1 / 75 | 1.33% | 0.24–7.17 | 2 | 0 |
| ED | unclassified | 2 / 214 | 0.93% | 0.26–3.34 | 3 | 0 |
| EPA | both | 4 / 96 | 4.17% | 1.63–10.23 | 6 | 2 |
| EPA | contract-only | 5 / 270 | 1.85% | 0.79–4.26 | 11 | 1 |
| HHS | both | 31 / 928 | 3.34% | 2.36–4.70 | 45 | 7 |
| HHS | contract-only | 7 / 403 | 1.74% | 0.84–3.54 | 13 | 1 |
| HHS | grant-only | 95 / 7,301 | 1.30% | 1.07–1.59 | 160 | 20 |
| HHS | unclassified | 21 / 2,017 | 1.04% | 0.68–1.59 | 42 | 7 |
| NASA | both | 13 / 339 | 3.83% | 2.25–6.45 | 27 | 3 |
| NASA | contract-only | 41 / 1,368 | 3.00% | 2.22–4.04 | 71 | 14 |
| NRC | both | 0 / 10 | too few to rate | — | 0 | 0 |
| NRC | contract-only | 0 / 6 | too few to rate | — | 0 | 0 |
| NRC | grant-only | 0 / 5 | too few to rate | — | 0 | 0 |
| NRC | unclassified | 1 / 28 | too few to rate | — | 1 | 0 |
| NSF | both | 27 / 915 | 2.95% | 2.04–4.26 | 37 | 8 |
| NSF | grant-only | 53 / 4,444 | 1.19% | 0.91–1.56 | 88 | 13 |
| USDA | both | 4 / 97 | 4.12% | 1.62–10.13 | 9 | 5 |
| USDA | grant-only | 36 / 1,196 | 3.01% | 2.18–4.14 | 58 | 10 |

A cell that does not appear has no firms. A small cell shows how far the SBA files reach into
that agency's awardees. It is not evidence about that agency's firms.

### Task 6 — timing of the first matched 7(a) approval (R2, baseline)

| When the first 7(a) approval falls | Firms |
|---|---|
| Before the first SBIR/STTR award | 301 / 898 = 33.5% |
| After the first award, firm has no Phase II | 148 / 898 = 16.5% |
| Between the first award and the first Phase II | 84 / 898 = 9.4% |
| After the first Phase II | 365 / 898 = 40.6% |
| *Overlapping:* after the last award | 301 / 898 = 33.5% |

- 89 of the 898 matched firms had their first award before FY1991. The loan files start in FY1991,
  so for these firms a loan before the first award cannot be observed.
- The "before first award" and "after last award" groups are separate, with no firm in both.
  Their equal size (301 each) is a coincidence.
- Of the 301 "after last award" firms, 116 have one award date only.

### Task 7 — exposure

**By first-award cohort (any loan to 2026-09-30):**

| cohort | Matched / firms | Rate | Wilson 95% |
|---|---|---|---|
| <=FY1989 | 76 / 4,019 | 1.89% | 1.51–2.36 |
| FY1990-94 | 78 / 3,196 | 2.44% | 1.96–3.04 |
| FY1995-99 | 101 / 3,500 | 2.89% | 2.38–3.49 |
| FY2000-04 | 154 / 4,224 | 3.65% | 3.12–4.25 |
| FY2005-09 | 125 / 3,710 | 3.37% | 2.84–4.00 |
| FY2010-14 | 103 / 3,762 | 2.74% | 2.26–3.31 |
| FY2015-19 | 118 / 4,857 | 2.43% | 2.03–2.90 |
| FY2020+ | 143 / 7,140 | 2.00% | 1.70–2.35 |

**Within 5 years of the first award.** Firms first awarded in FY1991 or later with 5 full years
before 2026-09-30: 259 / 25,478 · 1.02% · 0.90–1.15.

| mix | Matched / firms | Rate | Wilson 95% |
|---|---|---|---|
| both | 49 / 3,555 | 1.38% | 1.04–1.82 |
| contract-only | 121 / 8,985 | 1.35% | 1.13–1.61 |
| grant-only | 80 / 11,510 | 0.70% | 0.56–0.86 |
| unclassified | 9 / 1,428 | 0.63% | 0.33–1.19 |

| agency_first | Matched / firms | Rate | Wilson 95% |
|---|---|---|---|
| DHS | 4 / 175 | 2.29% | 0.89–5.73 |
| DOC | 4 / 288 | 1.39% | 0.54–3.52 |
| DOE | 17 / 1,388 | 1.22% | 0.77–1.95 |
| DOT | 1 / 187 | 0.53% | 0.09–2.97 |
| DoD | 121 / 8,333 | 1.45% | 1.22–1.73 |
| ED | 2 / 329 | 0.61% | 0.17–2.19 |
| EPA | 1 / 244 | 0.41% | 0.07–2.28 |
| HHS | 45 / 8,134 | 0.55% | 0.41–0.74 |
| NASA | 16 / 1,207 | 1.33% | 0.82–2.14 |
| NRC | 0 / 13 | too few to rate | — |
| NSF | 36 / 4,094 | 0.88% | 0.64–1.21 |
| USDA | 12 / 1,086 | 1.10% | 0.63–1.92 |

**Within 10 years of the first award.** Same rule, 10 years: 305 / 19,341 · 1.58% · 1.41–1.76.

| mix | Matched / firms | Rate | Wilson 95% |
|---|---|---|---|
| both | 68 / 2,940 | 2.31% | 1.83–2.92 |
| contract-only | 132 / 6,714 | 1.97% | 1.66–2.33 |
| grant-only | 91 / 8,290 | 1.10% | 0.89–1.35 |
| unclassified | 14 / 1,397 | 1.00% | 0.60–1.68 |

| agency_first | Matched / firms | Rate | Wilson 95% |
|---|---|---|---|
| DHS | 3 / 145 | 2.07% | 0.71–5.91 |
| DOC | 5 / 241 | 2.07% | 0.89–4.76 |
| DOE | 23 / 1,021 | 2.25% | 1.51–3.36 |
| DOT | 1 / 162 | 0.62% | 0.11–3.41 |
| DoD | 138 / 6,218 | 2.22% | 1.88–2.62 |
| ED | 2 / 295 | 0.68% | 0.19–2.44 |
| EPA | 1 / 206 | 0.49% | 0.09–2.70 |
| HHS | 65 / 6,389 | 1.02% | 0.80–1.29 |
| NASA | 16 / 995 | 1.61% | 0.99–2.60 |
| NRC | 0 / 13 | too few to rate | — |
| NSF | 35 / 2,743 | 1.28% | 0.92–1.77 |
| USDA | 16 / 913 | 1.75% | 1.08–2.83 |

**By cohort, within 5 and 10 years:**

| cohort | Matched / firms | Rate | Wilson 95% |
|---|---|---|---|
| FY1990-94 | 28 / 2,601 | 1.08% | 0.75–1.55 |
| FY1995-99 | 29 / 3,500 | 0.83% | 0.58–1.19 |
| FY2000-04 | 41 / 4,224 | 0.97% | 0.72–1.31 |
| FY2005-09 | 51 / 3,710 | 1.37% | 1.05–1.80 |
| FY2010-14 | 36 / 3,762 | 0.96% | 0.69–1.32 |
| FY2015-19 | 42 / 4,857 | 0.86% | 0.64–1.17 |
| FY2020+ | 32 / 2,824 | 1.13% | 0.80–1.60 |

| cohort | Matched / firms | Rate | Wilson 95% |
|---|---|---|---|
| FY1990-94 | 44 / 2,601 | 1.69% | 1.26–2.26 |
| FY1995-99 | 45 / 3,500 | 1.29% | 0.96–1.72 |
| FY2000-04 | 75 / 4,224 | 1.78% | 1.42–2.22 |
| FY2005-09 | 67 / 3,710 | 1.81% | 1.42–2.29 |
| FY2010-14 | 55 / 3,762 | 1.46% | 1.12–1.90 |
| FY2015-19 | 19 / 1,544 | 1.23% | 0.79–1.91 |

**Instrument mix within each first-award cohort (any loan):**

| cohort | mix | Matched / firms | Rate | Wilson 95% |
|---|---|---|---|---|
| <=FY1989 | both | 39 / 834 | 4.68% | 3.44–6.33 |
| <=FY1989 | contract-only | 27 / 1,684 | 1.60% | 1.10–2.32 |
| <=FY1989 | grant-only | 5 / 634 | 0.79% | 0.34–1.83 |
| <=FY1989 | unclassified | 5 / 867 | 0.58% | 0.25–1.34 |
| FY1990-94 | both | 24 / 534 | 4.49% | 3.04–6.60 |
| FY1990-94 | contract-only | 36 / 1,384 | 2.60% | 1.88–3.58 |
| FY1990-94 | grant-only | 12 / 752 | 1.60% | 0.92–2.77 |
| FY1990-94 | unclassified | 6 / 526 | 1.14% | 0.52–2.47 |
| FY1995-99 | both | 27 / 470 | 5.74% | 3.98–8.23 |
| FY1995-99 | contract-only | 42 / 1,364 | 3.08% | 2.29–4.14 |
| FY1995-99 | grant-only | 27 / 1,012 | 2.67% | 1.84–3.85 |
| FY1995-99 | unclassified | 5 / 654 | 0.76% | 0.33–1.78 |
| FY2000-04 | both | 34 / 732 | 4.64% | 3.34–6.42 |
| FY2000-04 | contract-only | 63 / 1,374 | 4.59% | 3.60–5.82 |
| FY2000-04 | grant-only | 49 / 1,826 | 2.68% | 2.04–3.53 |
| FY2000-04 | unclassified | 8 / 292 | 2.74% | 1.39–5.31 |
| FY2005-09 | both | 25 / 562 | 4.45% | 3.03–6.48 |
| FY2005-09 | contract-only | 66 / 1,385 | 4.77% | 3.76–6.02 |
| FY2005-09 | grant-only | 34 / 1,739 | 1.96% | 1.40–2.72 |
| FY2005-09 | unclassified | 0 / 24 | too few to rate | — |
| FY2010-14 | both | 19 / 560 | 3.39% | 2.18–5.24 |
| FY2010-14 | contract-only | 44 / 1,093 | 4.03% | 3.01–5.36 |
| FY2010-14 | grant-only | 39 / 2,087 | 1.87% | 1.37–2.54 |
| FY2010-14 | unclassified | 1 / 22 | too few to rate | — |
| FY2015-19 | both | 19 / 569 | 3.34% | 2.15–5.16 |
| FY2015-19 | contract-only | 59 / 1,394 | 4.23% | 3.30–5.42 |
| FY2015-19 | grant-only | 40 / 2,875 | 1.39% | 1.02–1.89 |
| FY2015-19 | unclassified | 0 / 19 | too few to rate | — |
| FY2020+ | both | 8 / 415 | 1.93% | 0.98–3.76 |
| FY2020+ | contract-only | 100 / 3,031 | 3.30% | 2.72–4.00 |
| FY2020+ | grant-only | 33 / 3,655 | 0.90% | 0.64–1.27 |
| FY2020+ | unclassified | 2 / 39 | 5.13% | 1.42–16.89 |

Grant-only firms have the lowest rate of the three classified groups in every cohort, including
the five-year and ten-year windows **[measured]**.

### Task 8 — standardized rates

Indirect standardization. Strata: state × first-award cohort × award-count band. Groups of 30
firms or more. Firm bootstrap, 1,000 resamples, seed 20261120.

**By agency of first award:**

| First agency | Firms | Observed | Expected | Standardized rate | 95% bootstrap |
|---|---|---|---|---|---|
| DHS | 195 | 6 | 5.9 | 2.67% | 0.85–4.76 |
| DOC | 351 | 15 | 11.3 | 3.47% | 1.94–5.28 |
| DOE | 1,949 | 78 | 54.9 | 3.70% | 2.93–4.45 |
| DOI | 14 | — | — | too few to rate | — |
| DOT | 301 | 9 | 6.9 | 3.39% | 1.55–5.84 |
| DoD | 11,722 | 445 | 334.5 | 3.47% | 3.17–3.78 |
| ED | 453 | 6 | 8.8 | 1.79% | 0.58–3.40 |
| EPA | 366 | 9 | 8.6 | 2.72% | 1.11–4.51 |
| HHS | 10,649 | 154 | 259.3 | 1.55% | 1.30–1.78 |
| NASA | 1,707 | 54 | 47.5 | 2.97% | 2.19–3.78 |
| NRC | 49 | 1 | 0.7 | 3.77% | 0.00–12.12 |
| NSF | 5,359 | 80 | 122.3 | 1.71% | 1.35–2.07 |
| USDA | 1,293 | 40 | 37.1 | 2.82% | 2.02–3.62 |

**By instrument mix:**

| Mix | Firms | Observed | Expected | Standardized rate | 95% bootstrap |
|---|---|---|---|---|---|
| both | 4,676 | 195 | 181.0 | 2.81% | 2.46–3.18 |
| contract-only | 12,709 | 437 | 327.6 | 3.48% | 3.19–3.78 |
| grant-only | 14,580 | 239 | 350.4 | 1.78% | 1.57–2.00 |
| unclassified | 2,443 | 27 | 39.1 | 1.80% | 1.22–2.51 |

**Grant-only ÷ contract-only ratio:**

| Version | Ratio [95% bootstrap] |
|---|---|
| Raw | 0.477 [0.411, 0.563] |
| Cohort only | 0.464 [0.393, 0.54] |
| State × cohort × award count | 0.511 [0.44, 0.589] |
| Same, plus SAM.gov NAICS-2 (side analysis, 10,073 firms with a SAM.gov NAICS) | 0.624 [0.502, 0.77] |

Both ÷ contract-only: 0.808 [0.692, 0.948] after full
standardization, and 1.16 [0.973, 1.359] by cohort only.

### Task 9 — recall checks

**Award count, baseline against variants:**

| Award-count band | Baseline matched / firms | Rate | Variants matched / firms | Rate |
|---|---|---|---|---|
| 1 | 239 / 13,114 | 1.82% | 239 / 13,114 | 1.82% |
| 2-3 | 272 / 10,708 | 2.54% | 272 / 10,708 | 2.54% |
| 4-9 | 184 / 6,684 | 2.75% | 184 / 6,684 | 2.75% |
| 10-24 | 116 / 2,551 | 4.55% | 116 / 2,551 | 4.55% |
| 25+ | 87 / 1,351 | 6.44% | 87 / 1,351 | 6.44% |

The rate rises with award count (1.82% for one award, 6.44% for 25 or more). It is not from
address variants, because there are none. It can reflect firm age, size, or survival, or
whether the one recorded address is current. This analysis does not separate these
**[inferred]**.

**Variants ratio.** The standardized grant-only ÷ contract-only ratio under variants is
0.511 [0.44, 0.595]. It equals the baseline, so this check carries
no information here.

**PPP, recall control only** (firms with an award in FY2016-FY2020; R2 baseline). This is not a finding about
borrowing:
- Overall: 3,489 / 9,133 · 38.20% · 37.21–39.20.
- Standardized grant-only ÷ contract-only PPP ratio, same firms: 0.923 [0.871, 0.979].
- Same ratio for 7(a) in the same firms: 0.435 [0.329, 0.574].

| mix | Matched / firms | Rate | Wilson 95% |
|---|---|---|---|
| both | 983 / 2,010 | 48.91% | 46.72–51.09 |
| contract-only | 1,101 / 2,881 | 38.22% | 36.46–40.00 |
| grant-only | 1,397 / 4,219 | 33.11% | 31.71–34.55 |
| unclassified | 8 / 23 | too few to rate | — |

| agency_first | Matched / firms | Rate | Wilson 95% |
|---|---|---|---|
| DHS | 27 / 62 | 43.55% | 31.94–55.91 |
| DOC | 38 / 90 | 42.22% | 32.54–52.54 |
| DOE | 231 / 522 | 44.25% | 40.05–48.54 |
| DOT | 16 / 37 | 43.24% | 28.67–59.09 |
| DoD | 1,224 / 3,015 | 40.60% | 38.86–42.36 |
| ED | 28 / 61 | 45.90% | 34.01–58.28 |
| EPA | 28 / 57 | 49.12% | 36.62–61.74 |
| HHS | 985 / 2,867 | 34.36% | 32.64–36.11 |
| NASA | 176 / 424 | 41.51% | 36.92–46.26 |
| NRC | 3 / 4 | too few to rate | — |
| NSF | 632 / 1,753 | 36.05% | 33.84–38.33 |
| USDA | 101 / 241 | 41.91% | 35.85–48.22 |

The name-and-address method finds grant-only firms in PPP at 0.92 of the contract-only rate. It
finds them in 7(a) at 0.44 of that rate. The intervals do not overlap. So a lower recall for
grant-only firms explains at most a small part of the 7(a) gap **[inferred]**.

### Task 10 — review file

- **File:** `data/internal/sba_loans_feasibility/a5_review.csv` (117 rows, git-ignored).
- **Content:** firm side and loan side, shuffled, group hidden, with an empty `review_label`
  column.
- **Sample:** 30 R2 baseline 7(a) matches each for both, contract-only, and grant-only, and all
  27 for unclassified.
- **Key:** `a5_review_key.csv`.
- **Labels:** I did not label it. Precision is not known until a person reviews it
  **[unverified]**.

### A5 limits

- **Instrument is partly inferred.** 52,187 of 216,850 awards (24.07%) take an agency default.
  These include most NASA awards and every blank DoD, DOE, NSF, and USDA ID. The USAspending
  check found no disagreement in 254 found IDs, but it could not check blank IDs, other
  transactions, or IDs before FY2008.
- **Agency and instrument are confounded.** No stratum separates them, so the grant-versus-
  contract result cannot be told apart from an agency result.
- **One address per firm.** The SBIR.gov export has no award-time address history, so R2 depends
  on the firm's last-recorded address. Loans taken at an earlier address are not observed.
- **Precision unknown.** The review file is unlabeled. The earlier blind review (A1–A4
  extension) was single-reader and unverified.
- **Coverage.** The loan files start in FY1991. 7(a) is one public channel. Ordinary bank credit,
  unsecured credit, and non-guaranteed lending are not observed.
- **Post hoc.** This is a new question asked after earlier results (A5). It has no placebo, and
  it says nothing about awardees against other firms.
- **No causal claim.** The rates describe public observation, not whether, why, or how much
  firms borrow.
- **Run notes.**
  - The first USAspending check ran past its time limit and saved nothing. The second sent
    assistance codes that the API rejects, so all assistance IDs read "not found". Both were
    fixed before task 4.
  - The first task 4–9 run stopped on a JSON key error after matching, before writing or
    printing any figure. The rerun changed only the log format. No rule changed after task 4
    started.
