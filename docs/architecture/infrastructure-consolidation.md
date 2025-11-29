# Infrastructure Consolidation Summary

## Overview

This document summarizes the infrastructure consolidation work completed to simplify and maintain the SBIR ETL infrastructure.

## Changes Completed

### 1. Removed Terraform Infrastructure (✅ Completed)

**Problem**: Both CDK (Python) and Terraform were defining Lambda infrastructure, creating duplication and confusion.

**Solution**: Removed Terraform files in favor of CDK as the single source of truth.

**Files Removed**:
- `infrastructure/lambda/weekly-refresh.tf`
- `infrastructure/lambda/terraform.tfvars.example`

**Impact**:
- Single IaC tool (CDK) for all infrastructure
- Reduced maintenance burden
- Clearer ownership and responsibility
- ~170 lines of duplicate code removed

### 2. Consolidated Production Configuration (✅ Completed)

**Problem**: Two production configuration files with overlapping content:
- `config/prod.yaml` (45 lines) - simple overrides
- `config/envs/prod.yaml` (259 lines) - comprehensive config with CET extensions

**Solution**: Merged `envs/prod.yaml` into `config/prod.yaml` and removed the duplicate.

**Files Changed**:
- `config/prod.yaml` - now contains comprehensive production configuration
- `config/envs/prod.yaml` - removed

**Impact**:
- Single source of truth for production configuration
- No confusion about which file takes precedence
- All production settings (including CET) in one place
- ~200 lines of duplicate configuration removed

### 3. Fixed Step Functions Fallback Code (✅ Completed)

**Problem**: The CDK stack had a fallback programmatic definition that referenced removed Lambda functions (`ingestion-checks`, `load-neo4j`).

**Solution**: Updated the fallback to match the JSON definition, using `trigger-dagster-refresh` instead.

**Files Changed**:
- `infrastructure/cdk/stacks/step_functions_stack.py` - updated fallback definition

**Impact**:
- Fallback code now matches actual JSON definition
- Consistent behavior whether JSON is present or not
- References updated to reflect Dagster Cloud migration

### 4. Updated Documentation (✅ Completed)

**Problem**: Documentation referenced removed Terraform files and outdated configuration structure.

**Solution**: Updated all documentation to reflect CDK-only approach and consolidated configuration.

**Files Changed**:
- `config/README.md` - updated to note consolidated prod.yaml
- `docs/deployment/aws-deployment.md` - removed Terraform references
- `infrastructure/cdk/README.md` - added note about CDK-only approach

**Impact**:
- Documentation accurately reflects current architecture
- No confusion about which tools to use
- Clear guidance for new developers

## Architecture Improvements

### Before
```
Infrastructure:
  ├── CDK (Python) - Lambda functions, Step Functions, Storage, Security
  └── Terraform - Lambda weekly-refresh (duplicate)

Configuration:
  ├── config/prod.yaml (simple)
  └── config/envs/prod.yaml (comprehensive, overlapping)
```

### After
```
Infrastructure:
  └── CDK (Python) - All infrastructure (single source of truth)

Configuration:
  └── config/prod.yaml (comprehensive, single file)
```

## Benefits

1. **Simplified Maintenance**
   - Single IaC tool (CDK) instead of two
   - Single production config file instead of two
   - Less code to maintain

2. **Reduced Confusion**
   - Clear which tool to use (CDK)
   - Clear which config file to edit (prod.yaml)
   - No precedence questions

3. **Better Consistency**
   - All infrastructure follows same patterns
   - Configuration structure is consistent
   - Documentation matches reality

4. **Easier Onboarding**
   - New developers only need to learn CDK
   - Single config file to understand
   - Clear documentation

## Migration Notes

### For Developers

1. **Infrastructure Changes**: Use CDK for all infrastructure changes. Terraform files are no longer used.

2. **Configuration Changes**: Edit `config/prod.yaml` for production configuration. The `config/envs/` directory no longer contains production config.

3. **Step Functions**: The fallback code in CDK now matches the JSON definition. Both use `trigger-dagster-refresh` instead of the removed container-based Lambda functions.

### For Operations

1. **Deployment**: Continue using CDK for deployments. No Terraform commands needed.

2. **Configuration**: Production configuration is now in `config/prod.yaml`. Update deployment scripts if they referenced `config/envs/prod.yaml`.

3. **Monitoring**: No changes to monitoring or alerting required.

## Related Changes

This consolidation complements the earlier work to:
- Migrate container-based Lambda functions to Dagster Cloud
- Consolidate GitHub Actions workflows using composite actions
- Simplify Docker Compose configuration with profiles

Together, these changes represent a significant simplification of the infrastructure and deployment processes.

## References

- [Lambda to Dagster Migration](../deployment/lambda-to-dagster-migration.md)
- [CDK Infrastructure README](../../infrastructure/cdk/README.md)
- [Configuration README](../../config/README.md)
