# M&A discovery search backends (exploratory, non-citable)

**Target epistemic tier:** `exploratory`  
**Status:** comparison note, not a recall benchmark. No live queries were run.

This note picks a default `SearchTool` backend for Form-D-missing M&A pair
confirmation. The job is **snippet + URL**, not a full-page crawl: the keyword
verifier (and the later LLM extractor) only need enough text to see both firm
names and an acquisition verb. Cost is bounded by the design cap of ~$5/run at
`--max-candidates 200`. Four query templates per candidate is 800 searches if
the orchestrator does not yet short-circuit a pair after the first hit.

## Comparison (public 2026 pricing, not measured quality)

| Backend | What you get | Cost at 800 queries | Key setup | Index |
|---|---|---|---|---|
| **Tavily** | Extracted `content` snippets built for agent/LLM use; POST `/search` | Credit-based; basic search is 1 credit, so one 200-candidate run is hundreds of credits — stay on `search_depth=basic` and skip `include_answer` to keep a run inside the $5 cap | One API key | Specialized search-for-agents layer, not an independent web index |
| **Brave Search API** | SERP `description` (+ optional extra snippets); GET `/res/v1/web/search` | ~$5/1k plus a monthly credit, so ~$4 for 800 queries before credits | One API key | Independent index (not Google/Bing) |
| **Serper** | Google SERP titles/snippets | Cheap Google-wrapper pricing; well under $5 | One API key | Google, via a third party |
| **Bing / Azure** | Bing web results | Azure-metered; cost is secondary to setup | Azure account, resource, key vault | Microsoft |

Snippet quality for *this* pipeline is the deciding axis. Tavily returns
paragraph-length `content` that can contain both names and a verb. Brave,
Serper, and Bing return short SERP descriptions that often drop one of the two
firm names — enough for a URL, weaker for the keyword verifier and the planned
LLM extractor. Independence of index favors Brave; Google coverage via Serper
is likely strongest for press-wires, but both still hand us SERP blurbs rather
than extracted body text. Bing loses on setup friction.

A 200-candidate run is affordable on Tavily basic, Brave, or Serper. Bing is
not materially cheaper once Azure overhead is counted.

## Recommendation

**Default production backend: Tavily.** It matches the use case (snippet-first,
no crawl, later LLM verification), stays inside the $5 cap on basic search, and
is one API key. Brave is implemented as a second client with the same
`{snippet, link, title?}` shape for callers who want an independent index.
Serper and Bing are not implemented.

Runtime default remains **mock** until `SBIR_ETL__MA_DISCOVERY__SEARCH_BACKEND`
selects a real vendor **and** `SBIR_ETL__MA_DISCOVERY__SEARCH_API_KEY` is set.

This is not a measured recall or precision result. Revisit after the sample run
in the parent design (step 7) if snippet quality is actually the bottleneck.
