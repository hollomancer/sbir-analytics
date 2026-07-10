# Product 1 Join-Key Audit — PIID Uniqueness, Grain, and IDV Inheritance

> **Status:** Audit complete on-branch; **fixes committed behind review, NOT merged.** This changes
> a number bound for an annual report under GAO scrutiny — freeze decision below.
> Branch: `claude/product1-piid-audit` (off the PR #423 tip).

## Go / no-go — freezing the validation sampling frame

**NO-GO to freeze today — but for a reassuring reason: Product 1 has never produced output.** Its
contract source (`data/transition/contracts_ingestion.parquet`, fallback
`data/processed/contracts_ingestion.parquet`) is **missing on disk**, and no
`data/processed/phase_iii_candidates.parquet` exists. There is **no flag population yet**, so no
report-bound number is presently at risk. This audit is therefore **preventive**: it fixes the bug
class before the first real run (post-M0a). **Freeze the sampling frame only after** (a) M0a lands a
contract source that carries the FPDS 10Q `research` element and an award-unique key, and (b) the
pipeline is re-run on the fixed code and the before/after table below is populated with real numbers.

## Phase A — Join inventory (Product 1 path)

| Site | Op | Key | Bare/Compound | Grain | Risk |
|---|---|---|---|---|---|
| `pairing.py:pair_filter_s1` merge | `merge(on="_uei")` | recipient UEI | firm key | firm → (prior×contract) pairs | **Safe from PIID collision** (firm-grade), but output is pair-grain not award-grain |
| `pairing.py:_prepare_contracts` `target_id` (pre-fix) | `_pick("contract_id","piid",…)` | bare `piid` fallback | **BARE** | contract row | **HIGH** — feeds `_candidate_id` |
| `assets.py:_candidate_id` | `sha1(class|prior|target_id)` | `target_id` | inherits bare piid | candidate identity | **HIGH** — collisions collapse distinct awards |
| `pairing.py:_is_phase_iii_already_coded` | per-row `.apply` | `research`/`sbir_phase` | — | contract row | **HIGH** — wrong grain + silent no-op if column absent |
| `assets.py:_default_retrospective_loader` | `read_parquet` | — | — | source | source missing → empties the pipeline |

Priors (`validated_phase_ii_awards`) are award-grain SBIR.gov Phase II; the merge key is UEI, so the
primary join is **not** a PIID join. The PIID exposure is entirely on the **target/identity side**.

## Phase B — Empirical collision census (on data that exists)

- **219,501 vs 540,343 reconciled.** `award_data.csv` is **540,343 physical lines** but **219,501
  parsed records**; the gap is **fully explained by embedded newlines in quoted `Abstract` fields**
  (award-grain data, not mods/transactions). Nothing unexplained remains. Use a real CSV parser, never
  `wc -l`.
- **FPDS SR3 pull (600 records, the future contract source):** the bare **order** PIID is genuinely
  "0001" for all 600 (these are all first-orders under parent IDVs, `referencedIDVID` present 100%) —
  spanning **286 firms**. Under a bare-`piid` `target_id`, all 600 collapse to a *single* identity;
  `_candidate_id` would collide across unrelated awards. **But "collapse to one key" was a parser
  artifact, not the true state** (correction below): the parent-IDV PIID varies (**485 distinct**), so
  the correct compound key `(order PIID, awarding agency, parent-IDV PIID, parent-IDV agency)` yields
  **485 distinct awards of 600 rows** (the ~115 remainder are mod/transaction dups — the transaction-
  grain multiplicity this audit warns about). The bare-PIID conclusion is *strengthened* (all → "0001"
  is worse than a partial collision); the "1 key" figure is corrected to 485.

  > **Correction (auditability, this branch).** The initial census reported "600/600 = 0001,
  > collapsing to 1 key." That uniformity was a **parser tell**: FPDS `<referencedIDVID>` is a *parent*
  > element (agencyID + PIID children), and the flat text-regex extractor silently dropped the
  > parent-IDV PIID — the varying disambiguator — leaving a degenerate compound key. Hand-verified
  > against three raw ATOM entries (parent PIIDs `OASCOOB9001`, `DAAB0700DK516`, `DAAE3003D1009`);
  > `parse_entry` now extracts the nested blocks. **The true keys were recoverable from the cache with
  > no re-pull** — 485 distinct compound keys. Lesson logged: 100% uniformity on a field that should
  > vary is a parser signal, not a data fact.
- **Cross-system key `Contract` (SBIR.gov → FPDS):** 76% non-null, but **9,204 values are shared by
  >1 award (19,815 rows)** — and many are not PIIDs at all: "NAS 96-1" (348 awards), "PHS2001-2" (145)
  are solicitation/BAA numbers. **`Agency Tracking Number` also collides** (47,105 values shared by
  >1 award). Any SBIR↔FPDS link on these bare fields is unsafe (see repo-wide list).

**Bias directions (counted separately, not netted):**
- **Manufactured flags (dominant here):** if the coding column is absent, the already-coded exclusion
  is a **silent no-op** → *every* coded Phase III to a firm becomes a candidate flag. On USAspending
  data (no `research`) this is the default failure.
- **Suppressed flags:** a bare-`piid` collision could match a candidate row to the wrong award's
  "already coded" status, dropping a true flag. Lower volume, but real.

## Phase C — Impact quantification

Because the production contract source is absent, a real before/after runs empty (**before = 0 flags;
current pipeline is a no-op**). The impact is therefore quantified **mechanistically** on a
representative frame (the SR3 census above and the committed test fixture), not on production output:

| | Bare-PIID / per-row (pre-fix) | Compound key / award-grain (post-fix) |
|---|---|---|
| Two order-"0001" awards under different parent IDVs | collapse to 1 identity ("0001") | 2 distinct award keys |
| Award with 1 SR3 mod + non-coded mods | non-coded rows survive → false flag | whole award excluded (any-SR3 rule) |
| Contracts frame lacking a coding column | silent no-op → all coded pass as flags | **raises** (fail loud) |

**Headline ratio** (flagged-uncoded / (flagged + coded), per agency): **unmeasurable today (no
output); a genuine null "before"**. The fix makes it correct-by-construction for the first real run.
Reporting the real per-agency deltas is a **post-M0a deliverable** and is explicitly gated in the
go/no-go above.

**Coded-status rule (documented choice):** the fix standardizes to the conservative, agency-generous
rule — **an award counts as coded if ANY of its transactions carries SR3/ST3**, aggregated at the
award-key grain. The pre-fix logic applied the check per contract row.

## Phase D — IDV inheritance bucket

Post-fix, an order's award key includes its parent-IDV reference, so orders under a parent are
distinguishable. **Whether an order should inherit its parent IDV's Phase III coding is a treatment
decision, not an audit call.** FPDS semantics: a task/delivery order under a Phase-III-coded IDV
frequently *is* Phase III work even when the order line omits the code; but coding practice is
inconsistent. **the parent-IDV **PIID** is now captured (parser fixed; 485 distinct), but the parent IDV's own
Phase III **coding** still requires a separate lookup of the parent records. Method to resolve
post-M0a: for each flagged order, fetch its `referenced_idv_piid`'s coding, then report the ratio
under **both** treatments (parent-coded orders counted as coded vs. as flags). The human reviewing
flags decides; the pipeline must not silently pick one.

## Phase E — Regression guards installed

1. **Loud guards in `_prepare_contracts`:** raises if the frame has only a bare PIID (no compound
   parts / no unique key), and raises if it carries no coding column (`research`/`sbir_phase`).
2. **`award_key_series()`** centralizes award-key construction (unique key preferred, else compound;
   never bare PIID) and is used for both `target_id` and coded-status grain.
3. **Committed test** `tests/unit/phase_iii_candidates/test_award_key_grain.py`: two "0001" orders
   under different parent IDVs — fails on a bare-PIID join, passes on the compound key — plus the two
   fail-loud guards and unique-key preference.
4. **Gotcha documented** in `docs/steering/data-quality.md` (alongside the record-count trap).

## Repo-wide bare-PIID joins (report-only — NOT fixed on this branch)

| Site | Risk | One-line note |
|---|---|---|
| `sbir_etl/ot_consortium/runner.py:26-38,112-117,181-197` | **CRITICAL — candidate preventive-audit #2** | bare-PIID dicts bridge firm claims → federal records, no agency disambiguation. **Not dead code** — wired into the live `assets/transition/ot_tiering.py` asset + a Neo4j loader. Triage question: do the published §638(qq)(3) commercialization-benchmark verdicts depend on this OT tiering output? If yes → audit before it bites; if no → ticket with CRITICAL label |
| `sbir_etl/extractors/sbir_gov_api.py:255-296` | MEDIUM | `by_contract` index keyed on bare SBIR.gov contract; lookup prefers it over UEI |
| `sbir_etl/enrichers/company_enrichment.py:656,726` | MEDIUM | bare `Contract` extracted → FPDS description lookup, no agency context |
| `sbir_etl/capital_events/sources/sbir_awards.py:81-83` | MEDIUM | falls back to bare `Contract` when ATN missing |
| `packages/…/phase_transition/pairs.py:237` | LOW-MED | merge on bare `phase_ii_award_id`; DUNS fallback join at :132 |
| `scripts/phase3_benchmark/build_pairs_and_score.py` | INFO | already uses a unique `pair_id`; comment acknowledges non-uniqueness |

## Open questions (surfaced, not guessed)

1. **Compound-key columns in the real M0a schema.** `award_key_series` supports several naming
   conventions (FPDS `PIID/agencyID/referencedIDVID`, FederalContract `contract_id/parent_contract_id`,
   USAspending `generated_unique_award_id`). The actual columns must be confirmed when M0a lands, and
   whether a precomputed unique award key exists (USAspending's `contract_award_unique_key`).
2. **`_is_phase_iii_already_coded` grain.** Pre-fix: per contract row. If the source is transaction-
   grain, an award's coded status was wrong; the fix aggregates to award grain (any-SR3). Confirm the
   source grain at ingestion.
3. **219,501 vs 540k:** fully explained by embedded newlines — resolved, nothing remains.
4. **Bare-PIID joins outside Product 1:** listed above; the OT consortium runner is the highest risk.
