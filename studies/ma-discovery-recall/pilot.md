# M&A discovery recall — pilot record

Epistemic tier: exploratory. Non-citable. This is not a passed validation.

The 200- and 500-pair Brave + Grok runs in 2026-09 informed the confirmatory
design. They are **burned** for confirmatory kill-gates. Do not evaluate a
rewritten gate on this freeze. Evidence-auditor 2026-09-02 **BLOCK**ed
`exploratory` → `validated` (see [amendments.md](amendments.md)).

Hashes and row counts: [run-manifest.json](run-manifest.json). Human labels:
[labels.jsonl](labels.jsonl). Frozen method that the first batch failed:
[design.md](design.md). Confirmatory protocol (hash before held-out capture):
[confirmatory-design.md](confirmatory-design.md).

## Population and method actually used

- Events: `data/sbir_ma_events.jsonl` sha256 `6ffc8481…`, 4,306 rows.
- Form-D-missing pairs with an acquirer: **3,754**.
- Search: Brave Web Search, **one** query template per pair
  (`"company" acquired by "acquirer" press release`), not the four templates
  in `generate_queries`.
- Confirmer: OpenRouter `x-ai/grok-4.6`. Stop at **first confirm**, even if
  the snippet had no date (confidence stays `low`).
- Identity: `CompanyNameProfile.RECIPIENT_V1`.

## Results

| Item | Result |
|---|---|
| 200-pair first batch | 9 C3 medium/high insert/promote — **failed** frozen recall ≥10 |
| 500-pair enlarge | After that miss was known. 17 C3 medium/high |
| Of those 17 | **10 already EFTS-medium** at a later date (C3 inserts a second row outside ±30 days) |
| Previously-low among 17 | 7: 5 labeled true, 1 false (GM/Opel 1929), 1 ambiguous (Cellceutix; snippet dropped on C3 join) |
| Strict yield | ~1% dated new-to-medium/high per pair (5 true / 500) |
| Precision | 16 medium labeled: 14 true / 1 false / 1 ambiguous; FP = 1/15 = 6.7% |
| Cost | Brave $5/1k list + OpenRouter $2/$6 per 1M; ~$0.018/pair; $8.89 on 500 pairs (over frozen $5) |

## Mechanism

- Weak recall (any C3 mutation without `discovery_confirmed`) is easy. Strict
  recall (detector would not already have called the pair medium/high) is
  scarce. C3’s ±30-day window is why the two counts diverge.
- First-confirm-wins is the main suppressor of medium rows: undated confirms
  never look at later dated hits.
- Keyword confirmation cannot emit medium/high. Grok reasoning tokens, not
  Brave, dominate cost.
- Name match alone accepted GM/Opel 1929. Review caught it; the extractor
  will not.
- `--max-cost-usd` was specified in the frozen note and never implemented.
  Kill-gate fields were patched into `sample_run_summary.json` after the
  process exited 0.

## What this authorizes

Nothing numerical may leave the repository. Inventory F2/A4 are not updated.
The confirmatory attempt uses a **held-out** 1,000 pairs (501–1500), strict
recall, stop-until-dated, and a design hashed **before** that capture.
