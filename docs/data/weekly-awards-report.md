# Weekly Awards Report

Generates a Markdown digest of recently-posted SBIR/STTR awards, optionally
enriched with LLM-written synopses, company/PI diligence, and web research.
Code lives in `sbir_etl/reporting/weekly/`; the entry point is
`scripts/data/weekly_awards_report.py`.

> `scripts/data/run_weekly_workflow_local.sh` is a legacy local validation helper. It does not
> generate this report and does not mirror a current GitHub Actions workflow.

On the live host this report is wrapped by the Dagster `weekly_awards_report_job`. Its
`weekly_awards_report` schedule defaults to Mondays at 12:00 UTC and is stopped until explicitly
enabled after a successful manual run.

## Run it

```bash
# Full report (last 7 days) to a file
OPENAI_API_KEY=sk-... uv run python scripts/data/weekly_awards_report.py --output weekly.md

# No LLM calls at all (fast, deterministic)
uv run python scripts/data/weekly_awards_report.py --no-ai --output weekly.md
```

## Arguments

| Flag | Default | Meaning |
|------|---------|---------|
| `--days N` | 7 | Look-back window |
| `--output PATH` | stdout | Markdown output file |
| `--no-ai` | off | Skip all LLM generation |
| `--no-company-research` | off | Skip web research (keeps synopsis/descriptions) |
| `--no-diligence` | off | Skip company + PI diligence paragraphs |
| `--skip-sbir-api` | env `SKIP_SBIR_API` | Skip SBIR.gov API calls |
| `--timeout SEC` | 720 (env `REPORT_TIMEOUT`) | Hard pipeline timeout |
| `--debug` | off | Verbose diagnostics to stderr |

## Credentials & tuning (env vars)

| Var | Default | Purpose |
|-----|---------|---------|
| `OPENAI_API_KEY` | *(required for AI)* | OpenAI key; if unset, AI stages skip with a warning |
| `MAX_COMPANIES_TO_RESEARCH` | 50 | Cap on web-researched companies |
| `MAX_AWARDS_TO_DESCRIBE` | 100 | Cap on LLM award descriptions |
| `MAX_COMPANIES_TO_DILIGENCE` | 50 | Cap on company diligence paragraphs |
| `MAX_PIS_TO_DILIGENCE` | 50 | Cap on PI diligence paragraphs |
| `OPENAI_MAX_CONCURRENT` | 4 | Concurrent OpenAI requests |

Models: descriptions/synopses use `gpt-4.1-mini`; diligence uses `gpt-4.1`. Optional
enrichment credentials (`SAM_GOV_API_KEY`, plus keyless USASpending / OpenCorporates /
press-wire feeds) improve diligence but degrade gracefully — see the
[enricher catalog](../enrichment/enricher-catalog.md).

## Input / output

- **Input:** the newest local SBIR awards CSV when available, otherwise a direct SBIR.gov bulk
  download, filtered to the look-back window.
- **Output:** a single Markdown document written to `--output` (or stdout).

Live reports are written under `<data_root>/reports/weekly_awards/<report-date>/`. See the
[Mac mini runbook](../deployment/mac-mini-server.md#scheduled-analysis-and-reporting) before
operating the live job.
