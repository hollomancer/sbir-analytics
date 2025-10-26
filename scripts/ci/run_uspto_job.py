#!/usr/bin/env python3
"""
CI runner for the USPTO Dagster job.

This script imports the `uspto_validation_job` defined in:
  `sbir-etl/src/assets/jobs/uspto_job.py`

and executes it in-process. It's intended to be run inside the CI test container
after test/dev dependencies (like Dagster and pandas/pyarrow/pyreadstat) have
been installed at container startup.

Exit codes:
  0  - job executed and reported success
  1  - import failure or job not found
  2  - job executed but reported failure
  3  - unexpected exception while running the job
"""

from __future__ import annotations

import logging
import sys
import traceback
from typing import Any

# Configure basic logging so CI logs show what's happening
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("ci.run_uspto_job")


def _print_result_summary(result: Any) -> None:
    """
    Print a compact, human-readable summary of the Dagster job result.

    We attempt to read common attributes used by Dagster's in-process execution
    API. If attributes are missing, we fall back to repr().
    """
    logger.info("Job execution result summary:")

    # Common API: result.success (bool)
    if hasattr(result, "success"):
        logger.info("  success: %s", getattr(result, "success"))
    # Some versions expose .success_as_bool or similar; try a few fallbacks
    elif hasattr(result, "was_successful"):
        logger.info("  success (was_successful): %s", getattr(result, "was_successful"))
    else:
        logger.info("  result object: %s", repr(result))

    # If the result contains step/event info, show a short snippet if available
    if hasattr(result, "run_id"):
        logger.info("  run_id: %s", getattr(result, "run_id"))
    elif hasattr(result, "run"):
        try:
            run = getattr(result, "run")
            logger.info("  run: %s", getattr(run, "run_id", repr(run)))
        except Exception:
            pass


def main() -> int:
    # Import the job dynamically so import errors are reported clearly.
    try:
        # Import the job symbol from the project package
        # The CI container should have PYTHONPATH set such that `src` is importable.
        from src.assets.jobs.uspto_job import uspto_validation_job  # type: ignore
    except Exception:
        logger.error("Failed to import `uspto_validation_job` from src.assets.jobs.uspto_job")
        logger.debug("Traceback:", exc_info=True)
        return 1

    if uspto_validation_job is None:
        logger.error("`uspto_validation_job` is None (assets unavailable at import time).")
        return 1

    logger.info("Starting in-process execution of `uspto_validation_job`")

    try:
        # Primary execution path: use Dagster's in-process runner if available.
        # This is the recommended approach for lightweight CI runs.
        if hasattr(uspto_validation_job, "execute_in_process"):
            result = uspto_validation_job.execute_in_process()
            _print_result_summary(result)
            # Determine success
            success = getattr(result, "success", None)
            if success is True:
                logger.info("uspto_validation_job completed successfully.")
                return 0
            else:
                logger.error("uspto_validation_job completed but indicated failure.")
                return 2
        else:
            # If execute_in_process isn't present, try the `execute` method (older APIs)
            if hasattr(uspto_validation_job, "execute"):
                logger.info("Falling back to `execute()` API.")
                result = (
                    uspto_validation_job.execute_in_process()
                )  # keep consistent; may still exist
                _print_result_summary(result)
                success = getattr(result, "success", None)
                if success is True:
                    return 0
                else:
                    return 2
            else:
                logger.error(
                    "uspto_validation_job does not expose an in-process execution API "
                    "(no `execute_in_process`/`execute` attribute)."
                )
                return 1

    except Exception as exc:  # pragma: no cover - runtime guard
        logger.error("Exception while executing `uspto_validation_job`: %s", exc)
        logger.debug("Full traceback:\n%s", traceback.format_exc())
        return 3


if __name__ == "__main__":  # pragma: no cover - script entrypoint
    rc = main()
    if rc != 0:
        logger.error("Runner exiting with code %d", rc)
    else:
        logger.info("Runner finished successfully (exit 0).")
    sys.exit(rc)
