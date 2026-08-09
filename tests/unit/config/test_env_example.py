from pathlib import Path


ENV_EXAMPLE = Path(__file__).parents[3] / ".env.example"


def _documented_keys() -> set[str]:
    return {
        line.partition("=")[0]
        for raw_line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if (line := raw_line.strip()) and not line.startswith("#") and "=" in line
    }


def test_env_example_documents_the_supported_runtime_selectors() -> None:
    keys = _documented_keys()

    assert {
        "ENVIRONMENT",
        "SBIR_ETL__PIPELINE__ENVIRONMENT",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "NEO4J_DATABASE",
    } <= keys

    assert {
        "SBIR_ETL__NEO4J__BOLT_URL",
        "SBIR_ETL__NEO4J__HOST",
        "SBIR_ETL__NEO4J__PORT",
        "SBIR_ETL__DATA_DIR",
        "SBIR_ETL__CONFIG_DIR",
        "SBIR_ETL__LOG_DIR",
        "SBIR_ETL__METRICS_DIR",
    }.isdisjoint(keys)
