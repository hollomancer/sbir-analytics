# Nanotechnology SBIR/STTR Phase II: Commercialization Pathways and Measurement Limits

**Prepared for:** NSET Subcommittee  
**Status:** Provisional — figures are bounded estimates, not rates  
**Data through:** FY2025 (SBIR.gov); FY2024 (USAspending); SEC EDGAR (ongoing)

---

## Summary

Analysis of 2,849 nanotechnology-adjacent SBIR/STTR Phase II awards identifies two nearly independent commercialization pathways, each visible in roughly one in ten awards. They are not additive — they serve different firms, funded by different agencies, going to different markets.

- **Government procurement pathway:** 9.2% of nanotech Phase II awards show a subsequent federally-coded Phase III contract. This signal is concentrated in DoD (67% of coded contracts) and is a known undercount for all other agencies.
- **Private investment pathway:** 9.5% of nanotech Phase II awards have a Regulation D offering filed *after* their Phase II ended — a temporal filter that eliminates 31% of the raw Form D matches. This signal is strongest for NSF-funded firms (17.7%).
- **Overlap between pathways:** 1.3% (37 awards). These populations are nearly disjoint. Firms that return for government Phase III are largely not the same firms that attract venture capital, and vice versa.
- **Combined observable signal:** 17.4% of nanotech Phase II awards show evidence of post-award commercialization activity through at least one channel.
- **Status indeterminate for 82.6%** of the cohort — a measurement problem, not necessarily a commercialization failure.

---

## Background: Why This Is Hard to Measure

The SBIR program does not define a single commercialization metric. Phase III — in statute — encompasses both continued federal procurement and private-sector commercialization resulting from Phase II work. These two outcomes land in entirely different data systems and are nearly invisible to each other.

Federal procurement shows up (partially) in FPDS. Private commercialization shows up in SEC filings, venture databases, and acquisition records — none of which are systematically linked to SBIR award identifiers. This analysis bridges those systems using entity matching on firm names and UEIs, which is imperfect.

A second structural problem: there is no authoritative definition of a "nanotechnology" SBIR award. The NNI's FY2026 Budget Supplement reports approximately $230M in nanotech SBIR/STTR activity in FY2023, but the methodology behind that figure is not published. Text-based keyword matching over award titles and abstracts — the approach used here — captures a different, likely smaller, slice of the same population. The figures below should be read as lower bounds on the nanotech SBIR universe, not a complete census.

---

## Cohort Definition

Awards were identified through keyword and phrase matching over award title and abstract text, using 52 patterns anchored to specific nanotechnology terminology (nanoparticle, nanotube, graphene, quantum dot, atomic layer deposition, NEMS, and related terms). This produced **2,849 Phase II awards** from a base of 68,075 total Phase II records in SBIR.gov — approximately 4.2% of all Phase II activity.

Two alternative methods were tested:

- A proxy based on the repository's existing CET (Critical and Emerging Technology) keyword heuristic produced 650 awards — a strict subset. This narrower count reflects only awards using the words "nanotechnology" or "nanomaterials" explicitly, missing awards that describe techniques without using the category label.
- A USPTO CPC-based approach (patent classification codes B82Y/B82B) could not be executed due to absent local patent data, but would provide a third, patent-anchored perspective on the same population.

The roughly 4:1 spread between methods (650 to 2,849) illustrates how much cohort size depends on definitional choices. The NNI's implied universe ($230M ÷ typical Phase II size) is larger still, suggesting NNI's agency-level identification captures solicitation-topic classifications that are invisible in abstract text.

---

## Finding 1: Two Distinct Commercialization Pathways

When transition signals are examined separately by agency, a clear pattern emerges:

| Agency | Nanotech Phase II awards | FPDS Phase III coded | Post-Phase II Form D | Either signal |
|---|---|---|---|---|
| Department of Defense | 1,413 | 12.5% | 8.8% | 19.4% |
| Dept. of Energy | 364 | 11.3% | 6.3% | 17.3% |
| NASA | 258 | 8.1% | 7.8% | 14.7% |
| Dept. of Health & Human Services | 393 | 3.1% | 9.4% | 12.0% |
| National Science Foundation | 333 | 2.4% | **17.7%** | 19.2% |

DoD and DOE nanotech firms return to the government procurement system at roughly three to five times the rate of NSF and NIH firms. NSF nanotech firms, by contrast, raise private capital at seven times the rate they appear in FPDS Phase III records. The two signals are nearly independent across the full cohort: only 37 awards (1.3%) show both FPDS Phase III and temporally-filtered Form D activity.

A third signal — M&A activity detected through SEC EDGAR filings (`ma_definitive`, `ma_proxy`, `acquisition`, and related mention types) — is present for 434 awards (15.2%) at any confidence level, narrowing to 54 awards (1.9%) at high confidence. Unlike the FPDS and Form D signals, M&A evidence does not separate cleanly by agency; rates range from 9–17% across all major agencies, suggesting acquisition is not strongly pathway-dependent. High-confidence M&A signals should be treated as a floor: entity matching by firm name misses acquisitions that occurred under a renamed entity or below SEC reporting thresholds.

This divergence reflects real differences in market structure, not measurement error. DoD nanotech — hypersonic thermal materials, MEMS-based sensors, radar absorbers — typically has no commercial market outside defense procurement. NSF and NIH nanotech — drug delivery systems, photonic devices, biosensors — can attract venture capital and ultimately reach commercial or clinical markets. The SBIR program is succeeding differently in these two contexts; a single aggregate transition rate obscures both.

**What the numbers imply for private capital:** Among the 272 temporally-filtered Form D matches (131 unique firms), the per-firm median raise was approximately $9 million, with the 90th percentile approximately $90 million. The median lag from Phase II end to first offering was approximately two years — consistent with a product development gap between government-funded prototype and investor-ready asset. This lag has policy implications: evaluation windows shorter than three to four years will systematically undercount NSF and NIH commercialization activity.

---

## Finding 2: Strategic Acquisition by Defense and Pharma Primes

A targeted search of SEC EDGAR filings for named large acquirers identifies **11 nanotech SBIR firms** whose acquisition by a defense or pharma/medtech prime is supported by EDGAR documentary evidence — representing approximately 0.8% of the 1,339 unique firms in the cohort, or 56 awards (2.0%). All confirmed matches cleared a temporal filter requiring that the EDGAR acquisition signal post-date the firm's Phase II end date. (The broader EDGAR detection sweep flagged 16 firms and 71 awards; the 5 additional firms did not clear the confidence threshold due to name ambiguity or insufficient corroborating evidence.)

**Defense prime acquisitions (6 firms):**

| SBIR Firm | Acquirer | Confidence | Technology domain |
|---|---|---|---|
| Physical Optics Corporation | Mercury Systems | High | Photonics, sensors, defense electronics |
| Intellisense Systems Inc | Mercury Systems | High | Sensing systems, defense electronics |
| Nomadics, Inc. | FLIR Systems | High | Chemical/biological threat detection |
| SY Technology, Inc. | L3 Technologies | High | Electronic warfare, defense systems |
| GATR Technologies | Cubic Corp | Medium | Deployable SATCOM antennas |
| KAI, LLC | L3Harris | Medium | Defense electronics (ma_proxy only) |

**Pharma/medtech prime acquisitions (5 firms):**

| SBIR Firm | Acquirer | Confidence | Technology domain |
|---|---|---|---|
| Anasys Instruments Corp | Bruker | High | Nano-IR spectroscopy, AFM-IR |
| EKOS Corporation | C.R. Bard | High | Ultrasound-enhanced catheter thrombolysis |
| EraGen Biosciences | Luminex | High | Molecular diagnostics, multiplexed assays |
| Senior Scientific | Bruker | High | Magnetic nanoparticle detection (MPI/MNP) |
| Visen Medical, Inc. | PerkinElmer | Medium | In vivo fluorescence imaging agents |

Several of these are publicly confirmed transactions with SEC-documented acquisition prices: Mercury Systems acquired Physical Optics Corporation in December 2020 for approximately $310 million (all-cash, per 8-K press release); Bruker acquired Anasys Instruments in 2018 for approximately $32.3 million total consideration ($27M cash + $5.3M contingent, per Bruker FY2018 10-K notes); Luminex acquired EraGen Biosciences in June 2011 for $34 million cash (per Luminex 8-K press release); and PerkinElmer acquired Visen Medical in July 2010 for $23 million (per PerkinElmer FY2010 10-K). ICx Technologies acquired Nomadics in August 2005 (price not SEC-disclosed; FLIR subsequently acquired all of ICx in October 2010 for $228M); C.R. Bard acquired EKOS Corporation in 2010 (EKOS was private; acquisition price not in SEC filings); Cubic Corp acquired GATR Technologies in August 2020 (price not SEC-disclosed; Cubic went private in 2021).

**What makes this pathway distinctive.** Strategic acquisition is arguably the strongest commercialization outcome in the dataset — it represents the acquirer's judgment that the technology and team were worth purchasing outright. It is also the most invisible to standard metrics: once acquired, the firm's subsequent contracts and grants appear under the acquirer's name and UEI, not the original SBIR awardee. The acquired firms vanish from Phase III transition counts entirely. A nanotech firm acquired by Mercury Systems for $310 million looks identical, in FPDS, to a firm that dissolved after its Phase II ended.

**SBIR leverage: government investment and acquisition outcomes.** The table below places each acquisition in context of the firm's total federal SBIR investment (all phases, all years). The "leverage multiple" — acquisition value divided by cumulative SBIR funding — is confirmed from SEC filings for four firms; for the remainder, prices were either not disclosed, the acquired firm was private, or the acquirer subsequently went private before filing. The SBIR investment figure is total across all phases and years, not solely the Phase II awards that preceded the acquisition; for long-tenured firms like Physical Optics, the majority of government funding came during the firm's mature contracting years, not its early R&D phase.

| SBIR Firm | Total SBIR investment | Acquirer | Approx. acquisition year | Reported acquisition value | Leverage (value / SBIR) |
|---|---|---|---|---|---|
| Physical Optics Corporation | $564M | Mercury Systems | 2020 | ~$310M (8-K press release) | 0.55× |
| Intellisense Systems Inc | $164M | Mercury Systems | ~2024 | undisclosed | — |
| Nomadics, Inc. | $27M | ICx Technologies → FLIR | 2005 | not in SEC filings | — |
| SY Technology, Inc. | $9M | L3 Technologies | ~2005 | not in SEC filings | — |
| GATR Technologies | $10M | Cubic Corp | 2020 | not in SEC filings | — |
| KAI, LLC | $6M | L3Harris | unknown | undisclosed | — |
| Anasys Instruments Corp | $14M | Bruker | 2018 | ~$32.3M (FY2018 10-K notes) | 2.3× |
| EKOS Corporation | $3M | C.R. Bard | 2010 | not in SEC filings (private) | — |
| EraGen Biosciences | $5M | Luminex | 2011 | ~$34M (8-K press release) | 6.8× |
| Senior Scientific | $5M | Bruker | ~2014 | undisclosed | — |
| Visen Medical, Inc. | $4M | PerkinElmer | 2010 | ~$23M (FY2010 10-K notes) | 5.8× |

The four confirmed leverage multiples reveal two distinct regimes. Physical Optics — a large, mature, primarily defense-oriented SBIR firm — was acquired for 0.55× its cumulative SBIR investment, below one dollar returned for each dollar of federal R&D funding. The government's outlay was already recouped many times over in delivered contracts; the $310M acquisition price reflects residual capability and IP value, not an exit premium. The three pharma/medtech firms tell a different story: EraGen (6.8×), Visen (5.8×), and Anasys (2.3×) were each acquired at multiples well above their cumulative SBIR funding, reflecting acquirer willingness to pay a strategic premium for technology they could not replicate organically. EraGen's molecular diagnostics platform and Visen's in vivo imaging agents were genuinely novel assets; the $34M and $23M prices, respectively, against $5M and $4M in total SBIR investment, represent a 6–7× government leverage ratio.

The pattern is not universal — acquisition leverage depends on the firm type. Defense contractors whose primary product is continued deliverability to the federal customer are acquired close to or below their government-funded cost basis. Technology creators with cross-market intellectual property are acquired well above it. A policy framing that uses a single "SBIR leverage" figure will mix these two regimes and produce a number that is uninformative about either.

The caveat is significant: seven of the eleven firms have no SEC-documented price — either because the acquired firm was private, because the acquirer went private before disclosure, or because the transaction was structured as an asset purchase below reporting thresholds. The table understates acquisition value in aggregate; the true leverage ratio across all 11 firms is unknown but likely higher than the four confirmed cases suggest, given that confirmed cases skew toward larger disclosed transactions.

**Agency pattern.** The split is consistent with the broader findings. DoD-funded firms appear exclusively in the defense prime column; HHS-funded firms (NIH grants for biosensors, imaging agents, and diagnostic systems) flow to pharma and medtech primes. NSF nanotech firms that commercialize appear more likely to raise Form D capital than to be acquired by a prime, though sample sizes are too small for this to be a firm conclusion.

**Temporal lags.** The median time from earliest Phase II end date to confirmed acquisition across the 10 firms with known acquisition dates is approximately 7 years. The longest is EKOS Corporation, where a Phase II award in 1998 preceded C.R. Bard's acquisition of the firm in 2010 — a 12-year span. This reinforces the evaluation window finding from Finding 1: outcome windows of two or three years will miss the majority of acquisition-pathway commercialization events.

**Floor estimate caveat.** This analysis detects acquisitions that (1) required SEC filing because they involved a publicly traded acquirer, (2) were large enough to trigger disclosure, and (3) matched by the acquired firm's name at the time of the transaction. Acquisitions of renamed entities, asset purchases below disclosure thresholds, and acquisitions by private-equity-owned defense contractors that are not SEC filers are not captured. The 11 firms identified should be treated as a lower bound.

---

## Finding 3: The Disappearance Problem

Of the 2,373 nanotech Phase II awards that are old enough to have matured (award year ≤ 2022) and show no FPDS-coded Phase III activity, the following breakdown applies:

| Reason transition status is indeterminate | N awards | Share of indeterminate |
|---|---|---|
| Firm has no federal activity record post-award | 1,298 | 54.7% |
| Firm cannot be linked to federal systems (no UEI) | 539 | 22.7% |
| Firm in FPDS but no contract carries Phase III coding | 354 | 14.9% |
| Non-DoD agency where FPDS Phase III coding is sparse | 182 | 7.7% |

The dominant category — 54.7% of the indeterminate population — is firms that received a Phase II award and subsequently disappeared from federal procurement records entirely. This is not automatically a negative outcome. Some of these firms will be among those captured by the Form D signal; others will have been acquired (removing them from the SBIR awardee name match); others will have reached commercial markets without touching SEC reporting thresholds; some will have dissolved.

The current data infrastructure cannot distinguish between these outcomes. A firm that raised $200M in a private round and was acquired by a major corporation looks identical, in FPDS, to a firm that received a Phase II award and immediately went out of business. Both show up in the "firm activity absent" bucket.

The 22.7% entity resolution failure rate — awards in SBIR.gov that lack a UEI — reflects a data quality problem that predates the UEI transition and is particularly acute for pre-2012 awards. This population is permanently opaque to FPDS-based analysis.

---

## Finding 4: The FPDS Coding Gap Is Structural, Not Incidental

For non-DoD agencies, the absence of FPDS Phase III coding is not evidence of failed transition — it is a known characteristic of how those agencies procure. GAO-24-106398 documents that FPDS Phase III flags are populated primarily by DoD contracting officers and are absent or inconsistent in NIH, NSF, and DOE procurement systems.

The practical effect: NIH and NSF nanotech firms that do receive subsequent federal awards — follow-on grants, cooperative agreements, BAA contracts — will generally not appear in Phase III contract counts. The 3.1% FPDS Phase III rate for NIH nanotech firms almost certainly understates the true federal re-engagement rate; it captures only the cases where a contracting officer specifically coded the Phase III flag, which is not standard NIH practice.

This matters for program evaluation. Using FPDS Phase III rates as a comparative metric across agencies systematically disadvantages programs — like NSF and NIH — whose procurement culture does not produce that coding. Any cross-agency comparison using this metric will misleadingly favor DoD.

---

## What Is Not Visible

Several commercialization pathways are beyond the reach of this analysis:

**Direct commercial revenue.** A nanotech firm that licenses a patent, wins a commercial contract, or sells product to industrial buyers leaves no trace in federal data systems unless it files with the SEC. Most small firms do not.

**Acquisitions below reporting thresholds.** A $15M acquisition of a nanotech startup — common in the materials and biomedical device sectors — may not trigger SEC reporting and will not appear in the Form D data used here.

**Licensing and technology transfer.** University-adjacent SBIR recipients (particularly common in NSF and NIH nanotech) often commercialize through patent licensing agreements that generate no SBIR-traceable transaction.

**NNI-classified awards missed by keyword matching.** The gap between our 2,849-award keyword cohort and NNI's implied ~3,800–6,000 award universe (based on $230M at typical Phase II sizes) means a meaningful fraction of nanotech SBIR activity is not captured here. Awards where the nanotech scope is stated in a classified solicitation topic, or where the abstract uses domain-specific terminology without standard nano-vocabulary, will be missed.

---

## Policy Implications

**1. Aggregate transition rates are uninformative for nanotech.** The split between government-procurement and private-capital pathways is large enough that a single program-wide number will be misleading regardless of how it is computed. Reporting should distinguish DoD from non-DoD, and procurement-pathway from commercial-pathway, as a minimum.

**2. Evaluation windows need to match commercialization timelines.** A median two-year lag from Phase II end to first private raise means that annual or biennial transition assessments will systematically undercount NIH and NSF outcomes. A four-to-five year follow-up window is more appropriate for nanotech given product development timelines.

**3. The entity resolution gap is a data infrastructure problem.** Nearly one in four nanotech Phase II awards that lack Phase III evidence cannot be assessed at all because the SBIR.gov record does not carry a UEI. Retroactive UEI matching for historical awards — or systematic awardee tracking through the SAM.gov registry — would materially reduce this gap in future analyses.

**4. FPDS Phase III coding is not a cross-agency metric.** Using FPDS-coded Phase III rates to compare NSF or NIH programs against DoD programs will produce misleading results by design. A more appropriate cross-agency metric would combine FPDS activity (contracts and grants, not just Phase III-flagged contracts) with Form D and capital events data, reported separately by pathway.

**5. The "disappeared" firm population deserves targeted investigation.** The 1,298 firms with no post-award federal activity record represent the largest single uncertainty in this analysis. A sample-based follow-up survey — even 50–100 firms — could establish what fraction dissolved, were acquired, commercialized, or simply cannot be found. That distribution would significantly sharpen estimates for the full population.

---

## Methodological Notes

All figures in this report are provisional and subject to the following limitations:

- **Cohort definition:** Keyword matching over text fields will miss nanotech awards where the abstract does not use standard terminology. The NNI universe may be substantially larger.
- **FPDS Phase III undercounting:** GAO-24-106398 documents this as a structural problem, concentrated outside DoD. FPDS-coded rates should be treated as floors.
- **Form D matching:** Entity matching is by firm name and is imperfect. False positives (two different firms with similar names) and false negatives (name changes after acquisition) both occur. The high-confidence tier used here applies a multi-signal scoring algorithm (name, person, state, temporal), but exact attribution to specific Phase II awards is not possible.
- **NNI reference figures:** The agency-by-year NNI Table 5 figures used in the underlying reconciliation analysis are approximate public summary values. The exact NNI methodology for identifying nanotech SBIR awards is not published.
- **SEC EDGAR M&A scan:** The full scan of 34,460 SBIR firms in `sec_edgar_scan.jsonl` is complete and covers 99.9% of the nanotech cohort. A separate recent scan run wrote a summary showing zero detections due to repeated HTTP 500 errors — that summary reflects a failed process, not the underlying data. M&A mention signals in this report draw on the complete scan, filtered to acquisition-specific mention types (`ma_definitive`, `ma_proxy`, `acquisition`, `subsidiary`, `ownership_active`). Confidence tiers reflect multi-signal scoring from the enrichment pipeline: high-confidence M&A signals are present for 54 awards (1.9%); medium for 166 (5.8%); low for 214 (7.5%). Only high-confidence signals should be cited in formal contexts.

Full methodology, term lists, confidence tags, and reproducible code are in `docs/nano_phase3_methodology.md` and `scripts/data/build_nano_cohort.py`.
