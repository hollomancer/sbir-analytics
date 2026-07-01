# Demoing This Pipeline to NSF and SBA Policy Leaders

*Audience: whoever is preparing or giving the demo. Not a technical doc — a
planning guide for what to show, in what order, and what to leave out.*

---

## 1. Why NSF and SBA need different demos

"Policy leaders" is not one audience. NSF and SBA sit in different roles
relative to the SBIR/STTR program, and the [research-questions
inventory](../research-questions.md) already tells you where each one's
entry point is:

- **SBA** is the program's statutory overseer. It has a specific compliance
  question to answer every year: which Phase II awardees meet the
  §638(qq)(3) Commercialization Benchmark (Pub. L. 117-183)? This is not a
  research question for SBA — it's a legal obligation. Lead with the tool
  that answers it directly.
- **NSF** is a program office running its own SBIR portfolio. Per the
  inventory's audience guidance, NSF program managers start with **B**
  (transitions, Phase II→III latency), **C1** (cross-agency CET portfolio
  composition), and **E6** (rolling quarterly snapshots) — i.e., "how is my
  program's technology mix and commercialization trending relative to other
  agencies," not "are we compliant."

Treat this as two short, separate walkthroughs rather than one combined
narrative — the material that lands for one audience (statutory compliance)
falls flat for the other (portfolio strategy), and vice versa.

## 2. What's genuinely demo-ready today

Everything below is implemented on `main`, backed by real data, and
reproducible — not a spec or a research target.

| Artifact | What it shows | Where |
|---|---|---|
| Commercialization Benchmark CLI | Live §638(qq)(3) eligibility, sensitivity, and per-company evaluation against real award data | `scripts/run_benchmark.py` (`evaluate` / `sensitivity` / `company` subcommands), backed by `sbir_etl/models/benchmark_models.py` |
| Form D private-capital leverage | For every $1 of federal SBIR funding, SBIR companies raised $1.82–$2.37 in private capital via SEC Reg D (95% bootstrap CIs, 3,640–4,760 companies) | `docs/research/sbir-form-d-fundraising-analysis.md` |
| DoD branch leverage heterogeneity | Aggregate DoD Form D leverage (1.01x) masks a ~9x spread — Air Force 2.12x vs. Navy 0.41x, tied to a federal-contract substitution channel | `docs/research/dod-form-d-leverage.md` |
| Cross-agency CET portfolio composition | Federal SBIR portfolio broken out by the 21-area NSTC-2025Q1 technology taxonomy, across all 11 agencies | `config/cet/taxonomy.yaml`, `packages/sbir-ml/sbir_ml/ml/config/taxonomy_loader.py`, spec at `specs/cross-agency-taxonomy/` |
| SEC EDGAR outcomes plain-English guide | Explains, in non-technical terms, how the pipeline detects acquisitions/investment/public-filer status for SBIR firms — good leave-behind reading | `docs/guides/sec-edgar-for-policy-makers.md` |

## 3. What to keep out of the room

- **The NSF ~18:1 portfolio-leverage figure.** Flagged `[TODO: verify]` in
  the research-questions doc — found only in trade press, not confirmed
  against an NSF publication (NSF's own pages returned 403 during the last
  review, and a separate NSF page citing "$6.5B private investment since
  2015" doesn't reconcile). Do not cite this in front of NSF. If asked,
  say it's being verified.
- **Choke-point / fragility questions (A-CP5, A-CP7, A-CP10–A-CP14).**
  Explicitly labeled "research target — not yet scoped" in the inventory.
  Fine to mention as roadmap if asked about supply-chain risk, not to demo.
- **The commercialization-benchmark methodology doc and per-firm audit
  harness.** Per the inventory, these exist only locally/uncommitted. Don't
  promise SBA a paper trail that isn't on `main` yet.
- **Congressional district success-story briefings.** Exist only "in
  conversation," not as committed repo artifacts — don't imply a
  ready-to-hand product.

## 4. Suggested flow

1. **Open together (5 min):** the Form D leverage finding and the DoD
   branch-heterogeneity breakdown, framed as "this pipeline finds things a
   quadrennial NASEM review can't, because it runs continuously." Works for
   both audiences as an opener.
2. **Split for ~10 minutes each:**
   - *SBA track:* run `scripts/run_benchmark.py evaluate ... --report` live
     against real award data; walk through one company's `evaluate_single_company`
     output to show the statutory test resolving end-to-end.
   - *NSF track:* CET cross-agency portfolio composition — NSF's technology
     mix vs. other agencies, then Phase II→III transition latency for NSF's
     own awards.
3. **Close together (5 min):** the continuous-monitoring pitch (E6) — this
   isn't a one-time study, it's infrastructure that can produce
   quarter-over-quarter snapshots between NASEM's four-year review cycles.
   See `docs/research-plan-alignment.md`, milestone M5.

## 5. Reproducing the live-demo commands beforehand

```bash
# Commercialization Benchmark — SBA track
python scripts/run_benchmark.py evaluate <awards.parquet> --fy 2024 --report
python scripts/run_benchmark.py company <awards.parquet> --id <UEI>

# Sensitivity — which companies are near the threshold boundary
python scripts/run_benchmark.py sensitivity <awards.parquet> --fy 2024
```

Rehearse against a real (or realistic fixture) awards file before the demo —
`tests/fixtures/follow_on_multiplier/sbir_awards.csv` is a starting point for
a dry run if production data isn't staged yet.

## 6. Where to go next

- Full research-question inventory and audience map:
  [research-questions.md](../research-questions.md)
- Milestone-by-milestone build status vs. the underlying research plan:
  [research-plan-alignment.md](../research-plan-alignment.md)
- Plain-English methodology explainer to leave behind: [sec-edgar-for-policy-makers.md](sec-edgar-for-policy-makers.md)
