# Navy Phase III transition readout v1

> **Exploratory — non-citable.** Prepared independently in a personal capacity; no agency
> affiliation. Descriptive only—no ranking, statutory undercount claim, causal interpretation,
> or recommendation.

**Frame.** SBIR.gov/FPDS through 2025-09-30; FY2016–FY2025.
“Navy” is SBIR.gov DoD/Navy or strict SR3/ST3 with awarding **or** funding sub-tier 1700.
Compound-key-deduplicated exact-UEI linkage is a same-firm screen, not a project-transition bound.
[Provenance and hashes](navy-transition-v1.summary.json) authenticate local inputs; untracked
snapshots prevent a clean-checkout rebuild.

## A — Coverage and description field

The cohort has 4,828 Phase I, 2,780 Phase II,
and 2,282 strict coded keys (2,000 DoN-awarded;
2,263 DoN-funded; 1,981 both).
1,884 first appear in-window; 398 predate it.

| FY | Phase I award date | Phase II award date | First coded action | Latest coded action |
|---:|---:|---:|---:|---:|
| FY2016 | 458 | 224 | 211 | 229 |
| FY2017 | 533 | 284 | 195 | 203 |
| FY2018 | 433 | 280 | 143 | 139 |
| FY2019 | 409 | 344 | 156 | 126 |
| FY2020 | 704 | 290 | 188 | 136 |
| FY2021 | 493 | 274 | 198 | 174 |
| FY2022 | 382 | 243 | 213 | 200 |
| FY2023 | 411 | 221 | 211 | 197 |
| FY2024 | 472 | 303 | 184 | 283 |
| FY2025 | 533 | 317 | 185 | 595 |

Latest-action descriptions: median 34 characters; ≥40,
902/2,282 (39.5%); ≥150,
177/2,282 (7.8%);
1,740 representatives are nonzero modifications.
FPDS [requires the field and caps newly entered text at 250 characters after 2019-06-28](https://beta.fpds.gov/downloads/Manuals/FPDS_User_Manual_V1.5.pdf);
all 8 later representatives above 250
trace to pre-cap contracts. Thus 900 is cross-vintage-incomparable—not a zero or §638 standard.

The **historical, unreproduced** DoD comparator (n=6,351) reported 53.6% ≥40
and 88.5% <150. Legacy notes disagree on median 42 versus
[43](../../specs/phase3-match-benchmark/mse-dark-phase3.md); no committed generator reproduces or
method-matches it to Navy.

## B — Phase II award-to-coded-signal assignments

Of 2,012 completed Phase II awards (775 firms),
799 (39.7%) map to
315 coded contracts across
157 firms. 159 contracts
cover 643 assignments (maximum reuse,
36). The other
1,213 lack a signal by the cut; this does not establish no transition.

Signed quantiles are assignment-weighted/event-conditional: 525
pre-completion, 274 on/after. No survival estimator is fitted.

| p10 | p20 | p30 | p40 | p50 | p60 | p70 | p80 | p90 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| -1,098 (-3.01) | -854 (-2.34) | -672 (-1.84) | -487 (-1.33) | -322 (-0.88) | -134 (-0.37) | 166 (0.45) | 493 (1.35) | 971 (2.66) |

*Cells: signed days (years) from Phase II period end; n=799
Phase-II-award assignments.*

| A. Description ECDF with FPDS cap | B. Conditional signed-latency ECDF |
|:---:|:---:|
| ![Description ECDF](figures/navy-transition-v1-description-cdf.png) | ![Latency ECDF](figures/navy-transition-v1-latency.png) |

## C — Description emptiness versus NAICS/PSC missingness

n=2,282: blank description=0, missing
NAICS=1, missing PSC=0. Correlation was not estimable because at least one binary input was constant; Panel C is therefore blocked rather than replaced with a different outcome.
Because FPDS requires description, zero blankness mainly reflects source validation—not narrative
richness or an optionality mechanism.

## D — Recent external capital/acquisition signals

Among 1,686 normalized Navy firms, 47
have positive non-combination Form D filings in 2024-09-01–2026-08-31
(43 high-confidence;
4 medium). This is filing participation—not
verified capital or SBIR attribution. EFTS lacks acquisition-specific dates, blocking that branch
and the union. No names are emitted.

## Quality audit and published context

**Infrastructure finding.** The 900-character value had leaked into shared benchmark diagnostics,
not the FPDS parser, which preserves source text. This revision centralizes the official required/250
constraint, rejects larger benchmark thresholds, and removes unqualified “lower-bound” and
Kaplan–Meier-ready metadata. The defect was in research-evaluation semantics, not core ingestion.

- [GAO-25-107942](https://files.gao.gov/reports/GAO-25-107942/index.html) and
  [NASEM 2026](https://www.nationalacademies.org/read/29329/chapter/9) find Phase III tracking
  incomplete; this supports the coverage caution, not a Navy estimate.
- The closest Navy study, [Rovito, Kamp, and Etemadi (2025)](https://doi.org/10.1007/s10961-024-10141-2),
  says Phase III receipt is not strongly predictive of broader commercialization. Its different
  linkage/prediction design still cannot validate this readout.
- An [NRC NIH assessment](https://www.nationalacademies.org/read/11964/chapter/6) says first sales can
  precede Phase II completion, making negative times plausible but not validating these matches. The
  event-only ECDF excludes censored follow-up and is not [Kaplan–Meier](https://doi.org/10.1080/01621459.1958.10501452).
- [NRC 2014](https://www.nationalacademies.org/read/18821/chapter/5) reports commercialization
  near 45–50%, which is not comparable to this signal rate. [Howell (2017)](https://www.aeaweb.org/articles?id=10.1257/aer.20150808)
  supports finance as an outcome; [SEC methodology](https://www.sec.gov/files/dera-white-paper_regulation-d_082018.pdf)
  shows Form D is incomplete and self-reported, with no Navy-SBIR attribution here.

**Bottom line.** The results are a reproducible local map of observed public signals, not a complete
commercialization measure. Coding and identity misses can bias downward; unrelated same-firm matches,
contract reuse, modifications, and name matching can bias upward. Nothing here identifies a mechanism.
