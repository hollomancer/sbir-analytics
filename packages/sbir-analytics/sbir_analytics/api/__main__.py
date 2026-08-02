"""CLI entry point for the private analytics API."""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "sbir_analytics.api.app:app",
        # Binds all interfaces *inside the container*, which is required to
        # accept traffic from the compose network. The security boundary is the
        # host publish: docker-compose.server.yml pins it to 127.0.0.1, and
        # server-check rejects a non-loopback SERVER_LOOPBACK.
        host=os.getenv("SBIR_ANALYTICS_API_HOST", "0.0.0.0"),  # noqa: S104 # nosec B104
        port=int(os.getenv("SBIR_ANALYTICS_API_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
