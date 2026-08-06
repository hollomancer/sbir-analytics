"""Repository-policy checks for committed research notebooks."""

import json
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
NOTEBOOK_ROOT = REPO_ROOT / "notebooks"

# Only enumerate notebooks tracked in the git index (not untracked/ignored
# *_executed.ipynb outputs that would be produced by the documented workflow).
# check=True so a missing git or a non-repository checkout fails loudly: an
# empty list would parametrize every policy check over nothing and pass.
_TRACKED_NOTEBOOKS = (
    subprocess.run(
        ["git", "ls-files", str(NOTEBOOK_ROOT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    )
    .stdout.strip()
    .splitlines()
)
NOTEBOOKS = sorted(REPO_ROOT / line for line in _TRACKED_NOTEBOOKS if line.endswith(".ipynb"))
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
