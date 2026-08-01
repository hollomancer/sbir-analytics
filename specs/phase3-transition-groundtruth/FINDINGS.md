# Phase III Ground-Truth — Collection & Skew Findings (2026-08-01)

Running findings from the collection + skew-analysis pass. Feeds T6 (scoring) / T7 (memo).

## Composition (procurement, distinct-firm deduped)

- **343 procurement transitions, 293 distinct firms, 15 agencies.**
- **Navy 51% / non-Navy 49%** — balanced (was 85% Navy at first pass).
- Agencies: Navy 174 · MDA 39 · DHA 34 · DLA 19 · AF 15 · Space Force 12 · NASA 11 · DTRA 9 · Army 9 · DARPA 8 · SOCOM 5 · DHS 4 · DIU 2 · OSD 1 · DOC 1.
- Strata: marquee 224 / hard 119.

## Provenance tiers (score & report separately)

1. **independent-clean** — marquee program-office / PR success stories (Navy DB, AFWERX/SpaceWERX, NASA, sbir.gov). Trustworthy but selection-biased → a **ceiling**, not the headline.
2. **independent-hard** — USAspending/press contract records whose *own description* says "SBIR PHASE III" (DLA/DTRA/DHA/SOCOM/MDA batches). External, non-marquee, 100% contract-resolved.
3. **pipeline** — the in-repo MDA set from `phase3_universe` (recipient+keyword attribution). Weakest tier; 10 of its rows are now independently re-confirmed by USAspending.

## The census frame (scalable hard tier)

`phase3_universe.jsonl`: **1,901 of 2,013 contracts declare "SBIR PHASE III" in their own description** — 868 firms, $6.5B. **Non-Navy: 1,485 contracts / 732 firms.** This is a stratified sampling frame — non-Navy volume is no longer a collection problem, it's a sampling choice.

## Detector-skew measurement (the important finding)

Measured the detector's dominant signal (word-TF-IDF cosine, per-firm ranking) on the frozen corpus (101 rankable firms):

| group | firms | precision@1 |
|---|---|---|
| Navy | 45 | 0.844 |
| **AF/Space** | 19 | **0.895** |
| OtherDoD | 37 | 0.541 |
| non-Navy (blended) | 56 | 0.661 |

**Interpretation:** the gap is **not** Navy-vs-rest — AF/Space *beats* Navy. It tracks **notice-description richness**: rich-text domains (Navy, AF/Space) rank well; sparse-text domains (OtherDoD) rank poorly. This matches the known [empty-description wall]. Two structural reasons Navy dominance does **not** adversely bias the detector:

1. **Ranking is per-firm.** Each firm's true transition competes only against *its own* candidate notices, never against Navy's. Navy cannot crowd out non-Navy — cross-agency score-scale differences wash out of within-firm ranking.
2. **Features are generic** (text similarity, NAICS length, notice type), not Navy vocabulary; frozen coefficients transfer.

**Consequence for validation:** the risk is no longer branch skew — it's **description-richness / tech-domain skew** and **thin per-agency cells**. Adding 34 DHA-medical + other sparse-text cases will pull the blended number down; that is *honest*, but it must be read per-domain, not blended.

## DIU CSO/OTA gate (vehicle-agnostic Phase III)

Swept all 8 DIU CSO/OTA firms for an SBIR prior with a plausible pre-transition timeline:
- **Qualify:** Anduril (PhI/II 2019–20 → 2021 C-UAS OT), EpiSci/EpiSys Science (44 SBIR, PhII 2012+ → 2023 OT).
- **Excluded:** Teleidoscope/Somewear/C3.ai/Ascent/Freefly (no SBIR); SpyCloud (only SBIR is PhI 2024, *postdates* its 2023 transition).
- **Rule:** the gate is the SBIR prior, not the contract vehicle — Phase III can flow through an OTA. OT#s + SBIR→OT lineage for the two qualifiers still to confirm.

## Open items → T6/T7

- Stratified-sample the census frame for a balanced, per-agency-capped scoring set (cap Navy to ~parity-per-agency at score-time; keep all collected).
- Report precision by **agency × tech_domain × provenance × stratum**; do not slice 15 agencies thinly — group by domain + the big cells; report CIs.
- Resolve the 2 SimVentions bare-order-number rows via parent IDV, or drop.
- Confirm Anduril/EpiSci SBIR→OT lineage.
