# M&A discovery recall — held-out 1501 protocol

Epistemic tier: exploratory until the gates below pass and evidence-auditor
does not BLOCK a rank flip. This note is the measured protocol for pairs
**1501–2500**. It does not rewrite [design.md](design.md) or
[confirmatory-design.md](confirmatory-design.md).

The 200-pair envelope in design.md remains a failed preregistered validation
(recall 9<10). The 501–1500 confirmatory freeze is an exploratory record;
evidence-auditor BLOCKED promoting it because freeze-before-run was not
shown. Do not evaluate a rewritten gate on either freeze.

Hash this file and [held-out-1501.yaml](held-out-1501.yaml) into
`study.yaml` **before** any Brave or LLM call on pairs 1501+.

Intended study rank if the gates pass and evidence-auditor does not BLOCK:
`validated`. Materialization stays closed. Inventory F2/A4 is not edited.
`citable` is out of scope.

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
- this cut overlaps pairs 1–1500 (pilot or confirmatory).

## Cut

- Order: `query_rows_from_events` on the pinned events file (file order).
- Skip the first **1,500** unique pairs (pilot 1–500 and confirmatory 501–1500).
- Keep the next **1,000** unique pairs (pairs 1501–2500).
- One query template:
  `"<RECIPIENT_V1 company>" acquired by "<RECIPIENT_V1 acquirer>" press release`.
  Not the four templates in `generate_queries`.
- Finish all 1,000 even if the recall floor is met early. Do not enlarge
  this cut after seeing the outcome.

Events pin: `data/sbir_ma_events.jsonl` sha256
`6ffc8481a240b2ee9bd9fdef806395d3f62e9d1f3ba12a68490d28fb53a1cf49`
(n=4306). Output directory:
`data/processed/ma_discovery_heldout_1501` (gitignored).

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

## Capture

Live Brave or `--capture-llm` must use
`--protocol studies/ma-discovery-recall/held-out-1501.yaml`. The CLI refuses
that call unless this note and the YAML are in `HEAD` and pinned in
`study.yaml` `frozen_artifacts`, the flags match the YAML, and
`--fail-on-gate` is on (implied by `--protocol`).

## Rerun

- Search backend: `snippets` over the frozen JSONL.
- Confirmer: freeze-only LLM extractor. No API key. Missing freeze row is
  unconfirmed and must not call the network.
- SHA mismatch on events, snippets, or LLM JSONL vs the held-out run
  manifest: non-zero exit.
- Kill-gates are written in the same process as the summary. Failed recall
  or completed-precision gate: non-zero exit. Incomplete labels keep
  `accepted: false` and are not a recall failure.

## Capture-code provenance

Commit `5fdccb7c` changed the capture path after `0023e204` hashed this note.
No Brave call and no LLM call had touched pairs 1501+ at that time.
Freeze-before-run holds for this cut.

The change counts network faults. It does not score them as evidence.
Before it, a failed search recorded an empty hit. An LLM timeout recorded an
unconfirmed verdict and wrote no freeze row. Both look identical to a true
negative, in the summary and in the replay. Either one lowers recall with no
trace. `sample_run_summary.json` now reports `search_failure_n`,
`llm_timeout_n`, and `kill_gate.fully_measured`.

### Validity precondition

A fault count above zero voids the run.

This is not a fourth gate. It cannot promote a run. It cannot excuse a miss.
It can only block.

Apply these rules:

- Treat a run with any fault as void.
- Do not read the discovery rows of a void run.
- Rerun the same 1,000 pairs.
- Do not enlarge the cut after a void run.
- Do not move to pairs 2501+ after a void run.
- Treat a fully measured run that misses recall as a miss. Do not rerun it.

A void run makes live calls on pairs 1501+. Its numbers are not measured and
must not be read. Blindness holds only if nobody reads them before the rerun.

## Out of scope

Inventory Status edits (`docs/research-questions.md`). `capital_events` /
Neo4j writes. Citable claims. Foreign-acquirer findings. Exit rates.
Changing C3’s ±30-day window (strict count is the filter). Restating gates
after seeing pairs 1–1500.
