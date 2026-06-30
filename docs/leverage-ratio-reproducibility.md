# DOD leverage ratio reproducibility report

## Gate statement

NASEM reports **4:1**. The deterministic pipeline fixture yields **1.1667:1** using transaction-level net USAspending obligations, same-agency SBIR-firm universes, nominal dollars, an entity-match threshold of 0.80, and all available fixture fiscal years.

## Traceable fixture comparison

| Measure | Value |
|---|---:|
| NASEM benchmark | 4.0000:1 |
| Pipeline DOD SBIR denominator | $300 |
| Pipeline DOD non-SBIR numerator | $350 |
| Pipeline DOD ratio | 1.1667:1 |
| Difference from benchmark | -2.8333 |

## Methodological differences, not implementation errors

- The fixture is a deliberately tiny edge-case population, not the NASEM study population.
- Pipeline amounts are net obligations and retain a `$-50` de-obligation.
- Low-confidence and unmatched entities are reported but excluded.
- The pipeline uses explicit cohort/fiscal windows and a same-agency SBIR-firm universe.
- The NASEM source edition, exact study window, transaction coverage, and denominator method remain product decisions documented in the analysis guide.

The deterministic numerator and denominator are asserted in unit tests. A difference from 4:1 is therefore classified as methodological; a non-finite observed aggregate is the implementation-error signal.
