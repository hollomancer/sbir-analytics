# T6 — Triangulated Scoring Design (frozen ranker vs independent ground truth)

Step-0 analysis forced a two-path design (user chose "both, triangulated"):
the ground truth is **contract-grained**, the ranker is **notice-grained**, and only
22/274 GT firms have a notice pool (20 Navy). So:

## Path A — Contract-ranking (scale headline, balanced/non-Navy)
- **Scorable set:** the **56** GT transition contracts with *substantive* descriptions
  in `phase3_universe.jsonl` (DHA 23 · DLA 18 · MDA 12 · DTRA 3). Optionally include
  the 46 `thin` ones as a sensitivity row. All independent-provenance, `stratum=hard`.
- **Query text:** the firm's pooled SBIR **Phase I/II abstracts** from
  `award_data.csv` (`Abstract` col; 87% populated), via `resolve_firm_awards`. Dedupe,
  cap length. Deterministic.
- **Candidate pool:** true transition contract + **K=9 decoys** sampled (fixed seed)
  from `phase3_universe` Phase III contracts with substantive descriptions, **same
  awarding agency**, excluding the firm's own. Report a harder variant where decoys =
  the firm's *own* other Phase III contracts when it has ≥2.
- **Score:** `score_pairs_with_fusion` (frozen `fusion_coefficients.json`). Feature
  order `[tfidf_word, tfidf_char, after_first, id_cited, naics_len, notice_type]`:
  tfidf from (abstract × contract-description, identity-scrubbed via `_scrub_identity`);
  `after_first=1` (transition postdates SBIR); `id_cited=0` (leakage-scrubbed, coef 0);
  `naics_len` from contract NAICS; `notice_type` ordinal from Contract Award Type.
- **Metrics:** precision@1, precision@3, MRR; **bootstrap 95% CIs**; split by
  **agency × provenance × stratum** and by a coarse **tech_domain** (medical/materials/
  logistics/sensing). Compare to proxy-label 0.681@1.

## Path B — Notice-retrieval (faithful anchor, Navy-limited)
- The **22** GT firms present in `phase3_notice_corpus.parquet` (≥2 candidates).
  Use the corpus's own (query_abstract × notice_text, label) structure; frozen fusion;
  precision@1/@3 per firm. Report explicitly as **~90% Navy, small-N** — an anchor, not
  a headline.

## The triangulation
Report A and B side by side. **The A↔B gap is the contract→notice transfer caveat,
measured.** State plainly whether either clears the bar to let fusion *order* the packet
(vs deadline-primary), and that neither validates forward/open-solicitation use.

## Deliverables
- `scripts/phase3_groundtruth/score_t6.py` (+ unit test on a tiny fixture).
- `specs/phase3-transition-groundtruth/T6_RESULTS.md` (tables + CIs + the go/no-go).
- Log every dropped/unscorable case with a reason — no silent truncation.
