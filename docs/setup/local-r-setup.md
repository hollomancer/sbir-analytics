# Local R Setup for Fiscal Impact Analysis

This guide helps you set up R and required packages (StateIO) for local development.

## Quick Start

### 1. Install R

**macOS:**

```bash
brew install r
```

**Linux (Ubuntu/Debian):**

```bash
sudo apt-get update
sudo apt-get install -y r-base r-base-dev \
    libcurl4-openssl-dev libssl-dev libxml2-dev libfontconfig1-dev
```

**Windows:**

- Download from <https://cran.r-project.org/bin/windows/base/>
- Run installer and add to PATH

### 2. Install Python rpy2

```bash
uv sync --extra r
```

### 3. Install R Packages

```bash
R -e "install.packages('remotes'); remotes::install_github('USEPA/stateior')"
```

### 4. Verify Installation

```bash
python scripts/verify_r_setup.py
```

You should see:

```
✓ ALL CHECKS PASSED - R setup is complete!
```

---

## Detailed Installation

### Step-by-Step R Package Installation

If the one-liner fails, install packages manually:

1. **Start R console:**

   ```bash
   R
   ```

2. **In R console, run:**

   ```r
   # Install remotes (needed for GitHub packages)
   install.packages("remotes")

   # Install StateIO
   remotes::install_github("USEPA/stateior")

   # Verify
   library(stateior)

   # Exit
   quit()
   ```

### First-Time Setup Issues

#### Issue: "non-zero exit status" during package install

**Cause:** Missing system dependencies

**macOS fix:**

```bash
brew install libxml2 openssl
```

**Linux fix:**

```bash
sudo apt-get install -y \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    libharfbuzz-dev \
    libjpeg-dev \
    libpng-dev
```

#### Issue: "cannot load shared object" or rpy2 import error

**Cause:** R_HOME environment variable not set

**Fix:**

```bash
# Find R home
R RHOME

# Add to your shell config (~/.bashrc or ~/.zshrc)
export R_HOME=/usr/local/lib/R  # Use path from R RHOME

# Reload
source ~/.bashrc  # or source ~/.zshrc
```

#### Issue: Package downloads are slow

**Cause:** Default CRAN mirror is slow

**Fix:** Use a faster mirror in R:

```r
# Set CRAN mirror before installing
options(repos = c(CRAN = "https://cloud.r-project.org/"))

# Then install packages
remotes::install_github("USEPA/stateior")
```

---

## Verification

### Manual Verification

Test in Python:

```python
# Test rpy2
import rpy2.robjects as ro
print(ro.r('R.version.string'))

# Test StateIO
from rpy2.robjects.packages import importr
stateio = importr("stateior")
print("StateIO loaded successfully!")

```

### Automatic Verification

Use the provided script:

```bash
python scripts/verify_r_setup.py
```

**Expected output:**

```
============================================================
R Setup Verification for SBIR Fiscal Impact Analysis
============================================================

1. Checking rpy2 (Python-R interface)...
✓ rpy2 installed (version 3.5.x)

2. Checking R installation...
✓ R available (R version 4.3.x)

3. Checking StateIO R package...
✓ R package 'stateior' installed
   Checking StateIO functions...
  ✓ Function 'buildFullTwoRegionIOTable' available
  ✓ Function 'getStateGVA' available
  ✓ Function 'getStateEmpCompensation' available

============================================================
✓ ALL CHECKS PASSED - R setup is complete!
============================================================
```

---

## Testing Your Setup

### Run the Example

```bash
python examples/sbir_fiscal_impact_example.py
```

**Expected behavior:**

- Should run without errors
- Should show tax and job impact calculations
- Should NOT show "placeholder_computation" quality flags

### Run Unit Tests

```bash
# Run R-related tests (requires pytest)
pytest tests/unit/transformers/test_r_stateio_functions.py -v
pytest tests/unit/transformers/test_r_stateio_adapter.py -v
```

---

## Alternative: Use Docker (Recommended)

If local setup is problematic, use Docker instead:

```bash
# Build Docker image (R packages pre-installed)
docker build -t sbir-analytics:latest .

# Run inside container
docker run -it sbir-analytics:latest bash

# Inside container, run example
python examples/sbir_fiscal_impact_example.py
```

Docker includes:

- ✅ R pre-installed
- ✅ StateIO pre-installed
- ✅ All system dependencies
- ✅ rpy2 configured correctly

---

## Package Versions

**Tested versions:**

- R: 4.3.0+
- rpy2: 3.5.0+
- StateIO: Latest from GitHub

**Compatibility:**

- Python: 3.11+
- Operating Systems: macOS, Linux, Windows (WSL recommended)

---

## Troubleshooting

### "Error in library(stateior): there is no package called 'stateior'"

**Fix:** Package not installed. Run:

```bash
R -e "remotes::install_github('USEPA/stateior')"
```

### "Failed to load StateIO R package"

**Check:**

1. R is installed: `R --version`
2. Package is installed: `R -e "library(stateior)"`
3. rpy2 can find R: `python -c "import rpy2; print(rpy2.__version__)"`

### "Quality flags show 'placeholder_computation'"

**Cause:** R packages not available or failed to load

**Check logs:** Look for warnings about StateIO not loading

**Verify:** Run `python scripts/verify_r_setup.py`

---

## Getting Help

If setup fails after following this guide:

1. **Run verification script:**

   ```bash
   python scripts/verify_r_setup.py
   ```

2. **Check logs:** Look for specific error messages

3. **Common solutions:**
   - Reinstall R: `brew reinstall r`
   - Clear R package cache: `rm -rf ~/Library/R` (macOS)
   - Use Docker instead (easiest option)

4. **Still stuck?** Share the output of:

   ```bash
   R --version
   python -c "import rpy2; print(rpy2.__version__)"
   python scripts/verify_r_setup.py
   ```

---

## References

- **R Installation**: <https://www.r-project.org/>
- **StateIO GitHub**: <https://github.com/USEPA/stateior>
- **rpy2 Documentation**: <https://rpy2.github.io/>
- **Docker Setup**: `Dockerfile` in project root
