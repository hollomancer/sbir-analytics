# Design — OT Consortium Sub-Award Attribution (FFATA/FSRS)

**Status:** spec only. See `requirements.md` for goals/constraints.

## Data source

USAspending sub-award (FFATA/FSRS) data. Three viable feeds, in order of
preference for this repo's existing infrastructure:

1. **Full DB dump `subaward` table** — already the access pattern used by
   `DuckDBUSAspendingExtractor`. Columns of interest:
   `unique_award_key` / `prime_award_piid`, `subaward_number`,
   `subawardee_uei` (+ `subawardee_name`), `subaward_amount`,
   `subaward_action_date`, `prime_recipient_uei`.
2. **Bulk sub-award archive** (CSV/parquet) — for offline/removable-media runs,
   mirrors the contracts extraction pattern.
3. **`/api/v2/subawards/` API** — per-prime lookup; fine for spot-checks, too
   chatty for population runs.

The loader is pluggable (DataFrame / parquet / CSV / table name), exactly like
`claims_loader` and the contracts extractor, so the feed can vary by environment.

## New components

```
sbir_etl/ot_consortium/
  subawards.py        # SubawardRecord model + SubawardIndex (prime_piid -> members)
  # classifier.py     # + route (c): subaward_uei
  # models.py         # OTAward: no change needed (lookup is external, like registry)
  # runner.py         # build SubawardIndex, pass into classify_*
  # aggregate.py      # recovered_from_rollup_{usd,count} on MagnitudeReport
sbir_etl/extractors/usaspending.py  # + extract_subawards(prime_piids)
config/schemas/domain.py            # OTConsortiumConfig: subaward_path, ffata_threshold_usd
```

### `SubawardRecord` / `SubawardIndex`

```python
class SubawardRecord(BaseModel):
    prime_piid: str
    subawardee_uei: str | None
    subawardee_name: str | None
    subaward_amount: float | None
    action_date: date | None

class SubawardIndex:
    # prime_piid (normalized) -> list[SubawardRecord]
    def members_of(self, prime_piid: str) -> list[SubawardRecord]: ...
    def attributed_amount(self, prime_piid: str, firm_uei: str) -> float | None:
        # sum of subaward_amount where subawardee_uei == firm_uei (exact)
```

The index is built once per run and passed to the classifier the same way the
CMF registry is — keeping `assign_tier` pure and unit-testable.

## Classifier integration — third T1 route

`assign_tier` gains an optional `subawards: SubawardIndex | None`. Precedence,
inserted among the existing authoritative T1 routes (all still require PIID 9th
∈ {3,9}); routes are tried in order and the first authoritative match wins:

```
T4  no federal record
T1a Consortia=Yes ∧ member UEI == firm UEI                      (resolution_method="uei")
T1b order recipient UEI == firm UEI under CMF base             ("order_recipient_uei")
T1c CMF prime ∧ subaward subawardee UEI == firm UEI            ("subaward_uei")   <-- NEW
T3  modification-based
T2  rollup / residual
```

Route **(c)** fires when: the recorded vendor (or base) is a registry CMF **and**
`subawards.attributed_amount(prime_piid, firm_uei)` is non-null. On a hit:

- `tier = T1`, `resolution_method = "subaward_uei"`.
- **`obligation_amount` is overridden with the sub-award amount** (member-level),
  and the original prime rollup is recorded in `metadata["rollup_obligation"]` so
  the audit trail shows both. This is the one place a tier assignment rewrites the
  obligation, because the prime total is explicitly *not* the firm's amount.
- Evidence cites the `subaward_number`, subawardee UEI, and amount.

Where (c) does not fire, behaviour is exactly today's — T2/T3 unchanged. Absence
of a sub-award never moves a record.

## Magnitude report

`aggregate` adds two first-class fields:

- `recovered_from_rollup_count` — records that route (c) lifted from T2 to T1.
- `recovered_from_rollup_usd` — sum of the sub-award amounts so attributed.

These are reported alongside the verified total with a note that they were
recovered from the rollup bucket via FSRS sub-awards, so the provenance of the
verified number stays legible. The unverifiable share is recomputed *after*
recovery (the recovered records leave T2), and the report still surfaces the
residual unverifiable share prominently.

## Dagster / config

- `OTConsortiumConfig`: `subaward_path: str | None = None`,
  `ffata_threshold_usd: float = 30000.0` (documented, used only for the "below
  threshold is invisible" caveat in metadata — we do not filter the firm's
  attributed amount by it).
- `ot_consortium_verification_tiers` asset: if a subaward feed is configured (env
  `SBIR_ETL__OT_CONSORTIUM__SUBAWARD_PATH` or the full-DB `subaward` table), build
  the `SubawardIndex` and pass it through; otherwise behave exactly as today
  (graceful no-op, like the CMF UEI enrichment).

## Risks & limitations (carry into metadata, like the FPDS lag note)

- **OT sub-award coverage is partial.** FFATA is built for contracts/grants; many
  CMFs do not file FSRS sub-awards for OT distributions. This recovers some, not
  all — the unverifiable share shrinks, it does not vanish.
- **Self-reported quality.** Sub-award data is prime-reported; amounts and UEIs
  have known gaps. UEI-exact matching protects T1 precision; partial rows simply
  don't reach (c).
- **Volume.** The `subaward` table is large; restrict ingestion to prime PIIDs in
  the CMF/consortium population (we already know the CMF primes from the registry
  + detected OT records) rather than loading the whole table.
- **T3 stays dark.** Modification-based rows have no sub-award and no member
  field; this route does not touch them.
