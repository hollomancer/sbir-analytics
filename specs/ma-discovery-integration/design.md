# M&A Discovery Integration — Design (1-pager)

**Status:** Draft for review.
**Date:** 2026-06-26.
**Relates to:** [`specs/archive/completed-features/merger_acquisition_detection/`](../archive/completed-features/merger_acquisition_detection/design.md) (existing Form D + EFTS detection), [`sbir_etl/capital_events/sources/ma_events.py`](../../sbir_etl/capital_events/sources/ma_events.py) (downstream consumer), local branch `chore/ma-discovery-toolkit` (scaffolded toolkit, never merged) preserved in draft PR [#371](https://github.com/hollomancer/sbir-analytics/pull/371).

## Why

The existing `detect_sbir_ma_events.py` infers M&A from two signals: Form D business-combination offerings and EFTS (SEC EDGAR Full-Text Search) mention classifications (`subsidiary`, `acquisition`, `ma_definitive`, `ma_proxy`, `ownership_active`). Firms that are acquired *without* either signal — small private-to-private deals where no Form D is filed and the acquirer leaves no full-text-searchable EDGAR mention, asset acquisitions, acquihires of pre-revenue firms — produce no detection at all. The capital-events timeline records `MA_EVENT` rows; missing rows in this segment are invisible miscounts of SBIR exits.

A web-search-based discovery path can recover some of those, but only if the rows it produces (a) plug into the existing pipeline without re-shaping it and (b) don't compete with or corrupt the high-quality Form D / EFTS evidence.

## The Decision

The capital-events builder at `sbir_etl/capital_events/sources/ma_events.py:13-55` reads `data/enriched_sbir_ma_events.jsonl` and filters on `confidence in {"high", "medium"}` (string tier, not a numeric score). The pipeline shape is fixed; discovery must conform to it.

Note: `detect_sbir_ma_events.py` writes `data/sbir_ma_events.jsonl`; the builder reads `data/enriched_sbir_ma_events.jsonl`. **No script in this branch produces the enriched file** — the press-wire enrichment step (`SyncPressWireClient` in `sbir_etl/enrichers/press_wire.py`) exists as a library but is not wired into a standalone CLI. The diagram below treats `enrich_ma_with_press.py` as a **to-be-added** component; discovery integration assumes this enrichment glue lands as part of (or before) the discovery implementation PR.

**Adopted: option C with collision rule C3.**

```
detect_sbir_ma_events.py ─► sbir_ma_events.jsonl ─┐
                                                  ├─► [TODO] enrich_ma_with_press.py ─► enriched_sbir_ma_events.jsonl ─► capital_events.parquet (MA_EVENT)
ma_discovery_orchestrator ────────────────────────┘                                     ▲
       ▲                                                                                │
       └── runs only on Form-D-missing rows surfaced by detect_sbir_ma_events           └── filter: confidence in {high, medium}
```

Discovery is a candidate-expansion step that fires only for firms detect_sbir_ma_events emitted *without* Form D backing. Its output joins `sbir_ma_events.jsonl` before press enrichment, so discovered rows pick up press-wire signals the same way Form D-backed rows do. Until the press-enrichment CLI is wired up, discovery output can be concatenated directly into `enriched_sbir_ma_events.jsonl` (the file the builder reads); the field contract is the same.

### C3 collision rule

When a discovered row matches an existing `sbir_ma_events.jsonl` row on `(company_name, event_date)` (or `event_date` ± 30 days). If the existing row's `event_date` is empty or missing (common for EFTS-only rows), fall back to company-name-only matching:

| Existing row's confidence | After discovery confirms | Behavior |
|---|---|---|
| `high` | stays `high` | Set `signals.discovery_confirmed = true` on the existing row (the builder propagates `signals` into `metadata`; see note below). Do not write a duplicate row. |
| `medium` | bumped to `high` | The discovery serves as independent corroboration; that is exactly the bar for promoting medium → high. Also set `signals.discovery_confirmed = true`. |
| `low` | bumped to `medium` | Now reaches the capital-events filter threshold. Discovery is the second of two required signals (per existing detection's promotion ladder). Also set `signals.discovery_confirmed = true`. |
| `(no existing row)` | inserted at the discovered row's own confidence | Bounded by per-row confidence rules below. New rows include `signals.discovery_confirmed = true`. |

Discovery never *lowers* a confidence and never *overwrites* a Form D-derived acquirer. If the LLM extractor disagrees with Form D on the acquirer name, the Form D value wins and the discovered acquirer is recorded as `signals.discovered_acquirer_disagrees = "<discovered_name>"`.

**Why `signals` and not a new top-level field:** `sbir_etl/capital_events/sources/ma_events.py` builds the emitted `CapitalEvent.metadata` from a fixed set of keys (`signals`, `press_wire_signals`, `signal_count`, `enriched`). Any flag placed in a *new* top-level field on `enriched_sbir_ma_events.jsonl` would be silently dropped at the builder step. Adding flags inside `signals` propagates them into `capital_events.parquet` without changing the builder. The existing `signals` dict is `dict[str, bool]` — extending it with one additional `str` value (`discovered_acquirer_disagrees`) is the smallest accommodating change; if a strict-type contract is preferred, that disagreement payload can move to `signals.discovered_acquirer_disagrees: bool` plus a sibling `signals.discovered_acquirer_name: str` written by the orchestrator.

### Per-discovered-row confidence (new rows, no collision)

Discovery's confidence assignment is conservative — the goal is to surface real misses, not pad counts:

| LLM extractor outcome | Confidence |
|---|---|
| Company name match + acquirer name match + extracted `acquisition_date` + extracted `value_usd` + ≥2 distinct sources | `high` |
| Company name match + acquirer name match + extracted `acquisition_date` + (no value OR single source) | `medium` |
| Company name match + acquirer match but date is "Unknown" / ambiguous, or rumor/talks-only language | `low` (filtered out downstream) |

Rows that fail company-name match outright are not written. The LLM extractor's `acquisition_date` field is mapped to `event_date` when the orchestrator writes JSONL, to match the existing on-disk contract consumed by `ma_events.py`.

## MAEvent model — fix the `confidence` field

The toolkit's `MAEvent.confidence: str` field on the `chore/ma-discovery-toolkit` branch has no derivation logic (description says "derived from the score" but every caller has to set it manually). Replace with a Pydantic `@computed_field` over `confidence_score`:

```python
class MAEvent(BaseModel):
    ...
    confidence_score: float = Field(description="0.0–1.0; raw score from the detector.")

    @computed_field
    @property
    def confidence(self) -> Literal["low", "medium", "high"]:
        if self.confidence_score >= 0.75:
            return "high"
        if self.confidence_score >= 0.45:
            return "medium"
        return "low"
```

**File-contract requirement.** The capital-events builder filters on the string-typed `confidence` tier (`_KEEP_CONFIDENCES = {"high", "medium"}`); it does not read a numeric score. Discovery must emit the string `confidence` tier in each row of `enriched_sbir_ma_events.jsonl` — internally derived from `confidence_score` via the `@computed_field` above, but the on-disk contract is the tier, not the score. The `≥ 0.45` threshold above is therefore an *internal* starting point; the builder-level inclusion bar is `confidence in {"high", "medium"}`.

**Threshold alignment requirement.** The preserved toolkit branch in PR #371 currently maps `confidence_score` to tiers at different cutoffs (`high >= 0.8`, `medium >= 0.5`) via a model validator. Do not land the confidence-field cleanup until the implementation branch either adopts the provisional `0.75 / 0.45` cutoffs in this design or explicitly replaces them with empirically calibrated thresholds. The important invariant is that every producer writes the same string tier for the same numeric score before rows reach `capital_events.parquet`.

## Triggering & cost

**Trigger model: manual for v1.** Discovery runs on-demand against the current `sbir_ma_events.jsonl`. Promotion to a Dagster sensor / scheduled refresh is a follow-up after recall has been measured.

**Cost cap:** every run is bounded by `--max-candidates N` (default 200) and `--max-cost-usd $X` (default $5). The orchestrator stops dispatching queries the moment either is hit and writes a partial output file. This is enough to surface useful signal on the first batch without bill surprises.

**Idempotency:** the orchestrator skips any `(company_name, event_date)` pair already present in `enriched_sbir_ma_events.jsonl` with `confidence in {high, medium}` *and* `signals.discovery_confirmed == true` (or with `confidence == "high"` independent of discovery — that row is settled). Keying on `acquirer` is unstable because Form D-only events have `acquirer = null` and would all collide on `(name, null)`. `event_date` is the right second axis: it's already the de-dup key used by the builder (`source_id = f"{name}__{event_date}"` in `ma_events.py`). For rows with an empty `event_date`, fall back to `(company_name, "")` and only skip if a prior discovery run already touched that row (via the `signals.discovery_confirmed` flag). Re-runs only target genuinely-unanswered candidates.

## Out of scope for v1

- Auto-tuning the confidence thresholds against a labeled set. Use the boundary thresholds above and revisit after the first manual run.
- Press-release scraping beyond the existing `SyncPressWireClient` (in `sbir_etl/enrichers/press_wire.py`). The to-be-added `enrich_ma_with_press.py` CLI is expected to wrap this client and stay in the pipeline as a sibling step.
- Discovery for non-Form-D-missing firms ("would discovery surface a *better* signal for a row Form D already covered?"). Adds cost without clearly improving recall.
- A graph loader for discovered M&A events. They flow into `capital_events.parquet` like every other source; the Neo4j path picks them up at the existing `MAEventLoader`.

## Open decisions deferred to the implementation PR

These are choices the design intentionally does *not* pin, because they're independent of the integration shape and easier to settle when the code is in front of us:

| Decision | Default I'd lead with | Why deferred |
|---|---|---|
| Search backend (Tavily / Brave / Bing / Serper) | Tavily — purpose-built for snippet-focused agentic search; pluggable interface stays put | Pricing changes; better resolved with a real cost estimate |
| LLM verifier model | Claude Haiku 4.5 for cost; Sonnet 4.6 for ambiguous cases (two-stage) | Calibrate per actual snippet quality |
| Output module path | `sbir_etl/enrichers/ma_discovery/` (matches enricher convention) | Easier to refactor when tests exist |
| Confidence threshold tuning | Provisional 0.75 / 0.45; must align #371 or be replaced by calibrated cutoffs before implementation lands | Empirical |

## Implementation sequencing (after this design is approved)

1. **Fix `MAEvent.confidence`** as a `@computed_field` and align the score-to-tier cutoffs with this design (or replace both with calibrated thresholds). Standalone PR; small, safe, lands first.
2. **Move toolkit scripts to a module path** (`sbir_etl/enrichers/ma_discovery/`) and fix relative imports. No behavior change.
3. **Implement a real `SearchTool`** against the chosen backend, with config + credentials in `.env.example` and `OTConsortiumConfig`-style schema entry.
4. **Replace keyword verifier with LLM extractor.** Structured output: `{matched_company, matched_acquirer, acquisition_date, value_usd, citation_url}`.
5. **Wire collision-detection / C3 promotion logic** between discovery output and existing `sbir_ma_events.jsonl`.
6. **Unit tests:** mocked search backend, mocked LLM, fixture-based positive / negative / collision-promotion cases.
7. **Sample run** on the actual Form-D-missing population; report (a) candidate count, (b) confirmed count, (c) confidence distribution, (d) cost. This baselines whether to keep or kill the effort.

Each of these is a separate PR, sequenced. Steps 1–2 are no-cost cleanups that can land independently of the discovery effort even if it's later abandoned.

## Success criteria

Discovery is worth landing if, after the sample run in step 7:

- It surfaces ≥ 10 confirmed `medium`-or-`high` confidence M&A events in the Form-D-missing population that detect_sbir_ma_events would not have produced.
- The false-positive rate (manual review of a stratified sample of 20 medium-confidence rows) is ≤ 25%.
- Per-row cost (search + LLM) is ≤ $0.10 at the chosen backend / model combo.

Below those numbers, close the draft PR and document the lessons in `specs/archive/completed-features/merger_acquisition_detection/` as a "tried, didn't pay off" note.
