"""Download USPTO data files using browser automation.

Epistemic tier: pipelines.

The USPTO Open Data Portal requires browser-based access to generate signed
CloudFront URLs for downloads. This script uses Playwright to automate the
download process.

Usage:
    python scripts/data/download_uspto_browser.py --dataset assignments

Requirements:
    pip install playwright
    python -m playwright install chromium
"""

import argparse
import asyncio
import hashlib
import sys
import tempfile
from pathlib import Path
from typing import TypedDict

from loguru import logger

EPISTEMIC_TIER = "pipelines"


class AssignmentFile(TypedDict):
    """One declared file in the USPTO assignment data release."""

    url: str
    size_mb: int


# USPTO Assignment Dataset files (2023 release)
USPTO_ASSIGNMENT_FILES: dict[str, AssignmentFile] = {
    "assignment": {
        "url": "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/assignment.csv.zip",
        "size_mb": 365,
    },
    "assignor": {
        "url": "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/assignor.csv.zip",
        "size_mb": 287,
    },
    "assignee": {
        "url": "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/assignee.csv.zip",
        "size_mb": 279,
    },
    "documentid": {
        "url": "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/documentid.csv.zip",
        "size_mb": 700,
    },
    "full": {
        "url": "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/csv.zip",
        "size_mb": 1823,
    },
}


async def download_file(page, url: str, output_path: Path, timeout_minutes: int = 30) -> dict:
    """Download a file using the browser session.

    Args:
        page: Playwright page object with active session
        url: USPTO download URL
        output_path: Path to save the downloaded file
        timeout_minutes: Download timeout in minutes

    Returns:
        dict with download info (path, size, sha256)
    """
    logger.info(f"Starting download: {url}")

    async with page.expect_download(timeout=timeout_minutes * 60 * 1000) as download_info:
        await page.evaluate(f'() => {{ window.location.href = "{url}"; }}')

    download = await download_info.value
    logger.info(f"Signed URL: {download.url[:80]}...")

    # Wait for download to complete (important for large files)
    logger.info(f"Downloading... (timeout: {timeout_minutes} min)")

    # Get the download path - this waits for completion
    temp_path = await download.path()
    if temp_path is None:
        raise RuntimeError("Download failed - no file path returned")

    # Copy to output path
    import shutil

    shutil.copy(temp_path, str(output_path))

    # Calculate hash
    hasher = hashlib.sha256()
    with open(output_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)

    size = output_path.stat().st_size
    sha256 = hasher.hexdigest()

    logger.info(f"Downloaded: {output_path.name}")
    logger.info(f"Size: {size / 1024 / 1024:.1f} MB")
    logger.info(f"SHA256: {sha256[:16]}...")

    return {
        "path": str(output_path),
        "size": size,
        "sha256": sha256,
        "suggested_filename": download.suggested_filename,
    }


async def download_assignments(
    output_dir: Path,
    files: list[str] | None = None,
) -> list[dict]:
    """Download USPTO assignment files.

    Args:
        output_dir: Directory to save downloaded files
        files: List of files to download (default: all core files)

    Returns:
        List of download results
    """
    from playwright.async_api import async_playwright

    if files is None:
        # Download core files needed for the pipeline
        files = ["assignment", "assignor", "assignee", "documentid"]

    output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            accept_downloads=True,
        )
        page = await context.new_page()

        # Load the main page to establish session
        logger.info("Establishing session with USPTO Open Data Portal...")
        await page.goto(
            "https://data.uspto.gov/ui/datasets/products/ECORSEXC",
            timeout=60000,
        )
        await asyncio.sleep(3)
        logger.info("Session established")

        for file_key in files:
            if file_key not in USPTO_ASSIGNMENT_FILES:
                logger.warning(f"Unknown file: {file_key}, skipping")
                continue

            file_info = USPTO_ASSIGNMENT_FILES[file_key]
            source_url = str(file_info["url"])
            size_mb = int(file_info["size_mb"])
            output_path = output_dir / f"{file_key}.csv.zip"

            logger.info(f"Downloading: {file_key} (~{size_mb} MB)")

            try:
                result = await download_file(
                    page,
                    source_url,
                    output_path,
                    timeout_minutes=max(30, size_mb // 10),
                )
                results.append({"file": file_key, **result})
            except Exception as e:
                logger.error(f"Failed to download {file_key}: {e}")
                results.append({"file": file_key, "error": str(e)})

        await browser.close()

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Download USPTO data using browser automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dataset",
        required=True,
        choices=["assignments"],
        help="Dataset to download",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        choices=list(USPTO_ASSIGNMENT_FILES.keys()),
        help="Specific files to download (default: assignment, assignor, assignee, documentid)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "uspto_downloads",
        help="Output directory for downloads",
    )

    args = parser.parse_args()

    logger.info("USPTO Browser Download")
    logger.info(f"Dataset: {args.dataset}")
    logger.info(f"Output: {args.output_dir}")

    try:
        results = asyncio.run(
            download_assignments(
                output_dir=args.output_dir,
                files=args.files,
            )
        )

        logger.info("Download Summary")

        success = 0
        failed = 0
        total_size = 0

        for r in results:
            if "error" in r:
                logger.error(f"{r['file']}: {r['error']}")
                failed += 1
            else:
                logger.info(f"{r['file']}: {r['size'] / 1024 / 1024:.1f} MB")
                success += 1
                total_size += r["size"]

        logger.info(f"Success: {success}/{len(results)}")
        logger.info(f"Total size: {total_size / 1024 / 1024 / 1024:.2f} GB")

        if failed > 0:
            sys.exit(1)

    except Exception as e:
        logger.exception(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
