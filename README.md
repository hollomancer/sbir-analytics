# SBIR/STTR Commercialization Analytics

A personal research project that links federal SBIR/STTR award data to
downstream commercialization signals — federal contracts, patents, private
investment, and acquisitions — to ask better questions about what happens
after a small business wins an SBIR award.

## About this project (please read first)

This is a **personal side project, not production software, and not a polished
engineering portfolio piece.** A few things to set expectations honestly:

- I'm a **federal program manager working in the SBIR/STTR domain** — not a
  trained data scientist or ML engineer. My contribution here is the domain
  framing: which questions are worth asking, how they map to the policy and
  academic literature, and what data could plausibly answer them.
- I built it with **substantial help from AI coding assistants.** Much of the
  implementation was generated and iterated with AI; I directed the design and
  validated the analysis, but I would not represent the code as professional-grade
  engineering.
- The value I'd point a reader to is **[docs/research-questions.md](docs/research-questions.md)** —
  a structured inventory of the questions this project exists to answer, each
  tied to the relevant GAO/NASEM/CRS reports and peer-reviewed studies. That
  document is the heart of the project; the pipeline is the scaffolding I built
  to chip away at it.

Read this as an exploration by a domain practitioner, not a finished product.

## The questions it tries to answer

SBIR/STTR is a ~$4B/year federal program whose statutory goal is
*commercialization* — turning early-stage R&D awards into products, contracts,
and companies. But the program's own tracking of what happens after Phase II is
famously thin (GAO has flagged Phase III data as unreliable for years). This
project is an attempt to reconstruct those outcomes by joining the public award
record to other public datasets. A few of the questions it explores:

- **Follow-on private investment.** Do SBIR awardees go on to raise private
  capital, and how much? This uses **SEC Form D** (Regulation D exempt-offering
  notices) to build a private-financing profile for awardee firms, and compares
  it against the SBIR funding they received.
- **Mergers & acquisitions / exits.** Which SBIR firms get acquired, by whom,
  and how long after their first award? This detects M&A events from **SEC EDGAR
  filings** (8-K and Form D full-text search) and looks at patterns by funding
  agency (e.g. biotech vs. defense) and acquirer type.
- **Phase II → Phase III transition latency.** How long does it take an awardee
  to go from finishing Phase II to landing a first follow-on federal contract,
  and how does that vary by agency and technology area?
- **Technology classification & patent linkage.** Which awards map to
  Critical & Emerging Technology (CET) areas, and which awards produced patents?
- **Economic & fiscal impact.** Rough estimates of tax receipts and economic
  activity attributable to award spending, using BEA input-output tables.

The full, sourced inventory — organized by policy area and complexity tier — is
in [docs/research-questions.md](docs/research-questions.md).

## What it actually does

At a mechanical level, it's an ETL pipeline that ingests several public
datasets, resolves them to common entities (the hard part — companies appear
under different names and identifiers across sources), and loads the result into
a graph so the relationships can be queried.

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

- **Entity resolution** cascades through UEI → CAGE → DUNS → fuzzy-name matching
  to decide when an SBIR recipient is the same firm that later won a contract,
  filed a patent, or raised capital.
- **Graph model (Neo4j).** Awards, firms, contracts, patents, and capital events
  become nodes and edges, which is what makes the cross-dataset questions above
  expressible as queries.
- **A couple of ML/heuristic components** live in `packages/sbir-ml/`: a CET
  technology classifier and a Phase II→III transition detector. These are
  approximate — see limitations.

## Repository structure

```text
sbir_etl/              Core ETL library: extractors, enrichers, transformers,
                       validators, models, config, quality, utils
packages/
  sbir-analytics/      Dagster assets, jobs, and sensors (orchestration)
  sbir-graph/          Neo4j loaders
  sbir-ml/             CET classifier and transition-detection models
config/                Thresholds, paths, performance settings (base.yaml)
docs/                  research-questions.md (start here), architecture, methodology
specs/                 Per-feature design notes
examples/              Standalone demo scripts
notebooks/             Exploratory Jupyter notebooks
scripts/               One-off analysis and operational scripts
infrastructure/        AWS CDK deployment (my personal cloud setup; optional)
```

Directories such as `.github/`, `infrastructure/`, deployment docs, and E2E
testing docs reflect experiments in making the project more runnable and
maintainable. They should not be read as a claim that this repository contains
production-grade infrastructure, and they should not be deleted or restructured
without explicit approval.

## Running it

The project uses **Python 3.11** and [`uv`](https://github.com/astral-sh/uv) for
dependency management. There is intentionally no `requirements.txt` — the
dependency set is defined by `pyproject.toml` and pinned in `uv.lock`. (If you
need a flat list, run `uv export`.)

```bash
git clone https://github.com/hollomancer/sbir-analytics
cd sbir-analytics
make install        # install dependencies with uv
make dev            # start the Dagster UI at http://localhost:3000
```

`make help` lists every available target. Most data sources need an API key or a
local bulk download; copy `.env.example` to `.env` and fill in what you have.
A local Neo4j instance is required to materialize the graph — `docker compose --profile dev up`
brings one up along with the supporting services. See
[docs/getting-started/](docs/getting-started/README.md) for a fuller walkthrough.

> **Note on data and reproducibility.** No award data is committed to this repo
> (only a small NAICS→BEA reference table). Reproducing the analyses end-to-end
> means downloading the source datasets yourself and supplying your own API
> credentials, which is a non-trivial amount of setup. Core components are
> designed to run locally, but full end-to-end reproduction requires source-data
> downloads, API credentials, and local services such as Neo4j.

## Honest limitations

- **Entity resolution is probabilistic.** Cross-dataset matches use fuzzy logic
  and will include false positives and misses. Match rates and confidence are
  tracked but not perfect, and they bound the reliability of everything
  downstream.
- **Several analyses are pilots or partial.** For example, the UCC-1
  secured-debt work was a California-only pilot; some literature benchmarks
  (NASEM leverage ratios, Howell's VC findings) are *targets to reproduce*, and
  the reproductions are approximate rather than validated replications.
- **Phase III / transition data is known to be unreliable** at the source (GAO
  has documented this). This project infers transitions rather than reading them
  from authoritative records, so the numbers are estimates.
- **The ML components are approximate.** The CET classifier and transition
  detector are pragmatic heuristics with a target precision benchmark, not
  rigorously evaluated production models.
- **Nothing here is peer-reviewed or official.** This reflects my own analysis
  on personal time and does not represent the position of any agency.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2025 Conrad Hollomon.

## Acknowledgments

- [BEA API](https://apps.bea.gov/api/) — Bureau of Economic Analysis input-output tables
- [stateior](https://github.com/USEPA/stateior) — EPA state-level I-O model
- [ModernBERT-Embed](https://huggingface.co/nomic-ai/modernbert-embed-base) — Nomic AI embedding model
- [SEC EDGAR EFTS](https://efts.sec.gov) — SEC full-text filing search
- [SAM.gov Data Services](https://api.sam.gov) — federal entity registration data
- The GAO, NASEM, CRS, and academic studies cited throughout [docs/research-questions.md](docs/research-questions.md)
