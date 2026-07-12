"""CLI entry point for the private analytics API."""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "sbir_analytics.api.app:app",
        host=os.getenv("SBIR_ANALYTICS_API_HOST", "0.0.0.0"),
        port=int(os.getenv("SBIR_ANALYTICS_API_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
