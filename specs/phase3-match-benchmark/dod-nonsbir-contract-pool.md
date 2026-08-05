# DoD non-SBIR contract pool: recipient-scoped puller

Status: **spec — not yet built. Gated behind the precision@K manual eval (see Gates).**

## What this unlocks

The NASA side has a non-SBIR target pool (TechPort, `nasa-techport.md`) that made within-NASA (0.879) and
cross-agency DoD→NASA (0.828, `cross-agency-scope.md`) transition retrieval measurable. DoD has **no
equivalent** — our only DoD target pool is the SR3/ST3-*coded* contracts (`m0a_coded_dod`, SBIR by
construction). Building the DoD analogue — a recipient-scoped pull of DoD SBIR firms' **non-SBIR** contracts
— collapses three open questions into one dataset:

1. **NASA→DoD transitions** — currently 3-strict, blocked *only* because the DoD target pool is SBIR-coded.
   A non-SBIR DoD pool makes the reverse direction measurable (run the same puller over NASA-SBIR firms' UEIs).
2. **DoD-internal *uncoded* Phase III** — the layer below the 141. The undercount (`undercount-award-grain.md`)
   is *described-not-coded* (the contract text still says "SBIR PHASE III"). This finds DoD SBIR tech maturing
   into contracts with **no SBIR marking at all** — invisible to any code- or description-based count.
3. **Real targets for the #455 DoD ranker** — today it trains on coded/described notices; recipient contracts
   give it the actual follow-on universe.

## Approach — extend `pull_described_phase3.py`, don't rebuild

Same USAspending `spending_by_award` endpoint, same `Fetch = Callable[[bytes], bytes]` seam, same manifest
shape and `_field_completeness`. Two changes: filter by **recipient**, not description; and **subtract SBIR**
in post.

New module `scripts/phase3_benchmark/pull_recipient_contracts.py`:

```text
_request_body(uei, award_types, page, start, end)   # spending_by_award, recipient_search_text=[uei],
                                                     #   NO description filter (we want ALL contracts)
pull_recipient(uei, *, start, end, max_pages, fetcher, source_vintage) -> (DataFrame, manifest)
pull_recipients(ueis, *, cache_dir, pace, fetcher, ...)  -> (DataFrame, manifest)  # per-UEI cache, paced
exclude_sbir(frame, coded_keys, described_keys)     -> DataFrame                    # the crux, below
main(argv)                                           # --ueis-file --agency --out --manifest --cache --limit
```

- **Recipient filter:** `filters.recipient_search_text: [uei]` (USAspending matches UEI here). Award types
  contracts only: `["A","B","C","D"]` + IDV group, mirroring `AWARD_TYPE_GROUPS`. Fields add `PSC Code`,
  `NAICS Code`, `Recipient UEI`, `generated_internal_id` to the existing `FIELDS`.
- **SBIR exclusion (three layers, most-reliable first):**
  1. drop award keys present in the SR3/ST3-coded pool (`m0a_coded_dod`, via `award_key_series`);
  2. drop keys present in the described-Phase-III pull (the 141/962 — already counted);
  3. drop rows whose `Description` matches `SBIR|STTR|PHASE\s*(I|II|III)` (belt-and-suspenders).
  The residual = the firm's DoD contracts with **no SBIR signal** = the uncoded candidate transition pool.
- **Output contract:** one row per (recipient UEI, non-SBIR DoD contract): award key, UEI, description,
  amount, action date, awarding sub-agency, PSC, NAICS. This is the **target** side for the ranker
  (query = firm SBIR abstract), keyed by UEI — drops straight into `transition_ranker.evaluate`.
- **Manifest parity:** `endpoint`, `source_vintage`, `run_at`, `recipients_requested`, `recipients_returned`,
  `rows_total`, `rows_after_sbir_exclusion`, per-recipient `raw_sha256`, `field_completeness`,
  `retrieval_complete` (all recipients paged to feed exhaustion, none throttled-out).

## This does NOT defeat the base-rate wall — scoping does

The output is **not** a Phase III classification. A global "is this DoD contract a Phase III?" is the
~1%-prevalence / need-0.95-AUC trap. This pool is only ever consumed **per-firm**: "which of *this firm's*
non-SBIR contracts continue *its* SBIR tech?" — firm-scoping tames the base rate, and it is the identical
retrieval frame that already yields 0.828 / 0.844 / 0.879. Evaluation is firm-clustered retrieval
(`evaluate`, GroupKFold by firm, same-register hard negatives = other firms' non-SBIR DoD contracts). No
count is emitted from the pool itself.

## Scale & cost

~8,064 DoD SBIR firms (UEI). USAspending pages 100/award; most firms hold <100 contracts → ~1–3 pages each
→ ~8–24k requests, paced + per-UEI cached → **resumable**, moderate effort. Scope **v1 to a subset** to
validate before the full sweep:
- the 1,487 firms already in `m0a_coded_dod` (known DoD Phase III performers), or
- the 306 cross-agency firms (lets us close NASA↔DoD both directions on a known cohort first).

## Testing (mirror `test_pull_described_phase3.py`)

Fixture with a canned `fetcher`; no network. Assert: (1) `_request_body` carries the UEI in
`recipient_search_text` and no description filter; (2) `exclude_sbir` drops coded + described keys and keeps
the uncoded residual; (3) manifest shape + `retrieval_complete` logic (throttle → False); (4)
`rows_after_sbir_exclusion` ≤ `rows_total`.

## Gates (do not build ahead of these)

1. **Manual eval confirms the proxy.** The precision@K pass must show that "a firm's non-SBIR contract that
   its SBIR abstract retrieves" is a *genuine* transition, not unrelated firm work — sample the 72 strict
   DoD→NASA cases + a within-DoD stratum first. If the proxy is weak, this pull harvests noise.
2. **v1 scoped subset** (coded-pool or cross-agency-306 firms) before the 8k sweep.
3. **Precision@K on ranker top-candidates** before any DoD-internal uncoded figure is reported — same
   discipline as the 141 (`undercount-award-grain.md`): a retrievable candidate is not a confirmed Phase III.

## Relation to PRs

Puller lives with the others in `scripts/phase3_benchmark/`. Feeds the #455 DoD ranker (real targets),
unlocks the `cross-agency-scope.md` NASA→DoD reverse direction, and supplies the DoD-internal uncoded
candidate layer. Symmetric with `pull_techport_nasa.py` — together they give both agencies a non-SBIR
target pool keyed by firm UEI.
