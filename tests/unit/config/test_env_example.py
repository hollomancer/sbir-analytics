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
    } <= keys
