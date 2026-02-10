"""Tests for custom exceptions."""

import os

# Ensure test environment vars are set before any imports
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test-secret-key")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("NOVA_IMAGE_BUCKET", "test-bucket")

from src.utils.exceptions import (
    BedrockError,
    CanvasError,
    ConfigurationError,
    ExternalAPIError,
    ImageError,
    NSFWError,
    RateLimitError,
)


class TestCanvasError:
    """Tests for CanvasError base exception."""

    def test_basic_error(self):
        """Test basic error creation."""
        error = CanvasError("Test error")
        assert error.message == "Test error"
        assert error.error_code is None
        assert str(error) == "Test error"

    def test_error_with_code(self):
        """Test error with error code."""
        error = CanvasError("Test error", "TEST_CODE")
        assert error.message == "Test error"
        assert error.error_code == "TEST_CODE"


class TestImageError:
    """Tests for ImageError exception."""

    def test_inherits_from_canvas_error(self):
        """Test ImageError inherits from CanvasError."""
        error = ImageError("Image failed")
        assert isinstance(error, CanvasError)
        assert error.message == "Image failed"


class TestNSFWError:
    """Tests for NSFWError exception."""

    def test_default_message(self):
        """Test default NSFW message."""
        error = NSFWError()
        assert error.message == "Content flagged as inappropriate"
        assert error.error_code == "NSFW_DETECTED"

    def test_custom_message(self):
        """Test custom NSFW message."""
        error = NSFWError("Custom NSFW message")
        assert error.message == "Custom NSFW message"
        assert error.error_code == "NSFW_DETECTED"


class TestRateLimitError:
    """Tests for RateLimitError exception."""

    def test_default_message(self):
        """Test default rate limit message."""
        error = RateLimitError()
        assert error.message == "Rate limit exceeded"
        assert error.error_code == "RATE_LIMIT_EXCEEDED"


class TestConfigurationError:
    """Tests for ConfigurationError exception."""

    def test_default_message(self):
        """Test default configuration error message."""
        error = ConfigurationError()
        assert error.message == "Configuration error"
        assert error.error_code == "CONFIG_ERROR"


class TestExternalAPIError:
    """Tests for ExternalAPIError exception."""

    def test_with_service(self):
        """Test external API error with service name."""
        error = ExternalAPIError("API failed", "huggingface")
        assert error.message == "API failed"
        assert error.service == "huggingface"
        assert error.error_code == "EXTERNAL_API_ERROR"


class TestBedrockError:
    """Tests for BedrockError exception."""

    def test_default_message(self):
        """Test default Bedrock error message."""
        error = BedrockError()
        assert error.message == "Bedrock service error"
        assert error.service == "bedrock"
