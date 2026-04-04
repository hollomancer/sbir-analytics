#!/usr/bin/env Rscript
#
# R/Python parity test: Leontief I-O math with mocked BEA data.
#
# This script performs the same economic impact calculations as the Python
# BEA adapter, using a synthetic Use table.  The results are written to
# a CSV file that the Python parity test reads and compares.
#
# No external packages required — uses only base R.
#
# Usage:
#   Rscript scripts/r_parity_reference.R <output_dir>

args <- commandArgs(trailingOnly = TRUE)
output_dir <- if (length(args) >= 1) args[1] else "."

# ---------------------------------------------------------------------------
# Mock BEA Use table (6 sectors, values in millions of dollars)
# Sectors loosely inspired by BEA summary codes:
#   11=Agriculture, 21=Mining, 31=Manufacturing,
#   42=Wholesale, 44=Retail, 54=Professional Services
# ---------------------------------------------------------------------------

sectors <- c("11", "21", "31", "42", "44", "54")
n <- length(sectors)

use_values <- matrix(c(
  10,  2,  8,  1,  1,  0,   # row 11: agriculture inputs
   1, 15,  5,  1,  0,  2,   # row 21: mining inputs
   5,  8, 60, 10,  5, 15,   # row 31: manufacturing inputs
   2,  1,  8, 12,  3,  4,   # row 42: wholesale inputs
   1,  0,  3,  2,  8,  2,   # row 44: retail inputs
   3,  5, 12,  6,  4, 30    # row 54: professional services inputs
), nrow = n, ncol = n, byrow = TRUE)

rownames(use_values) <- sectors
colnames(use_values) <- sectors

# ---------------------------------------------------------------------------
# Step 1: Industry output = intermediate inputs + value added
#
# In real BEA tables, total industry output is much larger than the
# intermediate-input column sums because it includes value-added (wages,
# profits, taxes).  We add explicit value-added so that technical
# coefficients stay below 1 and (I - A) is well-conditioned.
# ---------------------------------------------------------------------------
value_added <- c(50, 40, 150, 50, 30, 80)
industry_output <- colSums(use_values) + value_added

# ---------------------------------------------------------------------------
# Step 2: Technical coefficients: A[i,j] = Use[i,j] / Output[j]
# ---------------------------------------------------------------------------
A <- sweep(use_values, 2, industry_output, "/")
# Replace NaN/Inf from zero-output sectors
A[!is.finite(A)] <- 0

# ---------------------------------------------------------------------------
# Step 3: Leontief inverse: L = (I - A)^{-1}
# ---------------------------------------------------------------------------
I_mat <- diag(n)
L <- solve(I_mat - A)

# ---------------------------------------------------------------------------
# Step 4: Demand shock — $1M (in BEA millions = 1.0) to each sector
# ---------------------------------------------------------------------------
shock_results <- data.frame(
  shock_sector = character(),
  target_sector = character(),
  production_impact_millions = numeric(),
  stringsAsFactors = FALSE
)

for (s in sectors) {
  demand <- rep(0, n)
  names(demand) <- sectors
  demand[s] <- 1.0  # $1M shock in millions

  production <- as.numeric(L %*% demand)
  names(production) <- sectors

  for (t in sectors) {
    shock_results <- rbind(shock_results, data.frame(
      shock_sector = s,
      target_sector = t,
      production_impact_millions = production[t],
      stringsAsFactors = FALSE
    ))
  }
}

# ---------------------------------------------------------------------------
# Step 5: Value-Added ratios (mock)
# ---------------------------------------------------------------------------
# Mock VA components as fractions of industry output
va_wages   <- c(0.35, 0.25, 0.30, 0.40, 0.45, 0.50)
va_gos     <- c(0.30, 0.40, 0.25, 0.20, 0.15, 0.20)
va_taxes   <- c(0.10, 0.10, 0.15, 0.10, 0.10, 0.05)
va_propinc <- c(0.05, 0.05, 0.05, 0.10, 0.10, 0.15)

va_ratios <- data.frame(
  sector = sectors,
  wage_ratio = va_wages,
  gos_ratio = va_gos,
  tax_ratio = va_taxes,
  proprietor_income_ratio = va_propinc,
  stringsAsFactors = FALSE
)

# ---------------------------------------------------------------------------
# Step 6: Employment coefficients (jobs per $1M output)
# ---------------------------------------------------------------------------
# Mock employment: total jobs per sector
employment_total <- c(500, 200, 1500, 800, 2000, 1200)
emp_coefficients <- data.frame(
  sector = sectors,
  employment = employment_total,
  employment_coefficient = employment_total / industry_output,
  stringsAsFactors = FALSE
)

# ---------------------------------------------------------------------------
# Step 7: Full impact for $2M shock to sector "31" (Manufacturing)
# ---------------------------------------------------------------------------
shock_amount_millions <- 2.0
demand_31 <- rep(0, n)
names(demand_31) <- sectors
demand_31["31"] <- shock_amount_millions

production_31 <- as.numeric(L %*% demand_31)
names(production_31) <- sectors

# Employment from production
jobs_31 <- production_31 * (employment_total / industry_output)

# VA breakdown for sector 31
full_impact <- data.frame(
  sector = sectors,
  production_impact_millions = production_31,
  production_impact_dollars = production_31 * 1e6,
  employment_impact = jobs_31,
  stringsAsFactors = FALSE
)

# ---------------------------------------------------------------------------
# Write outputs
# ---------------------------------------------------------------------------

# Technical coefficients
write.csv(
  as.data.frame(A),
  file = file.path(output_dir, "r_tech_coefficients.csv"),
  row.names = TRUE
)

# Leontief inverse
write.csv(
  as.data.frame(L),
  file = file.path(output_dir, "r_leontief_inverse.csv"),
  row.names = TRUE
)

# Per-sector shock results
write.csv(
  shock_results,
  file = file.path(output_dir, "r_shock_results.csv"),
  row.names = FALSE
)

# VA ratios
write.csv(
  va_ratios,
  file = file.path(output_dir, "r_va_ratios.csv"),
  row.names = FALSE
)

# Employment coefficients
write.csv(
  emp_coefficients,
  file = file.path(output_dir, "r_employment_coefficients.csv"),
  row.names = FALSE
)

# Full impact for $2M manufacturing shock
write.csv(
  full_impact,
  file = file.path(output_dir, "r_full_impact_31.csv"),
  row.names = FALSE
)

# Industry output
write.csv(
  data.frame(sector = sectors, output = industry_output),
  file = file.path(output_dir, "r_industry_output.csv"),
  row.names = FALSE
)

# Use table
write.csv(
  as.data.frame(use_values),
  file = file.path(output_dir, "r_use_table.csv"),
  row.names = TRUE
)

cat("R parity reference data written to:", output_dir, "\n")
