# Government Policy Audience Demo Plan

*Audience: federal policy leaders, program evaluators, legislative staff, agency
portfolio managers, oversight analysts, and implementation teams evaluating how
public data can improve SBIR/STTR commercialization monitoring.*

---

## 1. Demo objective

The demo should show that this project is not just an engineering exercise or a
single research note. It is an **outcomes intelligence layer** for SBIR/STTR:

> Given a public award record, can we connect it to downstream evidence of
> commercialization, follow-on procurement, capital formation, technology
> diffusion, and economic activity — with enough provenance for policy review?

For a government policy audience, the purpose is not to prove causality in a
30-minute meeting. The purpose is to show a repeatable, auditable workflow that
helps answer questions government already has:

- Which awardees appear to transition after Phase II?
- Which firms attract private capital or are acquired?
- Which technology areas receive support across agencies?
- Which outcomes are visible in public data and which remain missing?
- Where do existing federal data systems undercount commercialization?
- Which findings are mature enough for decision support and which are still
  research leads?

## 2. Audience framing

Frame the core narrative as a reusable policy workflow with different entry
points depending on the stakeholder's job — not as a demo built for one named
agency. When you *are* presenting to a specific agency, tailor the entry point
(see the worked NSF/SBA example in section 11).

| Audience type | What they care about | Best demo entry point |
|---|---|---|
| Program oversight | Whether statutory benchmarks, reporting requirements, and performance signals can be measured consistently. | Benchmark CLI, entity-resolution caveats, data-quality checks. |
| Portfolio managers | Whether award portfolios are changing by technology area, agency, cohort, geography, or firm type. | CET portfolio composition, award/cohort cuts, trend monitoring. |
| Procurement / transition staff | Whether Phase II work turns into follow-on contracts and how much Phase III activity is undercounted. | Phase II→III latency, follow-on funding multiplier, evidence bundles. |
| Economic-policy staff | Whether public awards are associated with economic or fiscal effects. | Fiscal-impact examples, state/district cuts, uncertainty bands. |
| Legislative / oversight staff | Whether the program can be explained clearly and audited. | Plain-English evidence bundle, headline findings with caveats, reproducibility plan. |

## 3. Core message

Use this concise message throughout the demo:

> SBIR/STTR outcome tracking is fragmented. This project joins public datasets
> into evidence bundles so government users can distinguish observed outcomes,
> missing data, and research hypotheses.

Avoid saying:

- "This proves SBIR caused the outcome."
- "This is an official commercialization rate."
- "This captures all Phase III work."
- "This is production-ready."

Prefer:

- "Detected signal."
- "High-confidence match."
- "Candidate transition."
- "Public-data approximation."
- "Descriptive, not causal."
- "Ready for review / not yet ready for policy use."

## 4. Demo structure

### Segment 1 — The shared policy problem (5 minutes)

Start with the data gap:

1. SBIR/STTR award data exists.
2. Downstream commercialization signals exist in other public systems.
3. They are not joined into an auditable outcomes layer.
4. Program reviews therefore rely on fragmented reporting, surveys, and
   one-off studies.

Show the high-level pipeline:

- SBIR.gov awards
- USAspending / FPDS contracts
- SEC EDGAR / Form D filings
- USPTO patents
- SAM.gov entity records
- BEA / fiscal inputs
- Dagster, DuckDB, Neo4j, and reports

The point is not to show every asset. The point is to show that the architecture
can connect policy questions to evidence.

### Segment 2 — Outcome signals the pipeline can already explain (10 minutes)

Use three concrete findings as the "why this matters" portion.

#### A. Private capital after SBIR

Show the Form D analysis as a program-wide capital-formation signal:

- High-confidence matched firms: `$1.82` in Form-D-detected private capital per
  `$1` of total federal SBIR funding.
- High + medium confidence: `$2.37` per `$1`.
- Explain the denominator choice clearly: program-wide ratio and matched-firm
  ratio answer different questions.

Policy interpretation:

> This does not prove the award caused the raise. It does show which awardee
> cohorts later appear in a regulated private-capital disclosure system.

#### B. Branch / subportfolio heterogeneity

Use the DoD branch Form D decomposition as an example of why aggregate
benchmarks can hide important policy structure:

- Air Force appears much higher in Form-D-detected private-capital leverage.
- Navy appears lower in Form-D-detected private capital, with evidence of
  alternative commercialization or substitution channels.

Policy interpretation:

> The useful policy finding is not "Agency X is good or bad." It is that one
> aggregate program can contain multiple commercialization pathways.

#### C. M&A and acquisition signals

Show acquisition / business-combination detection as another outcome channel:

- Some firms commercialize through growth financing.
- Others commercialize through acquisition.
- Some signals are high confidence; others require human review.

Policy interpretation:

> A complete commercialization picture needs multiple evidence types, not one
> ratio.

### Segment 3 — Live-demo-ready mechanics (10 minutes)

Use a deterministic local file and one command-line workflow, not a fragile live
API run.

#### A. Benchmark CLI

Show `scripts/run_benchmark.py` with an explicit fiscal year:

```bash
PYTHONPATH=packages/sbir-ml:. \
python scripts/run_benchmark.py evaluate awards.csv --fy 2025 --report
```

Then show the same file through the focused subcommands:

```bash
PYTHONPATH=packages/sbir-ml:. \
python scripts/run_benchmark.py sensitivity awards.csv --fy 2025

PYTHONPATH=packages/sbir-ml:. \
python scripts/run_benchmark.py company awards.csv --fy 2025 --id uei:EXAMPLE
```

Why this matters to a government audience:

- The evaluation fiscal year is explicit and reproducible.
- The output is traceable to per-company counts and thresholds.
- The same command can run on sample, agency, or full-public-data inputs.

#### B. Evidence bundle walk-through

For one synthetic or public example company, show:

- SBIR award rows.
- Company identifier used for matching.
- Follow-on contract candidate.
- Form D signal, if present.
- Patent signal, if present.
- Confidence tier and caveats.

This should be shown as a simple table or static report rather than a database
query if the audience is policy-focused.

#### C. Portfolio slice

Show a cross-agency or cross-cohort portfolio slice:

- award dollars,
- technology area,
- downstream signals,
- data-quality coverage,
- caveats.

Use this to transition from individual cases to portfolio monitoring.

### Segment 4 — Continuous monitoring, not a one-time study (5 minutes)

Close by contrasting the workflow with periodic program reviews:

- Quarterly or monthly refreshes could track new awards, filings, patents, and
  contracts.
- Each refresh can emit deltas, not just static reports.
- Quality checks can show whether observed changes are real or data artifacts.

Policy interpretation:

> The differentiator is not a single headline number. It is a repeatable
> monitoring loop that can flag where the public record changed and where human
> review is needed.

## 5. What to demo, what to caveat, what to leave out

### Demo now

- Benchmark CLI on deterministic sample or prepared award data.
- Form D private-capital analysis as a documented finding.
- DoD branch heterogeneity as an example of subportfolio analysis.
- M&A signal methodology and confidence tiers.
- Phase II→III latency concept and undercount caveats.
- CET portfolio composition as a portfolio-management lens.

### Demo only with caveats

- Fiscal-impact modeling: describe as exploratory and assumption-sensitive.
- Phase III totals: describe as lower bounds when derived from public coding or
  keyword discovery.
- Entity resolution: show confidence scores and false-positive risk.
- District/state outputs: useful for briefings, but sensitive to geocoding and
  firm-location assumptions.

### Leave out of the live room unless specifically asked

- Unverified headline numbers from trade press or uncommitted notes. Concrete
  example: the NSF ~18:1 portfolio-leverage figure is flagged `[TODO: verify]`
  in [research-questions.md](../research-questions.md) — found only in trade
  press, not confirmed against an NSF publication. If asked, say it's being
  verified.
- Supply-chain chokepoint / fragility hypotheses that are not scoped or
  implemented (A-CP5, A-CP7, A-CP10–A-CP14 in the research-questions
  inventory). Fine to mention as roadmap if asked, not to demo.
- Local-only audit harnesses or files that are not in the repository — e.g.
  the commercialization-benchmark methodology doc and per-firm audit harness.
  Don't promise a paper trail that isn't on `main` yet.
- Congressional district success-story briefings — these exist only "in
  conversation," not as committed repo artifacts.
- Any language implying official agency validation.

## 6. Required artifacts for a credible policy demo

Before presenting to a government audience, prepare these artifacts in the PR or
demo bundle:

1. **One-page overview** — what data sources are joined and what outcomes are
   measured.
2. **Sample benchmark output** — generated from a deterministic CSV fixture.
3. **One firm evidence bundle** — a readable row-level example.
4. **One portfolio cut** — agency, cohort, technology area, or geography.
5. **Caveat slide** — entity resolution, data completeness, Phase III coding,
   causality, and reproducibility.
6. **Readiness matrix** — "demo now," "prototype," "research target," and
   "out of scope."

## 7. Pre-demo checklist

Run this checklist before a live policy meeting:

- [ ] Use a deterministic sample dataset or a precomputed public-data snapshot.
- [ ] Use an explicit `--fy` for benchmark outputs.
- [ ] Confirm every headline number has a committed source document.
- [ ] Confirm every "live" command has been run in the meeting environment.
- [ ] Prepare screenshots or static HTML fallback in case services are down.
- [ ] Keep raw company-level examples public, synthetic, or cleared for use.
- [ ] Put limitations on the same slide as headline results.
- [ ] Separate "observed in public data" from "inferred" and "not measured."

## 8. Suggested 30-minute run of show

| Time | Segment | Artifact |
|---:|---|---|
| 0–5 | Why outcome tracking is hard | Architecture / data-source slide |
| 5–12 | What the pipeline finds | Form D + M&A headline slides |
| 12–18 | Why aggregation can mislead | Branch / subportfolio heterogeneity slide |
| 18–24 | Live deterministic CLI | Benchmark CLI on sample data |
| 24–28 | Portfolio monitoring | CET / transition / quarterly-refresh mockup |
| 28–30 | Caveats and next decision | Readiness matrix |

## 9. Follow-up asks for policy audiences

End with questions that invite validation, not applause:

- Which outcome signals are most decision-relevant for your office?
- Which confidence thresholds would be acceptable for exploratory monitoring?
- Which records or identifiers would improve match quality?
- Which aggregate cuts matter most: agency, cohort, state, technology area, firm
  size, award phase, or procurement channel?
- Which findings require human audit before being used in formal reporting?

## 10. Success criteria

The demo succeeds if the audience leaves understanding:

1. what the project can measure today,
2. which claims are documented vs. speculative,
3. how a specific output can be reproduced,
4. where public data is incomplete,
5. what decision they need to make next to harden the workflow.

The demo fails if it becomes a tour of code, a debate over one headline number,
or an implied claim that public-data linkage is equivalent to official program
measurement.

## 11. Worked example: NSF and SBA

"Policy leaders" is not one audience. NSF and SBA sit in different roles
relative to the SBIR/STTR program, and the [research-questions
inventory](../research-questions.md) already tells you where each one's entry
point is:

- **SBA** is the program's statutory overseer. It has a specific compliance
  question to answer every year: which Phase II awardees meet the §638(qq)(3)
  Commercialization Benchmark (Pub. L. 117-183)? This is not a research
  question for SBA — it's a legal obligation. Lead with the tool that answers
  it directly.
- **NSF** is a program office running its own SBIR portfolio. Per the
  inventory's audience guidance, NSF program managers start with **B**
  (transitions, Phase II→III latency), **C1** (cross-agency CET portfolio
  composition), and **E6** (rolling quarterly snapshots) — i.e., "how is my
  program's technology mix and commercialization trending relative to other
  agencies," not "are we compliant."

Treat this as two short, separate walkthroughs rather than one combined
narrative — the material that lands for one audience (statutory compliance)
falls flat for the other (portfolio strategy), and vice versa.

### What's genuinely demo-ready today

Everything below is implemented on `main`, backed by real data, and
reproducible — not a spec or a research target.

| Artifact | What it shows | Where |
|---|---|---|
| Commercialization Benchmark CLI | Live §638(qq)(3) eligibility, sensitivity, and per-company evaluation against real award data | `scripts/run_benchmark.py` (`evaluate` / `sensitivity` / `company` subcommands), backed by `sbir_etl/models/benchmark_models.py` |
| Form D private-capital leverage | For every $1 of federal SBIR funding, SBIR companies raised $1.82–$2.37 in private capital via SEC Reg D (95% bootstrap CIs, 3,640–4,760 companies) | `docs/research/sbir-form-d-fundraising-analysis.md` |
| DoD branch leverage heterogeneity | Aggregate DoD Form D leverage (1.01x) masks a ~9x spread — Air Force 2.12x vs. Navy 0.41x, tied to a federal-contract substitution channel | `docs/research/dod-form-d-leverage.md` |
| Cross-agency CET portfolio composition | Federal SBIR portfolio broken out by the 21-area NSTC-2025Q1 technology taxonomy, across all 11 agencies | `config/cet/taxonomy.yaml`, `packages/sbir-ml/sbir_ml/ml/config/taxonomy_loader.py`, spec at `specs/cross-agency-taxonomy/` |
| SEC EDGAR outcomes plain-English guide | Explains, in non-technical terms, how the pipeline detects acquisitions/investment/public-filer status for SBIR firms — good leave-behind reading | [sec-edgar-for-policy-makers.md](sec-edgar-for-policy-makers.md) |

### Suggested flow

1. **Open together (5 min):** the Form D leverage finding and the DoD
   branch-heterogeneity breakdown, framed as "this pipeline finds things a
   quadrennial NASEM review can't, because it runs continuously." Works for
   both audiences as an opener.
2. **Split for ~10 minutes each:**
   - *SBA track:* run the benchmark CLI live against real award data (the
     commands in section 4, Segment 3); walk through one company's
     `evaluate_single_company` output to show the statutory test resolving
     end-to-end.
   - *NSF track:* CET cross-agency portfolio composition — NSF's technology
     mix vs. other agencies, then Phase II→III transition latency for NSF's
     own awards.
3. **Close together (5 min):** the continuous-monitoring pitch (E6) — this
   isn't a one-time study, it's infrastructure that can produce
   quarter-over-quarter snapshots between NASEM's four-year review cycles.
   See `docs/research-plan-alignment.md`, milestone M5.

### Rehearsing the live commands

Rehearse against a real awards file before the demo. The SBIR.gov bulk CSV
(`data/raw/sbir/award_data.csv`, see
[awards-refresh.md](../data/awards-refresh.md)) works directly — the evaluator
resolves its `Company` / `UEI` / `Phase` / `Award Year` columns as-is. Any
substitute file must have a phase column (`Phase` or `phase`) and a fiscal-year
column (`fiscal_year`, `award_year`, or `Award Year`); the CLI exits with an
error if either is missing. Do not use
`tests/fixtures/follow_on_multiplier/sbir_awards.csv` — it has no phase column.

### Where to go next

- Full research-question inventory and audience map:
  [research-questions.md](../research-questions.md)
- Milestone-by-milestone build status vs. the underlying research plan:
  [research-plan-alignment.md](../research-plan-alignment.md)
- Plain-English methodology explainer to leave behind:
  [sec-edgar-for-policy-makers.md](sec-edgar-for-policy-makers.md)
