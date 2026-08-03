---
Type: Runbook
Owner: engineering@project
Last-Reviewed: 2026-08-03
Status: active
---

# Performance Measurement

Performance claims are meaningful only with a named workload, data cut or generated sample,
hardware, configuration, and output artifact. This page documents how to measure; it does not
preserve changing benchmark numbers in prose.

## Available tools

| Tool | Purpose | Typical output |
| --- | --- | --- |
| `benchmark_enrichment.py` | Generated enrichment workload and optional baseline comparison | `reports/benchmarks/*.json` |
| `benchmark_transition_detection.py` | Generated transition-scoring throughput | `reports/benchmarks/transition_detection_*.json` |
| `profile_cet_performance.py` | CET inference throughput by sample and batch size | caller-selected JSON and Markdown |
| `profile_sbir_performance.py` | SBIR processing profile | `metrics/sbir_performance_report.json` |
| `profile_usaspending_dump.py` | Local archive/dump profiling | caller-selected JSON and summary |
| `detect_performance_regression.py` | Enrichment run compared with a supplied baseline | optional JSON, Markdown, or HTML |

Inspect each script's `--help` before running it. Profilers may require local data, models, or
substantial disk; none is a routine GitHub Actions job.

## Reproducible procedure

1. Record the git commit, Python version, machine/CPU/RAM, and relevant configuration.
2. Choose a representative but bounded sample. Use the same sample and concurrency for comparison.
3. Run a warm-up when caches or model initialization materially affect timing.
4. Write results to a dated JSON artifact instead of copying numbers into this page.
5. Compare time, peak memory, throughput, and output quality. A faster run with a lower match or
   classification rate is not automatically an improvement.
6. Promote a new baseline only after reviewing both the code change and measurement conditions.

Example generated workloads:

```bash
uv run python scripts/performance/benchmark_enrichment.py \
  --sample-size 1000 \
  --output reports/benchmarks/enrichment-local.json

uv run python scripts/performance/benchmark_transition_detection.py \
  --sample-size 5000 \
  --output reports/benchmarks/transition-local.json
```

Compare enrichment against an explicit baseline:

```bash
uv run python scripts/performance/detect_performance_regression.py \
  --sample-size 1000 \
  --baseline reports/benchmarks/baseline.json \
  --output-json reports/benchmarks/regression.json \
  --output-markdown reports/benchmarks/regression.md
```

The repository does not commit a universal `reports/benchmarks/baseline.json`. A local file at that
path is useful only when its provenance and hardware match the comparison. Do not interpret the
script's default path as an official baseline.

## Live-server boundary

Heavy assets on the Mac mini are manual and capacity-gated. Check current container limits and
follow [Heavy assets](deployment/mac-mini-server.md#heavy-assets) before profiling there. Never run
a benchmark from the development checkout against the live graph or overwrite live source data.

## Reporting results

A durable benchmark report should include:

- command and commit;
- sample construction or data vintage and hash;
- hardware and runtime configuration;
- wall time, peak memory, throughput, and relevant quality metric;
- comparison baseline with the same fields;
- raw JSON artifact location.

Move superseded narrative benchmarks under `docs/archive/performance/`. Keep the live runbook free
of hardware-specific headline numbers.
