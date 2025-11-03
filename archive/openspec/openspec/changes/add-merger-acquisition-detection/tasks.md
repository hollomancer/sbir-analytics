#1. Implementation

- [x] 1.1 Define the data model for M&A events in `src/models/ma_models.py`.
- [x] 1.2 Create a new Dagster asset `company_mergers_and_acquisitions` in `src/assets/ma_detection.py`.
- [x] 1.3 Implement logic to join SBIR companies with patent assignor data.
- [x] 1.4 Implement logic to detect changes in patent assignees over time.
- [x] 1.5 Create M&A candidate events when a change is detected.

##SEC EDGAR Enrichment

- [x] 1.6 Evaluate SEC EDGAR API for M&A data.
- [ ] 1.7 Add enrichment capabilities using SEC EDGAR API.
- [ ] 1.8 Write unit tests for SEC EDGAR API enrichment.

### GDELT Enrichment

- [x] 1.9 Evaluate GDELT for M&A data.
- [ ] 1.10 Add enrichment capabilities using GDELT.
- [ ] 1.11 Write unit tests for GDELT enrichment.

### Wikidata Enrichment

- [x] 1.12 Evaluate Wikidata for M&A data.
- [ ] 1.13 Add enrichment capabilities using Wikidata.
- [ ] 1.14 Write unit tests for Wikidata enrichment.

### Storage and Integration Testing

- [ ] 1.15 Store the enriched M&A events.
- [x] 1.15.1 Store the unenriched M&A candidate events.
- [x] 1.16 Write unit tests for the M&A detection asset.
- [ ] 1.17 Write integration tests for the M&A detection pipeline.
- [ ] 1.18 Write integration tests for the enrichment pipeline.
