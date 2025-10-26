# USAspending Subset Profile Report

This report contains profiling information for the USAspending Postgres dump subset used in SBIR ETL evaluation.

## Report Metadata

- **Generated**: [Run date will be populated when profiler executes]
- **Dump Path**: `/Volumes/X10 Pro/usaspending-db-subset_20251006.zip`
- **Dump Size**: [Size will be populated when profiler executes]
- **Profiling Tool**: `scripts/profile_usaspending_dump.py`

## Instructions for Generating This Report

To generate this report, ensure the "X10 Pro" drive is mounted and run:

```bash
cd /path/to/sbir-etl
python scripts/profile_usaspending_dump.py --output reports/usaspending_subset_profile.json
```

This will create both a JSON report and update this Markdown file with the findings.

## Expected Dump Contents

Based on USAspending data dictionary, the subset should contain these key tables:

### Core Award Tables
- `transaction_normalized` - Main transaction table with award details
- `awards` - Award header information
- `transaction_fabs` - Financial Assistance transactions
- `transaction_fpds` - Federal Procurement Data System transactions

### Recipient Information
- `recipient_lookup` - Recipient name and identifier mapping
- `recipient_profile` - Detailed recipient profiles

### Reference Tables
- `agency` - Agency reference data
- `toptier_agency` - Top-tier agency information
- `subtier_agency` - Sub-tier agency details
- `cfda` - Catalog of Federal Domestic Assistance programs

## Profiling Results

*[This section will be populated after running the profiler]*

### Table Inventory
- Total tables found: [count]
- Key tables present: [list]

### Sample Data Insights
- Largest table: [table name, approximate row count]
- Key columns identified: [list of important columns for SBIR matching]

### Enrichment Coverage Assessment
- UEI coverage: [percentage of transactions with UEI]
- DUNS coverage: [percentage of transactions with DUNS]
- PIID/FAIN coverage: [percentage with procurement/financial assistance IDs]

## SBIR Enrichment Mapping

### Required Fields for SBIR Matching
- **Recipient Identifiers**: UEI, DUNS, recipient_name
- **Award Identifiers**: PIID (procurement), FAIN (assistance)
- **Award Metadata**: awarding_agency, funding_agency, action_date
- **Financial Data**: federal_action_obligation, original_loan_subsidy_cost

### USAspending → SBIR Award Field Mapping

#### Recipient Information
- `recipient_uei` → `SbirAward.company_uei`
- `recipient_unique_id` (DUNS) → `SbirAward.company_duns`
- `recipient_name` → `SbirAward.company_name` (for validation/fuzzy matching)
- `recipient_uei` → Enrichment lookup for additional company metadata

#### Award Identification
- `award_id_piid` → `SbirAward.contract` (procurement awards)
- `award_id_fain` → `SbirAward.contract` (assistance awards)
- `transaction_unique_id` → Unique transaction identifier for deduplication

#### Financial Data
- `federal_action_obligation` → Award amount validation and enrichment
- `original_loan_subsidy_cost` → Loan subsidy amounts for certain programs
- `indirect_federal_sharing` → Federal funding breakdown

#### Agency Information
- `awarding_agency_name` → `SbirAward.agency` validation
- `funding_agency_name` → Additional agency context
- `awarding_subtier_agency_name` → More specific agency identification
- `awarding_office_name` → Office-level detail

#### Program Classification
- `cfda_number` → CFDA program codes
- `naics_code` → NAICS industry classification
- `product_or_service_code` (PSC) → Procurement service categories

#### Geographic Information
- `place_of_performance_city_name` → Award location data
- `place_of_performance_state_code` → State codes
- `place_of_performance_zip5` → ZIP codes
- `place_of_performance_congressional_district` → Congressional district

#### Transaction Metadata
- `action_date` → Transaction date (vs award date)
- `last_modified_date` → Data freshness indicator
- `transaction_fiscal_year` → Fiscal year context

### Transition Detection Fields

#### Competition and Award History
- `solicitation_identifier` → Solicitation references
- `extent_competed` → Competition level (full/open, etc.)
- `competitive_procedures` → Procurement method
- `number_of_offers_received` → Bid competition metrics

#### Award Progression Tracking
- `idv_type_description` → Indefinite delivery vehicle types
- `type_of_contract_pricing` → Pricing arrangements
- `contract_award_type` → Award type classifications

#### Financial History
- `base_and_exercised_options_value` → Total contract value
- `base_and_all_options_value` → Maximum potential value
- `action_type` → Transaction type (award, modification, etc.)

#### Agency Relationships
- `funding_agency_name` → Funding source
- `awarding_agency_name` → Awarding authority
- `referenced_idv_agency_name` → Parent contract agency

### Expected Match Rates
- Target: ≥70% of SBIR awards should find USAspending matches
- Current assessment: [To be determined from profiling]

## Technical Notes

### Data Quality Observations

#### Identifier Quality Issues
- **UEI Format Consistency**: Check for mixed case, leading/trailing spaces, or invalid characters in `recipient_uei`
- **DUNS Validation**: Verify 9-digit format, handle missing or zero-padded values
- **PIID/FAIN Patterns**: Identify inconsistent formatting, missing values, or duplicates across transactions

#### Data Completeness
- **Null Rates by Field**: Track percentage of missing values for key enrichment fields
- **Temporal Coverage**: Assess date range coverage and gaps in transaction history
- **Geographic Coverage**: Evaluate completeness of place of performance data

#### Data Accuracy Concerns
- **Amount Validation**: Cross-check `federal_action_obligation` against known SBIR award ranges
- **Agency Name Standardization**: Identify variations in agency naming conventions
- **Date Consistency**: Verify `action_date` falls within reasonable ranges for federal contracting

#### Enrichment Blocker Assessment
- **Match Rate Limitations**: Identify systemic issues preventing high match rates (e.g., UEI adoption timeline)
- **Data Freshness**: Evaluate how current the subset data is vs. SBIR award dates
- **Schema Evolution**: Note any changes in field definitions across fiscal years

#### Recommended Mitigations
- **Fallback Matching**: Implement cascading match logic (UEI → DUNS → Company Name)
- **Fuzzy Matching**: Prepare for approximate string matching on company names
- **Data Enrichment**: Plan for external UEI/DUNS lookup services
- **Incremental Updates**: Design for periodic refresh of USAspending data

### Performance Considerations
- Streaming from removable media: Expect 2-5x slower than local SSD
- Memory requirements: Most queries should work with <2GB RAM
- Temporary space: <1GB needed for most operations

## Next Steps

1. Mount "X10 Pro" drive
2. Run profiler script
3. Review coverage assessment
4. Update enrichment logic based on findings
5. Plan transition detection implementation

---
*This report is automatically generated by `scripts/profile_usaspending_dump.py`*
```
