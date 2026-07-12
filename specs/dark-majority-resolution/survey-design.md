# Disappeared-Firm Survey — Design (T11)

**Status:** Design only. Fielding is out of scope for this repo and requires a decision on
who conducts outreach (agency evaluation shop vs. contractor) and human-subjects/PRA review
if run by or for a federal agency.

## Objective

Establish, for the 651 `FIRM_ACTIVITY_ABSENT` firms, the distribution across outcomes that
public data cannot distinguish: **dissolved / acquired-or-renamed / commercialized outside
federal view / active-non-commercial / unreachable**. This is the only instrument in the
dark-majority plan that produces *negative* evidence (confirmed dissolution), which the
capture-recapture analysis (T10) shows is the sole way to bound the true commercialization
rate from above.

## Frame and strata

Population: 651 firms. Strata by patent-instrument outcome (`nano_survey_frame.py`,
seed 20260712, frame in `data/nano_survey_frame.csv`):

| Stratum | Definition | Pop. | Primary n | Purpose |
|---|---|---|---|---|
| S1_active_evidence | High-confidence post-award patent activity | 317 | 20 | Validate the patent instrument against ground truth; characterize *what kind* of activity |
| S2_holder_only | Patent holder, no high-confidence post-award signal | 111 | 20 | Boundary cases; tests whether holding-without-filing predicts dormancy |
| S3_dark_core | No patent match | 223 | 35 | The truly dark population — oversampled because nothing else observes it |

75 primaries + 2× ranked backups per stratum for unreachables. Backups are drawn from the
same shuffle, so substitution preserves randomization.

## Precision expectations (be honest about them)

With n=35 (S3), a population proportion is estimated to roughly ±16 pp at 95% confidence
(worst case p=0.5, with finite-population correction for N=223 ≈ ±15 pp). Aggregate
weighted estimates over 75 firms land near ±10 pp. This supports **coarse outcome
fractions** (e.g., "roughly a third dissolved"), not fine rates. That is sufficient: the
decision-relevant quantity is the rough split between dissolved and
commercialized-but-invisible, which currently spans [0%, 100%].

## Instrument (core items)

1. Firm status: active / dissolved (year) / acquired (acquirer, year) / renamed (new name).
2. Did technology from the Phase II award(s) reach any market? (product sales, licensing,
   internal use by acquirer, no)
3. Any federal work after the award under a different name or UEI? (captures renames that
   defeat entity matching)
4. Approximate cumulative revenue attributable to the Phase II technology (bands).
5. Why no further federal contracting? (no need / chose commercial path / lost recompetes /
   ceased operations)
6. Consent to link the response to award records for evaluation purposes.

## Contact discovery

Primary: `PI Name` / `Contact Email` from SBIR.gov award records (stale for older awards —
expect high bounce; that is what the backups are for). Secondary: correspondence addresses
on the firm's patent filings (S1/S2 strata), which are typically fresher than award-era
contacts. Tertiary: state registry registered-agent lookups (deferred T7 — if T7 is ever
executed, run it before fielding to pre-classify dissolved firms and save survey capacity).

## Analysis plan

- Per-stratum outcome fractions with finite-population-corrected intervals; weighted
  aggregate for the 651-firm population.
- S1 doubles as an instrument-validation sample: the fraction of S1 firms confirmed active
  estimates the patent-liveness true-positive rate, which retroactively calibrates the 49%
  high-confidence figure in Finding 3.
- Confirmed dissolutions provide the first negative-evidence mass for the T10 upper bound.
- Non-response is reported as its own outcome class, never imputed away.
