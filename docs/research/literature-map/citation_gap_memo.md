# Citation-Gap Analysis — `[L#]` Benchmark List vs. Recent Literature Map

**Question:** Which recent papers in the 179-work literature map are *not* in the
repo's `[L#]` benchmark list (`docs/research-questions.md`)?

## Headline

**All 179 mapped works are absent from the `[L#]` list — but that is expected, not alarming.**
The `[L#]` list is a curated *benchmark* set (33 entries), not a literature review. Only six of
its entries are peer-reviewed academic papers — **L9** (Myers & Lanahan 2022), **L10** (Lerner
1999), **L11** (Howell 2017), **L12** (Link & Scott 2010/2012), **L13** (Jaffe-Trajtenberg-
Henderson 1993), and **L24** (Kortum & Lerner 2000). The newest is L9 (2022); the rest predate
the 2019–2026 map window entirely. The remaining 27 entries are NASEM reviews, GAO/CRS reports,
CSIS/ITIF/TechLink studies, statutes, and data sources — grey literature OpenAlex covers poorly.

So the useful output is **not** "179 uncited papers." It is a curated, ranked shortlist of
*SBIR-specific* recent works worth adding, organized by which `[L#]` slot they update. I split
this into two tiers.

---

## Tier 1 — SBIR-specific works worth adding to `[L#]` (51 core works)

These directly study SBIR/STTR and would extend the benchmark list with post-2019 evidence.
The strongest candidates per area (full set in `citation_additions_core.csv`):

### Area A — National security / DIB → currently only policy reports (L16,L17,L28–L33)
This area has **no recent peer-reviewed econometrics in `[L#]`**. The two strongest adds:
- **"Opening Up Military Innovation: Causal Effects of Reforms to U.S. Defense Research"**
  (Journal of Political Economy 2025; NBER 2021). Causal estimates of DoD research-funding
  reform — directly relevant to the A3 leverage-ratio and open-topic-SBIR questions.
- **Link et al., "Small Firms and U.S. Technology Policy"** (Edward Elgar 2023) — synthesizing
  monograph; the natural companion to L10/L12.
- **"Evaluating the Effectiveness of the Air Force's Open Topic SBIR/STTR Process"** (2022) —
  speaks to the Air Force open-topic mechanism behind several A-section questions.

### Area B — Commercialization → updates L1/L3/L4/L12
- **"Are public subsidies effective for university spinoffs? Evidence from SBIR awards"**
  (Research Policy 2022, 44 cites) — the single most-cited recent core work; a modern
  complement to Link & Scott [L12].
- **"The transfer of federally funded technology…"** (Small Business Economics 2023).

### Area C — Innovation / spillovers → updates L9/L13
- **"Firm reliance on SBIR funding and its relation to the generation of spin-off firms"**
  (Journal of Technology Transfer 2026) — newest core work; spin-off generation.
- **"Knowledge begets knowledge: university knowledge spillovers"** (Scientometrics 2019).

### Area D — Economic / fiscal impact → updates grey-lit L19/L20/L21
The strongest peer-reviewed adds to an area currently anchored on TechLink/NCI/ITIF reports:
- **"Do public R&D subsidies produce jobs? Evidence from the SBIR/STTR program"**
  (Research Policy 2021, 43 cites).
- **"Evaluating the tail of the distribution: economic contributions of frequent awardees"**
  (Research Policy 2022, 21 cites) — directly relevant to the repeat-vs-new-winner ROI cut.
- **"Helping the Little Guy: the impact of government awards on small technology firms"**
  (Journal of Technology Transfer 2021, 28 cites).
- **Howell, "Do Cash Windfalls Affect Wages? Evidence from R&D Grants to Small Firms"**
  (NBER 2020) — extends the L11 anchor; note possible later published version.

### Area E — Program management / methods → updates L14/L15/L18
The deepest core cluster (18 works). Highest-value adds:
- **"An Empirical Model of R&D Procurement Contests: An Analysis of the DOD SBIR Program"**
  (Econometrica 2021, 32 cites) — the methodological flagship.
- **"Who captures the state? Evidence from irregular awards in a public innovation grant"**
  (Strategic Management Journal 2024) and **"SBIR mills and the U.S. Department of Defense"**
  (Journal of Technology Transfer 2024) — the academic treatment of the data-integrity /
  "SBIR mill" problem your entity-resolution and benchmark-evaluation work contends with.

### Area F — Capital formation → **zero core works exist**
No SBIR-specific peer-reviewed work surfaced. The published baselines your F-section benchmarks
against are adjacent (Tier 2): "Venture Capital's Role in Financing Innovation" (J. Economic
Perspectives 2020) and "Bridging the equity gap…" (Research Policy 2020). **This confirms the
F-area finding from the literature map: your Form-D / M&A-exit / private-leverage questions are
open research territory.**

---

## Tier 2 — Broader-context baselines (adjacent, 126 works)

High-citation general innovation-policy and entrepreneurial-finance works (e.g., "A Toolkit of
Policies to Promote Innovation," "The Changing Structure of American Innovation," "Mission-
oriented or mission adrift?"). These are useful *background* but are **not** SBIR-specific and
should not be promoted into `[L#]` on citation count alone — raw citations over-rank broad
reviews. Full list with area tags in `sbir_literature_map.csv` (relevance = "adjacent").

---

## Recommendation

1. Add a small number of Tier-1 core works per area to `[L#]`, prioritizing **D, E, and A**
   where recent peer-reviewed evidence most strengthens the existing grey-lit / pre-2019 anchors.
2. Leave **F** as-is but note explicitly in the inventory that no SBIR-specific academic
   literature exists for the capital-formation questions — a novelty signal for your own work.
3. Watch for **version collisions**: "Opening Up Military Innovation," "Small Business Innovation
   Applied to National Needs," and the Howell wage paper each circulate as NBER/SSRN/published
   versions; cite one canonical version each.

*Files: `citation_additions_core.csv` (51 core candidates, full metadata),
`recommended_citation_additions.csv` (top-5-per-area scored shortlist),
`sbir_literature_map.csv` (all 179 with relevance/area tags).*
