---
Type: Operator Guide
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-09-17
Status: active
---

# M&A Events Refresh

The M&A exit artifacts are produced by four CLI scripts run in order, not by a
Dagster asset. Each step fails closed on an input the previous step did not
prepare, so running them out of order produces an error rather than a wrong
number — but the order itself is not discoverable from any single script.

This runbook records the sequence, what each guard rejects, and the state the
stored inputs are actually in.

## Sequence

| Step | Script | Writes |
| --- | --- | --- |
| 1 | `scripts/data/rescore_form_d_details.py` | `data/form_d_details.jsonl` (in place, atomic) |
| 2 | `scripts/archive/data/detect_sbir_ma_events.py` | `data/sbir_ma_events.jsonl`, `data/sbir_ma_non_exit.jsonl` |
| 3 | `scripts/archive/data/refine_ma_medium_tier.py` | a directional-refinement JSONL |
| 4 | `scripts/archive/data/apply_ma_direction_refinement.py` | `data/enriched_sbir_ma_events.jsonl` |

Steps 1, 2 and 4 are offline and deterministic. Step 3 queries SEC EDGAR
full-text search and fetches filing documents, so it is the only step whose
runtime depends on the network and the only one that is not reproducible from a
declared cut alone.

## Step 1 — rescore Form D tiers

```bash
python scripts/data/rescore_form_d_details.py --input data/form_d_details.jsonl
```

Reads only signal values already present in the file and performs no network
requests. Output is deterministic and published with an atomic same-directory
replace.

**Why it is not optional.** Step 2 calls `require_form_d_tier_rule`, which
rejects any record whose `rule_version` is not the current
`corroborated-person-v2`:

```
FormDTierRuleError: Form D record '...' uses Form D tier rule None;
expected 'corroborated-person-v2'.
```

As of 2026-09-17 all 10,405 stored records were unversioned, so this step was
required before the chain would run at all. Migrating them moved 193 records
from `high` to `medium` (3,640 → 3,447 high; `low` unchanged at 5,645).

## Step 2 — detect events

```bash
python scripts/archive/data/detect_sbir_ma_events.py \
  --form-d data/form_d_details.jsonl \
  --efts data/sec_edgar_scan.jsonl \
  --awards data/raw/sbir/award_data.csv \
  --output data/sbir_ma_events.jsonl \
  --non-exit-output data/sbir_ma_non_exit.jsonl
```

`--awards` defaults to a `/tmp` path and must be pointed at the canonical
awards CSV. The two output paths must differ; equal resolved paths are rejected
before either handle opens, because both are buffered and would truncate each
other.

Two population gates run here, both introduced in #735:

- Records whose identity match did not reach `KEEP_MATCH_TIER` (`high`) are
  dropped, and the drop count prints.
- Rows whose only transaction evidence is Form D Item 10 are written to
  `--non-exit-output` with `non_exit_reason='acquirer_side'` rather than to the
  exit artifact. Item 10 marks a Rule 145 deemed offer and sale *by the
  issuer*, so the filer is the acquirer and the flag points away from an exit.

## Step 3 — refine directions

```bash
python scripts/archive/data/refine_ma_medium_tier.py \
  --input data/sbir_ma_events.jsonl \
  --output data/sbir_ma_direction_refined.jsonl \
  --resume --concurrency 2
```

Only events for which `needs_directional_refinement` is true require a record.
`--resume` skips companies already present in the output, so an interrupted run
costs only wall time. `--contact-email` defaults to the maintainer address
committed in the script.

**Throughput.** Measured 2026-09-17: 16 events/minute sustained at the default
concurrency of 2, so a full corpus of ~2,650 events takes roughly 2.5–3 hours.
A short sample overstates the rate — a 25-event sample projected 42/minute
because those events needed fewer document fetches than the corpus average.
Size the run from the sustained figure, not a sample.

## Step 4 — apply directional refinements

```bash
python scripts/archive/data/apply_ma_direction_refinement.py \
  --events data/sbir_ma_events.jsonl \
  --refinements data/sbir_ma_direction_refined.jsonl \
  --output data/enriched_sbir_ma_events.jsonl
```

This is the deterministic bridge, and its contract is strict in both
directions. It raises rather than guessing when:

| Condition | Error |
| --- | --- |
| a direction-sensitive event has no refinement | `refinement coverage mismatch: missing_count=...` |
| a refinement names an event that is not direction-sensitive | `refinement coverage mismatch: unexpected_count=...` |
| `context_classification_complete` is absent or not a bool | `refinement for '...' lacks typed context completeness` |
| completeness and `direction` disagree | `... has inconsistent direction and context completeness` |

`--refinements` takes **one** path.

A fresh step 3 writes a single file, so nothing extra is needed — pass the file
step 3 produced. As of 2026-09-17 that is
`data/sbir_ma_direction_refined.jsonl` (2,697 records), which is what the
command above uses.

Only the **legacy** corpus needs assembling. It predates the consolidated file
and is split across `data/sbir_ma_medium_refined.jsonl` and
`data/sbir_ma_low_refined.jsonl` (no company overlap), which are retained as
the prior vintage:

```bash
cat data/sbir_ma_medium_refined.jsonl data/sbir_ma_low_refined.jsonl \
  > data/sbir_ma_direction_refined_legacy.jsonl
```

Nothing in the argument surface indicates the split, and passing only the medium
file fails with a `missing_count` in the thousands. Note that concatenating the
legacy files is necessary but not sufficient: 2,656 of those records lack the
`context_classification_complete` field the bridge requires, so the legacy
corpus fails this step even when assembled — see the input findings below.

### Interaction worth knowing

`confidence_after_directional_refinement` returns `high` for any row carrying
`form_d_business_combination`, whatever the refined direction. That is only
sound because step 2 routes acquirer-side-only rows to the sibling artifact
before the bridge sees them. Rows that reach the bridge with a Form D
combination also carry target-side EFTS evidence. Relaxing the sibling routing
would restore the inflation #735 removed, through this line.

## Known state of the stored inputs

These four findings describe the **legacy** corpus, as it stood on 2026-09-17
before the chain was re-run. All predate #735. They are recorded because they
explain why that corpus cannot be fed to step 4, and because anyone reaching
for `sbir_ma_medium_refined.jsonl` or `sbir_ma_low_refined.jsonl` will hit
them.

All four are remediated in the current
`data/sbir_ma_direction_refined.jsonl`: the corpus was re-refined in full, the
40 missing events were fetched, the 4 orphaned records dropped, and the
malformed one replaced. The legacy files are retained unchanged as the prior
vintage.

| Finding | Count |
| --- | --- |
| refinement records lacking `context_classification_complete` | 2,656 of 2,697 in play |
| direction-sensitive events with no refinement record at all | 40 |
| refinements naming events that are not direction-sensitive | 4 |
| refinement records whose `direction` is malformed | 1 (`Physical Optics Corporation`) |

Consequence: the shipped `enriched_sbir_ma_events.jsonl` cannot have been
produced by step 4 from these inputs, because step 4 would have rejected them.
The 40 missing events were already direction-sensitive and low-confidence
before #735, so the gap is not a side effect of the tier gate. Re-running step
3 for an affected company produces a complete record, so the gap is a coverage
gap in the stored corpus rather than a property of the events.

## What is not reproducible

The shipped artifact carried 4,306 companies against the events file's 4,004,
plus a `press_wire_signals` field. That field's producer was deleted in #709:
it polled live RSS, so its output was a function of wall-clock time rather than
a declared cut, and its precision was 0/18 because company matching used an
unanchored substring test. Of the 4,306 rows, 18 carried any press-wire
evidence; the 302 companies absent from the events file were all Form-D-only
rows graded `high`, 301 of them with an empty `press_wire_signals` list.

A rebuild therefore drops those 302 rows and that field by design. Consumers to
re-run afterwards: `scripts/data/build_capital_events.py`,
`scripts/data/build_supplier_share_census.py`,
`scripts/data/build_form_d_ma_cross_enrichment.py`, and anything reading
`sbir_etl/utils/transition_signals.py` (`sig_ma_detected` is computed from the
enriched artifact).

## Related documentation

- [Data Sources Overview](README.md)
- [Capital events](capital-events.md)
- [Form D data dictionary](../research/form-d-data-dictionary.md)
- [Form D and M&A cross-enrichment](../research/form-d-ma-cross-enrichment.md)
- [Research questions — M&A detection is script-driven](../research-questions.md)
