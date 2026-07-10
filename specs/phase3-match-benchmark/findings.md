# Phase III Match-Quality Benchmark — Findings (A3 decision gate)

> **Status:** Result on a small labeled sample (M0b) with **true same-funding-office hard
> negatives** and a **realistic-pool precision@k**. Full A0 census + M0a (whole contract
> population) still pending; conclusions are directional but decision-grade.
> Supports inventory questions **B3** (Phase III undercount / transition detection) and **A2**
> (DIB integration via FPDS) in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** Can text similarity distinguish true SBIR Phase III derivative pairs
from plausible non-derivative pairs, given real FPDS description quality? Gates **Product 2**.
**Complexity tier:** Relational → Inferential (Tier 2–3)

## Sample

- **Positives (P1):** 401 same-firm pairs = (firm's most-recent-prior Phase II abstract) × (its
  FPDS record **coded `research=SR3`**, Element 10Q, from the FPDS ATOM feed). Labels come from the
  **structured 10Q code, not description keywords** — no label leakage. 190 firms.
- **Hard negatives (N1):** 357 pairs = firm B's Phase III description × a **different firm A's**
  prior Phase II abstract, where **A is another SR3 awardee in the SAME FPDS contracting office**
  (`contractingOfficeID`) — a real competitor in that office, not merely the same agency. (44 P1
  sit in single-firm offices and get no same-office negative.)
- Source: `data/derived/fpds_10q_sr3.parquet` (600 SR3 records; 100% UEI; **median description 47
  chars**; office 100% filled) joined to Phase II abstracts in `data/raw/sbir/award_data.csv`.

## Result — the four benchmark questions

**1. Is Product 2 viable as a lead ranker?** *Weak — no clear go.* Against true same-office
negatives, text barely separates derivative from non-derivative pairs, and the embedder does **not**
beat the lexical baseline.

P1-vs-N1 ROC-AUC (n = 357 vs 357):

| FPDS description length | n | Lexical (Jaccard) | ModernBERT-Embed |
|---|---|---|---|
| **Overall** | 357 | 0.560 (CI 0.527–0.592) | **0.564 (CI 0.524–0.608)** |
| Q1 ≤25 chars | 94 | 0.508 | 0.507 |
| Q2 26–42 | 91 | 0.570 | 0.572 |
| Q3 43–85 | 83 | 0.540 | 0.634 |
| Q4 ≥86 chars | 89 | 0.646 | 0.571 |

Both methods hover near chance (0.56 overall). The clean "well-described stratum wins" pattern seen
in an earlier pass **did not survive** hardening N1 from same-agency to same-office and fixing a
join bug (see Methodology corrections) — the quartile pattern is now flat/noisy, and the embedder's
Q4 edge disappears.

**2. Retrieval precision@k over realistic same-office pools** (222 queries; median pool **26
records / 22 firms**): can we rank a firm's true Phase III at the top among the same office's
Phase III awards?

| | P@1 | hit@5 | MRR |
|---|---|---|---|
| Random baseline | 0.113 | 0.423 | — |
| **ModernBERT (all)** | **0.225** | **0.527** | 0.363 |
| ModernBERT (well-described, gold ≥100 chars, n=59) | 0.288 | 0.593 | 0.433 |

The embedder beats random ~**2× on P@1** but only ~**1.2× by hit@5** — real but weak signal. Top-1
is wrong ~77% of the time (~71% even in the well-described subset). And this is an **optimistic
upper bound**: the pool is only SR3-*coded* records; the real pool (M0a: all contracts, coded and
uncoded, in the office) is 10–100× larger and harder, which will push precision@k lower.

**3. Did the lexical baseline match the embeddings?** Yes — 0.560 vs 0.564 overall; indistinguishable
within CI. The embedder does not justify its cost on separability. It adds value only in the
retrieval framing (2× random P@1), and even there marginally.

**4. Ceiling caveat (verbatim, per the task):**
> P1/P2 positives are agency-coded awards — the sample where agencies did the paperwork and wrote
> the better descriptions. True bypass cases live disproportionately where coding and text quality
> are worst. All benchmark results are an **upper bound** on real-world Product 2 performance; only
> the P3 gold set escapes this bias, and it is tiny.

## Recommendation — descope Product 2 (do not build the embedding ranker yet)

The task's provisional go anchors were precision@10 ≥ 0.30 vs hard negatives in the well-described
stratum **and** meaningful separability. On true same-office negatives with the bug fixed, the
embedder **misses on both**: separability ≈ chance and no better than lexical; realistic retrieval
is only ~2× random. Therefore:

- **Descope Product 2 to Tier-1 string-evidence-only** (product/system-name and explicit
  award-reference matching) as the primary lead source. The two-tier grammar stands, but Tier-2
  (embedding) is demoted to a **weak secondary signal feeding a human-review queue**, never a
  standalone ranker — and only on well-described candidates.
- **Reallocate to Products 1 and 4**, which do not depend on this gate.
- **Reopen the Product 2 embedding ranker only after M0a**, when precision@k can be measured over
  the real (all-contract) pool. Expect it to be lower than the numbers here.

## Methodology corrections (auditability)
- **N1 hardened.** Earlier draft used same-*agency* + time negatives (soft); this version uses
  same-*contracting-office* different-firm negatives. AUC fell (~0.60 → 0.56; Q4 0.76 → ~0.57–0.65),
  confirming the soft negatives were optimistic.
- **Join-key bug fixed.** P1↔N1 were joined on FPDS `PIID`, which is a non-unique order/mod number
  ("0001"), collapsing strata. Replaced with a unique `pair_id`. This removed a spurious
  well-described-stratum advantage.
- **Results are unaffected by the FPDS PIID/parser issue** (surfaced in the Product 1 audit, where
  the ATOM parser initially dropped the parent-IDV PIID). The benchmark keys every pair on the unique
  `pair_id` and scores on descriptions + recipient UEI + `contractingOfficeID` — never on PIID — so
  the near-chance separability and weak precision@k conclusions stand. The one refinement the parser
  fix enables: dedup the 600 SR3 rows to 485 award-grade keys (the rest are mod dups), which cannot
  strengthen a near-chance result.

## Limitations (direction of bias)
- **Pool = SR3-coded only** (M0a pending) → precision@k is an upper bound; real pool is larger/harder.
- **Balanced-pair AUC** still not a retrieval metric; the precision@k section is the realistic view.
- **Successor-in-interest not resolved** — N1 uses UEI≠ + name≠; true acquirer-of-Phase-II-firm
  resolution doesn't exist in the repo, so a few N1 could be mislabeled acquisitions (inflates AUC).
- **10Q noise** — some SR3 records are mis-coded (e.g. a library BPA); small positive-label noise.
- **Single code (SR3)**; STTR ST3 and agency mix not yet stratified.

## Reproduce
```
python scripts/phase3_benchmark/pull_fpds_10q.py SR3 --pages 60   # -> data/derived/fpds_10q_sr3.parquet
python scripts/phase3_benchmark/build_pairs_and_score.py          # pairs + lexical AUC (same-office N1)
python scripts/phase3_benchmark/embed_and_score.py                # ModernBERT AUC + precision@k
```
