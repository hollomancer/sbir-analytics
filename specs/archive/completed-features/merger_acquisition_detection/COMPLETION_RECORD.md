# Completion Record — merger_acquisition_detection

**Status**: Implemented and merged. M&A/exit detection lives in the SEC EDGAR
enrichment path and capital-events scripts.
**Archived**: 2026-07-02

Evidence:
- `scripts/archive/data/detect_sbir_ma_events.py` (tested in tests/unit/scripts/)
- capital_events `sources/ma_events.py`
- `sbir_etl/enrichers/sec_edgar/`
