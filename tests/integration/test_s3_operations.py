"""Integration tests for S3 operations with real AWS."""

import os

import boto3
import pytest

from src.utils.cloud_storage import build_s3_path, resolve_data_path


pytestmark = [pytest.mark.integration, pytest.mark.s3]


@pytest.fixture
def s3_test_bucket():
    """Get test S3 bucket from environment."""
    bucket = os.getenv("TEST_S3_BUCKET", "sbir-analytics-test")
    return bucket


@pytest.fixture
def s3_client():
    """Create S3 client."""
    return boto3.client("s3")


@pytest.fixture
def test_key_prefix():
    """Generate unique test key prefix."""
    import uuid

    return f"test/{uuid.uuid4()}"


@pytest.fixture(autouse=True)
def cleanup_test_files(s3_client, s3_test_bucket, test_key_prefix):
    """Cleanup test files after each test."""
    yield
    # Cleanup after test
    try:
        response = s3_client.list_objects_v2(Bucket=s3_test_bucket, Prefix=test_key_prefix)
        if "Contents" in response:
            objects = [{"Key": obj["Key"]} for obj in response["Contents"]]
            s3_client.delete_objects(Bucket=s3_test_bucket, Delete={"Objects": objects})
    except Exception:
        pass  # Best effort cleanup


@pytest.mark.skipif(not os.getenv("AWS_ACCESS_KEY_ID"), reason="AWS credentials required")
class TestS3Upload:
    """Test S3 upload operations."""

    def test_upload_small_file(self, s3_client, s3_test_bucket, test_key_prefix, tmp_path):
        """Test uploading a small file to S3."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_content = "test content"
        test_file.write_text(test_content)

        # Upload to S3
        key = f"{test_key_prefix}/test.txt"
        s3_client.upload_file(str(test_file), s3_test_bucket, key)

        # Verify upload
        response = s3_client.get_object(Bucket=s3_test_bucket, Key=key)
        downloaded_content = response["Body"].read().decode("utf-8")

        assert downloaded_content == test_content

    def test_upload_binary_file(self, s3_client, s3_test_bucket, test_key_prefix, tmp_path):
        """Test uploading a binary file to S3."""
        # Create test file
        test_file = tmp_path / "test.bin"
        test_content = b"\x00\x01\x02\x03\x04"
        test_file.write_bytes(test_content)

        # Upload to S3
        key = f"{test_key_prefix}/test.bin"
        s3_client.upload_file(str(test_file), s3_test_bucket, key)

        # Verify upload
        response = s3_client.get_object(Bucket=s3_test_bucket, Key=key)
        downloaded_content = response["Body"].read()

        assert downloaded_content == test_content


@pytest.mark.skipif(not os.getenv("AWS_ACCESS_KEY_ID"), reason="AWS credentials required")
class TestS3Download:
    """Test S3 download operations."""

    def test_download_file(self, s3_client, s3_test_bucket, test_key_prefix, tmp_path):
        """Test downloading a file from S3."""
        # Upload test file
        key = f"{test_key_prefix}/download_test.txt"
        test_content = "download test content"
        s3_client.put_object(Bucket=s3_test_bucket, Key=key, Body=test_content.encode())

        # Download file
        download_path = tmp_path / "downloaded.txt"
        s3_client.download_file(s3_test_bucket, key, str(download_path))

        # Verify download
        assert download_path.read_text() == test_content

    def test_resolve_data_path_with_s3(self, s3_client, s3_test_bucket, test_key_prefix):
        """Test resolve_data_path with real S3 URL."""
        # Upload test file
        key = f"{test_key_prefix}/resolve_test.txt"
        test_content = "resolve test content"
        s3_client.put_object(Bucket=s3_test_bucket, Key=key, Body=test_content.encode())

        # Resolve S3 path
        s3_url = f"s3://{s3_test_bucket}/{key}"
        resolved_path = resolve_data_path(s3_url)

        # Verify resolved path exists and has correct content
        assert resolved_path.exists()
        assert resolved_path.read_text() == test_content


@pytest.mark.skipif(not os.getenv("AWS_ACCESS_KEY_ID"), reason="AWS credentials required")
class TestS3Fallback:
    """Test S3 fallback to local."""

    def test_fallback_to_local_when_s3_missing(self, s3_test_bucket, test_key_prefix, tmp_path):
        """Test fallback to local file when S3 file doesn't exist."""
        # Create local fallback
        local_file = tmp_path / "fallback.txt"
        local_file.write_text("fallback content")

        # Try to resolve non-existent S3 file
        s3_url = f"s3://{s3_test_bucket}/{test_key_prefix}/nonexistent.txt"
        resolved_path = resolve_data_path(s3_url, local_fallback=local_file)

        # Should use local fallback
        assert resolved_path == local_file
        assert resolved_path.read_text() == "fallback content"

    def test_prefer_local_over_s3(self, s3_client, s3_test_bucket, test_key_prefix, tmp_path):
        """Test prefer_local flag uses local even when S3 exists."""
        # Upload to S3
        key = f"{test_key_prefix}/prefer_test.txt"
        s3_client.put_object(Bucket=s3_test_bucket, Key=key, Body=b"s3 content")

        # Create local file
        local_file = tmp_path / "local.txt"
        local_file.write_text("local content")

        # Resolve with prefer_local=True
        s3_url = f"s3://{s3_test_bucket}/{key}"
        resolved_path = resolve_data_path(s3_url, local_fallback=local_file, prefer_local=True)

        # Should use local file
        assert resolved_path == local_file
        assert resolved_path.read_text() == "local content"


@pytest.mark.skipif(not os.getenv("AWS_ACCESS_KEY_ID"), reason="AWS credentials required")
class TestS3PathBuilding:
    """Test S3 path building utilities."""

    def test_build_s3_path_with_bucket(self, s3_test_bucket):
        """Test building S3 path with explicit bucket."""
        result = build_s3_path("data/test.txt", bucket=s3_test_bucket)

        assert result == f"s3://{s3_test_bucket}/data/test.txt"

    def test_build_s3_path_with_env_bucket(self, s3_test_bucket):
        """Test building S3 path using environment bucket."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("SBIR_ANALYTICS_S3_BUCKET", s3_test_bucket)
            result = build_s3_path("data/test.txt")

            assert result == f"s3://{s3_test_bucket}/data/test.txt"


@pytest.mark.skipif(not os.getenv("AWS_ACCESS_KEY_ID"), reason="AWS credentials required")
class TestS3Permissions:
    """Test S3 permissions and access."""

    def test_can_list_bucket(self, s3_client, s3_test_bucket, test_key_prefix):
        """Test that we can list objects in the test bucket."""
        # Upload a test file
        key = f"{test_key_prefix}/list_test.txt"
        s3_client.put_object(Bucket=s3_test_bucket, Key=key, Body=b"test")

        # List objects
        response = s3_client.list_objects_v2(Bucket=s3_test_bucket, Prefix=test_key_prefix)

        assert "Contents" in response
        assert len(response["Contents"]) >= 1

    def test_can_delete_objects(self, s3_client, s3_test_bucket, test_key_prefix):
        """Test that we can delete objects from the test bucket."""
        # Upload a test file
        key = f"{test_key_prefix}/delete_test.txt"
        s3_client.put_object(Bucket=s3_test_bucket, Key=key, Body=b"test")

        # Delete object
        s3_client.delete_object(Bucket=s3_test_bucket, Key=key)

        # Verify deletion
        response = s3_client.list_objects_v2(Bucket=s3_test_bucket, Prefix=key)
        assert "Contents" not in response
