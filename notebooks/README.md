# SBIR Analytics Notebooks (Cloud-Native)

This directory contains Jupyter notebooks for interactive analysis of SBIR data, fiscal returns, and CET classification.

**Note:** These notebooks are designed to work with **cloud resources** (S3, HuggingFace). Ensure you have configured your environment correctly.

## Prerequisites

1. **Install ML Dependencies:**

    ```bash
    make install-ml
    ```

    This installs the `stack-dev` extra (first-party packages) and the
    `notebooks` dependency group (jupyter, matplotlib, seaborn). For local
    ModernBERT/GPU inference, additionally run:

    ```bash
    uv pip install -e "packages/sbir-ml[modernbert-local]"
    ```

2. **Configure Environment:**

    ```bash
    make setup-ml
    ```

    - Enables S3 usage (`use_s3_first=true`).
    - Ensures `HF_TOKEN` is present in `.env` (required for ModernBert/CET models).

## Running Notebooks

Start the Jupyter Lab server:

```bash
make notebook
```

## Available Notebooks

- `getting_started.ipynb`: Introduction to loading data from S3 and initializing models.
