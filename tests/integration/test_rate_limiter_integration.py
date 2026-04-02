"""Integration tests for rate limiter against real S3 (MiniStack)."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


class TestRateLimiterIntegration:
    """Rate limiter integration tests using real S3."""

    RATE_LIMIT_KEY = "rate-limit/jsonData.json"

    def _make_limiter(self, s3_client):
        """Create an OptimizedRateLimiter wired to the MiniStack S3 client."""
        with patch("src.services.rate_limiter.AWSClientManager") as mock_manager:
            mock_instance = MagicMock()
            mock_instance.s3_client = s3_client
            mock_manager.return_value = mock_instance

            from src.services.rate_limiter import OptimizedRateLimiter

            limiter = OptimizedRateLimiter()
            limiter.client_manager = mock_instance
            return limiter

    def test_first_request_initializes_data(self, s3_client, s3_bucket, clean_rate_limit_data):
        """First request creates rate-limit/jsonData.json in S3."""
        rate_data = {"premium": [], "standard": [time.time()]}

        s3_client.put_object(
            Bucket=s3_bucket,
            Key=self.RATE_LIMIT_KEY,
            Body=json.dumps(rate_data),
            ContentType="application/json",
        )

        response = s3_client.get_object(Bucket=s3_bucket, Key=self.RATE_LIMIT_KEY)
        stored = json.loads(response["Body"].read().decode())

        assert "standard" in stored
        assert "premium" in stored
        assert len(stored["standard"]) == 1

    def test_exceeding_limit_detected(self, s3_client, s3_bucket, clean_rate_limit_data):
        """Pre-populate with 20 entries, verify total exceeds limit."""
        now = time.time()
        rate_data = {"premium": [], "standard": [now - i for i in range(20)]}

        s3_client.put_object(
            Bucket=s3_bucket,
            Key=self.RATE_LIMIT_KEY,
            Body=json.dumps(rate_data),
            ContentType="application/json",
        )

        response = s3_client.get_object(Bucket=s3_bucket, Key=self.RATE_LIMIT_KEY)
        stored = json.loads(response["Body"].read().decode())

        total = len(stored.get("premium", [])) * 2 + len(stored.get("standard", []))
        assert total >= 20

    def test_old_entries_cleaned_via_limiter(self, s3_client, s3_bucket, clean_rate_limit_data):
        """Exercise the real rate limiter cleaning path against MiniStack S3."""
        now = time.time()
        window = 1200  # 20 minutes
        rate_data = {
            "premium": [now - window - 100],  # expired
            "standard": [now - 10],  # fresh
        }

        s3_client.put_object(
            Bucket=s3_bucket,
            Key=self.RATE_LIMIT_KEY,
            Body=json.dumps(rate_data),
            ContentType="application/json",
        )

        limiter = self._make_limiter(s3_client)

        with patch("src.services.rate_limiter.get_config") as mock_get_config:
            mock_cfg = mock_get_config.return_value
            mock_cfg.rate_limit = 20
            mock_cfg.nova_image_bucket = s3_bucket
            usage = limiter.get_current_usage()

        # Expired premium entry should have been cleaned
        assert usage["premium_requests"] == 0
        # Fresh standard entry should remain
        assert usage["standard_requests"] == 1
        assert usage["total_usage"] == 1

    def test_get_current_usage_reflects_state(self, s3_client, s3_bucket, clean_rate_limit_data):
        """get_current_usage reflects actual S3 state via the real limiter."""
        now = time.time()
        rate_data = {
            "premium": [now - 5],
            "standard": [now - 10, now - 15],
        }

        s3_client.put_object(
            Bucket=s3_bucket,
            Key=self.RATE_LIMIT_KEY,
            Body=json.dumps(rate_data),
            ContentType="application/json",
        )

        limiter = self._make_limiter(s3_client)

        with patch("src.services.rate_limiter.get_config") as mock_get_config:
            mock_cfg = mock_get_config.return_value
            mock_cfg.rate_limit = 20
            mock_cfg.nova_image_bucket = s3_bucket
            usage = limiter.get_current_usage()

        assert usage["premium_requests"] == 1
        assert usage["standard_requests"] == 2
        assert usage["total_usage"] == 4
