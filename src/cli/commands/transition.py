"""Transition detection CLI commands."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import typer

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


def _transition_asset_keys() -> list[str]:
    """Return asset key strings for transition MVP assets."""
    return [
        "validated_contracts_sample",
        "enriched_vendor_resolution",
        "transformed_transition_scores",
        "transformed_transition_evidence",
        "transformed_transition_detections",
    ]


@app.command("mvp")
def run_transition_mvp(
    ctx: typer.Context,
    contracts_path: Path | None = typer.Option(
        None,
        help="Contracts parquet path override (defaults to transition_contracts_output)",
    ),
    seed: bool = typer.Option(True, help="Seed a small contracts sample if missing"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
) -> None:
    """Execute the transition MVP pipeline via Dagster."""

    context: CommandContext = ctx.obj

    default_contract_path = Path(context.config.paths.resolve_path("transition_contracts_output"))
    seed_path = contracts_path or default_contract_path

    if seed:
        _seed_contracts(seed_path, verbose)

    ensure_parent_dir(Path("reports/validation/transition_mvp.json"))

    env_key = "SBIR_ETL__TRANSITION__CONTRACTS_SAMPLE__PATH"
    previous_value = os.environ.get(env_key)
    if contracts_path is not None:
        os.environ[env_key] = str(seed_path)

    try:
        result = context.dagster_client.trigger_materialization(
            asset_keys=_transition_asset_keys(),
        )
    except Exception as exc:
        context.console.print(f"[red]Failed to trigger transition MVP: {exc}[/red]")
        raise typer.Exit(code=1)
    finally:
        if contracts_path is not None:
            if previous_value is None:
                os.environ.pop(env_key, None)
            else:
                os.environ[env_key] = previous_value

    if result.status != "success":
        context.console.print(f"[red]Transition MVP run failed (run_id={result.run_id})[/red]")
        raise typer.Exit(code=1)

    if verbose:
        context.console.print(f"[green]Transition MVP completed (run_id={result.run_id})[/green]")


def register_command(main_app: typer.Typer) -> None:
    main_app.add_typer(app, name="transition")
