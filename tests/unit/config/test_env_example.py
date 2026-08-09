from pathlib import Path


ENV_EXAMPLE = Path(__file__).parents[3] / ".env.example"
COMPOSE_FILE = Path(__file__).parents[3] / "docker-compose.yml"


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
        "NEO4J_USERNAME",
        "SBIR_ETL__NEO4J__BOLT_URL",
    } <= keys

    nested_neo4j_keys = {key for key in keys if key.startswith("SBIR_ETL__NEO4J__")}
    assert nested_neo4j_keys == {"SBIR_ETL__NEO4J__BOLT_URL"}


def test_compose_forwards_every_documented_direct_neo4j_setting() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    common_environment = compose.split("x-common-environment:", 1)[1].split(
        "x-dev-environment:", 1
    )[0]

    for key in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_DATABASE"):
        assert f"  {key}:" in common_environment
