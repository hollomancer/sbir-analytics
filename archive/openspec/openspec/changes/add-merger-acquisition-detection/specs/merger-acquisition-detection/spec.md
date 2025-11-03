#ADDED Requirements


##Requirement: Detect M&A Events from Patent Assignment Changes

The system SHALL detect potential merger and acquisition (M&A) events by identifying when a patent previously assigned to an SBIR company is reassigned to a different company.

###Scenario: A patent is reassigned to a new company

- **GIVEN** a patent is assigned to "Company A", which is a known SBIR awardee
- **WHEN** the same patent is later assigned to "Company B"
- **THEN** the system SHALL create an M&A candidate event with "Company A" as the target and "Company B" as the acquirer.

### Requirement: Enrich M&A Events with External Data

The system SHALL enrich M&A candidate events with data from external sources to provide additional context and verification.

#### Scenario: An M&A event is enriched with SEC EDGAR data

- **GIVEN** an M&A candidate event
- **WHEN** the acquirer or target company is publicly traded
- **THEN** the system SHALL search the SEC EDGAR database for relevant filings (e.g., 8-K, S-4) and attach them to the event.

#### Scenario: An M&A event is enriched with news data

- **GIVEN** an M&A candidate event
- **WHEN** the system searches news APIs (GDELT, NewsAPI)
- **THEN** the system SHALL attach relevant news articles to the event.
