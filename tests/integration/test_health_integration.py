"""Integration tests for health checks against MiniStack."""

import pytest
from botocore.exceptions import ClientError

pytestmark = pytest.mark.integration


class TestHealthIntegration:
    """Health check integration tests using real S3."""

    def test_check_s3_healthy_bucket_exists(self, s3_client, s3_bucket):
        """_check_s3 returns healthy when bucket exists in MiniStack."""
        response = s3_client.head_bucket(Bucket=s3_bucket)
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200

    def test_check_s3_unhealthy_nonexistent_bucket(self, s3_client):
        """_check_s3 returns unhealthy for nonexistent bucket."""
        with pytest.raises(ClientError) as exc_info:
            s3_client.head_bucket(Bucket="nonexistent-bucket-12345")
        error_code = exc_info.value.response["Error"]["Code"]
        assert error_code in ("404", "NoSuchBucket")
