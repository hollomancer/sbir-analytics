#!/usr/bin/env python
"""Verify R and required packages are installed correctly.

Usage:
    python scripts/verify_r_setup.py
"""

import sys
from importlib import metadata


def check_rpy2():
    """Check if rpy2 is installed."""
    try:
        import rpy2

        version = getattr(rpy2, "__version__", None)
        if version is None:
            try:
                version = metadata.version("rpy2")
            except metadata.PackageNotFoundError:
                version = "unknown"

        print(f"✓ rpy2 installed (version {version})")
        return True
    except ImportError:
        print("✗ rpy2 NOT installed")
        print("  Install with: uv sync --extra r")
        return False


def check_r_available():
    """Check if R is available."""
    try:
        import rpy2.robjects as ro
        r_version = ro.r('R.version.string')[0]
        print(f"✓ R available ({r_version})")
        return True
    except Exception as e:
        print(f"✗ R NOT available: {e}")
        print("  Install R: brew install r (macOS) or apt-get install r-base (Linux)")
        return False


def check_r_package(package_name: str) -> bool:
    """Check if an R package is installed."""
    try:
        from rpy2.robjects.packages import importr

        pkg = importr(package_name)
        print(f"✓ R package '{package_name}' installed")
        return True
    except Exception as e:
        print(f"✗ R package '{package_name}' NOT installed: {e}")
        print(f"  Install with: R -e \"remotes::install_github('USEPA/{package_name}')\"")
        return False


def check_stateio_functions():
    """Check if StateIO functions are accessible."""
    try:
        from rpy2.robjects.packages import importr
        import rpy2.robjects as ro

        stateio = importr("stateior")

        # Try to call a function to verify it works
        ro.r('library(stateior)')

        # Check if key functions exist
        functions_to_check = [
            "buildFullTwoRegionIOTable",
            "getStateGVA",
            "getStateEmpCompensation",
        ]

        for func in functions_to_check:
            if hasattr(stateio, func):
                print(f"  ✓ Function '{func}' available")
            else:
                print(f"  ✗ Function '{func}' NOT found")
                return False

        return True

    except Exception as e:
        print(f"✗ Failed to verify StateIO functions: {e}")
        return False


def check_useeior_functions():
    """Check if USEEIOR functions are accessible."""
    try:
        from rpy2.robjects.packages import importr
        import rpy2.robjects as ro

        useeior = importr("useeior")

        # Try to call a function to verify it works
        ro.r('library(useeior)')

        # Check if key functions exist
        functions_to_check = [
            "buildTwoRegionModels",
            "calculateEEIOModel",
            "buildModel",
        ]

        for func in functions_to_check:
            if hasattr(useeior, func):
                print(f"  ✓ Function '{func}' available")
            else:
                print(f"  ✗ Function '{func}' NOT found")
                return False

        return True

    except Exception as e:
        print(f"✗ Failed to verify USEEIOR functions: {e}")
        return False


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("R Setup Verification for SBIR Fiscal Impact Analysis")
    print("=" * 60)
    print()

    all_passed = True

    # Check rpy2
    print("1. Checking rpy2 (Python-R interface)...")
    if not check_rpy2():
        all_passed = False
        print()
        return 1
    print()

    # Check R
    print("2. Checking R installation...")
    if not check_r_available():
        all_passed = False
        print()
        return 1
    print()

    # Check StateIO
    print("3. Checking StateIO R package...")
    if not check_r_package("stateior"):
        all_passed = False
    else:
        print("   Checking StateIO functions...")
        if not check_stateio_functions():
            all_passed = False
    print()

    # Check USEEIOR
    print("4. Checking USEEIOR R package...")
    if not check_r_package("useeior"):
        all_passed = False
    else:
        print("   Checking USEEIOR functions...")
        if not check_useeior_functions():
            all_passed = False
    print()

    # Summary
    print("=" * 60)
    if all_passed:
        print("✓ ALL CHECKS PASSED - R setup is complete!")
        print()
        print("You can now run fiscal impact calculations:")
        print("  python examples/sbir_fiscal_impact_example.py")
    else:
        print("✗ SOME CHECKS FAILED - See errors above")
        print()
        print("Quick fix commands:")
        print("  1. Install rpy2: uv sync --extra r")
        print("  2. Install R: brew install r (macOS)")
        print("  3. Install R packages:")
        print("     R -e \"install.packages('remotes')\"")
        print("     R -e \"remotes::install_github('USEPA/stateior')\"")
        print("     R -e \"remotes::install_github('USEPA/useeior')\"")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
