# SBIR/STTR research instrument

This is a personal research project about what happens after a small business
wins an SBIR or STTR award.

The public award record tells you who received the money and what they proposed
to do with it, but it is much worse at telling you what happened next. This repo
builds and tests narrow claims about U.S. Small Business Innovation Research
(SBIR) and Small Business Technology Transfer (STTR) data.

## About this project

- I work in the SBIR/STTR domain, but I am not a trained data scientist or ML
  engineer. I am focused on which questions seem worth asking, how they connect
  to the policy literature, and what data might plausibly answer them.
- I built this with substantial help from Claude and Codex. I directed the work,
  made the research and design choices, and review the outputs, but a lot of the
  implementation was written and iterated with AI coding agents.
- This is a side project. Nothing here represents the position of any agency.

[STATUS.md](STATUS.md) states which studies are citable, reproducible but not
citable, exploratory, or archived. Status comes from a versioned study contract.


Read [what this is](docs/public/what-this-is.md), the
[evidence-status guide](docs/public/evidence-status.md), and the
[reproduction guide](docs/public/reproducibility.md) before using a result. The
[generated public result](docs/public/sba-structural-comparison.md) is the
intended reader-facing page.

## Reproduce or challenge the candidate

The public path uses Python 3.11 or 3.12 and
[`uv`](https://docs.astral.sh/uv/). It does not require Docker, API keys, or a
running service. It downloads about 402 MB of public source files and
refuses any byte sequence that does not match the frozen source manifest.

```bash
git clone https://github.com/hollomancer/sbir-analytics
cd sbir-analytics
git checkout v0.18.0
make install-core
make reproduce-sba-structural
```

The command must run from the tagged study checkout; moving `main` deliberately
does not rewrite the released environment lock. It retrieves the declared
source bytes, verifies hashes, row counts,
page counts, and schema, rebuilds the count sidecar, reconciles the confirmatory
submission, and checks the public sidecar and Markdown byte-for-byte. After a
citable release exists, use the release tag—not a moving branch—and verify the
checksums in its study packet.

To challenge the result, start with the
[study contract](studies/sba-annual-report-structural-comparison/study.yaml),
[source manifest](studies/sba-annual-report-structural-comparison/source-manifest.json),
[validation design](studies/sba-annual-report-structural-comparison/validation-design-v1.md),
and [count comparison](studies/sba-annual-report-structural-comparison/results/count-comparison.csv).
Each disagreement remains `unresolved` unless direct evidence supports a
narrower explanation.

## Evidence model

- **Citable** means a tagged study release has frozen sources, a declared
  estimand, a passed prospective validation, an open materialization gate, and
  completed evidence and outside-reader reviews.
- **Validated, not citable** means the prospective test was run as frozen and
  its result is recorded, but publication or release gates remain closed.
- **Reproducible, not citable** means the inputs and implementation can be
  rerun, but a public claim is still blocked.
- **Exploratory** means hypothesis generation, candidate discovery,
  measurement development, or an unverified linkage.
- **Archived** means preserved for provenance, not maintained as a live
  evidence path.

Content-addressed study artifacts and governed analytical files are
authoritative. DuckDB and Parquet hold analytical records. A mutable service
database is not part of the evidence boundary.

## Future work

The repository also contains M&A discovery, Form D matching, transition
scoring, return-on-investment design, and other research in development. These
paths remain useful for candidate generation and methods
work, but they are not evidence for commercialization outcomes. Their status is
listed explicitly in [STATUS.md](STATUS.md) and in each `study.yaml`.

For contributor details, see the [research-question inventory](docs/research-questions.md),
[study-contract rules](studies/README.md), and
[development guide](CONTRIBUTING.md). The
[repository map](docs/public/repository-map.md) states the purpose and evidence
relationship of every tracked top-level directory. The software is MIT
licensed. Research claims remain bounded by their study contracts and release
records.

## Limitations

- **Entity resolution is probabilistic.** Fuzzy matching creates false positives
  and misses. Those errors flow into everything downstream.
- **Underlying outcome data is incomplete.** Phase III records are a particular problem,
  so inferred transitions are estimates rather than an authoritative census.
- **Nothing here is peer-reviewed or official.** It is independent research I do
  on personal time.
