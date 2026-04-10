# Requirements Document

## Introduction

This feature implements a classification system to categorize SBIR companies as Product, Service, or Mixed firms based on their complete federal contract portfolio from USAspending. The system identifies SBIR award recipients, retrieves their full contract history from USAspending, and classifies their business orientation based on contract characteristics. The classification uses a minimal set of data fields (PSC, Contract Type, Pricing, Award Description, SBIR Phase) and applies rule-based logic at both the award level and company level to determine business orientation with confidence scoring.

## Glossary

- **System**: The Company Categorization System
- **PSC**: Product Service Code - a federal classification code (numeric codes indicate products, alphabetic codes indicate services)
- **Contract Type**: The type of contract (e.g., CPFF, Cost-Type, T&M, FFP)
- **Award**: A single federal contract or grant from USAspending
- **SBIR Award**: A Small Business Innovation Research or STTR award
- **Company**: An SBIR award recipient identified by UEI
- **USAspending**: Federal spending database containing all federal contracts and grants
- **Contract Portfolio**: The complete set of federal contracts from USAspending for a given company
- **Product Award**: An award classified as product-oriented based on PSC and other indicators
- **Service Award**: An award classified as service-oriented based on PSC and other indicators
- **R&D Award**: An award classified as research and development
- **Confidence Level**: Classification reliability based on number of awards (Low: <2, Medium: 2-5, High: >5)
- **PSC Family**: The first character or digit grouping of a PSC code

## Requirements

### Requirement 1

**User Story:** As a data analyst, I want to retrieve the complete federal contract portfolio for each SBIR company from USAspending, so that I can classify their business orientation based on their full revenue profile rather than just SBIR awards.

#### Acceptance Criteria

1. WHEN THE System receives an SBIR company identifier, THE System SHALL query USAspending for all contracts associated with the company UEI
2. WHEN THE System retrieves contracts from USAspending, THE System SHALL extract PSC code, Contract Type, Pricing, Award Description, and Award Amount for each contract
3. WHEN THE System retrieves contracts from USAspending, THE System SHALL identify which contracts are SBIR awards and record the SBIR Phase
4. WHEN THE System completes USAspending retrieval, THE System SHALL include both SBIR and non-SBIR contracts in the company portfolio
5. WHEN THE System encounters a company with no USAspending contracts, THE System SHALL classify the company as Uncertain

### Requirement 2

**User Story:** As a data analyst, I want to classify individual federal contracts as Product, Service, or R&D based on minimal data fields, so that I can understand the nature of each contract.

#### Acceptance Criteria

1. WHEN THE System receives an award with a numeric PSC code, THE System SHALL classify the award as Product
2. WHEN THE System receives an award with an alphabetic PSC code, THE System SHALL classify the award as Service
3. WHEN THE System receives an award with PSC code starting with "A" or "B", THE System SHALL classify the award as R&D
4. WHEN THE System receives an award with CPFF or Cost-Type contract type, THE System SHALL classify the award as Service
5. WHEN THE System receives an award with T&M pricing, THE System SHALL classify the award as Service

### Requirement 3

**User Story:** As a data analyst, I want to apply description-based inference to award classification, so that I can improve classification accuracy when explicit indicators suggest product orientation.

#### Acceptance Criteria

1. WHEN THE System receives an award with FFP pricing, THE System SHALL retain the PSC-based classification as the final classification
2. WHEN THE System receives an award description containing "prototype", THE System SHALL classify the award as Product
3. WHEN THE System receives an award description containing "hardware", THE System SHALL classify the award as Product
4. WHEN THE System receives an award description containing "device", THE System SHALL classify the award as Product
5. WHEN THE System applies description-based inference, THE System SHALL record the inference method in the classification metadata

### Requirement 4

**User Story:** As a data analyst, I want to adjust award classification for SBIR-specific characteristics, so that I can account for the research-oriented nature of SBIR Phase I and Phase II awards.

#### Acceptance Criteria

1. WHEN THE System receives an SBIR Phase I award, THE System SHALL classify the award as R&D
2. WHEN THE System receives an SBIR Phase II award, THE System SHALL classify the award as R&D
3. WHEN THE System receives an SBIR Phase I or Phase II award with numeric PSC code, THE System SHALL classify the award as Product
4. WHEN THE System classifies an SBIR award as R&D, THE System SHALL treat the award as Service for company-level aggregation
5. WHEN THE System processes SBIR Phase III awards, THE System SHALL apply standard award classification rules without SBIR adjustment

### Requirement 5

**User Story:** As a data analyst, I want to aggregate award classifications at the company level, so that I can determine each company's overall business orientation.

#### Acceptance Criteria

1. WHEN THE System aggregates awards for a company, THE System SHALL calculate the percentage of total award dollars from Product awards
2. WHEN THE System aggregates awards for a company, THE System SHALL calculate the percentage of total award dollars from Service and R&D awards combined
3. WHEN THE System calculates that Product awards represent 60 percent or more of total dollars, THE System SHALL classify the company as Product-leaning
4. WHEN THE System calculates that Service and R&D awards represent 60 percent or more of total dollars, THE System SHALL classify the company as Service-leaning
5. WHEN THE System calculates that neither Product nor Service categories reach 60 percent of total dollars, THE System SHALL classify the company as Mixed

### Requirement 6

**User Story:** As a data analyst, I want to assign confidence levels to company classifications, so that I can assess the reliability of each classification based on portfolio size.

#### Acceptance Criteria

1. WHEN THE System classifies a company with fewer than 2 awards, THE System SHALL assign a confidence level of Low
2. WHEN THE System classifies a company with 2 to 5 awards, THE System SHALL assign a confidence level of Medium
3. WHEN THE System classifies a company with more than 5 awards, THE System SHALL assign a confidence level of High
4. WHEN THE System assigns a confidence level, THE System SHALL record the total number of awards in the classification metadata
5. WHEN THE System classifies a company with fewer than 2 awards, THE System SHALL classify the company as Uncertain

### Requirement 7

**User Story:** As a data analyst, I want to apply override rules for edge cases, so that I can prevent misclassification of companies with unusual portfolio characteristics.

#### Acceptance Criteria

1. WHEN THE System identifies a company with awards spanning more than 6 distinct PSC families, THE System SHALL classify the company as Mixed
2. WHEN THE System applies the PSC family override, THE System SHALL record the number of PSC families in the classification metadata
3. WHEN THE System applies an override rule, THE System SHALL preserve the original calculated classification in the metadata
4. WHEN THE System applies multiple override rules, THE System SHALL record all applicable override reasons
5. WHEN THE System classifies a company as Uncertain due to insufficient awards, THE System SHALL not apply other override rules

### Requirement 8

**User Story:** As a data analyst, I want to generate classification output with complete metadata, so that I can audit and validate the classification results.

#### Acceptance Criteria

1. WHEN THE System completes company classification, THE System SHALL output the Product percentage for each company
2. WHEN THE System completes company classification, THE System SHALL output the Service percentage for each company
3. WHEN THE System completes company classification, THE System SHALL output the final classification label for each company
4. WHEN THE System completes company classification, THE System SHALL output the confidence level for each company
5. WHEN THE System completes company classification, THE System SHALL output the classification metadata including award count, PSC family count, and override reasons
