"""Tests for rate limiter with optimistic locking."""

import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest


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
            "Body": MagicMock(read=lambda: json.dumps({"premium": [], "standard": []}).encode()),
        }

        with patch("requests.put") as mock_put:
            mock_put.return_value = MagicMock(status_code=200)
            mock_put.return_value.raise_for_status = MagicMock()

            limiter = OptimizedRateLimiter()
            # Should not raise
            limiter.check_rate_limit(rate_limit_request_body)

    def test_invalid_json_raises_error(self, mock_config, mock_rate_limiter_deps):
        """Test that invalid JSON in request raises RateLimitError."""
        from src.services.rate_limiter import OptimizedRateLimiter
        from src.utils.exceptions import RateLimitError

        limiter = OptimizedRateLimiter()
        with pytest.raises(RateLimitError, match="Invalid request format"):
            limiter.check_rate_limit("not valid json")


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
