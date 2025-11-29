# SBIR Analytics Notebooks (Cloud-Native)

This directory contains Jupyter notebooks for interactive analysis of SBIR data, fiscal returns, and CET classification.

**Note:** These notebooks are designed to work with **cloud resources** (S3, HuggingFace). Ensure you have configured your environment correctly.

## Prerequisites

1.  **Install ML Dependencies:**
    ```bash
    make install-ml
    ```
    This installs `ml`, `paecter-local`, and `r` dependency groups.

2.  **Configure Environment:**
    ```bash
    make setup-ml
    ```
    -   Enables S3 usage (`use_s3_first=true`).
    -   Ensures `HF_TOKEN` is present in `.env` (required for Paecter/CET models).

## Running Notebooks

Start the Jupyter Lab server:

```bash
make notebook
```

## Available Notebooks

-   `getting_started.ipynb`: Introduction to loading data from S3 and initializing models.
