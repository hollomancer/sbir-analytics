# Data Enrichment - Web Search Evaluation Delta

## ADDED Requirements

### Requirement: Web Search Provider Benchmarking
The enrichment framework SHALL benchmark any web search-based enrichment provider (SearXNG, Tavily, Brave Search API, Google Programmable Search, Perplexica, or future equivalents) before enabling it in production.

#### Scenario: Representative query suite
- **WHEN** evaluating a provider
- **THEN** the system SHALL execute a curated suite of ≥500 enrichment queries covering companies, principal investigators, commercialization events, and technology keywords
- **AND** the benchmark SHALL capture latency, HTTP status, snippet text, citation metadata, and response size for every query

#### Scenario: Quality and compliance scoring
- **WHEN** benchmark results are collected
- **THEN** the system SHALL score each provider for accuracy (precision/recall vs ground truth), citation quality, permissible use/compliance posture, and estimated cost per 1,000 queries
- **AND** providers that fail any go/no-go threshold (e.g., <70% precision, no citations, cost above configured cap) SHALL be marked “not approved” in the evaluation report

### Requirement: Structured Output Normalization
Benchmarking SHALL normalize provider outputs into a common schema that downstream enrichment logic can consume once a provider is approved.

#### Scenario: Provider response normalization
- **WHEN** a provider returns search results
- **THEN** the evaluation harness SHALL normalize each result into fields including `title`, `snippet`, `source_url`, `published_at`, `entity_type`, `confidence`, and `evidence_hash`
- **AND** the normalized records SHALL be persisted to `reports/search_enrichment_benchmark.jsonl` for reproducibility

### Requirement: Recommendation Artifacts
Each benchmark run SHALL emit documentation and machine-readable artifacts that summarize findings and integration recommendations.

#### Scenario: Benchmark report generation
- **WHEN** a benchmark run completes
- **THEN** a Markdown + JSON report SHALL be written under `reports/` detailing configuration, metrics, costs, compliance considerations, and recommended next steps for every provider
- **AND** the report SHALL call out which providers are approved for pilot integration, which require further review, and which are rejected
