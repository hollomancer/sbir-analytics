# M&A discovery recall — confirmatory design

Epistemic tier: exploratory until the gates below pass and evidence-auditor
does not BLOCK a rank flip. This note is the measured protocol for the
**held-out** run. It does not rewrite [design.md](design.md). The 200- and
500-pair work is a [pilot](pilot.md) only.

Hash this file into `study.yaml` **before** any Brave or LLM call on pairs
501–1500.

## Estimand (strict)

Among Form-D-missing rows in the pinned `data/sbir_ma_events.jsonl` cut that
name an acquirer **and whose existing event is not already**
`confidence in {medium, high}`, count distinct `(company, acquirer)` pairs
after `CompanyNameProfile.RECIPIENT_V1` that a web-search snippet extractor
confirms at medium or high confidence and that C3 inserts or promotes, as of
the run as-of date.

Non-detection is not proof of no acquisition. The count is not an SBIR exit
rate, not a foreign-acquirer finding, and not a section-level answer to
inventory F2 or A4.

The estimate is wrong if any of the following hold:

- the snippet cut or LLM freeze is not the declared input;
- an LLM call is live on the rerun path;
- pair identity uses any normalizer other than `RECIPIENT_V1`;
- C3 overwrites a Form D acquirer;
- fixture `mock` hits are mixed into the measured run;
- confirmatory pairs overlap the pilot first 500.

## Cut

- Order: `query_rows_from_events` on the pinned events file (file order).
- Skip the first **500** unique pairs (pilot).
- Keep the next **1,000** unique pairs (pairs 501–1500).
- One query template:
  `"<RECIPIENT_V1 company>" acquired by "<RECIPIENT_V1 acquirer>" press release`.
  Not the four templates in `generate_queries`.
- Finish all 1,000 even if the recall floor is met early. Do not enlarge
  this cut after seeing the outcome.

## Stop rule

For each pair, send search hits to the extractor until a **dated** confirm
(medium or high) or hits are exhausted. Skip hits with no snippet and no URL.
If every confirming hit is undated, keep one low-confidence confirm (first
undated confirm). This differs from the pilot’s first-confirm-wins rule.

## Gates

All three; no extra conjuncts.

1. **Recall.** ≥10 distinct **strict** medium/high C3 insert-or-promote pairs
   (existing event not already medium/high).
2. **Precision.** Label all medium rows if fewer than 20. Human
   `true` / `false` / `ambiguous` against the stored snippet and URL.
   FP = `false / (true + false)` ≤ 0.25. Ambiguous excluded from the
   denominator and reported.
3. **Cost.** Search + LLM ≤ $0.10 per candidate pair at list Brave Search
   ($5/1k) and OpenRouter/xAI grok-4.6 ($2/1M input, $6/1M output). Monthly
   vendor credits are not subtracted. No $5 absolute cap. No
   `--max-candidates 200`.

A run that fails any of the three does not promote. Do not restate the
envelope after a miss.

## Rerun

- Search backend: `snippets` over the frozen JSONL.
- Confirmer: freeze-only LLM extractor. No API key. Missing freeze row is
  unconfirmed and must not call the network.
- SHA mismatch on events, snippets, or LLM JSONL vs the confirmatory run
  manifest: non-zero exit.
- Kill-gates are written in the same process as the summary. Failed recall
  gate: non-zero exit.

## Out of scope

Inventory Status edits (`docs/research-questions.md`). `capital_events` /
Neo4j writes. Citable claims. Foreign-acquirer findings. Exit rates.
Changing C3’s ±30-day window (strict count is the filter).
