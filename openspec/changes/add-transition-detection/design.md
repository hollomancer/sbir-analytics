# SBIR Transition Detection Module - Technical Design

## Context

SBIR program stakeholders need to measure **technology transition** - the ultimate success metric indicating when research investments lead to real-world adoption through follow-on contracts, patents, and commercialization. Currently, the pipeline can track awards and patents but cannot:

- Detect successful commercialization events
- Measure program effectiveness (award-level vs company-level)
- Provide evidence-based scoring with audit trails
- Track the full innovation lifecycle (Research → Patents → Products → Contracts)
- Identify which Critical and Emerging Technology areas transition most effectively

**Available Resources:**
- Production-ready sbir-transition-classifier (66K detections/minute, 99.99% data retention)
- USAspending.gov federal contracts data (6.7M+ contracts, 14GB+)
- Proposed USPTO patent ETL (10.5M assignments)
- Proposed CET classification module (21 technology areas)
- Existing SBIR award data (252K awards)

**Constraints:**
- Must integrate seamlessly with existing Dagster pipeline
- Must support both batch and incremental processing
- Must provide explainable scoring (evidence bundles)
- Must handle large contract datasets efficiently (14GB+)
- Must enable graph-based transition pathway queries

**Stakeholders:**
- Program managers measuring ROI
- Policy makers evaluating program effectiveness
- Researchers studying innovation patterns
- Companies tracking their own success rates

## Goals / Non-Goals

### Goals
- Detect transitions from 100% of SBIR awards to follow-on contracts
- Achieve ≥85% precision for high-confidence detections
- Achieve ≥70% recall against known Phase III awards
- Provide evidence bundles for every detection (complete audit trail)
- Support dual-perspective analytics (award-level + company-level)
- Enable patent-based transition signals
- Track transition rates by CET technology area
- Process full fiscal year data in <8 hours
- Maintain ≥99.9% data retention rate

### Non-Goals
- Real-time transition detection (batch processing only)
- Commercial (non-government) contract tracking (focus on federal only)
- Manual review interface (separate tool)
- Automated acceptance/rejection (analyst validation required)
- International contract tracking (U.S. federal only)

## Decisions

### Decision 1: Rules-Based vs. ML-Based Detection

**Choice:** Rules-based heuristic scoring with configurable weights (defer ML to future phase)

**Rationale:**
- sbir-transition-classifier proves rules-based approach achieves 97.9% data retention
- Interpretable scoring (explainable to stakeholders)
- No training data required initially
- Fast to implement and deploy
- Can add ML later when sufficient validated data available

**Scoring Algorithm:**
```python
def calculate_transition_score(signals: TransitionSignals) -> float:
    """Calculate likelihood score from multiple signals."""
    score = 0.0

    # Base score for any candidate match
    score += 0.15  # Base: 0.15

    # Agency continuity (weight: 0.25)
    if signals.same_agency:
        score += 0.25
    elif signals.same_department:
        score += 0.125  # Cross-service, 50% weight

    # Timing proximity (weight: 0.15)
    # Closer timing = higher score
    timing_factor = calculate_timing_factor(signals.days_after_completion)
    score += timing_factor * 0.15

    # Competition type (weight: 0.20)
    if signals.sole_source:
        score += 0.20  # Strongest signal
    elif signals.limited_competition:
        score += 0.10

    # Patent signals (weight: 0.10) - NEW CAPABILITY
    if signals.has_patent:
        score += 0.05
    if signals.patent_filed_before_contract:
        score += 0.03  # IP protection strategy
    if signals.patent_topic_similarity > 0.7:
        score += 0.02

    # Text similarity (weight: 0.10)
    if signals.text_similarity_enabled:
        score += signals.description_similarity * 0.10

    # CET area alignment (weight: 0.05) - NEW CAPABILITY
    if signals.award_cet_id == signals.contract_cet_id:
        score += 0.05  # Technology continuity

    return min(score, 1.0)  # Cap at 1.0


def calculate_timing_factor(days_after: int) -> float:
    """Score based on timing proximity.

    - 0-3 months: 1.0 (immediate follow-on)
    - 3-12 months: 0.75
    - 12-24 months: 0.5
    - >24 months: 0.0 (outside window)
    """
    if days_after < 0:
        return 0.0  # Contract before award completion
    elif days_after <= 90:
        return 1.0
    elif days_after <= 365:
        return 0.75
    elif days_after <= 730:
        return 0.5
    else:
        return 0.0  # Outside 24-month window
```

**Alternatives Considered:**
- ML classifier (XGBoost, Random Forest): Rejected - requires training data
- Simple boolean rules: Rejected - too brittle, low recall
- LLM-based classification: Rejected - cost, latency, non-deterministic

### Decision 2: Evidence Bundle Structure

**Choice:** Comprehensive JSON evidence stored on Neo4j relationships

**Evidence Bundle Schema:**
```python
class EvidenceBundle(BaseModel):
    """Complete evidence for a transition detection."""

    # Identifiers
    detection_id: UUID
    sbir_award_id: str
    contract_piid: str

    # Scoring
    likelihood_score: float  # 0.0-1.0
    confidence: Literal["High", "Likely", "Possible"]

    # Signals
    agency_signals: AgencySignals
    timing_signals: TimingSignals
    competition_signals: CompetitionSignals
    patent_signals: Optional[PatentSignals]
    text_signals: Optional[TextSignals]
    cet_signals: Optional[CETSignals]

    # Evidence sources
    contract_details: ContractEvidence
    patent_details: Optional[List[PatentEvidence]]
    vendor_match: VendorMatchEvidence

    # Metadata
    detection_date: datetime
    detection_version: str  # Algorithm version for reproducibility


class AgencySignals(BaseModel):
    same_agency: bool
    same_department: bool
    sbir_agency: str
    contract_agency: str
    agency_score: float  # Contribution to total score


class TimingSignals(BaseModel):
    sbir_completion_date: date
    contract_start_date: date
    days_after_completion: int
    within_window: bool  # 0-24 months
    timing_score: float


class PatentSignals(BaseModel):
    """Patent-specific transition signals (NEW)."""
    has_patent: bool
    patent_count: int
    patent_filed_before_contract: bool
    patent_topic_similarity: float  # 0.0-1.0
    patent_filing_lag_days: Optional[int]
    patent_numbers: List[str]
    patent_score: float


class CETSignals(BaseModel):
    """Technology area alignment signals (NEW)."""
    award_cet_id: Optional[str]
    contract_cet_id: Optional[str]  # Inferred from description
    cet_area_match: bool
    award_cet_score: Optional[float]
    cet_score: float
```

**Rationale:**
- Complete audit trail for every detection
- Supports manual review and validation
- Enables retroactive recomputation if algorithm changes
- Interpretable to non-technical stakeholders
- Stores all context needed for queries

**Alternatives Considered:**
- Store scoring components only: Rejected - insufficient for validation
- Separate evidence table: Rejected - complicates queries
- External blob storage: Rejected - Neo4j JSON properties sufficient

### Decision 3: Vendor Resolution Strategy

**Choice:** Multi-identifier cross-walk with fallback hierarchy

**Vendor Matching Hierarchy:**
```
1. UEI (Unique Entity Identifier) - Primary, government-wide
   ↓ (if no match)
2. CAGE Code (Commercial and Government Entity) - Defense-specific
   ↓ (if no match)
3. DUNS Number (Data Universal Numbering System) - Legacy, being phased out
   ↓ (if no match)
4. Normalized Name Match with fuzzy similarity ≥0.90
```

**Implementation:**
```python
class VendorResolver:
    """Resolve vendor identity across SBIR awards and federal contracts."""

    def __init__(self):
        self.fuzzy_threshold = 0.90

    def resolve_vendor(
        self,
        sbir_vendor: SBIRVendor,
        contract_vendor: ContractVendor
    ) -> Optional[VendorMatch]:
        """Attempt to match vendors using cross-walk."""

        # 1. Exact UEI match
        if sbir_vendor.uei and contract_vendor.uei:
            if sbir_vendor.uei == contract_vendor.uei:
                return VendorMatch(
                    method="uei_exact",
                    confidence=0.99,
                    matched_on=sbir_vendor.uei
                )

        # 2. CAGE code match
        if sbir_vendor.cage and contract_vendor.cage:
            if sbir_vendor.cage == contract_vendor.cage:
                return VendorMatch(
                    method="cage_exact",
                    confidence=0.95,
                    matched_on=sbir_vendor.cage
                )

        # 3. DUNS match
        if sbir_vendor.duns and contract_vendor.duns:
            if sbir_vendor.duns == contract_vendor.duns:
                return VendorMatch(
                    method="duns_exact",
                    confidence=0.90,
                    matched_on=sbir_vendor.duns
                )

        # 4. Fuzzy name match
        normalized_sbir = normalize_company_name(sbir_vendor.name)
        normalized_contract = normalize_company_name(contract_vendor.name)

        similarity = fuzz.ratio(normalized_sbir, normalized_contract) / 100.0

        if similarity >= self.fuzzy_threshold:
            return VendorMatch(
                method="name_fuzzy",
                confidence=similarity,
                matched_on=normalized_sbir
            )

        return None  # No match found
```

**Rationale:**
- UEI is government-wide standard (highest confidence)
- CAGE code specific to defense contractors (high confidence)
- DUNS being phased out but still present in legacy data
- Fuzzy name matching catches variations and typos
- Hierarchical approach maximizes coverage

**Alternatives Considered:**
- Name-only matching: Rejected - too many false positives
- UEI-only: Rejected - not all records have UEI yet
- No fallback: Rejected - misses 20-30% of valid matches

### Decision 4: Neo4j Graph Schema for Transitions

**Choice:** Transition as first-class node with rich relationships

**Graph Model:**
```cypher
// Core transition pattern
(Award)-[:TRANSITIONED_TO {
    likelihood_score: 0.87,
    confidence: "High",
    evidence: {...},
    detection_date: datetime(),
    detection_version: "1.0"
}]->(Transition)-[:RESULTED_IN]->(Contract)

// Patent-backed transitions
(Award)-[:FUNDED]->(Patent)
(Transition)-[:ENABLED_BY {
    patent_filed_before_contract: true,
    filing_lag_days: 245,
    topic_similarity: 0.85
}]->(Patent)

// CET area tracking
(Award)-[:APPLICABLE_TO]->(CETArea {name: "Artificial Intelligence"})
(Transition)-[:INVOLVES_TECHNOLOGY]->(CETArea)

// Company-level transitions
(Company)-[:ACHIEVED {
    transition_count: 15,
    avg_likelihood_score: 0.82,
    success_rate: 0.68
}]->(TransitionProfile)
```

**Node Types:**
- **Transition**: Represents detected commercialization event
  - Properties: transition_id, detection_date, likelihood_score, confidence, evidence_bundle
- **Contract**: Federal contract awarded after SBIR
  - Properties: piid, agency, start_date, amount, competition_type
- **TransitionProfile**: Company-level aggregation
  - Properties: company_id, total_awards, total_transitions, success_rate

**Relationship Types:**
- **TRANSITIONED_TO**: Award → Transition (detection metadata)
- **RESULTED_IN**: Transition → Contract (outcome)
- **ENABLED_BY**: Transition → Patent (IP backing)
- **INVOLVES_TECHNOLOGY**: Transition → CETArea (technology tracking)
- **ACHIEVED**: Company → TransitionProfile (company success metrics)

**Query Examples:**
```cypher
// Find high-confidence AI transitions with patents
MATCH path = (a:Award)-[:APPLICABLE_TO]->(cet:CETArea {name: "Artificial Intelligence"}),
             (a)-[:TRANSITIONED_TO {confidence: "High"}]->(t:Transition),
             (t)-[:ENABLED_BY]->(p:Patent),
             (t)-[:RESULTED_IN]->(c:Contract)
RETURN
    a.award_id,
    a.firm_name,
    p.grant_doc_num,
    c.piid,
    c.amount as contract_value
ORDER BY contract_value DESC

// Calculate transition rate by CET area
MATCH (a:Award)-[:APPLICABLE_TO]->(cet:CETArea)
OPTIONAL MATCH (a)-[:TRANSITIONED_TO]->(t:Transition {confidence: "High"})
WITH cet, count(DISTINCT a) as total_awards, count(DISTINCT t) as transitions
RETURN
    cet.name as technology_area,
    total_awards,
    transitions,
    transitions * 100.0 / total_awards as transition_rate_pct
ORDER BY transition_rate_pct DESC

// Find companies with sustained commercialization capability
MATCH (c:Company)-[:ACHIEVED]->(tp:TransitionProfile)
WHERE tp.transition_count >= 5 AND tp.success_rate >= 0.60
RETURN
    c.name,
    tp.total_awards,
    tp.total_transitions,
    tp.success_rate,
    tp.avg_likelihood_score
ORDER BY tp.success_rate DESC
```

**Rationale:**
- Transition as node enables rich querying
- Evidence stored on relationships maintains context
- CET integration enables technology-specific analytics
- Company profiles support strategic analysis
- Graph structure reveals transition pathways

**Alternatives Considered:**
- Direct Award → Contract relationship: Rejected - loses evidence and scoring
- Transition as relationship property only: Rejected - limits query capabilities
- Separate transition database: Rejected - breaks graph connectivity

### Decision 5: Dual-Perspective Analytics

**Choice:** Track both award-level and company-level metrics

**Critical Insight from sbir-transition-classifier:**
- **Award-Level**: 69% of awards transition (encouraging)
- **Company-Level**: Only 7.9% of companies sustain commercialization (challenging)

**Implementation:**
```python
class TransitionAnalytics:
    """Dual-perspective transition analytics."""

    def calculate_award_level_metrics(self) -> AwardMetrics:
        """Individual award success rates."""
        return AwardMetrics(
            total_awards=252025,
            transitioned_awards=173897,
            transition_rate=0.690,
            phase_i_rate=0.659,
            phase_ii_rate=0.741,
            phase_ii_advantage=0.082  # 8.2 percentage points
        )

    def calculate_company_level_metrics(self) -> CompanyMetrics:
        """Sustained commercialization capability."""
        return CompanyMetrics(
            total_companies=33583,
            companies_with_transitions=2653,
            sustained_rate=0.079,  # Only 7.9%
            avg_transitions_per_successful_company=5.2,
            median_transitions=3
        )

    def calculate_cet_area_metrics(self) -> List[CETAreaMetrics]:
        """Technology-specific transition rates (NEW)."""
        return [
            CETAreaMetrics(
                cet_id="artificial_intelligence",
                total_awards=15432,
                transitioned_awards=11234,
                transition_rate=0.728,
                avg_time_to_transition_days=385,
                patent_backed_rate=0.42
            ),
            CETAreaMetrics(
                cet_id="quantum_computing",
                total_awards=2156,
                transitioned_awards=1298,
                transition_rate=0.602,
                avg_time_to_transition_days=512,
                patent_backed_rate=0.38
            ),
            # ... other CET areas
        ]
```

**Rationale:**
- Award-level shows individual success (tactical view)
- Company-level shows sustained capability (strategic view)
- CET-level shows technology effectiveness (portfolio view)
- All three perspectives needed for comprehensive analysis

### Decision 6: Patent Integration Strategy

**Choice:** Patents as additional transition signal with multiple roles

**Patent Roles in Transition Detection:**

1. **Commercialization Indicator:**
   - Patent filed after SBIR = intent to commercialize
   - Patent filed before contract = IP protection strategy
   - Adds 0.05 to transition score

2. **Technology Transfer Signal:**
   - Patent assigned to entity other than SBIR recipient = licensing
   - Creates separate "Technology Transfer Transition" type
   - Tracks spin-offs and partnerships

3. **Topic Validation:**
   - Patent abstract similarity to SBIR topic ≥0.7 = technology continuity
   - Adds 0.02 to transition score
   - Validates that contract is related to SBIR research

4. **Timeline Evidence:**
   - Patent filing lag (days between SBIR completion and patent filing)
   - Patent grant lag (days between patent grant and contract award)
   - Informs transition pathway analysis

**Implementation:**
```python
def extract_patent_signals(
    sbir_award: Award,
    patents: List[Patent],
    contract: Contract
) -> PatentSignals:
    """Extract patent-based transition signals."""

    if not patents:
        return PatentSignals(has_patent=False, patent_count=0, patent_score=0.0)

    # Find patents in relevant timeframe
    relevant_patents = [
        p for p in patents
        if sbir_award.completion_date <= p.filing_date <= contract.start_date
    ]

    if not relevant_patents:
        return PatentSignals(has_patent=False, patent_count=0, patent_score=0.0)

    # Calculate signals
    patent_filed_before_contract = any(
        p.filing_date < contract.start_date for p in relevant_patents
    )

    # Topic similarity (average across all relevant patents)
    topic_similarities = [
        calculate_text_similarity(sbir_award.abstract, p.title + " " + p.abstract)
        for p in relevant_patents
    ]
    avg_topic_similarity = sum(topic_similarities) / len(topic_similarities)

    # Filing lag
    filing_lags = [
        (p.filing_date - sbir_award.completion_date).days
        for p in relevant_patents
    ]
    avg_filing_lag = sum(filing_lags) / len(filing_lags)

    # Calculate patent contribution to score
    patent_score = 0.0
    patent_score += 0.05 if relevant_patents else 0.0  # Has patent
    patent_score += 0.03 if patent_filed_before_contract else 0.0  # IP strategy
    patent_score += 0.02 if avg_topic_similarity > 0.7 else 0.0  # Topic match

    return PatentSignals(
        has_patent=True,
        patent_count=len(relevant_patents),
        patent_filed_before_contract=patent_filed_before_contract,
        patent_topic_similarity=avg_topic_similarity,
        patent_filing_lag_days=int(avg_filing_lag),
        patent_numbers=[p.grant_doc_num for p in relevant_patents],
        patent_score=patent_score
    )
```

## Risks / Trade-offs

### Risk 1: False Positive Transitions

**Impact:** Detecting transitions that aren't actually related to SBIR award

**Mitigation:**
- Use high confidence threshold (≥0.85) for automated acceptance
- Require manual review for "Likely" detections (0.65-0.84)
- Include complete evidence bundles for validation
- Support analyst feedback loop for threshold tuning
- Track precision metrics against known Phase III awards

**Trade-off:** Higher precision (fewer false positives) vs. higher recall (find all true transitions)

### Risk 2: Vendor Match Failures

**Impact:** Missing transitions due to company name changes, acquisitions, or identifier gaps

**Mitigation:**
- Multi-identifier cross-walk (UEI, CAGE, DUNS)
- Fuzzy name matching (≥0.90 threshold)
- SAM.gov enrichment provides identifier completeness
- Track vendor match rate metrics (target: ≥90%)
- Manual review queue for unmatched high-value awards

**Trade-off:** Coverage vs confidence. Fuzzy matching increases coverage but lowers confidence.

### Risk 3: Contract Data Volume

**Impact:** 14GB+ contract dataset may strain memory and processing time

**Mitigation:**
- Chunked processing (100K contracts/batch)
- DuckDB for analytical queries on large contract dataset
- Incremental processing (only new contracts since last run)
- Vendor-based partitioning (only load contracts for companies with SBIR awards)
- Index contract data on vendor identifiers and start dates

**Trade-off:** Full coverage vs processing speed. Vendor filtering improves speed but may miss rare cross-vendor transitions.

### Risk 4: CET Classification Dependency

**Impact:** CET area analytics require CET classification module to be implemented first

**Mitigation:**
- Design transition detection to work without CET (optional enhancement)
- Phase 1: Core transition detection (contracts only)
- Phase 2: Add patent signals
- Phase 3: Add CET integration
- Graceful degradation if CET data unavailable

**Trade-off:** Phased delivery reduces risk but delays full capability.

## Migration Plan

### Phase 1: Core Transition Detection (Weeks 1-3)
1. Implement vendor resolution (UEI/CAGE/DUNS cross-walk)
2. Implement transition scoring algorithm
3. Create evidence bundle generation
4. Load federal contracts from USAspending
5. Detect transitions for FY2020-2024 data
6. Validate against known Phase III awards

### Phase 2: Neo4j Integration (Week 4)
1. Create Transition node schema
2. Create TRANSITIONED_TO, RESULTED_IN relationships
3. Load transition detections to Neo4j
4. Create indexes on transition_id, award_id, contract_piid
5. Implement basic transition queries

### Phase 3: Patent Integration (Week 5)
1. Integrate with USPTO patent ETL module
2. Implement patent signal extraction
3. Add ENABLED_BY relationships (Transition → Patent)
4. Test patent-backed transition scoring
5. Validate patent topic similarity

### Phase 4: CET Integration (Week 6)
1. Integrate with CET classification module
2. Add INVOLVES_TECHNOLOGY relationships (Transition → CETArea)
3. Implement CET area transition analytics
4. Generate technology-specific success rate reports

### Phase 5: Analytics & Reporting (Week 7)
1. Implement dual-perspective analytics (award + company level)
2. Create transition pathway queries
3. Generate executive dashboards
4. Build analyst review interface

### Phase 6: Validation & Deployment (Week 8)
1. Run full pipeline on production data
2. Validate precision/recall metrics
3. Performance benchmarking
4. Deploy to production
5. Generate initial transition reports

### Rollback Plan
- Transition detection is additive (no changes to existing awards/contracts)
- Can disable transition assets via Dagster configuration
- Neo4j transition data can be deleted without affecting core graph
- Rollback via Dagster asset version revert

## Open Questions

1. **Q: How do we handle contract modifications and IDV parent-child relationships?**
   - **A:** Track parent contract PIID. Modifications count toward original detection. IDV awards analyzed separately.

2. **Q: Should we detect commercial (non-federal) transitions?**
   - **A:** No for initial implementation. Focus on federal contracts (measurable ground truth). Commercial tracking is future work.

3. **Q: What timing window should we use (0-24 months is default)?**
   - **A:** Start with 24 months (from sbir-transition-classifier). Make configurable. May extend to 36 months for certain technologies.

4. **Q: How do we handle awards with no completion date?**
   - **A:** Use award year + expected phase duration (Phase I: 6 months, Phase II: 24 months) as proxy.

5. **Q: Should we track transition attempts (contracts that didn't result from SBIR)?**
   - **A:** No. Focus on positive detections only. "No transition" is absence of detection.

6. **Q: How do we weight patent signals vs contract signals?**
   - **A:** Patents contribute max 10% to score. Contracts are primary signal (40%). CET adds 5%. Timing adds 15%.

7. **Q: What if a company has multiple SBIR awards before one contract?**
   - **A:** Create multiple transition detections (one per award). Higher scores for more recent awards.

8. **Q: How do we measure transition effectiveness by CET area without bias?**
   - **A:** Normalize by funding levels. Calculate transition rate per $M invested, not just raw counts.
