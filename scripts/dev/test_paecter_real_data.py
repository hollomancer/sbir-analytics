#!/usr/bin/env python3
"""Test PaECTER embeddings with real SBIR award data.

This script loads real SBIR award data from your database/CSV and generates
PaECTER embeddings for testing and evaluation.

Usage:
    # API mode (default - requires HF_TOKEN environment variable)
    export HF_TOKEN="your_token_here"
    python scripts/test_paecter_real_data.py

    # Local mode (requires sentence-transformers)
    python scripts/test_paecter_real_data.py --local

    # Specify number of records to process
    python scripts/test_paecter_real_data.py --limit 100

    # Use specific CSV file
    python scripts/test_paecter_real_data.py --csv data/raw/sbir/awards_data.csv

Requirements:
    # API mode (default)
    pip install huggingface-hub

    # Local mode
    pip install sentence-transformers torch transformers
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add src to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

import pandas as pd
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

from src.config.loader import get_config
from src.extractors.sbir import SbirDuckDBExtractor
from src.ml.paecter_client import PaECTERClient
from src.utils.cloud_storage import build_s3_path, get_s3_bucket_from_env

console = Console()


def load_sbir_data(
    csv_path: Path | None = None,
    s3_url: str | None = None,
    s3_bucket: str | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """Load SBIR award data from CSV, S3, or DuckDB.

    Args:
        csv_path: Optional local path to CSV file. If None, uses config default.
        s3_url: Optional S3 URL (s3://bucket/path/to/file.csv). Takes precedence over csv_path.
        s3_bucket: Optional S3 bucket name (overrides env var).
        limit: Optional limit on number of records to load.

    Returns:
        DataFrame with SBIR award data.
    """
    config = get_config()
    
    # Determine data source
    csv_path_s3: str | None = None
    use_s3_first = False
    
    if s3_url:
        # Direct S3 URL provided
        csv_path_s3 = s3_url
        use_s3_first = True
        console.print(f"[yellow]Loading SBIR data from S3:[/yellow] {s3_url}")
        # Use a placeholder local path for fallback
        csv_path = csv_path or Path("data/raw/sbir/awards_data.csv")
    elif s3_bucket or get_s3_bucket_from_env():
        # Build S3 path from bucket and relative path
        bucket = s3_bucket or get_s3_bucket_from_env()
        if csv_path is None:
            csv_path = Path(config.extraction.sbir.csv_path)
        csv_path_s3 = build_s3_path(str(csv_path), bucket)
        use_s3_first = True
        console.print(f"[yellow]Loading SBIR data from S3:[/yellow] {csv_path_s3}")
    else:
        # Use local path
        if csv_path is None:
            csv_path = Path(config.extraction.sbir.csv_path)
        
        # Check if local file exists (but don't fail yet - let extractor handle S3 fallback)
        if not csv_path.exists():
            # Try to use S3 if bucket is configured
            bucket = get_s3_bucket_from_env()
            if bucket:
                csv_path_s3 = build_s3_path(str(csv_path), bucket)
                use_s3_first = True
                console.print(f"[yellow]Local file not found, trying S3:[/yellow] {csv_path_s3}")
            else:
                console.print(f"[yellow]Loading SBIR data from:[/yellow] {csv_path}")
                console.print("[yellow]Note:[/yellow] If file not found locally, set SBIR_ETL__S3_BUCKET to use S3")
        else:
            console.print(f"[yellow]Loading SBIR data from:[/yellow] {csv_path}")

    # Use DuckDB extractor for efficient loading (with S3 support)
    extractor = SbirDuckDBExtractor(
        csv_path=csv_path,
        duckdb_path=":memory:",
        table_name="sbir_awards",
        csv_path_s3=csv_path_s3,
        use_s3_first=use_s3_first,
    )

    # Import CSV to DuckDB
    with console.status("[bold green]Importing CSV to DuckDB..."):
        try:
            import_metadata = extractor.import_csv()
        except FileNotFoundError as e:
            console.print(f"[red]Error:[/red] Could not load SBIR data: {e}")
            console.print("\n[yellow]Available options:[/yellow]")
            console.print("1. Download SBIR data to data/raw/sbir/")
            console.print("2. Use --csv flag to specify a different local path")
            console.print("3. Use --s3 flag to specify S3 URL directly")
            console.print("4. Set SBIR_ETL__S3_BUCKET env var and use --s3-bucket flag")
            console.print("5. Use sample data: tests/fixtures/sbir_sample.csv")
            sys.exit(1)
    
    console.print(f"✓ Imported {import_metadata['row_count']:,} records")

    # Extract data with optional limit
    if limit:
        # Use SQL to limit records efficiently
        query = f"SELECT * FROM sbir_awards LIMIT {limit}"
        df = extractor.duckdb_client.execute_query_df(query)
        console.print(f"✓ Limited to {len(df):,} records")
    else:
        df = extractor.duckdb_client.execute_query_df("SELECT * FROM sbir_awards")

    return df


def prepare_award_texts(df: pd.DataFrame) -> tuple[list[str], pd.Series]:
    """Prepare award texts for embedding generation.

    Args:
        df: DataFrame with SBIR award data.

    Returns:
        Tuple of (prepared_texts, award_ids).
    """
    client = PaECTERClient()

    # Map CSV column names to expected fields
    # Handle both original CSV column names and normalized names
    solicitation_col = None
    for col in ["Solicitation Title", "solicitation_title", "Topic Code", "topic_code"]:
        if col in df.columns:
            solicitation_col = col
            break

    title_col = None
    for col in ["Award Title", "award_title", "Title", "title"]:
        if col in df.columns:
            title_col = col
            break

    abstract_col = None
    for col in ["Abstract", "abstract"]:
        if col in df.columns:
            abstract_col = col
            break

    # Get award ID column
    award_id_col = None
    for col in ["Contract", "contract", "Agency Tracking Number", "agency_tracking_number", "award_id"]:
        if col in df.columns:
            award_id_col = col
            break

    if not award_id_col:
        # Fallback: use index
        award_ids = df.index.astype(str)
        console.print("[yellow]Warning:[/yellow] No award ID column found, using index")
    else:
        award_ids = df[award_id_col].astype(str)

    # Prepare texts
    texts = []
    for _, row in df.iterrows():
        solicitation = row.get(solicitation_col) if solicitation_col else None
        title = row.get(title_col) if title_col else None
        abstract = row.get(abstract_col) if abstract_col else None

        # Convert to string and handle NaN
        solicitation = str(solicitation) if pd.notna(solicitation) else None
        title = str(title) if pd.notna(title) else None
        abstract = str(abstract) if pd.notna(abstract) else None

        # Clean up "nan" strings
        if solicitation and solicitation.lower() == "nan":
            solicitation = None
        if title and title.lower() == "nan":
            title = None
        if abstract and abstract.lower() == "nan":
            abstract = None

        text = client.prepare_award_text(
            solicitation_title=solicitation,
            abstract=abstract,
            award_title=title,
        )
        texts.append(text)

    return texts, award_ids


def main():
    """Run PaECTER test with real SBIR data."""
    parser = argparse.ArgumentParser(
        description="Test PaECTER embeddings with real SBIR award data"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local mode (requires sentence-transformers)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of records to process (default: all)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Local path to SBIR CSV file (default: from config)",
    )
    parser.add_argument(
        "--s3",
        type=str,
        default=None,
        help="S3 URL to SBIR CSV file (e.g., s3://bucket-name/path/to/file.csv). Takes precedence over --csv.",
    )
    parser.add_argument(
        "--s3-bucket",
        type=str,
        default=None,
        help="S3 bucket name (overrides SBIR_ETL__S3_BUCKET env var). Used with --csv to build S3 path.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/processed/paecter_embeddings_awards_sample.parquet",
        help="Output path for embeddings (default: data/processed/paecter_embeddings_awards_sample.parquet)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for embedding generation (default: 32)",
    )

    args = parser.parse_args()

    console.print("\n[bold blue]PaECTER Real Data Test[/bold blue]", style="bold")
    console.print("Testing patent embeddings with real SBIR award data\n")

    # Check mode
    use_local = args.local
    if use_local:
        console.print("[yellow]Mode:[/yellow] Local (using sentence-transformers)")
        console.print("[dim]Model will be downloaded (~500MB) on first run[/dim]\n")
    else:
        console.print("[yellow]Mode:[/yellow] API (using HuggingFace Inference API)")
        if not os.getenv("HF_TOKEN"):
            console.print(
                "[bold red]Warning:[/bold red] HF_TOKEN environment variable not set.\n"
                "API calls may fail or have rate limits.\n\n"
                "[yellow]To use API mode:[/yellow]\n"
                "  export HF_TOKEN=\"your_token_here\"\n\n"
                "[yellow]Or use local mode instead:[/yellow]\n"
                "  python scripts/test_paecter_real_data.py --local\n"
            )
            return 1
        console.print("[dim]Using HuggingFace API (no model download)[/dim]\n")

    # Step 1: Load SBIR data
    console.print("[yellow]Step 1:[/yellow] Loading SBIR award data...")
    try:
        csv_path = Path(args.csv) if args.csv else None
        df = load_sbir_data(
            csv_path=csv_path,
            s3_url=args.s3,
            s3_bucket=args.s3_bucket,
            limit=args.limit,
        )
        console.print(f"✓ Loaded {len(df):,} SBIR award records\n", style="green")
    except Exception as e:
        console.print(f"[red]✗ Error loading SBIR data: {e}[/red]")
        import traceback
        traceback.print_exc()
        return 1

    # Step 2: Prepare texts
    console.print("[yellow]Step 2:[/yellow] Preparing award texts for embedding...")
    try:
        texts, award_ids = prepare_award_texts(df)
        
        # Filter out empty texts
        valid_indices = [i for i, text in enumerate(texts) if text.strip()]
        texts = [texts[i] for i in valid_indices]
        award_ids = award_ids.iloc[valid_indices]
        
        console.print(f"✓ Prepared {len(texts):,} award texts")
        console.print(f"  (filtered {len(df) - len(texts):,} empty texts)\n", style="green")
        
        if len(texts) == 0:
            console.print("[red]Error:[/red] No valid texts to process")
            return 1
    except Exception as e:
        console.print(f"[red]✗ Error preparing texts: {e}[/red]")
        import traceback
        traceback.print_exc()
        return 1

    # Step 3: Initialize client
    console.print("[yellow]Step 3:[/yellow] Initializing PaECTER client...")
    try:
        client = PaECTERClient(use_local=use_local)
        console.print(
            f"✓ Client initialized: {client.model_name} "
            f"(dimension: {client.embedding_dim}, mode: {client.inference_mode})\n",
            style="green",
        )
    except ImportError as e:
        console.print(f"[red]✗ Error: {e}[/red]\n")
        if use_local:
            console.print("[yellow]Install local dependencies:[/yellow] pip install sentence-transformers torch")
        else:
            console.print("[yellow]Install API dependencies:[/yellow] pip install huggingface-hub")
        return 1
    except Exception as e:
        console.print(f"[red]✗ Error initializing client: {e}[/red]")
        return 1

    # Step 4: Generate embeddings
    console.print(f"[yellow]Step 4:[/yellow] Generating embeddings (batch size: {args.batch_size})...")
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Generating embeddings...", total=len(texts))
            
            result = client.generate_embeddings(
                texts,
                batch_size=args.batch_size,
                show_progress_bar=False,  # Use our custom progress bar
            )
            
            progress.update(task, completed=len(texts))

        console.print(
            f"✓ Generated {result.input_count:,} embeddings "
            f"(shape: {result.embeddings.shape}, "
            f"time: {result.generation_timestamp:.2f}s)\n",
            style="green",
        )
    except Exception as e:
        console.print(f"[red]✗ Error generating embeddings: {e}[/red]")
        import traceback
        traceback.print_exc()
        return 1

    # Step 5: Save embeddings
    console.print("[yellow]Step 5:[/yellow] Saving embeddings to Parquet...")
    try:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create DataFrame with embeddings
        # Note: We can't directly store numpy arrays in Parquet easily,
        # so we'll store them as lists or use a different format
        embeddings_df = pd.DataFrame({
            "award_id": award_ids.values,
            "embedding": [emb.tolist() for emb in result.embeddings],
            "model_version": result.model_version,
            "inference_mode": result.inference_mode,
            "dimension": result.dimension,
        })

        try:
            embeddings_df.to_parquet(output_path, index=False)
            console.print(f"✓ Saved embeddings to: {output_path}\n", style="green")
        except ImportError as e:
            if "pyarrow" in str(e).lower() or "fastparquet" in str(e).lower():
                console.print(
                    "[yellow]Warning:[/yellow] pyarrow not available. "
                    "Saving as CSV instead (larger file size).\n"
                    "[dim]To save as Parquet, install: uv pip install pyarrow[/dim]\n"
                )
                # Fallback to CSV
                csv_path = output_path.with_suffix(".csv")
                embeddings_df.to_csv(csv_path, index=False)
                console.print(f"✓ Saved embeddings to: {csv_path}\n", style="green")
            else:
                raise
    except Exception as e:
        console.print(f"[red]✗ Error saving embeddings: {e}[/red]")
        import traceback
        traceback.print_exc()
        return 1

    # Step 6: Display summary statistics
    console.print("[bold blue]Summary Statistics[/bold blue]\n")

    # Create summary table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Total records loaded", f"{len(df):,}")
    table.add_row("Valid texts", f"{len(texts):,}")
    table.add_row("Embeddings generated", f"{result.input_count:,}")
    table.add_row("Embedding dimension", f"{result.dimension}")
    table.add_row("Model version", result.model_version)
    table.add_row("Inference mode", result.inference_mode)
    table.add_row("Generation time", f"{result.generation_timestamp:.2f}s")
    table.add_row("Throughput", f"{result.input_count / result.generation_timestamp:.1f} embeddings/s")
    table.add_row("Output file", str(output_path))

    console.print(table)
    console.print()

    # Display sample embeddings info
    console.print("[bold blue]Sample Embedding Statistics[/bold blue]\n")
    
    # Compute some basic stats on embeddings
    import numpy as np
    norms = np.linalg.norm(result.embeddings, axis=1)
    
    stats_table = Table(show_header=True, header_style="bold magenta")
    stats_table.add_column("Statistic", style="cyan")
    stats_table.add_column("Value", justify="right")
    
    stats_table.add_row("Mean embedding norm", f"{norms.mean():.4f}")
    stats_table.add_row("Std embedding norm", f"{norms.std():.4f}")
    stats_table.add_row("Min embedding norm", f"{norms.min():.4f}")
    stats_table.add_row("Max embedding norm", f"{norms.max():.4f}")
    
    console.print(stats_table)
    console.print()

    # Success message
    console.print("[bold green]✓ Test completed successfully![/bold green]\n")

    console.print("[bold]Next steps:[/bold]")
    console.print(f"1. Review embeddings: [cyan]{output_path}[/cyan]")
    console.print("2. Load embeddings for similarity computation:")
    console.print("   ```python")
    console.print("   import pandas as pd")
    console.print("   import numpy as np")
    console.print("   df = pd.read_parquet('data/processed/paecter_embeddings_awards_sample.parquet')")
    console.print("   embeddings = np.array([np.array(e) for e in df['embedding']])")
    console.print("   ```")
    console.print("3. Test with patents: Generate patent embeddings and compute similarities")
    console.print("4. Integrate with Dagster pipeline (see Phase 4 in testing guide)\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

