#!/usr/bin/env python3
"""Freeze a study bundle and optionally run it on an external analysis provider.

Epistemic tier: exploratory. Provider output is not citable. Upload is
fail-closed without ``--allow-external-upload``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


EPISTEMIC_TIER = "exploratory"

REPO = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export a frozen study bundle to an external analysis provider "
            "and import the exploratory artifacts."
        )
    )
    parser.add_argument("--provider", required=True, choices=["edison"])
    parser.add_argument("--study", required=True, help="Study id under studies/<id>/")
    parser.add_argument(
        "--dataset",
        action="append",
        required=True,
        help="Dataset file to include. Repeat for multiple files.",
    )
    parser.add_argument(
        "--prompt",
        help="Prompt file. Defaults to studies/<id>/external_prompt.md when present.",
    )
    parser.add_argument("--data-dictionary", dest="data_dictionary")
    parser.add_argument("--constraints", help="Replacement constraints file")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument(
        "--allow-external-upload",
        action="store_true",
        help="Required for any network upload. Fail-closed without this flag.",
    )
    parser.add_argument(
        "--bundle-only",
        action="store_true",
        help="Write the frozen bundle and stop before contacting a provider.",
    )
    parser.add_argument("--output-dir", dest="output_dir")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from sbir_analytics.external_analysis import (
        ExternalAnalysisError,
        run_external_analysis,
    )

    datasets = [Path(item) for item in args.dataset]
    try:
        run = run_external_analysis(
            repository_root=REPO,
            provider=args.provider,
            study_id=args.study,
            datasets=datasets,
            allow_external_upload=args.allow_external_upload,
            prompt=Path(args.prompt) if args.prompt else None,
            data_dictionary=Path(args.data_dictionary) if args.data_dictionary else None,
            constraints=Path(args.constraints) if args.constraints else None,
            max_steps=args.max_steps,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            bundle_only=args.bundle_only,
        )
    except ExternalAnalysisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(run.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
