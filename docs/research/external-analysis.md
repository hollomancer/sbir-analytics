---
Type: Guide
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-09-13
Status: active
---

**Prepared for:** maintainers and operators running an external research agent against a frozen study.

# External analysis

An external analysis provider is an execution backend. The study contract stays in
`studies/<id>/study.yaml`. The provider receives a frozen bundle and returns
exploratory artifacts. Those artifacts cannot promote themselves to `validated`
or `citable`.

This path is operator-only. It is not a Dagster asset, not on a schedule, and
not part of normal CI.

## Why the result is exploratory

The provider is not the study. It does not pin a design, does not run blocking
asset checks, and is not deterministic. A rerun can change the prose even when
the bundle hashes match. Quote provider output only as exploratory working
material. Promotion is a separate, explicit study-contract change.

## Data-egress boundary

Nothing is uploaded unless the operator passes `--allow-external-upload`.
Without that flag the command fails before any network request.

The upload is the frozen bundle only: the named datasets, the generated
research-question and constraints files, an optional prompt, and
`manifest.json`. The command will not upload:

- `.env` files, credentials, API keys, or repository secrets
- the repository root
- Neo4j database directories
- unrequested `data/` or `data/raw/` trees

`EDISON_API_KEY` is read from the environment and is not written into
`manifest.json` or `run.json`.

## Install the Edison extra

Edison is optional. Do not add it to the normal `stack-dev` environment.

```bash
uv sync --extra edison
```

Create an API key on the Edison platform (Account → Profile → API Tokens) and
export it in the shell you will use:

```bash
export EDISON_API_KEY=...
```

## Run a study

```bash
uv run python scripts/research/run_external_analysis.py \
  --provider edison \
  --study phase-iii-census \
  --dataset path/to/cohort.parquet \
  --prompt studies/phase-iii-census/external_prompt.md \
  --allow-external-upload
```

`--dataset` can be repeated. `--prompt` defaults to
`studies/<id>/external_prompt.md` when that file exists. `--constraints`
replaces the default exploratory constraints file.

To freeze a bundle without contacting a provider:

```bash
uv run python scripts/research/run_external_analysis.py \
  --provider edison \
  --study phase-iii-census \
  --dataset path/to/cohort.parquet \
  --bundle-only
```

## What comes back

Results land at:

```text
studies/<study-id>/exploratory/external/<provider>/<run-id>/
    run.json
    prompt.md
    input_manifest.json
    analysis.ipynb
    report.md
    answer.md
    figures/
    bundle/
```

`run.json` records provider, executor, trajectory id, git commit, the bundle
manifest SHA-256, timestamps, `evidence_status: exploratory`, and
`citable: false`. Dataset copies under `bundle/data/` are local staging and
should not be committed.
