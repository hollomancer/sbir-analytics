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

## STILL OPEN — a real NASA transition number
Filter TechPort to **actual Phase III** targets (phase field / Phase-III language + later dates) and use
**other firms' Phase III projects** as hard negatives — the true DoD-0.844 analogue. Until then: NASA
**linkage is solved**; NASA **transition detection** is unmeasured but reachable via TechPort.

## Honest limits
- **API throttling** — a full ~20k pull needs polite pacing + caching + retries; treat as a background run.
- **Org→UEI matching** is fuzzy name resolution; measure the link rate on the real pull.
- Scope is **contract/portfolio transitions**; NASA grant/commercialization outcomes are a separate problem.
