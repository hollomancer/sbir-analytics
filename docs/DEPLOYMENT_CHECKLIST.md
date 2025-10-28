# SBIR-USAspending Enrichment Pipeline: Production Deployment Checklist

**Version:** 1.0
**Last Updated:** January 2024
**Audience:** DevOps, Release Managers, System Operators

---

## Overview

This checklist ensures the enrichment pipeline is production-ready before deployment. All items must be verified and marked complete before proceeding to production.

**Use this checklist for:**
- Pre-production deployments
- Major version upgrades
- Environment migrations
- Disaster recovery validations

---

## Pre-Deployment Phase (1-2 weeks before)

### Code Quality

- [ ] **Code Review Completed**
  - All changes reviewed by at least one engineer
  - No known critical issues remain
  - Evidence: GitHub PR approvals
  - Reference: See open PRs in repository

- [ ] **Testing Suite Passes**
  - Unit tests: ✅ All passing
  - Integration tests: ✅ All passing
  - Smoke tests: ✅ All passing
  - Command: `pytest tests/ -v`
  - Required: 100% of test suite passes

- [ ] **Type Checking Passes**
  - No mypy errors
  - All function signatures typed
  - Command: `mypy src/`
  - Required: Zero errors

- [ ] **Linting Passes**
  - Code style: ✅ PEP 8 compliant
  - Import order: ✅ Correct
  - Command: `ruff check src/`
  - Required: Zero violations

### Performance Validation

- [ ] **Baseline Established**
  - Baseline benchmark created
  - File: `reports/benchmarks/baseline.json`
  - Metrics recorded:
    - Duration: ✅ Documented
    - Throughput: ✅ Documented
    - Memory peak: ✅ Documented
    - Match rate: ✅ Documented
  - Command: `python scripts/benchmark_enrichment.py --save-as-baseline`
  - Required: Baseline file exists with all metrics

- [ ] **Performance Regression Testing Complete**
  - Benchmarks run with production sample size
  - No unexpected regressions (< 10% deviation)
  - Fuzzy match performance characterized
  - Memory usage within limits
  - Command: `python scripts/detect_performance_regression.py`
  - Required: Regression status = PASS

- [ ] **Load Testing Completed**
  - Test with full 10,000+ record dataset
  - Test with production USAspending dataset (3.3M+ recipients)
  - Verify memory doesn't exceed threshold
  - Verify no OOM errors
  - Expected: < 30 min for full dataset on production hardware

- [ ] **Scaling Parameters Validated**
  - Chunk size: ✅ Tested and acceptable
  - Memory threshold: ✅ Tested and acceptable
  - Timeout values: ✅ Sufficient for workload
  - Configuration: `config/base.yaml` reviewed
  - Required: All parameters appropriate for production

### Data Quality Validation

- [ ] **Quality Gates Verified**
  - Match rate threshold: ✅ Realistic and achievable
  - Completeness checks: ✅ Passing
  - Asset checks: ✅ All passing
  - Threshold value: 0.70 (70%) or higher
  - Command: `python scripts/validate_enrichment_quality.py --enriched-file [path]`
  - Required: Match rate > 0.70

- [ ] **Sample Data Quality Report Generated**
  - Tested with representative sample
  - HTML report generated
  - JSON report generated
  - Breakdown by:
    - Phase (I, II, III): ✅ Analyzed
    - Company size: ✅ Analyzed
    - Identifier type: ✅ Analyzed
  - Command: `python scripts/validate_enrichment_quality.py --output report.html`
  - Required: Report generated without errors

- [ ] **Edge Cases Tested**
  - Empty dataset: ✅ Handled gracefully
  - Missing identifiers: ✅ Handled gracefully
  - Invalid data: ✅ Handled gracefully
  - Large awards: ✅ Processed correctly
  - Old dates: ✅ Processed correctly
  - Evidence: Test results in `tests/e2e/test_dagster_enrichment_pipeline.py`

- [ ] **Enrichment Accuracy Spot-Checked**
  - Manual review of 20-50 records
  - Verify matches are correct
  - Check for false positives
  - Document any issues found
  - Required: No systematic accuracy issues

### Documentation

- [ ] **Performance Documentation Complete**
  - File: `docs/performance/enrichment-benchmarks.md`
  - Contents verified:
    - Baseline metrics: ✅ Present
    - Tuning guide: ✅ Present
    - Troubleshooting: ✅ Present
    - Scaling guidance: ✅ Present
  - Required: All sections present and accurate

- [ ] **Configuration Guide Complete**
  - File: `docs/performance/configuration-guide.md`
  - All parameters documented:
    - `chunk_size`: ✅ Documented
    - `memory_threshold_mb`: ✅ Documented
    - `match_rate_threshold`: ✅ Documented
    - Other parameters: ✅ Documented
  - Configuration profiles provided: ✅ Yes
  - Examples included: ✅ Yes
  - Required: All parameters explained with examples

- [ ] **Operational Runbooks Created**
  - File: `docs/RUNBOOKS.md` (or equivalent)
  - Covers:
    - Normal operation: ✅ Documented
    - Troubleshooting: ✅ Documented
    - Failure recovery: ✅ Documented
    - Escalation procedures: ✅ Documented
  - Required: Created and reviewed

- [ ] **README Updated**
  - Production deployment instructions: ✅ Present
  - Configuration requirements: ✅ Present
  - Known limitations: ✅ Present
  - Support contacts: ✅ Present
  - Required: All sections complete; include link to CET deployment guide: docs/deployment/cet-assets-deployment.md

---

## Infrastructure Phase (1 week before)

### Environment Setup

- [ ] **Production Environment Provisioned**
  - Compute resources: ✅ Allocated
  - Memory available: ✅ Verified (minimum 4GB, recommended 8GB+)
  - Storage available: ✅ Verified (minimum 50GB for data)
  - Network connectivity: ✅ Verified
  - Required: All resources confirmed available

- [ ] **Database Connectivity Verified**
  - DuckDB path accessible: ✅ Tested
  - USAspending dump accessible: ✅ Tested
  - SBIR CSV accessible: ✅ Tested
  - File permissions correct: ✅ Verified
  - Command: Verify file access from target environment

- [ ] **Python Environment Configured**
  - Python 3.11+ installed: ✅ Verified
  - Virtual environment created: ✅ Verified
  - Dependencies installed: ✅ Verified
  - Command: `pip install -e .`
  - Required: All dependencies installed without errors

- [ ] **Configuration Deployed**
  - `config/base.yaml` in place: ✅ Verified
  - Production values set: ✅ Verified
  - `config/prod.yaml` created (if needed): ✅ Verified
  - Environment variables configured: ✅ Verified
  - Required: Configuration matches production requirements

### Monitoring & Logging

- [ ] **Logging Configured**
  - Log level appropriate: ✅ Verified (INFO for production)
  - Log file location: ✅ Configured
  - Log rotation: ✅ Configured
  - Log retention: ✅ Configured
  - File: `config/base.yaml` logging section

- [ ] **Monitoring Setup Complete**
  - Performance metrics collection: ✅ Enabled
  - Metrics storage: ✅ Configured
  - Prometheus (if used): ✅ Configured
  - Dashboards (if used): ✅ Created
  - Required: Monitoring infrastructure ready

- [ ] **Alerting Configured**
  - Regression detection alerts: ✅ Configured
  - Quality gate alerts: ✅ Configured
  - Performance degradation alerts: ✅ Configured
  - Notification channels: ✅ Configured (email, Slack, etc.)
  - Required: Alert recipients defined

### Backup & Recovery

- [ ] **Backup Strategy Defined**
  - Baseline benchmarks backed up: ✅ Yes
  - Configuration backed up: ✅ Yes
  - Historical metrics backed up: ✅ Yes
  - Backup location documented: ✅ Yes
  - Recovery procedure documented: ✅ Yes

- [ ] **Disaster Recovery Plan Created**
  - Failure scenarios documented: ✅ Yes
  - Recovery procedures documented: ✅ Yes
  - Recovery time objective: ✅ Defined
  - Recovery point objective: ✅ Defined
  - Team trained: ✅ Yes (optional but recommended)

---

## Testing Phase (3-5 days before)

### Functional Testing

- [ ] **End-to-End Test Run**
  - Full pipeline executes successfully: ✅ Verified
  - All assets materialize: ✅ Verified
  - Data flows correctly: ✅ Verified
  - Output quality acceptable: ✅ Verified
  - Command: Run full enrichment pipeline
  - Required: Zero errors, match rate > 0.70

- [ ] **Quality Gate Testing**
  - Good scenarios pass gates: ✅ Verified
  - Bad scenarios fail gates: ✅ Verified
  - Edge cases handled: ✅ Verified
  - Evidence: Test fixtures in `tests/fixtures/enrichment_scenarios.json`
  - Required: Gates function as expected

- [ ] **Asset Checks Functioning**
  - Match rate check: ✅ Working
  - Completeness check: ✅ Working
  - Data quality check: ✅ Working
  - Proper severity levels: ✅ Set
  - Required: All checks execute and report correctly

### Performance Testing

- [ ] **Benchmark Run on Production Hardware**
  - Benchmark script executes: ✅ Verified
  - Results within expected range: ✅ Verified
  - No unexpected regressions: ✅ Verified
  - Metrics match baseline: ✅ Within 10%
  - Command: `python scripts/detect_performance_regression.py`
  - Required: Metrics align with baseline

- [ ] **Memory Usage Profiled**
  - Peak memory recorded: ✅ Verified
  - Below threshold: ✅ Verified
  - No memory leaks: ✅ Verified (monitor for increasing peak)
  - OOM not triggered: ✅ Verified
  - Required: Memory usage stable and predictable

- [ ] **Stress Test Completed**
  - Test with 50,000+ records: ✅ Completed
  - Monitor resource usage: ✅ Verified
  - No crashes or hangs: ✅ Verified
  - Error handling works: ✅ Verified
  - Required: System stable under load

### Integration Testing

- [ ] **Dagster Integration Verified**
  - Dagster UI accessible: ✅ Verified
  - Assets visible in DAG: ✅ Verified
  - Asset runs complete successfully: ✅ Verified
  - Metadata displayed: ✅ Verified
  - Performance metrics visible: ✅ Verified

- [ ] **CI/CD Pipeline Functional**
  - Workflow triggers correctly: ✅ Verified
  - Regression detection runs: ✅ Verified
  - PR comments posted: ✅ Verified
  - Artifacts saved: ✅ Verified
  - Build fails on regressions: ✅ Verified

- [ ] **Historical Metrics Archiving Works**
  - Archive script executes: ✅ Verified
  - Files saved with timestamps: ✅ Verified
  - Query works: ✅ Verified
  - Trend analysis functions: ✅ Verified
  - Command: `python scripts/analyze_performance_history.py --archive`

### Error Handling

- [ ] **Error Scenarios Tested**
  - Missing data handled: ✅ Verified
  - Invalid data rejected: ✅ Verified
  - Timeout triggers correctly: ✅ Verified
  - Retry logic works: ✅ Verified
  - Graceful degradation: ✅ Verified

- [ ] **Recovery Procedures Validated**
  - Checkpoint resume works: ✅ Verified
  - Failed chunks retry: ✅ Verified
  - State recovery correct: ✅ Verified
  - No data loss on failure: ✅ Verified

---

## Pre-Production Phase (1-2 days before)

### Final Verification

- [ ] **All Checklist Items Signed Off**
  - Previous sections: ✅ All complete
  - Owner: ____________________
  - Date: ____________________
  - Required: 100% completion

- [ ] **Security Review Completed**
  - No hardcoded credentials: ✅ Verified
  - Environment variables used: ✅ Verified
  - File permissions appropriate: ✅ Verified
  - Data access controlled: ✅ Verified
  - Required: No security issues found

- [ ] **Performance Requirements Met**
  - Throughput acceptable: ✅ Verified (target: 50+ rec/sec)
  - Memory usage acceptable: ✅ Verified (target: < 2GB peak)
  - Quality meets threshold: ✅ Verified (target: > 70% match rate)
  - No regressions: ✅ Verified (< 10% deviation)
  - Required: All targets met or documented variance

- [ ] **Capacity Planning Reviewed**
  - Data volume projections: ✅ Documented
  - Growth plan: ✅ Documented
  - Scaling approach: ✅ Documented
  - Resource upgrade timeline: ✅ Documented
  - Required: Documented for next 12 months

### Communication

- [ ] **Team Notification Sent**
  - Deployment date: ✅ Announced
  - Maintenance window: ✅ Defined
  - Team trained: ✅ Completed
  - Support contacts: ✅ Provided
  - Escalation path: ✅ Defined
  - Required: All team members informed

- [ ] **Stakeholder Sign-Off**
  - Business owner: ✅ Approved
  - Operations: ✅ Approved
  - Security: ✅ Approved
  - Data governance: ✅ Approved
  - Required: All approvals obtained

---

## Deployment Phase (Day of)

### Pre-Deployment

- [ ] **Final Code Verification**
  - Code is tagged/released: ✅ Verified
  - Hash documented: ____________________
  - Deployed version matches code: ✅ Verified

- [ ] **Backup Completed**
  - Current baseline backed up: ✅ Verified
  - Configuration backed up: ✅ Verified
  - Rollback procedure confirmed: ✅ Verified

- [ ] **Maintenance Window Announced**
  - Users notified: ✅ Yes
  - Window duration: ____________________
  - Expected completion: ____________________

### Deployment

- [ ] **Code Deployed**
  - Files copied to production: ✅ Verified
  - Permissions set correctly: ✅ Verified
  - Configuration applied: ✅ Verified
  - Dependencies installed: ✅ Verified

- [ ] **Services Started**
  - Dagster started: ✅ Running
  - Logging active: ✅ Verified
  - Monitoring active: ✅ Verified
  - Check: `ps aux | grep dagster`

- [ ] **Initial Smoke Test Run**
  - Test pipeline executes: ✅ Verified
  - Assets materialize: ✅ Verified
  - No errors in logs: ✅ Verified
  - Baseline metrics present: ✅ Verified

### Post-Deployment

- [ ] **Health Check Completed**
  - System operational: ✅ Verified
  - No errors in logs: ✅ Verified
  - Metrics being collected: ✅ Verified
  - Alerts configured: ✅ Verified

- [ ] **Performance Verified**
  - Throughput acceptable: ✅ Verified
  - Memory usage normal: ✅ Verified
  - No errors: ✅ Verified
  - Quality acceptable: ✅ Verified

- [ ] **Monitoring Active**
  - Dashboards updated: ✅ Verified
  - Alerts armed: ✅ Verified
  - Team monitoring: ✅ Confirmed
  - Duration: ______ hours (recommend 24+ hours)

---

## Post-Deployment Phase (1-7 days after)

### Operational Monitoring

- [ ] **Daily Health Checks (Days 1-3)**
  - System running normally: ✅ Daily verified
  - No unexpected errors: ✅ Daily verified
  - Performance stable: ✅ Daily verified
  - Alerts functioning: ✅ Daily verified

- [ ] **Weekly Health Checks (Week 1)**
  - Trend analysis: ✅ Completed
  - Performance stable: ✅ Verified
  - No systemic issues: ✅ Verified
  - Historical metrics accumulating: ✅ Verified

- [ ] **Performance Regression Detection**
  - Regression detection working: ✅ Verified
  - Alert thresholds appropriate: ✅ Verified
  - No false positives: ✅ Verified
  - Team response tested: ✅ Verified

### Issue Resolution

- [ ] **Issue Tracking Established**
  - Known issues documented: ✅ Yes
  - Workarounds provided: ✅ Yes (if applicable)
  - Tracking system: ____________________
  - Escalation procedure: ____________________

- [ ] **Incident Response Ready**
  - On-call rotation established: ✅ Yes
  - Runbooks available: ✅ Yes
  - Contact tree defined: ✅ Yes
  - Response SLA: ____________________

### Stabilization (Days 3-7)

- [ ] **Extended Monitoring Completed**
  - 7+ days of operation: ✅ Verified
  - Trend data collected: ✅ Verified
  - No critical issues: ✅ Verified
  - Performance stable: ✅ Verified

- [ ] **Baseline Updated (Optional)**
  - New performance baseline: ✅ Documented (if changed)
  - Reason for change: ____________________
  - Previous baseline preserved: ✅ Yes

- [ ] **Lessons Learned Captured**
  - Issues encountered: ____________________
  - Resolutions: ____________________
  - Improvements for next deployment: ____________________
  - Documentation: ____________________

---

## Rollback Criteria

**Automatic Rollback if:**

- [ ] Critical system failure (zero matches, 100% error rate)
- [ ] Data corruption detected
- [ ] Security breach detected
- [ ] Performance degradation > 50%
- [ ] Memory leak causing repeated failures

**Manual Rollback if:**

- [ ] Multiple critical bugs discovered
- [ ] Business requirement not met
- [ ] Stakeholder approval withdrawn
- [ ] Production infrastructure insufficient

**Rollback Procedure:**

1. Notify all stakeholders
2. Stop current deployment
3. Restore from backup
4. Verify restored state
5. Post-mortem analysis
6. Fix identified issues
7. Schedule new deployment

---

## Maintenance Window

**Planned Maintenance:**

- [ ] Schedule defined: ____________________
- [ ] Duration: ____________________
- [ ] Team assigned: ____________________
- [ ] Communication sent: ✅ Yes
- [ ] Stakeholders notified: ✅ Yes

**Emergency Maintenance:**

- [ ] On-call engineer identified: ____________________
- [ ] Approval chain defined: ____________________
- [ ] Escalation contacts: ____________________

---

## Sign-Off

### Deployment Team

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Project Lead | _______________ | _____ | _______________ |
| DevOps/Infrastructure | _______________ | _____ | _______________ |
| QA Lead | _______________ | _____ | _______________ |
| Operations | _______________ | _____ | _______________ |

### Stakeholders

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Business Owner | _______________ | _____ | _______________ |
| Security | _______________ | _____ | _______________ |
| Data Governance | _______________ | _____ | _______________ |

---

## Deployment Summary

**Deployment Date:** ____________________
**Deployed Version:** ____________________
**Deployed By:** ____________________
**Duration:** ____________________
**Issues Encountered:** ____________________
**Resolution:** ____________________
**Post-Deployment Status:** ✅ Successful / ⚠️ Partial / ❌ Rollback

**Notes:**
____________________
____________________
____________________

---

## Appendix: Quick Reference

### Critical Commands

```bash
# Verify deployment
python scripts/benchmark_enrichment.py --sample-size 100

# Check system health
ps aux | grep dagster
df -h | grep data
free -h

# Run regression detection
python scripts/detect_performance_regression.py

# View logs
tail -f logs/sbir-etl.log

# Rollback procedure
# 1. git checkout <previous-tag>
# 2. Restore baseline: cp reports/benchmarks/baseline.backup.json reports/benchmarks/baseline.json
# 3. Restart services
```

### Contact Information

**On-Call Engineer:** ____________________
**Backup On-Call:** ____________________
**Operations Lead:** ____________________
**Escalation Contact:** ____________________

### Related Documentation

- Performance Benchmarks: `docs/performance/enrichment-benchmarks.md`
- Configuration Guide: `docs/performance/configuration-guide.md`
- Operational Runbooks: `docs/RUNBOOKS.md`
- Technical Architecture: `docs/ARCHITECTURE.md`

---

**Last Updated:** January 2024
**Next Review:** [Date + 6 months]
**Owner:** [Your Name/Team]
