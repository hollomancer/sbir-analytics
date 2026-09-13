# M&A discovery recall — amendments

This note records measured-cut provenance for `studies/ma-discovery-recall`.
It does **not** replace the estimand, identity policy, C3 join, confidence
table, or the preregistered validation design in [design.md](design.md).
Those remain the frozen method at the design.md content hash in `study.yaml`.

Evidence-auditor 2026-09-02: **BLOCK** on `exploratory` → `validated`.
A post-run restatement of the cost/candidate envelope after the 200-pair
batch missed the recall floor is not a preregistered amendment.

## A1 — Measured 500-pair cut (exploratory record, 2026-09-01)

The frozen validation design still requires all three: recall ≥10 medium/high
C3 insert/promote pairs; medium-row FP ≤0.25 on ≤20 labels; search+LLM
≤$0.10/pair **and** `--max-candidates 200` **and** `--max-cost-usd 5`.
“A run that fails any of the three does not promote.”

What was actually run:

1. **200-pair first batch** (one query template per pair, Brave snippets,
   Grok via OpenRouter `x-ai/grok-4.6`): **9** C3 insert/promote medium/high
   pairs — recall floor **failed**.
2. **Enlarge to 500 pairs** on the same events file, same single template,
   appending to the snippet freeze, after that failure was known. That cut
   is recorded here as an exploratory measurement, not as a passed gate.

Observed on the 500-pair freeze (see `run-manifest.json`, `labels.jsonl`):

- 500 pairs, 1 query each; 745 frozen LLM replies.
- C3: 16 medium/high inserts + 1 medium promote = **17** pairs that did not
  already carry `discovery_confirmed`. Ten of those 17 already existed as
  EFTS medium at a later date (C3 inserts a second row outside ±30 days).
  One insert (GM/Opel 1929) is labeled **false**. One promote
  (Cellceutix/PolyMedix) is labeled **ambiguous** (snippet dropped on join).
- Medium queue: 16 rows, all labeled — **14 true / 1 false / 1 ambiguous**.
  FP = 1/15 = 6.7%.
- List Brave ($5/1k) + billed OpenRouter grok-4.6 ($2/$6 per 1M): about
  **$0.0178/pair**, **$8.89** for the 500-pair run (over the frozen $5 bound).

The frozen method also generates **four** query templates; this cut used one.

## A2 — Private snippet cut

Brave SERP snippets and Grok raw replies live under gitignored
`data/processed/ma_discovery/`. They are not redistributed. Content hashes
are in `run-manifest.json`. A machine without those files cannot rerun.

Inventory F2/A4 is not updated. Materialization into `capital_events` /
Neo4j is not authorized. `evidence_status` stays **exploratory**.

Narrative of this pilot: [pilot.md](pilot.md). Held-out confirmatory protocol
(hash before capture): [confirmatory-design.md](confirmatory-design.md).

## A3 — Held-out confirmatory cut (exploratory record, 2026-09-03)

`confirmatory-design.md` was recorded as the confirmatory protocol for pairs
501–1500. The run used one query template, stop-until-dated, and strict
recall. Evidence-auditor 2026-09-07: freeze-before-run was **not** shown
for that file (first git appearance is the same commit as the confirmatory
miss; Brave snippets predate it). See A5.

Observed (see `confirmatory-run-manifest.json`):

- 1,000 pairs; 2,369 frozen Brave snippets; 1,831 LLM freeze rows.
- Strict medium/high C3 insert-or-promote: **8** (floor ≥10 **failed**).
- Cost ~$0.0126/pair (under $0.10). Precision labels were not started
  because recall already failed.
- LLM freeze is incomplete: 855 empty `raw_response` rows from index 976,
  covering 241 pairs with no non-empty reply. OpenRouter 402 cut the tail.
  Completing those pairs would be a live LLM call on the already-frozen
  snippets, not a new search cut and not a restated envelope.

A run that fails any confirmatory gate does not promote. Do not evaluate a
rewritten gate on this freeze. `evidence_status` stays **exploratory**.

## A4 — Confirmatory tail completed (exploratory record, 2026-09-07)

The held-out freeze was resumed on the same Brave snippets, same hashed
`confirmatory-design.md`, stop-until-dated, strict recall. Empty freeze
rows were retried; 402s were not written as freeze rows. LLM chats used
`max_tokens=2048`.

Observed (see `confirmatory-run-manifest.json`):

- Strict medium/high C3 insert-or-promote: **13** (floor ≥10 **met**).
- 140 discovered rows (84 low, 52 medium, 4 high). C3: 138 inserts, 2
  promotes.
- Compacted LLM freeze: 1,831 unique `(company, acquirer, source_url)`
  keys, 1,753 filled. 78 empty URL keys remain; every pair has a filled
  reply on another URL.
- Cost ~$0.0186/pair (Brave $5 + LLM ~$13.64, under $0.10).
- Precision: 20 medium rows labeled **19 true / 0 false / 1 ambiguous**.
  FP = 0/19 = 0 (cap 0.25). Ambiguous is Synlogic/Mirna: snippet is
  contact boilerplate, claim is in the URL. Labels:
  `confirmatory-labels.jsonl`.

All three confirmatory gates are met as an exploratory record.
`evidence_status` stays **exploratory**. Do not edit
`docs/research-questions.md`. See A5 for the remaining hashed-cut path.

## A5 — Held-out 1501 protocol (hash before capture)

Evidence-auditor 2026-09-07: **BLOCK** on promoting the confirmatory
501–1500 freeze. `confirmatory-design.md` first appears in git in the
same commit as the confirmatory miss (`c94967b5`, 2026-09-06). The Brave
snippet freeze mtime is 2026-09-02. Completing empty LLM rows on that
freeze is not freeze-before-run and does not enlarge a hashed cut.

The 200-pair envelope in [design.md](design.md) remains a failed
preregistered validation (recall 9<10). Do not rewrite it. Do not
evaluate a rewritten gate on pairs 1–1500.

[held-out-1501.md](held-out-1501.md) is the measured protocol for pairs
1501–2500 (skip 1,500, keep 1,000). Hash this note and
`held-out-1501.yaml` into `study.yaml` **before** any Brave or LLM call
on that cut. Same three gates as confirmatory-design: strict recall ≥10,
medium-row FP ≤0.25, ≤$0.10/pair. Intended rank if gates pass and
evidence-auditor does not BLOCK: study `validated`. Materialization stays
closed. Inventory F2/A4 is not edited. `citable` is out of scope.

Live capture is refused unless `--protocol` is hashed in HEAD. This
amendment is Commit A of that cut: protocol only, zero results.

## Amendment — held-out 1501 recorded as non-confirmatory (2026-09-13)

**Authority:** evidence audit, 2026-09-13, on the single question of whether
`validation_result.confirmatory` could be `true` for the held-out 1501-2500 run.

**Verdict: it cannot, and the reason is dispositive rather than a judgement.**
`study.yaml` pins `held-out-1501.md` at `e7090020...`. Those bytes first exist
in git at `9bcb6dc9`, 2026-09-09 07:30:41 -0400. The replay's own
`replay_result.as_of_utc` is 2026-09-09T01:25:00Z, which is 2026-09-08 21:25
EDT, and the capture ran 09-07 11:58 to 09-08 02:15. The pinned design postdates
the run it is supposed to have preregistered by about ten hours, and the capture
by about two days. `confirmatory` asserts the design bytes were fixed in git
before the evaluated run; they were not.

The schema does not catch this. `StudyManifest` only checks that
`design_sha256` matches the pinned `frozen_artifacts` entry, which is exactly
the check its own docstring tells the auditor not to rely on.

**What holds, and is worth stating.** `held-out-1501.yaml` is byte-identical
from `0023e204` to `main`: `recall_floor: 10`, `skip_pairs: 1500`,
`max_candidates: 1000`, `stop_when: dated_confirm`, `strict_recall: true`. The
diff on `held-out-1501.md` from `0023e204` forward is a pure insertion, 89 added
lines with zero deletions or modifications. The estimand, the cut, the stop rule
and the floor of 10 were fixed before capture and were not moved to fit a 4.
Reporting the miss is honest and useful; it is the *confirmatory* label that
fails.

**Falling back to the pre-capture hash would be worse, not better.** Pinning
`b983466f...` so the design predates the run would assert confirmation against a
design the execution violated: that version authorizes no retry class, and the
run re-queried 476 rows under one.

**Recorded end state.** `evidence_status` stays `exploratory`.
`validation_result` carries the numbers with `confirmatory: false` and
`threshold_met: false`, and five `post_hoc_analyses` entries. A full design and
result block validates at `exploratory`, so no recorded detail is lost by
declining the promotion.

### Merge-strategy lesson, recorded because it will recur

`0023e204` — "hash held-out-1501 protocol before capture" — is not reachable
from `main`. PR #699 was squash-merged, so `0023e204`, `1fc7d936`, `bb7c2ac3`,
`82b7a210` and `9bcb6dc9` all collapsed into `fff0cef3`, and the freeze ordering
is legible only in the deleted branch's history. That is a real provenance
problem on its own merits, and it is *not* what blocked this cut.

Any future protocol must be hashed in a commit that survives the merge strategy,
and its digest pinned in `study.yaml` in the same PR, before capture, so the
ordering reads from `main` alone.

### What would have to be true for a later cut to be confirmatory

1. The design hash pinned in `study.yaml` on a commit reachable from `main`.
2. Every fault marker and retry class declared in that design before capture.
3. Capture performed by committed code, with its commit SHA recorded in the run
   manifest.
4. The evaluated design hash unchanged between freeze and replay.

None of the four hold for held-out 1501-2500.
