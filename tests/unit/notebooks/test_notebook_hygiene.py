"""Repository-policy checks for committed research notebooks."""

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
NOTEBOOK_ROOT = REPO_ROOT / "notebooks"
NOTEBOOKS = sorted(NOTEBOOK_ROOT.rglob("*.ipynb"))
SECRET_ASSIGNMENT = re.compile(
    r"(?:HF_TOKEN|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|SAM_GOV_API_KEY)\s*=\s*['\"][^'\"]+"
)


def load_notebook(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda path: str(path.relative_to(REPO_ROOT)))
def test_notebook_is_clean_and_reviewable(path: Path) -> None:
    notebook = load_notebook(path)

    assert notebook["nbformat"] == 4
    assert notebook["cells"], "committed notebooks must not be empty"

    source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
    assert "from src." not in source
    assert "import src." not in source
    assert not SECRET_ASSIGNMENT.search(source)

    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        assert cell.get("execution_count") is None
        assert cell.get("outputs", []) == []


@pytest.mark.parametrize(
    "path",
    sorted((NOTEBOOK_ROOT / "examples").glob("*.ipynb")),
    ids=lambda path: path.name,
)
def test_example_notebook_declares_research_contract(path: Path) -> None:
    notebook = load_notebook(path)
    opening = "".join(notebook["cells"][0]["source"])

    assert notebook["cells"][0]["cell_type"] == "markdown"
    assert "**Status:**" in opening
    assert "**Research" in opening
    assert "**Canonical computation:**" in opening


def test_notebook_workbench_has_template_and_examples() -> None:
    assert (NOTEBOOK_ROOT / "_template.ipynb").exists()
    assert len(list((NOTEBOOK_ROOT / "examples").glob("*.ipynb"))) >= 3
