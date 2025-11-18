#!/usr/bin/env python3
"""Test PaECTER embeddings with both SBIR and USPTO data from S3.

This script loads real SBIR award data and USPTO patent data from S3,
generates PaECTER embeddings for both, and computes similarity scores.

Usage:
    # API mode (default - requires HF_TOKEN)
    export HF_TOKEN="your_token_here"
    export SBIR_ETL__S3_BUCKET=sbir-etl-production-data
    python scripts/test_paecter_combined_s3.py

    # Local mode
    python scripts/test_paecter_combined_s3.py --local

    # Process limited records
    python scripts/test_paecter_combined_s3.py --limit-sbir 100 --limit-uspto 50

    # Use specific S3 paths
    python scripts/test_paecter_combined_s3.py \
        --sbir-s3 s3://sbir-etl-production-data/raw/sbir/award_data.csv \
        --uspto-s3 s3://sbir-etl-production-data/raw/uspto/patentsview/2025-11-18/patent.zip
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import zipfile
from pathlib import Path

# Add src to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

import boto3
import numpy as np
import pandas as pd
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, MofNCompleteColumn
from rich.table import Table

from src.config.loader import get_config
from src.extractors.sbir import SbirDuckDBExtractor
from src.extractors.uspto_extractor import USPTOExtractor
from src.ml.paecter_client import PaECTERClient
from src.utils.cloud_storage import build_s3_path, get_s3_bucket_from_env

console = Console()


def download_from_s3(s3_url: str, local_path: Path) -> Path:
    """Download file from S3 to local path."""
    if not s3_url.startswith("s3://"):
        raise ValueError(f"Invalid S3 URL: {s3_url}")
    
    parts = s3_url.replace("s3://", "").split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    
    console.print(f"[yellow]Downloading from S3:[/yellow] {s3_url}")
    s3 = boto3.client("s3")
    s3.download_file(bucket, key, str(local_path))
    console.print(f"[green]✓ Downloaded[/green] {local_path.name} ({local_path.stat().st_size / 1024 / 1024:.2f} MB)")
    
    return local_path


def extract_zip_if_needed(file_path: Path, extract_to: Path) -> None:
    """Extract ZIP file if needed to the specified directory."""
    if file_path.suffix == ".zip":
        console.print(f"[yellow]Extracting ZIP:[/yellow] {file_path.name}")
        extract_to.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(file_path, "r") as zip_ref:
            zip_ref.extractall(extract_to)
        # List extracted files for debugging
        extracted_files = [f.name for f in extract_to.iterdir() if f.is_file()]
        if extracted_files:
            console.print(f"[dim]Extracted {len(extracted_files)} file(s): {', '.join(extracted_files[:5])}[/dim]")


def load_sbir_from_s3(
    s3_url: str | None = None,
    s3_bucket: str | None = None,
    csv_path: str | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """Load SBIR data from S3 or local path."""
    config = get_config()
    
    # Determine S3 URL
    csv_path_s3: str | None = None
    use_s3_first = False
    
    # Default bucket (matches CDK infrastructure)
    default_bucket = "sbir-etl-production-data"
    
    if s3_url:
        # Explicit S3 URL provided
        csv_path_s3 = s3_url
        use_s3_first = True
        # Use a placeholder local path (won't be used if S3 works)
        if csv_path is None:
            csv_path = config.extraction.sbir.csv_path
    else:
        # Try to get bucket from args, env, or use default
        bucket = s3_bucket or get_s3_bucket_from_env() or default_bucket
        if csv_path is None:
            csv_path = config.extraction.sbir.csv_path
        try:
            csv_path_s3 = build_s3_path(str(csv_path), bucket)
            use_s3_first = True
            console.print(f"[yellow]Using S3:[/yellow] {csv_path_s3}")
        except ValueError as e:
            console.print(f"[yellow]Warning:[/yellow] {e}")
            console.print("[yellow]Falling back to local path[/yellow]")
    
    # Use local path as fallback (only if S3 not configured)
    if csv_path is None:
        csv_path = config.extraction.sbir.csv_path
    
    # Initialize extractor
    # If S3 is configured, pass the S3 URL explicitly
    # The extractor will handle S3-first logic
    extractor = SbirDuckDBExtractor(
        csv_path=csv_path,
        duckdb_path=":memory:",
        table_name="sbir_awards",
        csv_path_s3=csv_path_s3,
        use_s3_first=use_s3_first,
    )
    
    # Import CSV
    with console.status("[bold green]Importing SBIR CSV..."):
        try:
            import_metadata = extractor.import_csv()
        except FileNotFoundError as e:
            error_msg = str(e)
            if "S3" in error_msg or csv_path_s3:
                console.print(f"[bold red]Error:[/bold red] Could not access SBIR data from S3")
                console.print(f"[yellow]S3 URL:[/yellow] {csv_path_s3}")
                console.print(f"[yellow]Local fallback:[/yellow] {csv_path}")
                console.print("\n[yellow]Troubleshooting:[/yellow]")
                console.print("1. Verify S3 bucket is set: echo $SBIR_ETL__S3_BUCKET")
                console.print("2. Check file exists in S3: aws s3 ls s3://sbir-etl-production-data/raw/sbir/award_data.csv")
                console.print("3. Verify AWS credentials: aws s3 ls s3://sbir-etl-production-data/")
            else:
                console.print(f"[bold red]Error:[/bold red] {error_msg}")
                console.print("\n[yellow]Troubleshooting:[/yellow]")
                console.print("1. Set SBIR_ETL__S3_BUCKET to use S3")
                console.print("2. Or download data locally to: data/raw/sbir/award_data.csv")
            raise
    
    console.print(f"[green]✓[/green] Imported {import_metadata['row_count']:,} SBIR records")
    
    # Extract with limit
    if limit:
        query = f"SELECT * FROM sbir_awards LIMIT {limit}"
        df = extractor.duckdb_client.execute_query_df(query)
        console.print(f"[green]✓[/green] Limited to {len(df):,} records")
    else:
        df = extractor.duckdb_client.execute_query_df("SELECT * FROM sbir_awards")
    
    return df


def load_uspto_from_s3(
    s3_url: str | None = None,
    s3_bucket: str | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """Load USPTO PatentsView data from S3."""
    # Default bucket (matches CDK infrastructure)
    default_bucket = "sbir-etl-production-data"
    
    # Determine S3 URL
    if not s3_url:
        bucket = s3_bucket or get_s3_bucket_from_env() or default_bucket
        # Default to latest PatentsView patent data
        s3_url = f"s3://{bucket}/raw/uspto/patentsview/2025-11-18/patent.zip"
    
    # Download to temp location
    temp_dir = Path(tempfile.gettempdir()) / "sbir-etl-paecter-test"
    temp_dir.mkdir(parents=True, exist_ok=True)
    local_zip = temp_dir / "patentsview.zip"
    
    download_from_s3(s3_url, local_zip)
    
    # Extract if ZIP
    extract_dir = temp_dir / "extracted"
    extract_zip_if_needed(local_zip, extract_dir)
    
    # Always use the extraction directory (files are extracted here)
    # USPTOExtractor will discover files within this directory
    input_dir = extract_dir
    
    # Use USPTO extractor to load data
    extractor = USPTOExtractor(input_dir=input_dir)
    files = extractor.discover_files()
    
    if not files:
        raise FileNotFoundError(
            f"No USPTO files found in {input_dir}. "
            f"Contents: {list(input_dir.iterdir()) if input_dir.exists() else 'directory does not exist'}"
        )
    
    console.print(f"[green]✓[/green] Found {len(files)} USPTO file(s)")
    
    # Load data from first file (or all files)
    all_rows = []
    for file_path in files:
        console.print(f"[yellow]Loading from:[/yellow] {file_path.name}")
        count = 0
        for row in extractor.stream_rows(file_path, chunk_size=10000):
            all_rows.append(row)
            count += 1
            if limit and count >= limit:
                break
        if limit and count >= limit:
            break
    
    console.print(f"[green]✓[/green] Loaded {len(all_rows):,} USPTO records")
    
    # Convert to DataFrame
    df = pd.DataFrame(all_rows)
    
    return df


def prepare_award_texts(df: pd.DataFrame, client: PaECTERClient) -> tuple[list[str], pd.Series]:
    """Prepare award texts for embedding generation."""
    # Find columns
    solicitation_col = next((c for c in df.columns if "solicitation" in c.lower() or "topic" in c.lower()), None)
    title_col = next((c for c in df.columns if ("award" in c.lower() or "title" in c.lower()) and "solicitation" not in c.lower()), None)
    abstract_col = next((c for c in df.columns if "abstract" in c.lower()), None)
    award_id_col = next((c for c in df.columns if "contract" in c.lower() or "tracking" in c.lower() or "award_id" in c.lower()), None)
    
    if not award_id_col:
        award_ids = df.index.astype(str)
    else:
        award_ids = df[award_id_col].astype(str)
    
    texts = []
    for _, row in df.iterrows():
        solicitation = str(row[solicitation_col]) if solicitation_col and pd.notna(row.get(solicitation_col)) else None
        title = str(row[title_col]) if title_col and pd.notna(row.get(title_col)) else None
        abstract = str(row[abstract_col]) if abstract_col and pd.notna(row.get(abstract_col)) else None
        
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
    
    return texts, award_ids


def prepare_patent_texts(df: pd.DataFrame, client: PaECTERClient) -> tuple[list[str], pd.Series]:
    """Prepare patent texts for embedding generation."""
    # Find columns
    title_col = next((c for c in df.columns if "title" in c.lower()), None)
    abstract_col = next((c for c in df.columns if "abstract" in c.lower()), None)
    patent_id_col = next((c for c in df.columns if "patent" in c.lower() and "id" in c.lower() or "number" in c.lower()), None)
    
    if not patent_id_col:
        patent_ids = df.index.astype(str)
    else:
        patent_ids = df[patent_id_col].astype(str)
    
    texts = []
    for _, row in df.iterrows():
        title = str(row[title_col]) if title_col and pd.notna(row.get(title_col)) else None
        abstract = str(row[abstract_col]) if abstract_col and pd.notna(row.get(abstract_col)) else None
        
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
    
    return texts, patent_ids


def main():
    """Run combined PaECTER test with SBIR and USPTO data from S3."""
    parser = argparse.ArgumentParser(
        description="Test PaECTER embeddings with SBIR and USPTO data from S3"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local mode (requires sentence-transformers)",
    )
    parser.add_argument(
        "--limit-sbir",
        type=int,
        default=None,
        help="Limit number of SBIR records to process",
    )
    parser.add_argument(
        "--limit-uspto",
        type=int,
        default=None,
        help="Limit number of USPTO records to process",
    )
    parser.add_argument(
        "--sbir-s3",
        type=str,
        default=None,
        help="S3 URL to SBIR CSV file",
    )
    parser.add_argument(
        "--uspto-s3",
        type=str,
        default=None,
        help="S3 URL to USPTO data file (ZIP or CSV)",
    )
    parser.add_argument(
        "--s3-bucket",
        type=str,
        default=None,
        help="S3 bucket name (overrides SBIR_ETL__S3_BUCKET env var)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/processed/paecter",
        help="Output directory for embeddings and similarities",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for embedding generation",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.80,
        help="Minimum similarity score to include in results",
    )

    args = parser.parse_args()

    console.print("\n[bold blue]PaECTER Combined S3 Test[/bold blue]", style="bold")
    console.print("Testing patent embeddings with SBIR and USPTO data from S3\n")

    # Check mode
    use_local = args.local
    if use_local:
        console.print("[yellow]Mode:[/yellow] Local (using sentence-transformers)\n")
    else:
        console.print("[yellow]Mode:[/yellow] API (using HuggingFace Inference API)")
        if not os.getenv("HF_TOKEN"):
            console.print(
                "[bold red]Error:[/bold red] HF_TOKEN environment variable not set.\n"
                "Get a free token from https://huggingface.co/settings/tokens\n"
                "Then: export HF_TOKEN=\"your_token_here\"\n"
                "Or use --local flag for local mode.\n"
            )
            return 1
        console.print("[dim]Using HuggingFace API[/dim]\n")

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Load SBIR data
    console.print("[bold yellow]Step 1:[/bold yellow] Loading SBIR award data from S3...")
    
    # Use default bucket if not specified (matches CDK infrastructure)
    default_bucket = "sbir-etl-production-data"
    if not args.sbir_s3 and not args.s3_bucket and not get_s3_bucket_from_env():
        # Use default production bucket
        console.print(f"[yellow]Note:[/yellow] Using default S3 bucket: {default_bucket}")
        console.print(f"[dim]To override, set SBIR_ETL__S3_BUCKET or use --s3-bucket flag[/dim]")
        args.s3_bucket = default_bucket
    
    try:
        sbir_df = load_sbir_from_s3(
            s3_url=args.sbir_s3,
            s3_bucket=args.s3_bucket,
            limit=args.limit_sbir,
        )
        console.print(f"[green]✓[/green] Loaded {len(sbir_df):,} SBIR awards\n")
    except Exception as e:
        console.print(f"[bold red]Error loading SBIR data:[/bold red] {e}")
        return 1

    # Step 2: Load USPTO data
    console.print("[bold yellow]Step 2:[/bold yellow] Loading USPTO patent data from S3...")
    try:
        uspto_df = load_uspto_from_s3(
            s3_url=args.uspto_s3,
            s3_bucket=args.s3_bucket,
            limit=args.limit_uspto,
        )
        console.print(f"[green]✓[/green] Loaded {len(uspto_df):,} USPTO patents\n")
    except Exception as e:
        console.print(f"[bold red]Error loading USPTO data:[/bold red] {e}")
        return 1

    # Step 3: Initialize PaECTER client
    console.print("[bold yellow]Step 3:[/bold yellow] Initializing PaECTER client...")
    try:
        client = PaECTERClient(use_local=use_local)
        console.print(f"[green]✓[/green] PaECTER client initialized ({client.inference_mode} mode)\n")
    except Exception as e:
        console.print(f"[bold red]Error initializing PaECTER:[/bold red] {e}")
        return 1

    # Step 4: Prepare texts
    console.print("[bold yellow]Step 4:[/bold yellow] Preparing texts for embedding...")
    sbir_texts, sbir_ids = prepare_award_texts(sbir_df, client)
    uspto_texts, uspto_ids = prepare_patent_texts(uspto_df, client)
    console.print(f"[green]✓[/green] Prepared {len(sbir_texts):,} award texts and {len(uspto_texts):,} patent texts\n")

    # Step 5: Generate SBIR embeddings
    console.print("[bold yellow]Step 5:[/bold yellow] Generating SBIR award embeddings...")
    sbir_output = output_dir / "paecter_embeddings_sbir.parquet"
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Generating embeddings...", total=len(sbir_texts))
        result = client.generate_embeddings(
            sbir_texts,
            batch_size=args.batch_size,
            show_progress_bar=False,
        )
        progress.update(task, completed=len(sbir_texts))
    
    sbir_embeddings_df = pd.DataFrame({
        "award_id": sbir_ids,
        "embedding": [e.tolist() for e in result.embeddings],
        "model_version": result.model_version,
        "inference_mode": result.inference_mode,
        "dimension": result.dimension,
    })
    sbir_embeddings_df.to_parquet(sbir_output)
    console.print(f"[green]✓[/green] Generated {len(sbir_embeddings_df):,} SBIR embeddings")
    console.print(f"[green]✓[/green] Saved to {sbir_output}\n")

    # Step 6: Generate USPTO embeddings
    console.print("[bold yellow]Step 6:[/bold yellow] Generating USPTO patent embeddings...")
    uspto_output = output_dir / "paecter_embeddings_uspto.parquet"
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Generating embeddings...", total=len(uspto_texts))
        result = client.generate_embeddings(
            uspto_texts,
            batch_size=args.batch_size,
            show_progress_bar=False,
        )
        progress.update(task, completed=len(uspto_texts))
    
    uspto_embeddings_df = pd.DataFrame({
        "patent_id": uspto_ids,
        "embedding": [e.tolist() for e in result.embeddings],
        "model_version": result.model_version,
        "inference_mode": result.inference_mode,
        "dimension": result.dimension,
    })
    uspto_embeddings_df.to_parquet(uspto_output)
    console.print(f"[green]✓[/green] Generated {len(uspto_embeddings_df):,} USPTO embeddings")
    console.print(f"[green]✓[/green] Saved to {uspto_output}\n")

    # Step 7: Compute similarities
    console.print("[bold yellow]Step 7:[/bold yellow] Computing award-patent similarities...")
    sbir_embeddings = np.array([np.array(e) for e in sbir_embeddings_df["embedding"]])
    uspto_embeddings = np.array([np.array(e) for e in uspto_embeddings_df["embedding"]])
    
    similarities = client.compute_similarity(sbir_embeddings, uspto_embeddings)
    console.print(f"[green]✓[/green] Computed {similarities.shape[0]:,} x {similarities.shape[1]:,} similarity matrix\n")

    # Step 8: Find top matches
    console.print("[bold yellow]Step 8:[/bold yellow] Finding top matches...")
    threshold = args.similarity_threshold
    matches = []
    
    for i, award_id in enumerate(sbir_embeddings_df["award_id"]):
        top_indices = np.argsort(similarities[i])[::-1][:10]  # Top 10
        top_scores = similarities[i][top_indices]
        
        for idx, score in zip(top_indices, top_scores):
            if score >= threshold:
                matches.append({
                    "award_id": award_id,
                    "patent_id": uspto_embeddings_df.iloc[idx]["patent_id"],
                    "similarity_score": float(score),
                })
    
    matches_df = pd.DataFrame(matches)
    matches_output = output_dir / "award_patent_similarities.parquet"
    matches_df.to_parquet(matches_output)
    console.print(f"[green]✓[/green] Found {len(matches_df):,} matches above threshold {threshold}")
    console.print(f"[green]✓[/green] Saved to {matches_output}\n")

    # Step 9: Display summary
    console.print("[bold yellow]Step 9:[/bold yellow] Summary Statistics\n")
    
    table = Table(title="PaECTER Test Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("SBIR Awards Processed", f"{len(sbir_df):,}")
    table.add_row("USPTO Patents Processed", f"{len(uspto_df):,}")
    table.add_row("SBIR Embeddings Generated", f"{len(sbir_embeddings_df):,}")
    table.add_row("USPTO Embeddings Generated", f"{len(uspto_embeddings_df):,}")
    table.add_row("Total Similarities Computed", f"{similarities.size:,}")
    table.add_row("Matches Above Threshold", f"{len(matches_df):,}")
    table.add_row("Average Similarity", f"{similarities.mean():.3f}")
    table.add_row("Max Similarity", f"{similarities.max():.3f}")
    table.add_row("Min Similarity", f"{similarities.min():.3f}")
    
    console.print(table)
    
    # Show top matches
    if len(matches_df) > 0:
        console.print("\n[bold yellow]Top 10 Matches:[/bold yellow]\n")
        top_matches = matches_df.nlargest(10, "similarity_score")
        matches_table = Table()
        matches_table.add_column("Award ID", style="cyan")
        matches_table.add_column("Patent ID", style="cyan")
        matches_table.add_column("Similarity", style="green")
        
        for _, row in top_matches.iterrows():
            matches_table.add_row(
                str(row["award_id"]),
                str(row["patent_id"]),
                f"{row['similarity_score']:.3f}",
            )
        
        console.print(matches_table)
    
    console.print(f"\n[bold green]✓ Test complete![/bold green]")
    console.print(f"Output files saved to: {output_dir}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

