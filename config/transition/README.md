# Transition Detection Configuration

This directory contains configuration files for the SBIR transition detection module. These configurations control how the system detects and scores successful transitions from SBIR awards to follow-on federal contracts.

## Configuration Files

### `detection.yaml`
Main configuration file for transition detection parameters:
- **Timing windows**: Define acceptable timeframe for transitions (default: 0-24 months after award completion)
- **Vendor matching**: Configure vendor resolution methods and fuzzy matching thresholds
- **Scoring weights**: Set relative importance of different transition signals
- **Confidence thresholds**: Define score ranges for High/Likely/Possible confidence levels
- **Evidence configuration**: Control what evidence is captured in output
- **Performance settings**: Memory limits, batch sizes, parallelization
- **Data quality thresholds**: Minimum success rates and coverage requirements

### `presets.yaml`
Pre-configured detection modes for different use cases:
- **high_precision**: Conservative detection (≥0.85 score only)
- **balanced**: Default mode with good precision and recall
- **broad_discovery**: Exploratory mode to find all potential transitions
- **research**: Maximum detail for academic analysis
- **phase_2_focus**: Optimized for Phase II awards
- **cet_focused**: Emphasizes technology area alignment

## Quick Start

### Using the Default Configuration

```python
from pathlib import Path
import yaml

config_path = Path("config/transition/detection.yaml")
with open(config_path) as f:
    config = yaml.safe_load(f)

# Access settings
timing_window = config["transition_detection"]["timing_window"]
vendor_threshold = config["transition_detection"]["vendor_matching"]["fuzzy_threshold"]
```

### Selecting a Preset

```python
presets_path = Path("config/transition/presets.yaml")
with open(presets_path) as f:
    presets = yaml.safe_load(f)

# Load balanced preset (recommended default)
balanced_config = presets["presets"]["balanced"]

# Access preset settings
confidence_threshold = balanced_config["confidence_threshold"]
enabled_signals = balanced_config["enabled_signals"]
```

## Configuration Parameters

### Timing Window (detection.yaml)

```yaml
timing_window:
  min_months_after_completion: 0      # Earliest transition (immediate)
  max_months_after_completion: 24     # Latest transition (2 years)
```

Controls the acceptable timeframe for transitions:
- **0-24 months** (default): Standard window for federal contract follow-ons
- **0-12 months** (high_precision): Conservative, immediate transitions only
- **0-36 months** (broad_discovery): Extended for exploratory analysis
- **0-48 months** (research): Maximum window for academic study

### Vendor Matching (detection.yaml)

```yaml
vendor_matching:
  priority: ["uei", "cage", "duns", "fuzzy_name"]
  fuzzy_threshold: 0.85
  fuzzy_secondary_threshold: 0.70
```

Matching methods in priority order:
1. **UEI** (Unique Entity ID): SAM.gov identifier - highest confidence
2. **CAGE**: Defense-specific code - medium-high confidence
3. **DUNS**: Legacy D&B number - medium confidence
4. **fuzzy_name**: Company name fuzzy matching - lower confidence

Thresholds:
- **0.85+**: Primary fuzzy match threshold (recommended default)
- **0.70-0.84**: Secondary fallback threshold
- **Below 0.70**: Not recommended for production

### Scoring Signals (detection.yaml)

```yaml
scoring:
  weights:
    agency_continuity: 0.25      # Same agency/department
    timing_proximity: 0.20       # Contract timing
    competition_type: 0.15       # Sole source vs. competitive
    patent_signal: 0.10          # Patent-backed transitions
    cet_alignment: 0.05          # Technology area match
    text_similarity: 0.10        # Description similarity
```

Each signal contributes to final score:
- **Agency continuity**: Awards transitioning within the same agency or department
- **Timing proximity**: Contracts awarded soon after SBIR completion
- **Competition type**: Sole source contracts indicate higher confidence
- **Patent signal**: Patents filed between SBIR and contract
- **CET alignment**: Award and contract in same technology area
- **Text similarity**: Similarity between award and contract descriptions

### Confidence Levels (detection.yaml)

```yaml
confidence_classification:
  high_confidence: 0.85       # High confidence: Score ≥ 0.85
  likely_confidence: 0.65     # Likely confidence: Score ≥ 0.65
  possible_confidence: 0.0    # Possible: Score < 0.65
```

Output filtering by confidence:
- **High only**: Production reporting, official metrics
- **High + Likely**: General analysis, portfolio assessment
- **High + Likely + Possible**: Exploratory research
- **All scores**: Research and algorithm development

## Configuration Examples

### Example 1: Production Detection (High Precision)

```yaml
# Using high_precision preset
preset: "high_precision"

# Or configure manually:
timing_window:
  max_months_after_completion: 12

vendor_matching:
  fuzzy_threshold: 0.95
  priority: ["uei", "cage", "duns"]  # Exact matches only

confidence_threshold: 0.85

enabled_signals:
  - "agency_continuity"
  - "timing_proximity"
  - "competition_type"
```

Expected results: 10-20% detection rate, ≥90% precision, 40-50% recall

### Example 2: Research Analysis

```yaml
# Using research preset
preset: "research"

# Or configure manually:
timing_window:
  max_months_after_completion: 48

vendor_matching:
  fuzzy_threshold: 0.70
  fuzzy_secondary_threshold: 0.60

confidence_threshold: 0.0  # No threshold

enabled_signals:
  - "agency_continuity"
  - "timing_proximity"
  - "competition_type"
  - "patent_signal"
  - "cet_alignment"
  - "text_similarity"
```

Expected results: 50-70% detection rate, 50-65% precision, 90-95% recall

### Example 3: Phase II Focused

```yaml
# Using phase_2_focus preset
preset: "phase_2_focus"

# Or configure manually:
award_filter:
  phases: ["Phase II"]
  min_award_amount: 100000
  max_award_amount: 750000

scoring:
  weights:
    agency_continuity: 0.30
    timing_proximity: 0.25
    competition_type: 0.20
    patent_signal: 0.15
    cet_alignment: 0.10

timing_window:
  max_months_after_completion: 24
```

Expected results: 25-40% detection rate, 75-85% precision, 70-80% recall

### Example 4: CET-Focused Analysis

```yaml
# Using cet_focused preset
preset: "cet_focused"

# Or configure manually:
scoring:
  weights:
    agency_continuity: 0.20
    timing_proximity: 0.20
    competition_type: 0.15
    patent_signal: 0.15
    cet_alignment: 0.30  # High weight on CET

cet_integration:
  enabled: true
  use_award_classification: true
  infer_from_contract: true
  track_by_area: true

output:
  partition_by: ["cet_area", "confidence"]
```

Expected results: Technology-specific transition rates and ROI analysis

## Loading Configuration in Code

### Basic Configuration Loading

```python
from pathlib import Path
import yaml

def load_config(preset_name: str = "balanced") -> dict:
    """Load transition detection configuration."""
    # Load base configuration
    config_path = Path("config/transition/detection.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    # Load and apply preset
    presets_path = Path("config/transition/presets.yaml")
    with open(presets_path) as f:
        presets = yaml.safe_load(f)
    
    preset = presets["presets"][preset_name]
    
    # Merge preset into config
    config["selected_preset"] = preset_name
    config["transition_detection"].update(preset)
    
    return config
```

### Environment-Specific Configuration

```python
import os
from pathlib import Path
import yaml

def load_config_for_env(env: str = None) -> dict:
    """Load environment-specific configuration."""
    if env is None:
        env = os.getenv("ENVIRONMENT", "development")
    
    # Load base configuration
    base_path = Path("config/transition/detection.yaml")
    with open(base_path) as f:
        config = yaml.safe_load(f)
    
    # Load environment-specific overrides if they exist
    env_path = Path(f"config/transition/{env}.yaml")
    if env_path.exists():
        with open(env_path) as f:
            env_config = yaml.safe_load(f)
            config.update(env_config)
    
    return config
```

## Configuration Best Practices

### 1. Use Presets for Standard Scenarios
- **Production**: Use `high_precision` preset
- **Analysis**: Use `balanced` preset
- **Exploration**: Use `broad_discovery` preset
- **Research**: Use `research` preset

### 2. Tune Fuzzy Matching Thresholds
- **0.95+**: Only nearly exact matches (very conservative)
- **0.85-0.90**: Recommended for production (high precision)
- **0.75-0.85**: Balanced precision/recall
- **0.70-0.75**: Exploratory analysis
- **Below 0.70**: Research/academic only

### 3. Adjust Timing Windows
- **12 months**: Conservative, immediate follow-ons only
- **24 months** (default): Standard federal contract cycle
- **36 months**: Extended analysis window
- **48+ months**: Research and historical analysis

### 4. Consider Signal Importance
- Increase `agency_continuity` weight for inter-agency transitions
- Increase `patent_signal` weight for IP-focused analysis
- Increase `cet_alignment` weight for technology-specific research
- Increase `competition_type` weight for contract analysis

### 5. Monitor Data Quality
- Check `vendor_match_rate` (target: ≥90%)
- Monitor `detection_success_rate` (target: ≥99%)
- Validate precision/recall against known transitions
- Track score distribution (should be roughly: 20% High, 35% Likely, 45% Possible)

## Troubleshooting

### Low Vendor Match Rate
- **Symptom**: Many awards not matching to contracts
- **Solution**: 
  - Lower fuzzy_threshold from 0.85 to 0.75
  - Enable address-based matching
  - Check data quality in vendor names

### Too Many False Positives
- **Symptom**: High detection rate but low precision
- **Solution**:
  - Use `high_precision` preset
  - Increase confidence threshold to 0.85
  - Narrow timing window to 12 months
  - Increase agency_continuity weight

### Too Many False Negatives
- **Symptom**: Low detection rate
- **Solution**:
  - Use `broad_discovery` preset
  - Lower confidence threshold to 0.50
  - Extend timing window to 36 months
  - Enable text_similarity signal

### Missing Patent Signals
- **Symptom**: Patent-backed transitions not detected
- **Solution**:
  - Use `patent_backed` preset
  - Increase patent_signal weight to 0.30+
  - Verify patent data is loaded
  - Check patent-to-company linkage

## Environment-Specific Configuration

Create environment-specific override files:

- `config/transition/development.yaml` - Development settings
- `config/transition/staging.yaml` - Staging settings
- `config/transition/production.yaml` - Production settings

Example `production.yaml`:
```yaml
transition_detection:
  preset: "high_precision"
  
  vendor_matching:
    fuzzy_threshold: 0.95  # Very strict
  
  performance:
    parallel_workers: 8    # More parallelization
    duckdb:
      database_path: "/var/lib/sbir/transitions.duckdb"

output:
  paths:
    detections: "/data/transitions/detections.parquet"
```

## Related Documentation

- `docs/transition/detection_algorithm.md` - Algorithm details
- `docs/transition/scoring_guide.md` - Scoring methodology
- `docs/transition/vendor_matching.md` - Vendor resolution logic
- `docs/transition/evidence_bundles.md` - Evidence structure
- `docs/schemas/transition-graph-schema.md` - Neo4j schema

## Questions?

For issues or questions about configuration:
1. Check the troubleshooting section above
2. Review the detection algorithm documentation
3. Contact the SBIR ETL team