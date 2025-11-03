# Transition Detection System - Data Dictionary

## Overview

This data dictionary provides a comprehensive reference for all fields in the transition detection system, organized by entity type. Each field includes its data type, valid values, constraints, examples, and relationships to other fields.

### Format Convention

- **Field Name**: The exact field name in code/database
- **Type**: Data type (String, Integer, Float, DateTime, Boolean, List, Object, Enum)
- **Nullable**: Whether null values are allowed
- **Constraints**: Min/max values, format requirements, valid values
- **Description**: Purpose and usage
- **Example**: Sample value
- **Related Fields**: Links to related fields in same or other entities

---

## Transition Entity Fields

Represents a detected commercialization transition from SBIR award to federal contract.

### Core Identification

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `transition_id` | String | No | Unique, 20 chars | Unique identifier for transition | `trans_a1b2c3d4e5f6` | Primary key |
| `award_id` | String | No | Unique reference | Reference to SBIR award | `SBIR-2020-PHASE-II-001` | Award.award_id |
| `contract_id` | String | No | Unique reference | Reference to federal contract | `FA1234-20-C-0001` | Contract.contract_id |

### Scoring & Confidence

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `likelihood_score` | Float | No | 0.0 to 1.0 | Composite transition probability | `0.7625` | confidence |
| `confidence` | Enum | No | HIGH, LIKELY, POSSIBLE | Confidence classification | `LIKELY` | likelihood_score |
| `base_score` | Float | No | 0.0 to 1.0 | Baseline prior probability | `0.15` | Config parameter |

### Signal Contributions

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `agency_continuity_score` | Float | Yes | 0.0 to 1.0 | Agency signal contribution | `0.0625` | Signals.agency |
| `timing_proximity_score` | Float | Yes | 0.0 to 1.0 | Timing signal contribution | `0.20` | Signals.timing |
| `competition_type_score` | Float | Yes | 0.0 to 1.0 | Competition signal contribution | `0.04` | Signals.competition |
| `patent_signal_score` | Float | Yes | 0.0 to 1.0 | Patent signal contribution | `0.015` | Signals.patent |
| `cet_alignment_score` | Float | Yes | 0.0 to 1.0 | CET signal contribution | `0.005` | Signals.cet |
| `vendor_match_score` | Float | Yes | 0.0 to 1.0 | Vendor match contribution | `0.01` | Signals.vendor |

### Vendor Matching

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `vendor_match_method` | Enum | No | UEI, CAGE, DUNS, FUZZY_NAME, NONE | Vendor resolution method | `UEI` | VendorMatch |
| `vendor_match_confidence` | Float | No | 0.0 to 1.0 | Confidence in vendor match | `0.99` | VendorMatch |

### Metadata

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `detection_date` | DateTime | No | ISO 8601 | Timestamp of detection | `2024-01-15T10:30:00Z` | Audit trail |
| `detection_method` | String | Yes | Version string | Detection algorithm version | `transition_detector_v1` | Reproducibility |
| `created_at` | DateTime | No | ISO 8601 | Record creation time | `2024-01-15T10:30:00Z` | Audit trail |
| `updated_at` | DateTime | No | ISO 8601 | Last update time | `2024-01-15T10:30:00Z` | Audit trail |

### Evidence & Signals

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `signals` | Object | Yes | JSON | All signal details (nested) | `{...}` | TransitionSignals |
| `evidence_bundle` | String | Yes | JSON (max 100KB) | Complete evidence justification | `{...}` | EvidenceBundle |

---

## Award Entity Fields

Represents an SBIR award.

### Core Identification

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `award_id` | String | No | Unique, 20-50 chars | Unique award identifier | `SBIR-2020-PHASE-II-001` | Primary key |
| `award_number` | String | Yes | Alternative ID | Alternative award number | `1234567` | award_id |
| `sbir_award_id` | String | Yes | Alternative ID | SBIR-specific identifier | `2020-II-001` | award_id |

### Program Classification

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `phase` | Enum | No | PHASE_I, PHASE_II, PHASE_IIB, PHASE_III | Award phase | `PHASE_II` | Program structure |
| `program` | Enum | No | SBIR, STTR | Program type | `SBIR` | Program structure |
| `topic_code` | String | Yes | Variable length | Topic classification code | `AF20-028` | award_topic |
| `topic` | String | No | Freetext, max 500 chars | Award topic/title | `Advanced neural networks for threat detection` | award_topic |

### Agency & Organization

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `agency` | String | No | Standard code | Awarding agency | `17` | agency_name |
| `agency_name` | String | No | Freetext | Full agency name | `Department of Defense` | agency |
| `sub_agency` | String | Yes | Variable | Sub-agency/service | `5700` | sub_agency_name |
| `sub_agency_name` | String | Yes | Freetext | Full sub-agency name | `Department of the Air Force` | sub_agency |

### Dates

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `award_date` | Date | No | YYYY-MM-DD | Date award was granted | `2021-09-01` | timeline |
| `completion_date` | Date | No | YYYY-MM-DD | Phase completion date | `2023-01-15` | timeline |
| `start_date` | Date | Yes | YYYY-MM-DD | Phase start date | `2021-09-01` | timeline |
| `performance_period_days` | Integer | Yes | ≥0 | Duration of phase in days | `517` | Computed |

### Funding

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `award_amount` | Long | No | ≥0 | Award amount in dollars | `150000` | Budget |
| `currency` | Enum | No | USD, etc. | Currency of amount | `USD` | award_amount |

### Recipient Information

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `recipient_name` | String | No | Freetext, max 200 | Company/recipient name | `Acme AI Inc.` | recipient_id |
| `recipient_uei` | String | Yes | 12-char alphanumeric | Unique Entity Identifier | `ABC123DEF456` | recipient_id |
| `recipient_duns` | String | Yes | 9-digit | DUNS number | `123456789` | recipient_id |
| `recipient_cage` | String | Yes | 5-char code | CAGE code | `1A2B3` | recipient_id |
| `recipient_state` | String | Yes | 2-char state code | State of recipient | `VA` | recipient_location |
| `recipient_city` | String | Yes | Freetext | City of recipient | `Arlington` | recipient_location |

### Technical Classification

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `cet_area` | String | Yes | CET area name | Critical emerging technology | `AI & Machine Learning` | CET alignment |
| `cet_code` | String | Yes | CET area code | CET area code | `AI_ML` | cet_area |
| `technology_area` | String | Yes | Freetext | Technology focus | `Artificial Intelligence` | cet_area |
| `focus_area` | String | Yes | Freetext | Research focus area | `Neural Networks` | cet_area |

### Award Details

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `description` | Text | Yes | Freetext, max 5000 | Award description/abstract | `Development of federated learning techniques...` | topic |
| `principal_investigator` | String | Yes | Freetext | PI name | `Dr. Jane Smith` | recipient_name |
| `technical_contact` | String | Yes | Email | Technical contact email | `jane.smith@acme.com` | recipient_info |
| `business_contact` | String | Yes | Email | Business contact email | `business@acme.com` | recipient_info |

### Company Classification

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `company_size` | Enum | Yes | SMALL_BUSINESS, OTHER | Small business status | `SMALL_BUSINESS` | recipient_info |
| `naics_primary` | String | Yes | 6-digit code | Primary NAICS code | `541511` | business_type |
| `naics_secondary` | String | Yes | 6-digit code | Secondary NAICS code | `541512` | business_type |
| `business_type` | String | Yes | Freetext | Type of business | `Software Development` | company_size |

### Metadata

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `created_at` | DateTime | No | ISO 8601 | Record creation time | `2024-01-15T10:30:00Z` | Audit trail |
| `updated_at` | DateTime | No | ISO 8601 | Last update time | `2024-01-15T10:30:00Z` | Audit trail |
| `data_source` | String | Yes | SBIR.gov, etc. | Data source system | `SBIR.gov` | Data lineage |

---

## Contract Entity Fields

Represents a federal contract.

### Core Identification

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `contract_id` | String | No | Unique, 20-50 chars | Unique contract identifier | `FA1234-20-C-0001` | Primary key |
| `piid` | String | Yes | Unique, 13-17 chars | Procurement Instrument ID | `FA1234-20-C-0001` | contract_id |
| `fain` | String | Yes | Unique, 20-30 chars | Federal Award ID Number | `FAIN123456789` | contract_id |
| `parent_piid` | String | Yes | Reference | Parent contract PIID (for task orders) | `FA1234-20-C-0000` | contract_hierarchy |
| `idv_agency` | String | Yes | Variable | IDV agency code | `17` | contract_hierarchy |
| `idv_piid` | String | Yes | Reference | IDV parent PIID | `FA1234-20-D-0001` | contract_hierarchy |

### Contract Type

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `contract_type_code` | String | Yes | 1-2 chars | Contract type code | `C` (Fixed price) | contract_type |
| `contract_type` | Enum | Yes | FIXED_PRICE, COST_PLUS, TIME_MATERIALS | Contract type | `FIXED_PRICE` | contract_type_code |
| `contract_number_type` | String | Yes | Variable | Contract number format type | `PIID` | piid/fain |

### Agency & Organization

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `agency` | String | No | Standard code | Awarding agency | `17` | agency_name |
| `agency_name` | String | No | Freetext | Full agency name | `Department of Defense` | agency |
| `sub_agency` | String | Yes | Variable | Sub-agency code | `5700` | sub_agency_name |
| `sub_agency_name` | String | Yes | Freetext | Full sub-agency name | `Department of the Air Force` | sub_agency |

### Dates

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `action_date` | Date | No | YYYY-MM-DD | Contract action date | `2023-03-01` | timeline |
| `start_date` | Date | Yes | YYYY-MM-DD | Period of performance start | `2023-03-01` | timeline |
| `end_date` | Date | Yes | YYYY-MM-DD | Period of performance end | `2025-03-01` | timeline |
| `contract_duration_days` | Integer | Yes | ≥0 | Contract duration in days | `730` | Computed |

### Financial

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `obligated_amount` | Long | No | ≥0 | Amount obligated in this action | `500000` | budget |
| `base_amount` | Long | Yes | ≥0 | Base contract amount | `500000` | budget |
| `option_amount` | Long | Yes | ≥0 | Amount for options/extensions | `500000` | budget |
| `base_and_all_options_value` | Long | Yes | ≥0 | Total potential value | `1000000` | budget |
| `currency` | Enum | No | USD, etc. | Currency of amounts | `USD` | obligated_amount |

### Competition

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `competition_type` | Enum | Yes | SOLE_SOURCE, LIMITED, FULL_AND_OPEN, UNKNOWN | Competition type | `SOLE_SOURCE` | extent_competed |
| `extent_competed` | String | Yes | USAspending code | Raw competition code | `NONE` | competition_type |
| `extent_competed_code` | String | Yes | FULL, NONE, LIMITED | Normalized code | `NONE` | competition_type |

### Vendor Information

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `vendor_name` | String | No | Freetext, max 200 | Contractor name | `Acme AI Inc.` | vendor_id |
| `vendor_uei` | String | Yes | 12-char alphanumeric | Contractor UEI | `ABC123DEF456` | vendor_id |
| `vendor_cage` | String | Yes | 5-char code | Contractor CAGE code | `1A2B3` | vendor_id |
| `vendor_duns` | String | Yes | 9-digit | Contractor DUNS | `123456789` | vendor_id |
| `vendor_state` | String | Yes | 2-char state code | Contractor state | `VA` | vendor_location |
| `vendor_city` | String | Yes | Freetext | Contractor city | `Arlington` | vendor_location |
| `vendor_zip` | String | Yes | 5-9 digit | Contractor zip code | `22202` | vendor_location |

### Parent Organization

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `parent_vendor_name` | String | Yes | Freetext | Parent company name | `BigTech Corp` | vendor_hierarchy |
| `parent_vendor_uei` | String | Yes | 12-char | Parent company UEI | `XYZ789ABC012` | vendor_hierarchy |
| `parent_duns` | String | Yes | 9-digit | Parent company DUNS | `987654321` | vendor_hierarchy |

### Contract Description & Classification

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `description` | Text | Yes | Freetext, max 5000 | Statement of work/description | `AI-powered threat detection system` | contract_focus |
| `title` | String | Yes | Freetext, max 200 | Contract title | `Development of AI system` | description |
| `psc_code` | String | Yes | 4-char code | Product/Service Code | `D316` | classification |
| `psc_description` | String | Yes | Freetext | PSC description | `Computer Systems` | psc_code |
| `naics_code` | String | Yes | 6-digit | Industry classification | `541511` | classification |
| `naics_description` | String | Yes | Freetext | NAICS description | `Software Development` | naics_code |

### Work Location

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `place_of_performance` | String | Yes | Freetext | Primary work location | `Arlington, VA` | work_location |
| `pop_state` | String | Yes | 2-char code | PoP state code | `VA` | place_of_performance |
| `pop_city` | String | Yes | Freetext | PoP city | `Arlington` | place_of_performance |
| `pop_zip` | String | Yes | 5-9 digit | PoP zip code | `22202` | place_of_performance |

### Contract Hierarchy

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `is_task_order` | Boolean | Yes | true/false | Is this a task order on IDV | `false` | parent_piid |
| `is_idv` | Boolean | Yes | true/false | Is this an Indefinite Delivery contract | `false` | idv_piid |
| `child_count` | Integer | Yes | ≥0 | Number of child task orders | `5` | contract_hierarchy |

### Metadata

| Field | Type | Nullable | Constraints | Description | Example | Related |
|-------|------|----------|-------------|-------------|---------|---------|
| `created_at` | DateTime | No | ISO 8601 | Record creation time | `2024-01-15T10:30:00Z` | Audit trail |
| `updated_at` | DateTime | No | ISO 8601 | Last update time | `2024-01-15T10:30:00Z` | Audit trail |
| `data_source` | String | Yes | USAspending, etc. | Data source system | `USAspending.gov` | Data lineage |

---

## Transition Signals - Nested Fields

These fields are nested within the `signals` object of a Transition.

### Agency Continuity Signal

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `award_agency` | String | Award agency code | `17` |
| `contract_agency` | String | Contract agency code | `17` |
| `same_agency` | Boolean | Agencies match exactly | `true` |
| `same_department` | Boolean | Agencies in same department | `true` |
| `agency_score` | Float | Signal contribution (0.0-1.0) | `0.0625` |

### Timing Proximity Signal

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `award_completion_date` | Date | Award completion date | `2023-01-15` |
| `contract_start_date` | Date | Contract start date | `2023-03-01` |
| `days_between` | Integer | Days from completion to start | `45` |
| `months_between` | Float | Months (days/30) | `1.5` |
| `timing_window` | String | Window classification | `0-90 days` |
| `timing_score` | Float | Signal contribution (0.0-1.0) | `0.20` |

### Competition Type Signal

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `competition_type` | Enum | SOLE_SOURCE, LIMITED, FULL_AND_OPEN | `SOLE_SOURCE` |
| `extent_competed_code` | String | USAspending code | `NONE` |
| `competition_score` | Float | Signal contribution (0.0-1.0) | `0.04` |

### Patent Signal

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `patent_count` | Integer | Total patents filed | `2` |
| `pre_contract_count` | Integer | Patents filed before contract | `1` |
| `max_topic_similarity` | Float | Max TF-IDF similarity (0.0-1.0) | `0.78` |
| `has_patent_bonus` | Float | Bonus for having patents | `0.05` |
| `pre_contract_bonus` | Float | Bonus for pre-contract patents | `0.03` |
| `topic_match_bonus` | Float | Bonus for topic match | `0.02` |
| `patent_signal_score` | Float | Weighted contribution (0.0-1.0) | `0.015` |

### CET Alignment Signal

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `award_cet` | String | Award CET area | `AI & Machine Learning` |
| `contract_cet` | String | Inferred contract CET | `AI & Machine Learning` |
| `cet_alignment_type` | Enum | EXACT, PARTIAL, NONE, UNKNOWN | `EXACT` |
| `cet_confidence` | Float | Confidence in CET inference (0.0-1.0) | `0.92` |
| `cet_alignment_score` | Float | Signal contribution (0.0-1.0) | `0.005` |

### Vendor Match Signal

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `match_method` | Enum | UEI, CAGE, DUNS, FUZZY_NAME, NONE | `UEI` |
| `award_uei` | String | Award recipient UEI | `ABC123DEF456` |
| `contract_uei` | String | Contract vendor UEI | `ABC123DEF456` |
| `fuzzy_similarity` | Float | Fuzzy match score (0.0-1.0) | `0.82` |
| `match_confidence` | Float | Confidence in match (0.0-1.0) | `0.99` |
| `vendor_match_score` | Float | Signal contribution (0.0-1.0) | `0.01` |

---

## Vendor Resolution Fields

Represents mapping from award recipient to contract vendor.

### Identification

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `award_recipient_id` | String | Award recipient identifier | `SBIR-RECIPIENT-001` |
| `contractor_id` | String | Federal contractor identifier | `CONTRACTOR-001` |

### Resolution Details

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `match_type` | Enum | UEI, CAGE, DUNS, FUZZY_NAME | `UEI` |
| `confidence` | Float | Match confidence (0.0-1.0) | `0.99` |
| `resolution_date` | DateTime | Resolution timestamp | `2024-01-15T10:30:00Z` |

### Matched Identifiers

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `award_uei` | String | Award recipient UEI | `ABC123DEF456` |
| `contract_uei` | String | Contract vendor UEI | `ABC123DEF456` |
| `award_cage` | String | Award recipient CAGE | `1A2B3` |
| `contract_cage` | String | Contract vendor CAGE | `1A2B3` |
| `award_duns` | String | Award recipient DUNS | `123456789` |
| `contract_duns` | String | Contract vendor DUNS | `123456789` |
| `award_name` | String | Award recipient name | `Acme AI Inc.` |
| `contract_name` | String | Contract vendor name | `Acme Artificial Intelligence` |

---

## Evidence Bundle Fields

Structured evidence justifying a transition detection (nested within Transition).

### Metadata

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `transition_id` | String | Parent transition ID | `trans_a1b2c3d4e5f6` |
| `summary` | String | Human-readable summary | `DoD award to same vendor within 45 days` |

### Vendor Match Evidence

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `vendor_match_method` | String | Resolution method | `UEI` |
| `vendor_match_confidence` | Float | Match confidence (0.0-1.0) | `0.99` |

### Signal Evidence (nested objects)

Each signal has nested evidence with:

- `snippet`: 1-line human summary
- `score_contribution`: Numeric contribution to overall score
- `details`: Signal-specific structured data

---

## Analytics Fields

Computed summary statistics for transition analysis.

### Aggregation by Award Level

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `total_awards` | Long | Total SBIR awards analyzed | `250` |
| `award_transition_count` | Long | Awards with ≥1 transition | `85` |
| `award_transition_rate` | Float | Transitioned awards / total (0.0-1.0) | `0.34` |

### Aggregation by Company Level

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `total_companies` | Long | Unique SBIR recipients | `180` |
| `company_transition_count` | Long | Companies with ≥1 transition | `65` |
| `company_transition_rate` | Float | Companies with transitions / total (0.0-1.0) | `0.36` |

### Phase Effectiveness

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `phase_1_awards` | Long | Total Phase I awards | `150` |
| `phase_1_transitions` | Long | Phase I awards with transitions | `30` |
| `phase_1_transition_rate` | Float | Phase I transition rate (0.0-1.0) | `0.20` |
| `phase_2_awards` | Long | Total Phase II awards | `100` |
| `phase_2_transitions` | Long | Phase II awards with transitions | `55` |
| `phase_2_transition_rate` | Float | Phase II transition rate (0.0-1.0) | `0.55` |

### By Agency

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `agency` | String | Agency code/name | `17` (DoD) |
| `agency_awards` | Long | Awards from this agency | `100` |
| `agency_transitions` | Long | Transitions from this agency | `35` |
| `agency_transition_rate` | Float | Transition rate (0.0-1.0) | `0.35` |

### By CET Area

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `cet_area` | String | CET area name | `AI & Machine Learning` |
| `cet_awards` | Long | Awards in this CET area | `250` |
| `cet_transitions` | Long | Transitions in this CET area | `85` |
| `cet_transition_rate` | Float | Transition rate (0.0-1.0) | `0.34` |
| `cet_avg_score` | Float | Average transition score (0.0-1.0) | `0.72` |

### Patent-Backed Transitions

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `transitions_with_patents` | Long | Transitions with patent backing | `42` |
| `patent_backed_rate` | Float | Patent-backed / total transitions (0.0-1.0) | `0.49` |
| `avg_patent_count` | Float | Average patents per transition | `1.5` |

### Time-to-Transition

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `avg_days_to_transition` | Float | Average days award to contract | `240.5` |
| `median_days_to_transition` | Integer | Median days | `210` |
| `p25_days_to_transition` | Integer | 25th percentile days | `120` |
| `p75_days_to_transition` | Integer | 75th percentile days | `450` |
| `p90_days_to_transition` | Integer | 90th percentile days | `600` |

---

## Company Transition Profile Fields

Represents company-level aggregated statistics.

### Identification

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `profile_id` | String | Profile unique identifier | `profile_ABC123DEF456` |
| `company_id` | String | Reference to company | `company_ABC123DEF456` |
| `company_name` | String | Company name | `Acme AI Inc.` |

### Aggregate Metrics

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `total_awards` | Long | Total SBIR awards | `5` |
| `total_transitions` | Long | Total detected transitions | `3` |
| `success_rate` | Float | Transitions / awards (0.0-1.0) | `0.60` |

### Score Metrics

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `avg_likelihood_score` | Float | Average transition score (0.0-1.0) | `0.72` |
| `max_likelihood_score` | Float | Highest transition score (0.0-1.0) | `0.85` |
| `min_likelihood_score` | Float | Lowest transition score (0.0-1.0) | `0.58` |

### Timing Metrics

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `avg_time_to_transition` | Float | Average days to transition | `245.5` |
| `median_time_to_transition` | Integer | Median days | `210` |
| `fastest_transition_days` | Integer | Fastest transition | `45` |
| `slowest_transition_days` | Integer | Slowest transition | `720` |

### Financial Metrics

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `total_award_amount` | Long | Sum of award amounts | `750000` |
| `total_contract_amount` | Long | Sum of contract amounts | `2500000` |
| `roi_ratio` | Float | Contract amount / award amount | `3.33` |

---

## Data Type Reference

### Enumeration Values

#### Confidence Levels

- `HIGH`: likelihood_score ≥ 0.85
- `LIKELY`: 0.65 ≤ likelihood_score < 0.85
- `POSSIBLE`: likelihood_score < 0.65

#### Award Phases

- `PHASE_I`: Phase I award
- `PHASE_II`: Phase II award
- `PHASE_IIB`: Phase IIB (fast track) award
- `PHASE_III`: Phase III (commercialization) award

#### Programs

- `SBIR`: Small Business Innovation Research
- `STTR`: Small Business Technology Transfer

#### Vendor Match Methods

- `UEI`: Unique Entity Identifier exact match
- `CAGE`: CAGE code exact match
- `DUNS`: DUNS number exact match
- `FUZZY_NAME`: Fuzzy name matching (RapidFuzz)
- `NONE`: No match found

#### Competition Types

- `SOLE_SOURCE`: Single vendor competition
- `LIMITED`: Limited number of eligible vendors
- `FULL_AND_OPEN`: Open competition
- `UNKNOWN`: Competition type unknown

#### Company Size

- `SMALL_BUSINESS`: Small business concern
- `OTHER`: Non-small business

#### CET Areas

- `AI & Machine Learning`
- `Advanced Computing`
- `Biotechnology & Advanced Biology`
- `Advanced Manufacturing`
- `Quantum Computing`
- `Biodefense`
- `Microelectronics`
- `Hypersonics`
- `Space Systems`
- `Climate Resilience`

#### CET Alignment Types

- `EXACT`: Award CET == Contract CET
- `PARTIAL`: Related but not identical CET areas
- `NONE`: Unrelated CET areas
- `UNKNOWN`: Missing CET data

### Data Type Specifications

| Type | Format | Range | Example |
|------|--------|-------|---------|
| String | UTF-8 text | Max varies | `"Acme AI Inc."` |
| Integer | Whole number | Varies | `500000` |
| Long | Large integer | -2^63 to 2^63-1 | `1000000000` |
| Float | Decimal number | 0.0 to 1.0 (usually) | `0.7625` |
| Double | High precision decimal | Full IEEE 754 range | `0.123456789` |
| Boolean | True/False | Two values | `true` |
| Date | YYYY-MM-DD | Per calendar | `2024-01-15` |
| DateTime | ISO 8601 | Timestamp | `2024-01-15T10:30:00Z` |
| Enum | Predefined values | Specific set | `LIKELY` |
| Object | JSON structure | Nested data | `{...}` |
| List | Array of items | Any element type | `[...]` |

---

## Field Validation Rules

### Required Fields (must have non-null value)

- `transition_id`, `award_id`, `contract_id`, `likelihood_score`, `confidence`
- `award_date`, `completion_date`, `award_amount`
- `action_date`, `obligated_amount`, `vendor_name`
- `agency` (award and contract)

### Optional Fields (null allowed)

- `recipient_uei`, `recipient_duns`, `recipient_cage`
- `vendor_uei`, `vendor_cage`, `vendor_duns`
- `cet_area`, `description`
- Signal scores (if signal disabled)

### Constrained Fields

- `likelihood_score`: Must be 0.0 to 1.0
- `confidence`: Must be one of: HIGH, LIKELY, POSSIBLE
- `award_amount`, `obligated_amount`: Must be ≥ 0
- `completion_date`: Must be ≥ award_date
- `contract_start_date`: Should be ≥ award_completion_date (can be < for data quality issues)

---

## Cross-Field Relationships

| Field | Relationship | Related Field | Constraint |
|-------|--------------|---------------|-----------|
| `likelihood_score` | Determines | `confidence` | Score >= 0.85 → HIGH |
| `award_id` | References | `Transition.award_id` | Foreign key |
| `contract_id` | References | `Transition.contract_id` | Foreign key |
| `completion_date` | Used in | `timing_proximity_score` | Calculate days to contract_start |
| `cet_area` | Used in | `cet_alignment_score` | Match with inferred contract CET |
| `recipient_uei` | Used in | `vendor_match_method` | Primary resolution method |
| `vendor_match_confidence` | Impacts | `likelihood_score` | Higher confidence = higher score |

---

## Data Quality Guidelines

### Missing Data

- **Acceptable**: ≤5% of optional fields may be null
- **Warning**: ≥10% missing for required fields
- **Action**: Investigate and document reasons

### Out-of-Range Values

- **Likelihood scores** outside [0.0, 1.0]: Invalid
- **Amounts** negative: Data quality issue
- **Dates** reversed (end < start): Invalid

### Consistency Checks

- `completion_date` should be after `award_date`
- `contract_start_date` should be after `award_completion_date` (usually)
- `likelihood_score` matches confidence classification
- Signal scores sum approximately to final score

---

## Related Documentation

- **Algorithm Details**: `docs/transition/detection_algorithm.md`
- **Scoring Guide**: `docs/transition/scoring_guide.md`
- **Evidence Structure**: `docs/transition/evidence_bundles.md`
- **Neo4j Schema**: `docs/schemas/transition-graph-schema.md`
- **Configuration**: `config/transition/detection.yaml`
- **Data Models**: `src/models/transition_models.py`

</parameter>