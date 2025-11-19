"""Transition detection CLI commands."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import typer
from rich.panel import Panel

from src.utils.common.path_utils import ensure_parent_dir

from ..context import CommandContext


app = typer.Typer(name="transition", help="Transition detection utilities")


def _seed_contracts(path: Path, verbose: bool) -> None:
    if path.exists() or path.with_suffix(".csv").exists():
        if verbose:
            typer.echo(f"[dim]Contracts sample already present at {path}[/dim]")
        return

    ensure_parent_dir(path)
    df = pd.DataFrame(
        [
            {
                "contract_id": "C1",
                "piid": "PIID-001",
                "fain": None,
                "vendor_uei": "UEI123",
                "vendor_duns": None,
                "vendor_name": "UEI Vendor Inc",
                "action_date": "2023-01-01",
                "obligated_amount": 100000,
                "awarding_agency_code": "9700",
                "awarding_agency_name": "DEPT OF DEFENSE",
            },
            {
                "contract_id": "C2",
                "piid": "PIID-002",
                "fain": None,
                "vendor_uei": None,
                "vendor_duns": None,
                "vendor_name": "Acme Corporation",
                "action_date": "2023-02-01",
                "obligated_amount": 50000,
                "awarding_agency_code": "9700",
                "awarding_agency_name": "DEPT OF DEFENSE",
            },
        ]
    )
    try:
        df.to_parquet(path, index=False)
    except Exception:  # pragma: no cover - fallback for systems without pyarrow
        csv_path = path.with_suffix(".csv")
        df.to_csv(csv_path, index=False)
        typer.echo(f"[yellow]PyArrow missing; wrote contracts seed to {csv_path}[/yellow]")


def _build_asset_context() -> Any:
    from src.assets.transition import AssetExecutionContext

    try:
        return AssetExecutionContext()
    except TypeError as exc:
        if "op_execution_context" not in str(exc):
            raise
        # Create minimal mock Dagster op context
        mock_run = SimpleNamespace(run_id="transition-cli")
        mock_log = SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
            error=lambda *args, **kwargs: None,
            exception=lambda *args, **kwargs: None,
        )
        mock_op_ctx = SimpleNamespace(
            log=mock_log,
            instance=None,
            resources=SimpleNamespace(),
            run=mock_run,
            run_id="transition-cli",
        )
        return AssetExecutionContext(mock_op_ctx)


@app.command("mvp")
def run_transition_mvp(
    ctx: typer.Context,
    contracts_path: Path = typer.Option(
        Path("data/processed/contracts_sample.parquet"),
        help="Contracts sample parquet path (CSV fallback if parquet unavailable)",
    ),
    seed: bool = typer.Option(True, help="Seed a small contracts sample if missing"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
) -> None:
    """Execute the transition MVP pipeline without Dagster."""

    context: CommandContext = ctx.obj

    if seed:
        _seed_contracts(contracts_path, verbose)

    ensure_parent_dir(Path("reports/validation/transition_mvp.json"))

    from src.assets.transition import (
        enriched_vendor_resolution,
        transformed_transition_detections,
        transformed_transition_evidence,
        transformed_transition_scores,
        validated_contracts_sample,
    )

    asset_ctx = _build_asset_context()

    try:
        contracts_output = validated_contracts_sample(asset_ctx)
        vendor_output = enriched_vendor_resolution(asset_ctx)
        scores_output = transformed_transition_scores(asset_ctx)
        evidence_output = transformed_transition_evidence(asset_ctx)
        detections_output = transformed_transition_detections(asset_ctx)
    except Exception as exc:
        context.console.print(Panel(f"[red]Transition MVP failed: {exc}[/red]", title="Error"))
        raise typer.Exit(code=1)

    if verbose:
        context.console.print("[green]Transition MVP completed successfully[/green]")

    # Surface metadata paths if available
    for name, output in [
        ("contracts_sample", contracts_output),
        ("vendor_resolution", vendor_output),
        ("transition_scores", scores_output),
        ("transition_evidence", evidence_output),
        ("transition_detections", detections_output),
    ]:
        metadata = getattr(output, "metadata", None)
        if metadata:
            context.console.print(
                Panel(
                    f"{name} metadata:\n" + "\n".join(f"- {k}: {v}" for k, v in metadata.items()),
                    title=f"{name.title()}",
                    border_style="cyan",
                )
            )


def register_command(main_app: typer.Typer) -> None:
    main_app.add_typer(app, name="transition")
