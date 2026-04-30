# Form D Data Dictionary

## Fundraising Fields

The Form D XML contains three fundraising amount fields:

| Field | Meaning | Used in `total_raised`? |
|-------|---------|------------------------|
| `totalOfferingAmount` | How much the company *intended* to raise | No |
| `totalAmountSold` | How much was actually *sold* (accepted) by investors | **Yes** |
| `totalRemaining` | Difference: offering - sold | No |

The `total_raised` field in `form_d_details.jsonl` is the sum of
`totalAmountSold` across all of a company's Form D filings. It represents
actual capital accepted, not aspirational offering targets.

## Confidence Tiers

Tier assignment is rule-based on two discrete signals:

| Tier | Rule | Interpretation |
|------|------|----------------|
| High | `person_score >= 0.7` | PI name matches a Form D executive |
| Medium | `person_score < 0.7` AND `state_score >= 0.5` | No PI match but geographic confirmation |
| Low | `person_score < 0.7` AND `state_score < 0.5` | Name-only match, likely false positive |

A composite score (weighted sum of all 5 signals) is retained for
within-tier ranking but does not drive tier assignment.

## Temporal and Year-of-Inc Signals

These are computed and stored as metadata but do not influence tier
assignment:

- `temporal_score`: Form D date vs SBIR award date proximity
  (1.0 = within 2yr, 0.5 = 2-5yr, 0.0 = 6yr+)
- `year_of_inc_score`: 1.0 if incorporated before first SBIR award,
  0.0 if after (missing 29% of records)
