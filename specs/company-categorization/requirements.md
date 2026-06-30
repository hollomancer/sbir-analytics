# Company Categorization — Requirements

> **Status:** 77% complete.
> Anchors inventory question **B1** in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B1 — product / service / mixed-mode firm classification
**Answers for:** SBIR program managers, policy analysts (§638(qq)(3) compliance review)
**Complexity tier:** Descriptive (Tier 1)

---

## Done when

> An analyst can state: "Of the N SBIR companies in the pipeline, X% are product-leaning,
> Y% service-leaning, Z% mixed, with high-confidence classifications covering NN% of
> award dollars. Product-leaning firms show a [higher / lower] Phase II→III transition
> rate relative to service-leaning firms."
>
> The output must be queryable by CET area, agency, and confidence tier so that
> orientation can be used as a covariate in transition and benchmark analyses.

---

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

---

## Requirements

### Requirement 1

**User Story:** As an SBIR program manager evaluating firm commercialization history,
I want to retrieve the complete federal contract portfolio for each SBIR company from
USAspending, so that classification reflects the firm's full federal revenue profile —
not just SBIR awards — and can support §638(qq)(3) benchmark evaluation and
transition-effectiveness comparisons.

#### Acceptance Criteria

1. WHEN THE System receives an SBIR company identifier, THE System SHALL query USAspending for all contracts associated with the company UEI
2. WHEN THE System retrieves contracts from USAspending, THE System SHALL extract PSC code, Contract Type, Pricing, Award Description, and Award Amount for each contract
3. WHEN THE System retrieves contracts from USAspending, THE System SHALL identify which contracts are SBIR awards and record the SBIR Phase
4. WHEN THE System completes USAspending retrieval, THE System SHALL include both SBIR and non-SBIR contracts in the company portfolio
5. WHEN THE System encounters a company with no USAspending contracts, THE System SHALL classify the company as Uncertain

### Requirement 2

**User Story:** As a pipeline engineer building award-level classification logic, I want
to classify individual federal contracts as Product, Service, or R&D from PSC and
contract-type fields alone, so that company-level orientation rests on a consistent,
auditable per-award classification that does not require manual review.

#### Acceptance Criteria

1. WHEN THE System receives an award with a numeric PSC code, THE System SHALL classify the award as Product
2. WHEN THE System receives an award with an alphabetic PSC code, THE System SHALL classify the award as Service
3. WHEN THE System receives an award with PSC code starting with "A" or "B", THE System SHALL classify the award as R&D
4. WHEN THE System receives an award with CPFF or Cost-Type contract type, THE System SHALL classify the award as Service
5. WHEN THE System receives an award with T&M pricing, THE System SHALL classify the award as Service

### Requirement 3

**User Story:** As a pipeline engineer improving classification signal coverage, I want
to apply description-based keyword inference when PSC signals are ambiguous, so that
prototype, hardware, and device awards are correctly labeled rather than defaulting to
service classification.

#### Acceptance Criteria

1. WHEN THE System receives an award with FFP pricing, THE System SHALL retain the PSC-based classification as the final classification
2. WHEN THE System receives an award description containing "prototype", THE System SHALL classify the award as Product
3. WHEN THE System receives an award description containing "hardware", THE System SHALL classify the award as Product
4. WHEN THE System receives an award description containing "device", THE System SHALL classify the award as Product
5. WHEN THE System applies description-based inference, THE System SHALL record the inference method in the classification metadata

### Requirement 4

**User Story:** As a pipeline engineer preserving the integrity of SBIR-phase signals,
I want to override award classification for Phase I and II awards, so that early-stage
R&D contracts do not inflate a firm's product count and misrepresent its commercial
orientation.

#### Acceptance Criteria

1. WHEN THE System receives an SBIR Phase I award, THE System SHALL classify the award as R&D
2. WHEN THE System receives an SBIR Phase II award, THE System SHALL classify the award as R&D
3. WHEN THE System receives an SBIR Phase I or Phase II award with numeric PSC code, THE System SHALL classify the award as Product
4. WHEN THE System classifies an SBIR award as R&D, THE System SHALL treat the award as Service for company-level aggregation
5. WHEN THE System processes SBIR Phase III awards, THE System SHALL apply standard award classification rules without SBIR adjustment

### Requirement 5

**User Story:** As an SBIR program manager comparing firm orientations across the
portfolio, I want award classifications rolled up to a company-level product / service /
mixed label, so that I can correlate orientation with transition rates and exit outcomes
and identify whether product-leaning firms systematically outperform service-leaning ones.

#### Acceptance Criteria

1. WHEN THE System aggregates awards for a company, THE System SHALL calculate the percentage of total award dollars from Product awards
2. WHEN THE System aggregates awards for a company, THE System SHALL calculate the percentage of total award dollars from Service and R&D awards combined
3. WHEN THE System calculates that Product awards represent 60 percent or more of total dollars, THE System SHALL classify the company as Product-leaning
4. WHEN THE System calculates that Service and R&D awards represent 60 percent or more of total dollars, THE System SHALL classify the company as Service-leaning
5. WHEN THE System calculates that neither Product nor Service categories reach 60 percent of total dollars, THE System SHALL classify the company as Mixed

### Requirement 6

**User Story:** As a policy analyst preparing a briefing, I want confidence levels
assigned to company classifications, so that thin-portfolio results are clearly marked
and not cited alongside high-confidence findings in published reports.

#### Acceptance Criteria

1. WHEN THE System classifies a company with fewer than 2 awards, THE System SHALL assign a confidence level of Low
2. WHEN THE System classifies a company with 2 to 5 awards, THE System SHALL assign a confidence level of Medium
3. WHEN THE System classifies a company with more than 5 awards, THE System SHALL assign a confidence level of High
4. WHEN THE System assigns a confidence level, THE System SHALL record the total number of awards in the classification metadata
5. WHEN THE System classifies a company with fewer than 2 awards, THE System SHALL classify the company as Uncertain

### Requirement 7

**User Story:** As a pipeline engineer preventing misclassification of edge-case firms,
I want override rules for highly diversified portfolios, so that firms spanning many PSC
families are not misleadingly labeled by a narrow-category majority.

#### Acceptance Criteria

1. WHEN THE System identifies a company with awards spanning more than 6 distinct PSC families, THE System SHALL classify the company as Mixed
2. WHEN THE System applies the PSC family override, THE System SHALL record the number of PSC families in the classification metadata
3. WHEN THE System applies an override rule, THE System SHALL preserve the original calculated classification in the metadata
4. WHEN THE System applies multiple override rules, THE System SHALL record all applicable override reasons
5. WHEN THE System classifies a company as Uncertain due to insufficient awards, THE System SHALL not apply other override rules

### Requirement 8

**User Story:** As a pipeline engineer maintaining classification transparency, I want
full metadata emitted with each company classification, so that any result can be traced
back to its source awards, PSC families, and override reasons for audit or validation.

#### Acceptance Criteria

1. WHEN THE System completes company classification, THE System SHALL output the Product percentage for each company
2. WHEN THE System completes company classification, THE System SHALL output the Service percentage for each company
3. WHEN THE System completes company classification, THE System SHALL output the final classification label for each company
4. WHEN THE System completes company classification, THE System SHALL output the confidence level for each company
5. WHEN THE System completes company classification, THE System SHALL output the classification metadata including award count, PSC family count, and override reasons
