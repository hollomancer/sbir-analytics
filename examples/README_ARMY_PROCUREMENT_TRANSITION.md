# Army science and technology example

This deterministic example shows the monthly procurement-transition packet for
an Army-level science and technology audience. All companies, awards,
opportunities, identifiers, dates, amounts, scores, and alignment judgments are
synthetic. They demonstrate report structure only and must not be treated as
live acquisition intelligence.

The example uses three distinct public taxonomies so that a technology match is
not confused with an acquisition decision:

- **Mission interests:** the five Army Priority to Incentivize Technology (PIT)
  priorities for FY 2026–2027.
- **Technology ecosystems:** Army SBIR's published technology-area labels.
- **Potential transition lanes:** the six Portfolio Acquisition Executive
  portfolios. These are analyst routing hypotheses, not confirmed ownership.

Official references:

- [Army PIT priorities](https://pit.army.mil/about/priorities/)
- [Army SBIR technology ecosystems](https://armysbir.army.mil/who-we-are/)
- [Army acquisition portfolio structure](https://www.army.mil/article/288957/army_revolutionizes_acquisition_process_to_deliver_warfighting_capabilities_faster)

## Generate the packet

From the repository root:

```bash
uv run python scripts/data/monthly_procurement_transition_report.py \
  --month 2026-06 \
  --awards examples/army_science_technology_awards.csv \
  --candidates examples/army_science_technology_candidates.csv \
  --opportunities examples/army_science_technology_opportunities.csv \
  --output-root /tmp/procurement-transition-example
```

The generated packet is
`/tmp/procurement-transition-example/2026-06/centers/army-st-example.md`.
It should match
[army_science_technology_report.md](army_science_technology_report.md). The
other generated files demonstrate the audit sample, evidence ledger, master
candidate table, and source manifest.

Production use must replace these fixtures with current SBIR.gov and SAM.gov
records, preserve record-level public links, and pass the documented hand-audit
gate before representative distribution.
