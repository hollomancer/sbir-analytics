#!/usr/bin/env Rscript
#
# Generate reference values from the R/StateIO package for equivalency testing.
#
# Usage:
#   Rscript scripts/generate_r_reference_values.R
#
# Output:
#   tests/fixtures/r_reference_values.json
#
# This script requires:
#   - R 4.x with the stateior package installed
#   - install.packages("stateior")
#   - install.packages("jsonlite")
#
# Run this ONCE on a machine with R installed to produce the reference fixture.
# The fixture is then checked into the repo so CI doesn't need R.

library(stateior)
library(jsonlite)

cat("Generating R/StateIO reference values for equivalency testing...\n")

# --- Test case 1: Technical coefficients for 2020 summary Use table ---
cat("  Fetching 2020 Use table...\n")
use_2020 <- stateior::get_use_table(year = 2020, level = "summary")
industry_output <- colSums(use_2020)
# Avoid division by zero
industry_output[industry_output == 0] <- 1e-10
tech_coeff <- sweep(use_2020, 2, industry_output, "/")
# First 5x5 block for compact reference
tc_5x5 <- as.data.frame(tech_coeff[1:5, 1:5])

# --- Test case 2: Leontief inverse ---
cat("  Computing Leontief inverse...\n")
I <- diag(nrow(tech_coeff))
leontief_inv <- solve(I - as.matrix(tech_coeff))
li_5x5 <- as.data.frame(leontief_inv[1:5, 1:5])

# --- Test case 3: Demand shock application ---
cat("  Applying demand shocks...\n")
# $1M shock to sector "11" (Agriculture)
demand_vector <- rep(0, ncol(leontief_inv))
names(demand_vector) <- colnames(leontief_inv)
demand_vector["11"] <- 1.0  # $1M in millions

production_impact <- as.numeric(leontief_inv %*% demand_vector)
names(production_impact) <- rownames(leontief_inv)

# --- Test case 4: Value Added ratios ---
cat("  Fetching Value Added table...\n")
va_2020 <- tryCatch(
  stateior::get_value_added(year = 2020, level = "summary"),
  error = function(e) NULL
)
va_ratios <- NULL
if (!is.null(va_2020)) {
  total_va <- colSums(va_2020)
  # Extract component rows by name pattern
  comp_rows <- grep("compensation|wages", rownames(va_2020), ignore.case = TRUE)
  gos_rows <- grep("surplus", rownames(va_2020), ignore.case = TRUE)
  tax_rows <- grep("tax", rownames(va_2020), ignore.case = TRUE)

  if (length(comp_rows) > 0 && length(gos_rows) > 0 && length(tax_rows) > 0) {
    wage_share <- colSums(va_2020[comp_rows, , drop = FALSE]) / total_va
    gos_share <- colSums(va_2020[gos_rows, , drop = FALSE]) / total_va
    tax_share <- colSums(va_2020[tax_rows, , drop = FALSE]) / total_va

    # First 5 sectors
    va_ratios <- data.frame(
      sector = names(total_va)[1:5],
      wage_ratio = as.numeric(wage_share[1:5]),
      gos_ratio = as.numeric(gos_share[1:5]),
      tax_ratio = as.numeric(tax_share[1:5])
    )
  }
}

# --- Assemble reference fixture ---
reference <- list(
  metadata = list(
    generated_by = "scripts/generate_r_reference_values.R",
    stateior_version = as.character(packageVersion("stateior")),
    r_version = paste(R.version$major, R.version$minor, sep = "."),
    year = 2020,
    level = "summary",
    description = paste(
      "Reference values from R/StateIO for validating Python BEA API",
      "implementation equivalency. Generated once, checked into repo."
    )
  ),
  tech_coefficients_5x5 = list(
    sectors = colnames(tc_5x5),
    values = as.list(tc_5x5)
  ),
  leontief_inverse_5x5 = list(
    sectors = colnames(li_5x5),
    values = as.list(li_5x5)
  ),
  demand_shock_1m_sector_11 = list(
    shock_sector = "11",
    shock_amount_millions = 1.0,
    production_impact = as.list(production_impact),
    total_output = sum(production_impact)
  ),
  value_added_ratios = va_ratios
)

# Write to fixture file
output_path <- "tests/fixtures/r_reference_values.json"
dir.create(dirname(output_path), showWarnings = FALSE, recursive = TRUE)
write_json(reference, output_path, pretty = TRUE, auto_unbox = TRUE)
cat(sprintf("  Written to %s\n", output_path))
cat("Done.\n")
