# Codebase Consolidation Migration Guide

**Target Audience**: Developers working on the SBIR ETL pipeline  
**Purpose**: Guide for migrating from current architecture to consolidated structure  
**Status**: Planning Phase  

## Overview

This guide helps developers understand and adapt to the consolidated codebase architecture. The consolidation refactor aims to reduce complexity and eliminate duplication while maintaining all existing functionality.

## Breaking Changes (Final Cleanup)

As of Task 7.3 completion, the following deprecated components have been permanently removed:

### Removed Models

- **`SbirAward`**: The deprecated compatibility wrapper has been removed. Use `Award.from_sbir_csv()` or `Award` with field aliases instead.

### Removed Asset Aliases

- **`uspto_ai_extract_to_duckdb`**: Use `raw_uspto_ai_extract` instead
- **`uspto_ai_human_sample_extraction`**: Use `raw_uspto_ai_human_sample_extraction` instead

### Migration Required

If your code still references these removed items, update as follows:

```python

## Old (broken)

from src.models.sbir_award import SbirAward
from src.assets import uspto_ai_extract_to_duckdb, uspto_ai_human_sample_extraction

## New

from src.models import Award
from src.assets import raw_uspto_ai_extract, raw_uspto_ai_human_sample_extraction
```

## Migration Timeline

### Phase 1: Foundation (Weeks 1-2)

- **Configuration System**: Migrate to unified configuration loading
- **Performance Monitoring**: Adopt centralized monitoring
- **Testing Framework**: Update test patterns
- **Error Handling**: Use unified error handling

### Phase 2: Asset Consolidation (Weeks 3-4)

- **Asset Definitions**: Migrate to consolidated assets
- **Asset Dependencies**: Update dependency references
- **Asset Monitoring**: Adopt unified monitoring patterns

### Phase 3: Models and Utilities (Weeks 5-6)

- **Data Models**: Migrate to consolidated models
- **Utility Functions**: Use centralized utilities
- **Validation Logic**: Adopt unified validation

### Phase 4: Final Migration (Weeks 7-8)

- **Testing Updates**: Complete test migration
- **Documentation**: Update all documentation
- **Cleanup**: Remove deprecated code

## Before and After Comparisons

### Configuration Loading

### Before (Current)

```python

## Multiple configuration patterns

from src.config.loader import load_config
from src.config.schemas import SBIRConfig, USPTOConfig

## Different loading approaches

sbir_config = load_config("sbir", SBIRConfig)
uspto_config = load_config("uspto", USPTOConfig)
```

### After (Consolidated)

```python

## Unified configuration system

from src.core.config.loader import load_config
from src.core.config.schemas import PipelineConfig

## Single configuration with hierarchical access

config = load_config("pipeline", PipelineConfig)
sbir_settings = config.sbir
uspto_settings = config.uspto
```

### Asset Definitions

### Before (Current)

```python

## Multiple similar assets

@asset(group_name="sbir_ingestion")
def raw_sbir_awards(context: AssetExecutionContext) -> pd.DataFrame:
    # SBIR-specific logic
    pass

@asset(group_name="usaspending_ingestion")
def usaspending_extraction(context: AssetExecutionContext) -> pd.DataFrame:
    # USAspending-specific logic
    pass
```

### After (Consolidated)

```python

## Consolidated assets with unified patterns

from src.core.assets.base_asset import ConsolidatedAsset

@asset(group_name="ingestion")
def data_ingestion(
    context: AssetExecutionContext,
    config: PipelineConfig
) -> pd.DataFrame:
    """Consolidated data ingestion for all sources."""
    asset = ConsolidatedAsset(config, context)
    return asset.execute_ingestion()
```

### Performance Monitoring

### Before (Current)

```python

## Scattered monitoring code

import time
from src.utils.performance_monitor import PerformanceMonitor

def my_function():
    start_time = time.time()
    monitor = PerformanceMonitor()
    
    # Function logic
    result = process_data()
    
    # Manual monitoring
    duration = time.time() - start_time
    monitor.log_duration("my_function", duration)
    return result
```

### After (Consolidated)

```python

## Unified monitoring system

from src.core.monitoring.metrics import UnifiedPerformanceMonitor

def my_function():
    monitor = UnifiedPerformanceMonitor()
    
    with monitor.track_execution("my_function"):
        # Function logic - monitoring is automatic
        result = process_data()
    
    return result
```

### Data Models

### Before (Current)

```python

## Duplicate model definitions

from pydantic import BaseModel

class SBIRAward(BaseModel):
    award_id: str
    company_name: str
    amount: float
    # Duplicate validation logic

class USPTOPatent(BaseModel):
    patent_id: str
    title: str
    grant_date: date
    # Similar validation patterns
```

### After (Consolidated)

```python

## Hierarchical model structure

from src.core.models.base import BaseDataModel

class Award(BaseDataModel):
    """Consolidated award model."""
    award_id: str
    company_name: str
    amount: float
    # Shared validation logic inherited

class Patent(BaseDataModel):
    """Consolidated patent model."""
    patent_id: str
    title: str
    grant_date: date
    # Shared validation logic inherited
```

### Testing Patterns

### Before (Current)

```python

## Different test setup patterns

import pytest
from unittest.mock import Mock

class TestSBIRIngestion:
    def setup_method(self):
        self.mock_neo4j = Mock()
        self.config = load_sbir_config()
    
    def test_ingestion(self):
        # Test-specific setup
        pass
```

### After (Consolidated)

```python

## Unified testing framework

import pytest
from src.tests.helpers.database import DatabaseTestHelper
from src.tests.fixtures.configs import pipeline_config

class TestDataIngestion:
    def test_ingestion(self, pipeline_config, database_helper):
        # Shared fixtures and helpers
        pass
```

## Migration Checklist

### For Asset Developers

- [ ] **Update imports**: Change from module-specific to consolidated imports
- [ ] **Adopt base classes**: Extend ConsolidatedAsset for new assets
- [ ] **Use unified config**: Access configuration through PipelineConfig hierarchy
- [ ] **Apply monitoring**: Use UnifiedPerformanceMonitor for tracking
- [ ] **Update dependencies**: Reference consolidated asset names

### For Configuration Changes

- [ ] **Schema updates**: Migrate to hierarchical Pydantic models
- [ ] **Environment variables**: Use standardized SBIR_ETL__ prefix
- [ ] **File organization**: Move configs to appropriate subdirectories
- [ ] **Validation**: Use consolidated validation patterns

### For Testing Updates

- [ ] **Fixture migration**: Use shared test fixtures
- [ ] **Helper adoption**: Leverage consolidated test helpers
- [ ] **Mock patterns**: Use consistent mocking approaches
- [ ] **Data management**: Use unified test data management

### For Utility Functions

- [ ] **Import updates**: Use centralized utility imports
- [ ] **Function consolidation**: Replace duplicate functions with shared versions
- [ ] **Error handling**: Adopt unified error handling patterns
- [ ] **Logging**: Use consolidated logging configuration

## Common Migration Patterns

### 1. Configuration Access Pattern

### Old Pattern

```python
from src.config.loader import load_config
config = load_config("module_specific", ModuleConfig)
setting = config.specific_setting
```

### New Pattern

```python
from src.core.config.loader import load_config
config = load_config("pipeline", PipelineConfig)
setting = config.module.specific_setting
```

### 2. Asset Definition Pattern

### Old Pattern

```python
@asset(group_name="module_specific")
def module_asset(context):
    # Module-specific logic
    pass
```

### New Pattern

```python
@asset(group_name="consolidated_group")
def consolidated_asset(context, config: PipelineConfig):
    asset = ConsolidatedAsset(config, context)
    return asset.execute()
```

### 3. Validation Pattern

### Old Pattern

```python
def validate_data(data, config):
    # Custom validation logic
    issues = []
    # ... validation code ...
    return issues
```

### New Pattern

```python
from src.shared.validation.base import BaseValidator

validator = BaseValidator(config)
report = validator.validate(data)
```

### 4. Database Client Pattern

### Old Pattern

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver(uri, auth=(user, password))

## Manual session management

```

### New Pattern

```python
from src.shared.database.neo4j_client import Neo4jClient

client = Neo4jClient(config.neo4j)
with client.session() as session:
    # Automatic session management
    pass
```

## Backward Compatibility

### Compatibility Layers

During the migration period, compatibility layers will be provided:

```python

## src/legacy/compatibility.py

from src.core.config.loader import load_config as new_load_config
from src.core.config.schemas import PipelineConfig

def load_config(module_name: str, config_class):
    """Legacy configuration loader with deprecation warning."""
    import warnings
    warnings.warn(
        f"load_config({module_name}, {config_class}) is deprecated. "
        "Use unified PipelineConfig instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Map old config to new structure
    pipeline_config = new_load_config("pipeline", PipelineConfig)
    return getattr(pipeline_config, module_name)
```

### Migration Utilities

```python

## src/migration/helpers.py

class MigrationHelper:
    """Tools to assist with codebase migration."""
    
    def migrate_asset_config(self, old_config: dict) -> PipelineConfig:
        """Migrate old configuration to new format."""
        # Migration logic
        pass
    
    def validate_migration(self, component: str) -> MigrationReport:
        """Validate successful migration of component."""
        # Validation logic
        pass
```

## Testing Migration

### Test Migration Strategy

1. **Parallel Testing**: Run both old and new tests during migration
2. **Fixture Sharing**: Gradually migrate to shared fixtures
3. **Helper Adoption**: Replace custom helpers with consolidated versions
4. **Coverage Maintenance**: Ensure coverage doesn't drop during migration

### Example Test Migration

### Before

```python
class TestSBIRValidation:
    def setup_method(self):
        self.config = load_sbir_config()
        self.validator = SBIRValidator(self.config)
    
    def test_award_validation(self):
        awards = create_test_awards()
        issues = self.validator.validate(awards)
        assert len(issues) == 0
```

### After

```python
class TestDataValidation:
    def test_award_validation(self, pipeline_config, test_data_manager):
        validator = BaseValidator(pipeline_config.validation)
        awards = test_data_manager.get_sample_awards()
        report = validator.validate(awards)
        assert report.pass_rate >= 0.95
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Update import paths to consolidated structure
2. **Configuration Errors**: Use hierarchical config access patterns
3. **Asset Dependencies**: Update asset dependency references
4. **Test Failures**: Migrate to unified test patterns

### Migration Validation

```python

## Validation script to check migration completeness

def validate_migration():
    """Check if migration is complete and successful."""
    checks = [
        check_import_paths(),
        check_configuration_usage(),
        check_asset_dependencies(),
        check_test_patterns()
    ]
    
    return all(checks)
```

## Support and Resources

### Documentation

- [Consolidation Refactor Plan](consolidation-refactor-plan.md)
- [Design Patterns Gap Analysis](DESIGN_PATTERNS_GAP_ANALYSIS.md)
- [Shared Tech Stack Architecture](shared-tech-stack.md)

### Migration Support

- Weekly migration office hours
- Slack channel: #consolidation-migration
- Migration validation tools and scripts

### Code Review Guidelines

- All PRs during migration period require architecture review
- Migration checklist must be completed
- Backward compatibility must be maintained

---

**Document Version**: 1.0  
**Last Updated**: October 30, 2025  
**Next Review**: After Phase 1 completion