#!/usr/bin/env bash
# Quick test runner for new rawaward tests

# Activate venv
source .venv/bin/activate

# Run the new tests
python -m pytest tests/unit/test_sbir_extractor.py -k "rawaward" -v
