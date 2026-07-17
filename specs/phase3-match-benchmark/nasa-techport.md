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

## FIRST-RUN GATE (must check before trusting the AUC)
Confirm whether a TechPort SBIR project represents the **transition / Phase III** vs the **original Phase
I/II**, via its `program` / phase / date fields:
- If **transition-bearing** → the description is the ranker *target* text (direct NASA analogue of the DoD
  J&A), and the NASA AUC is comparable to DoD's 0.844.
- If it is the **original SBIR award** → it enriches the *query* side (redundant with the abstract), and
  NASA transition detection needs a different target (e.g. NASA Phase III contract writeups, or infusion
  records). Do not report a NASA AUC until this is resolved.

## Honest limits
- **API throttling** — a full ~20k pull needs polite pacing + caching + retries; treat as a background run.
- **Org→UEI matching** is fuzzy name resolution; measure the link rate on the real pull.
- Scope is **contract/portfolio transitions**; NASA grant/commercialization outcomes are a separate problem.
