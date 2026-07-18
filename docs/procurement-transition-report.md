# Monthly Procurement Transition Report

The monthly procurement-transition report combines public SBIR.gov awards,
SAM.gov opportunities, and USAspending/FPDS evidence into procurement-center
packets.  It reports recorded period-of-performance end dates; it does not
claim that technical work has been verified as complete.

The representative-facing output distinguishes two opportunity classes:

- **Directed candidates** have evidence consistent with a potential Phase III
  path, such as lineage language, recipient identity, and agency continuity.
- **Competitive follow-on candidates** are topically relevant public
  opportunities and are not labeled as statutory Phase III awards.

Generated packets must retain public source links and keep lower-confidence
watchlist entries separate from high-confidence candidates.

## Example packet

The
[synthetic Army science and technology example](../examples/army_science_technology_report.md)
shows a five-interest screening packet with award and candidate totals,
high-confidence and watchlist sections, technology-ecosystem tags, and
potential acquisition transition lanes. Its
[README](../examples/README_ARMY_PROCUREMENT_TRANSITION.md) includes
reproducible CSV inputs and the exact generation command.

The optional candidate fields `interest_alignment`, `technology_ecosystem`,
`potential_transition_lane`, and `alignment_rationale` are carried into the
packet when an upstream screening step supplies them. These annotations are not
evidence of a validated requirement, endorsement, or confirmed transition
decision.

## Running the monthly pipeline

Set `SAM_GOV_API_KEY` to a free public SAM.gov key, then run:

```bash
uv run python scripts/data/download_sam_opportunities.py --without-descriptions
uv run python scripts/data/enrich_procurement_awards.py \
  --month 2026-06 \
  --awards data/raw/sbir/award_data.csv
uv run python scripts/data/build_phase_iii_opportunity_candidates.py \
  --month 2026-06 \
  --awards data/processed/procurement_award_cohort.parquet \
  --opportunities data/raw/sam_gov_opportunities/opportunities.parquet
uv run python scripts/data/monthly_procurement_transition_report.py \
  --month 2026-06 \
  --awards data/processed/procurement_award_cohort.parquet \
  --candidates data/processed/phase_iii_candidates.parquet \
  --opportunities data/raw/sam_gov_opportunities/opportunities.parquet \
  --ai
```

Pass the preceding public award snapshot with `--previous-awards` to distinguish
new and changed records. The scheduled workflow restores that snapshot from the
prior monthly run and retains the report and evidence artifacts for 90 days.
When `OPENAI_API_KEY` is absent, `--ai` degrades to deterministic packet text.
AI receives only retrieved public fields, cannot change candidate scores, and
uncited output is discarded.

Representative distribution remains a human-controlled step. The generated
`audit_sample.csv` supports the required hand audit; each HIGH signal class must
reach at least 85% precision before its main packet section is distributed.
