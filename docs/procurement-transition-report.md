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

Every lead uses the same representative-facing evidence card: what the award
funded, what the solicitation asks for, the technical connection to validate,
why the pair was surfaced, and a class-specific representative check. Scores
are shown only as triage ranks; they are not probabilities or acquisition
determinations. A missing solicitation description is called out explicitly
instead of treating its title as a detailed statement of need.

## Example packet

The
[synthetic Army science and technology example](../examples/army_science_technology_report.md)
shows a five-interest screening packet with award and candidate totals,
an action queue, side-by-side technical evidence, technology-ecosystem tags,
and potential acquisition transition lanes. Its
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
uv run python scripts/data/hydrate_candidate_opportunity_descriptions.py \
  --opportunities data/raw/sam_gov_opportunities/opportunities.parquet \
  --awards data/processed/procurement_award_cohort.parquet \
  --max-records 500
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

The bounded hydration step shortlists active targets using recipient identity,
agency hierarchy, and acquisition-code gates before applying any
description-dependent scoring. It then retrieves full descriptions only for
that shortlist and computes candidates from the richer solicitation text. This
avoids an unbounded description crawl without creating a circular dependency
in which a missing description prevents a target from being selected for
hydration. The `--max-records` cap is an explicit coverage limit recorded in
the command output and adjacent `.hydration.json` audit file. If SAM.gov rate
limits the detail requests, the job keeps the descriptions already retrieved,
records the partial coverage, and continues with explicit missing-text labels.

Pass the preceding public award snapshot with `--previous-awards` to distinguish
new and changed records. The scheduled workflow restores that snapshot from the
prior monthly run and retains the report and evidence artifacts for 90 days.
When `OPENAI_API_KEY` is absent, `--ai` degrades to deterministic packet text.
AI receives only retrieved public fields, is invoked only when both technical
texts are available, and is capped at 10 priority leads by default. It cannot
change candidate scores, and uncited output is discarded. Use
`--ai-max-summaries` to lower or explicitly raise that cap.

Representative distribution remains a human-controlled step. The generated
`audit_sample.csv` supports the required hand audit; each HIGH signal class must
reach at least 85% precision before its main packet section is distributed.
