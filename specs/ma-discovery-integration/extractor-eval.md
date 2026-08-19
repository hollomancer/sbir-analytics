# M&A snippet extractor eval (exploratory, non-citable)

**Target epistemic tier:** `exploratory`  
**Status:** comparison note, not a live-web recall benchmark. No live LLM or
search APIs were called for this write-up.

This note compares two snippet verifiers for Form-D-missing M&A pair
confirmation. The job is a structured verdict from already-retrieved text:
`{confirmed, matched_company, matched_acquirer, acquisition_date, value_usd,
citation_url}`. The orchestrator still calls `verify_acquisition` and is
unchanged.

## What was compared

| Extractor | How it decides | Date / value | Cost |
|---|---|---|---|
| **Keyword** (`KeywordExtractor` over `verify_acquisition`) | Both names as raw substrings plus one of `{acquired, acquisition, bought, merger, merged, purchase}` | Never fills. Confirmed rows keep `date="Unknown"` in the heuristic and `None` on the structured verdict | Zero |
| **Structured LLM prompt** (`LlmExtractor`) | Injected chat callable; prompt asks for JSON matching the design schema and forbids talks-only / invented fields | Fills only when the model returns ISO date / numeric USD | Per-snippet token cost |

Models *considered*, not bake-off winners:

- Existing repo default: `OpenAIClient` / `gpt-4.1-mini` (`sbir_etl.enrichers.openai_client`).
- Design hint (`design.md`): cheap model for obvious snippets, stronger model
  for ambiguous ones (Claude Haiku / Sonnet in the draft). That split is
  unmeasured. This PR does not add an Anthropic client and does not rank
  models.

The committed eval is **keyword vs the JSON prompt + parse path**. LLM unit
tests inject a mock that returns JSON. The notebook default path uses the same
fixtures plus a gold-label replay (not a model). A live OpenAI cell exists
behind `MA_DISCOVERY_LIVE_LLM=1` and `OPENAI_API_KEY`; it is off in CI.

## What the frozen fixtures show (non-citable)

Twelve synthetic snippets in `tests/fixtures/ma_discovery/snippets.json`.
Keyword behavior on that set, computed by the harness, not a live result:

- Confirms slam-dunks that contain both names and a verb.
- Letter-case differences still match (`str.lower()`).
- **False negatives:** legal-suffix mismatch (`Quanta Materials Inc` vs
  snippet `Quanta Materials`).
- **False positives:** talks-only text that still contains `merger` or
  `acquisition`. `in talks to acquire` happens to miss the verb list.
- **Fill rates:** date and value are always empty.

Those failure modes are why a structured LLM prompt is *interesting*. They are
not a measured ≥X% on web results.

## What a live bake-off still needs

- An API-spend approver and keys (`OPENAI_API_KEY`; Anthropic only if the
  cheap/strong split is actually tried).
- A labeled sample drawn from real Form-D-missing rows (search snippets from
  Tavily/Brave, not these synthetic sentences).
- Dual annotation of `confirmed` plus optional date/value, with talks-only
  called out as a separate class.
- A pre-declared split: cheap default vs escalate-on-ambiguous. Do not pick
  the winner after seeing the scores.
- Cost per snippet against the design cap (`--max-candidates 200`, ~$5/run).

Until that run exists, do not quote fixture precision/recall as a finding and
do not mark F1/F2 M&A inventory items computable from this work.

## Recommendation for the next PR

Keep `KeywordExtractor` / `verify_acquisition` as the orchestrator default.
If the next PR wires `LlmExtractor` at all, make it opt-in (`--extractor llm`
or `OPENAI_API_KEY` present) and use the existing `gpt-4.1-mini` client for
every snippet until a live labeled sample justifies the design's cheap/strong
split. Do not delete the keyword heuristic and do not treat this eval as a
cutover warrant.

C3 collision, `MAEvent.confidence` rewrite, and capital-events join stay out
of scope.
