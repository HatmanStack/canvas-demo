"""Tests for rate limiter with optimistic locking."""

import json
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from botocore.exceptions import ClientError

from src.utils.exceptions import RateLimitError


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
            "ETag": '"abc123"',
            "Body": MagicMock(
                read=lambda: json.dumps({"premium": [], "standard": []}).encode()
            ),
        }

        with patch("requests.put") as mock_put:
            mock_put.return_value = MagicMock(status_code=200)
            mock_put.return_value.raise_for_status = MagicMock()

            limiter = OptimizedRateLimiter()
            # Should not raise
            limiter.check_rate_limit(rate_limit_request_body)

    def test_check_rate_limit_blocks_over_limit(
        self, mock_config, mock_rate_limiter_deps, rate_limit_request_body
    ):
        """Test that requests over limit raise RateLimitError."""
        from src.services.rate_limiter import OptimizedRateLimiter

        mock_config.rate_limit = 5
        _, mock_s3 = mock_rate_limiter_deps

        # Simulate 5 existing standard requests (at limit)
        current_time = time.time()
        existing_requests = [current_time - i for i in range(5)]
        mock_s3.get_object.return_value = {
            "ETag": '"abc123"',
            "Body": MagicMock(
                read=lambda: json.dumps(
                    {"premium": [], "standard": existing_requests}
                ).encode()
            ),
        }

        limiter = OptimizedRateLimiter()
        with pytest.raises(RateLimitError):
            limiter.check_rate_limit(rate_limit_request_body)

    def test_premium_requests_count_double(
        self, mock_config, mock_rate_limiter_deps, premium_rate_limit_request_body
    ):
        """Test that premium requests count as 2 against limit."""
        from src.services.rate_limiter import OptimizedRateLimiter

        mock_config.rate_limit = 3
        _, mock_s3 = mock_rate_limiter_deps

        # 1 premium = 2 weighted, adding another premium (2) = 4 > 3
        current_time = time.time()
        mock_s3.get_object.return_value = {
            "ETag": '"abc123"',
            "Body": MagicMock(
                read=lambda: json.dumps(
                    {"premium": [current_time], "standard": []}
                ).encode()
            ),
        }

        limiter = OptimizedRateLimiter()
        with pytest.raises(RateLimitError):
            limiter.check_rate_limit(premium_rate_limit_request_body)

    def test_old_entries_cleaned(
        self, mock_config, mock_rate_limiter_deps, rate_limit_request_body
    ):
        """Test that entries older than window are cleaned."""
        from src.services.rate_limiter import OptimizedRateLimiter

        mock_config.rate_limit = 5
        _, mock_s3 = mock_rate_limiter_deps

        # Old entries (25 minutes ago, outside 20-minute window)
        old_time = time.time() - 1500
        mock_s3.get_object.return_value = {
            "ETag": '"abc123"',
            "Body": MagicMock(
                read=lambda: json.dumps(
                    {"premium": [], "standard": [old_time] * 10}
                ).encode()
            ),
        }

        with patch("requests.put") as mock_put:
            mock_put.return_value = MagicMock(status_code=200)
            mock_put.return_value.raise_for_status = MagicMock()

            limiter = OptimizedRateLimiter()
            # Should not raise - old entries should be cleaned
            limiter.check_rate_limit(rate_limit_request_body)

    def test_optimistic_lock_retry_on_conflict(
        self, mock_config, mock_rate_limiter_deps, rate_limit_request_body
    ):
        """Test retry on optimistic lock conflict (412)."""
        from src.services.rate_limiter import OptimizedRateLimiter

        _, mock_s3 = mock_rate_limiter_deps
        mock_s3.get_object.return_value = {
            "ETag": '"abc123"',
            "Body": MagicMock(
                read=lambda: json.dumps({"premium": [], "standard": []}).encode()
            ),
        }

        call_count = 0

        def mock_put_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            if call_count < 3:
                response.status_code = 412  # Precondition Failed
            else:
                response.status_code = 200
                response.raise_for_status = MagicMock()
            return response

        with patch("requests.put", side_effect=mock_put_response):
            limiter = OptimizedRateLimiter()
            limiter.check_rate_limit(rate_limit_request_body)

        assert call_count == 3  # Should have retried

    def test_initializes_on_no_such_key(
        self, mock_config, mock_rate_limiter_deps, rate_limit_request_body
    ):
        """Test initialization when rate limit file doesn't exist."""
        from src.services.rate_limiter import OptimizedRateLimiter

        _, mock_s3 = mock_rate_limiter_deps

        error_response = {"Error": {"Code": "NoSuchKey", "Message": "Not found"}}
        mock_s3.get_object.side_effect = ClientError(error_response, "GetObject")

        limiter = OptimizedRateLimiter()
        # Should not raise - should initialize
        limiter.check_rate_limit(rate_limit_request_body)

        # Should have called put_object to initialize
        mock_s3.put_object.assert_called_once()

    def test_get_current_usage_empty(self, mock_config, mock_rate_limiter_deps):
        """Test get_current_usage with no requests."""
        from src.services.rate_limiter import OptimizedRateLimiter

        _, mock_s3 = mock_rate_limiter_deps
        mock_s3.get_object.return_value = {
            "ETag": '"abc123"',
            "Body": MagicMock(
                read=lambda: json.dumps({"premium": [], "standard": []}).encode()
            ),
        }

        limiter = OptimizedRateLimiter()
        usage = limiter.get_current_usage()

        assert usage["premium_requests"] == 0
        assert usage["standard_requests"] == 0
        assert usage["total_usage"] == 0
        assert usage["remaining"] == mock_config.rate_limit

    def test_get_current_usage_with_requests(self, mock_config, mock_rate_limiter_deps):
        """Test get_current_usage with existing requests."""
        from src.services.rate_limiter import OptimizedRateLimiter

        mock_config.rate_limit = 20
        _, mock_s3 = mock_rate_limiter_deps

        current_time = time.time()
        mock_s3.get_object.return_value = {
            "ETag": '"abc123"',
            "Body": MagicMock(
                read=lambda: json.dumps(
                    {
                        "premium": [current_time],
                        "standard": [current_time, current_time],
                    }
                ).encode()
            ),
        }

        limiter = OptimizedRateLimiter()
        usage = limiter.get_current_usage()

        assert usage["premium_requests"] == 1
        assert usage["standard_requests"] == 2
        assert usage["total_usage"] == 4  # 1*2 + 2*1
        assert usage["remaining"] == 16

    def test_invalid_json_raises_error(self, mock_config, mock_rate_limiter_deps):
        """Test that invalid JSON in request raises RateLimitError."""
        from src.services.rate_limiter import OptimizedRateLimiter

        limiter = OptimizedRateLimiter()
        with pytest.raises(RateLimitError, match="Invalid request format"):
            limiter.check_rate_limit("not valid json")
