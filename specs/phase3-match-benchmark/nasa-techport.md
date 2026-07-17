# NASA cross-agency transition detection — TechPort source

Status: **source identified + puller built/fixture-tested; first paced pull pending (API throttled at
authoring).** NASA-focused follow-on to the DoD transition ranker.

## Why NASA needs a different source (the archive fails)

The DoD ranker recovers rich text from the GSA `falextracts` archive by joining on PIID / Sol# / Awardee.
**For NASA every one of those keys fails** (FY2020 probe): NASA is present with 94% rich descriptions, but
populates `AwardNumber` on ~6% of notices, `Awardee` on ~5%, and FPDS `solicitationID` on ~2.5% (10 of
1,037 PIIDs) — and **zero matched** our NASA Phase III firms. NASA's archive text is general
solicitations/synopses, not the firm-specific award notices / J&As that made DoD work: NASA runs SBIR
through NSPIRES and its Phase III is sole-source with little FPDS trail, so it does not post firm-linkable
award documents to sam.gov Contract Opportunities. (The **undercount** still generalizes — 16/202, 7.9%,
from USAspending — only the *ranker's* rich-text recovery does not.)

## The NASA source: TechPort

`techport.nasa.gov/api` (public) is NASA's own technology portfolio: **~20,036 SBIR/STTR projects**, ~95%
of a sample carrying a **performing firm organization + a rich project description**. That is exactly where
NASA "posts" its funded work, and it is firm-linkable. `pull_techport_nasa.py` provides the paced, cached,
manifested puller plus the pure link logic (`parse_project`, `link_firm`); fixture-tested.

## Build design
1. Search TechPort for SBIR/STTR projects → project ids.
2. Pull each project (paced + retried + cached — **the API rate-limits under rapid calls**), extract firm
   org + description + program/dates.
3. Resolve firm org → SBIR firm UEI (normalized name).
4. Use the project description as rich text; run `transition_ranker.evaluate` (GroupKFold by firm) vs NASA
   firms' abstracts, with hard negatives = other NASA firms' projects.

## FIRST RUN — results (bounded 800-project pull)

Puller bug found + fixed: the **search endpoint returns key `"results"`, not `"projects"`** (and 200-with-
empty under load) — the puller now reads `results` and retries on empty. With that:

- **Linkage SOLVED (the headline):** 800 projects → 609 with a firm org, **429 linked to an SBIR-firm UEI
  (54%), 208 distinct firms** — the firm↔rich-text link the GSA archive could not make for NASA.
- **Descriptions are distinct** from the firm abstract (cosine median 0.12, only 8% near-duplicate); 46%
  carry transition/Phase-III language.
- **First retrieval AUC 0.961** (firm abstract → its TechPort project vs 25 random firms), top-1 86%.

**But 0.961 is NOT a transition-detection number** — it is the *easy* firm-linkage task (a firm's project
is its own tech; negatives are random firms). It is the NASA analogue of DoD's *easy* ~0.79 "which firm",
**not** the hard 0.844 (whose negatives were other firms' Phase III notices, same register). And the
pulled projects look like the **SBIR award itself** (program "Small Business Innovation Research",
2014-2017), not clearly Phase III.

## RESOLVED — TechPort is the original SBIR, not the transition target
Checked whether TechPort can supply Phase III targets. It cannot at scale: project details have
`trlBegin/trlCurrent/trlEnd` but **no phase field**, and of 400 sampled "SBIR" projects, **~51% name Phase
I/II and only ~2% name Phase III**. TechPort's SBIR content is overwhelmingly the **original Phase I/II
award**, so it enriches the **query side** (the firm's SBIR work) — it is **not** the Phase III target the
DoD ranker matched against.

**Conclusion — NASA transition detection is data-limited, not method-limited.** NASA's Phase III
transitions have **no public rich text anywhere found**: not sam.gov (sole-source, unposted) and not
TechPort (Phase I/II). Only the terse USAspending Phase III descriptions exist. DoD works because it posts
rich Phase III J&As; NASA posts nothing firm-linkable for Phase III. So for NASA:
- **Undercount** — works (16/202).
- **Linkage** — solved via TechPort (54%, 208 firms).
- **Transition detection (DoD-0.844 analogue)** — **not viable**; the target text does not exist publicly.
Residual angle (unpursued): TechPort `trl*` progression + `technologyOutcomes`/`destinationType` are a
*maturation* signal, a different formulation than Phase-I/II→Phase-III text matching.

## Honest limits
- **API throttling** — a full ~20k pull needs polite pacing + caching + retries; treat as a background run.
- **Org→UEI matching** is fuzzy name resolution; measure the link rate on the real pull.
- Scope is **contract/portfolio transitions**; NASA grant/commercialization outcomes are a separate problem.

## REOPENED — non-SBIR NASA projects are the transition target (correction)
Two corrections that reopen NASA:
1. **TechPort `searchQuery` does not filter** — it returns all ~20,036 projects for *any* term ("SBIR",
   a firm name, or nonsense all return 20,036). So the earlier "SBIR-only, Phase I/II" read was on the
   *whole* portfolio, not an SBIR subset — the "TechPort = original SBIR" conclusion above was too narrow.
2. **The transition footprint is there:** ~54% of *all* NASA TechPort projects involve a firm matching an
   SBIR company. SBIR firms are broadly present across NASA's mostly **non-SBIR** programs (Space
   Technology Research, Center Innovation Fund, Advanced Air Vehicles…) — those non-SBIR projects, with
   rich descriptions + `trl*` maturation data, are the **straight-NASA-award transitions** (per direction).

**Blocker is the API, not the data.** `searchQuery`/`organization` params don't filter, so a *per-firm*
pull needs the **`/api/organizations`** endpoint (firm → organizationId, confirmed 200) then a
per-organization project lookup. Build path: firm→orgId→projects, keep non-SBIR / higher-TRL / Phase-III
projects as transition targets, run `transition_ranker.evaluate` with other firms' NASA projects as hard
negatives. NASA transition detection is **reopened**, contingent on this endpoint work.

## RESULT — NASA transition detection VIABLE (0.879), via the non-SBIR reframe
Both reframes paid off. The full `/api/projects/search` response (one 104 MB call) carries every
project's orgs + description + `phase` — no per-detail fetches — but uses **snake_case** keys
(`organization_name`), which a camelCase parser silently drops (the earlier "0 firm links" bug).

- **Phase field:** Phase I 8,068 / Phase II 3,254(+461) / **Phase III only 8** / `None` 8,244. A literal
  Phase III target is a dead end; the **`None`-phase non-SBIR NASA program projects** are the transitions.
- **10,132** projects link to a SBIR firm; **333 firms** have a non-SBIR NASA project (transition candidate).
- **NASA transition retrieval AUC 0.879** (top-1 59%, top-3 73%): firm's SBIR abstract → its non-SBIR
  NASA project, hard negatives = 25 **other firms'** non-SBIR NASA projects (same register) — the DoD-0.844
  analogue. **Comparable to DoD.**

**So NASA transition detection generalizes** — via TechPort's non-SBIR projects, not sam.gov. Honest caveat
(same as DoD): "non-SBIR NASA project" is a *proxy* for transition; 0.879 confirms topical linkage of the
firm's SBIR work to its NASA project, but Phase-III-specificity needs the same precision@K human audit.
Method: parse the full search (snake_case), keep non-SBIR (`None`-phase, non-SBIR program) firm-linked
projects as targets, run `transition_ranker.evaluate`-style retrieval with same-register hard negatives.
