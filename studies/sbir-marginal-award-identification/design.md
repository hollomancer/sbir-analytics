# Marginal Award Identification Design

## Question

Estimate the effect of receiving an SBIR award near an agency selection boundary.

## Estimand

Estimate the local average treatment effect for applicants near a recorded cutoff.
Estimate effects by agency, phase, topic type, cohort, firm age, and prior awards.

## Required population

Include scored applications on both sides of the same selection boundary.
Preserve scores, ranks, cutoff rules, review dates, and funding decisions.
Separate administrative exceptions from score-based decisions.

## Outcomes

Measure operating status, survival, private capital, licensing, non-SBIR revenue, productivity, procurement, and exits.
Treat patents as intermediate outputs.
Use dated windows from the selection decision.

## Identification

Use regression discontinuity when the score determines treatment near a cutoff.
Test score density, covariate continuity, bandwidth sensitivity, and alternative polynomials.
Use randomized award features when an agency supplies a valid experiment.
Do not use unfunded nonapplicants as causal controls.

## Failure conditions

Stop causal estimation when scores are unavailable or the cutoff did not govern treatment.
Label matched comparisons as descriptive evidence.
Do not transport a local effect to the full portfolio without a declared model.
