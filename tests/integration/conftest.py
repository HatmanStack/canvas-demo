"""Integration test fixtures using LocalStack."""

import contextlib
import os
import urllib.request

import boto3
import pytest
from botocore.config import Config

LOCALSTACK_URL = os.getenv("LOCALSTACK_URL", "http://localhost:4566")
TEST_BUCKET = "test-canvas-bucket"


@pytest.fixture(scope="session")
def localstack_available():
    """Skip all integration tests if LocalStack is not running."""
    try:
        urllib.request.urlopen(f"{LOCALSTACK_URL}/_localstack/health", timeout=3)
    except Exception:
        pytest.skip("LocalStack not running")


@pytest.fixture(scope="session")
def s3_client(localstack_available):
    """Real boto3 S3 client pointed at LocalStack."""
    return boto3.client(
        "s3",
        endpoint_url=LOCALSTACK_URL,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
        config=Config(retries={"max_attempts": 0}),
    )


@pytest.fixture(scope="session")
def s3_bucket(s3_client):
    """Create test bucket, tear down after session."""
    with contextlib.suppress(s3_client.exceptions.BucketAlreadyOwnedByYou):
        s3_client.create_bucket(Bucket=TEST_BUCKET)
    yield TEST_BUCKET
    # Cleanup: delete all objects then bucket
    with contextlib.suppress(Exception):
        response = s3_client.list_objects_v2(Bucket=TEST_BUCKET)
        for obj in response.get("Contents", []):
            s3_client.delete_object(Bucket=TEST_BUCKET, Key=obj["Key"])
        s3_client.delete_bucket(Bucket=TEST_BUCKET)


@pytest.fixture
def clean_rate_limit_data(s3_client, s3_bucket):
    """Remove rate-limit key before and after each test."""
    key = "rate-limit/jsonData.json"
    with contextlib.suppress(Exception):
        s3_client.delete_object(Bucket=s3_bucket, Key=key)
    yield
    with contextlib.suppress(Exception):
        s3_client.delete_object(Bucket=s3_bucket, Key=key)
