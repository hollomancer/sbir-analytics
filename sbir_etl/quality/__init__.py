"""Quality utilities for SBIR ETL.

Epistemic tier: pipelines. Quality checks, baselines, and study-manifest
handling are deterministic gates over declared inputs; they infer nothing.

Submodules: reproduction, study_manifest. Dataset validators live in
``sbir_etl.validators``.
"""

EPISTEMIC_TIER = "pipelines"
