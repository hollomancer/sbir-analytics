"""Integration tests for USPTO download script.

These tests verify the download script's functionality without actually
downloading large files or uploading to S3.
"""

import subprocess
import sys
from pathlib import Path


def test_download_script_help():
    """Test that the download script shows help message."""
    result = subprocess.run(
        [sys.executable, "scripts/data/download_uspto.py", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Download USPTO data to S3" in result.stdout
    assert "--dataset" in result.stdout
    assert "patentsview" in result.stdout
    assert "assignments" in result.stdout
    assert "ai_patents" in result.stdout


def test_download_script_invalid_dataset():
    """Test that the download script rejects invalid datasets."""
    result = subprocess.run(
        [sys.executable, "scripts/data/download_uspto.py", "--dataset", "invalid"],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "invalid choice" in result.stderr.lower()


def test_download_script_invalid_table():
    """Test that the download script rejects invalid PatentsView tables."""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/data/download_uspto.py",
            "--dataset",
            "patentsview",
            "--table",
            "invalid_table",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "invalid choice" in result.stderr.lower()


def test_download_script_exists():
    """Test that the download script file exists and is executable."""
    script_path = Path("scripts/data/download_uspto.py")
    assert script_path.exists(), "Download script not found"
    assert script_path.is_file(), "Download script is not a file"

    # Check if file has execute permissions (on Unix-like systems)
    if sys.platform != "win32":
        import stat

        assert script_path.stat().st_mode & stat.S_IXUSR, "Script is not executable"


def test_download_script_imports():
    """Test that the download script can be imported without errors."""
    # This verifies all dependencies are available
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, 'scripts/data'); import download_uspto",
        ],
        capture_output=True,
        text=True,
    )

    # Should succeed or fail with specific import errors (not syntax errors)
    if result.returncode != 0:
        # Allow missing boto3 or requests in test environment
        assert any(
            msg in result.stderr
            for msg in ["No module named 'boto3'", "No module named 'requests'"]
        ), f"Unexpected import error: {result.stderr}"
