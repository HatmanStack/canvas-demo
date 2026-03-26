"""Unit tests for HealthCheck."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from src.handlers.health import HealthCheck


class TestHealthCheck:
    """Tests for HealthCheck class."""

    @pytest.fixture
    def mock_deps(self):
        """Mock external dependencies."""
        with (
            patch("src.handlers.health.AWSClientManager") as mock_manager,
            patch("src.handlers.health.rate_limiter") as mock_limiter,
            patch("src.handlers.health.config") as mock_config,
        ):
            # Setup config mock
            mock_config.aws_access_key_id = "test-key"
            mock_config.aws_secret_access_key = "test-secret"
            mock_config.nova_image_bucket = "test-bucket"
            mock_config.enable_nsfw_check = False
            mock_config.is_lambda = True
            mock_config.aws_region = "us-east-1"
            mock_config.bucket_region = "us-west-2"

            # Setup client manager mock
            mock_instance = MagicMock()
            mock_manager.return_value = mock_instance
            mock_instance.bedrock_client = MagicMock()
            mock_instance.s3_client.head_bucket.return_value = {}
            mock_instance.executor = None  # No executor by default

            # Setup rate limiter mock
            mock_limiter.get_current_usage.return_value = {
                "premium_requests": 0,
                "standard_requests": 0,
                "total_usage": 0,
                "limit": 100,
                "remaining": 100,
            }

            yield mock_manager, mock_limiter, mock_config

    def test_health_check_healthy(self, mock_deps):
        """Test healthy status response."""
        health = HealthCheck()
        status = health.get_health_status()

        assert status["status"] == "healthy"
        assert status["environment"] == "lambda"
        assert status["services"]["bedrock"]["status"] == "healthy"
        assert status["services"]["s3"]["status"] == "healthy"
        assert status["services"]["configuration"]["status"] == "healthy"

    def test_health_check_unhealthy_services(self, mock_deps):
        """Test degraded status when a service fails."""
        mock_manager, _, _ = mock_deps
        mock_instance = mock_manager.return_value

        # Simulate Bedrock failure
        type(mock_instance).bedrock_client = PropertyMock(
            side_effect=Exception("Connection failed")
        )

        health = HealthCheck()
        status = health.get_health_status()

        assert status["status"] == "degraded"
        assert status["services"]["bedrock"]["status"] == "unhealthy"

    def test_increment_counters(self):
        """Test request counter."""
        with patch("src.handlers.health.AWSClientManager"):
            health = HealthCheck()
            health.increment_request()
            health.increment_request()

            assert health.request_count == 2

    def test_simple_status(self, mock_deps):
        """Test simple status method."""
        health = HealthCheck()
        status = health.get_simple_status()

        assert status["status"] == "healthy"
        assert "timestamp" in status

    def test_health_check_exception_returns_error(self, mock_deps):
        """Test that exceptions in get_health_status return error dict."""
        _, mock_limiter, _ = mock_deps
        mock_limiter.get_current_usage.side_effect = RuntimeError("Unexpected")

        health = HealthCheck()
        status = health.get_health_status()

        assert status["status"] == "error"
        assert "Health check failed" in status["message"]

    def test_parallel_service_checks(self, mock_deps):
        """Test that service checks use executor when available."""
        mock_manager, _, _ = mock_deps
        mock_instance = mock_manager.return_value

        # Provide an executor
        mock_executor = MagicMock()
        mock_instance.executor = mock_executor

        # Mock the futures
        bedrock_future = MagicMock()
        bedrock_future.result.return_value = {"status": "healthy", "message": "OK"}
        s3_future = MagicMock()
        s3_future.result.return_value = {"status": "healthy", "message": "OK"}
        mock_executor.submit.side_effect = [bedrock_future, s3_future]

        health = HealthCheck()
        status = health.get_health_status()

        assert status["status"] == "healthy"
        assert mock_executor.submit.call_count == 2
