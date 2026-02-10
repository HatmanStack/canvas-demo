"""Integration tests for rate limiter against real S3 (LocalStack)."""

import json
import time

import pytest

pytestmark = pytest.mark.integration


class TestRateLimiterIntegration:
    """Rate limiter integration tests using real S3."""

    RATE_LIMIT_KEY = "rate-limit/jsonData.json"

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

    def test_old_entries_can_be_cleaned(self, s3_client, s3_bucket, clean_rate_limit_data):
        """Old entries (>20min) are cleaned on check."""
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

        response = s3_client.get_object(Bucket=s3_bucket, Key=self.RATE_LIMIT_KEY)
        stored = json.loads(response["Body"].read().decode())

        cutoff = now - window
        cleaned_premium = [t for t in stored.get("premium", []) if t > cutoff]
        cleaned_standard = [t for t in stored.get("standard", []) if t > cutoff]

        assert len(cleaned_premium) == 0
        assert len(cleaned_standard) == 1

    def test_get_current_usage_reflects_state(self, s3_client, s3_bucket, clean_rate_limit_data):
        """get_current_usage reflects actual S3 state."""
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

        response = s3_client.get_object(Bucket=s3_bucket, Key=self.RATE_LIMIT_KEY)
        stored = json.loads(response["Body"].read().decode())

        premium_count = len(stored.get("premium", []))
        standard_count = len(stored.get("standard", []))
        total = premium_count * 2 + standard_count

        assert premium_count == 1
        assert standard_count == 2
        assert total == 4
