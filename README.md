# SBIR/STTR research instrument

**Prepared for:** SBIR program managers and policy analysts in Treasury, OMB,
JCT, and state economic-development offices

This repository builds and tests narrow claims about U.S. Small Business
Innovation Research (SBIR) and Small Business Technology Transfer (STTR) data.
It is a research instrument, not an official program database, a
commercialization platform, or a verified record of company outcomes.

Start with [STATUS.md](STATUS.md). It states which studies are approved
evidence, validated, reproducible, exploratory, or archived. Status comes from
a versioned study contract. A working pipeline, chart, citation, or large test
suite does not make a result approved evidence.

## The first public release candidate

The narrow front door is the
[SBA annual-report structural comparison](studies/sba-annual-report-structural-comparison/).
It covers all 632 award-count cells printed in FY2020 Table 18, FY2021 Table
18, and FY2022 Table 20 of the SBA Annual Reports. It compares those cells with
counts computed from an exact, pinned September 17, 2026 SBIR.gov export under
declared row, year, program, phase, and jurisdiction rules.

The candidate claim is:

> For all 632 award-count cells printed in FY2020 Table 18, FY2021 Table 18,
> and FY2022 Table 20, this study reports the differences between those
> published counts and counts computed from the pinned September 17, 2026
> SBIR.gov export under `EXPORT_ROW_V1`, `AWARD_YEAR_FIELD_V1`, and the frozen
> program, phase, and jurisdiction rules. A separate blinded-role
> implementation reproduced 1,264 of 1,264 count operands. The recorded
> interval is `[1.0, 1.0]` using the method `exact complete-population point
> interval; no sampling`.

The comparison contains 632 count cells: 276 are exact and 356 are unresolved.
Recomputed minus published counts sum to +333, while absolute cell differences
sum to 869. Of the 276 exact cells, 57 are zero versus zero. Among the 575 cells
where either source reports a nonzero count, 219 are exact. The unresolved
cells comprise 208 positive and 148 negative recomputed-minus-published
differences. These summaries are not an omitted-award estimate, a
source-correctness verdict, or a causal explanation.

One parsed export row counts once, `Award Year` supplies the year, and the study
does not deduplicate. Of 20,836 retained FY2020-FY2022 rows, one had blank
`State` and was excluded under the frozen rule; 20,835 rows were counted.
Sixty eligible jurisdiction/program/phase groups had no retained row and
received a recomputed count of zero.

The repository may approve that statement only after one final pinned review
authorizes the exact claim boundary. The public rendering passes its
byte-stable round-trip checks. The prospective fidelity validation passed at
1,264/1,264 with the point interval
`[1.0, 1.0]`. A substantive change to the claim, method, input, or limitation
requires renewed independent review. Until the approval review is recorded,
treat the packet as validated and not approved evidence.

This study does not reproduce the unavailable publication-era SBIR.gov export.
It does not certify either source as complete or correct. It does not claim
official-report equivalence, compare award dollars, measure commercialization
or program effects, validate M&A or private-capital links, or transfer trust to
other repository outputs.

Read [what this is](docs/public/what-this-is.md), the
[evidence-status guide](docs/public/evidence-status.md), and the
[reproduction guide](docs/public/reproducibility.md) before using a result. The
[generated public result](docs/public/sba-structural-comparison.md) is the
intended reader-facing page.

## Reproduce or challenge the candidate

The public path uses Python 3.11 or 3.12 and
[`uv`](https://docs.astral.sh/uv/). It does not require Docker, Neo4j, API keys,
or a running service. It downloads about 402 MB of public source files and
refuses any byte sequence that does not match the frozen source manifest.

```bash
git clone https://github.com/hollomancer/sbir-analytics
cd sbir-analytics
make install-core
make reproduce-sba-structural
```

The command retrieves the declared source bytes, verifies hashes, row counts,
page counts, and schema, rebuilds the count sidecar, reconciles the confirmatory
submission, and checks the public sidecar and Markdown byte-for-byte. When
citing the result, use an immutable release tag—not a moving branch—and verify the
checksums in its study packet. Citation identifies those immutable bytes; it
does not imply that the repository approved every substantive claim they contain.

To challenge the result, start with the
[study contract](studies/sba-annual-report-structural-comparison/study.yaml),
[source manifest](studies/sba-annual-report-structural-comparison/source-manifest.json),
[validation design](studies/sba-annual-report-structural-comparison/validation-design-v1.md),
and [count comparison](studies/sba-annual-report-structural-comparison/results/count-comparison.csv).
Each disagreement remains `unresolved` unless direct evidence supports a
narrower explanation.

## Evidence model

- **Approved evidence** means the study passed its prospective validation
  threshold and one pinned final review approved the manifest's bounded claims.
- **Validated, not approved** means the prospective test was run as frozen and
  its result is recorded, but final claim approval is absent.
- **Reproducible, not validated** means the inputs and implementation can be
  rerun, but validation is incomplete.
- **Exploratory** means hypothesis generation, candidate discovery,
  measurement development, or an unverified linkage.
- **Archived** means preserved for provenance, not maintained as a live
  evidence path.

Any immutable release may be cited for what it contains. Evidence status says
what claims the repository endorses; publication metadata, merge approval, and
operational materialization remain separate controls.

Content-addressed study artifacts and governed analytical files are
authoritative. DuckDB and Parquet hold analytical records. Neo4j is an optional,
derived read projection; publishing a graph cannot strengthen a claim.

## Experimental work

The repository also contains M&A discovery, Form D matching, transition
scoring, return-on-investment design, graph projections, and other research in
development. These paths remain useful for candidate generation and methods
work, but they are not evidence for commercialization outcomes. Their status is
listed explicitly in [STATUS.md](STATUS.md) and in each `study.yaml`.

For contributor details, see the [research-question inventory](docs/research-questions.md),
[study-contract rules](studies/README.md), and
[development guide](CONTRIBUTING.md). The
[repository map](docs/public/repository-map.md) states the purpose and evidence
relationship of every tracked top-level directory. The software is MIT
licensed. Research claims remain bounded by their study contracts and release
records.
