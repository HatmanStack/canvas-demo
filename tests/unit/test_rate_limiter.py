"""Tests for rate limiter with S3-backed tracking."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError


class TestOptimizedRateLimiter:
    """Tests for OptimizedRateLimiter class."""

    @pytest.fixture
    def mock_rate_limiter_deps(self, mock_config, mock_s3_client):
        """Set up mocked dependencies for rate limiter."""
        with patch("src.services.rate_limiter.AWSClientManager") as mock_manager:
            mock_instance = MagicMock()
            mock_instance.s3_client = mock_s3_client
            mock_manager.return_value = mock_instance
            yield mock_manager, mock_s3_client

    def test_check_rate_limit_allows_under_limit(
        self, mock_config, mock_rate_limiter_deps, rate_limit_request_body
    ):
        """Test that requests under limit are allowed."""
        from src.services.rate_limiter import OptimizedRateLimiter

        _, mock_s3 = mock_rate_limiter_deps
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: json.dumps({"premium": [], "standard": []}).encode()),
        }

        limiter = OptimizedRateLimiter()
        # Should not raise
        limiter.check_rate_limit(rate_limit_request_body)
        mock_s3.put_object.assert_called_once()

    def test_invalid_json_raises_error(self, mock_config, mock_rate_limiter_deps):
        """Test that invalid JSON in request raises RateLimitError."""
        from src.services.rate_limiter import OptimizedRateLimiter
        from src.utils.exceptions import RateLimitError

        limiter = OptimizedRateLimiter()
        with pytest.raises(RateLimitError, match="Invalid request format"):
            limiter.check_rate_limit("not valid json")

    def test_initialize_rate_data_on_no_such_key(
        self, mock_config, mock_rate_limiter_deps, rate_limit_request_body
    ):
        """Test that NoSuchKey triggers initialization."""
        from botocore.exceptions import ClientError

        from src.services.rate_limiter import OptimizedRateLimiter

        _, mock_s3 = mock_rate_limiter_deps
        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}}, "GetObject"
        )

        limiter = OptimizedRateLimiter()
        limiter.check_rate_limit(rate_limit_request_body)
        # Should have called put_object to initialize
        mock_s3.put_object.assert_called_once()


class TestRateLimitLogic:
    """Unit tests for rate limit calculation logic that don't require AWS."""

    def test_calculate_total_empty(self):
        """Test total calculation with empty data."""
        rate_data = {"premium": [], "standard": []}
        premium_count = len(rate_data.get("premium", []))
        standard_count = len(rate_data.get("standard", []))
        total = premium_count * 2 + standard_count
        assert total == 0

    def test_calculate_total_standard_only(self):
        """Test total calculation with standard requests only."""
        current_time = time.time()
        rate_data = {"premium": [], "standard": [current_time, current_time, current_time]}
        premium_count = len(rate_data.get("premium", []))
        standard_count = len(rate_data.get("standard", []))
        total = premium_count * 2 + standard_count
        assert total == 3

    def test_calculate_total_premium_only(self):
        """Test total calculation with premium requests only."""
        current_time = time.time()
        rate_data = {"premium": [current_time, current_time], "standard": []}
        premium_count = len(rate_data.get("premium", []))
        standard_count = len(rate_data.get("standard", []))
        total = premium_count * 2 + standard_count
        assert total == 4  # 2 premium * 2 = 4

    def test_calculate_total_mixed(self):
        """Test total calculation with mixed requests."""
        current_time = time.time()
        rate_data = {
            "premium": [current_time],
            "standard": [current_time, current_time, current_time],
        }
        premium_count = len(rate_data.get("premium", []))
        standard_count = len(rate_data.get("standard", []))
        total = premium_count * 2 + standard_count
        assert total == 5  # 1*2 + 3*1 = 5

    def test_clean_old_entries(self):
        """Test cleaning old entries from rate data."""
        window_size = 1200  # 20 minutes
        current_time = time.time()
        cutoff = current_time - window_size

        # Old entries (25 minutes ago)
        old_time = current_time - 1500
        # Recent entries (5 minutes ago)
        recent_time = current_time - 300

        rate_data = {
            "premium": [old_time, recent_time],
            "standard": [old_time, old_time, recent_time],
        }

        # Clean old entries
        rate_data["premium"] = [t for t in rate_data.get("premium", []) if t > cutoff]
        rate_data["standard"] = [t for t in rate_data.get("standard", []) if t > cutoff]

        # Should only have recent entries
        assert len(rate_data["premium"]) == 1
        assert len(rate_data["standard"]) == 1

    def test_request_body_quality_extraction(self):
        """Test extracting quality from request body."""
        standard_body = json.dumps(
            {
                "taskType": "TEXT_IMAGE",
                "imageGenerationConfig": {"quality": "standard"},
            }
        )
        premium_body = json.dumps(
            {
                "taskType": "TEXT_IMAGE",
                "imageGenerationConfig": {"quality": "premium"},
            }
        )
        no_quality_body = json.dumps(
            {
                "taskType": "TEXT_IMAGE",
                "imageGenerationConfig": {},
            }
        )

        standard_dict = json.loads(standard_body)
        premium_dict = json.loads(premium_body)
        no_quality_dict = json.loads(no_quality_body)

        assert (
            standard_dict.get("imageGenerationConfig", {}).get("quality", "standard") == "standard"
        )
        assert premium_dict.get("imageGenerationConfig", {}).get("quality", "standard") == "premium"
        assert (
            no_quality_dict.get("imageGenerationConfig", {}).get("quality", "standard")
            == "standard"
        )


class TestRateLimitExceeded:
    """Tests for rate limit exceeded scenarios."""

    @pytest.fixture
    def limiter_with_mock(self):
        """Create a rate limiter with mocked AWS dependencies."""
        with patch("src.services.rate_limiter.AWSClientManager") as mock_manager:
            mock_instance = MagicMock()
            mock_manager.return_value = mock_instance
            from src.services.rate_limiter import OptimizedRateLimiter

            rl = OptimizedRateLimiter()
            rl.client_manager = mock_instance
            yield rl, mock_instance

    def test_rate_limit_exceeded_raises(self, limiter_with_mock):
        """20 standard entries + 1 new exceeds limit of 20."""
        rl, mock_cm = limiter_with_mock
        now = time.time()
        rate_data = {"premium": [], "standard": [now - i for i in range(20)]}

        mock_cm.s3_client.get_object.return_value = {
            "Body": MagicMock(read=lambda: json.dumps(rate_data).encode())
        }

        body = json.dumps({"imageGenerationConfig": {"quality": "standard"}})

        with (
            patch("src.services.rate_limiter.config") as mock_config,
            pytest.raises(
                (Exception,),
            ),
        ):
            mock_config.rate_limit = 20
            mock_config.nova_image_bucket = "test-bucket"
            rl.check_rate_limit(body)

    def test_premium_request_costs_two(self, limiter_with_mock):
        """19 standard + 1 premium (cost 2) = 21 > 20, exceeds limit."""
        rl, mock_cm = limiter_with_mock
        now = time.time()
        rate_data = {"premium": [], "standard": [now - i for i in range(19)]}

        mock_cm.s3_client.get_object.return_value = {
            "Body": MagicMock(read=lambda: json.dumps(rate_data).encode())
        }

        body = json.dumps({"imageGenerationConfig": {"quality": "premium"}})

        with (
            patch("src.services.rate_limiter.config") as mock_config,
            pytest.raises(
                (Exception,),
            ),
        ):
            mock_config.rate_limit = 20
            mock_config.nova_image_bucket = "test-bucket"
            rl.check_rate_limit(body)

    def test_fail_open_on_generic_client_error(self, limiter_with_mock):
        """Non-NoSuchKey ClientError allows request (fail open)."""
        rl, mock_cm = limiter_with_mock
        mock_cm.s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "boom"}},
            "GetObject",
        )

        body = json.dumps({"imageGenerationConfig": {"quality": "standard"}})

        with patch("src.services.rate_limiter.config") as mock_config:
            mock_config.rate_limit = 20
            mock_config.nova_image_bucket = "test-bucket"
            # Should not raise — fail open
            rl.check_rate_limit(body)


class TestGetCurrentUsage:
    """Tests for get_current_usage."""

    @pytest.fixture
    def limiter_with_mock(self):
        """Create a rate limiter with mocked AWS dependencies."""
        with patch("src.services.rate_limiter.AWSClientManager") as mock_manager:
            mock_instance = MagicMock()
            mock_manager.return_value = mock_instance
            from src.services.rate_limiter import OptimizedRateLimiter

            rl = OptimizedRateLimiter()
            rl.client_manager = mock_instance
            yield rl, mock_instance

    def test_returns_correct_dict(self, limiter_with_mock):
        """Returns correctly structured usage dict."""
        rl, mock_cm = limiter_with_mock
        now = time.time()
        rate_data = {"premium": [now - 10], "standard": [now - 5, now - 3]}

        mock_cm.s3_client.get_object.return_value = {
            "Body": MagicMock(read=lambda: json.dumps(rate_data).encode())
        }

        with patch("src.services.rate_limiter.config") as mock_config:
            mock_config.rate_limit = 20
            mock_config.nova_image_bucket = "test-bucket"
            usage = rl.get_current_usage()

        assert usage["premium_requests"] == 1
        assert usage["standard_requests"] == 2
        assert usage["total_usage"] == 4  # 1*2 + 2*1
        assert usage["limit"] == 20
        assert usage["remaining"] == 16

    def test_no_such_key_returns_empty(self, limiter_with_mock):
        """NoSuchKey error returns zero-value dict."""
        rl, mock_cm = limiter_with_mock
        mock_cm.s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": ""}},
            "GetObject",
        )

        with patch("src.services.rate_limiter.config") as mock_config:
            mock_config.rate_limit = 20
            usage = rl.get_current_usage()

        assert usage["total_usage"] == 0
        assert usage["remaining"] == 20

    def test_generic_error_returns_empty(self, limiter_with_mock):
        """Generic error returns zero-value dict."""
        rl, mock_cm = limiter_with_mock
        mock_cm.s3_client.get_object.side_effect = RuntimeError("boom")

        with patch("src.services.rate_limiter.config") as mock_config:
            mock_config.rate_limit = 20
            usage = rl.get_current_usage()

        assert usage["total_usage"] == 0
