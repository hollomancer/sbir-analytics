# Evidence Bundle Structure & Interpretation Guide

## Overview

An **evidence bundle** is a comprehensive audit trail that documents how and why a particular award-contract pair was identified as a transition. It contains:

- All signal evaluations (agency, timing, competition, patent, CET)
- Vendor match information with confidence scores
- Contract details for reference
- Human-readable summaries
- Raw data supporting each signal

**Purpose**: Enable stakeholders to understand, validate, and trust individual transition detections.

**Usage**: Evidence bundles are stored as JSON on Neo4j relationships, exported to NDJSON files, and presented in reports.

## Why Evidence Bundles Matter

### 1. Auditability

- Justify detection decisions to stakeholders
- Trace logic from raw data through scoring
- Enable reproducibility and debugging

### 2. Quality Control

- Identify systematic scoring errors
- Validate signal calculations
- Flag anomalies for investigation

### 3. Decision Support

- Help analysts evaluate transition quality
- Prioritize high-confidence detections
- Identify borderline cases needing manual review

### 4. Improvement

- Analyze patterns in false positives/negatives
- Guide algorithm tuning
- Inform threshold adjustments

## Evidence Bundle Structure

### High-Level Schema

```json
{
  "transition_id": "trans_abc123def456",
  "award_id": "SBIR-2020-PHASE-II-001",
  "contract_id": "FA1234-20-C-0001",
  "likelihood_score": 0.75,
  "confidence": "LIKELY",
  "detection_date": "2024-01-15T10:30:00Z",
  "detection_method": "transition_detector_v1",
  
  "summary": "Award recipient Acme AI Inc. (UEI: ABC123) awarded Phase II contract from DoD within 6 months after completion",
  
  "signals": {
    "agency_continuity": {...},
    "timing_proximity": {...},
    "competition_type": {...},
    "patent_signal": {...},
    "cet_alignment": {...},
    "vendor_match": {...}
  },
  
  "contract_details": {...},
  "award_details": {...},
  "matcher_details": {...},
  
  "validation": {
    "completeness": "PASS",
    "score_valid": true,
    "all_required_fields_present": true
  }
}
```

### Detailed Field Definitions

#### Top-Level Fields

```yaml
transition_id: str
  # Unique identifier for this detection
  # Format: "trans_" + hex(hash(award_id + contract_id + timestamp))
  # Example: "trans_a1b2c3d4e5f6"

award_id: str
  # SBIR award identifier
  # Example: "SBIR-2020-PHASE-II-001" or "1234567"

contract_id: str
  # Federal contract identifier (PIID)
  # Example: "FA1234-20-C-0001" or "contract_001"

likelihood_score: float
  # Composite likelihood score (0.0-1.0)
  # Example: 0.75
  # Interpretation: 75% likelihood of transition

confidence: str
  # Confidence band: "HIGH", "LIKELY", or "POSSIBLE"
  # Example: "LIKELY"
  # Mapping: HIGH (≥0.85), LIKELY (0.65-0.84), POSSIBLE (<0.65)

detection_date: str (ISO 8601)
  # Timestamp when detection occurred
  # Example: "2024-01-15T10:30:00Z"
  # Used for reproducibility and auditing

detection_method: str
  # Detection pipeline version/method
  # Example: "transition_detector_v1"
  # Enables tracking algorithm changes over time

summary: str
  # Human-readable one-liner summarizing key findings
  # Example: "DoD award to same vendor within 45 days of completion; sole source contract"
  # Length: 50-200 characters
```

#### Signals Object

Each signal contains:

```yaml
<signal_name>:
  enabled: bool
  # Whether this signal was included in scoring

  snippet: str
  # Short human-readable summary of finding
  # Example: "Same agency (DoD → DoD)"
  # Length: 30-100 characters

  score_contribution: float
  # This signal's contribution to final score
  # Example: 0.0625 = 0.25 bonus × 0.25 weight

  details: object
  # Signal-specific structured data (see below)

  confidence: float (optional)
  # Confidence in this particular signal (0.0-1.0)
  # Not all signals have confidence scores
```

### Agency Continuity Signal

```json
{
  "agency_continuity": {
    "enabled": true,
    "snippet": "Same agency (DoD → DoD)",
    "score_contribution": 0.0625,
    "details": {
      "match_type": "same_agency",
      "award_agency": "Department of Defense",
      "award_agency_code": "17",
      "contract_agency": "Department of Defense",
      "contract_agency_code": "17",
      "same_agency": true,
      "same_department": null,
      "agency_score": 0.0625
    }
  }
}
```

### Fields

- `match_type`: "same_agency" | "cross_service" | "different_dept" | "unknown"
- `award_agency`: Full name of award agency
- `award_agency_code`: Numeric agency code
- `contract_agency`: Full name of contract agency
- `contract_agency_code`: Numeric agency code
- `same_agency`: Boolean, true if award_agency == contract_agency
- `same_department`: Boolean or null, true if same department but different agency
- `agency_score`: Numeric contribution to final score

### Interpretation

- `same_agency: true` → Strong signal (0.0625 contribution)
- `same_department: true` → Moderate signal (0.03125 contribution)
- `same_agency: false, same_department: false` → Weak signal (0.0125 contribution)

### Timing Proximity Signal

```json
{
  "timing_proximity": {
    "enabled": true,
    "snippet": "45 days after completion (immediate commercialization)",
    "score_contribution": 0.20,
    "details": {
      "award_completion_date": "2023-01-15",
      "contract_start_date": "2023-03-01",
      "days_between_award_and_contract": 45,
      "months_between_award_and_contract": 1.5,
      "timing_window_range": [0, 90],
      "timing_window_label": "immediate",
      "timing_score": 0.20,
      "note": "Contract within 0-90 day immediate window"
    }
  }
}
```

### Fields

- `award_completion_date`: ISO date when Phase II ended
- `contract_start_date`: ISO date when contract began
- `days_between_award_and_contract`: Integer days (can be negative if contract pre-dates award)
- `months_between_award_and_contract`: Float months for readability
- `timing_window_range`: [min_days, max_days] this transaction fell into
- `timing_window_label`: "immediate" | "near_term" | "extended" | "beyond_window"
- `timing_score`: Contribution to final score
- `note`: Explanation of timing window match

### Interpretation

- `days_between_award_and_contract < 90` → Strong signal (0.20 contribution)
- `90 ≤ days < 365` → Moderate signal (0.15 contribution)
- `365 ≤ days < 730` → Weak signal (0.10 contribution)
- `days ≥ 730` → No contribution (0.0)

### Competition Type Signal

```json
{
  "competition_type": {
    "enabled": true,
    "snippet": "Sole source procurement (vendor-targeted)",
    "score_contribution": 0.04,
    "details": {
      "competition_type": "SOLE_SOURCE",
      "usaspending_code": "NONE",
      "competition_score": 0.04,
      "note": "Sole source indicates vendor was specifically targeted"
    }
  }
}
```

### Fields

- `competition_type`: "SOLE_SOURCE" | "LIMITED" | "FULL_AND_OPEN" | "UNKNOWN"
- `usaspending_code`: Original code from USAspending (FULL, NONE, LIMITED, etc.)
- `competition_score`: Contribution to final score
- `note`: Human interpretation

### Interpretation

- `competition_type: SOLE_SOURCE` → Strong signal (0.04 contribution)
- `competition_type: LIMITED` → Moderate signal (0.02 contribution)
- `competition_type: FULL_AND_OPEN` → No signal (0.0)

### Patent Signal

```json
{
  "patent_signal": {
    "enabled": true,
    "snippet": "2 patents filed; 1 pre-contract filing; 0.76 topic similarity",
    "score_contribution": 0.012,
    "details": {
      "patents_found": 2,
      "patent_ids": ["US10123456B2", "US20230123456"],
      "has_patent_bonus": 0.05,
      "pre_contract_patents": 1,
      "pre_contract_bonus": 0.03,
      "topic_similarity_scores": [0.76, 0.42],
      "max_topic_similarity": 0.76,
      "topic_match_threshold": 0.7,
      "topic_match_bonus": 0.02,
      "total_patent_bonus": 0.08,
      "patent_signal_score": 0.012,
      "note": "Max topic similarity (0.76) exceeds 0.7 threshold"
    }
  }
}
```

### Fields

- `patents_found`: Integer count of patents associated with award
- `patent_ids`: List of patent identifiers (US numbers or publication numbers)
- `has_patent_bonus`: Contribution if patents exist (0.05)
- `pre_contract_patents`: Count of patents filed before contract start
- `pre_contract_bonus`: Contribution per pre-contract patent (0.03)
- `topic_similarity_scores`: List of TF-IDF similarity scores (0.0-1.0)
- `max_topic_similarity`: Maximum similarity across all patents
- `topic_match_threshold`: Threshold for similarity bonus (0.7)
- `topic_match_bonus`: Contribution if similarity ≥ threshold (0.02)
- `total_patent_bonus`: Sum of all bonuses before weighting
- `patent_signal_score`: Weighted contribution to final score
- `note`: Explanation of patent findings

### Interpretation

- `patents_found > 0 AND pre_contract_patents > 0 AND max_topic_similarity ≥ 0.7` → Strong patent signal
- `patents_found > 0 AND pre_contract_patents == 0` → Weak patent signal
- `patents_found == 0` → No patent signal

### CET Alignment Signal

```json
{
  "cet_alignment": {
    "enabled": true,
    "snippet": "CET area match (AI & Machine Learning)",
    "score_contribution": 0.005,
    "details": {
      "award_cet": "AI & Machine Learning",
      "contract_cet": "AI & Machine Learning",
      "cet_inference_method": "keyword_matching",
      "cet_inference_confidence": 0.92,
      "cet_match_type": "exact_match",
      "cet_alignment_score": 0.05,
      "cet_signal_score": 0.005,
      "note": "Exact match on CET area indicates technology consistency"
    }
  }
}
```

### Fields

- `award_cet`: CET area from SBIR award classification (explicit)
- `contract_cet`: CET area inferred from contract description (algorithmic)
- `cet_inference_method`: "keyword_matching" | "ml_classifier" | "manual" | "none"
- `cet_inference_confidence`: Confidence in contract CET inference (0.0-1.0)
- `cet_match_type`: "exact_match" | "partial_match" | "no_match"
- `cet_alignment_score`: Raw signal bonus before weighting (0.05 for match)
- `cet_signal_score`: Weighted contribution to final score (0.005)
- `note`: Explanation of CET matching

### Interpretation

- `cet_match_type: exact_match` → Moderate signal (0.005 contribution)
- `cet_match_type: partial_match` → Weak signal (0.0)
- `cet_match_type: no_match` → No signal (0.0)

### Vendor Match Signal

```json
{
  "vendor_match": {
    "enabled": true,
    "snippet": "UEI exact match (ABC123DEF456)",
    "score_contribution": 0.01,
    "confidence": 0.99,
    "details": {
      "match_method": "UEI",
      "award_uei": "ABC123DEF456",  # pragma: allowlist secret
      "contract_uei": "ABC123DEF456",  # pragma: allowlist secret
      "match_score": 0.10,
      "vendor_match_signal_score": 0.01,
      "note": "Definitive UEI match confirms same vendor"
    }
  }
}
```

### Fields

- `match_method`: "UEI" | "CAGE" | "DUNS" | "FUZZY_NAME" | "NONE"
- `award_uei`: Award recipient's UEI (if available)
- `contract_uei`: Contract vendor's UEI (if available)
- `award_cage`: Award recipient's CAGE code (if available)
- `contract_cage`: Contract vendor's CAGE code (if available)
- `award_duns`: Award recipient's DUNS (if available)
- `contract_duns`: Contract vendor's DUNS (if available)
- `award_name`: Award recipient's legal name (if fuzzy match)
- `contract_name`: Contract vendor's legal name (if fuzzy match)
- `fuzzy_similarity_score`: Text similarity score (0.0-1.0) if fuzzy match
- `match_score`: Bonus before weighting (0.10 for UEI)
- `vendor_match_signal_score`: Weighted contribution to final score
- `confidence`: Confidence in this match (0.99 for UEI, varies for fuzzy)
- `note`: Explanation of vendor matching

### Interpretation

- `match_method: UEI` → Definitive match (confidence: 0.99)
- `match_method: CAGE` → Very strong match (confidence: 0.95)
- `match_method: DUNS` → Strong match (confidence: 0.90)
- `match_method: FUZZY_NAME` → Probabilistic match (confidence: 0.65-0.85)
- `match_method: NONE` → No match (confidence: 0.0)

### Contract Details

<!-- pragma: allowlist secret -->
```json
{
  "contract_details": {
    "piid": "FA1234-20-C-0001",
    "parent_piid": null,
    "agency": "Department of Defense",
    "agency_code": "17",
    "sub_agency": "Department of the Air Force",
    "sub_agency_code": "5700",
    "vendor_name": "Acme AI Inc.",
    "vendor_uei": "ABC123DEF456",
    "vendor_cage": null,
    "vendor_duns": null,
    "action_date": "2023-03-01",
    "period_of_performance_start_date": "2023-03-01",
    "period_of_performance_end_date": "2025-03-01",
    "obligated_amount": 500000,
    "base_and_all_options_value": 1000000,
    "competition_type": "SOLE_SOURCE",
    "extent_competed": "NONE",
    "description": "Development of AI-powered threat detection system for advanced warning capabilities",
    "naics_code": "541511",
    "primary_place_of_performance": "Arlington, VA",
    "note": "Phase II transition to Air Force Research Laboratory contract"
  }
}
```

### Fields

- `piid`: Contract identifier (Procurement Instrument Identifier)
- `parent_piid`: Parent contract if this is task order/child
- `agency`: Full agency name
- `agency_code`: Numeric agency code
- `sub_agency`: Sub-agency name (e.g., service branch)
- `sub_agency_code`: Sub-agency numeric code
- `vendor_name`: Contractor legal name
- `vendor_uei`: Contractor UEI (if available)
- `vendor_cage`: Contractor CAGE code (if available)
- `vendor_duns`: Contractor DUNS (if available)
- `action_date`: Date contract was signed/awarded
- `period_of_performance_start_date`: Contract start date
- `period_of_performance_end_date`: Contract end date
- `obligated_amount`: Amount committed (in dollars)
- `base_and_all_options_value`: Full potential value including options
- `competition_type`: "SOLE_SOURCE" | "LIMITED" | "FULL_AND_OPEN" | "UNKNOWN"
- `extent_competed`: Original code from data source
- `description`: Statement of work or contract description
- `naics_code`: Industry classification
- `primary_place_of_performance`: Location where work performed
- `note`: Additional context

### Award Details

```json
{
  "award_details": {
    "award_id": "SBIR-2020-PHASE-II-001",
    "phase": "II",
    "program": "SBIR",
    "topic_code": "AF20-028",
    "topic_title": "Advanced Neural Networks for Threat Detection",
    "agency": "Department of Defense",
    "agency_code": "17",
    "sub_agency": "Department of the Air Force",
    "sub_agency_code": "5700",
    "award_amount": 150000,
    "recipient_name": "Acme AI Inc.",
    "recipient_uei": "ABC123DEF456",
    "recipient_duns": null,
    "recipient_state": "VA",
    "award_date": "2021-09-01",
    "completion_date": "2023-01-15",
    "cet_area": "AI & Machine Learning",
    "description": "Development of federated learning techniques for distributed threat detection",
    "note": "High-performing SBIR award with demonstrated patent activity"
  }
}
```

### Fields

- `award_id`: SBIR award identifier
- `phase`: "I" | "II" | "IIB" | "III"
- `program`: "SBIR" | "STTR"
- `topic_code`: Topic classification
- `topic_title`: Award title/topic
- `agency`: Awarding agency name
- `agency_code`: Numeric agency code
- `sub_agency`: Sub-agency name
- `sub_agency_code`: Sub-agency numeric code
- `award_amount`: Award funding amount (dollars)
- `recipient_name`: Company/recipient legal name
- `recipient_uei`: Recipient UEI
- `recipient_duns`: Recipient DUNS (if available)
- `recipient_state`: State where recipient located
- `award_date`: Date award granted
- `completion_date`: Phase completion date
- `cet_area`: Critical & Emerging Technology area
- `description`: Research description/abstract
- `note`: Context for analysis

### Validation Object

```json
{
  "validation": {
    "completeness": "PASS",
    "completeness_details": {
      "required_fields_present": ["award_id", "contract_id", "likelihood_score", "confidence"],
      "optional_fields_present": ["summary", "signals"],
      "missing_optional": []
    },
    "score_valid": true,
    "score_validation_details": {
      "score_in_range": true,
      "score_min": 0.0,
      "score_max": 1.0,
      "actual_score": 0.75
    },
    "signal_scores_sum_to_likelihood": true,
    "signal_scores_detail": {
      "base_score": 0.15,
      "signals_total": 0.60,
      "expected_score": 0.75,
      "actual_score": 0.75,
      "match": true
    },
    "no_errors": true,
    "no_warnings": false,
    "warnings": [],
    "note": "Bundle structure and scoring validated successfully"
  }
}
```

### Fields

- `completeness`: "PASS" | "FAIL" (all required fields present)
- `completeness_details`: Details of field validation
- `score_valid`: Boolean (likelihood_score in [0.0, 1.0])
- `score_validation_details`: Details of score range check
- `signal_scores_sum_to_likelihood`: Boolean (signals sum to overall score)
- `signal_scores_detail`: Detailed breakdown of scoring
- `no_errors`: Boolean (no critical issues found)
- `no_warnings`: Boolean (no warnings generated)
- `warnings`: List of warning messages (if any)
- `note`: Explanation of validation result

## Example Evidence Bundles

### Example 1: High-Confidence Transition

```json
{
  "transition_id": "trans_a1b2c3d4e5f6",
  "award_id": "SBIR-2020-PHASE-II-001",
  "contract_id": "FA1234-20-C-0001",
  "likelihood_score": 0.8275,
  "confidence": "LIKELY",
  "detection_date": "2024-01-15T10:30:00Z",
  "detection_method": "transition_detector_v1",
  "summary": "DoD Phase II award (Acme AI) → Air Force sole source contract 45 days post-completion",
  
  "signals": {
    "agency_continuity": {
      "enabled": true,
      "snippet": "Same agency (DoD → DoD Air Force)",
      "score_contribution": 0.0625,
      "details": {
        "match_type": "same_department",
        "award_agency": "Department of Defense",
        "contract_agency": "Department of the Air Force",
        "same_agency": false,
        "same_department": true
      }
    },
    "timing_proximity": {
      "enabled": true,
      "snippet": "45 days (immediate commercialization)",
      "score_contribution": 0.20,
      "details": {
        "days_between_award_and_contract": 45,
        "months_between_award_and_contract": 1.5,
        "timing_window_range": [0, 90],
        "timing_window_label": "immediate"
      }
    },
    "competition_type": {
      "enabled": true,
      "snippet": "Sole source (vendor-targeted)",
      "score_contribution": 0.04,
      "details": {
        "competition_type": "SOLE_SOURCE",
        "usaspending_code": "NONE"
      }
    },
    "patent_signal": {
      "enabled": true,
      "snippet": "2 patents; 1 pre-contract; 0.76 topic similarity",
      "score_contribution": 0.012,
      "details": {
        "patents_found": 2,
        "pre_contract_patents": 1,
        "max_topic_similarity": 0.76
      }
    },
    "cet_alignment": {
      "enabled": true,
      "snippet": "CET match (AI & Machine Learning)",
      "score_contribution": 0.005,
      "details": {
        "award_cet": "AI & Machine Learning",
        "contract_cet": "AI & Machine Learning",
        "cet_match_type": "exact_match"
      }
    },
    "vendor_match": {
      "enabled": true,
      "snippet": "UEI exact match",
      "score_contribution": 0.01,
      "confidence": 0.99,
      "details": {
        "match_method": "UEI",
        "award_uei": "ABC123DEF456",
        "contract_uei": "ABC123DEF456"
      }
    }
  },
  
  "contract_details": {
    "piid": "FA1234-20-C-0001",
    "agency": "Department of Defense",
    "sub_agency": "Department of the Air Force",
    "vendor_name": "Acme AI Inc.",
    "vendor_uei": "ABC123DEF456",
    "action_date": "2023-03-01",
    "obligated_amount": 500000,
    "competition_type": "SOLE_SOURCE",
    "description": "Development of AI-powered threat detection system"
  },
  
  "award_details": {
    "award_id": "SBIR-2020-PHASE-II-001",
    "phase": "II",
    "program": "SBIR",
    "agency": "Department of Defense",
    "sub_agency": "Department of the Air Force",
    "award_amount": 150000,
    "recipient_name": "Acme AI Inc.",
    "recipient_uei": "ABC123DEF456",
    "award_date": "2021-09-01",
    "completion_date": "2023-01-15",
    "cet_area": "AI & Machine Learning",
    "description": "Federated learning for distributed threat detection"
  },
  
  "validation": {
    "completeness": "PASS",
    "score_valid": true,
    "signal_scores_sum_to_likelihood": true,
    "no_errors": true,
    "no_warnings": false
  }
}
```

### Analysis

- **Likelihood Score (0.8275)**: Base (0.15) + Agency (0.0625) + Timing (0.20) + Competition (0.04) + Patent (0.012) + CET (0.005) + Vendor (0.01) = 0.8275
- **Confidence**: LIKELY (0.8275 ≥ 0.65, < 0.85)
- **Key Indicators**:
  - UEI exact match (definitive vendor confirmation)
  - Immediate timing (45 days, strong commercialization signal)
  - Sole source (vendor-specific procurement)
  - Patent backing (technology matured)
  - CET alignment (focus consistency)
- **Reliability**: Very High (multiple strong signals, all pointing same direction)

### Example 2: Moderate-Confidence Transition

```json
{
  "transition_id": "trans_b2c3d4e5f6a7",
  "award_id": "SBIR-2019-PHASE-II-042",
  "contract_id": "NSF-2020-1234567",
  "likelihood_score": 0.5825,
  "confidence": "POSSIBLE",
  "detection_date": "2024-01-15T10:30:00Z",
  "summary": "NSF Phase II award → NSF contract 8 months later; fuzzy name match (0.82)",
  
  "signals": {
    "agency_continuity": {
      "enabled": true,
      "snippet": "Same agency (NSF → NSF)",
      "score_contribution": 0.0625,
      "details": {
        "match_type": "same_agency",
        "award_agency": "National Science Foundation",
        "contract_agency": "National Science Foundation",
        "same_agency": true
      }
    },
    "timing_proximity": {
      "enabled": true,
      "snippet": "245 days (8 months, near-term)",
      "score_contribution": 0.15,
      "details": {
        "days_between_award_and_contract": 245,
        "months_between_award_and_contract": 8.1,
        "timing_window_range": [91, 365],
        "timing_window_label": "near_term"
      }
    },
    "competition_type": {
      "enabled": true,
      "snippet": "Full and open (general competition)",
      "score_contribution": 0.0,
      "details": {
        "competition_type": "FULL_AND_OPEN",
        "usaspending_code": "FULL"
      }
    },
    "patent_signal": {
      "enabled": true,
      "snippet": "No patents found",
      "score_contribution": 0.0,
      "details": {
        "patents_found": 0,
        "pre_contract_patents": 0,
        "max_topic_similarity": 0.0
      }
    },
    "cet_alignment": {
      "enabled": true,
      "snippet": "No CET data available",
      "score_contribution": 0.0,
      "details": {
        "award_cet": null,
        "contract_cet": null,
        "cet_match_type": "no_data"
      }
    },
    "vendor_match": {
      "enabled": true,
      "snippet": "Fuzzy name match (0.82)",
      "score_contribution": 0.0032,
      "confidence": 0.82,
      "details": {
        "match_method": "FUZZY_PRIMARY",
        "award_name": "Beta Research Associates",
        "contract_name": "Beta Research Assoc.",
        "fuzzy_similarity_score": 0.82
      }
    }
  },
  
  "contract_details": {
    "piid": "NSF-2020-1234567",
    "agency": "National Science Foundation",
    "vendor_name": "Beta Research Assoc.",
    "action_date": "2020-09-15",
    "obligated_amount": 250000,
    "competition_type": "FULL_AND_OPEN",
    "description": "Advanced materials research and commercialization"
  },
  
  "award_details": {
    "award_id": "SBIR-2019-PHASE-II-042",
    "phase": "II",
    "program": "SBIR",
    "agency": "National Science Foundation",
    "award_amount": 175000,
    "recipient_name": "Beta Research Associates",
    "recipient_uei": null,
    "award_date": "2019-09-01",
    "completion_date": "2020-01-15",
    "description": "Development of advanced composite materials"
  },
  
  "validation": {
    "completeness": "PASS",
    "score_valid": true,
    "no_errors": true,
    "no_warnings": true
  }
}
```

### Analysis

- **Likelihood Score (0.5825)**: Base (0.15) + Agency (0.0625) + Timing (0.15) + Competition (0.0) + Patent (0.0) + CET (0.0) + Vendor (0.0032) = 0.5825
- **Confidence**: POSSIBLE (0.5825 < 0.65)
- **Key Indicators**:
  - Fuzzy name match (probabilistic, not definitive)
  - Same agency (good signal)
  - Near-term timing (moderate signal)
  - No patents (weak signal)
  - Full and open competition (no vendor-targeting signal)
- **Concerns**:
  - No exact vendor identifier match
  - No patent backing
  - Generic contract description
  - Open competition (could be unrelated company)
- **Reliability**: Moderate (requires manual verification)
- **Recommendation**: Include in broad discovery, exclude from executive summary

## JSON Persistence

### NDJSON Format

Evidence bundles are persisted as newline-delimited JSON:

```text
{"transition_id": "trans_a1b2c3d4e5f6", "award_id": "SBIR-001", ...}
{"transition_id": "trans_b2c3d4e5f6a7", "award_id": "SBIR-042", ...}
```

**File**: `data/processed/transitions_evidence.ndjson`

### Advantages

- One JSON object per line (streamable)
- Efficient for large datasets
- Easy to parse line-by-line

### Neo4j Storage

Evidence bundles are stored as JSON on relationship properties:

```cypher
MATCH (a:Award)-[t:TRANSITIONED_TO]->(c:Contract)
WHERE t.transition_id = "trans_a1b2c3d4e5f6"
RETURN t.evidence_bundle
```

**Storage Location**: `TRANSITIONED_TO.evidence_bundle` (JSON string)

### Advantages

- Queryable as relationship properties
- Linked to both award and contract nodes
- Supports graph traversal

## Validation & Quality

### Completeness Checks

```python
def validate_bundle(bundle: dict) -> dict:
    """Validate evidence bundle structure."""
    
    required_fields = [
        'transition_id', 'award_id', 'contract_id',
        'likelihood_score', 'confidence', 'detection_date'
    ]
    
    missing = [f for f in required_fields if f not in bundle]
    
    return {
        'valid': len(missing) == 0,
        'missing_fields': missing,
        'field_count': len(bundle)
    }
```

### Score Verification

```python
def verify_score_calculation(bundle: dict) -> bool:
    """Verify likelihood score matches sum of signals."""
    
    base_score = 0.15  # Assuming default
    signal_contributions = [
        bundle['signals'][sig].get('score_contribution', 0.0)
        for sig in bundle['signals'].keys()
        if bundle['signals'][sig].get('enabled', False)
    ]
    
    expected_score = base_score + sum(signal_contributions)
    actual_score = bundle['likelihood_score']
    
    return abs(expected_score - actual_score) < 0.001  # Allow floating point tolerance
```

### Usage Examples

```python

## Load evidence bundle

import json
import pandas as pd

## Load from NDJSON

with open('data/processed/transitions_evidence.ndjson') as f:
    bundles = [json.loads(line) for line in f]

## Filter by confidence

likely_bundles = [b for b in bundles if b['confidence'] in ['LIKELY', 'HIGH']]

## Extract signals for analysis

agency_scores = [
    b['signals']['agency_continuity']['score_contribution']
    for b in bundles
]

## Find all HIGH confidence transitions with patent backing

high_confidence_patent_backed = [
    b for b in bundles
    if b['confidence'] == 'HIGH' and 
    b['signals']['patent_signal']['details']['patents_found'] > 0
]
```

## Troubleshooting

### Issue: Score Doesn't Match Sum of Signals

**Cause**: Rounding errors or scoring logic mismatch

### Solution

```python

## Check detailed breakdown

bundle['validation']['signal_scores_detail']

## Should show base_score + signals_total = expected_score

```

### Issue: Missing Signal Information

**Cause**: Signal not applicable or data unavailable

**Solution**: Check `enabled` flag and `details` object for explanation

### Issue: Vendor Match Confidence Very Low

**Cause**: Fuzzy matching or missing identifiers

**Solution**: Review `vendor_match.details.match_method`:
- UEI/CAGE/DUNS: Very reliable
- FUZZY_PRIMARY/FUZZY_SECONDARY: Requires manual verification
- NONE: No match found

## Best Practices

1. **Always Include Summary**: One-liner explaining key findings
2. **Validate Bundles**: Run validation checks before export
3. **Preserve Metadata**: Keep detection date and method version
4. **Document Assumptions**: Note if signals were disabled/adjusted
5. **Enable Auditability**: Ensure reproducibility from bundle data
6. **Update Regularly**: Recalculate bundles if algorithm changes
7. **Archive Historical**: Keep old bundles for trend analysis

## References

- **Implementation**: `src/transition/detection/evidence.py`
- **Storage**: `data/processed/transitions_evidence.ndjson`
- **Neo4j**: `TRANSITIONED_TO.evidence_bundle`
- **Tests**: `tests/unit/test_evidence_generator.py`
