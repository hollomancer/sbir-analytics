# Open-Source Tax Impact Modeling for SBIR Fiscal Returns

**Date:** 2026-04-19
**Status:** Research / Pre-spec
**Relates to:** `sbir_etl/enrichers/fiscal_bea_mapper.py`, `docs/fiscal/`

## Problem

The fiscal returns module currently uses BEA Input-Output tables (via stateior) to calculate economic multipliers — how $1 of SBIR spending ripples through the economy via direct, indirect, and induced effects. But multipliers alone don't answer the policy question:

> "For every $1 the federal government invests in SBIR, how much comes back as tax revenue?"

IMPLAN answers this with proprietary tax impact modules that map industry output to federal, state, and local tax receipts. We need an open-source equivalent.

## What IMPLAN Does (the benchmark)

IMPLAN's tax impact analysis takes industry output and produces:

1. **Federal taxes**: income tax, payroll tax (FICA), corporate income tax, excise taxes, customs duties
2. **State taxes**: income tax, sales tax, corporate tax, property tax (commercial)
3. **Local taxes**: property tax, local sales tax, local income tax (where applicable)

The key mapping is: **industry output → compensation by type → tax liability by jurisdiction**.

IMPLAN uses proprietary datasets from BLS, BEA, Census, and IRS to build effective tax rate matrices by industry, income bracket, and geography.

## Open-Source Tools Evaluated

### Input-Output / Economic Multipliers

| Tool | Source | What it provides | Tax revenue? |
|------|--------|------------------|-------------|
| **stateior** | EPA | State-level I-O tables, Make/Use matrices | No |
| **BEA I-O Tables** | BEA | National industry-by-industry total requirements | No |
| **USEEIO** | EPA | Environmentally-extended I-O | No (environmental impacts only) |

### Tax Microsimulation

| Tool | Source | What it provides | Usable for fiscal impact? |
|------|--------|------------------|--------------------------|
| **Tax-Calculator** | PSLmodels | Federal income + payroll tax from household data | Yes — needs income distribution inputs |
| **TAXSIM** | NBER | Federal + state income tax from individual returns | Yes — individual level only |
| **OG-USA** | PSLmodels | Overlapping-generations macro model, tax revenue streams | Partially — too coarse for program-level ROI |

### Effective Tax Rate Data

| Source | What it provides | Coverage |
|--------|------------------|----------|
| **IRS SOI** | Statistics of Income by industry, income bracket | Federal |
| **Census ASGF** | Annual Survey of Government Finances | State + Local |
| **BEA Regional Accounts** | Compensation by industry by state | State-level income |
| **BLS QCEW** | Quarterly Census of Employment & Wages by industry | County-level wages |

## Proposed Architecture

Chain existing open-source tools to replicate IMPLAN's tax impact flow:

```
BEA I-O Multipliers (stateior)
        │
        ▼
Industry Output by Sector (direct + indirect + induced)
        │
        ▼
BEA Regional Accounts + BLS QCEW
    → Employee compensation by industry by state
    → Proprietor income by industry by state
        │
        ▼
Income Distribution Mapping
    → IRS SOI tables: industry compensation → income bracket distribution
    → Representative household profiles per industry/state
        │
        ├──────────────────────┐
        ▼                      ▼
Tax-Calculator              TAXSIM
(federal income +           (state income tax)
 payroll tax)
        │                      │
        ▼                      ▼
Federal Tax Receipts     State Tax Receipts
        │                      │
        └──────┬───────────────┘
               ▼
    Census ASGF effective rates
    → Local tax estimates (property, sales)
               │
               ▼
    Total Tax Impact by Jurisdiction
```

### Step-by-step

1. **Start with I-O output** (already have this): SBIR spending → industry multipliers → total economic output, employee compensation, proprietor income by sector.

2. **Map compensation to income distributions**: Use IRS Statistics of Income (SOI) to map industry-level compensation to representative income bracket distributions. SOI Table 1 provides returns by AGI bracket; SOI Table 2 provides returns by business type.

3. **Generate representative tax units**: For each industry-state combination, create synthetic household profiles matching the income distribution. This is the bridge IMPLAN builds internally.

4. **Run Tax-Calculator**: Feed synthetic profiles into PSLmodels Tax-Calculator to estimate federal income tax + payroll tax (FICA/SECA). Tax-Calculator handles current-law rates, brackets, credits, deductions.

5. **Run TAXSIM for state taxes**: Feed the same profiles into NBER TAXSIM to estimate state income tax by jurisdiction.

6. **Estimate local taxes**: Apply effective property/sales tax rates from Census ASGF to the estimated consumption and commercial property values implied by the industry output.

7. **Aggregate**: Sum federal + state + local = total tax impact per $ of SBIR spending.

## Complexity Assessment

| Step | Difficulty | Data availability | Notes |
|------|-----------|-------------------|-------|
| I-O multipliers | Done | stateior ✓ | Already in the codebase |
| Compensation by industry/state | Easy | BEA REA public | Annual updates, API available |
| Income bracket distribution | Medium | IRS SOI public | Need industry-to-bracket crosswalk |
| Synthetic tax unit generation | Hard | N/A (compute) | This is the key engineering challenge |
| Tax-Calculator integration | Medium | Open source ✓ | Python, well-documented API |
| TAXSIM integration | Medium | Free access | Web API or local install |
| Local tax estimation | Easy | Census ASGF public | Effective rate approach sufficient |
| **End-to-end validation** | **Hard** | IMPLAN comparisons | Need known-good benchmark |

**Total estimated effort:** 2-4 weeks for a basic implementation, another 2-4 weeks for validation against IMPLAN benchmarks.

## Key Risks

1. **Synthetic tax unit quality**: The entire approach depends on generating realistic income distributions from industry-level aggregates. Bad distributions → bad tax estimates. IRS SOI provides the right data but the crosswalk is non-trivial.

2. **TAXSIM access model**: TAXSIM is free but runs as a web service (or local Fortran install). Rate limits and availability could be an issue at scale.

3. **Validation**: Without access to IMPLAN results for the same inputs, validating the tax estimates is difficult. Could use published SBIR impact studies that used IMPLAN as benchmarks.

4. **Maintenance**: Tax law changes annually. Tax-Calculator tracks federal law; TAXSIM tracks state law. Both need to be kept current.

## Prior Art

- **Bartik (2012)** "Including Jobs in Benefit-Cost Analysis" — establishes the methodology for translating employment impacts to fiscal impacts using effective tax rates.
- **Weinstein & Partridge (2023)** — comparison of I-O model outputs (IMPLAN vs RIMS II) for regional economic analysis.
- **NASEM (2022)** "The Role of SBIR/STTR Programs in Supporting the U.S. Innovation Ecosystem" — uses IMPLAN for fiscal return estimates, could serve as validation benchmark.

## Recommendation

Start with the simplest version that produces defensible numbers:

1. Use BEA effective tax rates by industry (available in the National Income and Product Accounts, Table 3.6) rather than microsimulation. This gives federal corporate + individual income tax as a fraction of industry value-added.

2. Apply BEA Personal Tax Rates (NIPA Table 3.4) to the employee compensation from I-O multipliers. This avoids the synthetic tax unit problem entirely.

3. Use Census ASGF state/local effective rates as-is.

This "effective rate" approach is less precise than full microsimulation but is much simpler, fully reproducible, and defensible for policy analysis. It's essentially what GAO and CRS use in their SBIR program evaluations.

**Save the full Tax-Calculator/TAXSIM microsimulation chain for a later iteration** where precision matters more than simplicity.

## Dependencies

```
pip install taxcalc    # PSLmodels Tax-Calculator
# TAXSIM: web API at https://taxsim.nber.org/taxsim35/
# stateior: already in use
# BEA API: already in use
```

## Next Steps

- [ ] Prototype the "effective rate" approach using BEA NIPA Tables 3.4 and 3.6
- [ ] Compare output against published IMPLAN-based SBIR fiscal impact numbers
- [ ] If effective rates are sufficient, integrate into `fiscal_bea_mapper.py`
- [ ] If more precision needed, prototype Tax-Calculator integration
