"""Shared test fixtures for Canvas Demo application."""

import base64
import io
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

# Set environment variables before any imports that use config
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test-secret-key")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("BUCKET_REGION", "us-west-2")
os.environ.setdefault("NOVA_IMAGE_BUCKET", "test-bucket")


@pytest.fixture(autouse=True)
def _reset_config_between_tests():
    """Reset config singleton between tests for isolation."""
    from src.models.config import reset_config

    reset_config()
    yield
    reset_config()


@pytest.fixture
def mock_config():
    """Mock application configuration for tests that need custom config values."""
    with patch.dict(
        os.environ,
        {
            "AWS_ACCESS_KEY_ID": "test-access-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret-key",
            "AWS_REGION": "us-east-1",
            "BUCKET_REGION": "us-west-2",
            "NOVA_IMAGE_BUCKET": "test-bucket",
            "RATE_LIMIT": "20",
            "IS_LAMBDA": "false",
            "ENABLE_NSFW_CHECK": "false",
        },
    ):
        from src.models.config import get_config, reset_config

        reset_config()
        mock = get_config()
        yield mock


@pytest.fixture
def mock_boto3_client():
    """Mock boto3 client for all AWS services."""
    with patch("boto3.client") as mock:
        yield mock


@pytest.fixture
def mock_s3_client():
    """Mock S3 client with common operations."""
    mock = MagicMock()
    mock.get_object.return_value = {
        "Body": MagicMock(read=lambda: json.dumps({"premium": [], "standard": []}).encode()),
    }
    mock.put_object.return_value = {}
    return mock


@pytest.fixture
def sample_image():
    """Create a sample RGB PIL Image for testing."""
    return Image.new("RGB", (512, 512), color="red")


@pytest.fixture
def sample_rgba_image():
    """Create a sample RGBA PIL Image for testing."""
    return Image.new("RGBA", (512, 512), color=(255, 0, 0, 128))


@pytest.fixture
def small_image():
    """Create a small image that needs resizing."""
    return Image.new("RGB", (100, 100), color="blue")


@pytest.fixture
def large_image():
    """Create a large image that exceeds max pixels."""
    return Image.new("RGB", (3000, 3000), color="green")


@pytest.fixture
def sample_image_bytes(sample_image):
    """Get sample image as bytes."""
    buffer = io.BytesIO()
    sample_image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def sample_image_base64(sample_image_bytes):
    """Get sample image as base64 string."""
    return base64.b64encode(sample_image_bytes).decode("utf-8")


@pytest.fixture
def mock_bedrock_response(sample_image_base64):
    """Sample Bedrock image generation response."""
    response_body = json.dumps({"images": [sample_image_base64]}).encode()
    return {
        "body": MagicMock(read=lambda: response_body),
    }


@pytest.fixture
def mock_bedrock_text_response():
    """Sample Bedrock text generation response."""
    return {"output": {"message": {"content": [{"text": "A beautiful sunset over mountains"}]}}}


@pytest.fixture
def rate_limit_request_body():
    """Sample request body for rate limiting tests."""
    return json.dumps(
        {
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {"text": "test prompt"},
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": 1024,
                "width": 1024,
                "quality": "standard",
                "cfgScale": 8.0,
                "seed": 0,
            },
        }
    )


@pytest.fixture
def premium_rate_limit_request_body():
    """Sample premium request body for rate limiting tests."""
    return json.dumps(
        {
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {"text": "test prompt"},
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": 1024,
                "width": 1024,
                "quality": "premium",
                "cfgScale": 8.0,
                "seed": 0,
            },
        }
    )
