# UCC-1 Financing Analysis — Requirements

**Research questions:** A4 (private capital signals, foreign-acquisition risk,
M&A exit detection), B3 (Phase II → III latency)

**Status:** Pilot scope. Pursue multi-state expansion only after pilot validates
match quality and signal value.

## Background

The Form D analysis (`docs/research/sbir-form-d-fundraising-analysis.md`)
measures private *equity* raised by SBIR firms via Reg D — ~$1.82–$2.37 per
$1 of SBIR funding. It misses private *debt* entirely: venture debt
(SVB, Hercules, Trinity, Western Alliance), equipment financing, and
asset-backed lines.

UCC-1 financing statements, filed at state Secretaries of State under UCC
Article 9, are the public record of those secured transactions. Each filing
names a debtor, a secured party (lender), and a collateral description.

This spec scopes a **pilot** that uses free DE + CA UCC indexes to answer one
question: *what fraction of equity-backed SBIR firms also took venture debt,
and from whom?*

## Requirements

1. **SHALL** extract UCC-1 filings from Delaware and California state portals
   for the population of SBIR firms in the Form D high-confidence cohort
   (~3,640 companies per `sbir-form-d-fundraising-analysis.md`).
2. **SHALL** match UCC-1 debtors to SBIR firms using a name-and-state fuzzy
   cascade compatible with the existing entity-resolution approach.
3. **SHALL** classify secured parties into: known venture-debt lenders,
   equipment/inventory financiers, banks (depository), other / unknown.
4. **SHALL** report the fraction of matched SBIR firms with ≥1 UCC-1 filing
   from a venture-debt lender, stratified by award agency and award vintage.
5. **SHALL** report match rates and false-positive sensitivity (top-K
   manually reviewed matches per state).
6. **SHOULD** identify foreign secured parties as a separate flag (national-
   security signal aligned with A4 / CSIS [L17]).
7. **SHOULD NOT** attempt nationwide coverage, IP-collateral parsing,
   UCC-3 lifecycle reconstruction, or Neo4j loading in the pilot. Those
   are explicitly out of scope; revisit after pilot results.

## Gate Condition

Can state: "Of the N Form-D-confirmed SBIR firms in DE + CA, X% have at least
one UCC-1 filing from a known venture-debt lender. Top lenders by SBIR-firm
count are [list]. Match precision on a 50-firm hand-reviewed sample is Y%."

Reconciliation matters more than completeness. If the pilot shows <10% match
rate or <70% precision, the data source is not worth multi-state expansion;
that is also a valid result.

## Non-Goals (pilot)

- Nationwide UCC coverage (commercial feed required; cost not justified
  pre-pilot).
- UCC-3 amendment / termination lifecycle (event detection, M&A timing).
- IP-collateral text parsing (patent / trademark pledges).
- Dagster asset wiring or Neo4j loading.
- Lender-concentration time series.

## Dependencies

- Form D high-confidence cohort — EXISTS (`docs/research/sbir-form-d-fundraising-analysis.md`)
- SBIR awards table with company name + state — EXISTS
- Fuzzy entity-resolution utilities — EXIST (`sbir_etl` matching helpers)
