"""Dagster assets for PaECTER embedding generation and similarity computation.

This module provides assets for:
- Generating PaECTER embeddings for SBIR awards
- Generating PaECTER embeddings for USPTO patents
- Computing similarity scores between awards and patents
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from dagster import AssetCheckResult, AssetCheckSeverity, MetadataValue, Output, asset, asset_check

from ...config.loader import get_config
from ...ml.config import PaECTERClientConfig
from ...ml.paecter_client import PaECTERClient
from ...utils.asset_column_helper import AssetColumnHelper
from ...utils.config_accessor import ConfigAccessor
from ...utils.monitoring import performance_monitor


@asset(
    description="PaECTER embeddings for SBIR awards",
    group_name="paecter",
    compute_kind="ml",
    io_manager_key="parquet_io_manager",
)
def paecter_embeddings_awards(
    context,
    validated_sbir_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Generate PaECTER embeddings for SBIR awards.

    Args:
        validated_sbir_awards: Validated SBIR awards DataFrame

    Returns:
        DataFrame with award_id, embedding, and metadata
    """
    config = get_config()

    context.log.info(
        "Starting PaECTER embedding generation for SBIR awards",
        extra={"award_count": len(validated_sbir_awards)},
    )

    # Initialize PaECTER client
    use_local = ConfigAccessor.get_nested(config, "ml.paecter.use_local", False)
    client = PaECTERClient(config=PaECTERClientConfig(use_local=use_local))

    # Find award ID column using helper
    award_id_col = AssetColumnHelper.find_award_id_column(validated_sbir_awards)
    if not award_id_col:
        award_ids = validated_sbir_awards.index.astype(str)
        context.log.warning("No award ID column found, using index")
    else:
        award_ids = validated_sbir_awards[award_id_col].astype(str)

    # Find text columns using helper
    text_cols = AssetColumnHelper.find_text_columns(validated_sbir_awards, entity_type="award")
    solicitation_col = text_cols.get("solicitation")
    title_col = text_cols.get("title")
    abstract_col = text_cols.get("abstract")

    # Prepare texts
    texts = []
    for _, row in validated_sbir_awards.iterrows():
        solicitation = (
            str(row[solicitation_col])
            if solicitation_col and pd.notna(row.get(solicitation_col))
            else None
        )
        title = str(row[title_col]) if title_col and pd.notna(row.get(title_col)) else None
        abstract = (
            str(row[abstract_col]) if abstract_col and pd.notna(row.get(abstract_col)) else None
        )

        # Clean NaN strings
        for val in [solicitation, title, abstract]:
            if val and val.lower() == "nan":
                val = None

        text = client.prepare_award_text(
            solicitation_title=solicitation,
            abstract=abstract,
            award_title=title,
        )
        texts.append(text)

    # Generate embeddings with performance monitoring
    with performance_monitor.monitor_block("paecter_generate_award_embeddings"):
        batch_size = ConfigAccessor.get_nested(config, "ml.paecter.batch_size", 32)
        result = client.generate_embeddings(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
        )

    # Create output DataFrame
    embeddings_df = pd.DataFrame(
        {
            "award_id": award_ids,
            "embedding": [e.tolist() for e in result.embeddings],
            "model_version": result.model_version,
            "inference_mode": result.inference_mode,
            "dimension": result.dimension,
        }
    )

    context.log.info(
        "PaECTER embeddings generated",
        extra={
            "award_count": len(embeddings_df),
            "model_version": result.model_version,
            "inference_mode": result.inference_mode,
            "dimension": result.dimension,
        },
    )

    return Output(
        embeddings_df,
        metadata={
            "award_count": len(embeddings_df),
            "model_version": result.model_version,
            "inference_mode": result.inference_mode,
            "dimension": result.dimension,
            "generation_time_seconds": result.generation_timestamp,
        },
    )


@asset(
    description="PaECTER embeddings for USPTO patents",
    group_name="paecter",
    compute_kind="ml",
    io_manager_key="parquet_io_manager",
)
def paecter_embeddings_patents(
    context,
    transformed_patents: dict[str, Any],
) -> Output[pd.DataFrame]:
    """
    Generate PaECTER embeddings for USPTO patents.

    Loads patent data from transformed_patents JSONL file or S3 PatentsView data.

    Args:
        transformed_patents: Transformed patents metadata dict (contains output_path)

    Returns:
        DataFrame with patent_id, embedding, and metadata
    """
    import json
    import tempfile
    import zipfile

    import boto3

    config = get_config()

    context.log.info("Starting PaECTER embedding generation for USPTO patents")

    # Initialize PaECTER client
    use_local = ConfigAccessor.get_nested(config, "ml.paecter.use_local", False)
    client = PaECTERClient(config=PaECTERClientConfig(use_local=use_local))

    # Try to load from transformed_patents JSONL file first
    patents_df = None
    if transformed_patents.get("output_path"):
        jsonl_path = Path(transformed_patents["output_path"])
        if jsonl_path.exists():
            context.log.info(f"Loading patents from {jsonl_path}")
            patents = []
            with jsonl_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        patents.append(json.loads(line))
            patents_df = pd.DataFrame(patents)
            context.log.info(f"Loaded {len(patents_df)} patents from JSONL")

    # If no JSONL data, try loading from S3 PatentsView data
    if patents_df is None or len(patents_df) == 0:
        context.log.info("No transformed patents found, loading from S3 PatentsView")
        from ...extractors.uspto_extractor import USPTOExtractor
        from ...utils.cloud_storage import get_s3_bucket_from_env

        bucket = get_s3_bucket_from_env()
        if not bucket:
            raise ValueError("S3 bucket not configured. Set SBIR_ANALYTICS_S3_BUCKET env var.")

        # Default to latest PatentsView patent data
        s3_url = f"s3://{bucket}/raw/uspto/patentsview/2025-11-18/patent.zip"
        context.log.info(f"Loading from S3: {s3_url}")

        # Download and extract
        temp_dir = Path(tempfile.gettempdir()) / "sbir-analytics-paecter"
        temp_dir.mkdir(parents=True, exist_ok=True)
        local_zip = temp_dir / "patentsview.zip"

        s3 = boto3.client("s3")
        parts = s3_url.replace("s3://", "").split("/", 1)
        s3_bucket = parts[0]
        s3_key = parts[1] if len(parts) > 1 else ""
        s3.download_file(s3_bucket, s3_key, str(local_zip))

        # Extract if ZIP
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(local_zip, "r") as zip_ref:
            zip_ref.extractall(extract_dir)

        # Use USPTO extractor to load data
        extractor = USPTOExtractor(input_dir=extract_dir)
        files = extractor.discover_files()

        if not files:
            raise FileNotFoundError(f"No USPTO files found in {extract_dir}")

        # Load data
        all_rows = []
        for file_path in files:
            context.log.info(f"Loading from {file_path.name}")
            for row in extractor.stream_rows(file_path, chunk_size=10000):
                all_rows.append(row)
                if len(all_rows) >= 1000:  # Limit for testing
                    break
            if len(all_rows) >= 1000:
                break

        patents_df = pd.DataFrame(all_rows)
        context.log.info(f"Loaded {len(patents_df)} patents from S3")

    if patents_df is None or len(patents_df) == 0:
        raise ValueError("No patent data available for embedding generation")

    # Find patent ID column using helper
    patent_id_col = AssetColumnHelper.find_patent_id_column(patents_df)
    if not patent_id_col:
        patent_ids = patents_df.index.astype(str)
        context.log.warning("No patent ID column found, using index")
    else:
        patent_ids = patents_df[patent_id_col].astype(str)

    # Find text columns using helper
    text_cols = AssetColumnHelper.find_text_columns(patents_df, entity_type="patent")
    title_col = text_cols.get("title")
    abstract_col = text_cols.get("abstract")

    # Prepare texts
    texts = []
    for _, row in patents_df.iterrows():
        title = str(row[title_col]) if title_col and pd.notna(row.get(title_col)) else None
        abstract = (
            str(row[abstract_col]) if abstract_col and pd.notna(row.get(abstract_col)) else None
        )

        # Clean NaN strings
        if title and title.lower() == "nan":
            title = None
        if abstract and abstract.lower() == "nan":
            abstract = None

        text = client.prepare_patent_text(
            title=title or "",
            abstract=abstract or "",
        )
        texts.append(text)

    # Generate embeddings with performance monitoring
    with performance_monitor.monitor_block("paecter_generate_patent_embeddings"):
        batch_size = ConfigAccessor.get_nested(config, "ml.paecter.batch_size", 32)
        result = client.generate_embeddings(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
        )

    # Create output DataFrame
    embeddings_df = pd.DataFrame(
        {
            "patent_id": patent_ids,
            "embedding": [e.tolist() for e in result.embeddings],
            "model_version": result.model_version,
            "inference_mode": result.inference_mode,
            "dimension": result.dimension,
        }
    )

    context.log.info(
        "PaECTER embeddings generated",
        extra={
            "patent_count": len(embeddings_df),
            "model_version": result.model_version,
            "inference_mode": result.inference_mode,
            "dimension": result.dimension,
        },
    )

    return Output(
        embeddings_df,
        metadata={
            "patent_count": len(embeddings_df),
            "model_version": result.model_version,
            "inference_mode": result.inference_mode,
            "dimension": result.dimension,
            "generation_time_seconds": result.generation_timestamp,
        },
    )


@asset(
    description="Similarity scores between SBIR awards and USPTO patents",
    group_name="paecter",
    compute_kind="ml",
    io_manager_key="parquet_io_manager",
)
def paecter_award_patent_similarity(
    context,
    paecter_embeddings_awards: pd.DataFrame,
    paecter_embeddings_patents: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Compute similarity scores between SBIR awards and USPTO patents.

    Args:
        paecter_embeddings_awards: Award embeddings DataFrame
        paecter_embeddings_patents: Patent embeddings DataFrame

    Returns:
        DataFrame with award_id, patent_id, and similarity_score
    """
    config = get_config()

    context.log.info(
        "Computing award-patent similarities",
        extra={
            "award_count": len(paecter_embeddings_awards),
            "patent_count": len(paecter_embeddings_patents),
        },
    )

    # Convert embeddings to numpy arrays
    award_embeddings = np.array([np.array(e) for e in paecter_embeddings_awards["embedding"]])
    patent_embeddings = np.array([np.array(e) for e in paecter_embeddings_patents["embedding"]])

    # Initialize client for similarity computation
    use_local = ConfigAccessor.get_nested(config, "ml.paecter.use_local", False)
    client = PaECTERClient(config=PaECTERClientConfig(use_local=use_local))

    # Compute similarities with performance monitoring
    with performance_monitor.monitor_block("paecter_compute_similarities"):
        similarities = client.compute_similarity(award_embeddings, patent_embeddings)

    # Get similarity threshold from config
    threshold = ConfigAccessor.get_nested(config, "ml.paecter.similarity_threshold", 0.80)

    # Find matches above threshold
    matches = []
    for i, award_id in enumerate(paecter_embeddings_awards["award_id"]):
        top_indices = np.argsort(similarities[i])[::-1][:10]  # Top 10
        top_scores = similarities[i][top_indices]

        for idx, score in zip(top_indices, top_scores, strict=True):
            if score >= threshold:
                matches.append(
                    {
                        "award_id": award_id,
                        "patent_id": paecter_embeddings_patents.iloc[idx]["patent_id"],
                        "similarity_score": float(score),
                    }
                )

    matches_df = pd.DataFrame(matches)

    context.log.info(
        "Similarity computation complete",
        extra={
            "total_similarities": similarities.size,
            "matches_above_threshold": len(matches_df),
            "threshold": threshold,
            "average_similarity": float(similarities.mean()),
            "max_similarity": float(similarities.max()),
            "min_similarity": float(similarities.min()),
        },
    )

    return Output(
        matches_df,
        metadata={
            "total_similarities": similarities.size,
            "matches_above_threshold": len(matches_df),
            "threshold": threshold,
            "average_similarity": float(similarities.mean()),
            "max_similarity": float(similarities.max()),
            "min_similarity": float(similarities.min()),
        },
    )


@asset_check(
    asset="paecter_embeddings_awards",
    description="Check that PaECTER embeddings coverage meets threshold",
)
def paecter_awards_coverage_check(
    context,
    paecter_embeddings_awards: pd.DataFrame,
) -> AssetCheckResult:
    """Check that award embedding coverage meets quality threshold."""
    from ...utils.config_accessor import ConfigAccessor

    config = get_config()
    threshold = ConfigAccessor.get_nested(config, "ml.paecter.coverage_threshold_awards", 0.95)

    # Count valid embeddings (non-null, correct dimension)
    valid_count = 0
    expected_dim = 1024  # PaECTER embeddings are 1024-dimensional

    for embedding in paecter_embeddings_awards["embedding"]:
        if embedding and len(embedding) == expected_dim:
            valid_count += 1

    coverage = (
        valid_count / len(paecter_embeddings_awards) if len(paecter_embeddings_awards) > 0 else 0.0
    )
    passed = coverage >= threshold

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        description=f"Embedding coverage: {coverage:.2%} (threshold: {threshold:.2%})",
        metadata={
            "coverage": MetadataValue.float(coverage),
            "threshold": MetadataValue.float(threshold),
            "valid_embeddings": MetadataValue.int(valid_count),
            "total_awards": MetadataValue.int(len(paecter_embeddings_awards)),
        },
    )


@asset_check(
    asset="paecter_embeddings_patents",
    description="Check that PaECTER embeddings coverage meets threshold",
)
def paecter_patents_coverage_check(
    context,
    paecter_embeddings_patents: pd.DataFrame,
) -> AssetCheckResult:
    """Check that patent embedding coverage meets quality threshold."""
    from ...utils.config_accessor import ConfigAccessor

    config = get_config()
    threshold = ConfigAccessor.get_nested(config, "ml.paecter.coverage_threshold_patents", 0.98)

    # Count valid embeddings (non-null, correct dimension)
    valid_count = 0
    expected_dim = 1024  # PaECTER embeddings are 1024-dimensional

    for embedding in paecter_embeddings_patents["embedding"]:
        if embedding and len(embedding) == expected_dim:
            valid_count += 1

    coverage = (
        valid_count / len(paecter_embeddings_patents)
        if len(paecter_embeddings_patents) > 0
        else 0.0
    )
    passed = coverage >= threshold

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        description=f"Embedding coverage: {coverage:.2%} (threshold: {threshold:.2%})",
        metadata={
            "coverage": MetadataValue.float(coverage),
            "threshold": MetadataValue.float(threshold),
            "valid_embeddings": MetadataValue.int(valid_count),
            "total_patents": MetadataValue.int(len(paecter_embeddings_patents)),
        },
    )
