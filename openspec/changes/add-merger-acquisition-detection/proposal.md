## Why
Detecting merger and acquisition (M&A) activity involving SBIR awardee companies is crucial for understanding technology transition and commercialization pathways. This proposal outlines a new capability to identify potential M&A events by analyzing changes in patent assignment data and corroborating these signals with external news and financial data sources.

## What Changes
- **New Capability**: Introduce a new `merger-acquisition-detection` capability.
- **New Asset**: Create a `company_mergers_and_acquisitions` Dagster asset.
- **Data Enrichment**: Enrich M&A candidate events with data from SEC EDGAR, GDELT, and NewsAPI.
- **Data Model**: Define a new data model for M&A events.

## Impact
- **Affected Specs**: `merger-acquisition-detection` (new), `data-enrichment`
- **Affected Code**: `src/assets/`, `src/models/`
