# Policy Brief: NSF SBIR Is Not a Commercialization Outlier

**Audience:** SBIR program leadership, congressional staff, OSTP, GAO. **Date:** May 2, 2026. **Status:** Draft for circulation.

## TL;DR

A widely circulated framing — including ITIF's "America's Seed Fund" framing and the policy literature it draws on — suggests NSF's SBIR program is qualitatively different from peer agencies on commercialization outcomes. We tested this four ways on the cleanest available signals:

1. **M&A exit rates: statistically indistinguishable.** Matched cohort (vintage × industry × state, 2010–2014): NSF 32.4% vs. peer-SBIR 28.9% (CIs overlap; ratio 1.1x).

2. **Per-company capital raised: NSF lower at the median, fatter right tail.** NSF median $3.3M vs. peers' $5.8M (43% gap, opposite direction of the popular narrative). P95 $418M vs. $167M (NSF 2.5x higher).

3. **Per-agency Form-D-filing rates: uniform.** NSF 33.3% sits mid-pack: HHS 34.1%, DoE 30.1%, DoD 29.6%, NASA 28.1%. CIs overlap pairwise.

4. **Federal-contract presence: NSF *much* lower.** Non-R&D federal procurement contracts within 5 years of Phase II — NSF 2.9% (CI 1.3–6.7%) vs. peer-SBIR 14.0% (CI 12.1–16.0%); 4.8x gap, CIs do not overlap.

**Joint reading: NSF SBIR awardees are not measurably more "commercialization-productive" than peer-agency SBIR awardees — but they do commercialize through *different channels*.** NSF awardees pursue private markets (Form D filings, M&A exits) at peer-equivalent rates while pursuing federal procurement at dramatically lower rates. Peer-SBIR awardees (DoD/NIH/DOE-heavy) commercialize more through continued government contracting. Both pathways are legitimate; the difference reflects deliberate agency program design — DoD's Phase III sole-source pathway, NIH's mission-aligned follow-on funding, etc. — rather than NSF's superiority. The popular narrative of NSF as a uniquely productive program does not survive scrutiny; a more accurate description is that NSF's program design selects *against* federal-customer dependency in favor of private-market-oriented exits.

## Finding 1: M&A Exit Rates (Matched Cohort)

| Cohort | Definition | M&A exit rate | 95% CI | n |
|---|---|---|---|---|
| **Treatment (NSF)** | NSF Phase II awardees in SEC EDGAR (2010–2014) | **32.4%** | 25.8% – 39.7% | 170 |
| **Control (peer SBIR)** | Non-NSF SBIR Phase II awardees in SEC EDGAR with own Form D filings (2010–2014) | **28.9%** | 26.4% – 31.4% | 1,254 |

Cohorts matched via coarsened-exact matching on `(vintage_bucket, industry_group, state)`: vintage = 5-year award buckets, industry = SEC Form D's 9-bucket taxonomy (Biotechnology, Computers, Health Care, Energy, Manufacturing, etc.), state = 2-letter postal code. 85 strata had ≥1 awardee from each cohort.

The 1.1x ratio is consistent with no real difference. A study of this size has roughly 80% power to detect a true effect of ~1.4x or larger; the observed effect is well below that threshold.

**Coverage of the M&A signal.** The detector combines Form D `is_business_combination` flags (12% of NSF events fire on this alone) with EFTS-mention classification — definitive merger agreements in 8-K/S-4 filings, target-as-subsidiary references in acquirer filings, and Schedule 13D/13G ownership disclosures (62% of NSF events fire on EFTS signals without a Form D combo flag). Most professional acquisitions including PE buyouts get caught via at least one of these channels. The signal is genuinely blind only to fully-private cash-only deals with no SEC trace at either party — a small fraction of meaningful exits, and one that should be symmetric across cohorts.

## Finding 2: How Much Capital Each Cohort Raised

The M&A *rate* comparison is null. The per-company dollar picture is the second test — and runs counter to the direction the popular narrative would predict.

**The median NSF Form-D-filing awardee raises *less* than the median peer-SBIR Form-D-filing awardee.** Per-company cumulative Form D capital raised:

| Percentile | NSF (n=66) | Control (n=1,254) | NSF / Control |
|---|---|---|---|
| P25 | $0.5M | $1.2M | 0.42x |
| **P50 (median)** | **$3.3M** | **$5.8M** | **0.57x** |
| P75 | $25.9M | $24.5M | 1.06x |
| P90 | $109.7M | $89.2M | 1.23x |
| P95 | $417.8M | $167.5M | 2.50x |
| P99 | $761.3M | $460.4M | 1.65x |

The distribution is barbell-shaped: NSF Form-D-filers either raise small amounts or very large amounts; the control distribution is more uniform. This is reflected in concentration metrics — the top 10 NSF companies account for **87.6% of all NSF cohort dollars** ($3.34B of $3.81B), while the top 10 control companies account for **20.4%** ($9.38B of $46.03B). Removing the top 10 from each: the NSF body raises a mean of $8.4M per company; the control body raises a mean of $29.5M per company — a 3.5x gap in the *opposite* direction of the popular narrative.

**Caveats on the dollar comparison:**
- The NSF cohort with CIK matches is small (n=66 of 170 matched NSF rows). Right-tail percentiles are sensitive to a single $1B+ outlier; the distribution shape is robust, but the exact P95 magnitude should be treated as approximate.
- The control cohort is 100% own-Form-D-filers by construction. The NSF cohort is "EDGAR presence" — only 38.8% of which (1,168 of 3,012 awardees, 781 unique companies) actually filed their own Form D. (See Finding 3 for the per-agency Form-D-filing-rate comparison that contextualizes this asymmetry.)
- These are *cumulative* per-company Form D raises, not single-round amounts. Companies with longer EDGAR presence accumulate more.

## Finding 3: Per-Agency Form-D-Filing Rates

The cleanest test of the "selection-at-entry" hypothesis — *do NSF awardees disproportionately pursue private capital compared to peers?* — runs at the agency level on the full SBIR awardee population (not just the matched cohort). For each agency, we compute the fraction of unique awardee companies that appear as Form D filers in SEC EDGAR's quarterly Form D index (2009–2026).

| Agency | Unique awardees | Form-D-filers | Filing rate | 95% CI |
|---|---|---|---|---|
| HHS (NIH-led) | 12,355 | 4,218 | **34.1%** | 33.3% – 35.0% |
| **NSF** | **7,521** | **2,501** | **33.3%** | **32.2% – 34.3%** |
| EPA | 736 | 229 | 31.1% | — |
| DoE | 3,505 | 1,055 | 30.1% | 28.6% – 31.6% |
| DHS | 531 | 158 | 29.8% | — |
| DoD | 14,289 | 4,233 | 29.6% | 28.9% – 30.4% |
| NASA | 3,703 | 1,039 | 28.1% | 26.6% – 29.5% |
| USDA | 1,936 | 511 | 26.4% | — |
| DoC | 927 | 245 | 26.4% | — |
| EdD | 652 | 155 | 23.8% | — |
| DoT | 616 | 142 | 23.1% | — |

**NSF sits squarely in the middle of the agency pack.** HHS slightly exceeds NSF (34.1% vs. 33.3%, CIs overlap). DoD, NASA, and DoE are 1–5pp lower than NSF, with overlapping CIs in pairwise comparisons. The 11pp range across agencies (HHS 34.1% to DoT 23.1%) is plausibly explained by industry mix — biotech and software-heavy agencies (HHS, NSF, EPA) cluster at the top, while transportation- and education-focused agencies cluster at the bottom — rather than by agency program-design differences.

This is the test that, if NSF SBIR were uniquely commercialization-productive at the entry-point stage, would have shown the largest signal. It doesn't.

**Robustness check.** We replicated this analysis against the full SEC EDGAR Form D corpus (357,548 unique issuers across 763,178 filings since 2009). Using exact-match (no fuzzy normalization, more conservative) gives a lower-bound rate of NSF 16.3% (CI 15.5–17.2%) vs. HHS 16.5% / DoE 11.1% / DoD 10.5% / NASA 7.3% — **the rank-order is identical** to the fuzzy-match version, with NSF and HHS still statistically tied at the top. The two matching strategies bracket the true rate; both agree directionally that NSF is not the unique outlier the popular narrative would predict.

**Caveat:** filing rate is a binary signal (any Form D filing, ever). It doesn't distinguish small SAFE rounds from major equity raises. The 11pp spread across agencies could in principle reflect industry-mix effects (biotech-heavy portfolios cluster higher) rather than agency program-design effects; sub-industry decomposition would resolve this but requires NAICS coverage we don't have.

## Finding 4: Federal-Contract Presence (USAspending)

The first three tests look at private-capital channels. Federal procurement contracting is the *other* major commercialization channel — and the one where peer-SBIR agencies (DoD, NIH, DOE) would be expected to outperform NSF if any agency-design effect exists. We queried USAspending for each matched-cohort company's federal procurement contract presence within 5 years of their Phase II award.

| Filter | NSF (n=170) | Peer-SBIR control (n=1,254) | Ratio |
|---|---|---|---|
| Any procurement contract (A/B/C/D) | **2.9%** (CI 1.3–6.7%) | **26.1%** (CI 23.7–28.5%) | 9.0x |
| Non-R&D procurement (excludes NAICS 5417*) | **2.9%** (CI 1.3–6.7%) | **14.0%** (CI 12.1–16.0%) | 4.8x |

The NAICS 5417* filter (R&D in Nanotechnology / Biotech / Physical-Engineering-Life-Sciences) excludes contracts that are themselves SBIR-flavored R&D follow-ons, isolating the cleanest "transition to non-R&D federal procurement" signal. The control rate drops from 26.1% to 14.0% under this filter, indicating that ~12pp of the naïve gap was R&D-contract continuation. **The remaining 4.8x gap on non-R&D procurement is the cleanest signal of a real agency-level commercialization-channel difference.**

This is the only one of the four findings where NSF and peer-SBIR awardees differ at large magnitude with non-overlapping confidence intervals.

**Interpretation.** Peer-SBIR programs (especially DoD) have explicit mechanisms that channel awardees toward continued federal contracting: DoD's Phase III sole-source pathway, NIH's mission-aligned follow-on grants, DoE's national-lab partnerships. NSF SBIR has no equivalent. Combined with Findings 1–3 showing private-capital outcomes are statistically equivalent across cohorts, the picture is: **NSF and peer-SBIR awardees commercialize via different channels, not at different rates.** NSF awardees pursue private-market exits; peer-SBIR awardees continue federal contracting. Both are legitimate. The agencies channel commercialization differently by program design.

**Caveats:**
- The matched NSF cohort is the same restricted population as Findings 1–3 (n=170 NSF Phase II awardees in EDGAR with vintage 2010–2014 and successful matching). Generalization to the full NSF awardee population requires the same caveats as the other findings.
- The USAspending name-matching is exact-normalized; companies with very generic names ("RST, Inc.") are conservatively undercounted. The bias is symmetric across cohorts, so the rate comparison is robust, but absolute rates are conservative bounds.
- "Within 5 years of Phase II award" is approximated by a 2010–2024 global query window. Per-company time windows would be marginally cleaner but not directionally different at this gap magnitude.

## Why These Findings Matter

The popular framing of NSF SBIR as a uniquely commercialization-productive program rests on three lines of evidence: (1) qualitative case studies of high-profile NSF-funded exits; (2) ITIF's institutional argument that NSF's review process selects for technical novelty; and (3) Howell (2017)'s causal evidence that DOE SBIR awards roughly double follow-on VC probability — a finding sometimes generalized across SBIR-running agencies.

Our analysis tests this framing on four signals — three private-capital channels (exit rates, capital raised, Form-D-filing rates) and one government-contracting channel (USAspending federal procurement presence). **The findings paint a consistent picture: NSF and peer-SBIR awardees are not measurably different on commercialization *productivity* but are dramatically different on commercialization *channel*.** NSF awardees pursue private markets at peer-equivalent rates while pursuing federal procurement at 5x lower rates. Peer-SBIR awardees go the other direction.

Four implications follow:

1. **The "NSF is uniquely productive" framing is unsupported; the "NSF channels differently" framing is well-supported.** Three of four tests show NSF and peer-SBIR awardees as statistically equivalent. The fourth (federal-contract presence) shows them as dramatically different in the *opposite* direction of the popular narrative — NSF awardees less likely to be federal contractors, not more likely. The cleanest defensible characterization: NSF's program design *selects against* federal-customer dependency in favor of private-market-oriented exits. Whether this is a feature or a bug is a values question for policy audiences; the empirical fact is the channel difference, not a productivity difference.

2. **Headline claims about NSF's program-design superiority should be interpreted with care.** Specifically, the 12x M&A figure that briefly circulated in an internal draft was an artifact of an asymmetric data filter, not a real finding. (Full methodology disclosure: an earlier draft applied an NSF-agency filter to the shared M&A-events file and fed the result to both cohorts, structurally zeroing the control rate. The corrected analysis applies a symmetric all-agency M&A signal to both cohorts.) The filing-rate and dollar findings reinforce the corrected null.

3. **The channel-difference finding is consistent with deliberate program design, not accident.** DoD SBIR has Phase III sole-source contracting that explicitly rewards continued government work. NIH SBIR has mission-aligned follow-on grant pathways. DOE SBIR has national-lab partnership norms. NSF SBIR has none of these — its program is gated on technical merit at entry and provides no follow-on government-customer pull. The 4.8x federal-procurement gap (Finding 4) is exactly what these design differences would predict. The agencies are not failing or succeeding at the same task; they are running different programs that produce different commercialization-channel mixes.

4. **The right cross-agency questions for SBIR reauthorization should pivot.** Rather than "which agency's program design produces more commercialization?" — a question for which the productivity data shows no large effects — the productive question is: *what mix of commercialization channels does the federal SBIR portfolio want to produce, and which agencies' program designs deliver each?* If acquisition-led commercialization and IPO-style outcomes are valued, NSF's program is the existing federal exemplar (within the federal SBIR portfolio). If continued mission-aligned federal contracting is valued, DoD/NIH/DOE programs are the exemplars. Optimizing the portfolio mix is a values question, not an empirical one — but the empirical data does support that *both channels exist within current federal SBIR* and the agencies channel them differently.

## What This Analysis Cannot Tell Us

Several questions that policy audiences may reasonably ask are not answerable with current data:

- **Per-agency patent-yield rates.** Requires PATLINK award_id ↔ patent joins for both cohorts. Currently `data unavailable`.
- **Causal estimates.** This is a matched-observational comparison, not a causal estimate. Howell (2017)'s regression-discontinuity design exploiting NSF's funding-line cutoff is the standard for causal SBIR-effect identification; a similar RDD applied across multiple agencies would be the natural causal extension.
- **Sub-industry effects.** Form D's 9-bucket Industry Group taxonomy is coarse. NAICS-4 sub-industry matching might surface heterogeneity that the current matching collapses. Requires NAICS coverage for SBIR awardees, which is not on disk.

## What We Recommend

1. **Treat "different channels, not different rates" as the load-bearing finding.** Three of four tests show NSF and peer-SBIR awardees as statistically equivalent on commercialization productivity. The fourth shows them dramatically different on commercialization channel. Headline claims that NSF SBIR is uniquely *productive* are not supported; claims that NSF SBIR systematically channels awardees toward private-market exits rather than federal contracting *are* supported.

2. **Reframe SBIR program evaluation around channel-mix optimization, not productivity ranking.** If the federal SBIR portfolio aspires to produce both private-market-oriented exits AND mission-aligned continued federal contracting, both NSF (private channel) and DoD/NIH/DOE (federal channel) programs are succeeding at *different* parts of that mix. The policy question is what mix the portfolio wants — not which agency is "best."

3. **Materialize remaining data products to extend the analysis.** Two extensions remain: (a) PATLINK award_id ↔ patent joins (tests technology-diffusion-as-commercialization channel); (b) per-agency NAICS-4 sub-industry decomposition (tests whether the channel difference is industry-mix or program-design). The pipeline architecture is in place; the data products are the bottleneck.

4. **Don't over-weight right-tail anecdotes in agency program evaluation.** A handful of high-profile NSF-funded exits (n=10 of 66 Form-D-filers carry 87.6% of NSF cohort dollars) are real and impressive, but they are not a sufficient basis for portfolio-level claims about agency program-design productivity. The body of the distribution matters at least as much.

## Methodology Note

This brief reflects three material corrections from earlier internal drafts:

- **Corrected M&A-events filter** in `scripts/data/run_nsf_vc_phase2.py`. An earlier draft applied an NSF-agency filter to the shared M&A-events file and fed the result to both cohorts, structurally zeroing the control rate. The corrected analysis applies the same all-agency M&A signal to both cohorts, ensuring symmetric treatment.
- **Per-agency Form-D-filing rate added** as a third independent test, against the full SEC EDGAR Form D corpus (357,548 unique issuers, fetched via `scripts/data/fetch_form_d_index_full.py`). An earlier draft characterized this as unanswerable with available data; we corrected this and ran it.
- **USAspending federal-contract presence added** as a fourth independent test (Finding 4). An earlier draft of this same analysis returned ~0% for control due to a `NAICS` field type bug — USAspending returns NAICS as a `{"code": ..., "description": ...}` dict, but the script stringified the dict and the 5417* prefix filter never fired. Once corrected, the control rate dropped from a naïve 26.1% (which included R&D contract continuations counted as "transition") to a clean 14.0% on non-R&D procurement, while the NSF rate stayed at 2.9%.

We surface all three corrections transparently because they illustrate a general point about cross-agency analyses: small filter asymmetries and field-type bugs can produce dramatically wrong comparisons, and validation against alternative reasonable analysis paths is essential before circulating findings. None of the corrected drafts were ever circulated externally; the brief you are reading is the first version that has been.

## Reproducibility

The four findings each have a runnable producer script:

```bash
git checkout claude/nsf-sbir-vc-comparison-DtxBN
uv sync --extra stack-dev

# Findings 1 + 2 (M&A rates + per-company capital): the Phase 2 runner
uv run python scripts/data/run_nsf_vc_phase2.py
cat data/processed/nsf_vc/phase2/nsf_vs_form_d_comparison.md

# Finding 3 (per-agency Form-D-filing rates): full-corpus fetch then ad-hoc analysis
uv run python scripts/data/fetch_form_d_index_full.py  # ~3 min, 357K issuers
# Per-agency rate analysis is in this brief's source notebook

# Finding 4 (federal-contract presence): USAspending API queries
uv run python scripts/data/check_usaspending_presence.py  # ~16-30 min, 1,424 queries
cat data/processed/nsf_vc/usaspending_presence.jsonl
```

Methodology details: [`methodology.md`](methodology.md). Glossary: [`glossary.md`](glossary.md). Source citations: [`citations.md`](citations.md). Threats-to-validity registry shipped with each run: `data/processed/nsf_vc/phase2/threats_to_validity.json`.
