# SBIR Social Return Break-Even Design

## Question

What attributable share of observed benefits makes SBIR equal its taxpayer cost?

## Estimand

Let `C` equal present-value taxpayer cost.
Let `B_id` equal monetized benefits supported by causal evidence.
Let `B_linked` equal monetized awardee-linked benefits without causal identification.

Calculate `alpha_star = max(0, (C - B_id) / B_linked)`.
Interpret `alpha_star` as the minimum attributable share needed to break even.
Do not interpret it as an estimated causal share.

## Ledgers

Calculate fiscal and domestic-social ledgers separately.
Use incremental federal receipts and avoided federal costs in the fiscal ledger.
Use consumer surplus, producer surplus, productivity, mission value, and domestic spillovers in the social ledger.
Subtract real resources, administration, burden, displacement, and opportunity cost.

## Attribution

Assign causal, descriptive, or inference labels to every input.
Use causal estimates in `B_id` only for their identified population.
Apply explicit scenario weights to linked benefits.
Show results with and without transport to the full portfolio.

## Guardrails

Convert revenue to incremental value added or surplus.
Treat capital and exits as validation signals.
Treat taxes as fiscal benefits and domestic transfers in the social ledger.
Prevent duplicate counting across licenses, sales, profits, procurement, and downstream use.

## Sensitivity

Use constant-dollar cohorts and a declared discount schedule.
Report one-way, joint, and probabilistic sensitivity.
Compare SBIR with the strongest feasible alternative federal use of funds.
