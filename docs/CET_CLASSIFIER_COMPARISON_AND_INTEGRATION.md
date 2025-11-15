# CET Classifier Comparison & Integration Plan

**Date**: 2025-11-13
**Status**: Analysis Complete
**Purpose**: Compare archived `sbir-cet-classifier` with current `sbir-etl` CET implementation and identify integration opportunities

---

## Executive Summary

The **sbir-cet-classifier** (now archived) and **sbir-etl** both implement CET classification systems, but with different approaches and features. This document analyzes both implementations and recommends specific enhancements that can be integrated into sbir-etl.

### Key Findings

1. **Current sbir-etl** uses a clean, production-grade TF-IDF + Logistic Regression approach
2. **Archived classifier** offers several advanced features not present in sbir-etl:
   - Rule-based scoring with agency/branch priors
   - Enhanced multi-source vectorization (solicitation text integration)
   - Negative keyword filtering
   - Context-aware rules for keyword combinations
   - More granular configuration

---

## Architecture Comparison

### sbir-etl (Current Implementation)

```
┌─────────────────────────────────────────────────┐
│ CETAwareTfidfVectorizer                         │
│ - Keyword boosting (2.0x multiplier)            │
│ - Bigram support (1,2)                          │
│ - Chi-squared feature selection                 │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ Binary Logistic Regression (per CET)            │
│ - Calibrated probabilities (sigmoid, CV=3)     │
│ - Class weighting: balanced                    │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ Thresholding                                    │
│ - HIGH: ≥70                                     │
│ - MEDIUM: 40-69                                 │
│ - LOW: <40                                      │
└─────────────────────────────────────────────────┘
```

**Strengths:**
- Clean architecture with separation of concerns
- Well-tested and integrated into Dagster pipeline
- Batch processing optimized (10-15K awards/minute)
- Quality gates and validation built-in
- Neo4j integration complete

**Limitations:**
- No agency/branch contextual priors
- No negative keyword filtering
- No solicitation text integration
- Single text source (abstract only)

---

### sbir-cet-classifier (Archived)

```
┌─────────────────────────────────────────────────┐
│ MultiSourceTextVectorizer                       │
│ - Abstract (weight: 0.5)                        │
│ - Keywords (weight: 0.2)                        │
│ - Solicitation text (weight: 0.3)               │
│ - Trigram support (1,3)                         │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ Logistic Regression + RuleBasedScorer           │
│ - ML probabilities                              │
│ - Agency priors (e.g., DoD → hypersonics +15)  │
│ - Branch priors (e.g., DARPA → quantum +15)    │
│ - Keyword rules (core/related/negative)        │
│ - Context rules (keyword combinations)         │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ Hybrid Scoring                                  │
│ - Combines ML + rule-based scores              │
│ - Same thresholds (70/40)                       │
└─────────────────────────────────────────────────┘
```

**Strengths:**
- Hybrid ML + rule-based approach
- Agency/branch contextual awareness
- Negative keyword filtering (reduces false positives)
- Multi-source text integration
- Context-aware rules for ambiguous cases

**Limitations:**
- More complex architecture
- No Neo4j integration
- Archived (no longer maintained)
- Less sophisticated ETL pipeline

---

## Detailed Feature Comparison

| Feature | sbir-etl | Archived Classifier | Impact |
|---------|----------|---------------------|--------|
| **ML Model** | TF-IDF + LogReg | TF-IDF + LogReg | ✓ Same |
| **Calibration** | Sigmoid, CV=3 | Sigmoid, CV=3 | ✓ Same |
| **N-gram Range** | (1,2) bigrams | (1,3) trigrams | ⚠ Minor |
| **Max Features** | 5,000 | 50,000 | ⚠ Moderate |
| **Feature Selection** | Chi2, k=3000 | Chi2, k=20000 | ⚠ Moderate |
| **Keyword Boosting** | ✓ 2.0x | ✗ None | ⚠ Different |
| **Agency Priors** | ✗ None | ✓ 16 agencies | ★ High |
| **Branch Priors** | ✗ None | ✓ 12 branches | ★ High |
| **Negative Keywords** | ✗ None | ✓ Per-CET lists | ★ High |
| **Context Rules** | ✗ None | ✓ Keyword combos | ★ Moderate |
| **Multi-source Text** | ✗ Abstract only | ✓ Abstract + Keywords + Solicitation | ★ High |
| **Stop Words** | ✗ None | ✓ 50+ SBIR terms | ⚠ Moderate |
| **Neo4j Integration** | ✓ Complete | ✗ None | N/A |
| **Dagster Pipeline** | ✓ Complete | ✗ None | N/A |

**Legend:**
- ✓ = Feature present
- ✗ = Feature absent
- ★ = High-value integration opportunity
- ⚠ = Moderate-value enhancement

---

## Integration Opportunities (Prioritized)

### Priority 1: High-Value, Low-Risk Enhancements

#### 1.1 Agency/Branch Priors (★★★★★)
**What**: Add contextual score adjustments based on funding agency/branch
**Why**: Improves classification accuracy by leveraging known agency focus areas
**Example**: DoD awards get +15 boost for hypersonics, NIH awards get +20 for medical devices

**Implementation**:
```python
# Add to config/cet/classification.yaml
agency_priors:
  Department of Defense:
    hypersonics: 15
    autonomous_systems: 15
    directed_energy: 15
  Department of Health and Human Services:
    biotechnologies: 20
    # ... etc
```

**Effort**: Low (2-3 hours)
**Risk**: Low (additive scoring, easily reversible)
**Files to modify**:
- `config/cet/classification.yaml` (new section)
- `src/ml/models/cet_classifier.py` (add prior adjustment in `_get_scores`)

---

#### 1.2 Negative Keyword Filtering (★★★★★)
**What**: Subtract points when negative keywords are detected
**Why**: Reduces false positives (e.g., "quantum mechanics" ≠ "quantum computing")

**Implementation**:
```python
# Add to CETArea model
class CETArea(BaseModel):
    cet_id: str
    name: str
    keywords: list[str]
    negative_keywords: list[str] = []  # NEW

# In classifier, check negative keywords
if any(neg_kw in text.lower() for neg_kw in area.negative_keywords):
    score *= 0.7  # Apply penalty multiplier
```

**Effort**: Low (2-3 hours)
**Risk**: Low (conservative penalty, optional feature)
**Files to modify**:
- `src/models/cet_models.py` (add field)
- `config/cet/taxonomy.yaml` (add negative keywords per CET)
- `src/ml/models/cet_classifier.py` (apply filtering)

---

#### 1.3 Stop Words List (★★★☆☆)
**What**: Filter out generic SBIR/proposal terms from vectorization
**Why**: Reduces noise from boilerplate language

**Implementation**:
```python
# In CETAwareTfidfVectorizer.__init__
sbir_stop_words = [
    "phase", "sbir", "sttr", "award", "contract",
    "proposal", "program", "project", "research",
    "development", "technology", "technical"
]
super().__init__(stop_words=sbir_stop_words, **kwargs)
```

**Effort**: Very Low (1 hour)
**Risk**: Very Low (standard NLP practice)
**Files to modify**:
- `src/ml/models/cet_classifier.py`
- `config/cet/classification.yaml` (new section)

---

### Priority 2: Medium-Value, Moderate-Risk Enhancements

#### 2.1 Multi-Source Text Vectorization (★★★★☆)
**What**: Incorporate keywords and solicitation text alongside abstract
**Why**: More context improves classification, especially for short abstracts

**Current**: Only abstract is classified
**Enhanced**: Weighted combination of abstract (50%) + keywords (20%) + solicitation (30%)

**Implementation**:
- Adapt `MultiSourceTextVectorizer` from archived repo
- Add weight configuration to `classification.yaml`
- Update training data preparation to include all text sources

**Effort**: Medium (1 day)
**Risk**: Moderate (requires retraining, validation needed)
**Files to modify**:
- `src/ml/models/cet_classifier.py` (new vectorizer class)
- `src/assets/cet_assets.py` (update training data prep)

---

#### 2.2 Context-Aware Rules (★★★☆☆)
**What**: Boost specific CETs when keyword combinations are present
**Why**: Handles ambiguous cases (e.g., "AI + medical" → medical_devices, not artificial_intelligence)

**Example Rules**:
```yaml
context_rules:
  medical_devices:
    - [["ai", "diagnostic"], +20]
    - [["machine learning", "clinical"], +20]
  advanced_manufacturing:
    - [["ai", "manufacturing"], +20]
```

**Effort**: Medium (4-6 hours)
**Risk**: Moderate (requires careful rule design, validation)
**Files to modify**:
- `config/cet/classification.yaml` (new section)
- `src/ml/models/cet_classifier.py` (rule evaluation logic)

---

#### 2.3 Increase N-gram Range (★★☆☆☆)
**What**: Add trigrams to current bigram support
**Why**: Captures longer phrases like "quantum error correction"

**Current**: `ngram_range=(1,2)`
**Enhanced**: `ngram_range=(1,3)`

**Effort**: Very Low (config change + retrain)
**Risk**: Low (may increase features, requires validation)
**Trade-off**: Higher memory/compute for marginal accuracy gain

---

#### 2.4 Increase Feature Limits (★★☆☆☆)
**What**: Expand max features from 5K → 20K and feature selection from 3K → 10K
**Why**: More vocabulary coverage for technical terminology

**Effort**: Very Low (config change + retrain)
**Risk**: Low (may increase training time)
**Trade-off**: Better recall, slightly slower inference

---

### Priority 3: Research/Experimental (Future Work)

#### 3.1 Hybrid ML + Rule-Based Scoring
**What**: Ensemble approach combining calibrated probabilities with rule-based scores
**Why**: Potentially more robust, interpretable

**Approach**: `final_score = 0.7 * ml_score + 0.3 * rule_score`

**Effort**: High (1-2 weeks)
**Risk**: High (complex validation, may not improve accuracy)

---

#### 3.2 Evidence Extraction with spaCy
**What**: Extract supporting sentences that justify classification
**Why**: Improves transparency, enables auditing

**Note**: Archived classifier uses spaCy for this
**Status**: Not critical for current ETL pipeline

---

## Taxonomy Differences

### CET Area Coverage

| CET Area | sbir-etl | Archived |
|----------|----------|----------|
| Total Areas | 21 | 21 |
| Structure | Flat (no hierarchy) | Hierarchical (with parent_cet_id) |
| Keywords per Area | ~10 | ~5-10 |

**Notable Differences**:

1. **Hierarchical Taxonomy** (Archived only):
   - `quantum_sensing` is a child of `quantum_computing`
   - `thermal_protection` is a child of `advanced_materials`
   - Allows for nested classification

2. **Keyword Granularity**:
   - sbir-etl: More keywords, broader coverage
   - Archived: Fewer keywords, more targeted (with negative keywords)

3. **Uncategorized Handling**:
   - Archived has explicit "none/uncategorized" CET
   - sbir-etl uses thresholds to filter low-confidence matches

---

## Recommended Integration Roadmap

### Phase 1: Quick Wins (1 week)
1. ✓ Add stop words list
2. ✓ Add negative keywords to taxonomy
3. ✓ Implement agency/branch priors
4. ✓ Update configuration schema

**Deliverables**:
- Enhanced `config/cet/taxonomy.yaml` with negative keywords
- New `agency_priors` section in `config/cet/classification.yaml`
- Updated `CETAwareTfidfVectorizer` with stop words
- Prior adjustment logic in `ApplicabilityModel._get_scores()`

### Phase 2: Multi-Source Enhancement (2 weeks)
1. ✓ Adapt `MultiSourceTextVectorizer` from archived repo
2. ✓ Update data models to include keywords and solicitation text
3. ✓ Retrain classifiers with multi-source input
4. ✓ Validate accuracy improvements

**Deliverables**:
- New `MultiSourceCETVectorizer` class
- Updated training pipeline
- Validation report comparing single-source vs multi-source

### Phase 3: Context Rules (1 week)
1. ✓ Design context rule schema
2. ✓ Implement rule evaluation engine
3. ✓ Populate initial rules based on archived classifier
4. ✓ Add integration tests

**Deliverables**:
- Context rule evaluation in classifier
- Documented rules in `classification.yaml`
- Test coverage for rule engine

### Phase 4: Validation & Tuning (1-2 weeks)
1. ✓ Retrain all CET classifiers with enhancements
2. ✓ Run drift detection against baseline
3. ✓ Compare classification accuracy on test set
4. ✓ Optimize hyperparameters if needed
5. ✓ Update quality gates

**Deliverables**:
- Performance comparison report
- Updated model artifacts
- Documentation updates

---

## Risk Mitigation

### 1. Classification Drift
**Risk**: Changes may alter existing classifications
**Mitigation**:
- Use `scripts/run_cet_drift.py` to measure drift before deployment
- Set drift threshold at 10% (flag for manual review)
- Test on sample of 1,000 awards first

### 2. Performance Degradation
**Risk**: More features/rules may slow inference
**Mitigation**:
- Benchmark with `scripts/performance/profile_cet_performance.py`
- Target: maintain 10K+ awards/minute throughput
- Monitor memory usage during batch processing

### 3. Accuracy Regression
**Risk**: New features may decrease accuracy on edge cases
**Mitigation**:
- Split test set (20%) before any changes
- Require ≥95% agreement with baseline on test set
- Human review of top 100 disagreements

### 4. Configuration Complexity
**Risk**: More config options increase maintenance burden
**Mitigation**:
- Add config validation with Pydantic schemas
- Document all parameters with examples
- Provide sensible defaults for all optional features

---

## Implementation Guidelines

### Code Style
- Follow existing patterns in `src/ml/models/cet_classifier.py`
- Use Pydantic models for all config structures
- Add type hints to all new functions
- Maintain 85%+ test coverage

### Testing Strategy
1. **Unit tests**: Test each enhancement in isolation
2. **Integration tests**: Test full classification pipeline
3. **Regression tests**: Ensure backward compatibility
4. **Performance tests**: Validate throughput targets

### Configuration Management
- Keep enhancements optional (feature flags)
- Allow gradual rollout per enhancement
- Document all new config sections
- Provide migration guide for existing configs

---

## Appendix: Code Examples

### A. Agency Prior Implementation

```python
# In src/ml/models/cet_classifier.py

def _apply_agency_priors(self, scores: dict[str, float], agency: str | None) -> dict[str, float]:
    """
    Apply agency-specific score adjustments.

    Args:
        scores: Base classification scores
        agency: Funding agency name

    Returns:
        Adjusted scores
    """
    if not agency:
        return scores

    priors = self.config.get("agency_priors", {}).get(agency, {})

    adjusted_scores = scores.copy()
    for cet_id, boost in priors.items():
        if cet_id == "_all_cets":
            # Apply baseline boost to all CETs
            for cet in adjusted_scores:
                adjusted_scores[cet] = min(100.0, adjusted_scores[cet] + boost)
        elif cet_id in adjusted_scores:
            adjusted_scores[cet_id] = min(100.0, adjusted_scores[cet_id] + boost)

    return adjusted_scores
```

### B. Negative Keyword Implementation

```python
# In src/ml/models/cet_classifier.py

def _apply_negative_keyword_penalty(
    self,
    score: float,
    text: str,
    negative_keywords: list[str]
) -> float:
    """
    Reduce score if negative keywords are present.

    Args:
        score: Base classification score
        text: Document text
        negative_keywords: List of keywords that indicate false positive

    Returns:
        Penalized score
    """
    text_lower = text.lower()
    penalty_multiplier = 1.0

    for neg_kw in negative_keywords:
        if neg_kw.lower() in text_lower:
            penalty_multiplier *= 0.7  # 30% reduction per negative keyword

    return score * penalty_multiplier
```

### C. Multi-Source Vectorizer Adapter

```python
# New file: src/ml/models/multi_source_vectorizer.py

class MultiSourceCETVectorizer:
    """
    TF-IDF vectorizer that combines multiple text sources with weights.

    Adapted from sbir-cet-classifier for sbir-etl integration.
    """

    def __init__(
        self,
        abstract_weight: float = 0.5,
        keywords_weight: float = 0.2,
        solicitation_weight: float = 0.3,
        **tfidf_params
    ):
        assert abs(abstract_weight + keywords_weight + solicitation_weight - 1.0) < 1e-6

        self.weights = {
            "abstract": abstract_weight,
            "keywords": keywords_weight,
            "solicitation": solicitation_weight
        }
        self.vectorizer = TfidfVectorizer(**tfidf_params)

    def fit_transform(self, documents: list[dict[str, str]]):
        """
        Fit vectorizer on weighted combination of text sources.

        Args:
            documents: List of dicts with keys: abstract, keywords, solicitation

        Returns:
            Sparse TF-IDF matrix
        """
        combined_texts = [
            self._combine_sources(doc) for doc in documents
        ]
        return self.vectorizer.fit_transform(combined_texts)

    def _combine_sources(self, doc: dict[str, str]) -> str:
        """Combine text sources with repetition-based weighting."""
        parts = []

        # Repeat each source proportional to its weight
        for source, weight in self.weights.items():
            text = doc.get(source, "")
            repeat_count = int(weight * 10)  # Scale to integer repetitions
            parts.extend([text] * repeat_count)

        return " ".join(parts)
```

---

---

## Implementation Status

### Phase 1: Completed ✅

**Commit**: `cfece1c` - "feat: implement Phase 1 CET classifier enhancements"

**Implemented**:
1. ✅ Stop words filtering (30+ SBIR-specific terms)
2. ✅ Negative keyword penalties (7 CET areas with high false-positive rates)
3. ✅ Agency/branch contextual priors (8 agencies, 6 branches)

**Files Modified**:
- `config/cet/classification.yaml` - Added stop words and priors configuration
- `config/cet/taxonomy.yaml` - Added negative_keywords field for 7 CETs
- `src/models/cet_models.py` - Added negative_keywords field to CETArea model
- `src/ml/models/cet_classifier.py` - Implemented enhancement logic
- `tests/unit/ml/test_cet_enhancements_phase1.py` - Comprehensive unit tests

**Expected Impact**:
- +5-10% accuracy from agency/branch priors
- -20-30% false positives from negative keywords
- Cleaner feature space from stop words

---

### Phase 2: Completed ✅

**Commit**: TBD

**Implemented**:
1. ✅ Multi-source text vectorization (abstract + keywords + title)
2. ✅ Configurable weights (default: 50%/30%/20%)
3. ✅ Backward compatibility with single-source mode
4. ✅ Optional feature flag (`multi_source.enabled`)

**Files Created**:
- `src/ml/models/multi_source_vectorizer.py` - MultiSourceCETVectorizer implementation
- `tests/unit/ml/test_multi_source_vectorization.py` - Comprehensive unit tests

**Files Modified**:
- `config/cet/classification.yaml` - Added multi_source configuration section
- `src/ml/models/cet_classifier.py` - Updated to support multi-source mode
  - `train()` - Accepts dict or string input
  - `classify()` - Accepts dict or string input
  - `classify_batch()` - Accepts dict or string input
  - `_build_pipeline()` - Selects vectorizer based on config

**Configuration**:
```yaml
multi_source:
  enabled: false  # Set to true to enable (requires retraining)
  abstract_weight: 0.5  # 50%
  keywords_weight: 0.3  # 30%
  title_weight: 0.2     # 20%
```

**Usage**:
```python
# Multi-source mode (when enabled in config)
model.classify({
    "abstract": "quantum computing research",
    "keywords": "quantum algorithms qubits",
    "title": "Quantum Computing Study"
})

# Single-source mode (backward compatible)
model.classify("quantum computing research")
```

**Expected Impact**:
- +10-15% accuracy, especially for short or vague abstracts
- Better utilization of available metadata
- More robust classifications with richer context

**Note**: Requires model retraining to use multi-source mode. Set `multi_source.enabled: true` and retrain classifiers with dict input format.

---

## Conclusion

The archived **sbir-cet-classifier** offers several proven enhancements that can improve the accuracy and robustness of sbir-etl's CET classification system. The recommended integration roadmap prioritizes:

1. ✅ **Phase 1 Complete**: Agency priors, negative keywords, stop words
2. ✅ **Phase 2 Complete**: Multi-source vectorization
3. ⏳ **Phase 3 Pending**: Context rules, hybrid scoring (2-3 weeks)

**Completed Enhancements**:
- Stop words filtering
- Negative keyword penalties
- Agency/branch contextual priors
- Multi-source text vectorization
- Comprehensive unit tests
- Backward compatibility maintained

**Total Implementation Time**: 2 weeks (Phase 1 + Phase 2)

**Next Steps**:
1. Optional: Implement Phase 3 (context rules)
2. Retrain classifiers with `multi_source.enabled: true`
3. Run drift detection and validation
4. Measure accuracy improvements on test set
5. Deploy to production pipeline
