# SBIR Federal Spending vs Form D Private Capital (2009-2024)

**Date:** 2026-04-23
**Branch:** `claude/integrate-sec-edgar-sbir-6Krd1`

## Summary

For every $1 of federal SBIR funding, SBIR companies raised between
$1.82 and $2.37 in private capital via SEC Regulation D offerings,
depending on match confidence tier.

| Confidence Filter | Nominal Ratio | Companies |
|-------------------|---------------|-----------|
| High + Medium | 2.37x | 4,760 |
| High only | 1.82x | 3,640 |

These ratios measure a **different channel** than the commonly cited
NASEM 4:1 benchmark. NASEM measures follow-on *federal contracts* (FPDS);
this analysis measures *private capital* raised through Reg D filings.
The two are complementary, not comparable.

## Methodology

**SBIR data**: Bulk awards download from sbir.gov (219K awards). Federal
spending = sum of `Award Amount` by `Award Year`.

**Form D data**: SEC EDGAR Form D XML filings matched to SBIR companies
via company name fuzzy matching, with confidence scoring based on
PI-to-executive name matching, address matching, and state overlap.
Private capital = `totalAmountSold` (actual capital accepted by
investors), not `totalOfferingAmount` (intended raise target).

**Confidence tiers** (rule-based, two independent confirmation signals):
- **High**: PI name matches a Form D executive (person_score >= 0.7)
  OR SBIR ZIP code matches Form D issuer ZIP — 3,640 companies
- **Medium**: Neither person nor address match, but SBIR state matches
  Form D state — 1,120 companies
- **Low**: No confirming signal beyond name match, excluded from
  analysis — 5,645 companies

Address matching was added to address a structural limitation of
person matching for HHS/NIH companies, where the SBIR PI is often
an academic researcher who does not appear as an officer on the
company's Form D filing. See "HHS/NIH and Address Matching" below.

**Industry group exclusions**: Offerings in industry groups structurally
incompatible with SBIR companies are excluded: Insurance, Lodging and
Conventions, Other Travel, Pooled Investment Fund, Restaurants, Retailing,
Tourism and Travel Services. Pooled Investment Fund entities (520 companies,
92% low-tier) are VC/PE fund vehicles, not operating company raises; 71
cross-links to SBIR companies via shared persons/CIKs were identified
for future investor-relationship mapping.

**Exclusions**: 2025 excluded (partial year for both SBIR awards and
Form D filings).

## Results — SBIR vs Private Capital by Year

| Year | SBIR Federal | Form D (H+M) | Ratio (H+M) | Form D (High) | Ratio (High) |
|------|-------------|--------------|-------------|---------------|-------------|
| 2009 | $2.39B | $3.27B | 1.37x | $2.36B | 0.99x |
| 2010 | $2.60B | $10.94B | 4.22x | $3.34B | 1.29x |
| 2011 | $2.31B | $4.84B | 2.09x | $3.40B | 1.47x |
| 2012 | $2.27B | $4.07B | 1.79x | $3.13B | 1.38x |
| 2013 | $2.13B | $4.00B | 1.88x | $2.74B | 1.29x |
| 2014 | $2.34B | $4.96B | 2.12x | $3.84B | 1.64x |
| 2015 | $2.50B | $5.61B | 2.24x | $4.68B | 1.87x |
| 2016 | $2.68B | $5.04B | 1.88x | $3.89B | 1.45x |
| 2017 | $3.19B | $7.74B | 2.43x | $4.95B | 1.55x |
| 2018 | $2.85B | $7.81B | 2.74x | $6.91B | 2.43x |
| 2019 | $3.82B | $7.22B | 1.89x | $5.96B | 1.56x |
| 2020 | $3.96B | $8.63B | 2.18x | $7.39B | 1.87x |
| 2021 | $3.84B | $17.77B | 4.63x | $15.18B | 3.96x |
| 2022 | $4.49B | $10.34B | 2.30x | $9.23B | 2.06x |
| 2023 | $4.72B | $8.44B | 1.79x | $7.49B | 1.59x |
| 2024 | $4.90B | $9.93B | 2.02x | $8.43B | 1.72x |
| **Total** | **$50.97B** | **$120.61B** | **2.37x** | **$92.96B** | **1.82x** |

## Debt vs Equity Composition

SBIR companies have steadily shifted from debt to equity financing over
the 2009-2024 period. Debt's share of dollar volume dropped from 21% in
2009 to 6% in 2024, reaching a floor of 3% in 2021 (peak VC boom year).

| Year | Equity % | Debt % |
|------|----------|--------|
| 2009 | 79% | 21% |
| 2010 | 87% | 13% |
| 2011 | 82% | 18% |
| 2012 | 76% | 24% |
| 2013 | 81% | 19% |
| 2014 | 87% | 13% |
| 2015 | 87% | 13% |
| 2016 | 87% | 13% |
| 2017 | 92% | 8% |
| 2018 | 93% | 7% |
| 2019 | 90% | 10% |
| 2020 | 90% | 10% |
| 2021 | 97% | 3% |
| 2022 | 89% | 11% |
| 2023 | 92% | 8% |
| 2024 | 94% | 6% |
| **Overall** | **90%** | **10%** |

Percentages are share of equity + debt dollar volume only (excludes
offerings with neither type tagged). An offering can include both
equity and debt securities.

### Instrument combinations

The most common offering structures (high+medium tier, excluding
filtered industry groups):

| Structure | Share | Interpretation |
|-----------|-------|----------------|
| Equity alone | 53% | Standard VC/angel equity round |
| Debt + options | 10% | Convertible note with warrants (early-stage bridge) |
| Equity + options | 9% | Preferred equity with warrants (standard VC) |
| Debt alone | 8% | Pure debt — revenue-based or equipment financing |

### Sector comparison

Debt vs equity split is remarkably uniform across SBIR funding agencies.
HHS (bio/health), DoD (defense), NSF, and DOE all show 65-70% equity-only
offerings. The smaller agencies diverge slightly: Agriculture skews more
debt (25%), EPA is the most debt-heavy (31% debt-only).

## Offering Fill Rate (Offered vs Sold)

SBIR companies offered $172B in aggregate and actually sold $120.6B —
a **70% fill rate**. The $51B gap represents unmet capital demand.

| Year | Offered | Sold | Fill Rate |
|------|---------|------|-----------|
| 2009 | $5.2B | $3.3B | 64% |
| 2010 | $13.4B | $10.9B | 81% |
| 2011 | $9.0B | $4.8B | 54% |
| 2012 | $8.5B | $4.1B | 48% |
| 2013 | $8.2B | $4.0B | 49% |
| 2014 | $9.1B | $5.0B | 55% |
| 2015 | $10.1B | $5.6B | 56% |
| 2016 | $7.6B | $5.0B | 67% |
| 2017 | $11.1B | $7.7B | 70% |
| 2018 | $10.5B | $7.8B | 74% |
| 2019 | $9.7B | $7.2B | 74% |
| 2020 | $11.3B | $8.6B | 76% |
| 2021 | $20.5B | $17.8B | 87% |
| 2022 | $13.4B | $10.3B | 77% |
| 2023 | $11.5B | $8.4B | 73% |
| 2024 | $12.8B | $9.9B | 77% |
| **Total** | **$172.0B** | **$120.6B** | **70%** |

The fill rate tracks VC market conditions closely: 48% at the
post-financial-crisis trough (2012), 87% at the 2021 peak, stabilizing
at 73-77% post-correction. Per-offering median fill rate is 80%, but
the 25th percentile is 45% — a quarter of offerings close less than
half their target.

## Private Capital by SBIR Agency

### Aggregate ratio (total Form D $ / total SBIR $)

| Agency | SBIR $ | FD (H+M) | Ratio (H+M) | FD (High) | Ratio (High) | % cos w/ FD (H+M) |
|--------|--------|----------|-------------|-----------|-------------|-------------------|
| NSF | $2.5B | $13.6B | 5.54x | $8.7B | 3.54x | 16% |
| USDA | $0.4B | $2.1B | 5.16x | $1.9B | 4.60x | 11% |
| DHS | $0.3B | $1.1B | 3.86x | $1.0B | 3.47x | 7% |
| NASA | $2.7B | $9.4B | 3.51x | $2.9B | 1.07x | 6% |
| HHS | $16.0B | $50.7B | 3.16x | $42.6B | 2.66x | 27% |
| Commerce | $0.2B | $0.5B | 2.52x | $0.5B | 2.35x | 6% |
| DOE | $4.0B | $7.4B | 1.85x | $6.3B | 1.57x | 10% |
| DoD | $24.5B | $35.0B | 1.43x | $28.5B | 1.16x | 17% |

NSF leads at 5.54x (H+M) / 3.54x (high-only). HHS — previously
the weakest agency in high-only (0.70x with person matching alone) —
now shows 2.66x after address matching recovered companies where the
PI is an academic collaborator rather than a company officer.

### Key agency findings

- **HHS has the highest Form D participation rate** (27% of companies)
  and the largest absolute Form D volume ($50.7B H+M). Address matching
  was critical for HHS — it promoted 1,176 companies from medium to
  high tier.
- **DoD has the lowest ratio** (1.43x H+M / 1.16x high) despite the
  largest SBIR budget. Only 17% of DoD companies raise private capital.
- **NSF punches above its weight** at 5.54x — smaller SBIR awards
  (lower denominator) combined with 16% Form D participation.

## Observations

1. **High-only ratio of 1.82x** is the headline number. For every $1
   of federal SBIR, companies with confirmed matches (person OR address)
   raised $1.82 in private Reg D capital.

2. **H+M ratio is stable at ~2.0-2.5x** across most years, with outliers
   in 2010 (4.22x) and 2021 (4.63x) — both VC boom years.

3. **High-only ratio trends upward** from ~1.0x (2009) to ~1.7x (2024),
   suggesting growing private capital flows to SBIR companies over time.

4. **Debt-to-equity shift** mirrors the broader venture market. As VC
   funding expanded post-2010, SBIR companies gained access to equity
   capital that was previously unavailable to deep-tech startups.

5. **This is not comparable to NASEM's 4:1.** NASEM measures follow-on
   federal contracts (FPDS data). This measures private Reg D capital.
   The two funding channels are additive — SBIR companies access both.

## HHS/NIH and Address Matching

Person matching — the original primary signal for high-tier assignment —
is structurally weaker for HHS/NIH-funded SBIR companies. Before
address matching was added, only 18% of HHS high+medium companies
were high-tier, vs 52-67% for every other agency.

**Root cause**: 88% of person-based high-tier matches are
PI → Executive Officer. For DoD/NSF, the SBIR PI is typically the
company founder/CTO who appears on the Form D as an officer. For
HHS/NIH, the PI is often a university researcher (8.5% have `.edu`
emails; many more are academic with non-institutional email) who
collaborates on the SBIR grant but is not an officer of the
commercializing company.

**Solution**: ZIP code matching between the SBIR company address and
the Form D issuer address provides a PI-independent confirmation
signal. Both data sources have 100% address coverage. ZIP matching
validates at high rates for genuine matches (70% for HHS high-tier,
67% for HHS medium-tier) and at 0% for low-tier (false positives),
confirming its discriminative power.

**Impact**: Address matching promoted 1,620 companies from medium
to high tier (1,617 medium → high, 3 low → high). HHS high-only
ratio improved from 0.70x to 2.66x. The gap between high-only
(1.82x) and H+M (2.37x) is now narrow, meaning the remaining
medium tier (1,120 companies) is genuinely uncertain rather than
a large bucket of unconfirmed matches.

## Caveats

- **Medium tier includes some false positives.** These are state-match-only
  records without person or address confirmation. The true ratio likely
  falls between the high-only (1.82x) and H+M (2.37x) bounds — a
  much narrower range than before address matching (0.88x to 2.37x).

- **Form D captures only Reg D private placements.** Public offerings,
  bank debt, grants, and revenue are not included.

- **Multiple Form D filings per company.** Companies that raise capital
  in multiple rounds have each offering counted in its filing year.
  This is correct for annual flow analysis but means the same company
  contributes to multiple years.

- **totalAmountSold is self-reported.** SEC does not independently verify
  the amounts reported in Form D filings.

- **Pooled Investment Funds excluded.** Fund vehicles matched to SBIR
  company names are excluded from totals. Some are linked to real SBIR
  companies via shared persons/CIKs (71 cross-links identified) — these
  represent potential investor-to-company relationships worth mapping
  in future work.
