# SBIR Social Return Break-Even Design

## Question

What attributable share of observed benefits makes SBIR equal its taxpayer cost?

## Estimand

Compute one break-even share per ledger. Each ledger has its own cost base.

Let `B_id` equal monetized benefits supported by causal evidence, in that ledger.
Let `B_linked` equal monetized awardee-linked benefits without causal identification, in that ledger.

- Fiscal: `alpha_star_fiscal = (C_fiscal - B_id_fiscal) / B_linked_fiscal`,
  with `C_fiscal` = present-value federal outlays.
- Domestic-social: `alpha_star_social = (C_social - B_id_social) / B_linked_social`,
  with `C_social` = real resource costs plus excess burden.

Name the outcome instead of clamping the number:

| Condition | Outcome |
| --- | --- |
| `C - B_id <= 0` | `breaks_even_on_identified` |
| `B_linked = 0` and `C - B_id > 0` | `undefined_no_linked_benefits` |
| `0 < alpha_star <= 1` | `feasible` |
| `alpha_star > 1` | `unattainable` |

Interpret a feasible `alpha_star` as the minimum attributable share needed to break even.
Do not interpret it as an estimated causal share. `unattainable` is a finding, not an
error: linked benefits cannot close the gap at any attribution share.

## Ledgers

Calculate fiscal and domestic-social ledgers separately, each from its own cost base.
Use incremental federal receipts and avoided federal costs in the fiscal ledger.
Use consumer surplus, producer surplus, productivity, mission value, and domestic spillovers in the social ledger.
In the social ledger, subtract real resources, administration, burden, displacement, and excess burden.
Report the alternative-mechanism comparison beside the social result; never subtract it.

## Attribution

Assign causal, descriptive, or inference labels to every input.
Use causal estimates in `B_id` only for their identified population.
Apply explicit scenario weights to linked benefits.
Show results with and without transport to the full portfolio.

## Guardrails

Convert revenue to incremental value added or surplus.
Treat capital and exits as validation signals.
Treat taxes as fiscal benefits; in the social ledger they are domestic transfers valued at zero,
with the excess burden of raising them carried as a separate real social cost.
Prevent duplicate counting across licenses, sales, profits, procurement, and downstream use.

## Sensitivity

Use constant-dollar cohorts and a declared discount schedule.
Report one-way, joint, and probabilistic sensitivity.
Compare SBIR with the strongest feasible alternative federal use of funds.
