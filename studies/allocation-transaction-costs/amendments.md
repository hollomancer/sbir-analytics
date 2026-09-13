# Allocation Transaction Costs Study — Amendment Log

`design.md` is frozen and pinned by SHA-256 in `study.yaml`. This file records design-level
findings that arrive after the freeze without altering the frozen bytes.

## Revision 0 — Frozen NIH break-even design

- **Date:** 2026-09-12.
- **Rule:** Named `mechanism-year-v1`. NIH SBIR/STTR phases compared against NIH
  R01-equivalent grants as a break-even condition over declared hour and duration
  assumptions, from published mechanism-year tables.
- **Frozen design SHA-256:**
  `2a2b28054de33b8aa1f57916f6fb5997124b3788e592596f3346e6f085f07afd`.
- **Result status:** Reproducible, not validated, not citable.

## Revision 1 — The NIH-SBIR-versus-R01 contrast is not a performer comparison

- **Date:** 2026-09-13. No change to the frozen design, the committed tables, or any
  computed series. This revision records an identification limitation and names the designs
  that would address it.
- **Finding:** The observed difference between NIH SBIR Phase I and NIH R01-equivalent
  grants is the sum of at least four effects that this design cannot separate: the performer
  (small firm versus university), the award architecture (staged SBIR selection versus
  single-stage grant), the award size, and the research type (product-directed feasibility
  work versus investigator-initiated science). The study's estimand and permitted claims
  already refuse a directional ranking, which is the correct posture; this revision states
  *why* a ranking would be unidentified rather than merely underpowered.
- **Consequence for interpretation:** A break-even threshold computed from this design
  answers "at what assumed SBIR applicant-hour count does cost per awarded dollar equalize
  between these two mechanisms". It does not answer "do small businesses transact federal
  R&D dollars more cheaply than universities". The second question requires holding the
  mechanism constant.
- **Designs that would identify the performer effect,** in descending order of strength:
  1. Small businesses and universities competing inside the *same* funding opportunity under
     the *same* assistance instrument. DOE Office of Science financial assistance and some
     NIH research-grant opportunities admit both performer types; DARPA BAAs do too but
     introduce instrument variation (a university cooperative agreement is not a company
     procurement contract) and would need instrument matching.
  2. STTR as an internal matched pair. Every STTR project contains both a small business and
     a research institution, holding technology, agency, award, period, and objectives nearly
     constant. The asymmetry is real and must be declared: the small business is the prime
     recipient and the research institution is normally subordinate.
  3. The present SBIR-versus-R01 contrast, which is weak for the performer question
     specifically, whatever its value for describing the mechanisms as they stand.
- **Measurement rule carried forward:** Neither a university F&A rate nor a company indirect
  rate is a transaction-cost rate. University F&A contains buildings, utilities, libraries,
  IT, and depreciation; company indirect pools contain rent, payroll taxes, insurance, and
  accounting. `forbidden_hour_sources` already refuses `fa_rate`; the company-indirect side
  is the same error and is refused on the same grounds. Transaction cost means resources
  consumed *because* the money must be competed for, transferred, monitored, and documented,
  not resources required to perform the research.
- **Not adopted:** no new mechanism, table, or assumption is introduced here. Acting on the
  designs above would be a new study with its own spec and freeze, not an amendment to this
  one.
