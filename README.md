# SBIR/STTR Commercialization Analytics

[![CI](https://github.com/hollomancer/sbir-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/hollomancer/sbir-analytics/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A research project linking federal SBIR/STTR award data to
downstream commercialization signals (federal contracts,
patents, private financing, and acquisitions) to better
understand what happens after a small business wins an SBIR award.

## My role and use of AI

- Defined the research agenda and functional requirements, starting with the
  policy questions in [docs/research-questions.md](docs/research-questions.md).
- Selected public data sources and specified the entity-linkage, analytical,
  and reporting methods used to investigate those questions.
- Set evidence and validation boundaries, including what the outputs can and
  cannot support.
- Used Claude and Codex extensively to implement and iterate on the software,
  then reviewed the work through tests, reproducibility checks, and documented
  evidence limits.

This is independent research software developed on personal time. It is not an
agency product or a production service, and its findings do not represent the
position of any agency.

## See it work

The fastest end-to-end example is a deterministic Army procurement-transition
packet built entirely from committed synthetic data:

Run `make install` from the repository root first; `make install-core` omits the
`sbir_ml` package used by this example.

```bash
uv run python scripts/data/monthly_procurement_transition_report.py \
  --month 2026-06 \
  --awards examples/army_science_technology_awards.csv \
  --candidates examples/army_science_technology_candidates.csv \
  --opportunities examples/army_science_technology_opportunities.csv \
  --output-root /tmp/procurement-transition-example
```

Read the [example walkthrough](examples/army-procurement-transition.md)
and compare the result with the committed
[expected report](examples/army_science_technology_report.md). Every company,
award, opportunity, and judgment in this example is synthetic; it demonstrates
the workflow and evidence trail, not live acquisition intelligence.

The repository separates software capability from evidentiary maturity:

| Capability | Current status | Evidence or boundary |
| --- | --- | --- |
| Procurement-transition reporting | Exploratory; runnable synthetic demonstration | [Synthetic example and expected output](examples/army-procurement-transition.md) |
| Award ingestion, entity resolution, and graph loading | Implemented; real-data setup required | Operational capability, not an evidence claim; see the [getting-started guide](docs/getting-started/README.md) and [architecture](docs/architecture/detailed-overview.md) |
| Phase III outcome analysis | Reproducible; not validated or approved for citation | [Phase III census study record](studies/phase-iii-census/study.yaml) |
| Private-capital, M&A, and fiscal analyses | Exploratory and data-dependent | [Research output status index](docs/research/README.md) and the limitations below |

## Questions I'm trying to answer

SBIR/STTR is a ~$4B/year federal program whose statutory goal is
*commercialization* — turning early-stage R&D awards into products, contracts,
and companies. But the program's own tracking of what happens after Phase II has
challenges (GAO has flagged Phase III data as unreliable for years). This project
is an attempt to reconstruct those outcomes by joining the public award
record to other public datasets. A few of the questions it explores:

- **Follow-on private investment.** Do SBIR awardees go on to raise private
  capital, and how much? This uses **SEC Form D** (Regulation D exempt-offering
  notices) to build a private financing profile for awardee firms, and compares
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
- **Economic & fiscal impact.** Rough exploratory estimates of tax receipts and
  economic activity attributable to award spending, using BEA input-output tables
  where available and fallback assumptions when live BEA inputs are unavailable.

The full, sourced inventory in
[docs/research-questions.md](docs/research-questions.md) is the heart of the
project: the code and studies exist to investigate and validate those questions.

## What it actually does

At a mechanical level, this is an ETL pipeline that ingests several public
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
  still being actively worked on.

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
specs/                 Per-feature design notes; status.md is the lifecycle registry
studies/               Versioned contracts for reproducible, citable research
tests/                 Unit, integration, functional, and end-to-end suites
examples/              Standalone demo scripts (see examples/README.md)
notebooks/             Notebook-first research workbench and reusable examples
scripts/               One-off analysis and operational scripts (exploratory tier)
```

The live deployment runs Docker Compose behind Tailscale.
See the [deployment overview](docs/deployment/README.md) for the current model.

## Suggested reading path

If you want the fastest route to the domain insight without reading the whole
repository, start with these documents in order:

1. [Research questions](docs/research-questions.md): the core policy and
   evaluation questions the project is trying to answer.
2. [Army procurement-transition example](examples/army-procurement-transition.md):
   a runnable vertical slice with synthetic inputs and a committed expected report.
3. [Epistemic tiers](docs/steering/epistemic-tiers.md): the contract that decides
   what each artifact in this repository is allowed to claim, and what it costs
   to move a result from exploratory to citable.
4. [Study contracts](studies/README.md): how the project distinguishes exploratory,
   reproducible, validated, and citable work.
5. [SEC EDGAR SBIR learnings](docs/research/sec-edgar-sbir-learnings.md):
   practical findings from using EDGAR to detect SBIR-related exits and
   financing signals.
6. [SBIR Form D fundraising analysis](docs/research/sbir-form-d-fundraising-analysis.md):
   the private-capital lens on awardee commercialization.
7. [Phase transition latency](docs/phase-transition-latency.md): how the repo
   thinks about timing from SBIR awards to follow-on federal contracts.
8. [SBIR identification methodology](docs/sbir-identification-methodology.md):
   the methodology behind identifying and linking SBIR firms across datasets.

## Running it

The project targets **Python 3.11** and uses
[`uv`](https://github.com/astral-sh/uv) for
dependency management. There is intentionally no `requirements.txt` — the
dependency set is defined by `pyproject.toml` and pinned in `uv.lock`. (If you
need a flat list, run `uv export`.)

```bash
git clone https://github.com/hollomancer/sbir-analytics
cd sbir-analytics
make install        # install the full local stack with uv
make dev            # start the Dagster UI at http://localhost:3000
```

`make install-core` installs only the reusable `sbir_etl` library dependencies;
it does not install Dagster or the application packages. `make help` lists every
available target. Most data sources need an API key or a
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

### Verifying a checkout

None of these need credentials, network access, or Neo4j — they run against a
fresh clone and are the same gates CI enforces:

```bash
make install          # uv sync --extra stack-dev
make test-unit        # ~5,800 unit tests, under a minute
make lint             # Ruff across the repository, MyPy over sbir_etl
make lint-boundaries  # architecture, epistemic-tier, config, and study guards
make docs-check       # dead doc links, stale commands, spec-registry coverage
```

The remaining suites need services: `uv run pytest -m integration` expects a
local Neo4j (`make neo4j-up`), and `make docker-e2e` drives the full stack.

## Versioning

The repository follows [Semantic Versioning 2.0.0](https://semver.org/) with synchronized
versions for the root ETL project and the three packages under `packages/`. Git release tags use
the form `vMAJOR.MINOR.PATCH`. See the [versioning and release policy](docs/steering/versioning.md)
for compatibility boundaries, increment rules, and the release checklist, and
[CHANGELOG.md](CHANGELOG.md) for what has landed in each release.

## Limitations

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

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) for the local
workflow and review expectations.

## Acknowledgments

- [BEA API](https://apps.bea.gov/api/) — Bureau of Economic Analysis input-output tables
- [stateior](https://github.com/USEPA/stateior) — EPA state-level I-O model
- [ModernBERT-Embed](https://huggingface.co/nomic-ai/modernbert-embed-base) — Nomic AI embedding model
- [SEC EDGAR EFTS](https://efts.sec.gov) — SEC full-text filing search
- [SAM.gov Data Services](https://api.sam.gov) — federal entity registration data
- The GAO, NASEM, CRS, and academic studies cited throughout [docs/research-questions.md](docs/research-questions.md)
