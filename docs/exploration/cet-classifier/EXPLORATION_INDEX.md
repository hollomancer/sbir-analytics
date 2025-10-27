# SBIR CET Classifier Exploration - Document Index

**Exploration Date**: October 26, 2025
**Status**: Complete
**Location**: `/Users/conradhollomon/projects/sbir-etl/`

---

## Start Here

If you're new to this exploration, start with **README_CET_EXPLORATION.md** - it provides navigation and context for all other documents.

---

## All Documents

### 1. README_CET_EXPLORATION.md ⭐ START HERE
- **Size**: 10 KB
- **Purpose**: Navigation guide and project overview
- **Contains**: Document index, status summary, integration timeline
- **Read Time**: 10-15 minutes
- **Best For**: Getting oriented, finding what you need

### 2. CET_CLASSIFIER_QUICK_REFERENCE.md
- **Size**: 16 KB
- **Purpose**: Quick lookup reference during development
- **Contains**: Architecture diagrams, API endpoints, CLI commands, performance metrics, integration checklist
- **Read Time**: 15-20 minutes
- **Best For**: Daily reference, common tasks, quick answers

### 3. CET_CLASSIFIER_ANALYSIS.md
- **Size**: 32 KB
- **Purpose**: Comprehensive technical analysis
- **Contains**: 13 sections covering all aspects from architecture to integration
- **Read Time**: 60-90 minutes
- **Best For**: Deep understanding, planning, design decisions

### 4. CET_CLASSIFIER_EXPLORATION_SUMMARY.txt
- **Size**: 8 KB
- **Purpose**: Project overview and methodology
- **Contains**: Exploration approach, key findings, artifacts analyzed
- **Read Time**: 5-10 minutes
- **Best For**: Context, methodology, validation

---

## Recommended Reading Order

**For Quick Overview** (30 minutes):
1. README_CET_EXPLORATION.md
2. CET_CLASSIFIER_QUICK_REFERENCE.md (skim)

**For Planning Integration** (2 hours):
1. README_CET_EXPLORATION.md
2. CET_CLASSIFIER_ANALYSIS.md (sections 1, 2, 3, 10, 13)
3. CET_CLASSIFIER_QUICK_REFERENCE.md (full read)

**For Complete Understanding** (3-4 hours):
1. All documents in order listed above
2. Then review source code in sbir-cet-classifier project

---

## Navigation by Topic

| Topic | Document | Section |
|-------|----------|---------|
| Project Overview | README_CET_EXPLORATION.md | Overview |
| Quick Reference | CET_CLASSIFIER_QUICK_REFERENCE.md | Any |
| Architecture | ANALYSIS.md | § 1 |
| ML Model | ANALYSIS.md | § 2 |
| CET Taxonomy | ANALYSIS.md | § 3 |
| Data Pipeline | ANALYSIS.md | § 4 |
| Enrichment | ANALYSIS.md | § 5 |
| Model Training | ANALYSIS.md | § 6 |
| API Usage | QUICK_REF.md | API Endpoints |
| CLI Usage | QUICK_REF.md | CLI Commands |
| Configuration | ANALYSIS.md | § 8 |
| Design Patterns | ANALYSIS.md | § 9 |
| Integration | ANALYSIS.md | § 10, 13 |
| Performance | QUICK_REF.md | Key Statistics |
| Testing | QUICK_REF.md | Testing |

---

## Key Information Quick Access

### Project Status
- **Overall**: Production Ready
- **Tests**: 232/232 passing
- **Coverage**: >85%
- **Performance**: All SLAs exceeded 100x+
- **Source**: `/Users/conradhollomon/projects/sbir-cet-classifier/`

### ML Model
- **Type**: TF-IDF + Logistic Regression + Calibration
- **Features**: Trigrams, chi-squared selection (50k→20k)
- **Performance**: 0.17ms per award (target: 500ms)
- **Success Rate**: 97.9%

### Architecture Highlights
- Service-oriented with dependency injection
- Externalized YAML configuration
- Lazy enrichment with 90% cache hit
- Evidence extraction with spaCy
- Comprehensive testing

### CET Categories
- **Total**: 21 categories
- **Structure**: Hierarchical (some with parent/child)
- **Keywords**: 5-10 per category
- **Version**: NSTC-2025Q1

### Integration
- **Effort**: 4-6 weeks
- **Knowledge Transfer**: 1-2 days
- **Planning**: 3-5 days
- **Implementation**: 2-3 weeks
- **Validation**: 1-2 weeks

---

## File Structure

```
/Users/conradhollomon/projects/sbir-etl/
├── README_CET_EXPLORATION.md              ⭐ START HERE
├── CET_CLASSIFIER_QUICK_REFERENCE.md      (quick lookup)
├── CET_CLASSIFIER_ANALYSIS.md             (comprehensive)
├── CET_CLASSIFIER_EXPLORATION_SUMMARY.txt (overview)
└── EXPLORATION_INDEX.md                   (this file)

Source Project:
/Users/conradhollomon/projects/sbir-cet-classifier/
├── README.md                              (project overview)
├── DEVELOPMENT.md                         (dev guide)
├── STATUS.md                              (detailed status)
├── src/sbir_cet_classifier/               (source code)
├── tests/                                 (232 tests)
└── config/                                (YAML configs)
```

---

## Next Steps

1. **Read** README_CET_EXPLORATION.md (start here)
2. **Review** CET_CLASSIFIER_QUICK_REFERENCE.md
3. **Study** relevant sections of CET_CLASSIFIER_ANALYSIS.md
4. **Explore** source code in sbir-cet-classifier project
5. **Plan** integration approach
6. **Begin** implementation

---

## Questions?

Refer to the appropriate document:
- **"What is this project?"** → README_CET_EXPLORATION.md
- **"How do I use it?"** → CET_CLASSIFIER_QUICK_REFERENCE.md
- **"How does it work?"** → CET_CLASSIFIER_ANALYSIS.md
- **"What was analyzed?"** → CET_CLASSIFIER_EXPLORATION_SUMMARY.txt

---

**Created**: October 26, 2025
**Status**: Complete and Ready for Review
