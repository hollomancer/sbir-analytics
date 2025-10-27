## Context
This document outlines the technical design for detecting M&A activity involving SBIR companies. The primary signal for an M&A event is a change in the assignee of a patent previously held by an SBIR company. This signal will be enriched and verified using external data sources.

## Goals / Non-Goals
- **Goals**:
  - To create a reliable, automated system for detecting potential M&A events.
  - To provide enriched data that can be used to analyze technology transition pathways.
- **Non-Goals**:
  - To provide a definitive, 100% accurate list of all M&A events. The output of this system will be a list of *potential* M&A events that will require further human review.

## Decisions
- **Decision**: A new Dagster asset will be created to orchestrate the M&A detection process.
  - **Alternatives considered**: A standalone script. A Dagster asset is preferred for its integration with the existing data pipeline, scheduling, and monitoring capabilities.
- **Decision**: Fuzzy string matching will be used to link SBIR companies to patent assignors.
  - **Alternatives considered**: Using a unique company identifier. This is not feasible as there is no common identifier between the SBIR and USPTO datasets.
- **Decision**: The system will use a combination of free data sources for enrichment, including SEC EDGAR, GDELT, OpenCorporates, Wikidata, and publicly available news feeds.
  - **Alternatives considered**: Using paid data sources. Free sources are preferred to minimize operational costs.

## Risks / Trade-offs
- **Risk**: Fuzzy matching of company names may produce false positives and negatives.
  - **Mitigation**: The matching algorithm will be tunable, and the output will be clearly marked as a list of *potential* M&A events.
- **Risk**: The external APIs may be unreliable or change their schemas.
  - **Mitigation**: The code will be designed to be resilient to API failures, and the API clients will be encapsulated to make them easy to update.

## Migration Plan
This is a new capability, so no migration is required.

## Open Questions
- What is the best fuzzy matching algorithm and threshold to use for linking company names?
- What are the usage limits, rate limits, and terms of service for the free external APIs?
