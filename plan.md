# Phase III Detection — Phase 0 Survey & Execution Plan

> **Status:** Survey complete; **paused for review before any large data pulls or spec writing** (per task Phase 0 / acceptance criterion 1).
> Scope: match-quality benchmark (Deliverable A) + three product specs (Deliverable B: Products 1, 2, 4). No Product 3, no violation classifier, no training on "violations."

## 1. Capability inventory (house status ladder)

| Capability | Status | Location / evidence | Dependency tags |
|---|---|---|---|
| SBIR Phase II **abstracts** | **Implemented** | `data/raw/sbir/award_data.csv` — 99.9% fill on 68,075 Phase II; median 1,308 chars; **13.5% are ≤100-char stubs** | — |
| Entity-resolution cascade (`resolve_entities`) | **Implemented** | `packages/sbir-analytics/sbir_analytics/tools/phase0/resolve_entities.py` — UEI→DUNS exact, then **Name+State** deterministic (Step 4), then fuzzy(rapidfuzz)→LLM tiebreak. *Note: the docstring says "Name+State+NAICS" but the code matches on Name+State only — NAICS is stored, not used. CAGE is indexed for FPDS vendors, not SBIR company rows.* | `ER` |
| **Successor-in-interest / novation** resolution | **Not started** (events only = Partial) | `sbir_etl/enrichers/sec_edgar/enricher.py` emits `EdgarMAEvent`/`CompanyEdgarProfile` but does **not** cascade acquirer→SBIR lineage. **Gap** for Product 2 and for N1 non-lineage confirmation | `M&A signals`, `SEC EDGAR`, `ER` |
| ModernBERT-Embed similarity | **Implemented** | `packages/sbir-ml/sbir_ml/ml/modernbert_client.py` (`nomic-ai/modernbert-embed-base`, `compute_similarity`); 22k abstracts + contract descs already embedded (PR #413, median cosine ~0.69) | `IMP` |
| Lexical baseline (topical) | **Partial** | `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/similarity.py` — NAICS+PSC+Jaccard. **No TF-IDF/BM25** → build for A2 | — |
| FPDS **descriptions** (SBIR subset) | **Partial** | `data/processed/sbir_phase3/*.jsonl` `Description` field, 100% fill on 2,013–4,082 keyword-filtered rows; **text is thin** ("SBIR PHASE III AWARD.") | — |
| FPDS **full candidate population** (all contracts, SBIR agencies, 5–8 FYs) | **Not started** | `sbir_etl/extractors/contract_extractor.py` reads a USAspending Postgres dump that is absent; its output `data/transition/contracts_ingestion.parquet` is an **expected runtime artifact, not present** in the repo — so the Product 1 asset emits nothing (confirmed in the join-key audit) | — |
| **FPDS Element 10Q** (`research`, SR3/ST3 coding) | **Not started** | Codes defined in `sbir_etl/models/sbir_identification.py` but **not populated**; Phase III currently inferred from description text (~32% DoD recall) | `ID` |
| IDV↔order linkage | **Partial** | `parent_contract_id` (referenced_idv_piid), ~20% fill | — |
| Competition/authority codes | **Partial** | `extent_competed` 100%; `other_than_full_and_open` not ingested | — |
| FSRS / subaward | **Not integrated** | Not wired into the core pipeline; subaward *exploration* tooling exists (`scripts/ot_consortium/probe_subaward_coverage.py`; USAspending queries pass `subawards: false`). **Blocks Product 2 subaward check** until integrated | — |
| Phase I→II→III progression (same firm) | **Implemented** | `detect_award_progressions` (`sbir_neo4j_loading.py`) → Neo4j `FOLLOWS`, conf = 0.5 +topic +PI +timing. **Prior art for Product 1** | `ER`, `ID` |
| Transition-detection scorer | **Implemented** | `packages/sbir-ml/sbir_ml/transition/detection/` — lineage regex, 6-signal score, `ConfidenceLevel {HIGH,LIKELY,POSSIBLE}`. **Prior art overlapping Products 1/2 — reuse, do not re-implement** | `transitions` |
| Two-tier confidence grammar | **Convention** | Tier-1-exact / Tier-2-fuzzy grammar used across the repo (transition scorer `ConfidenceLevel {HIGH,LIKELY,POSSIBLE}`; enrichment High/Med/Low in `docs/steering/glossary.md`). Product 2 lead tiers mirror this. *(A `specs/nih-commercialization-signal/` spec stating Tier 1 ~0.98 / Tier 2 ~0.78 exists locally but is **untracked** — not in this PR.)* | — |

> **Evidence note.** `data/` is gitignored, so rows citing `data/**` (fill rates, lengths, coverage)
> are computed from **local, uncommitted data runs** (SBIR / USAspending / FPDS pulls) and are not
> validatable from the PR diff alone. Reproduce via `scripts/phase3_benchmark/` and the pull commands
> in §5. File paths are shown at full repo-relative form where they exist in-tree.

## 2. Milestone zero (data) — the timeline-defining gap

Two sources are **not** ingested and gate the work:

- **M0a — Candidate contract population with descriptions.** Needed for A0 census + N1/N2 negatives. Full contracts (not just SBIR keyword hits) from SBIR-participating agencies, recent 5–8 FYs. Path: USAspending `spending_by_award` API (descriptions present) ranged by agency+FY, cached to `data/raw/usaspending/`. **Large pull — deferred pending your go.**
- **M0b — FPDS Element 10Q coding for label construction.** USAspending surfaces 10Q poorly; the structured SBIR/STTR/Phase-III code likely requires the **FPDS ATOM feed**. Required so P1 **positive labels come from agency coding, not description keywords** (see §3). Also directly quantifies the GAO-24-106398 [L14] undercount = Product 1's benchmark anchor.

If M0b proves infeasible from public data, P1 positives fall back to related-award structural keys (§4) and the benchmark leans harder on P2/P3 — a material scope change I will surface, not absorb silently.

## 3. Critical design constraint — no label leakage
P1 positives ("coded Phase III, same firm") must be labeled from the **structured 10Q field**. If labeled from description text containing "PHASE III", the feature (description similarity) contains the label and A2 metrics are meaningless. This is non-negotiable and reshapes M0b from "nice to have" to "required for a valid benchmark."

## 4. Open questions → answers from the survey
1. **Full-text FPDS descriptions ingested?** Partial — SBIR-keyword subset only (100% fill but thin); full candidate population **not** ingested (M0a).
2. **SBIR.gov related-award references as Tier-1 keys?** No explicit "related award" field. But **`Contract` (79% Phase II fill) = the FPDS PIID** → a genuine Tier-1 SBIR→FPDS join key; **`Agency Tracking Number` (99.8%)** links within SBIR.gov. Proposed Tier-1 pairing keys.
3. **2026 FPDS schema deltas (Pub. L. 119-83, signed 2026-04-13)?** Referenced in `docs/research-questions.md`; **not reflected** in ingestion. 10Q post-reauth award-category values **unverified** — must check current FPDS data dictionary before trusting any SR3/ST3 value. Flagged, not adapted from memory.
4. **Proposed A3 thresholds?** Start from task anchors — precision@10 ≥ 0.30 vs N1 hard negatives *in the well-described stratum*, P3 gold recall@50 ≥ 0.60, meaningful N3 sibling discrimination — but **revisit after A0**: descriptions look thin enough that the "well-described stratum" may be small; A0 decides whether the anchors are even measurable.

## 5. Execution order (plan → census → sample → harness → report → specs)
- **M0** (gated on your go): pull candidate population (M0a) + resolve 10Q label source (M0b). Exact commands to be written into this file before running.
- **A0** — description-quality census → `data/derived/fpds_description_census.parquet` + md. **Hard gate:** if median usable text is hopeless per stratum, stop and report.
- **A1** — labeled pairs (6 strata) → `data/derived/phase3_match_benchmark_pairs.parquet`, full provenance, reproducible builder. Reuse `resolve_entities`; N1 must confirm non-lineage *after* resolution (acquirer of the Phase II firm ≠ negative).
- **A2** — eval harness: TF-IDF/BM25 + string-match baselines **first**, ModernBERT-Embed scorer via `ModernBertClient`; per-stratum ROC-AUC / P@k / R@k, N3 discrimination, P3 recall@50. Single entry point; results parquet + figures (plain matplotlib — no `figure-style` skill present).
- **A3** — report + decision gate in `specs/phase3-match-benchmark/`; answers the 4 questions; states the ceiling caveat verbatim; descopes Product 2 to string-evidence-only if thresholds miss.
- **B** — three spec dirs (Products 1/2/4) in house style; Products 1 & 4 buildable independent of the A3 gate; Product 2 gated on A3. Include nullable `disposition` in lead schemas.

## 6. Scope guards
- **Reuse, don't rebuild:** `resolve_entities`, `ModernBertClient`, `detect_award_progressions`, transition-detection scorer, two-tier grammar. Product 1 ≈ a precision cut over existing same-firm progression + 10Q-absence; Product 2 ≈ new blocking/scoring around the existing embedder.
- **Language discipline:** `flags` / `leads` / `candidates` / `watchlist` only — never `violation` / `noncompliance`.
- **Non-goals:** no Product 3, no subcontract-displacement detection, no violation classifier, no training on violations, no changes to NIH/Form D/M&A pipelines beyond read-only reuse.

## 7. Paused here
Awaiting review of this survey/plan and a go decision on the M0 pulls (and the M0b 10Q-source question), before any large data pull or spec writing.

---

# Phase 0 Addendum — verified findings + scope decision (post scope-guard)

## Verified since survey
- **M0b RESOLVED — 10Q is reachable.** The FPDS ATOM feed exposes element 10Q as
  `<ns1:research>` (value `SR3`/`SR2`, `description="… PHASE III ACTION"`) and is
  queryable via `q=RESEARCH:SR3`. This is the structured, non-leaking label source
  for P1 positives. Confirmed the ~2k Phase III rows already on disk carry **no**
  `research` field, so the ATOM pull is genuinely required (not redundant).
- **Product 1 is already built.** `phase_iii_retrospective_candidates`
  (`packages/sbir-analytics/.../phase_iii_candidates/assets.py:545`) +
  `_is_phase_iii_already_coded` (`pairing.py:49`) already implement the
  status-denial filter (SBIR-lineage follow-on lacking Phase III coding). Product 1
  becomes a **tuning/labeling PR** (threshold + nullable `disposition` on
  `PhaseIIICandidate` + real contracts loader), not a new pipeline.
- **"22k already embedded" is false on disk.** Only the asset module
  (`assets/modernbert/embeddings.py`) exists; no materialized `.npy`/parquet.
  Embeddings must be regenerated as the first embedding step.

## Scope decision (adopted)
- **Benchmark trimmed 6→3 strata:** P1, N1 (+N3 if cheap). Drop P2, N2, and
  P3-recall@50 from the go/no-go gate. Size **~200 pairs/class** (separability
  test with bootstrap CI, not model training). Baselines = existing **Jaccard
  topical + ModernBERT cosine**; TF-IDF/BM25 cut from the gating path.
- **Gating question (unchanged):** can text separate P1 derivatives from N1 hard
  negatives in the well-described stratum? ROC-AUC(P1 vs N1) + N3 sibling check.
- **Products:** P1 = tuning PR; **write Product 2 and Product 4 specs** (P4 as a
  thin watchlist over coded Phase IIIs + P1 flags). One benchmark spec dir
  `specs/phase3-match-benchmark/`.
- **Sequence:** M0b (targeted FPDS-ATOM SR3 pull) **before** M0a (full population).
  M0a deferred behind a Product 2 go.

## Small M0b build (in progress this pass)
1. Pull ~200–300 SR3-coded records from FPDS ATOM → `data/raw/fpds/` (cached XML).
2. Parse → structured (PIID, UEI, requirement description, dates, PSC/NAICS, IDV).
3. Join to Phase II abstracts by resolved identity → **P1** pairs.
4. Assemble **N1** (same office / adjacent PSC / overlapping time, different lineage
   confirmed via `resolve_entities`) and **N3** (same-topic sibling) if cheap.
5. Embed via `ModernBertClient`; **P1-vs-N1 separability** (AUC + bootstrap CI),
   Jaccard baseline alongside. No large population pull.

---

# M0a — DoD-scoped hybrid contract pull (revised)

> **Status:** Spec revised; **execution gated on explicit go**. Supersedes the earlier per-UEI
> "frozen" draft. Reframed to DoD after measuring that SR3 coding is 82% DoD (civilian Phase III is
> structurally non-contract — see below). Recipient firm list already built (8,290 entities / 8,090
> UEIs, FY2016–2025).

## Why DoD-scoped
FPDS SR3 coded records by department: **DoD 66,450 (82%)**, NASA 6,130, DOE 120, NIH 80, **NSF 1**.
The civilian near-zeros are mostly **structural** — NIH/NSF/DOE SBIR runs on grants and their "Phase
III" is commercialization/sales, not a follow-on federal *contract* — so an "uncoded Phase III
contract" undercount is only well-defined for **DoD** (and partly NASA). **Product 1's undercount
ratio is therefore DoD-primary**; civilian Phase III is treated separately / out of scope for v1.

## Architecture — hybrid (not per-UEI, not pure bulk)
Pure bulk is impossible: USAspending exposes a `Research` column but **leaves it null even for
contracts whose description says "SBIR PHASE III"** (verified: 0/40). FPDS ATOM is the only working
10Q source, and its feed is **hard-capped at 10 records/page** (no `num/count/rows/size` override).
So:

1. **Coded set — FPDS ATOM** (`RESEARCH:SR3` + `ST3`, `DEPARTMENT_ID:9700`, `SIGNED_DATE:[2015/10/01,
   2025/09/30]`). In-window DoD coded ≈ **28,270 records** (SR3 25,050 + ST3 3,220) → **~2,830
   paginated requests**. Shard by fiscal year (10 shards) to parallelize + cache under
   `data/raw/fpds/`. Extract the compound key + `research` + parent-IDV per M0b's fixed parser.
2. **Recipient universe — USAspending bulk_download** (DoD prime contracts A/B/C/D, FY2016–2025) →
   one job → one CSV/ZIP. Columns: `contract_award_unique_key` (a precomputed unique award key —
   the audit's `award_key_series` prefers it, so no PIID compounding needed here), recipient UEI,
   description, obligations, `parent_award_id`, dates, competition. **Filter locally** to the 8,090
   recipient UEIs. ~1–5 requests.
3. **Flags = uncoded** = recipient contracts in the bulk universe **not** matched to a coded ATOM
   record (join on compound key / PIID + agency). Partition at **award grain** (coded if ANY
   transaction SR3/ST3 — the `pairing.py` fix).

## Request-count estimate
| Component | Requests | Note |
|---|---|---|
| Coded set (FPDS ATOM, DoD, in-window) | **~2,830** | hard 10/page cap; shard by FY; cacheable |
| Recipient universe (USAspending bulk) | ~1–5 | bulk file(s), filtered locally |
| **Total** | **~2,835** | vs ~20,000+ for the per-UEI draft (~7× fewer) |

~20–40 min wall-clock if the coded pull is sharded and polite. Bounded, cacheable, single-query —
**API-heavy but not a firm-by-firm hammer, and not a one-click bulk download.**

## Unchanged
Required fields, the award-grain coded rule + audit guards, the IDV-inheritance bucket (parent-coded
orders reported both ways; human reviewer decides), and the go/no-go: **freeze the validation
sampling frame only after** the pull + per-agency ratio + the audit before/after table.

## Coverage gaps (all bias the undercount DOWN)
DoD-scope excludes civilian contract-based Phase III (small — NASA ~6k SR3 could be added as a v1.1
extension); 210 name-only recipient firms (3%); unresolved successors; FPDS-only.

## M0a spike — FY2022 validation (done)
Ran `scripts/phase3_benchmark/m0a_spike_fy2022.py` (one FY shard) to de-risk before the full pull:
- **Coded pull:** FY2022 DoD SR3+ST3 = **3,144 records in 316 requests** (~2.7 min) → **~3,160
  requests** projected for all 10 FYs (matches the estimate).
- **Award-grain dedup confirmed essential:** 3,144 records → **1,389 distinct compound keys** (~55%
  are mod/transaction dups). The `award_key_series` collapse is load-bearing, not cosmetic.
- **USAspending join validated:** 24/25 sampled coded records found in USAspending on
  `order_piid == "Award ID"`. Set-difference for uncoded flags is feasible.
- **Refinement for the full run:** join on the FULL compound key (order PIID + parent PIID + agency),
  not order-PIID alone — a loose join biases toward false uncoded flags. The ~1/25 miss is a lower
  bound from the spike's per-UEI presence check, not the production compound join.

## M0a — EXECUTED (full pull, FY2016–2025 DoD)
Ran the hybrid: FPDS-ATOM coded pull + USAspending description ground-truth + compound-key join.
- **Coded Phase III universe:** 28,264 SR3/ST3 transactions → **6,351 distinct coded awards** to
  **1,487 DoD firms** (2,835 requests, ~45 min, cached). ~78% of transactions were mod/txn dups —
  award-grain dedup essential.
- **Undercount (first real number):** of **962** DoD contracts described "SBIR PHASE III", **141
  (14.7%) lack the SR3/ST3 code** (strict == loose compound-key join). By sub-agency: Navy 19%,
  DCMA 19%, Army 15%, Air Force 13%; MDA/DHA/DTRA 0%.
- **A lower bound:** description-matching finds only ~12% of coded Phase III (792 of 6,351 coded
  awards say "PHASE III"), so 14.7% counts only the *obvious* miscoded cases. The dark undercount
  (Phase III with neither the phrase nor the code) needs Product 1 inferential flags over the full
  8,090-firm universe — still deferred.
- Outputs (gitignored): `m0a_coded_dod.parquet`, `m0a_desc_phase3_dod.parquet`,
  **`m0a_status_denial_flags.parquet`** (the 141 uncoded flags, with nullable `disposition`),
  `m0a_undercount_summary.json`. Scripts: `scripts/phase3_benchmark/m0a_*.py`.
- **Data note:** FY2025 coded awards (1,655) run high vs the trend (FY2024 = 907) — verify before
  citing per-FY; does not affect the description-set undercount.
