#!/usr/bin/env python3
"""Debug script to investigate high similarity scores in PaECTER embeddings.

This script helps diagnose why certain award-patent pairs have unexpectedly
high similarity scores by showing the actual text being embedded and computing
detailed similarity metrics.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add src to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.ml.paecter_client import PaECTERClient

console = Console()


def main():
    """Debug PaECTER similarity scores."""
    console.print("\n[bold blue]PaECTER Similarity Debugger[/bold blue]\n")

    # Check for HF_TOKEN
    if not os.getenv("HF_TOKEN"):
        console.print(
            "[bold red]Warning:[/bold red] HF_TOKEN environment variable not set.\n"
            "Set it with: export HF_TOKEN=\"your_token_here\"\n"
        )
        return 1

    # Initialize client
    console.print("[yellow]Initializing PaECTER client...[/yellow]")
    try:
        client = PaECTERClient()
        console.print(f"✓ Client initialized: {client.model_name}\n", style="green")
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        return 1

    # Problematic pair from the test
    award = {
        "title": "Deep Learning for Drug Discovery",
        "abstract": (
            "This project proposes a novel deep learning architecture for predicting "
            "drug-target interactions. Using transformer-based models and molecular "
            "fingerprints, we aim to accelerate the drug discovery process and identify "
            "promising therapeutic candidates for cancer treatment."
        ),
    }

    patent = {
        "title": "High-Performance Photovoltaic Device",
        "abstract": (
            "A solar cell device with improved efficiency and stability. The invention "
            "features a multi-layer architecture with perovskite absorber materials and "
            "advanced encapsulation for protection against environmental degradation."
        ),
    }

    # Prepare texts
    award_text = client.prepare_award_text(
        solicitation_title=None,
        abstract=award["abstract"],
        award_title=award["title"],
    )

    patent_text = client.prepare_patent_text(patent["title"], patent["abstract"])

    # Display prepared texts
    console.print("[bold blue]Prepared Texts[/bold blue]\n")

    console.print(Panel(
        f"[cyan]Award Text:[/cyan]\n{award_text}",
        title="Deep Learning for Drug Discovery",
        border_style="cyan",
    ))
    console.print()

    console.print(Panel(
        f"[yellow]Patent Text:[/yellow]\n{patent_text}",
        title="High-Performance Photovoltaic Device",
        border_style="yellow",
    ))
    console.print()

    # Generate embeddings
    console.print("[yellow]Generating embeddings...[/yellow]")
    try:
        award_result = client.generate_embeddings([award_text], show_progress_bar=False)
        patent_result = client.generate_embeddings([patent_text], show_progress_bar=False)
        console.print("✓ Embeddings generated\n", style="green")
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        return 1

    # Compute similarity
    similarity = client.compute_similarity(
        award_result.embeddings,
        patent_result.embeddings
    )[0, 0]

    # Compute additional metrics
    award_emb = award_result.embeddings[0]
    patent_emb = patent_result.embeddings[0]

    # Embedding statistics
    award_norm = np.linalg.norm(award_emb)
    patent_norm = np.linalg.norm(patent_emb)
    dot_product = np.dot(award_emb, patent_emb)
    euclidean_dist = np.linalg.norm(award_emb - patent_emb)

    # Word overlap analysis
    award_words = set(award_text.lower().split())
    patent_words = set(patent_text.lower().split())
    common_words = award_words & patent_words
    unique_award_words = award_words - patent_words
    unique_patent_words = patent_words - award_words

    # Display results
    console.print("[bold blue]Similarity Analysis[/bold blue]\n")

    metrics_table = Table(show_header=True, header_style="bold magenta")
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Value", justify="right")

    metrics_table.add_row("Cosine Similarity", f"{similarity:.4f}")
    metrics_table.add_row("Dot Product", f"{dot_product:.4f}")
    metrics_table.add_row("Euclidean Distance", f"{euclidean_dist:.4f}")
    metrics_table.add_row("Award Embedding Norm", f"{award_norm:.4f}")
    metrics_table.add_row("Patent Embedding Norm", f"{patent_norm:.4f}")

    console.print(metrics_table)
    console.print()

    # Word overlap analysis
    console.print("[bold blue]Text Overlap Analysis[/bold blue]\n")

    overlap_table = Table(show_header=True, header_style="bold magenta")
    overlap_table.add_column("Category", style="cyan")
    overlap_table.add_column("Count", justify="right")
    overlap_table.add_column("Words", style="dim")

    overlap_table.add_row(
        "Common Words",
        str(len(common_words)),
        ", ".join(sorted(common_words))[:100] + ("..." if len(", ".join(sorted(common_words))) > 100 else "")
    )
    overlap_table.add_row(
        "Award-Only Words",
        str(len(unique_award_words)),
        ", ".join(sorted(list(unique_award_words)[:10])) + ("..." if len(unique_award_words) > 10 else "")
    )
    overlap_table.add_row(
        "Patent-Only Words",
        str(len(unique_patent_words)),
        ", ".join(sorted(list(unique_patent_words)[:10])) + ("..." if len(unique_patent_words) > 10 else "")
    )

    console.print(overlap_table)
    console.print()

    # Compare with other pairs for context
    console.print("[bold blue]Comparison with Other Pairs[/bold blue]\n")

    # Test with a clearly related pair
    related_award = {
        "title": "Deep Learning for Drug Discovery",
        "abstract": award["abstract"],
    }

    related_patent = {
        "title": "Neural Network Architecture for Molecular Property Prediction",
        "abstract": (
            "A deep learning system for predicting molecular properties and bioactivity. "
            "The invention uses graph neural networks to process molecular structures "
            "and transformer attention mechanisms for improved prediction accuracy."
        ),
    }

    related_award_text = client.prepare_award_text(
        solicitation_title=None,
        abstract=related_award["abstract"],
        award_title=related_award["title"],
    )

    related_patent_text = client.prepare_patent_text(
        related_patent["title"],
        related_patent["abstract"]
    )

    related_award_result = client.generate_embeddings([related_award_text], show_progress_bar=False)
    related_patent_result = client.generate_embeddings([related_patent_text], show_progress_bar=False)
    related_similarity = client.compute_similarity(
        related_award_result.embeddings,
        related_patent_result.embeddings
    )[0, 0]

    # Test with a clearly unrelated pair
    unrelated_patent = {
        "title": "Method for Additive Manufacturing of Metal Parts",
        "abstract": (
            "A method for producing metal components using layer-by-layer deposition. "
            "The invention includes a laser system for selective melting of metal powder "
            "and control systems for optimizing part quality and mechanical properties."
        ),
    }

    unrelated_patent_text = client.prepare_patent_text(
        unrelated_patent["title"],
        unrelated_patent["abstract"]
    )

    unrelated_patent_result = client.generate_embeddings([unrelated_patent_text], show_progress_bar=False)
    unrelated_similarity = client.compute_similarity(
        award_result.embeddings,
        unrelated_patent_result.embeddings
    )[0, 0]

    comparison_table = Table(show_header=True, header_style="bold magenta")
    comparison_table.add_column("Pair", style="cyan")
    comparison_table.add_column("Similarity", justify="right")
    comparison_table.add_column("Expected", style="dim")

    comparison_table.add_row(
        "Drug Discovery ↔ Molecular Prediction",
        f"{related_similarity:.4f}",
        "High (related)"
    )
    comparison_table.add_row(
        "Drug Discovery ↔ Photovoltaic Device",
        f"{similarity:.4f}",
        "Low (unrelated)"
    )
    comparison_table.add_row(
        "Drug Discovery ↔ Additive Manufacturing",
        f"{unrelated_similarity:.4f}",
        "Low (unrelated)"
    )

    console.print(comparison_table)
    console.print()

    # Analysis and recommendations
    console.print("[bold blue]Analysis[/bold blue]\n")

    if similarity > 0.85:
        console.print(
            "[yellow]⚠ High similarity detected[/yellow] between unrelated domains.\n"
            "This could indicate:\n"
            "1. Model is picking up on general technical language patterns\n"
            "2. Shared vocabulary (e.g., 'architecture', 'materials', 'efficiency')\n"
            "3. Similar sentence structure or length\n"
            "4. Model limitations in domain-specific discrimination\n\n"
            "[bold]Recommendations:[/bold]\n"
            "- Consider using domain-specific filtering before similarity matching\n"
            "- Use threshold-based filtering (e.g., only consider similarities > 0.9)\n"
            "- Add keyword-based pre-filtering for domain matching\n"
            "- Test with larger, more diverse datasets to establish baseline thresholds\n"
        )

    console.print()

    return 0


if __name__ == "__main__":
    sys.exit(main())

