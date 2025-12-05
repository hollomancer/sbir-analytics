#!/usr/bin/env python3
"""Download USPTO data files using browser automation.

The USPTO Open Data Portal requires browser-based access to generate signed
CloudFront URLs for downloads. This script uses Playwright to automate the
download process.

Usage:
    python scripts/data/download_uspto_browser.py --dataset assignments
    python scripts/data/download_uspto_browser.py --dataset assignments --upload-s3

Requirements:
    pip install playwright
    python -m playwright install chromium
"""

import argparse
import asyncio
import hashlib
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

# USPTO Assignment Dataset files (2023 release)
USPTO_ASSIGNMENT_FILES = {
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
    print(f"📥 Starting download: {url}")

    async with page.expect_download(timeout=timeout_minutes * 60 * 1000) as download_info:
        await page.evaluate(f'() => {{ window.location.href = "{url}"; }}')

    download = await download_info.value
    print(f"   Signed URL: {download.url[:80]}...")

    # Wait for download to complete (important for large files)
    print(f"   Downloading... (timeout: {timeout_minutes} min)")

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

    print(f"✅ Downloaded: {output_path.name}")
    print(f"   Size: {size / 1024 / 1024:.1f} MB")
    print(f"   SHA256: {sha256[:16]}...")

    return {
        "path": str(output_path),
        "size": size,
        "sha256": sha256,
        "suggested_filename": download.suggested_filename,
    }


async def download_assignments(
    output_dir: Path,
    files: list[str] | None = None,
    upload_s3: bool = False,
    s3_bucket: str | None = None,
) -> list[dict]:
    """Download USPTO assignment files.

    Args:
        output_dir: Directory to save downloaded files
        files: List of files to download (default: all core files)
        upload_s3: Whether to upload to S3 after download
        s3_bucket: S3 bucket name for upload

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
        print("🌐 Establishing session with USPTO Open Data Portal...")
        await page.goto(
            "https://data.uspto.gov/ui/datasets/products/ECORSEXC",
            timeout=60000,
        )
        await asyncio.sleep(3)
        print("✅ Session established\n")

        for file_key in files:
            if file_key not in USPTO_ASSIGNMENT_FILES:
                print(f"⚠️  Unknown file: {file_key}, skipping")
                continue

            file_info = USPTO_ASSIGNMENT_FILES[file_key]
            output_path = output_dir / f"{file_key}.csv.zip"

            print(f"\n{'='*60}")
            print(f"Downloading: {file_key} (~{file_info['size_mb']} MB)")
            print(f"{'='*60}")

            try:
                result = await download_file(
                    page,
                    file_info["url"],
                    output_path,
                    timeout_minutes=max(30, file_info["size_mb"] // 10),
                )
                results.append({"file": file_key, **result})

                # Upload to S3 if requested
                if upload_s3 and s3_bucket:
                    import boto3

                    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
                    s3_key = f"raw/uspto/assignments/{date_str}/{file_key}.csv.zip"

                    print(f"📤 Uploading to s3://{s3_bucket}/{s3_key}")
                    s3 = boto3.client("s3")
                    s3.upload_file(
                        str(output_path),
                        s3_bucket,
                        s3_key,
                        ExtraArgs={
                            "ContentType": "application/zip",
                            "Metadata": {
                                "sha256": result["sha256"],
                                "source": "uspto-open-data-portal",
                                "downloaded_at": datetime.now(UTC).isoformat(),
                            },
                        },
                    )
                    print(f"✅ Uploaded to S3")

            except Exception as e:
                print(f"❌ Failed to download {file_key}: {e}")
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
        default=Path("/tmp/uspto_downloads"),
        help="Output directory for downloads",
    )
    parser.add_argument(
        "--upload-s3",
        action="store_true",
        help="Upload downloaded files to S3",
    )
    parser.add_argument(
        "--s3-bucket",
        default=os.environ.get("S3_BUCKET", "sbir-etl-production-data"),
        help="S3 bucket for upload",
    )

    args = parser.parse_args()

    print("🚀 USPTO Browser Download")
    print(f"   Dataset: {args.dataset}")
    print(f"   Output: {args.output_dir}")
    if args.upload_s3:
        print(f"   S3 Bucket: {args.s3_bucket}")
    print()

    try:
        results = asyncio.run(
            download_assignments(
                output_dir=args.output_dir,
                files=args.files,
                upload_s3=args.upload_s3,
                s3_bucket=args.s3_bucket,
            )
        )

        print("\n" + "=" * 60)
        print("📊 Download Summary")
        print("=" * 60)

        success = 0
        failed = 0
        total_size = 0

        for r in results:
            if "error" in r:
                print(f"❌ {r['file']}: {r['error']}")
                failed += 1
            else:
                print(f"✅ {r['file']}: {r['size'] / 1024 / 1024:.1f} MB")
                success += 1
                total_size += r["size"]

        print()
        print(f"Success: {success}/{len(results)}")
        print(f"Total size: {total_size / 1024 / 1024 / 1024:.2f} GB")

        if failed > 0:
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
