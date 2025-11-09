#!/usr/bin/env Rscript
# R script to explore StateIO and USEEIOR package APIs
# This script lists exported functions, shows signatures, and tests basic functionality

cat("=== Exploring USEEIOR and StateIO R Packages ===\n\n")

# Function to safely try loading a package
try_load_package <- function(pkg_name) {
  tryCatch({
    library(pkg_name, character.only = TRUE)
    cat(sprintf("✓ Successfully loaded package: %s\n", pkg_name))
    return(TRUE)
  }, error = function(e) {
    cat(sprintf("✗ Failed to load package %s: %s\n", pkg_name, e$message))
    return(FALSE)
  })
}

# Function to list exported functions
list_exported_functions <- function(pkg_name) {
  cat(sprintf("\n--- Exported Functions: %s ---\n", pkg_name))

  tryCatch({
    # Get namespace exports
    ns <- getNamespace(pkg_name)
    exports <- getNamespaceExports(ns)

    cat(sprintf("Total exported functions: %d\n", length(exports)))
    cat("\nFunction names:\n")

    # List functions (limit to first 50 for readability)
    func_list <- sort(exports)
    if (length(func_list) > 50) {
      cat(paste(head(func_list, 50), collapse = ", "))
      cat(sprintf("\n... and %d more functions\n", length(func_list) - 50))
    } else {
      cat(paste(func_list, collapse = ", "))
      cat("\n")
    }

    # Look for key function patterns
    cat("\nKey function patterns:\n")
    key_patterns <- c("build", "load", "model", "calculate", "compute", "impact",
                      "state", "sector", "shock", "demand", "result")

    for (pattern in key_patterns) {
      matches <- grep(pattern, func_list, ignore.case = TRUE, value = TRUE)
      if (length(matches) > 0) {
        cat(sprintf("  '%s': %s\n", pattern, paste(matches, collapse = ", ")))
      }
    }

    return(func_list)

  }, error = function(e) {
    cat(sprintf("Error listing functions: %s\n", e$message))
    return(character(0))
  })
}

# Function to get function signature
get_function_signature <- function(pkg_name, func_name) {
  tryCatch({
    # Try to get function arguments
    func <- get(func_name, envir = getNamespace(pkg_name))
    if (is.function(func)) {
      args <- formals(func)
      sig <- paste(names(args), collapse = ", ")
      return(sprintf("%s(%s)", func_name, sig))
    }
  }, error = function(e) {
    return(sprintf("%s() - unable to get signature", func_name))
  })
  return(NULL)
}

# Function to get help text (first few lines)
get_function_help <- function(func_name) {
  tryCatch({
    help_text <- capture.output(help(func_name, package = NULL, help_type = "text"))
    if (length(help_text) > 0) {
      # Return first 10 lines of help
      return(head(help_text, 10))
    }
  }, error = function(e) {
    return(NULL)
  })
  return(NULL)
}

# ============================================================================
# Explore USEEIOR Package
# ============================================================================

cat("\n" , rep("=", 60), "\n", sep = "")
cat("USEEIOR PACKAGE EXPLORATION\n")
cat(rep("=", 60), "\n\n")

if (try_load_package("useeior")) {
  useeior_funcs <- list_exported_functions("useeior")

  # Try to get more details on key functions
  cat("\n--- Key Function Details ---\n")

  key_funcs <- grep("build|calculate|model|load", useeior_funcs, ignore.case = TRUE, value = TRUE)
  if (length(key_funcs) > 0) {
    for (func in head(key_funcs, 10)) {
      sig <- get_function_signature("useeior", func)
      if (!is.null(sig)) {
        cat(sprintf("\n%s\n", sig))

        # Try to get help
        help_lines <- get_function_help(func)
        if (!is.null(help_lines) && length(help_lines) > 0) {
          cat("Description:", help_lines[1], "\n")
        }
      }
    }
  }

  # Try to understand model structure
  cat("\n--- Testing Model Building ---\n")
  tryCatch({
    # Check if there's a way to list model specifications
    if (exists("getModelSpecifications", envir = getNamespace("useeior"))) {
      cat("Found getModelSpecifications function\n")
    }

    # Try to see example model specs
    if (exists("ModelSpecs", envir = getNamespace("useeior"))) {
      cat("Found ModelSpecs object\n")
    }

  }, error = function(e) {
    cat(sprintf("Could not test model building: %s\n", e$message))
  })
}

# ============================================================================
# Explore StateIO Package
# ============================================================================

cat("\n", rep("=", 60), "\n", sep = "")
cat("STATEIO PACKAGE EXPLORATION\n")
cat(rep("=", 60), "\n\n")

if (try_load_package("stateior") || try_load_package("stateio")) {
  # Try both naming conventions
  pkg_name <- if ("stateior" %in% loadedNamespaces()) "stateior" else "stateio"

  stateio_funcs <- list_exported_functions(pkg_name)

  # Try to get more details on key functions
  cat("\n--- Key Function Details ---\n")

  key_funcs <- grep("build|load|model|state|shock|impact|calculate|compute",
                    stateio_funcs, ignore.case = TRUE, value = TRUE)
  if (length(key_funcs) > 0) {
    for (func in head(key_funcs, 10)) {
      sig <- get_function_signature(pkg_name, func)
      if (!is.null(sig)) {
        cat(sprintf("\n%s\n", sig))

        # Try to get help
        help_lines <- get_function_help(func)
        if (!is.null(help_lines) && length(help_lines) > 0) {
          cat("Description:", help_lines[1], "\n")
        }
      }
    }
  }

  # Test with sample data if possible
  cat("\n--- Testing with Sample Data ---\n")
  tryCatch({
    # Create sample shocks data
    sample_shocks <- data.frame(
      state = c("CA", "NY"),
      sector = c("11", "21"),
      amount = c(1000000, 500000),
      year = c(2023, 2023)
    )

    cat("Sample shocks data created:\n")
    print(sample_shocks)

    # Try to find functions that might work with this
    cat("\nLooking for functions that accept shocks or demand vectors...\n")

  }, error = function(e) {
    cat(sprintf("Could not test with sample data: %s\n", e$message))
  })
}

# ============================================================================
# Integration Patterns
# ============================================================================

cat("\n", rep("=", 60), "\n", sep = "")
cat("INTEGRATION PATTERNS\n")
cat(rep("=", 60), "\n\n")

cat("Looking for integration points between StateIO and USEEIOR...\n")

if ("useeior" %in% loadedNamespaces() && ("stateior" %in% loadedNamespaces() || "stateio" %in% loadedNamespaces())) {
  cat("Both packages loaded - checking for integration functions...\n")

  # Look for functions that mention both packages
  useeior_funcs <- getNamespaceExports(getNamespace("useeior"))
  stateio_funcs <- if ("stateior" %in% loadedNamespaces()) {
    getNamespaceExports(getNamespace("stateior"))
  } else {
    getNamespaceExports(getNamespace("stateio"))
  }

  # Check for state-related functions in USEEIOR
  state_in_useeior <- grep("state", useeior_funcs, ignore.case = TRUE, value = TRUE)
  if (length(state_in_useeior) > 0) {
    cat("USEEIOR functions with 'state':", paste(state_in_useeior, collapse = ", "), "\n")
  }

  # Check for useeio-related functions in StateIO
  useeio_in_stateio <- grep("useeio|eeio", stateio_funcs, ignore.case = TRUE, value = TRUE)
  if (length(useeio_in_stateio) > 0) {
    cat("StateIO functions with 'useeio/eeio':", paste(useeio_in_stateio, collapse = ", "), "\n")
  }
}

# ============================================================================
# Summary
# ============================================================================

cat("\n", rep("=", 60), "\n", sep = "")
cat("EXPLORATION SUMMARY\n")
cat(rep("=", 60), "\n\n")

cat("To generate API reference documentation, run:\n")
cat("  Rscript scripts/explore_r_packages.R > docs/fiscal/r-package-exploration.txt\n\n")

cat("Next steps:\n")
cat("1. Review function lists above\n")
cat("2. Test key functions with sample data\n")
cat("3. Document actual function signatures\n")
cat("4. Create Python wrappers for discovered functions\n")
