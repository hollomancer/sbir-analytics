# SBIR/STTR Commercialization Analytics

This is a personal research project about a fairly simple question: what happens
after a small business wins an SBIR or STTR award?

The public award record tells you who received the money and what they proposed
to do with it. It is much worse at telling you what happened next. Did the
company win a follow-on contract? File a patent? Raise private capital? Get
acquired? This repo is my attempt to piece together some of those outcomes from
public data.

## About this project (please read first)

- I work in the SBIR/STTR domain, but I am not a trained data scientist or ML
  engineer. What I bring to the project is the domain framing: which questions
  seem worth asking, how they connect to the policy literature, and what data
  might plausibly answer them.
- I built this with substantial help from Claude and Codex. I directed the work,
  made the research and design choices, and review the outputs, but a lot of the
  implementation was written and iterated with AI coding agents.
- This is a side project, not an agency product or a production service. Nothing
  here represents the position of any agency.

If you only read one other thing, make it
[docs/research-questions.md](docs/research-questions.md). That is the real heart
of the project. The pipeline is mostly scaffolding for chipping away at those
questions.

## Questions I'm trying to answer

SBIR/STTR is a roughly $4 billion-per-year federal program whose statutory goal
is *commercialization*—turning early-stage R&D into products, contracts, and
companies. Tracking what happens after Phase II is notoriously difficult, and
GAO has flagged the quality of Phase III data for years.

A few of the things I'm exploring:

- **Follow-on private investment.** Do SBIR awardees go on to raise private
  capital, and how much? SEC Form D filings provide one imperfect window into
  that question.
- **Mergers and acquisitions.** Which SBIR firms get acquired, by whom, and how
  long after their first award? This work looks for signals in SEC EDGAR filings.
- **Phase II to Phase III transition time.** How long does it take an awardee to
  land a follow-on federal contract, and how does that differ by agency or
  technology area?
- **Technology and patent links.** Which awards map to Critical and Emerging
  Technology areas, and which ones appear to have produced patents?
- **Economic and fiscal effects.** What can public input-output data tell us
  about the economic activity associated with award spending? This part is
  especially exploratory.

The [full list](docs/research-questions.md) is sourced and organized by policy
area. Some questions are much more answerable than others.

## What it actually does

Mechanically, this is an ETL pipeline. It pulls in several public datasets,
tries to figure out which records refer to the same company (the hard part), and
loads the resulting relationships into Neo4j and analytical files.

```text
Public sources                  Processing                 Outputs
──────────────                  ──────────                 ───────
SBIR.gov awards          ┐
USAspending contracts    │      extract → validate
USPTO patents            ├──►   → enrich (entity         ──►  Neo4j graph
SAM.gov entities         │        resolution) →               + DuckDB / files
SEC EDGAR filings        │      transform → load
BEA input-output tables  ┘      (orchestrated by Dagster)
```

- **Entity resolution** starts with identifiers such as UEI, CAGE, and DUNS,
  then falls back to fuzzy name matching. A company rarely uses exactly the same
  name everywhere.
- **The graph** connects firms, awards, contracts, patents, and capital events so
  they can be queried together.
- **The ML-ish pieces** live in `packages/sbir-ml/`. There is a CET classifier
  and a Phase II-to-III transition detector. Both are pragmatic research tools,
  not polished production models.

## Want to see something run?

The easiest end-to-end example builds a procurement-transition report from
small synthetic datasets committed to the repo. It does not need credentials,
Neo4j, or any external data.

```bash
make install

uv run python scripts/data/monthly_procurement_transition_report.py \
  --month 2026-06 \
  --awards examples/army_science_technology_awards.csv \
  --candidates examples/army_science_technology_candidates.csv \
  --opportunities examples/army_science_technology_opportunities.csv \
  --output-root /tmp/procurement-transition-example
```

The [walkthrough](examples/army-procurement-transition.md) explains what it is
doing, and the repo includes an [expected report](examples/army_science_technology_report.md)
for comparison. All of the companies, awards, opportunities, and judgments in
this example are made up. It demonstrates the workflow, not live acquisition
intelligence.

## How seriously should I take the results?

It depends on the result.

- The ingestion, entity-resolution, and graph-loading code is implemented, but
  running it on real data requires source downloads, credentials, and local
  services.
- The procurement-transition example above is a runnable demonstration built
  from synthetic data.
- The Phase III census is reproducible, but it is not yet validated or approved
  for citation. Its current record is in
  [studies/phase-iii-census](studies/phase-iii-census/study.yaml).
- The private-capital, M&A, and fiscal work is exploratory and data-dependent.

The repo uses [epistemic tiers](docs/steering/epistemic-tiers.md) to keep a useful
analysis from quietly turning into a stronger claim than the evidence supports.
That machinery can sound a little grand, but the basic idea is just: label what
you know, label what you do not, and do not confuse working code with validated
evidence.

## Running the full project

The project targets Python 3.11 and uses
[`uv`](https://github.com/astral-sh/uv) for dependency management.

```bash
git clone https://github.com/hollomancer/sbir-analytics
cd sbir-analytics
make install        # install the full local stack
make dev            # start Dagster at http://localhost:3000
```

Most data sources require an API key or a local bulk download. Copy
`.env.example` to `.env` and fill in what you have. You will also need a local
Neo4j instance to build the graph. The
[getting-started guide](docs/getting-started/README.md) has the longer version.

No real award corpus is committed here, so reproducing the analyses end to end
is a non-trivial setup job. `make install-core` installs only the reusable
`sbir_etl` library; it leaves out Dagster and the application packages.

Useful checks for a local checkout:

```bash
make test-unit
make lint
make lint-boundaries
make docs-check
```

Integration tests need local services. `make help` lists the available targets.

## Where things live

```text
sbir_etl/              Core ETL code
packages/
  sbir-analytics/      Dagster assets, jobs, and sensors
  sbir-graph/          Neo4j loaders
  sbir-ml/             CET and transition-detection models
config/                Shared settings and thresholds
docs/                  Research questions, methods, architecture, and operations
specs/                 Feature designs and status
studies/               Reproducible research contracts
notebooks/             Exploratory research
scripts/               One-off analysis and operational tools
examples/              Small demonstrations and synthetic inputs
tests/                 Unit, integration, functional, and end-to-end tests
```

If you want the technical tour, see the
[architecture overview](docs/architecture/detailed-overview.md).

## Honest limitations

- **Entity resolution is probabilistic.** Fuzzy matching creates false positives
  and misses. Those errors flow into everything downstream.
- **The underlying outcome data is incomplete.** Phase III records are a
  particular problem, so inferred transitions are estimates rather than an
  authoritative census.
- **Several analyses are pilots or partial.** Some use limited geographies,
  fallback assumptions, or literature values that have not been independently
  validated.
- **The ML components are approximate.** They have benchmark targets, but they
  are not rigorously evaluated production models.
- **Nothing here is peer-reviewed or official.** It is independent research I do
  on personal time.

## A few useful links

- [Research questions](docs/research-questions.md)
- [Research output status](docs/research/README.md)
- [Study contracts](studies/README.md)
- [Contributing](CONTRIBUTING.md)
- [Release history](CHANGELOG.md)
- [Versioning policy](docs/steering/versioning.md)

The project is available under the [MIT License](LICENSE).

## Acknowledgments

This work uses data and methods from the
[Bureau of Economic Analysis](https://apps.bea.gov/api/),
[stateior](https://github.com/USEPA/stateior),
[SEC EDGAR](https://efts.sec.gov), [SAM.gov](https://api.sam.gov), and the other
public and academic sources cited throughout the research-question inventory.
The embedding work uses
[ModernBERT-Embed](https://huggingface.co/nomic-ai/modernbert-embed-base).
