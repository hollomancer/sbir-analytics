# Test Migration Strategy

**Date**: 2025-11-29
**Status**: Phase 1 Complete, Migration Started

## ✅ Completed

### Phase 1: Foundation (Complete)
- [x] Created mock factories (`tests/mocks/`)
- [x] Created DataFrame builders (`tests/factories.py`)
- [x] Added comprehensive documentation
- [x] Verified all factories work

### Initial Migration (Complete)
- [x] Migrated Neo4j fixtures in `conftest_shared.py`
- [x] Updated `test_neo4j_client.py`
- [x] Tests passing: 30/32 (2 pre-existing failures)

## 📋 Migration Strategy

### Approach 1: Fixture-First (✅ Proven)
**Best for**: Shared fixtures used across many tests

**Pattern**:
1. Identify fixtures in conftest files
2. Replace inline Mock() with factory calls
3. All tests using fixture automatically benefit

**Example**:
```python
# Before
@pytest.fixture
def mock_driver():
    driver = MagicMock()
    driver.close = Mock()
    return driver

# After
@pytest.fixture
def mock_driver():
    return Neo4jMocks.driver()
```

**Impact**: High (affects all tests using fixture)
**Risk**: Low (single point of change)
**Effort**: Low (minutes per fixture)

### Approach 2: File-by-File (🎯 Next)
**Best for**: Files with many inline mocks/DataFrames

**Pattern**:
1. Add factory imports at top
2. Replace inline creations one by one
3. Run tests after each change
4. Commit when file complete

**Prioritization**:
- Start with files that have simple, repetitive patterns
- Avoid files with complex custom mock setups initially
- Focus on high-impact files (many usages)

### Approach 3: Incremental (📝 Ongoing)
**Best for**: New tests and test updates

**Pattern**:
- Use factories for all new tests
- Update existing tests when modifying them
- Gradually reduce inline usage over time

## 🎯 Recommended Order

### Week 1: High-Impact Fixtures
1. ✅ Neo4j fixtures (complete)
2. [ ] Enrichment client fixtures
3. [ ] Config fixtures
4. [ ] Common DataFrame fixtures

**Estimated Impact**: 100-150 inline usages eliminated
**Estimated Effort**: 2-4 hours

### Week 2: Simple File Migrations
Focus on files with repetitive, simple patterns:
1. [ ] `test_validators.py` (18 simple DataFrames)
2. [ ] `test_asset_column_helper.py` (16 DataFrames)
3. [ ] Files with <20 usages and simple patterns

**Estimated Impact**: 50-80 inline usages eliminated
**Estimated Effort**: 4-6 hours

### Week 3: Complex File Migrations
Files with many usages but complex patterns:
1. [ ] `test_analytics.py` (48 DataFrames)
2. [ ] `test_evaluator.py` (45 DataFrames)
3. [ ] `test_transitions.py` (37 DataFrames + 84 Mocks)

**Estimated Impact**: 200-300 inline usages eliminated
**Estimated Effort**: 8-12 hours

## 🚫 What NOT to Migrate (Yet)

### Complex Custom Mocks
Files where mocks have intricate custom behavior:
- Complex side_effect chains
- Stateful mocks with multiple interactions
- Mocks that simulate specific error conditions

**Strategy**: Document patterns, consider adding to factories later

### Test-Specific DataFrames
DataFrames with very specific column combinations that don't match builders:
- Custom validation test data
- Edge case data structures
- Legacy format data

**Strategy**: Keep inline, add comment explaining why

### Integration Tests
Tests that use real data or real services:
- Tests marked with `@pytest.mark.integration`
- Tests using real Neo4j instances
- Tests with real API calls

**Strategy**: These don't need mocks/builders

## 📊 Success Metrics

### Per-File Metrics
Track for each migrated file:
- Lines removed
- Inline usages eliminated
- Tests still passing
- Time spent

### Overall Metrics
Track weekly:
```bash
# Mock usages
grep -r "Mock()" tests/unit --include="*.py" | wc -l

# DataFrame creations
grep -r "pd.DataFrame" tests --include="*.py" | wc -l

# Factory imports
grep -r "from tests.mocks import" tests --include="*.py" | wc -l
grep -r "from tests.factories import DataFrameBuilder" tests --include="*.py" | wc -l
```

## 🎓 Lessons Learned

### What Works Well
1. ✅ Fixture migration has highest ROI
2. ✅ Simple, repetitive patterns migrate easily
3. ✅ Running tests frequently catches issues early

### Challenges
1. ⚠️ DataFrames with specific column names need careful handling
2. ⚠️ Some tests have complex mock setups that don't fit factories
3. ⚠️ Need to understand test intent before migrating

### Best Practices
1. **Start simple**: Migrate fixtures and simple files first
2. **Test frequently**: Run tests after each change
3. **Commit often**: Small commits make it easy to revert
4. **Document**: Note any patterns that don't fit factories
5. **Don't force it**: If migration is complex, skip and document

## 🔄 Continuous Improvement

### Add to Factories
When encountering common patterns not in factories:
1. Document the pattern
2. Add to factory if used 3+ times
3. Update existing usages

### Update Documentation
When learning new patterns:
1. Update this strategy doc
2. Add examples to REFACTORING_GUIDE.md
3. Share with team

## 📝 Migration Checklist

For each file:
- [ ] Review file for migration opportunities
- [ ] Add factory imports
- [ ] Migrate simple patterns first
- [ ] Run tests after each change
- [ ] Commit when tests pass
- [ ] Update MIGRATION_PROGRESS.md
- [ ] Document any skipped patterns

## 🎯 Next Actions

**Immediate** (Today):
1. Identify 2-3 simple files for migration
2. Migrate one file completely
3. Document any new patterns discovered

**This Week**:
1. Complete 5 file migrations
2. Add any missing factory patterns
3. Update progress tracking

**This Month**:
1. Complete high-impact file migrations
2. Achieve 30-40% reduction in inline usages
3. Document final patterns and lessons learned

---

**Last Updated**: 2025-11-29
**Next Review**: After completing 5 file migrations
