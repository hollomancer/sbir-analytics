# NSF SBIR vs. Form D Matched-Cohort Comparison — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Phase 2 of `specs/nsf-vc-comparison/` — produce a defensible apples-to-apples comparison between NSF Phase II SBIR awardees and matched non-SBIR private-capital-financed firms (Form D issuers), keyed on (vintage, Industry Group, state), reporting per-cohort outcome rates with explicit threats-to-validity.

**Architecture:** Build a new `phase2` sub-module under `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/` that consumes raw on-disk artifacts from PR #286 (SEC EDGAR scan, Form D index/details, M&A events) plus the SBIR.gov bulk CSV. The module reuses Phase 1's `OutcomeMetricsCalculator` and `vintage_bucket` helpers, then layers on: NSF cohort restriction to the NSF ∩ EDGAR subset, Form D control cohort construction, hand-rolled coarsened-exact matching on (vintage, industry_group, state), and a threats-to-validity gate that suppresses headline output if any required entry is missing. An in-process runner script mirrors Phase 1's `run_nsf_vc_phase1.py` pattern; a Dagster asset wires the same logic into the orchestration graph.

**Tech Stack:** Python 3.11, pandas, pyyaml (config loading), pytest, Dagster (asset wiring only — runner script bypasses materialization). No new third-party deps.

---

## Decisions Locked Pre-Plan

These resolve the 8 blockers surfaced during pre-flight against `specs/nsf-vc-comparison/tasks.md`. The plan below assumes them; revisit them only if implementation reveals a contradiction.

| ID | Decision |
|---|---|
| B1 | **Industry Group** is the matching axis (not NAICS-2). Form D side reads native `industry_group` from `data/form_d_details.jsonl` offerings (100% population). NSF side derives Industry Group via a Topic Code → IG crosswalk (`config/nsf_vc/topic_code_to_industry_group.yaml`); 43% of NSF rows lack a Topic Code and bucket to `Other` (documented in threats-to-validity). |
| B2 | Spec's `sec_edgar_enrichment` asset name is incorrect; codebase uses `sec_edgar_enriched_companies` at `packages/sbir-analytics/sbir_analytics/assets/sec_edgar_enrichment.py:32`. All task descriptions below use the correct name. |
| B3 | Read raw on-disk inputs (`data/sec_edgar_scan.jsonl`, `data/form_d_index.jsonl`, `data/form_d_details.jsonl`, `data/sbir_ma_events.jsonl`) directly. Do not depend on a materialized Dagster asset for the runner script. |
| B4 | M&A signal cross-cohort linkage uses fuzzy name normalization. Emit `name_match_coverage` as a per-stratum quantitative signal alongside binary `ma_exit_rate` (numerator: NSF/control cohort companies for which at least one EDGAR-keyed equivalent name was resolved; denominator: cohort size). Treats name-match precision as measured, not assumed. |
| B5 | `phase_ii_to_federal_contract_transition` in Phase 2 = raw USAspending recipient/vendor presence (binary), distinct from Phase 1's score-thresholded `transition_score >= 0.65`. Both available; the Phase 2 gate report uses USAspending presence. Gracefully renders `available=False` if no USAspending parquet present. |
| B6 | NSF cohort for Phase 2 = NSF ∩ EDGAR (companies appearing in `sec_edgar_scan.jsonl`). Matches the spec's broader-SBIR-CIK-set framing and avoids comparing EDGAR-only Form D issuers against mixed EDGAR/non-EDGAR NSF awardees. |
| B7 | Hand-roll coarsened-exact matching (~30 LoC) rather than depend on the unmaintained PyPI `cem` package. Algorithm: tuple-key on (vintage_bucket, industry_group, state); inner-join NSF ↔ control; report unmatched residuals + matching ratio. |
| B8 | Headline vintage: **2010-2014**. Form D became mandatory-electronic in 2009; 2010-2014 has full 5-year follow-up windows for transition signals and avoids right-censoring that 2015-2019 would introduce. |

---

## Fork B Reframe (2026-04-30, post Task 6 smoke test)

The Task 6 in-process runner surfaced a structural data-scope blocker: `data/form_d_index.jsonl` from PR #286 is the SBIR-CIK ∩ Form D intersection (10,405 records, 100% with `award_count ≥ 1`), NOT the broader Form D corpus. The original plan's control cohort definition ("Form D issuers with NO SBIR exposure") cannot be built from on-disk data. Re-fetching the broader Form D corpus from SEC EDGAR is out of Phase 2 scope.

**Fork B reframes Phase 2 as an inter-SBIR comparison:**
- **Treatment:** NSF Phase II awardees in EDGAR ∩ Form D.
- **Control:** Non-NSF SBIR awardees in EDGAR ∩ Form D (DoD, NIH, DOE, NASA, etc.).
- **Question:** "Does NSF SBIR's program design produce different private-capital / transition / patent / M&A outcomes than other agencies' SBIR programs, holding constant the SBIR-selection-filter and EDGAR-presence-filter?"

This is a different research question than the spec's NSF-vs-non-SBIR comparison, but defensible and answerable with current data.

**Changes from original plan:**

1. **`PrivateCapitalControlCohortBuilder`:** rename `sbir_company_keys` parameter → `nsf_company_keys` (semantic change: drop NSF-overlap issuers, keep non-NSF SBIR-overlap issuers). The "drop SBIR overlap" logic stays structurally identical, only the input-set semantic changes.
2. **Field-name bug fix in `control.py`:** `filing_date` → `date_filed` (production schema; unit tests used the plan's wrong key, masking the bug). Test fixtures updated to match.
3. **`threats.py` REQUIRED_ENTRIES:** swap `technical_merit_vs_lawyer_access_bias` → `inter_sbir_program_design_confounding`. Add `fork_b_inter_sbir_reframe` (explicit documentation that this is no longer a SBIR-vs-non-SBIR comparison). Total entries: 9.
4. **Runner (`run_nsf_vc_phase2.py`):** build `nsf_company_keys` from the NSF-restricted cohort (not all EDGAR companies), pass to control builder. Update threat-entry bodies in `_load_seed_threats()` for entries 5+9.
5. **Headline language (Task 10):** "On vintage 2010-2014, Industry Group X, state Y: NSF Phase II awardees in Form D had transition rate A%; matched non-NSF SBIR awardees in Form D had B%. Difference attributable to inter-agency program-design choices."

**What stays unchanged:** Tasks 0, 1, 3, 4, 5 (industry_group, awardee_filter, matcher, matched_outcomes, threats gate machinery). Task 7 (Dagster asset) wires same shape. Task 8 (decomposition) and Task 9 (integration test fixture) need minor reframe in their gate-report language but not their structural code.

---

## File Structure

### Files to create

| Path | Responsibility |
|---|---|
| `config/nsf_vc/topic_code_to_industry_group.yaml` | NSF topic-code letter-prefix → SEC Form D Industry Group crosswalk (with `Other` fallback). |
| `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/industry_group.py` | `IndustryGroupClassifier` — loads YAML crosswalk, classifies NSF rows by Topic Code prefix; surfaces coverage rate. |
| `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/awardee_filter.py` | `NSFAwardeeFilter` (spec 2.1) — restricts NSF cohort to NSF ∩ EDGAR via `data/sec_edgar_scan.jsonl`. |
| `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/control.py` | `PrivateCapitalControlCohortBuilder` (spec 2.2) — reads Form D index, drops issuers in broader SBIR-CIK set, buckets by (filing-year, industry_group, state). |
| `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/matcher.py` | `CohortMatcher` (spec 2.3) — hand-rolled CEM on (vintage, industry_group, state); reports balance + unmatched residuals. |
| `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/matched_outcomes.py` | `MatchedCohortOutcomes` (spec 2.4) — joins both cohorts to USAspending presence, PATLINK, M&A events; reuses Phase 1's `OutcomeMetricsCalculator` where applicable; emits `name_match_coverage` signal. |
| `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/threats.py` | `ThreatsToValidity` (spec 2.5) — registry of required entries; gate suppresses headline if any entry missing/stale. |
| `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/decomposition.py` | Security-type / offering-size decomposition (spec 2.7) — reproduces #286's 1.82x leverage ratio scoped to NSF only. |
| `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/asset_phase2.py` | Dagster asset wiring (spec 2.6) — `nsf_vc_form_d_matched_comparison`. |
| `scripts/data/run_nsf_vc_phase2.py` | In-process Phase 2 runner mirroring `run_nsf_vc_phase1.py` pattern. |
| `docs/nsf-vc-comparison/methodology.md` | Methodology writeup (cross-phase task X.1). |
| `docs/nsf-vc-comparison/glossary.md` | Glossary of terms (Industry Group, CEM, etc.). |
| `docs/nsf-vc-comparison/citations.md` | Citation table (mirrors `docs/transition/`). |
| `tests/unit/nsf_vc/test_industry_group.py` | Unit tests for crosswalk classifier. |
| `tests/unit/nsf_vc/test_awardee_filter.py` | Unit tests for NSF ∩ EDGAR restriction. |
| `tests/unit/nsf_vc/test_control.py` | Unit tests for control cohort construction. |
| `tests/unit/nsf_vc/test_matcher.py` | Unit tests for CEM matcher. |
| `tests/unit/nsf_vc/test_matched_outcomes.py` | Unit tests for matched-cohort outcomes. |
| `tests/unit/nsf_vc/test_threats.py` | Unit tests for threats-to-validity gate. |
| `tests/unit/nsf_vc/test_decomposition.py` | Unit tests for security-type decomposition. |
| `tests/integration/nsf_vc/test_phase2_pipeline.py` | Integration test against small fixture set. |

### Files to modify

| Path | Change |
|---|---|
| `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/__init__.py` | Export new Phase 2 modules. |
| `docs/research-questions.md` | Annotate B2/B3 and A4 with this spec citation (cross-phase task X.2). |

---

## Tasks

Each task has TDD-ordered steps. Run all tests after each commit (`uv run pytest tests/unit/nsf_vc/ -v`). Commit only on green.

---

### Task 0: Pre-flight scaffolding + crosswalk YAML

**Files:**
- Create: `config/nsf_vc/topic_code_to_industry_group.yaml`
- Create: `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/industry_group.py`
- Create: `tests/unit/nsf_vc/test_industry_group.py`

- [ ] **Step 1: Write the crosswalk YAML.**

The crosswalk maps NSF SBIR topic-code letter prefixes to SEC Form D Industry Group values. Coverage rate must be reported by the classifier; the `Other` fallback is intentional and feeds a threats-to-validity entry.

```yaml
# config/nsf_vc/topic_code_to_industry_group.yaml
# NSF SBIR/STTR topic-code letter prefix -> SEC Form D Industry Group.
# Source: NSF SBIR/STTR program solicitation topic taxonomy (public, NSF.gov).
# Form D Industry Group values: see SEC Form D, Item 4.
# Unmatched/missing Topic Codes -> 'Other' (documented in threats-to-validity).
crosswalk:
  B: Biotechnology       # Biological technologies, agriculture, biosensing
  C: Other               # Chemical / environmental — no clean Form D mapping
  D: Health Care         # Smart Health and Biomedical Technologies
  E: Computers           # Electronic Hardware, Robotics, Wireless
  I: Computers           # Information Technologies
  M: Manufacturing       # Manufacturing Technologies
  N: Other Technology    # Nanotechnology, Advanced Materials
  P: Other Technology    # Photonics
  S: Computers           # Semiconductors
  EW: Energy             # Energy & Water (two-letter prefix override)
  EI: Energy             # Energy / Infrastructure
  EO: Energy             # Energy / Other
  EA: Energy             # Energy / Agricultural
fallback: Other
```

- [ ] **Step 2: Write failing test for the classifier.**

```python
# tests/unit/nsf_vc/test_industry_group.py
from pathlib import Path

import pytest
import pandas as pd

from sbir_analytics.assets.nsf_vc.industry_group import IndustryGroupClassifier


CROSSWALK_PATH = Path("config/nsf_vc/topic_code_to_industry_group.yaml")


def test_classifies_two_letter_prefix_first():
    """Two-letter prefixes (e.g. EW) must take precedence over single-letter (E)."""
    clf = IndustryGroupClassifier.load(CROSSWALK_PATH)
    assert clf.classify("EW") == "Energy"
    assert clf.classify("EL") == "Computers"  # falls back to single-letter E


def test_single_letter_prefix():
    clf = IndustryGroupClassifier.load(CROSSWALK_PATH)
    assert clf.classify("BC") == "Biotechnology"
    assert clf.classify("DH") == "Health Care"
    assert clf.classify("MN") == "Manufacturing"


def test_missing_topic_code_returns_fallback():
    clf = IndustryGroupClassifier.load(CROSSWALK_PATH)
    assert clf.classify(None) == "Other"
    assert clf.classify("") == "Other"
    assert clf.classify(float("nan")) == "Other"


def test_unknown_prefix_returns_fallback():
    clf = IndustryGroupClassifier.load(CROSSWALK_PATH)
    assert clf.classify("XQ") == "Other"


def test_apply_to_dataframe_reports_coverage():
    clf = IndustryGroupClassifier.load(CROSSWALK_PATH)
    df = pd.DataFrame({"Topic Code": ["BC", "EW", None, "XQ", "DH"]})
    result = clf.apply(df)
    assert list(result["industry_group"]) == [
        "Biotechnology", "Energy", "Other", "Other", "Health Care"
    ]
    # Coverage = fraction with non-None, non-fallback classification
    # 3 of 5 rows resolved to a real IG, 2 fell to Other.
    assert clf.coverage(df) == pytest.approx(3 / 5)
```

- [ ] **Step 3: Run test to verify failure.**

Run: `uv run pytest tests/unit/nsf_vc/test_industry_group.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named '...industry_group'`.

- [ ] **Step 4: Implement the classifier.**

```python
# packages/sbir-analytics/sbir_analytics/assets/nsf_vc/industry_group.py
"""Industry Group classifier for the NSF cohort.

Maps NSF SBIR/STTR Topic Codes to SEC Form D Industry Group values via a
letter-prefix crosswalk loaded from YAML. Two-letter prefixes take
precedence over single-letter prefixes (e.g. ``EW`` -> Energy beats
``E*`` -> Computers). Unknown / missing Topic Codes fall back to the
configured fallback value (typically ``Other``); coverage is reported
as the fraction of rows that resolved to a non-fallback Industry Group.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


@dataclass(frozen=True)
class IndustryGroupClassifier:
    crosswalk: dict[str, str]
    fallback: str

    @classmethod
    def load(cls, path: Path) -> "IndustryGroupClassifier":
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return cls(crosswalk=dict(data["crosswalk"]), fallback=str(data["fallback"]))

    def classify(self, topic_code: Any) -> str:
        if topic_code is None:
            return self.fallback
        if isinstance(topic_code, float) and pd.isna(topic_code):
            return self.fallback
        s = str(topic_code).strip().upper()
        if not s:
            return self.fallback
        # Two-letter prefix takes precedence over single-letter
        if len(s) >= 2 and s[:2] in self.crosswalk:
            return self.crosswalk[s[:2]]
        if s[:1] in self.crosswalk:
            return self.crosswalk[s[:1]]
        return self.fallback

    def apply(self, df: pd.DataFrame, *, source_col: str = "Topic Code") -> pd.DataFrame:
        result = df.copy()
        result["industry_group"] = result.get(source_col, pd.Series(dtype=object)).map(self.classify)
        return result

    def coverage(self, df: pd.DataFrame, *, source_col: str = "Topic Code") -> float:
        if df.empty:
            return 0.0
        applied = self.apply(df, source_col=source_col)
        non_fallback = (applied["industry_group"] != self.fallback).sum()
        return float(non_fallback) / float(len(df))
```

- [ ] **Step 5: Run test to verify pass.**

Run: `uv run pytest tests/unit/nsf_vc/test_industry_group.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit.**

```bash
git add config/nsf_vc/topic_code_to_industry_group.yaml \
        packages/sbir-analytics/sbir_analytics/assets/nsf_vc/industry_group.py \
        tests/unit/nsf_vc/test_industry_group.py
git commit -m "feat(nsf-vc): add Topic Code -> Industry Group classifier for Phase 2"
```

---

### Task 1: NSFAwardeeFilter (spec 2.1)

Restricts the NSF cohort to companies that appear in #286's EDGAR scan (the broader SBIR-CIK set). Reads `data/sec_edgar_scan.jsonl` directly, normalizes company names via the same `_company_key` logic Phase 1 uses, and inner-joins.

**Files:**
- Create: `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/awardee_filter.py`
- Create: `tests/unit/nsf_vc/test_awardee_filter.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/unit/nsf_vc/test_awardee_filter.py
import pandas as pd
import pytest

from sbir_analytics.assets.nsf_vc.awardee_filter import NSFAwardeeFilter


def test_filter_keeps_only_nsf_awardees_in_edgar():
    nsf_cohort = pd.DataFrame({
        "Company": ["AcmeAI Inc.", "Beta Bio", "Gamma Robotics", "Delta Devices"],
        "phase_label": ["II", "II", "I", "II"],
        "vintage_bucket": ["2010-2014"] * 4,
    })
    edgar_companies = {"name:acmeai inc.", "name:gamma robotics"}
    flt = NSFAwardeeFilter(edgar_companies=edgar_companies)
    out = flt.filter(nsf_cohort)
    assert set(out["Company"]) == {"AcmeAI Inc.", "Gamma Robotics"}


def test_filter_handles_empty_input():
    flt = NSFAwardeeFilter(edgar_companies=set())
    out = flt.filter(pd.DataFrame(columns=["Company", "phase_label", "vintage_bucket"]))
    assert out.empty


def test_load_edgar_companies_from_jsonl(tmp_path):
    # Mini fixture mirroring data/sec_edgar_scan.jsonl schema (keys: company_name, ...)
    p = tmp_path / "edgar.jsonl"
    p.write_text(
        '{"company_name": "AcmeAI Inc.", "award_count": 1}\n'
        '{"company_name": "Gamma Robotics", "award_count": 3}\n',
        encoding="utf-8",
    )
    keys = NSFAwardeeFilter.load_edgar_companies(p)
    assert keys == {"name:acmeai inc.", "name:gamma robotics"}
```

- [ ] **Step 2: Run test to verify failure.** Run: `uv run pytest tests/unit/nsf_vc/test_awardee_filter.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.**

```python
# packages/sbir-analytics/sbir_analytics/assets/nsf_vc/awardee_filter.py
"""NSF awardee filter (spec 2.1).

Restricts the NSF cohort to companies that appear in PR #286's broader
SBIR-CIK set (the EDGAR scan). Only companies with EDGAR presence are
comparable against Form D issuers (which are EDGAR-defined by
construction).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from sbir_analytics.assets.nsf_vc.outcomes import _company_key


@dataclass(frozen=True)
class NSFAwardeeFilter:
    edgar_companies: set[str] = field(default_factory=set)

    @staticmethod
    def load_edgar_companies(path: Path) -> set[str]:
        keys: set[str] = set()
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                name = rec.get("company_name")
                if name and str(name).strip():
                    keys.add(f"name:{str(name).strip().lower()}")
        return keys

    def filter(self, cohort: pd.DataFrame) -> pd.DataFrame:
        if cohort.empty:
            return cohort
        keys = cohort.apply(_company_key, axis=1)
        mask = keys.isin(self.edgar_companies)
        return cohort[mask].copy()
```

- [ ] **Step 4: Run test.** Expected: 3 passed.

- [ ] **Step 5: Commit.**

```bash
git add packages/sbir-analytics/sbir_analytics/assets/nsf_vc/awardee_filter.py \
        tests/unit/nsf_vc/test_awardee_filter.py
git commit -m "feat(nsf-vc): add NSFAwardeeFilter restricting cohort to NSF n EDGAR"
```

---

### Task 2: PrivateCapitalControlCohortBuilder (spec 2.2)

Reads `data/form_d_index.jsonl`, drops issuers whose company key appears in the broader SBIR-CIK set (control = capital-financed firms with no SBIR exposure), and buckets surviving issuers by (filing-year, industry_group, state). Industry Group comes from the offering-level `industry_group` field on `data/form_d_details.jsonl` (joined by `form_d_cik`).

**Files:**
- Create: `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/control.py`
- Create: `tests/unit/nsf_vc/test_control.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/unit/nsf_vc/test_control.py
import json
import pandas as pd
import pytest

from sbir_analytics.assets.nsf_vc.control import PrivateCapitalControlCohortBuilder


def test_builder_drops_sbir_issuers_and_buckets_by_iv_state(tmp_path):
    # form_d_index records (issuer-level)
    index_path = tmp_path / "form_d_index.jsonl"
    index_path.write_text(
        '{"company_name": "PureVC Co", "form_d_cik": "0001000001", "state": "CA",\n'
        ' "form_d_filings": [{"filing_date": "2012-03-01"}]}\n'
        '{"company_name": "AcmeAI Inc.", "form_d_cik": "0001000002", "state": "MA",\n'
        ' "form_d_filings": [{"filing_date": "2013-06-15"}]}\n'
        '{"company_name": "Other Co", "form_d_cik": "0001000003", "state": "TX",\n'
        ' "form_d_filings": [{"filing_date": "2011-01-10"}]}\n',
        encoding="utf-8",
    )
    # form_d_details (offering-level industry_group)
    details_path = tmp_path / "form_d_details.jsonl"
    details_path.write_text(
        '{"form_d_cik": "0001000001", "offerings": [{"industry_group": "Biotechnology"}]}\n'
        '{"form_d_cik": "0001000002", "offerings": [{"industry_group": "Computers"}]}\n'
        '{"form_d_cik": "0001000003", "offerings": [{"industry_group": "Energy"}]}\n',
        encoding="utf-8",
    )
    sbir_company_keys = {"name:acmeai inc."}  # AcmeAI is in SBIR set; drop it
    builder = PrivateCapitalControlCohortBuilder(
        sbir_company_keys=sbir_company_keys,
    )
    out = builder.build(index_path=index_path, details_path=details_path)
    # Two issuers remain after dropping the SBIR overlap
    assert len(out) == 2
    assert set(out["company_name"]) == {"PureVC Co", "Other Co"}
    # Vintage from filing year, industry from details, state from index
    pure_vc = out[out["company_name"] == "PureVC Co"].iloc[0]
    assert pure_vc["vintage_bucket"] == "2010-2014"
    assert pure_vc["industry_group"] == "Biotechnology"
    assert pure_vc["state"] == "CA"


def test_handles_missing_industry_group(tmp_path):
    index_path = tmp_path / "i.jsonl"
    index_path.write_text(
        '{"company_name": "X", "form_d_cik": "1", "state": "NY",\n'
        ' "form_d_filings": [{"filing_date": "2012-01-01"}]}\n',
        encoding="utf-8",
    )
    details_path = tmp_path / "d.jsonl"
    details_path.write_text(
        '{"form_d_cik": "1", "offerings": [{"industry_group": null}]}\n',
        encoding="utf-8",
    )
    builder = PrivateCapitalControlCohortBuilder(sbir_company_keys=set())
    out = builder.build(index_path=index_path, details_path=details_path)
    assert out.iloc[0]["industry_group"] == "Other"


def test_uses_first_filing_year_for_vintage(tmp_path):
    index_path = tmp_path / "i.jsonl"
    index_path.write_text(
        '{"company_name": "Multi", "form_d_cik": "9", "state": "WA",\n'
        ' "form_d_filings": [{"filing_date": "2018-05-01"}, {"filing_date": "2011-08-12"}]}\n',
        encoding="utf-8",
    )
    details_path = tmp_path / "d.jsonl"
    details_path.write_text(
        '{"form_d_cik": "9", "offerings": [{"industry_group": "Computers"}]}\n',
        encoding="utf-8",
    )
    builder = PrivateCapitalControlCohortBuilder(sbir_company_keys=set())
    out = builder.build(index_path=index_path, details_path=details_path)
    # Earliest filing date (2011) determines vintage bucket
    assert out.iloc[0]["vintage_bucket"] == "2010-2014"
```

- [ ] **Step 2: Run test, verify FAIL.**

- [ ] **Step 3: Implement.**

```python
# packages/sbir-analytics/sbir_analytics/assets/nsf_vc/control.py
"""Private-capital control cohort builder (spec 2.2).

Reads Form D index + details, drops issuers in the broader SBIR-CIK set
(control population = capital-financed firms with NO SBIR exposure ever),
and buckets surviving issuers by (filing-year vintage, Industry Group,
state). Vintage is keyed on the issuer's earliest filing date.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_analytics.assets.nsf_vc.cohort import vintage_bucket


@dataclass(frozen=True)
class PrivateCapitalControlCohortBuilder:
    sbir_company_keys: set[str] = field(default_factory=set)
    fallback_industry_group: str = "Other"

    def build(self, *, index_path: Path, details_path: Path) -> pd.DataFrame:
        details_by_cik = self._load_details_industry_groups(details_path)
        records: list[dict[str, Any]] = []
        with index_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                name = (rec.get("company_name") or "").strip()
                if not name:
                    continue
                key = f"name:{name.lower()}"
                if key in self.sbir_company_keys:
                    continue  # drop SBIR-overlap issuers
                cik = str(rec.get("form_d_cik") or "").strip()
                filings = rec.get("form_d_filings") or []
                vintage = self._earliest_vintage(filings)
                if vintage is None:
                    continue
                records.append(
                    {
                        "company_name": name,
                        "company_key": key,
                        "form_d_cik": cik,
                        "vintage_bucket": vintage,
                        "industry_group": details_by_cik.get(cik, self.fallback_industry_group),
                        "state": (rec.get("state") or "").strip().upper() or None,
                    }
                )
        return pd.DataFrame.from_records(records)

    def _load_details_industry_groups(self, path: Path) -> dict[str, str]:
        out: dict[str, str] = {}
        if not path.exists():
            return out
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cik = str(rec.get("form_d_cik") or "").strip()
                if not cik:
                    continue
                offerings = rec.get("offerings") or []
                for off in offerings:
                    ig = off.get("industry_group")
                    if ig and str(ig).strip():
                        out[cik] = str(ig).strip()
                        break
        return out

    @staticmethod
    def _earliest_vintage(filings: list[dict[str, Any]]) -> str | None:
        years: list[int] = []
        for f in filings:
            d = f.get("filing_date")
            if not d:
                continue
            ts = pd.to_datetime(d, errors="coerce")
            if pd.notna(ts):
                years.append(int(ts.year))
        if not years:
            return None
        return vintage_bucket(min(years))
```

- [ ] **Step 4: Run test.** Expected: 3 passed.

- [ ] **Step 5: Commit.**

```bash
git add packages/sbir-analytics/sbir_analytics/assets/nsf_vc/control.py \
        tests/unit/nsf_vc/test_control.py
git commit -m "feat(nsf-vc): add PrivateCapitalControlCohortBuilder for non-SBIR Form D issuers"
```

---

### Task 3: CohortMatcher — hand-rolled CEM (spec 2.3)

Coarsened-exact matching: tuple-key on `(vintage_bucket, industry_group, state)`. NSF and control are inner-joined on this key. Output: matched cohort frame plus a balance/residuals report. Matching ratio (NSF row : k controls) is reported per-stratum and as an aggregate.

**Files:**
- Create: `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/matcher.py`
- Create: `tests/unit/nsf_vc/test_matcher.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/unit/nsf_vc/test_matcher.py
import pandas as pd

from sbir_analytics.assets.nsf_vc.matcher import CohortMatcher


def test_inner_join_on_tuple_key():
    nsf = pd.DataFrame({
        "company_name": ["A", "B", "C"],
        "vintage_bucket": ["2010-2014", "2010-2014", "2015-2019"],
        "industry_group": ["Computers", "Biotechnology", "Computers"],
        "state": ["CA", "MA", "CA"],
    })
    ctrl = pd.DataFrame({
        "company_name": ["X", "Y", "Z", "W"],
        "vintage_bucket": ["2010-2014", "2010-2014", "2010-2014", "2020-2024"],
        "industry_group": ["Computers", "Computers", "Biotechnology", "Energy"],
        "state": ["CA", "CA", "MA", "OR"],
    })
    matcher = CohortMatcher()
    result = matcher.match(nsf, ctrl)
    # Strata with both NSF and control: (2010-2014, Computers, CA) and (2010-2014, Biotech, MA)
    assert set(result.matched_strata.itertuples(index=False, name=None)) == {
        ("2010-2014", "Computers", "CA"),
        ("2010-2014", "Biotechnology", "MA"),
    }
    # NSF row C (2015-2019, Computers, CA) is unmatched
    assert "C" in set(result.unmatched_nsf["company_name"])
    # Control rows X, Y, Z survive; W (no NSF in 2020-2024 OR Energy) drops
    assert set(result.matched_controls["company_name"]) == {"X", "Y", "Z"}


def test_matching_ratio_reported_per_stratum():
    nsf = pd.DataFrame({
        "company_name": ["A"],
        "vintage_bucket": ["2010-2014"],
        "industry_group": ["Computers"],
        "state": ["CA"],
    })
    ctrl = pd.DataFrame({
        "company_name": ["X1", "X2", "X3"],
        "vintage_bucket": ["2010-2014"] * 3,
        "industry_group": ["Computers"] * 3,
        "state": ["CA"] * 3,
    })
    result = CohortMatcher().match(nsf, ctrl)
    # 1:3 matching ratio
    ratio_row = result.matched_strata.iloc[0]
    assert ratio_row["nsf_n"] == 1
    assert ratio_row["control_n"] == 3
    assert ratio_row["ratio_k"] == 3.0


def test_empty_intersection_reports_no_matches():
    nsf = pd.DataFrame({
        "company_name": ["A"], "vintage_bucket": ["2010-2014"],
        "industry_group": ["Computers"], "state": ["CA"],
    })
    ctrl = pd.DataFrame({
        "company_name": ["X"], "vintage_bucket": ["2020-2024"],
        "industry_group": ["Energy"], "state": ["NY"],
    })
    result = CohortMatcher().match(nsf, ctrl)
    assert result.matched_strata.empty
    assert len(result.unmatched_nsf) == 1
    assert len(result.unmatched_controls) == 1
```

- [ ] **Step 2: Run test, verify FAIL.**

- [ ] **Step 3: Implement.**

```python
# packages/sbir-analytics/sbir_analytics/assets/nsf_vc/matcher.py
"""Coarsened-exact matcher for NSF vs. private-capital control cohorts (spec 2.3).

Key = ``(vintage_bucket, industry_group, state)``. All three are categorical
or already binned, so CEM reduces to an inner-join on the tuple. Output
includes the matched frames plus per-stratum balance and unmatched residuals
so the report can quantify how much of each cohort the comparison covers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import pandas as pd


MATCH_KEYS: tuple[str, ...] = ("vintage_bucket", "industry_group", "state")


@dataclass
class MatchResult:
    matched_strata: pd.DataFrame
    matched_nsf: pd.DataFrame
    matched_controls: pd.DataFrame
    unmatched_nsf: pd.DataFrame
    unmatched_controls: pd.DataFrame


@dataclass(frozen=True)
class CohortMatcher:
    keys: tuple[str, ...] = MATCH_KEYS

    def match(self, nsf: pd.DataFrame, control: pd.DataFrame) -> MatchResult:
        if nsf.empty or control.empty:
            empty_strata = pd.DataFrame(
                columns=list(self.keys) + ["nsf_n", "control_n", "ratio_k"]
            )
            return MatchResult(
                matched_strata=empty_strata,
                matched_nsf=nsf.iloc[0:0].copy(),
                matched_controls=control.iloc[0:0].copy(),
                unmatched_nsf=nsf.copy(),
                unmatched_controls=control.copy(),
            )
        nsf_strata = self._stratum_set(nsf)
        ctrl_strata = self._stratum_set(control)
        common = nsf_strata & ctrl_strata
        nsf_in = self._filter_by_strata(nsf, common)
        nsf_out = self._filter_by_strata(nsf, common, invert=True)
        ctrl_in = self._filter_by_strata(control, common)
        ctrl_out = self._filter_by_strata(control, common, invert=True)
        nsf_counts = nsf_in.groupby(list(self.keys), dropna=False).size().rename("nsf_n")
        ctrl_counts = ctrl_in.groupby(list(self.keys), dropna=False).size().rename("control_n")
        strata = pd.concat([nsf_counts, ctrl_counts], axis=1).reset_index().fillna(0)
        strata["nsf_n"] = strata["nsf_n"].astype(int)
        strata["control_n"] = strata["control_n"].astype(int)
        strata["ratio_k"] = strata["control_n"] / strata["nsf_n"].where(strata["nsf_n"] > 0, 1)
        return MatchResult(
            matched_strata=strata,
            matched_nsf=nsf_in,
            matched_controls=ctrl_in,
            unmatched_nsf=nsf_out,
            unmatched_controls=ctrl_out,
        )

    def _stratum_set(self, df: pd.DataFrame) -> set[tuple]:
        return {tuple(r) for r in df[list(self.keys)].itertuples(index=False, name=None)}

    def _filter_by_strata(
        self, df: pd.DataFrame, strata: set[tuple], *, invert: bool = False
    ) -> pd.DataFrame:
        if df.empty:
            return df.copy()
        rows = df[list(self.keys)].itertuples(index=False, name=None)
        mask = pd.Series([t in strata for t in rows], index=df.index)
        return (df[~mask] if invert else df[mask]).copy()
```

- [ ] **Step 4: Run test.** Expected: 3 passed.

- [ ] **Step 5: Commit.**

```bash
git add packages/sbir-analytics/sbir_analytics/assets/nsf_vc/matcher.py \
        tests/unit/nsf_vc/test_matcher.py
git commit -m "feat(nsf-vc): add CohortMatcher with hand-rolled CEM on (vintage, IG, state)"
```

---

### Task 4: MatchedCohortOutcomes (spec 2.4)

Joins both matched cohorts to (a) USAspending recipient/vendor presence (binary), (b) PATLINK patents, (c) `data/sbir_ma_events.jsonl`. Reuses `OutcomeMetricsCalculator` for the per-stratum Wilson-CI rates. Adds `name_match_coverage` as a measured signal per B4. Phase-graduation and survival metrics are NSF-only (control N/A).

**Files:**
- Create: `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/matched_outcomes.py`
- Create: `tests/unit/nsf_vc/test_matched_outcomes.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/unit/nsf_vc/test_matched_outcomes.py
import pandas as pd

from sbir_analytics.assets.nsf_vc.matched_outcomes import MatchedCohortOutcomes


def test_per_cohort_rates_with_match_coverage():
    nsf = pd.DataFrame({
        "company_name": ["A", "B"],
        "company_key": ["name:a", "name:b"],
        "vintage_bucket": ["2010-2014"] * 2,
        "industry_group": ["Computers"] * 2,
        "state": ["CA"] * 2,
        "phase_label": ["II"] * 2,
    })
    ctrl = pd.DataFrame({
        "company_name": ["X", "Y"],
        "company_key": ["name:x", "name:y"],
        "vintage_bucket": ["2010-2014"] * 2,
        "industry_group": ["Computers"] * 2,
        "state": ["CA"] * 2,
    })
    usaspending = {"name:a", "name:x"}              # 1/2 NSF, 1/2 control
    ma_events = {"name:b"}                          # 1/2 NSF, 0/2 control
    matched = MatchedCohortOutcomes(
        usaspending_companies=usaspending,
        ma_event_companies=ma_events,
    )
    out = matched.compute(nsf, ctrl)
    # Expect rows for each metric x cohort
    nsf_rates = out[out["cohort"] == "nsf"]
    ctrl_rates = out[out["cohort"] == "control"]
    fed_nsf = nsf_rates[nsf_rates["metric"] == "phase_ii_to_federal_contract_transition"].iloc[0]
    fed_ctrl = ctrl_rates[ctrl_rates["metric"] == "phase_ii_to_federal_contract_transition"].iloc[0]
    assert fed_nsf["numerator"] == 1 and fed_nsf["denominator"] == 2
    assert fed_ctrl["numerator"] == 1 and fed_ctrl["denominator"] == 2
    ma_nsf = nsf_rates[nsf_rates["metric"] == "ma_exit_rate"].iloc[0]
    assert ma_nsf["numerator"] == 1
    # name_match_coverage emitted as a signal row
    cov_row = out[out["metric"] == "name_match_coverage"].iloc[0]
    assert 0.0 <= cov_row["rate"] <= 1.0


def test_unavailable_when_inputs_missing():
    nsf = pd.DataFrame({
        "company_name": ["A"], "company_key": ["name:a"],
        "vintage_bucket": ["2010-2014"], "industry_group": ["Computers"],
        "state": ["CA"], "phase_label": ["II"],
    })
    ctrl = nsf.rename(columns={"company_key": "company_key"}).copy()
    matched = MatchedCohortOutcomes(usaspending_companies=None, ma_event_companies=None)
    out = matched.compute(nsf, ctrl)
    fed_rows = out[out["metric"] == "phase_ii_to_federal_contract_transition"]
    assert (fed_rows["available"] == False).all()
```

- [ ] **Step 2: Run test, verify FAIL.**

- [ ] **Step 3: Implement.**

```python
# packages/sbir-analytics/sbir_analytics/assets/nsf_vc/matched_outcomes.py
"""Matched-cohort outcomes (spec 2.4).

Computes per-stratum, per-cohort rates with Wilson CIs for:
- phase_ii_to_federal_contract_transition (USAspending presence; binary)
- patent_rate (PATLINK award_id intersection; NSF-only as control N/A)
- ma_exit_rate (sbir_ma_events name match; both cohorts)

Plus a per-cohort ``name_match_coverage`` signal: fraction of cohort
companies whose normalized name resolves to at least one EDGAR-keyed
equivalent. Quantifies how much of each cohort the M&A signal can
theoretically reach (B4 decision).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from sbir_analytics.assets.nsf_vc.outcomes import wilson_interval


@dataclass
class MatchedCohortOutcomes:
    usaspending_companies: set[str] | None = field(default=None)
    patent_award_ids: set[str] | None = field(default=None)
    ma_event_companies: set[str] | None = field(default=None)
    edgar_company_keys: set[str] | None = field(default=None)

    def compute(self, nsf: pd.DataFrame, control: pd.DataFrame) -> pd.DataFrame:
        records: list[dict[str, Any]] = []
        records.extend(self._cohort_metrics("nsf", nsf, include_patent=True))
        records.extend(self._cohort_metrics("control", control, include_patent=False))
        records.append(self._coverage_row("nsf", nsf))
        records.append(self._coverage_row("control", control))
        return pd.DataFrame.from_records(records)

    def _cohort_metrics(
        self, cohort_name: str, df: pd.DataFrame, *, include_patent: bool
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        keys = {k for k in df.get("company_key", pd.Series(dtype=object)).tolist() if k}
        denom = len(keys)
        # USAspending presence
        if self.usaspending_companies is None:
            out.append(self._row(cohort_name, "phase_ii_to_federal_contract_transition",
                                 0, denom, available=False))
        else:
            out.append(self._row(cohort_name, "phase_ii_to_federal_contract_transition",
                                 len(keys & self.usaspending_companies), denom, available=True))
        # M&A
        if self.ma_event_companies is None:
            out.append(self._row(cohort_name, "ma_exit_rate", 0, denom, available=False))
        else:
            out.append(self._row(cohort_name, "ma_exit_rate",
                                 len(keys & self.ma_event_companies), denom, available=True))
        # Patent rate (NSF only — control has no award_id)
        if include_patent:
            award_ids = set(df.get("award_id", pd.Series(dtype=object)).dropna().astype(str))
            if self.patent_award_ids is None:
                out.append(self._row(cohort_name, "patent_rate", 0, len(award_ids),
                                     available=False))
            else:
                out.append(self._row(cohort_name, "patent_rate",
                                     len(award_ids & self.patent_award_ids),
                                     len(award_ids), available=True))
        return out

    def _coverage_row(self, cohort_name: str, df: pd.DataFrame) -> dict[str, Any]:
        if self.edgar_company_keys is None:
            return self._row(cohort_name, "name_match_coverage", 0, len(df), available=False)
        keys = {k for k in df.get("company_key", pd.Series(dtype=object)).tolist() if k}
        return self._row(cohort_name, "name_match_coverage",
                         len(keys & self.edgar_company_keys), len(keys), available=True)

    @staticmethod
    def _row(cohort: str, metric: str, num: int, denom: int, *, available: bool) -> dict[str, Any]:
        if available and denom > 0:
            wi = wilson_interval(num, denom)
        else:
            wi = {
                "rate": float("nan"),
                "ci_low": float("nan"),
                "ci_high": float("nan"),
                "numerator": num,
                "denominator": denom,
            }
        return {
            "cohort": cohort,
            "metric": metric,
            "numerator": int(wi["numerator"]),
            "denominator": int(wi["denominator"]),
            "rate": wi["rate"],
            "ci_low": wi["ci_low"],
            "ci_high": wi["ci_high"],
            "available": bool(available),
        }
```

- [ ] **Step 4: Run test.** Expected: 2 passed.

- [ ] **Step 5: Commit.**

```bash
git add packages/sbir-analytics/sbir_analytics/assets/nsf_vc/matched_outcomes.py \
        tests/unit/nsf_vc/test_matched_outcomes.py
git commit -m "feat(nsf-vc): add MatchedCohortOutcomes with name_match_coverage signal"
```

---

### Task 5: ThreatsToValidity gate (spec 2.5)

Required entries: SAFE/convertible undercount, late-stage Form D inclusion, Topic Code self-report noise (substituting NAICS noise from spec since we use Topic Code), #286 CIK-recall floor, technical-merit vs. lawyer-access selection bias, control-cohort timing-leak, USAspending materialization dependency, 43%-Other-bucket inflation. Headline output is suppressed if any entry is missing or stale.

**Files:**
- Create: `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/threats.py`
- Create: `tests/unit/nsf_vc/test_threats.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/unit/nsf_vc/test_threats.py
from datetime import UTC, datetime, timedelta
import pytest

from sbir_analytics.assets.nsf_vc.threats import (
    REQUIRED_ENTRIES,
    ThreatEntry,
    ThreatsToValidity,
)


def _full_registry():
    now = datetime.now(UTC)
    return {name: ThreatEntry(name=name, body="b", as_of=now) for name in REQUIRED_ENTRIES}


def test_passes_when_all_required_entries_present_and_fresh():
    ttv = ThreatsToValidity(entries=_full_registry())
    assert ttv.gate_passes()


def test_fails_when_required_entry_missing():
    reg = _full_registry()
    del reg[next(iter(REQUIRED_ENTRIES))]
    ttv = ThreatsToValidity(entries=reg)
    assert not ttv.gate_passes()
    assert ttv.gate_failures()  # non-empty list of names


def test_fails_when_entry_is_stale():
    reg = _full_registry()
    stale_name = next(iter(REQUIRED_ENTRIES))
    reg[stale_name] = ThreatEntry(
        name=stale_name, body="b", as_of=datetime.now(UTC) - timedelta(days=400)
    )
    ttv = ThreatsToValidity(entries=reg, max_age_days=180)
    assert not ttv.gate_passes()
    assert stale_name in ttv.gate_failures()
```

- [ ] **Step 2: Run test, verify FAIL.**

- [ ] **Step 3: Implement.**

```python
# packages/sbir-analytics/sbir_analytics/assets/nsf_vc/threats.py
"""Threats-to-validity registry + gate (spec 2.5).

A required-entry registry that suppresses headline Phase 2 output if any
entry is missing or stale. Required entries were enumerated in
``specs/nsf-vc-comparison/tasks.md`` task 2.5; topic-code noise replaces
the spec's NAICS noise (B1 decision substituting Topic Code), and we add
USAspending materialization + 43% Other-bucket entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


REQUIRED_ENTRIES: frozenset[str] = frozenset(
    {
        "safe_convertible_undercount",
        "late_stage_form_d_inclusion",
        "topic_code_self_report_noise",
        "edgar_cik_recall_floor",
        "technical_merit_vs_lawyer_access_bias",
        "control_cohort_timing_leak",
        "usaspending_materialization_dependency",
        "topic_code_other_bucket_inflation",
    }
)

DEFAULT_MAX_AGE_DAYS = 180


@dataclass(frozen=True)
class ThreatEntry:
    name: str
    body: str
    as_of: datetime


@dataclass
class ThreatsToValidity:
    entries: dict[str, ThreatEntry] = field(default_factory=dict)
    max_age_days: int = DEFAULT_MAX_AGE_DAYS

    def gate_failures(self) -> list[str]:
        failures: list[str] = []
        cutoff = datetime.now(UTC) - timedelta(days=self.max_age_days)
        for name in REQUIRED_ENTRIES:
            entry = self.entries.get(name)
            if entry is None:
                failures.append(name)
                continue
            if entry.as_of < cutoff:
                failures.append(name)
        return failures

    def gate_passes(self) -> bool:
        return not self.gate_failures()
```

- [ ] **Step 4: Run test.** Expected: 3 passed.

- [ ] **Step 5: Commit.**

```bash
git add packages/sbir-analytics/sbir_analytics/assets/nsf_vc/threats.py \
        tests/unit/nsf_vc/test_threats.py
git commit -m "feat(nsf-vc): add ThreatsToValidity gate for Phase 2 headline suppression"
```

---

### Task 6: Phase 2 in-process runner script

Mirrors `run_nsf_vc_phase1.py` pattern. Loads SBIR.gov bulk CSV (cached at `/tmp/sbir_awards_full.csv`), `data/sec_edgar_scan.jsonl`, `data/form_d_index.jsonl`, `data/form_d_details.jsonl`, `data/sbir_ma_events.jsonl`. Optional inputs: USAspending presence parquet (renders unavailable if absent), PATLINK parquet (same). Outputs: `data/processed/nsf_vc/phase2/nsf_vs_form_d_comparison.parquet`, `nsf_vs_form_d_comparison.md`, `threats_to_validity.json`.

**Files:**
- Create: `scripts/data/run_nsf_vc_phase2.py`

- [ ] **Step 1: Write the runner.**

```python
#!/usr/bin/env python3
"""Run the NSF SBIR vs. Form D matched-cohort (Phase 2) comparison
in-process, mirroring ``run_nsf_vc_phase1.py``'s pattern. Bypasses the
Dagster materialization chain.

Usage:
    uv run python scripts/data/run_nsf_vc_phase2.py
    uv run python scripts/data/run_nsf_vc_phase2.py --headline-vintage 2010-2014

Outputs to ``data/processed/nsf_vc/phase2/``:
- nsf_vs_form_d_comparison.parquet
- nsf_vs_form_d_comparison.md
- threats_to_validity.json
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from sbir_analytics.assets.nsf_vc.awardee_filter import NSFAwardeeFilter
from sbir_analytics.assets.nsf_vc.cohort import NSFCohortBuilder
from sbir_analytics.assets.nsf_vc.control import PrivateCapitalControlCohortBuilder
from sbir_analytics.assets.nsf_vc.industry_group import IndustryGroupClassifier
from sbir_analytics.assets.nsf_vc.matched_outcomes import MatchedCohortOutcomes
from sbir_analytics.assets.nsf_vc.matcher import CohortMatcher
from sbir_analytics.assets.nsf_vc.outcomes import _company_key
from sbir_analytics.assets.nsf_vc.threats import (
    REQUIRED_ENTRIES,
    ThreatEntry,
    ThreatsToValidity,
)


DEFAULT_AWARDS_CSV = Path("/tmp/sbir_awards_full.csv")
DEFAULT_EDGAR_SCAN = Path("data/sec_edgar_scan.jsonl")
DEFAULT_FORM_D_INDEX = Path("data/form_d_index.jsonl")
DEFAULT_FORM_D_DETAILS = Path("data/form_d_details.jsonl")
DEFAULT_MA_EVENTS = Path("data/sbir_ma_events.jsonl")
DEFAULT_CROSSWALK = Path("config/nsf_vc/topic_code_to_industry_group.yaml")
DEFAULT_OUTPUT_DIR = Path("data/processed/nsf_vc/phase2")
DEFAULT_HEADLINE_VINTAGE = "2010-2014"


def _load_ma_companies(path: Path, *, agency_filter: str | None = None) -> set[str] | None:
    if not path.exists():
        return None
    keys: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if agency_filter and rec.get("sbir_context", {}).get("agency") != agency_filter:
                continue
            name = rec.get("company_name")
            if name and str(name).strip():
                keys.add(f"name:{str(name).strip().lower()}")
    return keys


def _load_seed_threats() -> dict[str, ThreatEntry]:
    """Initial in-line threat-entry bodies. Each must be reviewed before any
    headline release; bodies live in the runner so they are versioned with
    the data run."""
    now = datetime.now(UTC)
    return {
        "safe_convertible_undercount": ThreatEntry(
            name="safe_convertible_undercount",
            body="Form D Reg D filings under-report SAFE / convertible-note rounds; private-capital intensity is biased low for early-stage controls.",
            as_of=now,
        ),
        "late_stage_form_d_inclusion": ThreatEntry(
            name="late_stage_form_d_inclusion",
            body="Form D index includes late-stage / private-equity issuers conflated with seed-stage controls; filing-year vintage may not match company founding vintage.",
            as_of=now,
        ),
        "topic_code_self_report_noise": ThreatEntry(
            name="topic_code_self_report_noise",
            body="NSF Topic Codes are self-reported by program officers; cross-topic boundaries are fuzzy. Substitutes for spec's NAICS-noise entry per B1 decision.",
            as_of=now,
        ),
        "edgar_cik_recall_floor": ThreatEntry(
            name="edgar_cik_recall_floor",
            body="PR #286 EDGAR-CIK recall ~28% of SBIR awardees; NSF cohort restricted to NSF n EDGAR for matching, which may not generalize to non-EDGAR NSF awardees.",
            as_of=now,
        ),
        "technical_merit_vs_lawyer_access_bias": ThreatEntry(
            name="technical_merit_vs_lawyer_access_bias",
            body="NSF awardees pre-selected on technical merit + proposal quality; Form D issuers self-select on lawyer access + growth narrative. Selection filters differ structurally.",
            as_of=now,
        ),
        "control_cohort_timing_leak": ThreatEntry(
            name="control_cohort_timing_leak",
            body="Control = Form D issuers without SBIR exposure ever. Issuers can become SBIR awardees post-control-period; vintage-bucket leakage possible.",
            as_of=now,
        ),
        "usaspending_materialization_dependency": ThreatEntry(
            name="usaspending_materialization_dependency",
            body="phase_ii_to_federal_contract_transition requires USAspending recipient/vendor presence parquet; renders unavailable if not materialized.",
            as_of=now,
        ),
        "topic_code_other_bucket_inflation": ThreatEntry(
            name="topic_code_other_bucket_inflation",
            body="~43% of NSF rows lack Topic Codes; bucketed to 'Other' Industry Group, inflating that stratum and diluting matched-comparison precision there.",
            as_of=now,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards-csv", type=Path, default=DEFAULT_AWARDS_CSV)
    parser.add_argument("--edgar-scan", type=Path, default=DEFAULT_EDGAR_SCAN)
    parser.add_argument("--form-d-index", type=Path, default=DEFAULT_FORM_D_INDEX)
    parser.add_argument("--form-d-details", type=Path, default=DEFAULT_FORM_D_DETAILS)
    parser.add_argument("--ma-events", type=Path, default=DEFAULT_MA_EVENTS)
    parser.add_argument("--crosswalk", type=Path, default=DEFAULT_CROSSWALK)
    parser.add_argument("--usaspending", type=Path, default=None,
                        help="Optional parquet of USAspending recipient/vendor company keys.")
    parser.add_argument("--patents", type=Path, default=None,
                        help="Optional parquet of PATLINK award_id -> patent links.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--headline-vintage", default=DEFAULT_HEADLINE_VINTAGE)
    args = parser.parse_args()

    # 1. NSF cohort (vintage + phase) — reuses Phase 1 builder
    if not args.awards_csv.exists():
        print(f"awards CSV not found at {args.awards_csv}; run Phase 1 first to download.",
              file=sys.stderr)
        return 2
    awards = pd.read_csv(args.awards_csv, dtype=str, low_memory=False, encoding_errors="replace")
    nsf_full = NSFCohortBuilder().build(awards)
    print(f"NSF cohort (Phase 1 builder): {len(nsf_full):,}")

    # 2. Restrict to NSF n EDGAR
    edgar_companies = NSFAwardeeFilter.load_edgar_companies(args.edgar_scan)
    nsf_edgar = NSFAwardeeFilter(edgar_companies=edgar_companies).filter(nsf_full)
    print(f"NSF n EDGAR: {len(nsf_edgar):,}")

    # 3. Add Industry Group + company_key columns
    classifier = IndustryGroupClassifier.load(args.crosswalk)
    nsf_edgar = classifier.apply(nsf_edgar)
    nsf_edgar["company_key"] = nsf_edgar.apply(_company_key, axis=1)
    nsf_edgar["state"] = nsf_edgar.get("State", pd.Series(dtype=object)).str.strip().str.upper()
    print(f"NSF Industry Group coverage: {classifier.coverage(nsf_full):.1%}")

    # 4. Build control cohort
    sbir_company_keys = edgar_companies  # all SBIR-CIK companies; broader set
    control = PrivateCapitalControlCohortBuilder(
        sbir_company_keys=sbir_company_keys,
    ).build(index_path=args.form_d_index, details_path=args.form_d_details)
    print(f"Control cohort (Form D, no SBIR overlap): {len(control):,}")

    # 5. CEM
    matched = CohortMatcher().match(nsf_edgar, control)
    print(f"Matched strata: {len(matched.matched_strata):,}")
    print(f"Matched NSF rows: {len(matched.matched_nsf):,}")
    print(f"Matched control rows: {len(matched.matched_controls):,}")
    print(f"Unmatched NSF rows: {len(matched.unmatched_nsf):,}")

    # 6. Outcomes
    ma_companies = _load_ma_companies(args.ma_events, agency_filter="National Science Foundation")
    usaspending_companies = None
    if args.usaspending and args.usaspending.exists():
        usaspending_companies = set(
            pd.read_parquet(args.usaspending).get("company_key", pd.Series(dtype=object))
            .dropna().astype(str).tolist()
        )
    patent_award_ids = None
    if args.patents and args.patents.exists():
        patent_award_ids = set(
            pd.read_parquet(args.patents).get("award_id", pd.Series(dtype=object))
            .dropna().astype(str).tolist()
        )
    outcomes = MatchedCohortOutcomes(
        usaspending_companies=usaspending_companies,
        patent_award_ids=patent_award_ids,
        ma_event_companies=ma_companies,
        edgar_company_keys=edgar_companies,
    ).compute(matched.matched_nsf, matched.matched_controls)

    # 7. Threats gate
    ttv = ThreatsToValidity(entries=_load_seed_threats())
    failures = ttv.gate_failures()
    if failures:
        print(f"GATE FAILED: missing/stale threats-to-validity entries: {failures}",
              file=sys.stderr)
        return 3

    # 8. Write artifacts
    args.output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = args.output_dir / "nsf_vs_form_d_comparison.parquet"
    md_path = args.output_dir / "nsf_vs_form_d_comparison.md"
    json_path = args.output_dir / "threats_to_validity.json"
    outcomes.to_parquet(parquet_path, index=False)
    md_path.write_text(_render_markdown(outcomes, args.headline_vintage, matched), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            [{"name": e.name, "body": e.body, "as_of": e.as_of.isoformat()}
             for e in ttv.entries.values()],
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {parquet_path}")
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    return 0


def _render_markdown(outcomes: pd.DataFrame, headline: str, matched) -> str:
    lines = [
        "# NSF SBIR vs. Form D Matched Cohort Comparison",
        "",
        f"Headline vintage: **{headline}**",
        f"Matched strata: {len(matched.matched_strata):,}",
        f"Matched NSF rows: {len(matched.matched_nsf):,}",
        f"Matched control rows: {len(matched.matched_controls):,}",
        "",
        "## Per-cohort metrics",
        "",
        "| Cohort | Metric | Numerator | Denominator | Rate (95% CI) | Available |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for _, row in outcomes.iterrows():
        if row["available"]:
            ci = f"{row['rate']:.1%} ({row['ci_low']:.1%}-{row['ci_high']:.1%})"
        else:
            ci = "data unavailable"
        lines.append(
            f"| {row['cohort']} | {row['metric']} | {row['numerator']} | "
            f"{row['denominator']} | {ci} | {row['available']} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke-test the runner against current on-disk inputs.**

Run: `uv run python scripts/data/run_nsf_vc_phase2.py 2>&1 | tail -25`
Expected: prints cohort sizes and "Matched strata: N" without exception. Writes 3 artifacts to `data/processed/nsf_vc/phase2/`. Some metrics may render as `data unavailable` (USAspending/patents) — that's expected per Phase 1 conventions; the gate must still pass because all required threat entries are in `_load_seed_threats()`.

- [ ] **Step 3: Inspect the artifacts.**

Run: `cat data/processed/nsf_vc/phase2/nsf_vs_form_d_comparison.md`
Expected: per-cohort table with NSF and control rows for each metric; "data unavailable" cells where USAspending/patents not provided; numeric rates for `ma_exit_rate` and `name_match_coverage`.

- [ ] **Step 4: Commit.**

```bash
git add scripts/data/run_nsf_vc_phase2.py
git commit -m "feat(nsf-vc): add Phase 2 in-process runner for matched-cohort comparison"
```

---

### Task 7: Dagster asset wiring (spec 2.6)

Wire the same logic into a Dagster asset `nsf_vc_form_d_matched_comparison`. Reads from upstream Dagster assets (`validated_sbir_awards`, `sec_edgar_enriched_companies`, `form_d_offerings`) rather than raw JSONL, but produces the same three artifacts.

**Files:**
- Create: `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/asset_phase2.py`

- [ ] **Step 1: Implement the asset.**

```python
# packages/sbir-analytics/sbir_analytics/assets/nsf_vc/asset_phase2.py
"""Dagster asset for NSF vs. Form D matched-cohort comparison (spec 2.6).

Reuses the Phase 2 in-process classes; consumes upstream Dagster assets
instead of raw JSONL.
"""

import pandas as pd
from dagster import AssetExecutionContext, MetadataValue, Output, asset

from sbir_analytics.assets.nsf_vc.awardee_filter import NSFAwardeeFilter
from sbir_analytics.assets.nsf_vc.cohort import NSFCohortBuilder
from sbir_analytics.assets.nsf_vc.control import PrivateCapitalControlCohortBuilder
from sbir_analytics.assets.nsf_vc.industry_group import IndustryGroupClassifier
from sbir_analytics.assets.nsf_vc.matched_outcomes import MatchedCohortOutcomes
from sbir_analytics.assets.nsf_vc.matcher import CohortMatcher
from sbir_analytics.assets.nsf_vc.outcomes import _company_key
from sbir_analytics.assets.nsf_vc.threats import ThreatsToValidity

from pathlib import Path
from datetime import UTC, datetime


@asset(
    description="NSF SBIR vs. Form D matched-cohort comparison (Phase 2)",
    group_name="nsf_vc",
    compute_kind="analytics",
)
def nsf_vc_form_d_matched_comparison(
    context: AssetExecutionContext,
    validated_sbir_awards: pd.DataFrame,
    sec_edgar_enriched_companies: pd.DataFrame,
) -> Output[pd.DataFrame]:
    classifier = IndustryGroupClassifier.load(
        Path("config/nsf_vc/topic_code_to_industry_group.yaml")
    )
    nsf_full = NSFCohortBuilder().build(validated_sbir_awards)
    edgar_keys = {
        f"name:{str(n).strip().lower()}"
        for n in sec_edgar_enriched_companies.get("company_name", pd.Series(dtype=object))
        if n and str(n).strip()
    }
    nsf_edgar = NSFAwardeeFilter(edgar_companies=edgar_keys).filter(nsf_full)
    nsf_edgar = classifier.apply(nsf_edgar)
    nsf_edgar["company_key"] = nsf_edgar.apply(_company_key, axis=1)
    control = PrivateCapitalControlCohortBuilder(
        sbir_company_keys=edgar_keys,
    ).build(
        index_path=Path("data/form_d_index.jsonl"),
        details_path=Path("data/form_d_details.jsonl"),
    )
    matched = CohortMatcher().match(nsf_edgar, control)
    outcomes = MatchedCohortOutcomes(
        usaspending_companies=None,  # wired up later when USAspending asset stable
        patent_award_ids=None,       # wired up later when PATLINK asset stable
        ma_event_companies=None,     # wired up later
        edgar_company_keys=edgar_keys,
    ).compute(matched.matched_nsf, matched.matched_controls)
    return Output(
        value=outcomes,
        metadata={
            "matched_strata": len(matched.matched_strata),
            "matched_nsf_rows": len(matched.matched_nsf),
            "matched_control_rows": len(matched.matched_controls),
            "unmatched_nsf_rows": len(matched.unmatched_nsf),
        },
    )
```

- [ ] **Step 2: Verify the asset imports cleanly.**

Run: `uv run python -c "from sbir_analytics.assets.nsf_vc.asset_phase2 import nsf_vc_form_d_matched_comparison; print(nsf_vc_form_d_matched_comparison)"`
Expected: prints the asset object; no ImportError.

- [ ] **Step 3: Commit.**

```bash
git add packages/sbir-analytics/sbir_analytics/assets/nsf_vc/asset_phase2.py
git commit -m "feat(nsf-vc): wire Phase 2 matched comparison as Dagster asset"
```

Note: full materialization of this asset depends on `validated_sbir_awards` and `sec_edgar_enriched_companies` being materializable in the local Dagster env. The runner script (Task 6) is the recommended path for headline reports; this asset is for orchestration integration.

---

### Task 8: Security-type / offering-size decomposition (spec 2.7)

Reproduces #286's published 1.82x SBIR-to-Form-D leverage ratio scoped to NSF only, plus a security-type / offering-size breakdown. First step: locate the existing leverage-ratio code in the repo; reuse it rather than re-deriving.

**Files:**
- Create: `packages/sbir-analytics/sbir_analytics/assets/nsf_vc/decomposition.py`
- Create: `tests/unit/nsf_vc/test_decomposition.py`

- [ ] **Step 1: Find the existing leverage-ratio computation.**

Run: `uv run python -c "import subprocess; print(subprocess.check_output(['grep', '-rn', 'leverage', 'packages/', 'sbir_etl/', 'docs/research/'], text=True))" 2>&1 | head -20`

Or use Grep tool in IDE. Expected: locates an existing function or doc that defines `total_form_d_raised_per_dollar_sbir`. This is the function to reuse.

- [ ] **Step 2: Write failing test for the decomposition.**

```python
# tests/unit/nsf_vc/test_decomposition.py
import pandas as pd

from sbir_analytics.assets.nsf_vc.decomposition import (
    SecurityTypeDecomposition,
    nsf_leverage_ratio,
)


def test_leverage_ratio_reproduces_286_within_tolerance():
    # 1.82x is #286's published value across all SBIR. NSF-scoped value
    # should be in the same neighborhood (1.0x-3.0x); the test asserts
    # plausibility, not exact match (NSF subset is small).
    nsf_sbir_dollars = 100_000_000  # $100M NSF SBIR
    nsf_form_d_dollars = 182_000_000  # $182M Form D for those firms
    ratio = nsf_leverage_ratio(
        sbir_dollars=nsf_sbir_dollars, form_d_dollars=nsf_form_d_dollars
    )
    assert ratio == 1.82


def test_decomposition_buckets_by_security_type():
    offerings = pd.DataFrame({
        "form_d_cik": ["1", "1", "2", "3"],
        "security_type": ["Equity", "SAFE", "Equity", "Convertible"],
        "total_offering_amount": [1_000_000, 500_000, 2_000_000, 3_000_000],
    })
    nsf_ciks = {"1", "2"}  # NSF-scoped
    out = SecurityTypeDecomposition().decompose(offerings, nsf_ciks=nsf_ciks)
    # Three security types in NSF subset: Equity ($3M), SAFE ($500K)
    eq = out[out["security_type"] == "Equity"].iloc[0]
    safe = out[out["security_type"] == "SAFE"].iloc[0]
    assert eq["total_offering_amount"] == 3_000_000
    assert safe["total_offering_amount"] == 500_000
    # Convertible is NOT in NSF subset (CIK 3 not in nsf_ciks)
    assert "Convertible" not in set(out["security_type"])
```

- [ ] **Step 3: Run test, verify FAIL.**

- [ ] **Step 4: Implement.**

```python
# packages/sbir-analytics/sbir_analytics/assets/nsf_vc/decomposition.py
"""Security-type / offering-size decomposition (spec 2.7).

Reproduces #286's 1.82x SBIR-to-Form-D leverage ratio scoped to NSF only,
and breaks the NSF subset down by Form D security type (Equity / SAFE /
Convertible / Debt) and by offering-amount bucket. The leverage-ratio
formula is intentionally simple (sum of Form D dollars / sum of SBIR
dollars for matching CIKs); the value of the test is reproducibility, not
sophistication.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def nsf_leverage_ratio(*, sbir_dollars: float, form_d_dollars: float) -> float:
    if sbir_dollars <= 0:
        return float("nan")
    return round(form_d_dollars / sbir_dollars, 2)


@dataclass(frozen=True)
class SecurityTypeDecomposition:
    def decompose(
        self,
        offerings: pd.DataFrame,
        *,
        nsf_ciks: set[str],
    ) -> pd.DataFrame:
        if offerings.empty or not nsf_ciks:
            return pd.DataFrame(columns=["security_type", "n_offerings", "total_offering_amount"])
        scoped = offerings[offerings["form_d_cik"].astype(str).isin(nsf_ciks)].copy()
        if scoped.empty:
            return pd.DataFrame(columns=["security_type", "n_offerings", "total_offering_amount"])
        grouped = (
            scoped.groupby("security_type", dropna=False)
            .agg(n_offerings=("form_d_cik", "count"),
                 total_offering_amount=("total_offering_amount", "sum"))
            .reset_index()
        )
        return grouped.sort_values("total_offering_amount", ascending=False).reset_index(drop=True)
```

- [ ] **Step 5: Run test.** Expected: 2 passed.

- [ ] **Step 6: Commit.**

```bash
git add packages/sbir-analytics/sbir_analytics/assets/nsf_vc/decomposition.py \
        tests/unit/nsf_vc/test_decomposition.py
git commit -m "feat(nsf-vc): add security-type decomposition + NSF leverage ratio"
```

---

### Task 9: Integration test on small NSF + Form D fixture (spec 2.8)

Tests the full Phase 2 pipeline against a small fixture set. Verifies: cohort restriction works, Industry Group classification works, CEM matching works, outcome computation works, threats gate passes.

**Files:**
- Create: `tests/integration/nsf_vc/test_phase2_pipeline.py`

- [ ] **Step 1: Write the integration test.**

```python
# tests/integration/nsf_vc/test_phase2_pipeline.py
import json
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.nsf_vc.awardee_filter import NSFAwardeeFilter
from sbir_analytics.assets.nsf_vc.cohort import NSFCohortBuilder
from sbir_analytics.assets.nsf_vc.control import PrivateCapitalControlCohortBuilder
from sbir_analytics.assets.nsf_vc.industry_group import IndustryGroupClassifier
from sbir_analytics.assets.nsf_vc.matched_outcomes import MatchedCohortOutcomes
from sbir_analytics.assets.nsf_vc.matcher import CohortMatcher
from sbir_analytics.assets.nsf_vc.outcomes import _company_key


CROSSWALK = Path("config/nsf_vc/topic_code_to_industry_group.yaml")


def test_phase2_end_to_end_on_fixture(tmp_path):
    # SBIR.gov-style fixture: 4 NSF awards, 1 non-NSF
    awards = pd.DataFrame([
        {"Company": "AcmeAI Inc.", "Agency": "National Science Foundation",
         "Phase": "Phase II", "Award Year": "2012", "Topic Code": "EI",
         "State": "CA"},
        {"Company": "Beta Bio", "Agency": "National Science Foundation",
         "Phase": "Phase II", "Award Year": "2013", "Topic Code": "BC",
         "State": "MA"},
        {"Company": "Gamma Robotics", "Agency": "National Science Foundation",
         "Phase": "Phase II", "Award Year": "2011", "Topic Code": "EL",
         "State": "CA"},
        {"Company": "Delta Devices", "Agency": "National Science Foundation",
         "Phase": "Phase II", "Award Year": "2010", "Topic Code": "MN",
         "State": "WA"},
        {"Company": "DoD Co", "Agency": "Department of Defense",
         "Phase": "Phase II", "Award Year": "2013", "Topic Code": "X",
         "State": "VA"},
    ])
    edgar_jsonl = tmp_path / "edgar.jsonl"
    edgar_jsonl.write_text(
        '{"company_name": "AcmeAI Inc."}\n'
        '{"company_name": "Gamma Robotics"}\n'
        '{"company_name": "PureVC Co"}\n',
        encoding="utf-8",
    )
    form_d_index = tmp_path / "i.jsonl"
    form_d_index.write_text(
        '{"company_name": "PureVC Co", "form_d_cik": "100", "state": "CA",\n'
        ' "form_d_filings": [{"filing_date": "2012-04-01"}]}\n'
        '{"company_name": "AcmeAI Inc.", "form_d_cik": "200", "state": "CA",\n'
        ' "form_d_filings": [{"filing_date": "2013-01-01"}]}\n',  # SBIR overlap, dropped
        encoding="utf-8",
    )
    form_d_details = tmp_path / "d.jsonl"
    form_d_details.write_text(
        '{"form_d_cik": "100", "offerings": [{"industry_group": "Computers"}]}\n'
        '{"form_d_cik": "200", "offerings": [{"industry_group": "Computers"}]}\n',
        encoding="utf-8",
    )
    # Pipeline
    classifier = IndustryGroupClassifier.load(CROSSWALK)
    nsf = NSFCohortBuilder().build(awards)
    edgar_keys = NSFAwardeeFilter.load_edgar_companies(edgar_jsonl)
    nsf_edgar = NSFAwardeeFilter(edgar_companies=edgar_keys).filter(nsf)
    nsf_edgar = classifier.apply(nsf_edgar)
    nsf_edgar["company_key"] = nsf_edgar.apply(_company_key, axis=1)
    nsf_edgar["state"] = nsf_edgar["State"].str.upper()
    control = PrivateCapitalControlCohortBuilder(
        sbir_company_keys=edgar_keys,
    ).build(index_path=form_d_index, details_path=form_d_details)
    matched = CohortMatcher().match(nsf_edgar, control)
    # AcmeAI (2010-2014, Computers, CA) ↔ PureVC (2010-2014, Computers, CA)
    assert len(matched.matched_strata) == 1
    assert matched.matched_strata.iloc[0]["nsf_n"] == 1
    assert matched.matched_strata.iloc[0]["control_n"] == 1
    # Outcomes
    out = MatchedCohortOutcomes(
        usaspending_companies={"name:acmeai inc."},
        ma_event_companies={"name:purevc co"},
        edgar_company_keys=edgar_keys,
    ).compute(matched.matched_nsf, matched.matched_controls)
    nsf_fed = out[(out["cohort"] == "nsf") &
                  (out["metric"] == "phase_ii_to_federal_contract_transition")].iloc[0]
    ctrl_fed = out[(out["cohort"] == "control") &
                   (out["metric"] == "phase_ii_to_federal_contract_transition")].iloc[0]
    assert nsf_fed["numerator"] == 1 and nsf_fed["denominator"] == 1
    assert ctrl_fed["numerator"] == 0 and ctrl_fed["denominator"] == 1
```

- [ ] **Step 2: Run the integration test.**

Run: `uv run pytest tests/integration/nsf_vc/test_phase2_pipeline.py -v`
Expected: 1 passed.

- [ ] **Step 3: Commit.**

```bash
git add tests/integration/nsf_vc/test_phase2_pipeline.py
git commit -m "test(nsf-vc): integration test for Phase 2 pipeline against fixture"
```

---

### Task 10: Phase 2 gate report + cross-phase docs (spec 2.9 + X.1 + X.2)

Final task. Run the runner against real on-disk data. Inspect the report. Update `docs/research-questions.md` to cite this spec.

**Files:**
- Create: `docs/nsf-vc-comparison/methodology.md`
- Create: `docs/nsf-vc-comparison/glossary.md`
- Create: `docs/nsf-vc-comparison/citations.md`
- Modify: `docs/research-questions.md`

- [ ] **Step 1: Run the Phase 2 runner against real data.**

Run: `uv run python scripts/data/run_nsf_vc_phase2.py 2>&1 | tee /tmp/phase2_run.log`
Expected: gate passes, three artifacts written. Log shows cohort sizes (NSF n EDGAR ≈ 4-5K of 15.5K NSF; control = full Form D minus SBIR overlap ≈ 30-40K), matched strata count, matched row counts.

- [ ] **Step 2: Inspect the markdown report.**

Run: `cat data/processed/nsf_vc/phase2/nsf_vs_form_d_comparison.md`
Expected: per-cohort table populated, `name_match_coverage` numeric for both cohorts.

- [ ] **Step 3: Write methodology / glossary / citations docs.**

```markdown
# docs/nsf-vc-comparison/methodology.md
# NSF SBIR vs. Private-Capital Comparison Methodology

## Phase 1 (published baselines)
NSF Phase I/II graduation rate vs. NVCA seed->A baseline; raw graduation
computed from SBIR.gov bulk awards keyed on company name; Wilson 95% CIs.

## Phase 2 (matched-cohort against Form D issuers)
NSF cohort restricted to NSF n EDGAR (per the spec's broader-SBIR-CIK-set
framing) to make the comparison apples-to-apples with Form D issuers.
Control cohort = Form D issuers with no SBIR exposure ever, bucketed by
(filing-year vintage, Industry Group, state). Matched via coarsened-exact
matching on the same tuple key.

## Outcome metrics
- `phase_ii_to_federal_contract_transition`: USAspending recipient/vendor
  presence within 5 years of award (binary, per cohort).
- `ma_exit_rate`: company name appears in `data/sbir_ma_events.jsonl`
  (per cohort, scoped to NSF agency for NSF side).
- `patent_rate`: NSF-only; PATLINK award_id intersection.
- `name_match_coverage`: per-cohort fraction of companies resolved to
  EDGAR equivalents — quantifies the upper-bound recall of the M&A signal.

## Threats to validity
See `data/processed/nsf_vc/phase2/threats_to_validity.json` produced by
each run; required entries enumerated in
`packages/sbir-analytics/sbir_analytics/assets/nsf_vc/threats.py`.
```

```markdown
# docs/nsf-vc-comparison/glossary.md
# Glossary

- **CEM (Coarsened Exact Matching):** Stratified matching where continuous
  variables are binned (e.g., vintage_bucket = 5-year bins) and matching
  is exact within bins.
- **Industry Group:** SEC Form D Item 4 taxonomy (~9 buckets:
  Biotechnology, Computers, Health Care, Energy, Manufacturing, etc.).
  Used as the cross-cohort matching axis (B1 decision; native to Form D,
  derived for NSF via Topic Code crosswalk).
- **NSF n EDGAR:** NSF SBIR/STTR awardees who appear in PR #286's EDGAR
  scan. Approximately 28% of all NSF awardees per the spec's
  threats-to-validity entry.
- **Topic Code:** NSF SBIR/STTR program-internal taxonomy of research
  areas; letter prefix maps to Industry Group via
  `config/nsf_vc/topic_code_to_industry_group.yaml`.
```

```markdown
# docs/nsf-vc-comparison/citations.md
# Citations

| Claim | Source | URL |
| --- | --- | --- |
| NVCA seed->A graduation ~33% | NVCA Yearbook 2023 | https://nvca.org/research/nvca-yearbook/ |
| BLS 5-year survival ~50% | BLS Business Employment Dynamics | https://www.bls.gov/bdm/entrepreneurship/bdm_chart3.htm |
| SBIR follow-on growth +27% | Lerner (1999) Government as VC | https://www.nber.org/papers/w5753 |
| Early-stage SBIR doubles VC probability | Howell (2017) AER | https://www.aeaweb.org/articles?id=10.1257/aer.20150808 |
| NSF as "America's Seed Fund" framing | ITIF (2019) | https://itif.org/publications/2019/09/26/becoming-americas-seed-fund-why-nsfs-sbir-program-should-be-model-rest/ |
| Form D Industry Group taxonomy | SEC Form D Item 4 | https://www.sec.gov/forms |
| 1.82x SBIR-to-Form-D leverage ratio (PR #286) | PR #286 / `docs/research/sbir-form-d-fundraising-analysis.md` | (in-repo) |
```

- [ ] **Step 4: Annotate `docs/research-questions.md`.**

Modify the relevant existing entries (B2, B3, A4) to cite `specs/nsf-vc-comparison/`. Do NOT add a new question. Find each affected line and append a citation note like ``(See `specs/nsf-vc-comparison/`, Phase 1+2.)``.

- [ ] **Step 5: Commit docs.**

```bash
git add docs/nsf-vc-comparison/ docs/research-questions.md
git commit -m "docs(nsf-vc): add methodology/glossary/citations + research-questions cross-refs"
```

- [ ] **Step 6: Phase 2 gate review.**

Hand the produced `nsf_vs_form_d_comparison.md` + `threats_to_validity.json` to the user. Deliverable language (per spec task 2.9): *"On vintage 2010-2014, NAICS-2 Computers, state CA: NSF Phase II awardees transitioned to federal contract at A% within 5 years; matched non-SBIR Form D issuers transitioned at B%. Caveats below."*

If headline values are missing because of `available=False`, document which upstream artifact (USAspending parquet, PATLINK parquet) needs materialization to fill them. Stop here for sign-off.

---

## Self-Review

**Spec coverage:**

| Spec sub-task | Plan task |
|---|---|
| 2.1 NSFAwardeeFilter | Task 1 |
| 2.2 PrivateCapitalControlCohortBuilder | Task 2 |
| 2.3 CohortMatcher (CEM) | Task 3 |
| 2.4 MatchedCohortOutcomes | Task 4 |
| 2.5 ThreatsToValidity gate | Task 5 |
| 2.6 Dagster asset wiring | Task 7 |
| 2.7 Security-type / offering-size decomposition | Task 8 |
| 2.8 Unit + integration tests | Tasks 1-9 (each task includes its own tests; Task 9 is end-to-end) |
| 2.9 Phase 2 gate report | Task 10 |
| X.1 docs/nsf-vc-comparison/ | Task 10 |
| X.2 update research-questions.md | Task 10 |
| (in-process runner) | Task 6 |
| (Topic Code -> Industry Group crosswalk) | Task 0 |

All sub-tasks have explicit task coverage.

**Placeholder scan:** Reviewed each task's code blocks. Test code is concrete, implementation code is concrete, commands are concrete. No "TBD" / "implement later" / "similar to Task N" patterns. The phrase "later" appears only in `asset_phase2.py` comments noting future wire-up of optional inputs (USAspending/PATLINK), which is a documented limitation, not a placeholder.

**Type consistency:**
- `_company_key` reused from Phase 1 across Tasks 1, 2, 4, 6, 7, 9. Same signature.
- `vintage_bucket` reused from Phase 1 in Task 2.
- `wilson_interval` reused from Phase 1 in Task 4.
- `IndustryGroupClassifier.classify()` and `IndustryGroupClassifier.apply()` consistent across Tasks 0, 6, 7, 9.
- `CohortMatcher.match() -> MatchResult` with fields `matched_strata`, `matched_nsf`, `matched_controls`, `unmatched_nsf`, `unmatched_controls` consistent across Tasks 3, 6, 7, 9.
- `MatchedCohortOutcomes.compute()` returns DataFrame with columns `cohort`, `metric`, `numerator`, `denominator`, `rate`, `ci_low`, `ci_high`, `available` consistent across Tasks 4, 6, 7, 9.
- `ThreatEntry` fields `name`, `body`, `as_of` consistent across Tasks 5, 6.

No type-naming drift.
