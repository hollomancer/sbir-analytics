#!/usr/bin/env python3
"""Quick test script for PaECTER with your SBIR data.

This script provides a simple way to test PaECTER embeddings and similarity
computation with sample SBIR awards and patents.

Usage:
    python scripts/test_paecter_quick.py

Requirements:
    uv pip install -e ".[paecter]"
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

import numpy as np
from rich.console import Console
from rich.table import Table

from src.ml.paecter_client import PaECTERClient


console = Console()


def main():
    """Run quick PaECTER test."""
    console.print("\n[bold blue]PaECTER Quick Test[/bold blue]", style="bold")
    console.print("Testing patent embeddings with sample SBIR and patent data\n")

    # Sample data
    awards = [
        {
            "id": "AWARD-001",
            "title": "Novel 3D Printing Method for Aerospace Components",
            "abstract": (
                "This Phase I SBIR project will develop an innovative additive manufacturing "
                "technique for producing high-strength aerospace components using advanced "
                "materials. The method combines selective laser melting with in-situ alloy "
                "formation to achieve superior mechanical properties."
            ),
        },
        {
            "id": "AWARD-002",
            "title": "Deep Learning for Drug Discovery",
            "abstract": (
                "This project proposes a novel deep learning architecture for predicting "
                "drug-target interactions. Using transformer-based models and molecular "
                "fingerprints, we aim to accelerate the drug discovery process and identify "
                "promising therapeutic candidates for cancer treatment."
            ),
        },
        {
            "id": "AWARD-003",
            "title": "High-Efficiency Perovskite Solar Cells",
            "abstract": (
                "This Phase II SBIR award supports the development of next-generation "
                "perovskite solar cells with improved stability and efficiency. Our approach "
                "uses novel encapsulation techniques and interface engineering to achieve "
                "power conversion efficiencies exceeding 25%."
            ),
        },
    ]

    patents = [
        {
            "id": "US-10123456",
            "title": "Method for Additive Manufacturing of Metal Parts",
            "abstract": (
                "A method for producing metal components using layer-by-layer deposition. "
                "The invention includes a laser system for selective melting of metal powder "
                "and control systems for optimizing part quality and mechanical properties."
            ),
        },
        {
            "id": "US-10234567",
            "title": "Neural Network Architecture for Molecular Property Prediction",
            "abstract": (
                "A deep learning system for predicting molecular properties and bioactivity. "
                "The invention uses graph neural networks to process molecular structures "
                "and transformer attention mechanisms for improved prediction accuracy."
            ),
        },
        {
            "id": "US-10345678",
            "title": "High-Performance Photovoltaic Device",
            "abstract": (
                "A solar cell device with improved efficiency and stability. The invention "
                "features a multi-layer architecture with perovskite absorber materials and "
                "advanced encapsulation for protection against environmental degradation."
            ),
        },
    ]

    # Step 1: Initialize client
    console.print("[yellow]Step 1:[/yellow] Initializing PaECTER client...")
    try:
        client = PaECTERClient()
        console.print(
            f"✓ Model loaded: {client.model_name} (dimension: {client.embedding_dim})\n",
            style="green",
        )
    except ImportError as e:
        console.print(
            f"[red]✗ Error: {e}[/red]\n"
            "[yellow]Install dependencies:[/yellow] uv pip install -e \".[paecter]\""
        )
        return 1
    except Exception as e:
        console.print(f"[red]✗ Error initializing client: {e}[/red]")
        return 1

    # Step 2: Generate award embeddings
    console.print("[yellow]Step 2:[/yellow] Generating embeddings for SBIR awards...")
    award_texts = [
        client.prepare_award_text(
            solicitation_title=None,
            abstract=award["abstract"],
            award_title=award["title"],
        )
        for award in awards
    ]

    try:
        award_result = client.generate_embeddings(award_texts, show_progress_bar=False)
        console.print(
            f"✓ Generated {award_result.input_count} award embeddings "
            f"(shape: {award_result.embeddings.shape})\n",
            style="green",
        )
    except Exception as e:
        console.print(f"[red]✗ Error generating award embeddings: {e}[/red]")
        return 1

    # Step 3: Generate patent embeddings
    console.print("[yellow]Step 3:[/yellow] Generating embeddings for patents...")
    patent_texts = [
        client.prepare_patent_text(patent["title"], patent["abstract"]) for patent in patents
    ]

    try:
        patent_result = client.generate_embeddings(patent_texts, show_progress_bar=False)
        console.print(
            f"✓ Generated {patent_result.input_count} patent embeddings "
            f"(shape: {patent_result.embeddings.shape})\n",
            style="green",
        )
    except Exception as e:
        console.print(f"[red]✗ Error generating patent embeddings: {e}[/red]")
        return 1

    # Step 4: Compute similarities
    console.print("[yellow]Step 4:[/yellow] Computing award-patent similarities...")
    similarities = client.compute_similarity(award_result.embeddings, patent_result.embeddings)
    console.print(
        f"✓ Computed similarity matrix (shape: {similarities.shape})\n", style="green"
    )

    # Step 5: Display results
    console.print("[bold blue]Results: Award-Patent Similarity Matrix[/bold blue]\n")

    # Create similarity table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Award", style="cyan", width=40)
    for patent in patents:
        table.add_column(f"{patent['id']}", justify="center", width=12)

    for i, award in enumerate(awards):
        row = [award["title"][:37] + "..." if len(award["title"]) > 40 else award["title"]]
        for j in range(len(patents)):
            score = similarities[i, j]
            # Color code by similarity score
            if score > 0.7:
                color = "green"
            elif score > 0.5:
                color = "yellow"
            else:
                color = "white"
            row.append(f"[{color}]{score:.3f}[/{color}]")
        table.add_row(*row)

    console.print(table)

    # Step 6: Show top matches
    console.print("\n[bold blue]Top Patent Matches for Each Award[/bold blue]\n")

    for i, award in enumerate(awards):
        console.print(f"[cyan]Award {i+1}:[/cyan] {award['title']}")

        # Get top 2 matches
        top_indices = np.argsort(similarities[i])[::-1][:2]
        for rank, idx in enumerate(top_indices, 1):
            score = similarities[i, idx]
            patent = patents[idx]

            # Color code
            if score > 0.7:
                color = "green"
            elif score > 0.5:
                color = "yellow"
            else:
                color = "white"

            console.print(
                f"  [{color}]{rank}. {patent['id']}: {patent['title']} "
                f"(similarity: {score:.3f})[/{color}]"
            )
        console.print()

    # Summary
    console.print("[bold green]✓ Test completed successfully![/bold green]\n")

    console.print("[bold]Next steps:[/bold]")
    console.print("1. Review the similarity scores above")
    console.print("2. Run full integration tests: [cyan]uv run pytest tests/integration/test_paecter_client.py -v[/cyan]")
    console.print("3. Test with your real data (see docs/PAECTER_TESTING_GUIDE.md)")
    console.print("4. Integrate with Dagster pipeline\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
